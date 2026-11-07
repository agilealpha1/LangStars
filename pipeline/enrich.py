#!/usr/bin/env python3
"""Step 2: add each repo's language byte breakdown (the /languages endpoint) -> data/repos.jsonl.

  GITHUB_TOKEN=... python3 pipeline/enrich.py
  python3 pipeline/enrich.py --refresh-all        # re-fetch every breakdown

Everything else the site needs (name, description, stars, forks, open issues, license, topics, created_at,
pushed_at, homepage) already comes from the search results in data/candidates.json.

With GITHUB_TOKEN: one GraphQL `nodes(ids: ...)` query per 50 repos returns the breakdown with linguist colors
(about 40 queries for ~2,000 repos). Without a token (GraphQL unavailable) it falls back to REST
GET /repositories/{id}/languages, which costs one call per repo against the 60/hour anonymous quota: it fetches
what the quota allows, most-starred first, and the rest keep their previous breakdown (or none) until next run.

A breakdown is reused while the repo's pushed_at hasn't changed: bytes only move when code is pushed.
"""
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, GitHub, log, read_json, read_jsonl, write_jsonl

TOP = 8              # keep the 8 largest languages per repo; the remainder shows as "Other"
BATCH = 50
FIELDS = ['id', 'node_id', 'full_name', 'html_url', 'description', 'stars', 'forks', 'open_issues', 'language', 'license',
          'topics', 'created_at', 'pushed_at', 'homepage', 'archived', 'default_branch']


def breakdown_from_rest(obj):
    """{"Python": 123, "C": 45} -> ([[name, bytes, None], ...] largest first, total bytes)."""
    pairs = sorted(((k, int(v)) for k, v in (obj or {}).items() if isinstance(v, (int, float))), key=lambda kv: (-kv[1], kv[0]))
    return [[k, v, None] for k, v in pairs[:TOP]], sum(v for _, v in pairs)


def breakdown_from_gql(node):
    langs = (node or {}).get('languages') or {}
    edges = [e for e in langs.get('edges') or [] if e and e.get('node')]
    rows = [[e['node']['name'], int(e['size']), e['node'].get('color')] for e in edges]
    rows.sort(key=lambda r: (-r[1], r[0]))
    return rows[:TOP], int(langs.get('totalSize') or sum(r[1] for r in rows))


GQL = """query($ids: [ID!]!) { nodes(ids: $ids) { ... on Repository { databaseId
  languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { totalSize edges { size node { name color } } } } } }"""


def fetch_gql(gh, repos):
    out = {}
    for i in range(0, len(repos), BATCH):
        chunk = [r for r in repos[i:i + BATCH] if r.get('node_id')]
        if not chunk:
            continue
        try:
            data = gh.graphql(GQL, {'ids': [r['node_id'] for r in chunk]})
        except Exception as e:                       # REST fallback picks these up
            log(f'GraphQL chunk {i // BATCH} failed: {e}'); continue
        for node in data.get('nodes') or []:
            if node and node.get('databaseId'):
                out[node['databaseId']] = breakdown_from_gql(node)
    return out


def rest_budget(gh):
    """Calls we can make without hitting the core rate limit (the GitHub client would otherwise sleep up to an hour)."""
    if gh.token:
        return 10 ** 9
    r = gh.get('/rate_limit')                        # free: doesn't count against the quota
    try:
        return max(0, int(r.json()['resources']['core']['remaining']) - 1)
    except Exception:
        return 0


def fetch_rest(gh, repos, budget):
    out = {}
    for r in repos[:budget]:
        resp = gh.get(f"/repositories/{r['id']}/languages")
        if resp.status_code == 200:
            out[r['id']] = breakdown_from_rest(resp.json())
        elif resp.status_code in (403, 429):
            log('REST quota used up; remaining repos keep their previous breakdown'); break
    return out


def needs_fetch(c, old, refresh_all=False):
    return refresh_all or not old or old.get('languages') is None or old.get('pushed_at') != c.get('pushed_at')


def merge_rows(cands, prev, fresh, now):
    rows = []
    for c in cands:
        row = {k: c.get(k) for k in FIELDS}
        old = prev.get(c['id']) or {}
        if c['id'] in fresh:
            row['languages'], row['lang_total'] = fresh[c['id']]
            row['languages_fetched_at'] = now
        else:
            row['languages'], row['lang_total'] = old.get('languages'), old.get('lang_total')
            row['languages_fetched_at'] = old.get('languages_fetched_at')
        rows.append(row)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--candidates', default=os.path.join(DATA, 'candidates.json'))
    ap.add_argument('--out', default=os.path.join(DATA, 'repos.jsonl'))
    ap.add_argument('--refresh-all', action='store_true')
    a = ap.parse_args(argv)

    cands = (read_json(a.candidates) or {}).get('repos') or sys.exit('no candidates; run discover.py first')
    prev = {r['id']: r for r in read_jsonl(a.out)}
    todo = sorted((c for c in cands if needs_fetch(c, prev.get(c['id']), a.refresh_all)),
                  key=lambda c: (prev.get(c['id'], {}).get('languages') is not None, -c['stars']))
    log(f'{len(cands)} repos; {len(todo)} need a language breakdown, {len(cands) - len(todo)} reused')

    gh, fresh = GitHub(), {}
    if todo and gh.token:
        fresh.update(fetch_gql(gh, todo))
        log(f'GraphQL: {len(fresh)}/{len(todo)} breakdowns')
    rest = [c for c in todo if c['id'] not in fresh]
    if rest:
        budget = rest_budget(gh)
        got = fetch_rest(gh, rest, budget)
        fresh.update(got)
        log(f'REST: {len(got)}/{len(rest)} breakdowns' + ('' if gh.token else f' (anonymous quota allowed {budget}; '
            'set GITHUB_TOKEN to fetch them all)'))

    rows = merge_rows(cands, prev, fresh, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    write_jsonl(a.out, rows)
    have = sum(1 for r in rows if r['languages'] is not None)
    log(f'{len(rows)} repos -> {os.path.relpath(a.out)} ({have} with a language breakdown, {len(rows) - have} pending)')


if __name__ == '__main__':
    main()

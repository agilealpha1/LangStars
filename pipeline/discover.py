#!/usr/bin/env python3
"""Step 1: find every repo with >= 20,000 stars whose primary language is one of pipeline/languages.py.

  GITHUB_TOKEN=... python3 pipeline/discover.py            # writes data/candidates.json
  python3 pipeline/discover.py --max-seconds 150           # stop early (exit 3); re-run to resume from .cache/search
  python3 pipeline/discover.py --only Rust,Go              # just these languages (merged into the existing file)

One Search API query per language (`language:<slug> stars:>=20000`). A query whose result set would exceed the
1,000-result cap is split into star ranges until each slice fits. Results are deduplicated by repo id, forks
are dropped, and archived repos are kept with `archived: true` (the site hides them by default). Only repos whose
API `language` equals the configured name are kept, so a loose qualifier match can't leak in.

Safety: if the new candidate list is less than 70% the size of the previous one, the old file is kept and the
script exits 1 (a broken token or API outage shouldn't wipe the site). --force overrides.
"""
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CACHE, DATA, MIN_STARS, GitHub, log, read_json, safe_url, sha, write_json
from languages import LANGUAGES

CAP = 1000          # the Search API never returns more than 1,000 results for one query


def normalize(item):
    lic = item.get('license') or {}
    return {
        'id': item['id'], 'node_id': item.get('node_id'), 'full_name': item['full_name'], 'html_url': safe_url(item.get('html_url')) or f"https://github.com/{item['full_name']}",
        'description': (item.get('description') or '').strip(), 'stars': item.get('stargazers_count', 0),
        'forks': item.get('forks_count', 0), 'open_issues': item.get('open_issues_count', 0), 'language': item.get('language'),
        'license': lic.get('spdx_id') if lic.get('spdx_id') not in (None, 'NOASSERTION') else (lic.get('name') or None),
        'topics': item.get('topics') or [], 'created_at': item.get('created_at'), 'pushed_at': item.get('pushed_at'),
        'homepage': safe_url(item.get('homepage')), 'archived': bool(item.get('archived')), 'fork': bool(item.get('fork')),
        'default_branch': item.get('default_branch') or 'main',
    }


def keep(repo, min_stars=MIN_STARS):
    """Inclusion rule. Archived repos stay (flagged); the site decides whether to show them."""
    return repo['stars'] >= min_stars and not repo['fork']


def merge(found, repo):
    """Deduplicate by repo id. A later sighting refreshes metadata (a rename keeps the same id)."""
    cur = found.get(repo['id'])
    if cur is None:
        found[repo['id']] = dict(repo)
    else:
        cur.update(repo)
    return found


class Searcher:
    def __init__(self, gh, ttl_hours=20, deadline=None):
        self.gh, self.ttl, self.deadline = gh, ttl_hours * 3600, deadline
        self.cdir = os.path.join(CACHE, 'search'); os.makedirs(self.cdir, exist_ok=True)
        self.queries = []                       # every (query, total_count) issued, for the log / tests

    def page(self, q, page):
        key = os.path.join(self.cdir, sha(f'{q}|{page}') + '.json')
        hit = read_json(key)
        if hit and time.time() - hit['t'] < self.ttl:
            return hit['data']
        if self.deadline and time.time() > self.deadline:
            raise TimeoutError
        r = self.gh.get('/search/repositories', params={'q': q, 'sort': 'stars', 'order': 'desc', 'per_page': 100, 'page': page})
        if r.status_code == 422:
            log(f'  422 for {q!r}: {r.text[:160]}'); data = {'total_count': 0, 'items': [], 'incomplete_results': False}
        else:
            r.raise_for_status(); data = r.json()
        if data.get('incomplete_results'):
            log(f'  warning: GitHub returned incomplete results for {q!r} (search timed out server-side)')
        write_json(key, {'t': time.time(), 'q': q, 'page': page, 'data': data})
        return data

    def search(self, base, lo=MIN_STARS, hi=None):
        """All results for `base` within stars lo..hi, splitting the range while a slice exceeds the 1,000 cap."""
        rng = f'stars:>={lo}' if hi is None else f'stars:{lo}..{hi}'
        q = f'{base} {rng}'
        first = self.page(q, 1)
        total = first.get('total_count', 0)
        self.queries.append((q, total))
        if total > CAP and (hi is None or hi > lo):
            mid = split_point(lo, hi)
            log(f'  {total} results for {q!r}; splitting at {mid}')
            return self.search(base, lo, mid) + self.search(base, mid + 1, hi)
        items = list(first.get('items', []))
        for p in range(2, min(10, -(-min(total, CAP) // 100)) + 1):
            items += self.page(q, p).get('items', [])
        return items


def split_point(lo, hi):
    """Where to cut stars lo..hi (hi=None means open-ended). Open ranges cut at 2x lo: star counts are long-tailed,
    so the lower half holds most repos and keeps splitting while the top slice is small."""
    return lo * 2 - 1 if hi is None else (lo + hi) // 2


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(DATA, 'candidates.json'))
    ap.add_argument('--max-seconds', type=float, default=0, help='stop early (exit 3) and resume on the next run')
    ap.add_argument('--only', default='', help='comma-separated language names to refresh (others kept from --out)')
    ap.add_argument('--force', action='store_true', help='write even if the result shrank by more than 30%%')
    a = ap.parse_args(argv)

    gh = GitHub()
    log('GitHub token:', 'yes' if gh.token else 'no (10 searches/min; set GITHUB_TOKEN for 30/min)')
    s = Searcher(gh, deadline=time.time() + a.max_seconds if a.max_seconds else None)
    only = {x.strip().lower() for x in a.only.split(',') if x.strip()}
    langs = [l for l in LANGUAGES if not only or l.name.lower() in only or l.slug in only]
    prev = read_json(a.out, {}) or {}
    found, per_lang, other = {}, {}, 0
    if only:                                   # keep the other languages' rows from the last run
        for r in prev.get('repos', []):
            if r.get('language') not in {l.name for l in langs}:
                merge(found, r)
    try:
        for lang in langs:
            items = s.search(f'language:{lang.slug}')
            n0 = len(found)
            for it in items:
                if it.get('language') != lang.name:       # qualifier aliases can match a neighbour; trust the API field
                    other += 1; continue
                merge(found, normalize(it))
            per_lang[lang.name] = len(found) - n0
            log(f'{lang.name:12} {len(items):5} hits, {len(found) - n0:5} new, {len(found)} total')
    except TimeoutError:
        log(f'time budget reached after {gh.calls} API calls; re-run to resume (cached pages are reused)')
        sys.exit(3)

    repos = sorted((r for r in found.values() if keep(r)), key=lambda r: (-r['stars'], r['full_name'].lower()))
    prev_n = len(prev.get('repos', []))
    if prev_n and len(repos) < 0.7 * prev_n and not a.force:
        log(f'ABORT: {len(repos)} candidates vs {prev_n} last time; keeping the previous file (use --force to override)')
        sys.exit(1)
    counts = {l.name: {'repos': sum(1 for r in repos if r['language'] == l.name),
                       'active': sum(1 for r in repos if r['language'] == l.name and not r['archived'])} for l in LANGUAGES}
    write_json(a.out, {'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'min_stars': MIN_STARS,
                       'counts': counts, 'repos': repos})
    log(f'{len(repos)} repos with >= {MIN_STARS} stars across {len(LANGUAGES)} languages '
        f'({other} hits with a different primary language skipped), {gh.calls} API calls -> {os.path.relpath(a.out)}')
    return counts


if __name__ == '__main__':
    main()

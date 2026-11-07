#!/usr/bin/env python3
"""Step 5: build the static site into site_dist/.

  python3 pipeline/build_site_data.py [--out site_dist]

Writes
  index.html, app.js, style.css,   copied from site/ (the whole app; relative paths, works under /LangStars/)
  vendor/fuse.min.js
  data/index.json                  slim list of every repo (archived ones flagged): what the pages filter and sort
  data/languages.json              per language: color, repo count, total stars, weekly gain, top repo
  data/r/<owner>__<name>.json      one file per repo: full description, language byte breakdown, star history
  data/stats.json                  totals, snapshot dates, type counts
  feed.xml                         RSS of repos that newly crossed the star threshold
  download/langstars-data.zip      CSV + JSON + star history, CC0

The site is built in a temporary sibling directory, validated (validate()), and only then swapped in, so a
failed build leaves the previous site_dist/ untouched.
"""
import argparse, csv, datetime as dt, io, json, os, re, shutil, sys, time, zipfile
from email.utils import format_datetime
from xml.sax.saxutils import escape as xesc
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, MIN_STARS, ROOT, log, read_json, read_jsonl, safe_url
from languages import BY_NAME, LANGUAGES, LINGUIST_COLORS
from taxonomy import TYPE_IDS, TYPE_LABELS, TYPES, rule_type

OUT = os.path.join(ROOT, 'site_dist')
SITE = os.path.join(ROOT, 'site')
STATIC = ['index.html', 'app.js', 'style.css', 'vendor/fuse.min.js']   # validate() checks these exist
SKIP = {'data.json', '.DS_Store'}                                       # stale/generated files never shipped
SCHEMA_VERSION = 1
NONE = type(None)
INDEX_FIELDS = {'id': int, 'name': str, 'slug': str, 'url': str, 'desc': str, 'lang': str, 'type': str, 'stars': int,
                'gain': (int, NONE), 'forks': int, 'issues': int, 'license': (str, NONE), 'topics': list, 'created': str,
                'pushed': str, 'archived': bool, 'new': bool}
DETAIL_FIELDS = {'description': str, 'homepage': (str, NONE), 'topics': list, 'breakdown': (list, NONE), 'history': list,
                 'first_seen': (str, NONE), 'type_src': str}
LANG_FIELDS = {'name': str, 'slug': str, 'color': str, 'count': int, 'archived': int, 'stars': int, 'gain': (int, NONE),
               'top': (dict, NONE)}
ZIP_MEMBERS = {'langstars.csv', 'langstars.json', 'languages.json', 'stars-history.jsonl', 'LICENSE.txt', 'README.txt'}
CSV_COLUMNS = ['full_name', 'url', 'language', 'type', 'type_label', 'description', 'stars', 'weekly_gain', 'forks', 'open_issues',
               'license', 'topics', 'created_at', 'pushed_at', 'homepage', 'archived', 'language_breakdown', 'first_seen', 'type_source']
TOPICS_IN_INDEX = 20          # GitHub allows 20; all of them, so topic filters never miss a repo


def slug_of(full_name):
    return re.sub(r'[^A-Za-z0-9._-]', '-', full_name.replace('/', '__'))


def history_index(history):
    """id -> list of [date, stars]; plus first-seen date per id."""
    series, first = {}, {}
    for h in history:
        for rid, stars in h['stars'].items():
            series.setdefault(rid, []).append([h['date'], stars])
            first.setdefault(rid, h['date'])
    return series, first


def breakdown(langs, total):
    """[[name, bytes, color|None], ...] + total bytes -> [[name, percent, color], ...] plus 'Other' for the remainder.
    None (not fetched yet) stays None; a repo with no code (e.g. an awesome-list) gives []."""
    if langs is None:
        return None
    total = total or sum(row[1] for row in langs)
    if not total:
        return []
    out = []
    for row in langs:
        name, size, color = row[0], row[1], (row[2] if len(row) > 2 else None)
        pct = round(100 * size / total, 1)
        if pct >= 0.1:                                   # slivers that would print as "0%" go into Other
            out.append([name, pct, color or LINGUIST_COLORS.get(name) or '#8b8b8b'])
    other = round(100 - sum(p for _, p, _ in out), 1)
    if other >= 0.1:
        out.append(['Other', other, '#c4c4c4'])
    return out


def breakdown_text(bd):
    return '; '.join(f'{n} {p}%' for n, p, _ in bd or [])


def assemble(repos, labels, history):
    """Join repos + type labels + history into (index items, per-repo details). Pure; easy to test."""
    series, first_seen = history_index(history)
    last, prev = (history[-1] if history else None), (history[-2] if len(history) > 1 else None)
    items, details = [], {}
    for r in repos:
        if r.get('language') not in BY_NAME:          # language removed from languages.py
            continue
        rid = str(r['id'])
        lab = labels.get(rid) or {'type': rule_type(r), 'source': 'rules'}
        gain = None
        if last and prev and rid in last['stars'] and rid in prev['stars']:
            gain = last['stars'][rid] - prev['stars'][rid]
        fs = first_seen.get(rid)
        topics = [t for t in (r.get('topics') or []) if isinstance(t, str)]
        items.append({'id': int(r['id']), 'name': r['full_name'], 'slug': slug_of(r['full_name']),
                      'url': safe_url(r.get('html_url')) or f"https://github.com/{r['full_name']}",
                      'desc': r.get('description') or '', 'lang': r['language'],
                      'type': lab['type'] if lab.get('type') in TYPE_IDS else 'other',
                      'stars': int(r['stars']), 'gain': gain, 'forks': int(r.get('forks') or 0), 'issues': int(r.get('open_issues') or 0),
                      'license': r.get('license'), 'topics': topics[:TOPICS_IN_INDEX],
                      'created': (r.get('created_at') or '')[:10], 'pushed': (r.get('pushed_at') or '')[:10],
                      'archived': bool(r.get('archived')), 'new': bool(prev and fs == last['date'])})
        details[int(r['id'])] = {'description': r.get('description') or '', 'homepage': safe_url(r.get('homepage')), 'topics': topics,
                                 'breakdown': breakdown(r.get('languages'), r.get('lang_total')), 'history': series.get(rid, []),
                                 'first_seen': fs, 'type_src': lab.get('source') or 'rules', 'type_model': lab.get('model')}
    items.sort(key=lambda x: (-x['stars'], x['name'].lower()))
    return items, details


def language_rows(items, have_gain):
    """One row per configured language, archived repos excluded from count/stars/top."""
    out = []
    for l in LANGUAGES:
        rows = [i for i in items if i['lang'] == l.name]
        live = [i for i in rows if not i['archived']]
        top = live[0] if live else None
        out.append({'name': l.name, 'slug': l.slug, 'color': l.color, 'count': len(live), 'archived': len(rows) - len(live),
                    'stars': sum(i['stars'] for i in live),
                    'gain': sum(i['gain'] or 0 for i in live) if have_gain else None,
                    'top': top and {'name': top['name'], 'slug': top['slug'], 'stars': top['stars']}})
    return out


def rss(items, base, generated):
    k = f'{MIN_STARS // 1000}K'
    out = ['<?xml version="1.0" encoding="utf-8"?>', '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">', '<channel>',
           f'<title>LangStars: new over {k} stars</title>', f'<link>{xesc(base)}</link>',
           f'<atom:link href="{xesc(base)}feed.xml" rel="self" type="application/rss+xml"/>',
           f'<description>GitHub repos that newly crossed {MIN_STARS:,} stars, by primary language.</description>',
           '<language>en</language>', f'<lastBuildDate>{format_datetime(generated)}</lastBuildDate>']
    for r in items:
        when = format_datetime(dt.datetime.fromisoformat(r['first_seen']).replace(tzinfo=dt.timezone.utc))
        out += ['<item>', f"<title>{xesc(r['name'])} ({xesc(r['lang'])}, {r['stars']:,} stars)</title>",
                f"<link>{xesc(base)}#/r/{xesc(r['name'])}</link>", f"<guid isPermaLink=\"false\">langstars-repo-{r['id']}</guid>",
                f'<pubDate>{when}</pubDate>', f"<category>{xesc(r['lang'])}</category>",
                f"<description>{xesc(r['desc'])} ({xesc(r['url'])})</description>", '</item>']
    return '\n'.join(out + ['</channel>', '</rss>']) + '\n'


def data_zip(items, details, langs, history_path, generated):
    buf, stamp = io.BytesIO(), generated.timetuple()[:6]
    rows = []
    for r in items:
        d = details[r['id']]
        rows.append({'full_name': r['name'], 'url': r['url'], 'language': r['lang'], 'type': r['type'], 'type_label': TYPE_LABELS[r['type']],
                     'description': d['description'], 'stars': r['stars'], 'weekly_gain': '' if r['gain'] is None else r['gain'],
                     'forks': r['forks'], 'open_issues': r['issues'], 'license': r['license'] or '', 'topics': ';'.join(d['topics']),
                     'created_at': r['created'], 'pushed_at': r['pushed'], 'homepage': d['homepage'] or '',
                     'archived': str(r['archived']).lower(), 'language_breakdown': breakdown_text(d['breakdown']),
                     'first_seen': d['first_seen'] or '', 'type_source': d['type_src']})
    s = io.StringIO()
    w = csv.DictWriter(s, CSV_COLUMNS, lineterminator='\n'); w.writeheader(); w.writerows(rows)
    history = ''
    if os.path.exists(history_path):
        with open(history_path, encoding='utf-8') as f:
            history = f.read()
    as_json = [dict(x, topics=details[r['id']]['topics'], archived=r['archived'], weekly_gain=r['gain'],
                    language_breakdown=details[r['id']]['breakdown']) for x, r in zip(rows, items)]
    files = {
        'langstars.csv': s.getvalue(),
        'langstars.json': json.dumps(as_json, ensure_ascii=False, indent=1),
        'languages.json': json.dumps(langs, ensure_ascii=False, indent=1),
        'stars-history.jsonl': history,
        'LICENSE.txt': 'CC0 1.0 Universal (public domain dedication)\n\nTo the extent possible under law, the LangStars maintainers have '
                       'waived all copyright and related rights to this dataset.\nhttps://creativecommons.org/publicdomain/zero/1.0/\n\n'
                       'Repository names and descriptions belong to their authors; the dataset only catalogs public GitHub metadata.\n',
        'README.txt': f"LangStars open data, generated {generated:%Y-%m-%d %H:%M} UTC.\n\n"
                      f"langstars.csv / langstars.json  one row per repo ({len(rows)} repos with >= {MIN_STARS:,} stars, archived ones flagged)\n"
                      "languages.json                  per language: color, repo count, total stars, top repo\n"
                      "stars-history.jsonl             one line per weekly snapshot: {week, date, stars: {github_repo_id: stars}}\n\n"
                      "language is GitHub's primary language. type_source is 'llm' (Claude Haiku) or 'rules' (keyword fallback).\n"
                      "weekly_gain is empty until two snapshots exist; language_breakdown is empty until /languages was fetched.\n",
    }
    with zipfile.ZipFile(buf, 'w') as z:
        for name, text in files.items():
            zi = zipfile.ZipInfo(name, stamp); zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, text)
    return buf.getvalue()


def build(out, data_dir=DATA, site=SITE, base=None, now=None):
    now = now or dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    base = (base or os.environ.get('LS_BASE_URL') or './').rstrip('/') + '/'
    repos = read_jsonl(os.path.join(data_dir, 'repos.jsonl'))
    if not repos:
        raise ValueError('no data/repos.jsonl; run the pipeline first')
    labels = read_json(os.path.join(data_dir, 'labels', 'types.json'), {}) or {}
    hist_path = os.path.join(data_dir, 'history', 'stars.jsonl')
    history = sorted(read_jsonl(hist_path), key=lambda h: h['date'])
    last, prev = (history[-1] if history else None), (history[-2] if len(history) > 1 else None)
    items, details = assemble(repos, labels, history)
    langs = language_rows(items, have_gain=prev is not None)

    tmp = out.rstrip('/') + '.tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        os.makedirs(os.path.join(tmp, 'data', 'r')); os.makedirs(os.path.join(tmp, 'download'))

        def dump(rel, obj):
            with open(os.path.join(tmp, rel), 'w', encoding='utf-8') as f:
                json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))

        gen = now.strftime('%Y-%m-%dT%H:%M:%SZ')
        live = [i for i in items if not i['archived']]
        dump('data/index.json', {'schema': SCHEMA_VERSION, 'generated_at': gen, 'snapshot': last and last['date'],
                                 'prev_snapshot': prev and prev['date'], 'types': [{'id': t, 'label': l} for t, l, _ in TYPES],
                                 'repos': items})
        dump('data/languages.json', langs)
        for it in items:
            dump(f"data/r/{it['slug']}.json", dict(it, **details[it['id']]))
        srcs = {}
        for it in items:
            s = details[it['id']]['type_src']; srcs[s] = srcs.get(s, 0) + 1
        dump('data/stats.json', {'schema': SCHEMA_VERSION, 'generated_at': gen, 'repos': len(live), 'archived': len(items) - len(live),
                                 'total_stars': sum(i['stars'] for i in live), 'languages': len(LANGUAGES), 'min_stars': MIN_STARS,
                                 'snapshots': len(history), 'first_snapshot': history[0]['date'] if history else None,
                                 'last_snapshot': last and last['date'], 'prev_snapshot': prev and prev['date'],
                                 'new_this_week': sum(1 for i in live if i['new']),
                                 'by_type': {t: sum(1 for i in live if i['type'] == t) for t in TYPE_IDS}, 'type_sources': srcs,
                                 'with_breakdown': sum(1 for i in items if details[i['id']]['breakdown'] is not None),
                                 'types': [{'id': t, 'label': l, 'description': d} for t, l, d in TYPES]})
        # feed: repos first seen after the baseline snapshot, newest first
        fresh = [dict(it, first_seen=details[it['id']]['first_seen']) for it in live
                 if history and (details[it['id']]['first_seen'] or '') > history[0]['date']]
        fresh.sort(key=lambda x: (x['first_seen'], x['stars']), reverse=True)
        with open(os.path.join(tmp, 'feed.xml'), 'w', encoding='utf-8') as f:
            f.write(rss(fresh[:50], base, now))
        with open(os.path.join(tmp, 'download', 'langstars-data.zip'), 'wb') as f:
            f.write(data_zip(items, details, langs, hist_path, now))
        for d, dirs, files in os.walk(site):                         # the whole app, vendor/ included
            dirs[:] = [x for x in dirs if not x.startswith('.') and x != 'data']
            for f in files:
                if f in SKIP or f.startswith('.'):
                    continue
                src = os.path.join(d, f)
                dst = os.path.join(tmp, os.path.relpath(src, site))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)                             # content only, not the source mode
        open(os.path.join(tmp, '.nojekyll'), 'w').close()
        for d, dirs, files in os.walk(tmp):                          # servable regardless of the local umask
            os.chmod(d, 0o755)
            for f in files:
                os.chmod(os.path.join(d, f), 0o644)
        validate(tmp)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)     # never leave a half-built site around
        raise
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.replace(tmp, out)
    return {'repos': len(live), 'archived': len(items) - len(live), 'snapshots': len(history),
            'by_language': {l['name']: l['count'] for l in langs}}


def _check(cond, msg):
    if not cond:
        raise ValueError(msg)


def _types(obj, spec, where):
    for k, t in spec.items():
        _check(k in obj, f'{where}: missing {k}')
        _check(isinstance(obj[k], t) and not (t is int and isinstance(obj[k], bool)), f'{where}: {k} has type {type(obj[k]).__name__}')


def validate(out):
    """Schema check of a built site. Raises ValueError on the first problem; used by build() and the tests."""
    def load(rel):
        with open(os.path.join(out, rel), encoding='utf-8') as f:
            return json.load(f)
    idx = load('data/index.json')
    _check(idx.get('schema') == SCHEMA_VERSION and isinstance(idx.get('repos'), list), 'index.json: bad header')
    _check([t['id'] for t in idx.get('types', [])] == TYPE_IDS, 'index.json: types differ from taxonomy')
    repos = idx['repos']
    _check(len(repos) > 0, 'index.json: no repos')
    ids = set()
    for r in repos:
        _types(r, INDEX_FIELDS, f"index.json {r.get('name')}")
        _check(r['type'] in TYPE_IDS, f"{r['name']}: unknown type {r['type']}")
        _check(r['lang'] in BY_NAME, f"{r['name']}: language {r['lang']} not in languages.py")
        _check(all(isinstance(t, str) for t in r['topics']), f"{r['name']}: bad topics")
        _check(r['url'].startswith(('https://', 'http://')), f"{r['name']}: unsafe url")
        _check(r['stars'] >= 0 and r['id'] not in ids, f"{r['name']}: bad stars or duplicate id")
        ids.add(r['id'])
        p = os.path.join(out, 'data', 'r', r['slug'] + '.json')
        _check(os.path.exists(p), f'missing {p}')
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        _types(d, DETAIL_FIELDS, f'r/{r["slug"]}.json')
        _check(all(isinstance(h, list) and len(h) == 2 for h in d['history']), f"{r['slug']}: bad history")
        _check(d['homepage'] is None or d['homepage'].startswith(('https://', 'http://')), f"{r['slug']}: unsafe homepage {d['homepage']!r}")
        _check(d['breakdown'] is None or all(len(b) == 3 and isinstance(b[1], (int, float)) for b in d['breakdown']),
               f"{r['slug']}: bad breakdown")
    langs = load('data/languages.json')
    _check([l['name'] for l in langs] == [l.name for l in LANGUAGES], 'languages.json: languages differ from languages.py')
    for l in langs:
        _types(l, LANG_FIELDS, f"languages.json {l.get('name')}")
        _check(re.fullmatch(r'#[0-9A-Fa-f]{6}', l['color']) is not None, f"{l['name']}: bad color")
    live = [r for r in repos if not r['archived']]
    _check(sum(l['count'] for l in langs) == len(live), 'languages.json: counts do not add up')
    stats = load('data/stats.json')
    for k in ('generated_at', 'repos', 'archived', 'total_stars', 'snapshots', 'last_snapshot', 'by_type', 'type_sources', 'new_this_week'):
        _check(k in stats, f'stats.json: missing {k}')
    _check(stats['repos'] == len(live) and stats['archived'] == len(repos) - len(live), 'stats.json: repo count mismatch')
    _check(sum(stats['by_type'].values()) == len(live), 'stats.json: by_type does not add up')
    import xml.etree.ElementTree as ET
    ET.parse(os.path.join(out, 'feed.xml'))
    with zipfile.ZipFile(os.path.join(out, 'download', 'langstars-data.zip')) as z:
        _check(ZIP_MEMBERS <= set(z.namelist()), f'zip: missing {ZIP_MEMBERS - set(z.namelist())}')
        rows = list(csv.DictReader(io.StringIO(z.read('langstars.csv').decode('utf-8'))))
        _check(len(rows) == len(repos) and list(rows[0]) == CSV_COLUMNS, 'zip: csv rows/columns')
    for name in STATIC:
        _check(os.path.exists(os.path.join(out, name)), f'{name} missing')
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--data', default=DATA)
    a = ap.parse_args(argv)
    t = time.time()
    try:
        res = build(a.out, a.data)
    except (ValueError, OSError, KeyError) as e:
        log(f'BUILD FAILED, previous site kept: {e!r}')
        sys.exit(1)
    log(f"site_dist: {res['repos']} repos (+{res['archived']} archived), {res['snapshots']} snapshots, "
        f"{time.time() - t:.1f}s -> {os.path.relpath(a.out)}")
    log('  ' + ', '.join(f'{k} {v}' for k, v in res['by_language'].items()))


if __name__ == '__main__':
    main()

import csv, datetime as dt, io, json, os, shutil, tempfile, unittest, zipfile
import xml.etree.ElementTree as ET
from helpers import repo
import build_site_data as B, snapshot, taxonomy
from languages import LANGUAGES


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(''.join(json.dumps(r) + '\n' for r in rows))


class TestBuildOutput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data, self.out, self.site = (os.path.join(self.tmp, x) for x in ('data', 'site_dist', 'site'))
        os.makedirs(os.path.join(self.site, 'vendor'))
        for name, text in {'index.html': '<!doctype html><title>LangStars</title>', 'app.js': '//', 'style.css': '',
                           'vendor/fuse.min.js': '//', 'data.json': '{"stale": true}'}.items():
            with open(os.path.join(self.site, name), 'w') as f:
                f.write(text)
        self.repos = [
            repo('torvalds/linux', 1, stars=250000, language='C', description='Linux kernel source tree',
                 languages=[['C', 980, '#555555'], ['Assembly', 15, None]], lang_total=1000),
            repo('pallets/flask', 2, stars=70000, description='The Python micro framework for building web applications',
                 homepage='javascript:alert(1)', topics=['flask', 'python', 'web-framework']),
            repo('old/archived', 3, stars=40000, archived=True),
            repo('new/comer', 4, stars=20100, language='Rust', homepage='https://comer.dev', languages=[], lang_total=0),
            repo('x/elixir-thing', 5, stars=30000, language='Elixir'),               # language not configured: skipped
        ]
        write_jsonl(os.path.join(self.data, 'repos.jsonl'), self.repos)
        os.makedirs(os.path.join(self.data, 'labels'))
        with open(os.path.join(self.data, 'labels', 'types.json'), 'w') as f:
            json.dump({'1': {'type': 'systems', 'source': 'llm', 'model': 'claude-haiku-4-5'},
                       '2': {'type': 'not-a-type', 'source': 'rules'}}, f)       # 3, 4 get rule labels on the fly
        h = snapshot.add_snapshot([], [dict(r, stars=r['stars'] - 500) for r in self.repos[:3]], dt.date(2026, 11, 2))
        h = snapshot.add_snapshot(h, self.repos, dt.date(2026, 11, 9))
        write_jsonl(os.path.join(self.data, 'history', 'stars.jsonl'), h)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self):
        return B.build(self.out, self.data, site=self.site, base='https://example.github.io/LangStars',
                       now=dt.datetime(2026, 11, 9, 4, 0, tzinfo=dt.timezone.utc))

    def load(self, rel):
        with open(os.path.join(self.out, rel), encoding='utf-8') as f:
            return json.load(f)

    def test_index_schema_and_contents(self):
        self.build()
        self.assertTrue(B.validate(self.out))
        idx = self.load('data/index.json')
        self.assertEqual((idx['snapshot'], idx['prev_snapshot']), ('2026-11-09', '2026-11-02'))
        self.assertEqual([t['id'] for t in idx['types']], taxonomy.TYPE_IDS)
        by = {r['name']: r for r in idx['repos']}
        self.assertEqual([r['name'] for r in idx['repos']], ['torvalds/linux', 'pallets/flask', 'old/archived', 'new/comer'])
        for r in idx['repos']:
            self.assertEqual(set(r), set(B.INDEX_FIELDS))
        self.assertEqual(by['torvalds/linux']['gain'], 500)
        self.assertEqual(by['torvalds/linux']['type'], 'systems')
        self.assertEqual(by['pallets/flask']['type'], 'other')          # invalid label falls back to 'other'
        self.assertIsNone(by['new/comer']['gain'])
        self.assertTrue(by['new/comer']['new'])
        self.assertFalse(by['torvalds/linux']['new'])
        self.assertTrue(by['old/archived']['archived'])
        self.assertEqual(by['pallets/flask']['topics'], ['flask', 'python', 'web-framework'])

    def test_languages_json_excludes_archived_and_follows_config(self):
        self.build()
        langs = {l['name']: l for l in self.load('data/languages.json')}
        self.assertEqual(list(langs), [l.name for l in LANGUAGES])
        py = langs['Python']
        self.assertEqual((py['count'], py['archived'], py['stars'], py['gain']), (1, 1, 70000, 500))
        self.assertEqual(py['top'], {'name': 'pallets/flask', 'slug': 'pallets__flask', 'stars': 70000})
        self.assertEqual((langs['Go']['count'], langs['Go']['top']), (0, None))
        self.assertEqual(langs['C']['color'], '#555555')

    def test_gains_are_null_with_one_snapshot(self):
        hist = os.path.join(self.data, 'history', 'stars.jsonl')
        with open(hist) as f:
            first = f.readline()
        with open(hist, 'w') as f:
            f.write(first)
        self.build()
        self.assertTrue(all(r['gain'] is None and not r['new'] for r in self.load('data/index.json')['repos']))
        self.assertTrue(all(l['gain'] is None for l in self.load('data/languages.json')))
        self.assertEqual(self.load('data/stats.json')['snapshots'], 1)

    def test_per_repo_detail(self):
        self.build()
        d = self.load('data/r/torvalds__linux.json')
        self.assertTrue(set(B.DETAIL_FIELDS) <= set(d))
        self.assertEqual(d['history'], [['2026-11-02', 249500], ['2026-11-09', 250000]])
        self.assertEqual(d['breakdown'], [['C', 98.0, '#555555'], ['Assembly', 1.5, '#6E4C13'], ['Other', 0.5, '#c4c4c4']])
        self.assertIsNone(self.load('data/r/pallets__flask.json')['breakdown'])        # not fetched yet
        self.assertEqual(self.load('data/r/new__comer.json')['breakdown'], [])           # no code
        self.assertIsNone(self.load('data/r/pallets__flask.json')['homepage'])         # javascript: dropped
        self.assertEqual(self.load('data/r/new__comer.json')['homepage'], 'https://comer.dev')

    def test_stats_feed_zip_and_static_files(self):
        self.build()
        stats = self.load('data/stats.json')
        self.assertEqual((stats['repos'], stats['archived'], stats['snapshots'], stats['new_this_week']), (3, 1, 2, 1))
        self.assertEqual(stats['type_sources'], {'llm': 1, 'rules': 3})
        self.assertEqual(sum(stats['by_type'].values()), 3)
        items = ET.parse(os.path.join(self.out, 'feed.xml')).getroot().findall('./channel/item')
        self.assertEqual([i.findtext('title') for i in items], ['new/comer (Rust, 20,100 stars)'])
        self.assertTrue(items[0].findtext('link').startswith('https://example.github.io/LangStars/#/r/'))
        with zipfile.ZipFile(os.path.join(self.out, 'download', 'langstars-data.zip')) as z:
            self.assertTrue(B.ZIP_MEMBERS <= set(z.namelist()))
            rows = list(csv.DictReader(io.StringIO(z.read('langstars.csv').decode())))
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]['language_breakdown'], 'C 98.0%; Assembly 1.5%; Other 0.5%')
            self.assertIn('CC0', z.read('LICENSE.txt').decode())
        for f in ('index.html', 'app.js', 'style.css', 'vendor/fuse.min.js', '.nojekyll'):
            self.assertTrue(os.path.exists(os.path.join(self.out, f)), f)
        self.assertFalse(os.path.exists(os.path.join(self.out, 'data.json')))       # stale file not shipped

    def test_output_is_world_readable(self):
        os.chmod(os.path.join(self.site, 'index.html'), 0o600)
        self.build()
        for d, _, files in os.walk(self.out):
            self.assertEqual(os.stat(d).st_mode & 0o777, 0o755, d)
            for f in files:
                self.assertEqual(os.stat(os.path.join(d, f)).st_mode & 0o777, 0o644, f)

    def test_failed_build_keeps_previous_site(self):
        self.build()
        before = self.load('data/index.json')
        os.remove(os.path.join(self.site, 'vendor', 'fuse.min.js'))      # validation fails before the swap
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual(self.load('data/index.json'), before)
        self.assertFalse(os.path.exists(self.out + '.tmp'))

    def test_validate_rejects_broken_output(self):
        self.build()
        for mutate in (lambda i: i['repos'][0].update(type='nope'), lambda i: i['repos'][0].update(stars='1'),
                       lambda i: i['repos'][0].pop('gain'), lambda i: i['repos'][0].update(url='javascript:x')):
            idx = self.load('data/index.json'); mutate(idx)
            with open(os.path.join(self.out, 'data', 'index.json'), 'w') as f:
                json.dump(idx, f)
            with self.assertRaises(ValueError):
                B.validate(self.out)
            self.build()


class TestSnapshot(unittest.TestCase):
    def test_same_week_replaces_and_new_week_appends(self):
        r = [repo('a/b', 1, stars=10)]
        h = snapshot.add_snapshot([], r, dt.date(2026, 11, 2))                      # Monday, W45
        h = snapshot.add_snapshot(h, [dict(r[0], stars=11)], dt.date(2026, 11, 8))   # Sunday, still W45
        self.assertEqual((len(h), h[0]['stars']), (1, {'1': 11}))
        h = snapshot.add_snapshot(h, [dict(r[0], stars=15)], dt.date(2026, 11, 9))   # W46
        self.assertEqual([x['week'] for x in h], ['2026-W45', '2026-W46'])


if __name__ == '__main__':
    unittest.main()

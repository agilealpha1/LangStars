import re, unittest
from helpers import search_item
import discover
from common import safe_url


class TestDedupe(unittest.TestCase):
    def test_same_repo_twice_is_one_entry(self):
        found = {}
        for _ in range(3):
            discover.merge(found, discover.normalize(search_item('a/b', 1)))
        self.assertEqual(len(found), 1)

    def test_dedupe_is_by_id_so_renames_collapse_to_the_newest_name(self):
        found = {}
        discover.merge(found, discover.normalize(search_item('old/name', 7, stars=20500)))
        discover.merge(found, discover.normalize(search_item('new/name', 7, stars=20600)))
        self.assertEqual(len(found), 1)
        self.assertEqual((found[7]['full_name'], found[7]['stars']), ('new/name', 20600))

    def test_different_ids_with_the_same_name_stay_separate(self):
        found = {}
        discover.merge(found, discover.normalize(search_item('x/y', 1)))
        discover.merge(found, discover.normalize(search_item('x/y', 2)))
        self.assertEqual(len(found), 2)


class TestInclusionRule(unittest.TestCase):
    def test_keep(self):
        n = discover.normalize
        self.assertTrue(discover.keep(n(search_item('a/b', 1, stars=20000)), 20000))
        self.assertFalse(discover.keep(n(search_item('a/b', 1, stars=19999)), 20000))
        self.assertFalse(discover.keep(n(search_item('a/b', 1, fork=True)), 20000))
        self.assertTrue(discover.keep(n(search_item('a/b', 1, archived=True)), 20000))     # kept, flagged
        self.assertTrue(n(search_item('a/b', 1, archived=True))['archived'])

    def test_normalize_fields(self):
        r = discover.normalize(search_item('a/b', 1, license={'spdx_id': 'NOASSERTION', 'name': 'Other'}, description=None,
                                           homepage='javascript:alert(1)'))
        self.assertEqual((r['license'], r['description'], r['homepage'], r['open_issues'], r['node_id']), ('Other', '', None, 3, 'R_1'))
        self.assertIsNone(discover.normalize(search_item('a/b', 1, license=None))['license'])
        self.assertEqual(discover.normalize(search_item('a/b', 1, homepage='flashml.ai'))['homepage'], 'https://flashml.ai')


class FakeSearcher(discover.Searcher):
    """Pretends 2,500 repos have 20,000..22,499 stars (one per star count) to exercise range splitting."""
    LO, HI = 20000, 22499

    def __init__(self):
        self.calls, self.queries = [], []

    def page(self, q, page):
        self.calls.append((q, page))
        m = re.search(r'stars:(?:>=(\d+)|(\d+)\.\.(\d+))', q)
        lo = int(m.group(1) or m.group(2)); hi = int(m.group(3)) if m.group(3) else self.HI
        ids = list(range(max(lo, self.LO), min(hi, self.HI) + 1))
        chunk = ids[(page - 1) * 100: page * 100]
        return {'total_count': len(ids), 'items': [search_item(f'o/r{i}', i, stars=i) for i in chunk]}


class TestSearchSplitting(unittest.TestCase):
    def test_every_slice_fits_under_the_cap_and_nothing_is_lost_or_duplicated(self):
        s = FakeSearcher()
        items = s.search('language:python', lo=20000)
        ids = [it['id'] for it in items]
        self.assertEqual(len(ids), 2500)
        self.assertEqual(len(set(ids)), 2500)                    # slices don't overlap
        self.assertTrue(all(p <= 10 for _, p in s.calls))        # never asks past page 10
        totals = dict(s.queries)
        paged = {q for q, p in s.calls if p > 1}                  # only slices under the cap are paged through
        self.assertTrue(paged and all(totals[q] <= discover.CAP for q in paged))
        self.assertGreater(len(s.queries), 1, 'expected the query to be split')

    def test_small_result_is_not_split(self):
        s = FakeSearcher(); s.HI = 20450
        items = s.search('language:rust', lo=20000)
        self.assertEqual(len(items), 451)
        self.assertEqual(len(s.queries), 1)
        self.assertEqual(sorted({p for _, p in s.calls}), [1, 2, 3, 4, 5])

    def test_split_point(self):
        self.assertEqual(discover.split_point(20000, None), 39999)
        self.assertEqual(discover.split_point(20000, 30000), 25000)


class TestLanguageFilter(unittest.TestCase):
    def test_only_the_primary_language_is_kept(self):
        class S(FakeSearcher):
            def page(self, q, page):
                return {'total_count': 2, 'items': [search_item('a/py', 1), search_item('a/js', 2, language='JavaScript')]} if page == 1 else {'items': []}
        import tempfile, os, json
        d = tempfile.mkdtemp(); out = os.path.join(d, 'c.json')
        orig_s, orig_gh, orig_l = discover.Searcher, discover.GitHub, discover.LANGUAGES
        try:
            discover.Searcher = lambda gh, deadline=None: S()
            discover.GitHub = lambda: type('G', (), {'token': '', 'calls': 0})()
            discover.LANGUAGES = [l for l in orig_l if l.name == 'Python']
            discover.main(['--out', out])
            with open(out) as f:
                names = [r['full_name'] for r in json.load(f)['repos']]
        finally:
            discover.Searcher, discover.GitHub, discover.LANGUAGES = orig_s, orig_gh, orig_l
        self.assertEqual(names, ['a/py'])


class TestSafeUrl(unittest.TestCase):
    def test_only_http_urls_survive(self):
        self.assertEqual(safe_url('example.com/docs'), 'https://example.com/docs')
        self.assertEqual(safe_url(' https://ok.io/a?b=1 '), 'https://ok.io/a?b=1')
        for bad in ['javascript:alert(1)', 'data:text/html,x', 'mailto:a@b.c', 'https://', 'not a url', '', None]:
            self.assertIsNone(safe_url(bad), bad)


if __name__ == '__main__':
    unittest.main()

import unittest
from helpers import repo
import enrich


class TestBreakdownParsing(unittest.TestCase):
    def test_rest_sorted_largest_first_and_capped(self):
        rows, total = enrich.breakdown_from_rest({'C': 25, 'Python': 70, 'Shell': 5})
        self.assertEqual(rows, [['Python', 70, None], ['C', 25, None], ['Shell', 5, None]])
        self.assertEqual(total, 100)
        many = {f'L{i}': i + 1 for i in range(12)}
        rows, total = enrich.breakdown_from_rest(many)
        self.assertEqual(len(rows), enrich.TOP)
        self.assertEqual(total, sum(many.values()))             # total keeps the languages that were cut

    def test_graphql_keeps_colors(self):
        node = {'databaseId': 1, 'languages': {'totalSize': 100, 'edges': [
            {'size': 30, 'node': {'name': 'C', 'color': '#555555'}}, {'size': 70, 'node': {'name': 'Python', 'color': '#3572A5'}}]}}
        self.assertEqual(enrich.breakdown_from_gql(node), ([['Python', 70, '#3572A5'], ['C', 30, '#555555']], 100))

    def test_empty_repo(self):
        self.assertEqual(enrich.breakdown_from_rest({}), ([], 0))


class TestCaching(unittest.TestCase):
    def test_needs_fetch_only_when_missing_or_pushed(self):
        c = repo('a/b', 1)
        self.assertTrue(enrich.needs_fetch(c, None))
        self.assertTrue(enrich.needs_fetch(c, dict(c, languages=None)))
        self.assertFalse(enrich.needs_fetch(c, dict(c, languages=[['Python', 1, None]])))
        self.assertTrue(enrich.needs_fetch(c, dict(c, languages=[['Python', 1, None]], pushed_at='2020-01-01T00:00:00Z')))
        self.assertTrue(enrich.needs_fetch(c, dict(c, languages=[['Python', 1, None]]), refresh_all=True))

    def test_merge_keeps_previous_breakdown_when_not_refetched(self):
        cands = [repo('a/b', 1), repo('c/d', 2)]
        prev = {1: dict(cands[0], languages=[['Go', 9, None]], lang_total=9, languages_fetched_at='old')}
        fresh = {2: ([['Rust', 5, None]], 5)}
        rows = {r['id']: r for r in enrich.merge_rows(cands, prev, fresh, 'now')}
        self.assertEqual((rows[1]['languages'], rows[1]['languages_fetched_at']), ([['Go', 9, None]], 'old'))
        self.assertEqual((rows[2]['languages'], rows[2]['lang_total'], rows[2]['languages_fetched_at']), ([['Rust', 5, None]], 5, 'now'))
        self.assertTrue(set(enrich.FIELDS) <= set(rows[1]))


if __name__ == '__main__':
    unittest.main()

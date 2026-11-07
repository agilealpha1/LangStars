import json, unittest
from helpers import repo
import categorize, taxonomy


class TestRules(unittest.TestCase):
    def t(self, **kw):
        return taxonomy.rule_type(repo(kw.pop('full_name', 'o/x'), 1, **kw))

    def test_specific_types(self):
        self.assertEqual(self.t(full_name='vinta/awesome-python', description='A curated list of awesome Python frameworks'), 'learning')
        self.assertEqual(self.t(description='Tensors and dynamic neural networks in Python', topics=['deep-learning']), 'ai-ml')
        self.assertEqual(self.t(description='The open-source time series database', topics=['database']), 'database')
        self.assertEqual(self.t(description='Godot Engine – multi-platform 2D and 3D game engine'), 'game')
        self.assertEqual(self.t(description='Display and control your Android device'), 'mobile')
        self.assertEqual(self.t(description='Linux kernel source tree'), 'systems')
        self.assertEqual(self.t(description='The Web framework for perfectionists with deadlines'), 'framework')
        self.assertEqual(self.t(description='A command-line tool for downloading videos', topics=['cli']), 'tool')
        self.assertEqual(self.t(description='The library for web and native user interfaces'), 'library')
        self.assertEqual(self.t(description=''), 'other')

    def test_topics_count_less_than_the_owners_words(self):
        r = repo('o/x', 1, description='A fast web framework', topics=['cli'])
        self.assertEqual(taxonomy.rule_type(r), 'framework')

    def test_every_type_has_rules_and_ids_are_unique(self):
        self.assertEqual(len(set(taxonomy.TYPE_IDS)), len(taxonomy.TYPE_IDS))
        for tid in taxonomy.TYPE_IDS[:-1]:
            self.assertIn(tid, taxonomy.TEXT_RULES); self.assertIn(tid, taxonomy.TOPIC_RULES)


class TestLlmPlumbing(unittest.TestCase):
    def test_parse_answer_validates_the_type(self):
        self.assertEqual(categorize.parse_answer('{"type": "database"}'), 'database')
        self.assertEqual(categorize.parse_answer('Sure: {"type":"tool"} done'), 'tool')
        self.assertIsNone(categorize.parse_answer('{"type": "spaceship"}'))
        self.assertIsNone(categorize.parse_answer('no json'))

    def test_cache_key_changes_with_description_or_topics_only(self):
        r = repo('o/x', 1, description='a', topics=['t'])
        k = categorize.cache_key(r)
        self.assertEqual(k, categorize.cache_key(dict(r, stars=99999)))
        self.assertNotEqual(k, categorize.cache_key(dict(r, description='b')))
        self.assertNotEqual(k, categorize.cache_key(dict(r, topics=['u'])))

    def test_rules_never_overwrite_llm_labels(self):
        rs = [repo('o/a', 1, description='Linux kernel'), repo('o/b', 2, description='Linux kernel')]
        labels = {'1': {'type': 'game', 'source': 'llm', 'key': 'k'}}
        n = categorize.apply_rules(rs, labels, '2026-11-09')
        self.assertEqual(n, 1)
        self.assertEqual((labels['1']['type'], labels['2']['type'], labels['2']['source']), ('game', 'systems', 'rules'))
        self.assertEqual(labels['1']['last_seen'], '2026-11-09')

    def test_no_key_means_rule_labels_and_no_network(self):
        import os, tempfile
        d = tempfile.mkdtemp()
        rp, lp = os.path.join(d, 'repos.jsonl'), os.path.join(d, 'types.json')
        with open(rp, 'w') as f:
            f.write(json.dumps(repo('o/a', 1, description='A curated list of awesome things')) + '\n')
        old = os.environ.pop('ANTHROPIC_API_KEY', None)
        try:
            categorize.main(['--repos', rp, '--labels', lp, '--state', os.path.join(d, 's.json')])
        finally:
            if old is not None:
                os.environ['ANTHROPIC_API_KEY'] = old
        with open(lp) as f:
            self.assertEqual(json.load(f)['1']['type'], 'learning')


if __name__ == '__main__':
    unittest.main()

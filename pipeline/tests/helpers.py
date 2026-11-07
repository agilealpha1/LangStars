"""Fixtures shared by the tests: tiny repo dicts in the shapes discover.normalize() and enrich.py produce."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def search_item(full_name, rid, stars=25000, language='Python', archived=False, fork=False, **kw):
    it = {'id': rid, 'node_id': f'R_{rid}', 'full_name': full_name, 'html_url': f'https://github.com/{full_name}',
          'description': 'd', 'stargazers_count': stars, 'forks_count': 1, 'open_issues_count': 3, 'language': language,
          'license': {'spdx_id': 'MIT', 'name': 'MIT'}, 'topics': ['cli'], 'created_at': '2020-01-01T00:00:00Z',
          'pushed_at': '2026-11-01T00:00:00Z', 'homepage': '', 'archived': archived, 'fork': fork, 'default_branch': 'main'}
    it.update(kw)
    return it


def repo(full_name, rid, stars=25000, language='Python', description='', topics=(), languages=None, lang_total=None, **kw):
    r = {'id': rid, 'node_id': f'R_{rid}', 'full_name': full_name, 'html_url': f'https://github.com/{full_name}',
         'description': description, 'stars': stars, 'forks': 100, 'open_issues': 7, 'language': language, 'license': 'MIT',
         'topics': list(topics), 'created_at': '2018-05-01T00:00:00Z', 'pushed_at': '2026-11-01T00:00:00Z', 'homepage': None,
         'archived': False, 'default_branch': 'main', 'languages': languages, 'lang_total': lang_total}
    r.update(kw)
    return r

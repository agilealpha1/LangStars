#!/usr/bin/env python3
"""Kept for compatibility: the site build now lives in build_site_data.py (site/ -> site_dist/ with data/*.json).

  python3 pipeline/build_site.py      # same as: python3 pipeline/build_site_data.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_site_data

if __name__ == '__main__':
    build_site_data.main(sys.argv[1:])

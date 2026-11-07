# LangStars

Browse the most-starred GitHub repositories for each programming language: every repo with **20,000+ stars**, grouped by
GitHub's primary language, refreshed every Monday. Same architecture as [SkillStars](https://github.com/agilealpha1/SkillStars):
a Python pipeline writes static JSON, a vanilla-JS site renders it, GitHub Pages hosts it, GitHub Actions refreshes it.

- **Overview**: a tile per language (official color, repo count, total stars, top repo), rising repos, popular topics.
- **Language pages**: sortable table (stars, weekly gain, forks, last push, age) with filters by type, license, topic and
  "active in the last 6 months"; archived repos are hidden unless you include them.
- **Compare**: bar chart of repos over 20K per language (or total stars / weekly gain) plus "Rising this week".
  Rising sections stay hidden until two weekly snapshots exist.
- **Repo pages**: star sparkline, language byte breakdown ("C 98% / Assembly 1%"), rank in its language.
- Global fuzzy search ([Fuse.js](https://www.fusejs.io/)), About/methodology, keyboard shortcuts (`?`), dark mode, RSS, CC0 data zip.

## How it works

```
pipeline/discover.py        GitHub Search: language:<x> stars:>=20000, one query per language; star ranges are split
                            whenever a query would pass the 1,000-result cap; dedupe by repo id  -> data/candidates.json
pipeline/enrich.py          language byte breakdown (/languages; GraphQL in batches of 50 with a token)  -> data/repos.jsonl
pipeline/categorize.py      one type per repo: keyword rules on topics/name/description, or Claude Haiku
                            when ANTHROPIC_API_KEY is set (cached by repo id)                     -> data/labels/types.json
pipeline/snapshot.py        this week's star counts                                               -> data/history/stars.jsonl
pipeline/build_site_data.py site/ + data/*.json + per-repo files + feed.xml + open-data zip        -> site_dist/
```

Inclusion rule: `stargazers_count >= 20000`, not a fork. Archived repos are kept with a flag (hidden by default on the site).
The language is GitHub's primary language for the repo, so e.g. `laravel/laravel` (primary language "Blade") is not under PHP.

### Adding a language

One line in [`pipeline/languages.py`](pipeline/languages.py): name exactly as GitHub reports it, search slug, linguist color.

```python
Lang('Scala',    'scala',      '#c22d40'),
```

Scala, Lua, Zig, Elixir and Haskell are already there, commented out. Repo types live in [`pipeline/taxonomy.py`](pipeline/taxonomy.py).

## Run it locally

Needs Python 3.10+ and `requests`.

```bash
make install                       # pip install -r requirements.txt
export GITHUB_TOKEN=ghp_...        # optional but recommended (any classic or fine-grained token, no scopes needed)
make update                        # discover, enrich, categorize, snapshot, then build site_dist/
make serve                         # http://localhost:8000/
make test                          # unit tests
```

Steps run individually too: `make discover`, `make enrich`, `make categorize`, `make snapshot`, `make build`.
`make build` only rebuilds the site from the committed `data/`, so you can work on `site/` without touching the API.

Without a token the pipeline still works but slowly: search is limited to 10 requests/minute (discovery takes ~2 minutes) and
the anonymous REST quota (60/hour) only covers ~60 language breakdowns per run; the rest show "not fetched yet" until a run
with a token. `discover.py --max-seconds 100` stops early and resumes from `.cache/` on the next run.

## Deploy (GitHub Pages)

1. Push this folder to a GitHub repo (e.g. `agilealpha1/LangStars`; the site's "Source" links assume that name, see `REPO_URL` in `site/app.js`).
2. **Settings → Pages → Source: GitHub Actions.**
3. Optional: **Settings → Secrets → Actions → `ANTHROPIC_API_KEY`** for Claude Haiku types instead of keyword rules.
4. Run **Actions → Refresh data and deploy Pages → Run workflow** once (with "refresh" ticked) to fetch everything with the
   Actions token, including all language breakdowns.

[`.github/workflows/pages.yml`](.github/workflows/pages.yml):

- **push to main**: run the tests, build from the committed data, deploy.
- **every Monday 04:00 UTC** (and manual runs with *refresh*): tests, then `deploy/update.sh` (discover → enrich → categorize →
  snapshot → validation build), commit `data/` as `github-actions[bot]`, build, deploy.
- **A failing step keeps the previous data**: if discovery or enrichment fails, the old candidates and repo data are restored
  and no snapshot is taken; if the validation build fails, all of `data/` is restored (paid LLM labels are kept); the site is
  still deployed from the last good data. `discover.py` also refuses to write a result less than 70% the size of the last one.

The site uses relative paths only, so it works under `https://<user>.github.io/LangStars/` with no configuration.

## Cost: $0

- **GitHub Actions**: free for public repos (a weekly run takes a few minutes).
- **GitHub Pages**: free hosting for public repos.
- **GitHub API**: the built-in `GITHUB_TOKEN` in Actions covers it: ~20–40 search calls and ~40 GraphQL calls per run.
- **Claude Haiku** is optional. Without `ANTHROPIC_API_KEY`, keyword rules assign types for free. With it, labeling all
  ~1,900 repos once costs roughly $0.50 through the Message Batches API; weekly runs only relabel new or changed repos (cents).

## Data

`site_dist/data/index.json` (all repos), `languages.json`, `stats.json`, `r/<owner>__<name>.json` (detail + star history),
`feed.xml` (repos newly over 20K) and `download/langstars-data.zip` (CSV + JSON + full history). The data is CC0; the code is MIT.
Fuse.js is vendored in `site/vendor/` under its Apache-2.0 license.

## Tests

`make test` (also run in CI before every deploy): search splitting and dedupe, the inclusion rule, enrichment caching,
type rules and LLM-answer validation, the built site's schema (index, languages, per-repo files, feed, zip), snapshots,
and `deploy/update.sh` keeping data consistent when any step fails.

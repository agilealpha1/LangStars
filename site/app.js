// LangStars static site. Loads data/index.json, languages.json and stats.json (built by pipeline/build_site_data.py)
// and renders with hash routes, so it works from any sub-path (GitHub Pages project sites at /<repo>/):
//   #/                                    overview: language tiles, rising this week, popular topics
//   #/lang/<slug>?q=&t=&type=&license=&active=1&archived=1&sort=&dir=   one language, sortable + filterable table
//   #/all?…                               every repo (the header search lands here: fuzzy, via Fuse.js)
//   #/compare?m=count|stars|gain          bar chart per language + rising this week
//   #/r/<owner>/<name>                    repo detail: star sparkline, language breakdown
//   #/about                               methodology
// All repo text comes from GitHub and is untrusted: it is only ever set via textContent, never innerHTML.
'use strict';

const PAGE = 100;
const ACTIVE_DAYS = 183;                 // "active in the last 6 months"
const REPO_URL = 'https://github.com/agilealpha1/LangStars';
let DATA, FUSE, LANG_BY_NAME, LANG_BY_SLUG, BY_NAME, TYPE;
const S = { view: 'home', lang: null, repo: null, q: '', topics: [], type: '', license: '', active: false, archived: false,
  sort: '', dir: '', m: 'count', limit: PAGE };
const detailCache = {};

// ---------- helpers ----------
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'style') for (const [p, x] of Object.entries(v)) el.style.setProperty(p, x);
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c instanceof Node ? c : String(c));
  return el;
}
function svg(tag, attrs, ...kids) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) el.setAttribute(k, v);
  for (const c of kids.flat()) if (c) el.append(c);
  return el;
}
const $ = (id) => document.getElementById(id);
const httpUrl = (u) => (typeof u === 'string' && /^https?:\/\/[^\s"'<>`\\]+$/i.test(u) ? u : null);   // defence in depth
const compact = (n) => new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
const num = (n) => Number(n).toLocaleString('en');
const signed = (g) => (g == null ? '—' : (g > 0 ? '+' : g < 0 ? '−' : '±') + num(Math.abs(g)));
const daysSince = (d) => (Date.now() - Date.parse(String(d).slice(0, 10) + 'T00:00:00Z')) / 864e5;
function ago(d) {
  if (!d) return '—';
  const n = Math.max(0, daysSince(d));
  if (n < 1) return 'today';
  if (n < 30) return `${Math.floor(n)}d ago`;
  if (n < 365) return `${Math.floor(n / 30)}mo ago`;
  return `${(n / 365).toFixed(1)}y ago`;
}
function age(d) {
  if (!d) return '—';
  const y = daysSince(d) / 365.25;
  return y >= 1 ? `${y.toFixed(y >= 10 ? 0 : 1)}y` : `${Math.max(1, Math.round(y * 12))}mo`;
}
const fmtDate = (d) => (d ? new Date(d.slice(0, 10) + 'T00:00:00Z').toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }) : '—');
const ext = { target: '_blank', rel: 'noopener noreferrer' };
const dot = (c) => h('span', { class: 'dot', style: { background: c || '#8b8b8b' }, 'aria-hidden': 'true' });
const repoHash = (r) => '#/r/' + r.name.split('/').map(encodeURIComponent).join('/');
const ghUrl = (r) => httpUrl(r.url) || 'https://github.com/' + r.name.split('/').map(encodeURIComponent).join('/');
const isActive = (r) => daysSince(r.pushed) <= ACTIVE_DAYS;
const hasGains = () => DATA.stats.snapshots >= 2;
const live = (rows) => rows.filter((r) => !r.archived);
const minK = () => compact(DATA.stats.min_stars);
const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
function nextMonday() {
  const d = new Date(); d.setUTCDate(d.getUTCDate() + ((8 - d.getUTCDay()) % 7 || 7));
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
}
async function getJSON(url) {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

// ---------- routing / URL state ----------
function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const i = raw.indexOf('?');
  const dec = (x) => { try { return decodeURIComponent(x); } catch { return x; } };   // a stray % must not crash routing
  const seg = (i < 0 ? raw : raw.slice(0, i)).split('/').filter(Boolean).map(dec);
  const p = new URLSearchParams(i < 0 ? '' : raw.slice(i + 1));
  S.lang = null; S.repo = null;
  if (seg[0] === 'lang') { S.lang = LANG_BY_SLUG[seg[1]] || null; S.view = S.lang ? 'list' : 'missing'; }
  else if (seg[0] === 'all' || seg[0] === 'search') S.view = 'list';
  else if (seg[0] === 'compare') S.view = 'compare';
  else if (seg[0] === 'about') S.view = 'about';
  else if (seg[0] === 'r' && seg.length >= 3) { S.view = 'repo'; S.repo = seg.slice(1).join('/'); }
  else S.view = seg.length ? 'missing' : 'home';
  S.q = p.get('q') || '';
  S.topics = (p.get('t') || '').split(',').filter(Boolean);
  S.type = TYPE[p.get('type')] ? p.get('type') : '';
  S.license = p.get('license') || '';
  S.active = p.get('active') === '1';
  S.archived = p.get('archived') === '1';
  S.sort = SORTS[p.get('sort')] || p.get('sort') === 'relevance' ? p.get('sort') : '';
  S.dir = p.get('dir') === 'asc' || p.get('dir') === 'desc' ? p.get('dir') : '';
  S.m = METRICS[p.get('m')] ? p.get('m') : 'count';
  S.limit = PAGE;
}
function hashFor(over = {}) {
  const st = { ...S, ...over };
  const path = st.lang ? `lang/${st.lang.slug}` : 'all';
  const p = new URLSearchParams();
  if (st.q) p.set('q', st.q);
  if (st.topics.length) p.set('t', st.topics.join(','));
  for (const k of ['type', 'license', 'sort', 'dir']) if (st[k]) p.set(k, st[k]);
  if (st.active) p.set('active', '1');
  if (st.archived) p.set('archived', '1');
  const qs = p.toString().replace(/%2C/g, ',');
  return `#/${path}${qs ? '?' + qs : ''}`;
}
const CLEAR = { q: '', topics: [], type: '', license: '', active: false, archived: false, sort: '', dir: '' };
function syncUrl() { history.replaceState(null, '', hashFor()); }   // replaceState doesn't fire hashchange

// ---------- sorting / filtering ----------
const SORTS = {   // val: sort key (null = missing, always last); first click sorts descending (name: ascending)
  name: { label: 'Repository', val: (r) => r.name.toLowerCase(), dir: 'asc' },
  stars: { label: 'Stars', val: (r) => r.stars },
  gain: { label: 'Weekly', val: (r) => r.gain },
  forks: { label: 'Forks', val: (r) => r.forks },
  pushed: { label: 'Last push', val: (r) => r.pushed || null },
  age: { label: 'Age', val: (r) => (r.created ? -Date.parse(r.created) : null) },   // descending = oldest first
};
function sorter(key, dir) {
  const val = SORTS[key].val;
  const sign = dir === 'asc' ? 1 : -1;
  return (a, b) => {
    const va = val(a), vb = val(b);
    if (va == null || vb == null) return (va == null) - (vb == null) || b.stars - a.stars;
    return (va < vb ? -1 : va > vb ? 1 : 0) * sign || b.stars - a.stars;
  };
}
const effSort = () => S.sort || (S.q.trim() ? 'relevance' : 'stars');
const effDir = (k) => S.dir || (SORTS[k] && SORTS[k].dir) || 'desc';
function filtered() {
  const rows = S.q.trim() ? FUSE.search(S.q.trim()).map((x) => x.item) : DATA.repos;   // Fuse: relevance order
  return rows.filter((r) => (!S.lang || r.lang === S.lang.name) && (S.archived || !r.archived)
    && (!S.type || r.type === S.type) && (!S.license || (r.license || 'none') === S.license)
    && (!S.active || isActive(r)) && S.topics.every((t) => r.topics.includes(t)));
}
function topicCounts(rows, limit) {
  const c = new Map();
  for (const r of rows) for (const t of r.topics) c.set(t, (c.get(t) || 0) + 1);
  return [...c].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, limit);
}

// ---------- shared repo table ----------
function gainCell(g) {
  if (g == null) return h('span', { class: 'muted', title: hasGains() ? 'Not in the previous snapshot' : 'Weekly gains start with the second weekly snapshot' }, '—');
  return h('span', { class: g > 0 ? 'gain' : 'gain zero' }, signed(g));
}
// opts: { showLang, sortable, onTopic(t) }. Sortable tables read and write S.sort / S.dir.
function repoTable(rows, opts = {}) {
  const sort = effSort(), dir = effDir(sort);
  const th = (key, cls) => h('th', { class: cls, scope: 'col', 'aria-sort': opts.sortable && sort === key ? (dir === 'asc' ? 'ascending' : 'descending') : null },
    opts.sortable ? h('button', { type: 'button', title: `Sort by ${SORTS[key].label.toLowerCase()}`, onclick: () => {
      if (sort === key) S.dir = dir === 'asc' ? 'desc' : 'asc'; else { S.sort = key; S.dir = ''; }
      S.limit = PAGE; syncUrl(); renderList();
    } }, SORTS[key].label) : SORTS[key].label);
  const plain = (label, cls) => h('th', { class: cls, scope: 'col' }, label);
  return h('div', { class: 'tablewrap' }, h('table', { class: 'repos' },
    h('thead', null, h('tr', null, plain('#', 'num'), th('name'), opts.showLang ? plain('Language') : null, plain('Type', 'c-type'),
      th('stars', 'num'), th('gain', 'num'), th('forks', 'num c-forks'), th('pushed', 'num'), th('age', 'num c-age'), plain('License', 'c-lic'))),
    h('tbody', null, rows.map((r, i) => {
      const [owner, name] = r.name.split('/');
      const l = LANG_BY_NAME[r.lang];
      return h('tr', { 'data-href': repoHash(r), 'data-url': ghUrl(r) },
        h('td', { class: 'rk' }, i + 1),
        h('td', null,
          h('div', null,
            h('a', { class: 'name', href: repoHash(r) }, h('span', { class: 'owner' }, owner + ' / '), name),
            r.archived ? h('span', { class: 'tag arch' }, 'archived') : null,
            r.new ? h('span', { class: 'tag new', title: `Crossed ${minK()} stars this week` }, 'new') : null,
            h('a', { class: 'gh c-gh', href: ghUrl(r), ...ext, 'aria-label': `${r.name} on GitHub` }, 'GitHub ↗')),
          r.desc ? h('div', { class: 'desc' }, r.desc) : null,
          r.topics.length ? h('div', { class: 'topics' }, r.topics.slice(0, 5).map((t) => opts.onTopic
            ? h('button', { type: 'button', class: `chip${S.topics.includes(t) ? ' on' : ''}`, onclick: () => opts.onTopic(t) }, t)
            : h('a', { class: 'chip', href: hashFor({ ...CLEAR, lang: null, topics: [t] }) }, t))) : null),
        opts.showLang ? h('td', null, h('a', { class: 'lang', href: `#/lang/${l.slug}` }, dot(l.color), r.lang)) : null,
        h('td', { class: 'c-type' }, h('span', { class: 'type' }, TYPE[r.type] || r.type)),
        h('td', { class: 'num' }, num(r.stars)),
        h('td', { class: 'num' }, gainCell(r.gain)),
        h('td', { class: 'num c-forks' }, num(r.forks)),
        h('td', { class: 'num', title: r.pushed }, ago(r.pushed)),
        h('td', { class: 'num c-age', title: `Created ${r.created}` }, age(r.created)),
        h('td', { class: 'c-lic muted' }, r.license || '—'));
    }))));
}

// ---------- views ----------
function nav() {
  const on = (cond) => (cond ? 'on' : null);
  $('nav').replaceChildren(
    h('a', { href: '#/', class: on(S.view === 'home') }, 'Overview'),
    h('a', { href: '#/all', class: on(S.view === 'list' && !S.lang) }, 'All languages'),
    h('a', { href: '#/compare', class: on(S.view === 'compare') }, 'Compare'),
    h('a', { href: '#/about', class: on(S.view === 'about') }, 'About'),
    h('span', { class: 'sep', 'aria-hidden': 'true' }),
    ...[...DATA.langs].sort((a, b) => b.count - a.count).map((l) => h('a', { href: `#/lang/${l.slug}`, class: on(S.lang === l) }, dot(l.color), l.name)),
  );
}
const stat = (k, v, attrs) => h('div', { class: 'stat' }, h('div', { class: 'k' }, k), h('div', { class: 'v', ...attrs }, v));
function rising(n) {
  return live(DATA.repos).filter((r) => r.gain != null && r.gain > 0).sort(sorter('gain', 'desc')).slice(0, n);
}

function home() {
  const s = DATA.stats;
  const langs = [...DATA.langs].sort((a, b) => b.count - a.count || b.stars - a.stars);
  const maxN = Math.max(...langs.map((l) => l.count), 1);
  const active = live(DATA.repos);
  const recent = active.filter((r) => daysSince(r.pushed) < 30).length;
  const top = rising(10);
  return [
    h('section', { class: 'hero' },
      h('h1', null, 'The ', h('span', { class: 'grad' }, 'most-starred'), ' open source, by language'),
      h('p', null, `Every GitHub repository with ${num(s.min_stars)}+ stars, grouped by primary language and refreshed every Monday. `
        + 'Pick a language for a sortable table, or search fuzzily across names, descriptions and topics.')),
    h('div', { class: 'stats' },
      stat('Repositories', num(s.repos)), stat('Combined stars', compact(s.total_stars)), stat('Languages', langs.length),
      hasGains() ? stat('New this week', num(s.new_this_week)) : stat('Pushed in last 30 days', `${Math.round((100 * recent) / Math.max(1, active.length))}%`)),
    h('div', { class: 'section-head' }, h('h2', null, 'Languages'), h('a', { href: '#/compare' }, 'Compare languages →')),
    h('div', { class: 'tiles' }, langs.map((l) => h('a', { class: 'tile', href: `#/lang/${l.slug}`, style: { '--c': l.color } },
      h('div', { class: 'head' }, dot(l.color), l.name),
      h('div', { class: 'n' }, num(l.count)),
      h('div', { class: 'sub' }, `${compact(l.stars)} stars` + (l.gain != null ? ` · +${compact(l.gain)} this week` : '')),
      h('div', { class: 'sub' }, l.top ? `Top: ${l.top.name} · ★ ${compact(l.top.stars)}` : '—')))),
    top.length ? [h('div', { class: 'section-head' }, h('h2', null, 'Rising this week'), h('a', { href: '#/compare' }, 'Top 25 →')),
      repoTable(top, { showLang: true })] : null,
    h('div', { class: 'grid2', style: { 'margin-top': '14px' } },
      h('div', { class: 'panel' }, h('h2', { style: { margin: '0 0 10px' } }, `Repos over ${minK()} per language`),
        langs.map((l) => h('div', { class: 'bar' },
          h('a', { href: `#/lang/${l.slug}` }, l.name),
          h('div', { class: 'track' }, h('div', { class: 'fill', style: { width: `${(100 * l.count) / maxN}%`, background: l.color } })),
          h('span', { class: 'v' }, l.count)))),
      h('div', { class: 'panel' }, h('h2', { style: { margin: '0 0 12px' } }, 'Popular topics'),
        h('div', { class: 'chips' }, topicCounts(active, 48).map(([t, n]) =>
          h('a', { class: 'chip', href: hashFor({ ...CLEAR, lang: null, topics: [t] }) }, t, h('span', { class: 'c' }, n)))))),
  ];
}

let resultsEl, filtersEl;
function list() {
  const base = DATA.repos.filter((r) => !S.lang || r.lang === S.lang.name);
  const liveBase = live(base);
  const stars = liveBase.reduce((s, r) => s + r.stars, 0);
  const L = S.lang && DATA.langs.find((l) => l.slug === S.lang.slug);
  filtersEl = h('div', { class: 'filters' });
  resultsEl = h('div');
  renderList();
  return h('div', null,
    h('div', { class: 'page-head' },
      h('h1', null, S.lang ? dot(S.lang.color) : null, S.lang ? S.lang.name : 'All languages')),
    h('div', { class: 'facts' }, `${num(liveBase.length)} repositories · ${compact(stars)} stars`
      + (L && L.gain != null ? ` · ${signed(L.gain)} this week` : '') + ` · ${base.length - liveBase.length} archived (hidden unless included)`),
    filtersEl, resultsEl);
}

function renderList() {
  const rows = filtered();
  const sort = effSort(), dir = effDir(sort);
  if (sort !== 'relevance') rows.sort(sorter(sort, dir));
  const rerender = () => { S.limit = PAGE; syncUrl(); renderList(); };

  // facets are computed on the current results; selected topics are always shown first
  const facets = topicCounts(rows, 24).filter(([t]) => !S.topics.includes(t));
  const setTopics = (t) => { S.topics = t; rerender(); };
  const pool = DATA.repos.filter((r) => (!S.lang || r.lang === S.lang.name) && (S.archived || !r.archived));
  const count = (key) => { const n = {}; for (const r of pool) { const k = key(r); n[k] = (n[k] || 0) + 1; } return n; };
  const nType = count((r) => r.type), nLic = count((r) => r.license || 'none');
  const lics = Object.keys(nLic).sort((a, b) => nLic[b] - nLic[a] || a.localeCompare(b));
  if (S.license && !nLic[S.license]) lics.unshift(S.license);
  filtersEl.replaceChildren(
    h('div', { class: 'row' },
      h('span', { class: 'label' }, 'Topics'),
      h('div', { class: 'chips', style: { flex: '1' } },
        S.topics.map((t) => h('button', { type: 'button', class: 'chip on', title: 'Remove filter', onclick: () => setTopics(S.topics.filter((x) => x !== t)) }, t, ' ×')),
        facets.map(([t, n]) => h('button', { type: 'button', class: 'chip', onclick: () => setTopics([...S.topics, t]) }, t, h('span', { class: 'c' }, n))),
        S.topics.length ? h('button', { type: 'button', class: 'chip clear', onclick: () => setTopics([]) }, 'Clear') : null,
        !S.topics.length && !facets.length ? h('span', { class: 'muted' }, 'No topics in these results') : null)),
    h('div', { class: 'row' },
      h('span', { class: 'label' }, 'Filter'),
      S.lang ? h('input', { type: 'search', id: 'local-q', placeholder: `Filter ${S.lang.name} repos…`, value: S.q, 'aria-label': `Filter ${S.lang.name} repos`,
        oninput: (e) => { clearTimeout(renderList.t); renderList.t = setTimeout(() => { S.q = e.target.value; if (!S.q.trim() && S.sort === 'relevance') S.sort = ''; rerender(); restoreFocus('local-q'); }, 120); } }) : null,
      h('select', { 'aria-label': 'Filter by type', onchange: (e) => { S.type = e.target.value; rerender(); } },
        h('option', { value: '' }, 'All types'),
        DATA.types.filter((t) => nType[t.id] || S.type === t.id).map((t) => h('option', { value: t.id, selected: S.type === t.id }, `${t.label} (${nType[t.id] || 0})`))),
      h('select', { 'aria-label': 'Filter by license', onchange: (e) => { S.license = e.target.value; rerender(); } },
        h('option', { value: '' }, 'Any license'),
        lics.map((k) => h('option', { value: k, selected: S.license === k }, `${k === 'none' ? 'No license' : k === 'Other' ? 'Other license' : k} (${nLic[k] || 0})`))),
      h('label', { class: 'toggle' }, h('input', { type: 'checkbox', checked: S.active, onchange: (e) => { S.active = e.target.checked; rerender(); } }), 'Active in last 6 months'),
      h('label', { class: 'toggle' }, h('input', { type: 'checkbox', checked: S.archived, onchange: (e) => { S.archived = e.target.checked; rerender(); } }), 'Include archived'),
      h('span', { class: 'spacer' }),
      S.q || S.topics.length || S.type || S.license || S.active || S.archived || S.sort
        ? h('a', { href: hashFor(CLEAR), onclick: () => { $('q').value = ''; } }, 'Reset all') : null));

  const shown = rows.slice(0, S.limit);
  sel = -1;
  resultsEl.replaceChildren(
    h('div', { class: 'result-meta' },
      h('span', null, `${num(rows.length)} result${rows.length === 1 ? '' : 's'}` + (S.q.trim() ? ` for “${S.q.trim()}”` : '')),
      h('span', null, sort === 'relevance' ? 'sorted by best match · click a column to sort' : 'click a column header to sort')),
    rows.length ? repoTable(shown, { showLang: !S.lang, sortable: true,
      onTopic: (t) => setTopics(S.topics.includes(t) ? S.topics.filter((x) => x !== t) : [...S.topics, t]) })
      : h('div', { class: 'empty' }, 'No repositories match. Try fewer filters or a shorter query.'),
    rows.length > S.limit ? h('button', { type: 'button', class: 'more', onclick: () => { S.limit += PAGE; const y = scrollY; renderList(); scrollTo(0, y); } },
      `Show more (${num(rows.length - S.limit)} left)`) : null);
}
function restoreFocus(id) {
  const el = $(id);
  if (el && document.activeElement !== el) { const n = el.value.length; el.focus(); el.setSelectionRange(n, n); }
}

// ---------- compare ----------
const METRICS = {
  count: { label: () => `Repos over ${minK()}`, val: (l) => l.count, fmt: num },
  stars: { label: () => 'Total stars', val: (l) => l.stars, fmt: compact },
  gain: { label: () => 'Stars gained this week', val: (l) => l.gain || 0, fmt: signed, needsGains: true },
};
function compare() {
  if (METRICS[S.m].needsGains && !hasGains()) S.m = 'count';
  const chart = h('div', { class: 'panel bars-lg', role: 'figure', 'aria-label': 'Bar chart by language' });
  const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Metric' });
  const draw = () => {
    history.replaceState(null, '', '#/compare' + (S.m === 'count' ? '' : `?m=${S.m}`));
    const M = METRICS[S.m];
    const rows = [...DATA.langs].sort((a, b) => M.val(b) - M.val(a) || a.name.localeCompare(b.name));
    const max = Math.max(...rows.map((l) => Math.abs(M.val(l))), 1);
    seg.replaceChildren(...Object.entries(METRICS).filter(([, x]) => !x.needsGains || hasGains()).map(([k, x]) =>
      h('button', { type: 'button', 'aria-pressed': String(k === S.m), onclick: () => { S.m = k; draw(); } }, x.label())));
    chart.replaceChildren(h('h3', null, M.label()), ...rows.map((l) => h('a', { class: 'bar', href: `#/lang/${l.slug}`, title: `${l.name}: ${M.fmt(M.val(l))}` },
      h('span', { class: 'lab' }, dot(l.color), l.name),
      h('div', { class: 'track' }, h('div', { class: 'fill', style: { width: `${(100 * Math.max(0, M.val(l))) / max}%`, background: l.color } })),
      h('span', { class: 'v' }, M.fmt(M.val(l))))));
  };
  draw();
  const top = rising(25);
  return [
    h('div', { class: 'page-head' }, h('h1', null, 'Compare languages')),
    h('div', { class: 'facts' }, `How many repos each language has over ${num(DATA.stats.min_stars)} stars (GitHub primary language; archived repos excluded).`
      + (hasGains() ? '' : ` Weekly gains and “Rising this week” appear after the second weekly snapshot (${nextMonday()}).`)),
    h('div', { style: { margin: '0 0 12px' } }, seg), chart,
    top.length ? [h('div', { class: 'section-head' }, h('h2', null, 'Rising this week')),
      h('div', { class: 'facts' }, `Top ${top.length} by stars gained since ${fmtDate(DATA.stats.prev_snapshot)}, all languages.`),
      repoTable(top, { showLang: true })] : null,
  ];
}

// ---------- repo page ----------
function repoPage() {
  const r = BY_NAME[S.repo.toLowerCase()];
  if (!r) return notFound(`${S.repo} isn't one of the ${num(DATA.repos.length)} repos LangStars tracks: it may be under ${num(DATA.stats.min_stars)} stars, a fork, or written mainly in a language that isn't listed.`);
  document.title = `${r.name} · LangStars`;
  const wrap = h('div', null, h('div', { class: 'loading' }, 'Loading…'));
  const load = detailCache[r.slug] || (detailCache[r.slug] = getJSON(`data/r/${encodeURIComponent(r.slug)}.json`));
  load.then((d) => { if (document.body.contains(wrap)) { wrap.replaceChildren(...repoView(r, d).flat()); wireSpark(wrap); } })
    .catch((e) => { delete detailCache[r.slug]; wrap.replaceChildren(h('div', { class: 'empty' }, `Couldn't load this repo (${e.message}).`)); });
  return wrap;
}
function repoView(r, d) {
  const l = LANG_BY_NAME[r.lang];
  const [owner, name] = r.name.split('/');
  const peers = live(DATA.repos).filter((x) => x.lang === r.lang);
  const rank = peers.indexOf(r) + 1;
  const home = httpUrl(d.homepage);
  const more = peers.filter((x) => x.type === r.type && x.id !== r.id).slice(0, 8);
  return [
    h('nav', { class: 'crumbs', 'aria-label': 'Breadcrumb' }, h('a', { href: '#/' }, 'Overview'), ' / ', h('a', { href: `#/lang/${l.slug}` }, r.lang)),
    h('div', { class: 'repo-h' }, h('h1', null, h('span', { class: 'owner' }, owner + ' / '), name),
      r.archived ? h('span', { class: 'tag arch' }, 'archived') : null, r.new ? h('span', { class: 'tag new' }, `new over ${minK()}`) : null),
    d.description ? h('p', { class: 'lede' }, d.description) : null,
    h('div', { class: 'pills' },
      h('a', { class: 'chip', href: `#/lang/${l.slug}` }, dot(l.color), r.lang),
      h('a', { class: 'chip', href: hashFor({ ...CLEAR, lang: l, type: r.type }) }, TYPE[r.type]),
      r.license ? h('span', { class: 'chip' }, r.license) : null,
      (d.topics || []).map((t) => h('a', { class: 'chip', style: { color: 'var(--accent)' }, href: hashFor({ ...CLEAR, lang: null, topics: [t] }), title: 'All repos with this topic' }, t))),
    h('div', { class: 'actions' },
      h('a', { class: 'btn primary', href: ghUrl(r), ...ext }, 'Open on GitHub ↗'),
      home ? h('a', { class: 'btn', href: home, ...ext, rel: 'noopener noreferrer nofollow' }, 'Homepage ↗') : null,
      h('span', { class: 'muted', style: { 'font-size': '13px' } }, 'Press ', h('kbd', null, 'o'), ' to open on GitHub')),
    h('div', { class: 'stats kv' },
      stat('Stars', num(r.stars)), stat('Weekly gain', signed(r.gain), { class: r.gain > 0 ? 'v gain' : 'v' }),
      stat('Forks', num(r.forks)), stat('Open issues + PRs', num(r.issues)),
      stat(`Rank in ${r.lang}`, rank ? `#${rank} of ${peers.length}` : 'archived'), stat('Age', `${age(r.created)}`, { title: `Created ${fmtDate(r.created)}` }),
      stat('Last push', ago(r.pushed), { title: r.pushed }), stat('Listed since', fmtDate(d.first_seen))),
    h('div', { class: 'grid2' },
      h('section', { class: 'panel' }, h('h3', null, 'Star history'), sparkline(d.history || [])),
      h('section', { class: 'panel' }, h('h3', null, 'Languages'), langBreakdown(d.breakdown))),
    more.length ? [h('div', { class: 'section-head' }, h('h2', null, `More ${TYPE[r.type]} repos in ${r.lang}`),
      h('a', { href: hashFor({ ...CLEAR, lang: l, type: r.type }) }, 'See all →')), repoTable(more, {})] : null,
    h('p', { class: 'cap' }, `Created ${fmtDate(r.created)}. Type labeled by ${d.type_src === 'llm' ? 'Claude Haiku' : 'keyword rules'}.`),
  ];
}
function langBreakdown(bd) {
  if (bd == null) return h('p', { class: 'muted' }, 'Language breakdown not fetched yet; it is added on the next weekly refresh.');
  if (!bd.length) return h('p', { class: 'muted' }, 'GitHub detects no code in this repo (it is mostly text or docs).');
  const head = bd.filter((b) => b[0] !== 'Other').slice(0, 3).map((b) => `${b[0]} ${Math.round(b[1])}%`).join(' / ');
  return [
    h('p', { style: { margin: '0 0 10px', 'font-weight': '650' } }, head),
    h('div', { class: 'stack', role: 'img', 'aria-label': bd.map((b) => `${b[0]} ${b[1]}%`).join(', ') },
      bd.map((b) => h('i', { style: { width: `${b[1]}%`, background: b[2] }, title: `${b[0]} ${b[1]}%` }))),
    h('ul', { class: 'legend' }, bd.map((b) => h('li', null, dot(b[2]), h('b', null, b[0]), h('span', { class: 'muted' }, `${b[1]}%`)))),
  ];
}
function sparkline(hist) {
  if (!hist.length) return h('p', { class: 'muted' }, 'No snapshots yet.');
  const W = 300, H = 130, pt = 14, pb = 18, px = 4;
  const ys = hist.map((x) => x[1]);
  let lo = Math.min(...ys), hi = Math.max(...ys);
  if (hi === lo) { lo -= Math.max(1, lo * 0.01); hi += Math.max(1, hi * 0.01); }
  const X = (i) => (hist.length === 1 ? W / 2 : px + (i * (W - 2 * px)) / (hist.length - 1));
  const Y = (v) => pt + ((hi - v) * (H - pt - pb)) / (hi - lo);
  const pts = hist.map((x, i) => ({ x: X(i), y: Y(x[1]), d: x[0], v: x[1] }));
  const path = pts.map((q, i) => `${i ? 'L' : 'M'}${q.x.toFixed(1)} ${q.y.toFixed(1)}`).join(' ');
  const first = pts[0], last = pts[pts.length - 1];
  const box = h('div', { class: 'spark' });
  box._pts = pts;
  box.append(svg('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', role: 'img', 'aria-label': 'Star history: ' + hist.map((x) => `${fmtDate(x[0])} ${num(x[1])}`).join(', ') },
    svg('line', { x1: 0, x2: W, y1: H - pb, y2: H - pb, stroke: 'var(--border)', 'vector-effect': 'non-scaling-stroke' }),
    pts.length > 1 ? svg('path', { d: `${path} L${last.x} ${H - pb} L${first.x} ${H - pb} Z`, fill: 'var(--accent)', opacity: '.12' }) : null,
    pts.length > 1 ? svg('path', { d: path, fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2, 'stroke-linejoin': 'round', 'vector-effect': 'non-scaling-stroke' }) : null,
    svg('line', { class: 'xl', x1: 0, x2: 0, y1: pt - 6, y2: H - pb, stroke: 'var(--muted)', opacity: 0, 'vector-effect': 'non-scaling-stroke' }),
    svg('rect', { class: 'hit', x: 0, y: 0, width: W, height: H, fill: 'transparent' })));
  box.append(h('span', { class: 'sdot', style: { position: 'absolute', width: '9px', height: '9px', 'border-radius': '50%', background: 'var(--accent)',
    'box-shadow': '0 0 0 2px var(--panel)', transform: 'translate(-50%,-50%)', 'pointer-events': 'none' } }), h('div', { class: 'tip', hidden: true }));
  const cap = hist.length === 1 ? `History starts ${fmtDate(first.d)}; a point is added every Monday.`
    : `${hist.length} weekly snapshots, ${fmtDate(first.d)} – ${fmtDate(last.d)}: ${signed(last.v - first.v)} stars.`;
  return [box, h('p', { class: 'cap' }, cap)];
}
function wireSpark(root) {
  const box = root.querySelector('.spark');
  if (!box || !box._pts) return;
  const pts = box._pts, el = box.querySelector('svg'), sdot = box.querySelector('.sdot'), tip = box.querySelector('.tip'), xl = box.querySelector('.xl');
  const place = (q) => {
    const r = el.getBoundingClientRect(), b = box.getBoundingClientRect();
    const x = r.left - b.left + (q.x * r.width) / 300, y = r.top - b.top + (q.y * r.height) / 130;
    sdot.style.left = x + 'px'; sdot.style.top = y + 'px';
    return [x, y];
  };
  const rest = () => { place(pts[pts.length - 1]); tip.hidden = true; xl.setAttribute('opacity', 0); };
  rest();
  const move = (e) => {
    const r = el.getBoundingClientRect();
    const vx = ((e.clientX - r.left) * 300) / r.width;
    const q = pts.reduce((a, b) => (Math.abs(b.x - vx) < Math.abs(a.x - vx) ? b : a));
    const [x, y] = place(q);
    xl.setAttribute('x1', q.x); xl.setAttribute('x2', q.x); xl.setAttribute('opacity', 0.5);
    tip.hidden = false; tip.textContent = `${fmtDate(q.d)} · ${num(q.v)} ★`;
    tip.style.left = Math.min(Math.max(x, 70), box.clientWidth - 70) + 'px'; tip.style.top = y - 10 + 'px';
  };
  const hit = box.querySelector('.hit');
  hit.addEventListener('pointermove', move); hit.addEventListener('pointerdown', move); hit.addEventListener('pointerleave', rest);
  new ResizeObserver(() => { if (tip.hidden) rest(); }).observe(box);
}

// ---------- about / not found ----------
function about() {
  const s = DATA.stats;
  const P = (...k) => h('p', null, ...k), C = (t) => h('code', null, t);
  const src = Object.entries(s.type_sources || {}).map(([k, v]) => `${num(v)} by ${k === 'llm' ? 'Claude Haiku' : 'keyword rules'}`).join(', ');
  return h('article', { class: 'prose' },
    h('h1', null, 'How LangStars works'),
    P(`LangStars lists every public GitHub repository with at least ${num(s.min_stars)} stars whose primary language is one of ${DATA.langs.length} languages. `
      + 'A Python pipeline rebuilds the data every Monday at 04:00 UTC in GitHub Actions and publishes it as static files on GitHub Pages.'),
    h('h2', null, 'Inclusion rule'),
    P(C(`stargazers_count >= ${s.min_stars}`), ', not a fork, and GitHub\'s primary language (the ', C('language'),
      ' field, the language with the most bytes of code) is on the list. Archived repos are kept but hidden unless you tick “Include archived”. '
      + `Right now: ${num(s.repos)} repos plus ${num(s.archived)} archived.`),
    h('h2', null, '1. Discovery'),
    P('One GitHub Search API query per language: ', C(`language:<lang> stars:>=${s.min_stars}`),
      '. The Search API returns at most 1,000 results per query, so a query that would exceed that is split into star ranges until every slice fits. '
      + 'Results are de-duplicated by repository id, so a renamed repo keeps its history.'),
    h('h2', null, '2. Enrichment'),
    P('Name, description, stars, forks, open issues (GitHub counts open pull requests here too), license, topics, creation date, last push and homepage come with the search results. '
      + 'The language byte breakdown on each repo page (“Python 70% / C 25%”) comes from GitHub\'s languages data and is re-fetched only when a repo has new pushes. '
      + `${num(s.with_breakdown || 0)} of ${num(s.repos + s.archived)} repos have one so far.`),
    h('h2', null, '3. Type'),
    P(`Each repo gets one type from its topics plus keyword rules on its name and description; when an Anthropic API key is configured, Claude Haiku labels it instead (cached per repo). Currently: ${src}.`),
    h('table', null, h('thead', null, h('tr', null, h('th', null, 'Type'), h('th', null, 'Repos'), h('th', null, 'Meaning'))),
      h('tbody', null, (s.types || DATA.types).map((t) => h('tr', null, h('td', null, h('a', { href: hashFor({ ...CLEAR, lang: null, type: t.id }) }, t.label)),
        h('td', null, num(s.by_type[t.id] || 0)), h('td', { class: 'muted' }, t.description || ''))))),
    h('h2', null, '4. Weekly snapshots'),
    P('Every run records each repo\'s star count. “Weekly gain” is the difference between the last two snapshots and “new” marks repos that were not in the previous one. '
      + `The first snapshot (${fmtDate(s.first_snapshot)}) is the baseline, so gains and “Rising this week” start with the second.`),
    h('h2', null, 'Limits'),
    h('ul', null,
      h('li', null, 'Primary language is GitHub\'s byte count: a framework whose templates outweigh its code (Laravel is “Blade”) lands under a language that is not listed.'),
      h('li', null, 'GitHub\'s search index lags real star counts slightly, and types are a best guess.'),
      h('li', null, 'Stars measure popularity, not quality.')),
    h('h2', null, 'Open data'),
    P('Everything is CC0: ', h('a', { href: 'download/langstars-data.zip' }, 'langstars-data.zip'), ' (CSV, JSON and the full star history), ',
      h('a', { href: 'data/index.json' }, 'data/index.json'), ', ', h('a', { href: 'data/languages.json' }, 'data/languages.json'), ', and an ',
      h('a', { href: 'feed.xml' }, 'RSS feed'), ` of repos newly over ${minK()}. Source: `, h('a', { href: REPO_URL, ...ext }, REPO_URL.replace('https://', '')),
      '. Fuzzy search uses ', h('a', { href: 'https://www.fusejs.io/', ...ext }, 'Fuse.js'), ' (Apache-2.0).'),
    h('h2', null, 'Keyboard shortcuts'),
    P(h('kbd', null, '/'), ' search · ', h('kbd', null, 'j'), ' ', h('kbd', null, 'k'), ' move between rows · ', h('kbd', null, 'Enter'), ' open repo · ',
      h('kbd', null, 'o'), ' open on GitHub · ', h('kbd', null, 'g'), ' ', h('kbd', null, 'a'), ' ', h('kbd', null, 'c'), ' overview, all, compare · ',
      h('kbd', null, 't'), ' dark mode · ', h('kbd', null, '?'), ' help'));
}
function notFound(msg) {
  return h('div', { class: 'empty' }, h('h1', null, 'Not found'), h('p', null, msg || 'There is no page at this address.'), h('a', { href: '#/' }, 'Back to the overview'));
}

function route() {
  parseHash();
  if (document.activeElement !== $('q')) $('q').value = S.view === 'list' && !S.lang ? S.q : '';
  nav();
  const on = $('nav').querySelector('.on');
  if (on) on.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  const views = { home, list, compare, repo: repoPage, about, missing: () => notFound() };
  sel = -1;
  $('app').replaceChildren(...[views[S.view]()].flat(Infinity).filter(Boolean));   // views may nest arrays
  const titles = { home: 'LangStars — the most-starred GitHub repos by language', list: `${S.lang ? S.lang.name : 'All languages'} · LangStars`,
    compare: 'Compare languages · LangStars', about: 'About · LangStars', missing: 'Not found · LangStars' };
  if (titles[S.view]) document.title = titles[S.view];
  window.scrollTo(0, 0);
}

// ---------- keyboard ----------
let sel = -1;
const rowEls = () => [...document.querySelectorAll('#app table.repos tbody tr')];
function select(i) {
  const rows = rowEls();
  if (!rows.length) return;
  sel = Math.max(0, Math.min(rows.length - 1, i));
  rows.forEach((r, j) => r.classList.toggle('sel', j === sel));
  rows[sel].scrollIntoView({ block: 'nearest' });
}
function toggleTheme() {
  const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = t; store.set('ls-theme', t);
}
function wireHeader() {
  let timer;
  $('q').addEventListener('input', (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const q = e.target.value;
      if (!(S.view === 'list' && !S.lang)) { location.hash = hashFor({ ...CLEAR, lang: null, q }); return; }   // global: lands on #/all
      S.q = q; S.limit = PAGE; if (S.sort === 'relevance' && !q.trim()) S.sort = '';
      syncUrl(); renderList();
    }, 120);
  });
  $('q').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); setTimeout(() => select(0), 150); } });
  document.addEventListener('keydown', (e) => {
    if ($('keys').open) return;
    const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName);
    if (e.key === 'Escape') {
      if (e.target === $('q')) { if ($('q').value) { $('q').value = ''; $('q').dispatchEvent(new Event('input')); } $('q').blur(); return; }
      if (typing) { e.target.blur(); return; }
      if (S.view === 'repo') { history.length > 1 ? history.back() : (location.hash = '#/'); return; }
      if (sel >= 0) { rowEls().forEach((r) => r.classList.remove('sel')); sel = -1; }
      return;
    }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
    const rows = rowEls();
    if (e.key === '/') { e.preventDefault(); $('q').focus(); $('q').select(); }
    else if (e.key === 'j') { e.preventDefault(); select(sel + 1); }
    else if (e.key === 'k') { e.preventDefault(); select(sel < 0 ? 0 : sel - 1); }
    else if (e.key === 'Enter' && sel >= 0 && rows[sel] && !e.target.closest('a,button')) location.hash = rows[sel].dataset.href;
    else if (e.key === 'o') {
      const cur = S.view === 'repo' ? BY_NAME[S.repo.toLowerCase()] : null;
      const url = sel >= 0 && rows[sel] ? rows[sel].dataset.url : cur ? ghUrl(cur) : null;
      if (url) window.open(url, '_blank', 'noopener');
    }
    else if (e.key === 'g') location.hash = '#/';
    else if (e.key === 'a') location.hash = '#/all';
    else if (e.key === 'c') location.hash = '#/compare';
    else if (e.key === 't') toggleTheme();
    else if (e.key === '?') { e.preventDefault(); $('keys').showModal(); }
  });
  $('theme').addEventListener('click', toggleTheme);
  $('keys-btn').addEventListener('click', () => $('keys').showModal());
}

// ---------- boot ----------
Promise.all([getJSON('data/index.json'), getJSON('data/languages.json'), getJSON('data/stats.json')])
  .then(([idx, langs, stats]) => {
    DATA = { repos: idx.repos, langs, stats, types: idx.types };
    for (const r of DATA.repos) { r.topics = r.topics || []; r.short = r.name.split('/')[1]; }
    LANG_BY_NAME = Object.fromEntries(langs.map((l) => [l.name, l]));
    LANG_BY_SLUG = Object.fromEntries(langs.map((l) => [l.slug, l]));
    BY_NAME = Object.fromEntries(DATA.repos.map((r) => [r.name.toLowerCase(), r]));
    TYPE = Object.fromEntries(idx.types.map((t) => [t.id, t.label]));
    FUSE = new Fuse(DATA.repos, {
      keys: [{ name: 'short', weight: 4 }, { name: 'name', weight: 2 }, { name: 'topics', weight: 2 }, { name: 'desc', weight: 1 }],
      threshold: 0.33, ignoreLocation: true, minMatchCharLength: 2,
    });
    $('foot').replaceChildren(`Data from the GitHub API · snapshot ${fmtDate(stats.last_snapshot)} · refreshed Mondays 04:00 UTC · `,
      h('a', { href: '#/about' }, 'Methodology'), ' · ', h('a', { href: 'download/langstars-data.zip' }, 'Open data (CC0)'), ' · ',
      h('a', { href: 'feed.xml' }, `RSS: new over ${minK()}`), ' · ', h('a', { href: REPO_URL, ...ext }, 'Source'), ' · press ', h('kbd', null, '?'), ' for shortcuts');
    wireHeader();
    window.addEventListener('hashchange', route);
    route();
  })
  .catch((e) => {
    $('app').replaceChildren(h('div', { class: 'empty' }, `Could not load data (${e.message}). Build the site with `,
      h('code', null, 'make build'), ' and serve it with ', h('code', null, 'make serve'), '; opening index.html directly does not work.'));
    console.error(e);
  });

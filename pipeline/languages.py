"""Languages LangStars tracks. Adding one is a one-line change: append a Lang(...) row.

  name   GitHub's display name, exactly as the API's `language` field reports it (the repo's primary language)
  slug   the Search API qualifier value (`language:<slug>`), also used in site URLs (#/lang/<slug>)
  color  the language's color from github-linguist (languages.yml), used for tiles and bars
"""
from collections import namedtuple

Lang = namedtuple('Lang', 'name slug color')

LANGUAGES = [
    Lang('C',          'c',          '#555555'),
    Lang('C++',        'cpp',        '#f34b7d'),
    Lang('Java',       'java',       '#b07219'),
    Lang('Python',     'python',     '#3572A5'),
    Lang('JavaScript', 'javascript', '#f1e05a'),
    Lang('TypeScript', 'typescript', '#3178c6'),
    Lang('Go',         'go',         '#00ADD8'),
    Lang('Rust',       'rust',       '#dea584'),
    Lang('C#',         'csharp',     '#178600'),
    Lang('PHP',        'php',        '#4F5D95'),
    Lang('Ruby',       'ruby',       '#701516'),
    Lang('Swift',      'swift',      '#F05138'),
    Lang('Kotlin',     'kotlin',     '#A97BFF'),
    Lang('Dart',       'dart',       '#00B4AB'),
    Lang('Shell',      'shell',      '#89e051'),
    # More: uncomment (or add) one line each.
    # Lang('Scala',    'scala',      '#c22d40'),
    # Lang('Lua',      'lua',        '#000080'),
    # Lang('Zig',      'zig',        '#ec915c'),
    # Lang('Elixir',   'elixir',     '#6e4a7e'),
    # Lang('Haskell',  'haskell',    '#5e5086'),
]

BY_NAME = {l.name: l for l in LANGUAGES}
BY_SLUG = {l.slug: l for l in LANGUAGES}

# Colors (github-linguist) for languages that show up in per-repo byte breakdowns. GraphQL returns colors itself;
# this fills them in when breakdowns came from the REST endpoint, which has none.
LINGUIST_COLORS = {
    'Assembly': '#6E4C13', 'Astro': '#ff5a03', 'Batchfile': '#C1F12E', 'Blade': '#f7523f', 'CMake': '#DA3434', 'CSS': '#663399',
    'Clojure': '#db5855', 'CoffeeScript': '#244776', 'Cuda': '#3A4E3A', 'Cython': '#fedf5b', 'Dockerfile': '#384d54',
    'EJS': '#a91e50', 'Elixir': '#6e4a7e', 'Emacs Lisp': '#c065db', 'Erlang': '#B83998', 'F#': '#b845fc', 'Fortran': '#4d41b1',
    'GLSL': '#5686a5', 'Groovy': '#4298b8', 'HCL': '#844FBA', 'HTML': '#e34c26', 'Handlebars': '#f7931e', 'Haskell': '#5e5086',
    'Jinja': '#a52a22', 'Julia': '#a270ba', 'Jupyter Notebook': '#DA5B0B', 'Less': '#1d365d', 'Lua': '#000080', 'MDX': '#fcb32c',
    'Makefile': '#427819', 'Meson': '#007800', 'Metal': '#8f14e9', 'Nix': '#7e7eff', 'OCaml': '#ef7a08', 'Objective-C': '#438eff',
    'Objective-C++': '#6866fb', 'Perl': '#0298c3', 'PowerShell': '#012456', 'R': '#198CE7', 'SCSS': '#c6538c', 'Scala': '#c22d40',
    'Smarty': '#f0c040', 'Solidity': '#AA6746', 'Starlark': '#76d275', 'Svelte': '#ff3e00', 'TSQL': '#e38c00', 'Tcl': '#e4cc98',
    'TeX': '#3D6117', 'V': '#4f87c4', 'Vim Script': '#199f4b', 'Vue': '#41b883', 'WebAssembly': '#04133b', 'Zig': '#ec915c',
}
LINGUIST_COLORS.update({l.name: l.color for l in LANGUAGES})

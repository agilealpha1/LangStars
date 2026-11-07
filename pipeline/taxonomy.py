"""Repo types: 10 fixed ids plus 'other' (ids are stable; the site and the label cache key off them), and the
keyword rules used when ANTHROPIC_API_KEY is missing.

Rules score each type from three signals, weighted by how deliberate they are: the repo name and description are
written by the owner for humans (5 points per matching phrase), GitHub topics are cheap to add and often padded
(2 points per matching topic). The highest score wins; ties go to the type listed first, so specific types
(learning resource, AI/ML, database, game, mobile) beat broad ones (library, tool).
"""
import re

TYPES = [
    # id,          label,                    one-line definition (shown to the LLM and on the About page)
    ('learning',  'Learning resource/list', 'Tutorials, books, courses, roadmaps, interview prep, algorithm collections and curated awesome-lists.'),
    ('ai-ml',     'AI/ML',                  'Machine learning, deep learning, LLMs, AI agents and apps, model training and inference.'),
    ('database',  'Database',               'Databases, storage engines, key-value stores, search engines and query engines.'),
    ('game',      'Game',                   'Games, game engines and game-development tools.'),
    ('mobile',    'Mobile',                 'Mobile apps and mobile development (Android, iOS, cross-platform).'),
    ('systems',   'OS/systems',             'Operating systems, kernels, compilers, language runtimes, emulators, virtualization and embedded.'),
    ('framework', 'Framework',              'Application or web frameworks you build a whole program inside.'),
    ('web',       'Web',                    'Web apps, frontend tooling, browsers, CSS, static-site generators and self-hosted web services.'),
    ('library',   'Library',                'Libraries, SDKs and packages you import into your own code.'),
    ('tool',      'Tool/CLI',               'Command-line tools, developer tools, editors, desktop apps and utilities.'),
    ('other',     'Other',                  'Fits none of the above.'),
]
TYPE_IDS = [t[0] for t in TYPES]
TYPE_LABELS = {t[0]: t[1] for t in TYPES}
TAXONOMY_VERSION = 1          # bump to relabel everything after changing TYPES

W_TEXT, W_TOPIC = 5, 2

# phrases matched against "owner/name + description" (lowercased)
TEXT_RULES = {
    'learning':  r'\b(awesome|curated (list|collection)|list of|roadmaps?|interview|tutorials?|courses?|books?|cheat ?sheets?|'
                 r'learn(ing)? (to|how)|for beginners|guide to|study|lessons|exercises|examples? of|algorithms? (implemented|in)|'
                 r'implemented in|leetcode|system design|free programming|handbook|collection of|cookbook|best practices|style ?guide|'
                 r'concepts|explained|notes)\b',
    'ai-ml':     r'\b(machine learning|deep learning|neural (network|net)s?|llms?|large language models?|gpt|chatgpt|openai|claude|'
                 r'gemini|ai agents?|agentic|artificial intelligence|\bai\b|transformers?|diffusion|stable diffusion|inference|'
                 r'computer vision|nlp|natural language|speech recognition|text[- ]to[- ]speech|embeddings?|rag|mcp|'
                 r'model context protocol|pytorch|tensorflow|reinforcement learning|generative|chatbot|copilot|ollama|coding agents?|'
                 r'agent skills|skills for (ai|agents|claude|codex))\b',
    'database':  r'\b(databases?|sql|nosql|key[- ]value|time[- ]series|olap|oltp|storage engine|vector (database|search|store)|'
                 r'search engine|query engine|data ?warehouse|document store|graph database)\b',
    'game':      r'\b(games?|game engine|gamedev|game development|minecraft|godot|roguelike|voxel|retro gaming|game emulator|rpg)\b',
    'mobile':    r'\b(android|ios|iphone|ipad|mobile|react native|flutter|swiftui|jetpack compose|cross[- ]platform apps?)\b',
    'systems':   r'\b(operating systems?|kernel|compilers?|programming language|interpreter|virtual machine|runtime|emulators?|'
                 r'hypervisor|virtuali[sz]ation|containers?|filesystem|embedded|firmware|microcontrollers?|rtos|bootloader|'
                 r'webassembly|wasm|linux distribution|init system|garbage collector|jit|superset of|compiles to)\b',
    'framework': r'\b(framework|web framework|full[- ]stack framework|application framework|meta[- ]framework|microframework)\b',
    'web':       r'\b(web ?(app|apps|application|site|sites|ui|server|browser|interface)|websites?|frontend|front[- ]end|browser|css|'
                 r'html|static site|cms|blog(ging)?|self[- ]hosted|http server|reverse proxy|dashboard|spa|single[- ]page)\b',
    'library':   r'\b(library|libraries|sdk|package|module|bindings|components?|ui kit|toolkit|api client|parser|wrapper)\b',
    'tool':      r'\b(cli|command[- ]line|terminal|tools?|utility|utilities|editor|ide|shell|linter|formatter|build (tool|system)|'
                 r'package manager|devtools|developer tools|desktop app|app for (mac|macos|windows|linux)|plugin|extension|proxy|vpn|'
                 r'downloader|automation|dotfiles|launcher|manager|sync\w*|monitoring|observability|diagrams?)\b',
}

TOPIC_RULES = {
    'learning':  {'awesome', 'awesome-list', 'awesome-lists', 'education', 'tutorial', 'tutorials', 'interview', 'interview-questions',
                  'interview-preparation', 'books', 'book', 'roadmap', 'roadmaps', 'learning', 'learn', 'course', 'courses', 'cheatsheet',
                  'algorithms', 'algorithm', 'leetcode', 'data-structures', 'system-design', 'lists', 'resources', 'beginner-friendly'},
    'ai-ml':     {'machine-learning', 'deep-learning', 'llm', 'llms', 'ai', 'artificial-intelligence', 'nlp', 'computer-vision', 'pytorch',
                  'tensorflow', 'chatgpt', 'openai', 'gpt', 'agents', 'ai-agents', 'ai-agent', 'agent', 'generative-ai', 'llama', 'rag',
                  'mcp', 'claude', 'stable-diffusion', 'diffusion', 'transformers', 'neural-network', 'ml', 'gemini', 'ollama', 'langchain',
                  'speech-recognition', 'tts', 'reinforcement-learning', 'data-science', 'chatbot', 'llmops', 'vector-database'},
    'database':  {'database', 'databases', 'sql', 'nosql', 'key-value', 'time-series', 'timeseries', 'olap', 'distributed-database',
                  'kv-store', 'search-engine', 'postgresql', 'mysql', 'redis', 'sqlite', 'storage', 'analytics-database', 'graph-database'},
    'game':      {'game', 'games', 'game-engine', 'gamedev', 'game-development', 'minecraft', 'unity', 'godot', 'gaming'},
    'mobile':    {'android', 'ios', 'mobile', 'flutter', 'react-native', 'android-app', 'ios-app', 'swiftui', 'jetpack-compose', 'mobile-app'},
    'systems':   {'kernel', 'operating-system', 'os', 'compiler', 'programming-language', 'emulator', 'virtualization', 'embedded',
                  'linux-kernel', 'rtos', 'interpreter', 'runtime', 'webassembly', 'wasm', 'containers', 'docker', 'hypervisor', 'llvm'},
    'framework': {'framework', 'web-framework', 'frameworks', 'mvc', 'fullstack'},
    'web':       {'web', 'frontend', 'css', 'html', 'nextjs', 'cms', 'static-site-generator', 'website', 'browser', 'webapp',
                  'self-hosted', 'selfhosted', 'web-app', 'dashboard', 'http-server', 'reverse-proxy', 'tailwindcss'},
    'library':   {'library', 'sdk', 'package', 'components', 'ui-components', 'component-library', 'api-client', 'parser'},
    'tool':      {'cli', 'command-line', 'terminal', 'devtools', 'tool', 'tools', 'developer-tools', 'productivity', 'shell', 'editor',
                  'ide', 'vscode', 'neovim', 'vim', 'linter', 'formatter', 'build-tool', 'package-manager', 'proxy', 'vpn', 'automation',
                  'dotfiles', 'macos', 'windows', 'desktop', 'utility'},
}
_TEXT_RX = {k: re.compile(v) for k, v in TEXT_RULES.items()}


def scores(repo):
    text = f"{repo.get('full_name') or ''} {repo.get('description') or ''}".lower().replace('_', ' ')
    topics = {str(t).lower() for t in repo.get('topics') or []}
    out = {}
    for tid in TYPE_IDS[:-1]:
        s = W_TEXT * len(set(m.group(0) for m in _TEXT_RX[tid].finditer(text)))
        s += W_TOPIC * len(topics & TOPIC_RULES[tid])
        if s:
            out[tid] = s
    return out


def rule_type(repo):
    """Best type id by keyword rules; 'other' when nothing matches."""
    s = scores(repo)
    if not s:
        return 'other'
    best = max(s.values())
    return next(t for t in TYPE_IDS if s.get(t) == best)

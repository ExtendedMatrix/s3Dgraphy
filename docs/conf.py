# Configuration file for the Sphinx documentation builder.
# s3dgraphy documentation configuration

import os
import sys
import datetime

# Add the project root and src to Python path
sys.path.insert(0, os.path.abspath('..'))
sys.path.insert(0, os.path.abspath('../src'))

# -- Project information -----------------------------------------------------
project = 's3dgraphy'
copyright = f'2024-{datetime.datetime.now().year}, Emanuel Demetrescu'
author = 'Emanuel Demetrescu'

# Read version from package or pyproject.toml.
# Best-effort dynamic lookup, falling back to a hardcoded string so the
# build never fails on a fresh checkout that has not been pip-installed.
def _read_version():
    # 1) Try importing the installed package
    try:
        import s3dgraphy  # type: ignore
        v = getattr(s3dgraphy, "__version__", None)
        if v:
            return v
    except Exception:
        pass
    # 2) Try parsing pyproject.toml directly
    try:
        import re
        pyproject = os.path.join(os.path.abspath('..'), 'pyproject.toml')
        with open(pyproject, 'r', encoding='utf-8') as fh:
            text = fh.read()
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if m:
            return m.group(1)
    except Exception:
        pass
    # 3) Hardcoded fallback (keep in sync with pyproject.toml on each release)
    # TODO 1.6: drop fallback once Sphinx is always run from an installed env.
    return '1.5.1'

version = _read_version()
release = version

# -- General configuration ---------------------------------------------------
extensions = [
    # Core Sphinx extensions
    'sphinx.ext.autodoc',           # Auto-generate API docs
    'sphinx.ext.autosummary',       # Generate summaries
    'sphinx.ext.napoleon',          # Google/NumPy docstring style
    'sphinx.ext.viewcode',          # Add source code links
    'sphinx.ext.intersphinx',       # Cross-reference other docs
    'sphinx.ext.todo',              # TODO items
    'sphinx.ext.coverage',          # Documentation coverage
    'sphinx.ext.ifconfig',          # Conditional content
    
    # External extensions
    'myst_parser',                  # Markdown support
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------
html_theme = 'sphinx_rtd_theme'
html_theme_options = {
    'analytics_id': '',  # Google Analytics ID
    'analytics_anonymize_ip': False,
    'logo_only': False,
    'display_version': True,
    'prev_next_buttons_location': 'bottom',
    'style_external_links': False,
    'vcs_pageview_mode': '',
    'style_nav_header_background': '#2980B9',
    # Toc options
    'collapse_navigation': True,
    'sticky_navigation': True,
    'navigation_depth': 4,
    'includehidden': True,
    'titles_only': False
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Custom CSS. Il marchio arriva da `stratigraph-brand`, vendorizzato dal suo
# `docs-theme/sync-brand-docs.sh` come lo vendorizzano le applicazioni; chiaro e
# scuro seguono l'impostazione di sistema di chi legge.
html_css_files = [
    'brand/stratigraph-theme.css',
    'brand/skins.css',
    'brand/sphinx-rtd-bridge.css',
    'custom.css',
]

# L'interruttore delle due facce: chiaro, scuro, come il sistema. Senza
# scelta esplicita vale il sistema di chi legge, che è il modo di serie.
html_js_files = ['brand/brand-theme-toggle.js']

# -- Options for LaTeX / PDF output ------------------------------------------
#
# Read the Docs builds a PDF for this version too, and under pdfLaTeX it could
# not: this documentation contains characters pdfLaTeX's 8-bit fonts cannot
# encode, and each one is a FATAL error rather than a missing glyph. Two
# settings fix it, and both are deliberately undemanding of the build image.
#
# 1. XeLaTeX. An unmapped character becomes a warning and the build completes.
#    The `-pdf` that Read the Docs hardcodes stays harmless: with this setting
#    Sphinx writes $pdflatex = 'xelatex ...' into latexmkrc, so the flag picks
#    XeTeX anyway.
# 2. makeindex rather than xindy, which Sphinx would otherwise prefer under
#    XeLaTeX. makeindex is enough for an English index and ships everywhere.
#
# The fonts are guarded: a missing family costs glyphs in the PDF, never the
# build. No extra \usepackage is added, for the same reason.
latex_engine = 'xelatex'
latex_use_xindy = False

latex_elements = {
    'papersize': 'a4paper',
    'pointsize': '10pt',
    'figure_align': 'htbp',
    'fontpkg': r"""
\IfFontExistsTF{DejaVu Serif}
  {\setmainfont{DejaVu Serif}}
  {\IfFontExistsTF{FreeSerif}{\setmainfont{FreeSerif}}{}}
\IfFontExistsTF{DejaVu Sans}
  {\setsansfont{DejaVu Sans}}
  {\IfFontExistsTF{FreeSans}{\setsansfont{FreeSans}}{}}
\IfFontExistsTF{DejaVu Sans Mono}
  {\setmonofont{DejaVu Sans Mono}[Scale=MatchLowercase]}
  {\IfFontExistsTF{FreeMono}{\setmonofont{FreeMono}[Scale=MatchLowercase]}{}}
""",
    'preamble': r"""
% Long identifiers (IRIs, dotted module paths) must be allowed to break, or
% they overflow the text block in a two-column table.
\sloppy
""",
}

latex_documents = [
    ('index', 's3dgraphy.tex', 's3dgraphy Documentation',
     'Emanuel Demetrescu', 'manual'),
]

# Show URLs of external links as footnotes: a printed page cannot be clicked.
latex_show_urls = 'footnote'


# -- Extension configuration -------------------------------------------------

# -- Options for autodoc ----------------------------------------------------
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'show-inheritance': True,
    # 'imported-members': True is deliberately omitted in 1.5:
    # it created hundreds of duplicate-object and ambiguous-xref
    # warnings (every Node/Edge re-exported via `from .x import Y`
    # appeared once per importing module). Re-enable per-page with
    # :imported-members: when needed.
}

# -- Options for autosummary ------------------------------------------------
autosummary_generate = True
autosummary_generate_overwrite = False

# -- Options for napoleon ---------------------------------------------------
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True

# -- Options for intersphinx ------------------------------------------------
intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'pandas': ('https://pandas.pydata.org/docs/', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
    'networkx': ('https://networkx.org/documentation/stable/', None),
}

# -- Options for todo extension ---------------------------------------------
todo_include_todos = True

# -- Options for MyST parser -----------------------------------------------
myst_enable_extensions = [
    "deflist",
    "tasklist",
    "colon_fence",
    "fieldlist",
    "linkify",
]

# Generate implicit header anchors for MyST so RST toctrees can cross-link
# into specific sections of the Markdown design notes
# (DATA_FORMALIZATIONS.md, GRAPHML_EXPORT.md).
myst_heading_anchors = 3

# Suppress noisy warnings for non-canonical MD anchors during the 1.5
# documentation push. Drop once every cross-reference is migrated.
suppress_warnings = [
    # EPUB non conosce il tipo di un .woff2 e lo dice: i caratteri del
    # marchio servono alla pagina web, non al libro.
    'epub.unknown_project_files',
    'myst.header',
    # autodoc's cross-reference resolution treats `from x import Y`
    # in two modules as two valid targets for `Y`. The duplicates are
    # benign (autoclass picks the right one via the qualified name in
    # the directive) but produce a lot of build noise. Suppress.
    'ref.python',
    'misc.highlighting_failure',
    # Same root cause: when the package re-exports symbols at multiple
    # qualified paths and we autodoc more than one of those paths, the
    # individual member definitions duplicate. Benign in practice.
    'autosectionlabel.*',
    'app.add_directive',
]

# -- Custom configuration ---------------------------------------------------

# Master document (index file)
master_doc = 'index'

# Source file suffixes
# myst_parser registers .md automatically when loaded as an extension
source_suffix = ['.rst', '.md']

# Language for content autogenerated by Sphinx
language = 'en'

# HTML context for templates
html_context = {
    'display_github': True,
    'github_user': 'zalmoxes-laran',
    'github_repo': 's3dgraphy',
    'github_version': 'main',
    'conf_py_path': '/docs/',
}

# Show last updated timestamp
html_last_updated_fmt = '%b %d, %Y'

def setup(app):
    """Custom setup function for additional configuration."""
    app.add_css_file('custom.css')

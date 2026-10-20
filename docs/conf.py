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
    return '1.6.0.dev7'

version = _read_version()
release = version

# Il badge di versione non si scrive a mano: si compone dalla versione che
# _read_version() ha appena risolto, cosi' non puo' restare indietro rispetto
# al pacchetto. Shields.io vuole i trattini raddoppiati.
_badge_version = version.replace("-", "--")
rst_prolog = """
.. |version_badge| image:: https://img.shields.io/badge/version-%s-blue.svg
   :target: https://pypi.org/project/s3dgraphy/
   :alt: Version %s
""" % (_badge_version, version)

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

# Custom CSS
html_css_files = [
    'custom.css',
]

# -- Options for LaTeX / PDF output ------------------------------------------
#
# The PDF is not a convenience format: it is what gets deposited in a repository
# and cited by version DOI, so a change that breaks it breaks a citation path.
# Two things had to be settled for it to build at all.
#
# 1. XeLaTeX rather than pdfLaTeX. This documentation legitimately contains
#    characters pdfLaTeX's 8-bit fonts cannot encode — mathematical symbols
#    (∈ ≤ ⊂ ≈), arrows, box drawing in ASCII diagrams, and Greek and Arabic in
#    the internationalisation examples. Under pdfLaTeX each one is a FATAL
#    error (197 of them, before this change); under XeLaTeX an unmapped glyph
#    is a warning and the build completes. Emoji still have no glyph in the
#    chosen font and are simply dropped from the PDF; they carry no meaning
#    the surrounding prose does not.
# 2. DejaVu rather than Sphinx's XeLaTeX default (FreeSerif/FreeSans/FreeMono).
#    DejaVu covers everything above, and it is present in both the Read the
#    Docs build image and an ordinary texlive-fonts-recommended install, which
#    the Free fonts are not everywhere.
latex_engine = 'xelatex'

# Sphinx defaults to `xindy` for the index under XeLaTeX. `makeindex` is enough
# for an English, Latin-script index and ships with every texlive base install,
# while `xindy` does not — and a PDF that is cited by DOI should not be able to
# fail over an optional indexing binary.
latex_use_xindy = False

latex_elements = {
    'papersize': 'a4paper',
    'pointsize': '10pt',
    'figure_align': 'htbp',
    # Guarded: a missing font must not be able to fail the build. If DejaVu is
    # absent, the Free fonts are tried, and failing those fontspec's own default
    # stands — more glyphs go missing in the PDF, and it still builds.
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
    # No extra packages here on purpose: every \usepackage is one more thing
    # that can be absent from a build image and take the PDF down with it.
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

# Optional / heavy third-party libraries that some submodules import at
# module level. They are NOT part of the `docs` extra, so on Read the Docs
# (which runs `pip install .[docs]`) they are absent and autodoc would fail
# to import the dependent modules — leaving the sync/ subsystem and the RDF
# exporter undocumented. Mocking them lets autodoc introspect signatures and
# docstrings without the real packages installed.
#   - sqlalchemy / psycopg2 : s3dgraphy.sync.* (PyArchInit SQLite/PostgreSQL bridge)
#   - rdflib                : s3dgraphy.exporter.rdf_exporter
#   - bpy                   : Blender-only code paths guarded at runtime
# The core hard deps (pandas, lxml, openpyxl, networkx) are installed
# transitively by `pip install .` and therefore do NOT need mocking.
autodoc_mock_imports = [
    'sqlalchemy',
    'psycopg2',
    'rdflib',
    'bpy',
]

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
# Render docstring "Attributes:" sections as :ivar: fields rather than as
# standalone py:attribute objects. This avoids the "duplicate object
# description" warnings that arise when a class both documents an attribute
# in its docstring and exposes it as an autodoc member (e.g. dataclass
# fields, the `node_type` class var).
napoleon_use_ivar = True
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
# Il proprietario e il nome del repository: sono ciò con cui Sphinx costruisce
# i link «edit on GitHub» di ogni pagina. Il 22 settembre 2026 s3Dgraphy è
# passato in `github.com/ExtendedMatrix` e questi due valori sono rimasti
# indietro — funzionavano per il redirect di GitHub, che è una cortesia e non
# un contratto: smette il giorno in cui qualcuno riusa il nome vecchio, e da
# quel giorno «edit on GitHub» porta al repository di un altro.
html_context = {
    'display_github': True,
    'github_user': 'ExtendedMatrix',
    'github_repo': 's3Dgraphy',
    'github_version': 'main',
    'conf_py_path': '/docs/',
}

# Show last updated timestamp
html_last_updated_fmt = '%b %d, %Y'

def _regenerate_report(app=None):
    """Refresh docs/generated-report.md from the datamodels before the build.

    Every count and version in this documentation is derived, never typed. This
    hook runs the generator on ``builder-inited`` so the published page cannot be
    older than the datamodels it describes. It is best-effort: a checkout where
    the package is not importable still builds, and the previously committed
    report is used as-is.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(here, 'generated-report.md')
    try:
        from s3dgraphy.tools import deliverable_report
    except Exception as exc:  # noqa: BLE001
        print(f'[s3dgraphy] generated-report.md NOT regenerated ({exc}); '
              f'using the committed copy.')
        return
    try:
        text = deliverable_report.render(deliverable_report.collect())
        with open(target, 'w', encoding='utf-8') as fh:
            fh.write(text + '\n')
        print('[s3dgraphy] generated-report.md regenerated from the datamodels.')
    except Exception as exc:  # noqa: BLE001
        print(f'[s3dgraphy] generated-report.md NOT regenerated ({exc}); '
              f'using the committed copy.')


# The CRMem declarations page (classes and properties, with em.ttl and em.rdf
# beside it) is generated into _ontology/ontology/ and copied as is into the
# site, at <docs>/ontology/. Never committed: it is rebuilt from em.ttl on
# every build, so it cannot drift from the ontology.
_ONTOLOGY_EXTRA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_ontology')
os.makedirs(_ONTOLOGY_EXTRA, exist_ok=True)
html_extra_path = ['_ontology']


def _regenerate_ontology_page(app=None):
    """Write the CRMem declarations page before the build (best-effort)."""
    try:
        from pathlib import Path
        from s3dgraphy.tools import ontology_html
        ontology_html.build(Path(_ONTOLOGY_EXTRA) / 'ontology')
        print('[s3dgraphy] CRMem declarations page regenerated from em.ttl.')
    except Exception as exc:  # noqa: BLE001
        print(f'[s3dgraphy] CRMem declarations page NOT regenerated ({exc}).')


def setup(app):
    """Custom setup function for additional configuration."""
    app.add_css_file('custom.css')
    app.connect('builder-inited', _regenerate_report)
    app.connect('builder-inited', _regenerate_ontology_page)

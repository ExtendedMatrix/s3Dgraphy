# EMStudio Python API — the reference of ``em``, generated from the code.
#
# A site of its own, separate from the EMStudio manual, as Blender's Python API
# is separate from Blender's manual: written pages (Quickstart, overview, best
# practice, gotchas, change log) plus a reference generated at every build from
# the docstrings of ``s3dgraphy.em`` (autodoc), the datamodels (types), the slot
# table (slots) and EMStudio's command registry (commands — generated where an
# EMStudio checkout is at hand, committed otherwise).
#
# Build:   sphinx-build -W --keep-going -b html docs-api docs-api/_build/html
# Italian: sphinx-build -W --keep-going -b html -D language=it docs-api docs-api/_build/html-it

import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))   # this checkout's library, not an installed one

# -- Versions: the API's own, then the library's --------------------------------
_em_init = (ROOT / "src/s3dgraphy/em/__init__.py").read_text(encoding="utf-8")
API_VERSION = re.search(r'^API_VERSION\s*=\s*"([^"]+)"', _em_init, re.M).group(1)
_pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
S3D_VERSION = re.search(r'^version\s*=\s*"([^"]+)"', _pyproject, re.M).group(1)

project = "EMStudio Python API"
copyright = "2026, Consiglio Nazionale delle Ricerche (CNR) — Istituto di Scienze del Patrimonio Culturale"
author = "Emanuel Demetrescu"
version = API_VERSION
release = f"{API_VERSION} (s3dgraphy {S3D_VERSION})"

# -- The generated reference: written before Sphinx reads the sources ----------
# types and slots need only this repository, so they are rewritten at every
# build (Read the Docs included); commands need EMStudio's sources and keep the
# committed pages when there is no EMStudio next to this checkout.
for tool in ("gen_types.py", "gen_slots.py", "gen_commands.py"):
    path = HERE / "_tools" / tool
    if path.exists():
        subprocess.run([sys.executable, str(path)], check=(tool != "gen_commands.py"))

# -- General configuration --------------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {"members": True, "undoc-members": False, "show-inheritance": True}
# dtcstamp is a light dependency, but Read the Docs installs only what
# requirements.txt names: mock it so a missing wheel never empties a page.
autodoc_mock_imports = ["dtcstamp"]
autosummary_generate = False
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_ivar = True     # «Attributes:» as fields: autodoc also finds the annotated ones

intersphinx_mapping = {"python": ("https://docs.python.org/3/", None)}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "_tools", "locale"]

# The pages carry the API version they were made from (rst_epilog: |api|).
rst_epilog = f"""
.. |api| replace:: {API_VERSION}
.. |s3d| replace:: {S3D_VERSION}
"""

# -- Languages, as the EMStudio manual -------------------------------------------
language = os.environ.get("READTHEDOCS_LANGUAGE", os.environ.get("DOCS_LANGUAGE", "en")).split("-")[0]
locale_dirs = ["locale/"]
gettext_compact = False
gettext_uuid = False
gettext_location = False
RTL_LANGUAGES = {"he"}
rtl = language in RTL_LANGUAGES

# -- HTML: the theme and the brand of the EMStudio manual ------------------------
html_theme = "sphinx_rtd_theme"
html_title = f"EMStudio Python API {API_VERSION}"
html_static_path = ["_assets"]
# MICRO-TIL004 · the foot of every page (_templates/footer.html, vendored from
# stratigraph-brand): the EMStudio manual, and the small block of the funding.
# MICRO-SEG04: the block names the projects of the manual's page «Funding»
# (today only StratiGraph), and links to it.
# MICRO-SEG06: the text of the reference is CC BY 4.0, as the other EM manuals
# (docs-api/LICENSE, holder the institute): the line of the rights is shown.
_MANUAL = f"https://docs.extendedmatrix.org/projects/emstudio-doc/{'it' if language == 'it' else 'en'}/1.6/"
_FOOT = {
    "en": {
        "manual": "EMStudio manual",
        "text": "EMStudio, whose scripting API this reference describes, has been developed with "
                "the support of StratiGraph (Horizon Europe, grant agreement 101232855).",
        "disclaimer": "Funded by the European Union. Views and opinions expressed are however "
                      "those of the author(s) only and do not necessarily reflect those of the "
                      "European Union or the European Research Executive Agency (REA). Neither "
                      "the European Union nor the granting authority can be held responsible "
                      "for them.",
        "more": "Funding",
    },
    "it": {
        "manual": "Manuale di EMStudio",
        "text": "EMStudio, di cui questo riferimento descrive l'API di scripting, è stato "
                "sviluppato con il sostegno di StratiGraph (Horizon Europe, grant agreement "
                "n. 101232855).",
        "disclaimer": "Finanziato dall'Unione europea. I punti di vista e le opinioni espressi "
                      "sono tuttavia esclusivamente quelli degli autori e non riflettono "
                      "necessariamente quelli dell'Unione europea o dell'Agenzia esecutiva "
                      "europea per la ricerca (REA). Né l'Unione europea né l'autorità che "
                      "concede il finanziamento possono esserne ritenute responsabili.",
        "more": "Finanziamenti",
    },
}
_foot = _FOOT.get(language, _FOOT["en"])
html_context = {
    "rtl": rtl,
    "sg_footer_links": [(_foot["manual"], _MANUAL)],
    "sg_funding": {
        "text": _foot["text"],
        "disclaimer": _foot["disclaimer"],
        "more": (_foot["more"], _MANUAL + "acknowledgements.html"),
    },
    "sg_rights": True,
}
html_css_files = ["brand/stratigraph-theme.css", "brand/skins.css", "brand/sphinx-rtd-bridge.css"] + (
    ["rtl.css"] if rtl else [])
html_js_files = ["brand/brand-theme-toggle.js"]
html_theme_options = {"navigation_depth": 3, "collapse_navigation": False}
# MICRO-TIL00 · the site is a sub-project of docs.extendedmatrix.org: every page
# names its canonical address there (Read the Docs gives the version's own;
# a local build points at «latest»).
html_baseurl = os.environ.get(
    "READTHEDOCS_CANONICAL_URL",
    "https://docs.extendedmatrix.org/projects/emstudio-python-api/en/latest/")
suppress_warnings = ["epub.unknown_project_files"]

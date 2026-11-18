"""Extensions — community packages, plugins and mixed packages — installed by parts.

MICRO-PL04-INSTALLAZIONE-PER-PARTI, row W21 of the extensions plan (E.D.,
18 Nov 2026). An archive with an ``em-extension.toml`` carries data
(``[data]``: an EM Profile and the vocabularies it brings), code (``[code]``:
a Python plugin) or both. One action installs it with three deliveries, each
to its owner — the vocabulary manager (:mod:`s3dgraphy.vocabularies`), the
packages' folder (:mod:`s3dgraphy.profiles`), the plugins' folder
(``~/.s3dgraphy/plugins/<source>/<id>/<code version>/``) — and one register
that ties the parts together (``~/.s3dgraphy/extensions/installed.json``).
SPEC-pacchetto §16.3–§16.7, SPEC-plugin §17.

* :func:`preview` — the two panels of the confirmation, nothing written;
* :func:`install` / :func:`update` / :func:`install_code` — data first, code
  after, the code falls alone; ``parts="data"`` is «Data only»;
* :func:`remove_code` / :func:`remove_data` / :func:`remove` — the three
  removals; :func:`removal_plan` says before what each would do;
* :func:`enable` / :func:`disable` / :func:`active_code` — one active code
  version per id, one module per host (the clash refused at activation).

* :func:`validate_archive` — the validator of an archive, the same for the
  window, the command line and the CI; :func:`build` — the curator's folder
  to ``<id>-<version>.zip``, the envelope completed (W19,
  ``python -m s3dgraphy.extensions validate|build``).

The window (EMStudio W6) asks; this library does. It never asks a question
itself: the trust is a parameter, and :func:`preview` says when it is needed.
"""
from .store import (ENABLED_FILE, EXTENSIONS_ENV, PARTS, PLUGINS_ENV, REGISTER_FILE, SOURCE_DISK, TRUST_KEYS,
                    ExtensionError, active_code, archive_hash, disable, enable, extensions_dir, find_cycle, get,
                    install, install_code, installed, plugins_dir, preview, read_enabled, read_register,
                    removal_plan, remove, remove_code, remove_data, requirements, this_platform, update,
                    wheel_platforms)
from .build import DEFAULT_EXCLUDES, build, dump_toml, select_files
from .validate import ARCHIVE_CODE_PROBLEMS, validate_archive
from .wheels import PLATFORMS

__all__ = [
    "EXTENSIONS_ENV", "PLUGINS_ENV", "REGISTER_FILE", "ENABLED_FILE", "SOURCE_DISK", "PARTS", "TRUST_KEYS",
    "ExtensionError", "extensions_dir", "plugins_dir", "read_register", "read_enabled", "this_platform",
    "wheel_platforms", "archive_hash", "find_cycle", "requirements", "preview", "install", "update",
    "install_code", "installed", "get", "enable", "disable", "active_code", "removal_plan", "remove_code",
    "remove_data", "remove", "validate_archive", "ARCHIVE_CODE_PROBLEMS", "PLATFORMS", "build", "dump_toml",
    "select_files", "DEFAULT_EXCLUDES",
]

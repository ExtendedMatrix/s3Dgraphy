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

* :func:`server_generate` — a folder of archives to its ``index.json`` in
  the form of Blender's Listing API v1 (X1, ``python -m
  s3dgraphy.extensions server-generate``); :func:`repository_checks` — what
  only a repository sees; :func:`validate_index` / :func:`verify_archive` —
  for the clients of a repository.

* :func:`add_repository` / :func:`sync` / :func:`available` /
  :func:`install_from` — the repositories of this machine (X2): an index
  read (``https``, ``file://``, a NAS), the archive checked against its
  ``archive_hash`` before it is opened, the ``blocklist`` respected,
  ``[requires]`` resolved, tier C fetched; :func:`online_access` — «Allow
  online access», off by default, one switch for the machine.

* :func:`versions` / :func:`use_code` — the versions side by side, and
  going back to an older code without a download; :func:`check_updates` /
  :func:`update_all` — «Update all»; :func:`document_updates` /
  :func:`redeclare` — «this file uses 1.0.0, 1.1.0 is here»;
  :func:`remove_version` / :func:`prune_code` / :func:`leftovers` /
  :func:`clean` — clean removal; ``build(split_platforms=True)`` — one
  archive per platform with its wheels only (X3).

* :func:`dev_dir` / :func:`set_dev_dir` / :func:`dev_code` — the plugins'
  development folder (``plugins_dev_dir``, W15a): loaded where they are,
  marked ``dev``, never installed; the host decides when it counts.

The window (EMStudio W6) asks; this library does. It never asks a question
itself: the trust is a parameter, and :func:`preview` says when it is needed.
"""
from .store import (ENABLED_FILE, EXTENSIONS_ENV, PARTS, PLUGINS_ENV, REGISTER_FILE, SOURCE_DISK, TRUST_KEYS,
                    ExtensionError, active_code, archive_hash, disable, enable, extensions_dir, find_cycle, get,
                    install, install_code, installed, plugins_dir, preview, read_enabled, read_register,
                    removal_plan, remove, remove_code, remove_data, requirements, this_platform, update,
                    wheel_platforms, code_folders)
from .build import DEFAULT_EXCLUDES, build, dump_toml, select_files
from .validate import ARCHIVE_CODE_PROBLEMS, validate_archive
from .dev import DEV_ENV, SOURCE_DEV, describe_dev, dev_code, dev_dir, dev_dir_setting, set_dev_dir
from .wheels import PLATFORMS
from .repository import (INDEX_FILE, INDEX_VERSION, index_entry, repository_checks, server_generate, validate_index,
                         verify_archive)
from .remote import (OFFICIAL_URL, ONLINE_ENV, RepoError, add_repository, available, cached_index, download,
                     get_repository, install_from, normalize_url, online_access, online_access_setting,
                     plan_install, preview_from, remove_repository, repositories, set_online_access, sync,
                     update_from, update_repository, updates, check_updates, update_all, for_platform)
from .lifecycle import (changelog, clean, document_updates, leftovers, prune_code, redeclare, remove_version,
                      use_code, versions)

__all__ = [
    "EXTENSIONS_ENV", "PLUGINS_ENV", "REGISTER_FILE", "ENABLED_FILE", "SOURCE_DISK", "PARTS", "TRUST_KEYS",
    "ExtensionError", "extensions_dir", "plugins_dir", "read_register", "read_enabled", "this_platform",
    "wheel_platforms", "archive_hash", "find_cycle", "requirements", "preview", "install", "update",
    "install_code", "installed", "get", "enable", "disable", "active_code", "removal_plan", "remove_code",
    "remove_data", "remove", "validate_archive", "ARCHIVE_CODE_PROBLEMS", "PLATFORMS", "build", "dump_toml",
    "select_files", "DEFAULT_EXCLUDES",
    "INDEX_FILE", "INDEX_VERSION", "index_entry", "repository_checks", "server_generate", "validate_index",
    "verify_archive",
    "OFFICIAL_URL", "ONLINE_ENV", "RepoError", "online_access", "online_access_setting", "set_online_access",
    "normalize_url", "repositories", "get_repository", "add_repository", "update_repository", "remove_repository",
    "sync", "cached_index", "available", "updates", "download", "plan_install", "preview_from", "install_from",
    "update_from",
    "check_updates", "update_all", "for_platform", "code_folders", "versions", "use_code", "remove_version",
    "prune_code", "leftovers", "clean", "changelog", "document_updates", "redeclare",
    "DEV_ENV", "SOURCE_DEV", "dev_dir", "dev_dir_setting", "set_dev_dir", "dev_code", "describe_dev",
]

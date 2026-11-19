"""Test isolation shared by the whole suite.

MICRO-U · the vocabularies installed on THIS machine (``EM_VOCABULARIES_DIR``,
:func:`s3dgraphy.authorities.packages.vocab_dir`) feed the resolver and the
labels: a suite run on a machine where somebody installed Getty AAT must not
answer differently from one where nobody did. Every test starts from an empty
folder of its own unless it sets one.

MICRO-PL03 · the same for the community packages (``S3DGRAPHY_PROFILES_DIR``,
:func:`s3dgraphy.profiles.profiles_dir`): an em.json that declares a package is
activated against an empty folder unless the test installs one.

MICRO-PL04 · and for the register of the extensions and the plugins' folder
(``S3DGRAPHY_EXTENSIONS_DIR``, ``S3DGRAPHY_PLUGINS_DIR``).

MICRO-PL18 · and no development folder of the plugins (``S3DGRAPHY_PLUGINS_DEV_DIR``)
unless the test names one.
"""
import pytest


@pytest.fixture(autouse=True)
def _empty_vocabulary_folder(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("EM_VOCABULARIES_DIR", str(tmp_path_factory.mktemp("vocabularies")))
    monkeypatch.setenv("S3DGRAPHY_PROFILES_DIR", str(tmp_path_factory.mktemp("profiles")))
    monkeypatch.setenv("S3DGRAPHY_EXTENSIONS_DIR", str(tmp_path_factory.mktemp("extensions")))
    monkeypatch.setenv("S3DGRAPHY_PLUGINS_DIR", str(tmp_path_factory.mktemp("plugins")))
    monkeypatch.delenv("S3DGRAPHY_PLUGINS_DEV_DIR", raising=False)
    try:
        from s3dgraphy.authorities import packages
        packages._changed()
    except Exception:  # pragma: no cover
        pass
    yield

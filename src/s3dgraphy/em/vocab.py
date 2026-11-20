"""Vocabularies, qualia and community packages — the same everywhere (SPEC-plugin §2.2).

``em.vocab`` reads the vocabulary MANAGER of this machine
(:mod:`s3dgraphy.vocabularies`, W20): a concept by its URI with its labels —
in the language asked, else through a VERIFIED alignment (the way
stratigraph-templates' renderer does), else none (a label is never invented);
a search that proposes candidates and never decides.

``em.profiles`` reads the packages: the ones the open document declares (the
host's overlay, ``header.profiles``), the ones installed on the machine, and
the merged views of the library (qualia, extractor types with their geometry,
landmark sets, combiners).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .errors import EmError
from .messages import both


class ConceptNotFound(EmError, KeyError):
    """No installed vocabulary knows the URI. A ``KeyError`` too."""

    def __init__(self, uri: str):
        super().__init__(both("no_concept", uri=uri), uri=uri)

    def __str__(self) -> str:
        return self.args[0]


class Concept:
    """A concept of an installed vocabulary, read.

    Attributes:
        uri: the concept's URI.
        vocabulary: the id of the vocabulary package it comes from.
        version: the vocabulary's version.
        attribution: the attribution the vocabulary asks for.
        license: the vocabulary's licence.
    """

    def __init__(self, uri: str, concept: Dict[str, Any], vocabulary: Dict[str, Any]):
        self.uri = uri
        self._c = concept
        self.vocabulary = vocabulary.get("id")
        self.version = vocabulary.get("version")
        self.attribution = vocabulary.get("attribution")
        self.license = vocabulary.get("license")

    @property
    def labels(self) -> Dict[str, str]:
        """The preferred labels, ``{language: label}``."""
        return dict(self._c.get("pref") or {})

    @property
    def broader(self) -> List[str]:
        """The URIs of the broader concepts."""
        return list(self._c.get("broader") or [])

    @property
    def narrower(self) -> List[str]:
        """The URIs of the narrower concepts."""
        return list(self._c.get("narrower") or [])

    def label(self, lang: str = "en", *, aligned: bool = True) -> Optional[str]:
        """The preferred label in ``lang`` (or its base language); else, with
        ``aligned``, the label of a concept verified as the same; else None."""
        from ..authorities.packages import label_in
        hit = label_in(self._c, lang)
        if hit:
            return hit[0]
        if aligned:
            from ..authorities.alignments import aligned_label
            al = aligned_label(self.uri, lang)
            if al:
                return al["text"]
        return None

    def term(self, lang: str = "en") -> Dict[str, Any]:
        """The double value a property carries (``data.concept``): what
        ``tx.set_property(..., concept=c)`` writes."""
        from ..terms import make_term
        return make_term(self.uri, self.label(lang) or "", lang, self.vocabulary, self.version)

    def __repr__(self) -> str:
        return f"<em concept {self.uri} ({self.vocabulary}@{self.version})>"


class Vocab:
    """``em.vocab`` — the vocabularies installed on this machine.

    A concept is read by its URI, with its labels; a search proposes
    candidates. A label is never invented: when no installed vocabulary has
    it, the answer is None.
    """

    def concept(self, uri: str, *, vocabulary: Optional[str] = None,
                version: Optional[str] = None) -> Concept:
        """The concept with this URI, from the installed vocabularies.

        Args:
            uri: the concept's URI.
            vocabulary: look in this vocabulary package first.
            version: with ``vocabulary``, that exact version first.

        Returns:
            Concept: the concept, with its labels.

        Raises:
            ConceptNotFound: no installed vocabulary knows the URI.

        Example:
            >>> em.vocab.concept("https://example.org/nothing")
            Traceback (most recent call last):
            ...
            s3dgraphy.em.vocab.ConceptNotFound: no installed vocabulary knows «https://example.org/nothing»
        """
        from ..authorities.packages import concept_of
        found = concept_of(str(uri), vocabulary, version)
        if found is None:
            raise ConceptNotFound(str(uri))
        summary, concept = found
        return Concept(str(uri), concept, summary)

    def find(self, uri: str, **kw: Any) -> Optional[Concept]:
        """Like :meth:`concept`, but None instead of raising.

        Args:
            uri: the concept's URI.
            **kw: ``vocabulary`` and ``version``, as in :meth:`concept`.

        Example:
            >>> em.vocab.find("https://example.org/nothing") is None
            True
        """
        try:
            return self.concept(uri, **kw)
        except ConceptNotFound:
            return None

    def search(self, text: str, *, lang: Optional[str] = None, serves: Optional[str] = None,
               limit: int = 30) -> List[Dict[str, Any]]:
        """Candidates — never an identity: a person confirms."""
        from ..authorities.packages import search
        return search(text, lang=lang, serves=serves, limit=limit)

    def installed(self) -> List[Dict[str, Any]]:
        """The vocabulary packages installed on this machine (one summary each).

        Example:
            >>> isinstance(em.vocab.installed(), list)
            True
        """
        from ..authorities.packages import vocab_installed
        return vocab_installed()

    def __repr__(self) -> str:
        return "<em.vocab: the vocabularies of this machine>"


class ExtractorType(dict):
    """An extractor type of the overlay; ``.geometry`` is its 3D component
    (primitive, vertices, measure, unit) with the SPEC's defaults."""

    def __init__(self, type_id: str, entry: Dict[str, Any], geometry: Optional[Dict[str, Any]]):
        super().__init__(entry)
        self.id = type_id
        self.geometry = geometry


class Profiles:
    """``em.profiles`` — the community packages (qualia, extractor types,
    landmark sets, combiners).

    Reads the packages the open document declares and this machine has (the
    host's overlay), and those installed on the machine.
    """

    def _overlay(self) -> Any:
        from . import host as _host
        return _host.current().overlay()

    def active(self) -> List[Dict[str, Any]]:
        """The packages the open document declares and this machine has:
        ``[{name, iri, prefix, version, origin}]``."""
        return [{"name": p.name, "iri": p.iri, "prefix": p.prefix, "version": p.version,
                 "origin": p.origin} for p in self._overlay()]

    def missing(self) -> List[Dict[str, Any]]:
        """Declared by the document, not installed here (the file opens all the same)."""
        from . import host as _host
        return list(getattr(getattr(_host.current(), "container", None), "profiles_missing", None) or [])

    def overlay(self) -> Any:
        """The merged view of the active packages (a :class:`~s3dgraphy.profiles.ProfileOverlay`)."""
        return self._overlay()

    def installed(self) -> List[Dict[str, Any]]:
        """The packages installed on this machine, active or not."""
        from .. import profiles as P
        return P.installed()

    def qualia_types(self) -> Dict[str, Dict[str, Any]]:
        """The qualia (property types) of the active packages, by id."""
        return self._overlay().qualia_types()

    def extractor_types(self) -> Dict[str, Dict[str, Any]]:
        """The extractor types of the active packages, by id."""
        return self._overlay().extractor_types()

    def combiner_types(self) -> Dict[str, Dict[str, Any]]:
        """The combiner types of the active packages, by id."""
        return self._overlay().combiner_types()

    def landmark_sets(self) -> Dict[str, Dict[str, Any]]:
        """The landmark sets (sets of canonical points) of the active packages, by id."""
        return self._overlay().landmark_sets()

    def extractor_type(self, type_id: str) -> ExtractorType:
        """One extractor type, with its geometry (``.geometry``).

        Args:
            type_id: the prefixed id (``stat:punto_canonico``).

        Raises:
            KeyError: no active package declares it.
        """
        ov = self._overlay()
        entry = ov.extractor_types().get(type_id)
        if entry is None:
            raise KeyError(both("no_profile", ref=type_id)["en"])
        return ExtractorType(type_id, entry, ov.extractor_geometry(type_id))

    def landmark_set(self, set_id: str) -> Dict[str, Any]:
        """One landmark set (its canonical points).

        Args:
            set_id: the prefixed id (``stat:volto``).

        Raises:
            KeyError: no active package declares it.
        """
        ls = self._overlay().landmark_set(set_id)
        if ls is None:
            raise KeyError(both("no_profile", ref=set_id)["en"])
        return ls

    def label(self, type_id: str, lang: str = "en") -> Optional[str]:
        """The label of a package type in ``lang``, or None.

        Args:
            type_id: any prefixed id of the active packages.
            lang: the language wanted.
        """
        return self._overlay().label(type_id, lang)

    def __repr__(self) -> str:
        return f"<em.profiles: {len(self.active())} active>"


__all__ = ["Vocab", "Concept", "ConceptNotFound", "Profiles", "ExtractorType"]

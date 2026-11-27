"""Public API for pyArchInit ``rapporti`` ↔ canonical s3dgraphy edges.

This module is the single home for the bidirectional mapping between
pyArchInit's stratigraphic ``rapporti`` packed string format and the
canonical edge types in the s3dgraphy property graph.

Architectural baseline (decided 2026-06-04 with the EM project lead):

* **In s3dgraphy in memory**, physical/topological stratigraphic
  relationships (``copre`` / ``coperto da`` / ``taglia`` / …) are
  **first-class edges** between US-type nodes — ``overlies`` /
  ``is_overlain_by`` / ``cuts`` / etc., the canonical edge types
  declared in ``s3Dgraphy_connections_datamodel.json`` and already
  recognised by the GraphML exporter, the unified XLSX importer and
  the JSON exporter. The property graph carries the single source of
  truth.

* **In pyArchInit's `us_table.rapporti` column**, the same
  relationships are serialised as a list-of-lists Python literal
  (e.g. ``[["Copre", "12", "1", "Pompei"], …]``). pyArchInit's
  vocabulary mixes Italian and English terms; the GraphML world has
  used both depending on the file's provenance, so we accept both
  on parse and emit canonical Italian on serialise.

* **In yEd GraphML (EM 1.6 palette onwards)**, the same
  relationships are serialised again, this time as a packed string
  attribute ``physical_relationships`` on each US node — because yEd
  edges are reserved for the temporal Matrix dimension and cannot
  visually carry physical relations without polluting the layout.
  The packed format is the **same pyArchInit-native list-of-lists**
  so the GraphML ↔ pyArchInit transit is byte-identical when the
  graph between them is unmutated.

This module exposes the constants the parsers / serialisers /
dispatchers consume. The parse/serialise *functions* land in a later
commit; today's commit is purely the constants extraction from
``graphml_writer.py`` and ``graph_ingestor.py`` so the canonical
vocabulary lives in one place.

The legacy private names (``_RAPPORTI_TO_EDGE_TYPE`` etc.) remain
importable from their original modules — see the re-export shims at
the bottom of ``graphml_writer.py`` and ``graph_ingestor.py``.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Forward: pyArchInit-native label → canonical s3dgraphy edge type
# ---------------------------------------------------------------------------
#: pyArchInit ``rapporti`` labels (Italian + English) mapped to canonical
#: s3dgraphy edge types declared in
#: ``s3Dgraphy_connections_datamodel.json``.
#:
#: Used by:
#:
#: * ``s3dgraphy.sync.graph_projector`` when reading the
#:   ``us_table.rapporti`` column out of a pyArchInit DB and turning
#:   each entry into a graph edge.
#: * ``s3dgraphy.sync.graphml_writer`` for the same translation step
#:   when an external pipeline feeds ``rapporti``-style strings into
#:   the writer's pre-export enrichment.
#:
#: pyArchInit's vocabulary is loose — older sites have Italian terms,
#: newer ones with English UIs have English. Both are accepted on
#: import. On serialise we emit the verbose Italian form (or shorthand
#: tokens for non-canonical unit types — see ``RAPPORTI_SHORTHAND``).
#:
#: The two symmetric bonds are written in their CANONICAL spelling,
#: ``bonded_to`` / ``equals``. The datamodel keeps ``is_bonded_to`` /
#: ``is_physically_equal_to`` as older spellings (``spelling_of``) — the same
#: relation, read and never written — and until 2026-09-27 this table wrote
#: them, so a pyArchInit graph and an xlsx graph carried the same bond under
#: two names. The serialise side accepts both (see :func:`_as_written`).
RAPPORTI_TO_EDGE_TYPE: dict[str, str] = {
    # Italian
    "copre": "overlies",
    "coperto da": "is_overlain_by",
    "taglia": "cuts",
    "tagliato da": "is_cut_by",
    "riempie": "fills",
    "riempito da": "is_filled_by",
    "uguale a": "equals",
    "si lega a": "bonded_to",
    "si appoggia a": "abuts",
    "gli si appoggia": "is_abutted_by",
    # English
    "covers": "overlies",
    "covered by": "is_overlain_by",
    "cuts": "cuts",
    "cut by": "is_cut_by",
    "fills": "fills",
    "filled by": "is_filled_by",
    "same as": "equals",
    "bonds with": "bonded_to",
    "abuts": "abuts",
    "supports": "is_abutted_by",   # English reciprocal of "Abuts"
}


# ---------------------------------------------------------------------------
# Full multilingual coverage
# ---------------------------------------------------------------------------
# pyArchInit (and any EM tool with a localized UI) stores relationship labels
# in the user's language, so parse_rapporti must recognise them all —
# otherwise a graph projected from a non-IT/EN site builds no edges, and a
# reciprocity round-trip (e.g. the reciprocal of "Abuts" is "Supports" =
# is_abutted_by) silently fails. The 10×10 table below mirrors the EM/
# pyArchInit stratigraphic-relationship vocabulary (10 relations × 10 UI
# languages: it/en/de/es/fr/ar/ca/ro/pt/el).
#
# Index → canonical edge type (same order as each language's term list):
_REL_INDEX_EDGE_TYPE: tuple[str, ...] = (
    "equals",                  # 0  Uguale a / Same as
    "bonded_to",               # 1  Si lega a / Connected to
    "overlies",                # 2  Copre / Covers
    "is_overlain_by",          # 3  Coperto da / Covered by
    "fills",                   # 4  Riempie / Fills
    "is_filled_by",            # 5  Riempito da / Filled by
    "cuts",                    # 6  Taglia / Cuts
    "is_cut_by",               # 7  Tagliato da / Cut by
    "abuts",                   # 8  Si appoggia a / Abuts
    "is_abutted_by",           # 9  Gli si appoggia / Supports
    # pyArchInit's «Genera continuità» writes this pair for the relation
    # that says a unit's life continues past the epoch it was born in.
    # Input aliases only: `is_before` is the reverse READING the datamodel
    # declares for `is_after`, exactly as `is_overlain_by` is for
    # `overlies`, so nothing localized reaches the graph and what people
    # are shown stays with the datamodel translations (#25).
    "is_after",                # 10 Continuità successiva a
    "is_before",               # 11 Continuità precedente a
)

#: 10 relationship terms per language (same indices as _REL_INDEX_EDGE_TYPE).
_REL_TERMS_BY_LANG: dict[str, tuple[str, ...]] = {
    "it": ("Uguale a", "Si lega a", "Copre", "Coperto da", "Riempie",
           "Riempito da", "Taglia", "Tagliato da", "Si appoggia a",
           "Gli si appoggia",
           "Continuità successiva a", "Continuità precedente a"),
    "en": ("Same as", "Connected to", "Covers", "Covered by", "Fills",
           "Filled by", "Cuts", "Cut by", "Abuts", "Supports",
           "Subsequent continuity of", "Prior continuity of"),
    "de": ("Entspricht", "Bindet an", "Liegt über", "Liegt unter",
           "Verfüllt", "Wird verfüllt durch", "Schneidet",
           "Wird geschnitten", "Stützt sich auf", "Wird gestützt von",
           "Nachfolgende Kontinuität von", "Vorherige Kontinuität von"),
    "es": ("Igual a", "Se liga a", "Cubre", "Cubierto por", "Rellena",
           "Rellenado por", "Corta", "Cortado por", "Se apoya en",
           "Le se apoya",
           "Continuidad posterior a", "Continuidad anterior a"),
    "fr": ("Égal à", "Se lie à", "Couvre", "Couvert par",
           "Remplit", "Rempli par", "Coupe", "Coupé par",
           "S’appuie sur", "Lui s’appuie",
           "Continuité postérieure à", "Continuité antérieure à"),
    "ar": ("مساوي ل", "يرتبط ب",
           "يغطي", "مغطى من",
           "يملأ", "ممتلئ من",
           "يقطع", "مقطوع من",
           "يستند إلى",
           "يستند عليه",
           "استمرارية لاحقة لـ",
           "استمرارية سابقة لـ"),
    "ca": ("Igual a", "Es lliga a", "Cobreix", "Cobert per", "Omple",
           "Omplert per", "Talla", "Tallat per", "S’recolza en",
           "Li es recolza",
           "Continuïtat posterior a", "Continuïtat anterior a"),
    "ro": ("Egal cu", "Se leagă de", "Acoperă", "Acoperit de",
           "Umple", "Umplut de", "Taie", "Tăiat de",
           "Se sprijină pe", "I se sprijină",
           "Continuitate ulterioară a", "Continuitate anterioară a"),
    "pt": ("Igual a", "Liga-se a", "Cobre", "Coberto por", "Preenche",
           "Preenchido por", "Corta", "Cortado por", "Apoia-se em",
           "Apoiado por",
           "Continuidade posterior a", "Continuidade anterior a"),
    "el": ("Ίσο με", "Συνδέεται με",
           "Καλύπτει",
           "Καλύπτεται από",
           "Γεμίζει",
           "Γεμίζεται από",
           "Τέμνει", "Τέμνεται από",
           "Εφάπτεται", "Υποστηρίζει",
           "Μεταγενέστερη συνέχεια του",
           "Προγενέστερη συνέχεια του"),
}

# Fold every language's terms into RAPPORTI_TO_EDGE_TYPE (keys lowercased to
# match parse_rapporti's lookup). setdefault keeps the explicit aliases above
# (e.g. "bonds with").
for _terms in _REL_TERMS_BY_LANG.values():
    for _i, _term in enumerate(_terms):
        RAPPORTI_TO_EDGE_TYPE.setdefault(_term.lower(), _REL_INDEX_EDGE_TYPE[_i])
del _terms, _i, _term


# ---------------------------------------------------------------------------
# Inverse: canonical edge type → verbose Italian rapporti label
# ---------------------------------------------------------------------------
#: Inverse of ``RAPPORTI_TO_EDGE_TYPE``: the verbose Italian voice (the
#: form pyArchInit's Scheda US shows) of every PHYSICAL relation.
#:
#: 1.6 · MICRO-LG7 (E.D., 22 Nov 2026) — a relation of TIME goes out as
#: time, a PHYSICAL one as physical, never the first as the second. Until
#: then this table had ``"is_after": "Copre"`` («default fallback for
#: temporal precedence»): «after» became «covers», and pyArchInit's
#: export read it back as ``overlies`` — a fact of time turned into a
#: fact of the ground. ``is_after`` / ``is_before`` now go out as ``>`` /
#: ``<`` for every pair of units (:func:`select_rapporti_label`), the
#: token pyArchInit's combobox already has and its own em.json import
#: writes since 17 Oct 2026. ``generic_connection`` («Connesso a», a voice
#: pyArchInit does not know and pyarchinit-mini read as a bond) is always
#: the paradata arrow ``>>`` / ``<<``.
EDGE_TYPE_TO_RAPPORTI_IT: dict[str, str] = {
    "overlies": "Copre",
    "is_overlain_by": "Coperto da",
    "cuts": "Taglia",
    "is_cut_by": "Tagliato da",
    "fills": "Riempie",
    "is_filled_by": "Riempito da",
    "equals": "Uguale a",
    "bonded_to": "Si lega a",
    "abuts": "Si appoggia a",
    "is_abutted_by": "Gli si appoggia",
}


#: Relations of TIME and their token (MICRO-LG7): ``>`` «later than», ``<``
#: «earlier than», whatever the two units are. The reverse reading
#: ``is_before`` is the same fact seen from the other end.
TEMPORAL_RAPPORTI_EDGE_TYPES: frozenset[str] = frozenset({"is_after", "is_before"})


#: The paradata chain: the double arrow ``>>`` / ``<<``, as pyArchInit
#: means it (its ``em_native_import.PARADATA_EDGES``), with the reverse
#: readings the datamodel declares. The serialiser still leaves out the
#: three this module has always left to their own columns
#: (``has_property``, ``extracted_from``, ``combines``, see
#: :data:`NON_RAPPORTI_EDGE_TYPES`); :func:`select_rapporti_label` gives
#: their token to whoever asks.
PARADATA_RAPPORTI_EDGE_TYPES: frozenset[str] = frozenset({
    "generic_connection",
    "has_property", "extracted_from", "combines",
    "has_data_provenance", "is_data_provenance_of",
    "has_documentation", "is_documentation_of",
    "is_part_of", "has_part",
})


# ---------------------------------------------------------------------------
# Shorthand tokens for relations between non-Harris unit types
# ---------------------------------------------------------------------------
#: Shorthand ``rapporti`` tokens for relations between non-US/USM units
#: (USVs / USVn / SF / CON / Combinar / Extractor / property / DOC).
#: Per pyArchInit author convention (May 2026):
#:
#: * single arrow ``>`` / ``<`` carries simple temporal precedence
#:   (first used for Continuity units, ``CON``; since MICRO-LG7 for every
#:   ``is_after`` / ``is_before``, whatever the units);
#: * double arrow ``>>`` / ``<<`` carries paradata-style data flow
#:   (Extractor / Combiner / property / DOC chains, expressed as
#:   ``generic_connection`` edges so the GraphML writer's paradata
#:   filter handles them correctly).
#:
#: Each value is ``(edge_type, swap)``:
#:
#: * ``swap=False`` means emit the edge with source / target as the
#:   user wrote them (``A > B`` → ``A is_after B``);
#: * ``swap=True`` means swap source / target (``A < B`` →
#:   ``B is_after A``).
#:
#: Mirrored in ``EDGE_TYPE_DIRECTION_FORWARD`` for the
#: serialise direction.
RAPPORTI_SHORTHAND: dict[str, tuple[str, bool]] = {
    ">":  ("is_after", False),            # A > B  ⇒  A is_after B
    "<":  ("is_after", True),             # A < B  ⇒  B is_after A
    ">>": ("generic_connection", False),  # A >> B ⇒  A → B
    "<<": ("generic_connection", True),   # A << B ⇒  B → A
}


# ---------------------------------------------------------------------------
# Edge-type direction for shorthand serialise
# ---------------------------------------------------------------------------
#: Per-edge-type direction. ``True`` means the rapporti token reads as
#: ``>`` / ``>>`` (source covers target); ``False`` means ``<`` / ``<<``
#: (source is covered by target).
#:
#: Used by the serialiser when the dispatch logic falls back to
#: shorthand for non-canonical unit-type endpoints.
EDGE_TYPE_DIRECTION_FORWARD: dict[str, bool] = {
    "overlies": True,
    "is_overlain_by": False,
    "cuts": True,
    "is_cut_by": False,
    "fills": True,
    "is_filled_by": False,
    "equals": True,                   # equality conventionally `>`
    "bonded_to": True,
    "abuts": True,
    "is_abutted_by": False,
    "is_after": True,
    "is_before": False,
    "generic_connection": True,
    "has_data_provenance": True,
    "is_data_provenance_of": False,
    "has_documentation": True,
    "is_documentation_of": False,
    "is_part_of": True,
    "has_part": False,
    "extracted_from": True,
    "combines": True,
    "has_property": True,
}


def _as_written(edge_type):
    """The name the datamodel WRITES for *edge_type*: an older spelling
    (``spelling_of`` — ``is_bonded_to`` → ``bonded_to``) comes back canonical,
    every other name (reverses included) unchanged.

    Asked of the connections datamodel, so this module keeps no alias table
    of its own. Lazy, because this module is imported by light-weight sync
    paths; if the datamodel cannot be read the name passes through."""
    try:
        from .edges.connections_loader import get_connections_datamodel
        entry = get_connections_datamodel().get_edge_definition(edge_type) or {}
    except Exception:                                  # noqa: BLE001
        return edge_type
    return entry.get("spelling_of") or edge_type


def _add_spellings(table: dict) -> None:
    """Also key *table* by every older spelling of its keys, derived from the
    datamodel, so a caller still indexing ``EDGE_TYPE_TO_RAPPORTI_IT
    ["is_bonded_to"]`` finds «Si lega a». Nothing is typed here."""
    try:
        from .edges.connections_loader import get_connections_datamodel
        datamodel = get_connections_datamodel()
    except Exception:                                  # noqa: BLE001
        return
    for name, value in list(table.items()):
        for spelling in datamodel.spellings(name):
            table.setdefault(spelling, value)


_add_spellings(EDGE_TYPE_TO_RAPPORTI_IT)
_add_spellings(EDGE_TYPE_DIRECTION_FORWARD)


# ---------------------------------------------------------------------------
# Unit-type frozensets driving the verbose-vs-shorthand dispatch
# ---------------------------------------------------------------------------
#: Localized US / USM ``unita_tipo`` code → canonical code. pyArchInit
#: localizes ONLY the US / USM abbreviations per UI language (its
#: ``pyarchinit_i18n_stratigraphic.UNIT_TYPE_ABBREV`` is the source of
#: truth). This module is the pyArchInit↔canonical bridge, and the
#: prefix-strip regex above already enumerates SU|SE|WSU|MSE|UE|…, so the
#: gating set lives here too. The mapping doubles as the normalization
#: source: any code path that needs the canonical form calls
#: :func:`canonical_unita_tipo`. ``attributes['unita_tipo']`` is kept
#: VERBATIM (original code) elsewhere so round-trip stays byte-identical;
#: only the verbose/shorthand dispatch and the projector's stratigraphic
#: gating read through this alias map.
#:
#:   US  → US (it/fr/ro) · SU (en/ar) · SE (de) · UE (es/ca/pt) · ΣΜ (el)
#:   USM → USM (it/fr) · WSU (en/ar) · MSE (de) · UEM (es/ca/pt) ·
#:         USZ (ro) · ΤΣΜ (el)
#:   USR → USR · USS (its English translation, *surface*; 1.6.13, E.D.).
#:         Not localized by pyArchInit: the two codes are the EM ones.
UNITA_TIPO_CANONICAL: dict[str, str] = {
    "US": "US", "SU": "US", "SE": "US", "UE": "US", "ΣΜ": "US",
    "USM": "USM", "WSU": "USM", "MSE": "USM", "UEM": "USM",
    "USZ": "USM", "ΤΣΜ": "USM",
    "USR": "USR", "USS": "USR",
}


def canonical_unita_tipo(unita_tipo) -> str:
    """Map a (possibly localized) US/USM code to its canonical form.

    Non-US/USM codes (USV*, SF, CON, DOC, …) and unknown values pass
    through unchanged.
    """
    return UNITA_TIPO_CANONICAL.get(unita_tipo, unita_tipo)


#: Unit types where both endpoints get the verbose dispatch ("Copre"/
#: "Covers"/…, "Coperto da"/"Covered by"/…). All language variants of the
#: Harris US/USM atoms, derived from the alias map so the two never drift.
CANONICAL_UNIT_TYPES: frozenset[str] = frozenset(UNITA_TIPO_CANONICAL)


#: Continuity unit type. Single-arrow shorthand ``>`` / ``<`` is
#: reserved for relations where at least one endpoint is a CON.
CONTINUITY_UNIT_TYPES: frozenset[str] = frozenset({"CON"})


# ---------------------------------------------------------------------------
# Python class name → pyArchInit unita_tipo column value
# ---------------------------------------------------------------------------
#: Recovery lookup for ``unita_tipo`` when a GraphML round-trip strips
#: the attribute metadata from a node. The only semantic info that
#: survives such a round-trip is the s3dgraphy Python class name; we
#: use it to recover the pyArchInit ``unita_tipo`` code so the
#: verbose-vs-shorthand dispatch in :func:`select_rapporti_label` and
#: the row-routing in :class:`GraphIngestor` keep working.
#:
#: Several entries are aliases of one another (``StructuralVirtualStratigraphicUnit``
#: vs ``VirtualStratigraphicStructuralUnit``) because historical
#: s3dgraphy classes have been renamed twice and old GraphML files
#: still carry the old names. Keep both spellings.
S3DGRAPHY_TYPE_TO_UNITA_TIPO: dict[str, str] = {
    "StratigraphicUnit": "US",
    "StructuralVirtualStratigraphicUnit": "USVs",
    "VirtualStratigraphicStructuralUnit": "USVs",
    "VirtualStratigraphicNonStructuralUnit": "USVn",
    "NonStructuralVirtualStratigraphicUnit": "USVn",
    "StratigraphicUnitMasonry": "USM",
    "DocumentaryStratigraphicUnit": "USD",
    "SpecialFindUnit": "SF",
    "VirtualSpecialFindUnit": "VSF",
    "TransformationStratigraphicUnit": "TSU",
    "WorkingUnit": "UL",
    "ContinuityNode": "CON",
    "DocumentNode": "DOC",
    "ExtractorNode": "Extractor",
    "CombinerNode": "Combinar",
    # yE-D (5.8.0-alpha): VirtualActivity used by SYNTHETIC folder
    # policy in yed_import_pipeline.py for folder-derived synthetic
    # us_table rows (unita_tipo='VA').
    "VirtualActivity": "VA",
    # s3dgraphy-bump (5.8.1-alpha): ReusedSpecialFind ("spolia"),
    # introduced in s3dgraphy 0.1.42 (DP-26). Family=real, non-series.
    # Routed to us_table by yE-D pipeline (unita_tipo='RSF').
    "ReusedSpecialFind": "RSF",
}


# ---------------------------------------------------------------------------
# Multilingual unita-tipo prefix strip
# ---------------------------------------------------------------------------
#
# Pyarchinit displays US labels with language-aware prefixes (US/SU/SE/UE/...,
# USM/WSU/MSE/..., USVs/USVn both rendered as "USV<n>", SF/VSF, CON,
# D./C. for paradata). For round-trip serialisation we strip ANY of
# these prefixes (longest match first) so the bare US identifier
# survives (e.g. "6", "102", "103a").

import re as _re

_US_PREFIX_PATTERN = _re.compile(
    r"^(?P<prefix>"
    r"USVs|USVn|USVA|USVB|USVC|USV|"
    # USNt before USN: the alternation is longest-match-first (see above), so the
    # NEUTRAL unit's token has to come first — otherwise a name like "USNt 12"
    # gets "USN" stripped and keeps a stray "t 12". USN itself is unchanged and is
    # pyArchInit's own code for the negativa, which is why it was already here.
    r"USNt|USM|USR|USS|USD|USN|"
    r"VSF|SF|"
    # the paradata rows of us_table, as the 1.6 name template writes them
    # (``1.Combinar900``, ``1.Extractor400``, ``1.DOC4001``,
    # ``1.property800``): measured 27 Nov 2026, the number came back as
    # «Combinar900». Only before a digit («Documento12» stays a name).
    r"(?:Combinar|Extractor|property|DOC)(?=\d)|"
    r"CON|"
    # every localized code of UNITA_TIPO_CANONICAL (27 Nov 2026, measured on
    # pyArchInit's demo: «1.UEM6» read as «M6», «1.USZ6» as «Z6», «1.ΣΜ2»
    # not read — the rapporti of the es / ca / pt / ro / el sites pointed
    # at numbers no row has). The longer code first.
    r"UEM|USZ|ΤΣΜ|ΣΜ|"
    r"WSU|MSE|TSU|SUS|UE|UM|UC|UL|"
    r"D\.|C\.|"
    r"US|SU|SE"
    r")\s*",
    _re.IGNORECASE,
)


def strip_us_prefix(name: str) -> str:
    """Read the ``us`` value out of a node name.

    The LAST RESORT, for a graph that arrives with labels and no
    ``attributes``. A graph built by the importer carries the columns in
    ``attributes`` and is never read this way (see
    ``graph_projector._propagate_node_uuid_and_us``).

    Since 1.6 ``node_name_template`` puts the area, and across sites a
    site code, in front of the unit type — ``1.US1``,
    ``TM16.1.USM100`` — so the segment after the last dot is taken
    first, and the unit-type prefix stripped from that. The dotted
    paradata codes (``D.``, ``C.``) are unaffected: their own dot is the
    last one, and what follows is already the bare value.

    Examples::

        strip_us_prefix("1.US1")         == "1"
        strip_us_prefix("TM16.1.USM100") == "100"
        strip_us_prefix("USM6")          == "6"
        strip_us_prefix("USV102")        == "102"
        strip_us_prefix("US103a")        == "103a"
        strip_us_prefix("D.4001")        == "4001"
        strip_us_prefix("C.900")         == "900"
        strip_us_prefix("6")             == "6"   # no prefix → unchanged
    """
    if not name:
        return name
    testo = str(name)
    # The unit type sits in the last dotted segment of a 1.6 label.
    coda = testo.rsplit(".", 1)[-1]
    m = _US_PREFIX_PATTERN.match(coda)
    if m:
        return coda[m.end():]
    # Not there: the whole name may be the prefix, dot included, which is
    # how the paradata codes are written (``D.4001`` → ``4001``).
    m = _US_PREFIX_PATTERN.match(testo)
    if m:
        return testo[m.end():]
    # No unit type anywhere: a bare value (``6``), or a name whose dot
    # belongs to the value itself (``12.3``). Keep what came in.
    return testo


# ---------------------------------------------------------------------------
# Units WITHOUT a number (node datamodel 1.6.55, MICRO-LG11)
# ---------------------------------------------------------------------------
_HAS_DIGIT = _re.compile(r"\d")


def is_declared_unnumbered(node) -> bool:
    """``True`` when the unit is DECLARED without a number: the node element
    ``data.unnumbered`` (node datamodel 1.6.55, MICRO-LG11, E.D. 23 Nov
    2026) — a unit recognised and recorded whose number nobody has assigned
    yet (the earth over the foundations of the Great Temple, until SU051).
    Read from ``node.data`` and, for a graph that came through the sync,
    ``node.attributes``."""
    if node is None:
        return False
    for bag in (getattr(node, "data", None), getattr(node, "attributes", None)):
        if isinstance(bag, dict) and bag.get("unnumbered") in (True, "true", "True", 1):
            return True
    return False


def us_number_of(node) -> str | None:
    """The ``us`` value a unit can take in pyArchInit's ``us_table``, or
    ``None`` when it has NO NUMBER.

    The ``us`` attribute when there is one (a graph built by the sync),
    otherwise :func:`strip_us_prefix` of the name. ``None`` when the unit
    is declared without a number (:func:`is_declared_unnumbered`) or when
    what is left of the name has no digit at all — «US non numerata — terra
    che ricopre le fondazioni» would become the «number» «non numerata —
    terra…». Never a number invented: the number is assigned by a person
    (E.D., rule of MICRO-LG11)."""
    if node is None or is_declared_unnumbered(node):
        return None
    attrs = getattr(node, "attributes", None) or {}
    us = attrs.get("us")
    if us is None or str(us).strip() == "":
        name = getattr(node, "name", None)
        if not name:
            return None
        us = strip_us_prefix(str(name))
    us = str(us).strip()
    return us if _HAS_DIGIT.search(us) else None


def is_unnumbered_unit(node) -> bool:
    """A STRATIGRAPHIC unit with no number (:func:`us_number_of` is
    ``None``), or any node declared so: the test of the WARNING
    (:func:`s3dgraphy.diagnostics.unnumbered_hints`). Only the declared
    ones (:func:`is_declared_unnumbered`) are kept out of pyArchInit; a
    name with no digit is said, not blocked (MICRO-LG13, E.D. 23 Nov 2026). The paradata nodes (a property
    «definition», an extractor) are not units and are never «unnumbered»
    here: their name is not a number to begin with. Nor is the continuity
    node (BR), whose name «continuity_node» is a convention of EM, not a
    number left out: it keeps the way it has always travelled."""
    if node is None:
        return False
    if is_declared_unnumbered(node):
        return True
    try:
        from .nodes.stratigraphic_node import ContinuityNode, StratigraphicNode
    except Exception:                                  # noqa: BLE001
        return False
    if not isinstance(node, StratigraphicNode) or isinstance(node, ContinuityNode):
        return False
    return us_number_of(node) is None


# ---------------------------------------------------------------------------
# Unita_tipo resolution helpers
# ---------------------------------------------------------------------------

def resolve_unita_tipo_for_dispatch(node) -> str | None:
    """Best-effort lookup of pyarchinit ``unita_tipo`` for *node*.

    Used by :func:`select_rapporti_label` to decide between verbose
    Italian (when both endpoints are canonical Harris units) and
    shorthand ``>`` / ``<`` / ``>>`` / ``<<`` (everything else).

    Lookup order:

    1. ``node.attributes['unita_tipo']`` (set by the AI03 enrichment
       in :mod:`graph_projector`);
    2. :data:`S3DGRAPHY_TYPE_TO_UNITA_TIPO` keyed by the node's Python
       class name (the fallback for graphs that survived a GraphML
       round-trip without preserving attributes).

    Returns ``None`` when neither source has a value — callers treat
    "unknown" as "fall through to shorthand" in the dispatcher.
    """
    if node is None:
        return None
    attrs = getattr(node, "attributes", None) or {}
    ut = attrs.get("unita_tipo")
    if ut:
        return str(ut)
    # 27 Nov 2026 · the class says it (with the code it came in with, a
    # localized SU / WSU): sync.unit_row.row_code
    from .unit_row import row_code
    code = row_code(node)
    if code:
        return code
    # 1.6.12 · a masonry US is a USM for pyArchInit (its us_table keeps the
    # recording practice as unita_tipo); 1.6.13 · a coating US a USR, or the
    # code it came in with (USS, WSU…)
    from .nodes.stratigraphic_node import unit_code
    code = unit_code(node)
    if code:
        return code
    cls_name = type(node).__name__
    return S3DGRAPHY_TYPE_TO_UNITA_TIPO.get(cls_name)


def select_rapporti_label(edge_type: str,
                          src_unita_tipo: str | None,
                          tgt_unita_tipo: str | None) -> str | None:
    """Pick the pyarchinit ``rapporti`` token for an edge, or ``None``.

    The rule (E.D., MICRO-LG7, 22 Nov 2026): a relation of time goes out as
    time, a physical one as physical; never the first as the second.

    * ``is_after`` / ``is_before`` → ``>`` / ``<``, **for every pair of
      units** (US, USM, USV, SF, USD, CON…). Until 1.6.0.dev138 an
      ``is_after`` between two US went out as «Copre» and came back as
      ``overlies``;
    * a PHYSICAL relation (overlies, cuts, fills, abuts, bonded_to,
      equals and their reverses) → its verbose voice
      (:data:`EDGE_TYPE_TO_RAPPORTI_IT`), **whatever the units** — between
      a USV and a US too (until then ``>>``, read back as a paradata link);
    * the paradata chain (:data:`PARADATA_RAPPORTI_EDGE_TYPES`) →
      ``>>`` / ``<<``;
    * anything else → ``None``: it is not a rapporto (``has_same_time``,
      which pyArchInit has no voice for; ``changed_from``;
      ``contrasts_with``; activities, authors…). Never the raw edge name,
      which pyArchInit discarded on the way back.

    The unit types are kept in the signature: they no longer change the
    token, but the callers (and pyArchInit's own copy) pass them.
    Direction (``>`` vs ``<``) is read from
    :data:`EDGE_TYPE_DIRECTION_FORWARD`.
    """
    edge_type = _as_written(edge_type)
    if edge_type in TEMPORAL_RAPPORTI_EDGE_TYPES:
        return ">" if EDGE_TYPE_DIRECTION_FORWARD.get(edge_type, True) else "<"
    if edge_type in EDGE_TYPE_TO_RAPPORTI_IT:
        return EDGE_TYPE_TO_RAPPORTI_IT[edge_type]
    if edge_type in PARADATA_RAPPORTI_EDGE_TYPES:
        return ">>" if EDGE_TYPE_DIRECTION_FORWARD.get(edge_type, True) else "<<"
    return None


def rapporti_edge_types() -> frozenset:
    """Every edge name that goes into the ``rapporti`` column — a WHITE
    list (MICRO-LG7): the physical relations that have a voice (every one
    the datamodel's :meth:`physical_relations` names, older spellings
    included), ``is_after`` / ``is_before``, the paradata chain. Everything
    else is left out and counted (:func:`serialize_rapporti_from_edges`,
    ``report=``)."""
    return ((frozenset(EDGE_TYPE_TO_RAPPORTI_IT)
             | TEMPORAL_RAPPORTI_EDGE_TYPES | PARADATA_RAPPORTI_EDGE_TYPES)
            - NON_RAPPORTI_EDGE_TYPES)


# ---------------------------------------------------------------------------
# Edge types that are NOT physical/stratigraphic rapporti
# ---------------------------------------------------------------------------
#: Edges with these types are intentionally **excluded** from the
#: pyarchinit ``rapporti`` column on serialise: they encode
#: epoch / paradata / property relationships that live in different
#: pyarchinit tables (or are paradata internal to s3dgraphy and have
#: no pyarchinit counterpart at all).
#:
#: Kept here (rather than as a magic constant inside ``serialize``)
#: so callers can introspect the exclusion list when debugging
#: missing rapporti.
#:
#: Since MICRO-LG7 the serialiser reads a WHITE list
#: (:func:`rapporti_edge_types`); this set stays as the names left out ON
#: PURPOSE (they have their own columns), for callers that import it —
#: pyArchInit's ``em_native_import`` among them. ``has_same_time`` is
#: here because pyArchInit has no voice for it yet: it is counted, never
#: dropped in silence.
#:
#: 1.6 · MICRO-LG11 (E.D., 23 Nov 2026) — it also names EVERY other edge of
#: the connections datamodel that has no voice in pyArchInit (those for which
#: :func:`select_rapporti_label` gives ``None``: ``changed_from`` /
#: ``changed_to``, ``contrasts_with``, ``is_in_activity``, ``has_author``…,
#: reverses and older spellings included), derived from the datamodel and
#: never typed here. pyArchInit's ``em_native_import.build_rapporti``
#: consults this set BEFORE asking :func:`select_rapporti_label`: until then
#: a ``changed_from`` between two US reached it and went into the column as
#: ``[None, '28', '1', sito]``. Now such an edge is skipped there and
#: counted here (``report=``), as the other exclusions of MICRO-LG7.
_NON_RAPPORTI_DECLARED: frozenset[str] = frozenset({
    "has_first_epoch",
    "has_paradata_nodegroup",
    "has_property",
    "extracted_from",
    "combines",
    "survive_in_epoch",
    "has_same_time",
})


def _without_voice() -> frozenset:
    """Every edge name of the connections datamodel (canonical, reverse,
    older spelling) for which :func:`select_rapporti_label` has no token.
    Empty if the datamodel cannot be read (the declared set still holds)."""
    try:
        from .edges.connections_loader import get_connections_datamodel
        names = get_connections_datamodel().get_all_edge_names()
    except Exception:                                  # noqa: BLE001
        return frozenset()
    return frozenset(n for n in names
                     if select_rapporti_label(n, None, None) is None)


NON_RAPPORTI_EDGE_TYPES: frozenset[str] = _NON_RAPPORTI_DECLARED | _without_voice()


# ---------------------------------------------------------------------------
# Public parse / serialize API
# ---------------------------------------------------------------------------

def parse_rapporti(value, skipped=None):
    """Parse a pyarchinit ``us_table.rapporti`` value into canonical
    relations ready to materialise as graph edges.

    *value* can be:

    * a ``str`` carrying the Python-literal serialisation pyarchinit
      writes to the column (``"[['Copre', '12', '1', 'Pompei'], ...]"``);
    * a ``list`` already parsed by the caller (``[['Copre', '12', '1',
      'Pompei'], ...]``);
    * ``None`` or empty — returns ``[]``.

    Returns a list of 5-tuples ``(edge_type, target_us, area, sito, swap)``:

    * ``edge_type`` — the canonical s3dgraphy edge type (e.g.
      ``overlies``, ``is_after``, ``generic_connection``);
    * ``target_us`` — the second element of the pyarchinit tuple (the
      target US identifier as a bare string, no prefix);
    * ``area``, ``sito`` — the third and fourth elements; ``None`` when
      the source row was a short 2-tuple ``["Copre", "12"]``;
    * ``swap`` — ``True`` when the shorthand token requested a
      source/target swap (``<`` and ``<<``). The caller materialises
      the edge as ``source_us is_after target_us`` after the swap.

    Labels not in :data:`RAPPORTI_TO_EDGE_TYPE` nor
    :data:`RAPPORTI_SHORTHAND` are skipped; pass a list as *skipped* and
    each one is appended to it (the raw label, MICRO-LG7) so the caller
    can say how many voices it could not read — ``<->``, «Connesso a»,
    pyarchinit-mini's «Posteriore a», raw edge names written by an older
    s3Dgraphy — instead of losing them in silence. Malformed list entries (not a
    list, or empty) are skipped likewise.

    The function is pure and side-effect-free; it does not mutate the
    input.
    """
    items = _coerce_to_list(value)
    out = []
    for entry in items:
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        raw_label = str(entry[0]) if entry[0] is not None else ""
        named = raw_label.strip().lower()
        edge_type = RAPPORTI_TO_EDGE_TYPE.get(named)
        swap = False
        if edge_type is None:
            shorthand = RAPPORTI_SHORTHAND.get(raw_label.strip())
            if shorthand is None:
                if skipped is not None:
                    skipped.append(raw_label)
                continue
            edge_type, swap = shorthand
        target_us = str(entry[1]).strip() if len(entry) > 1 and entry[1] is not None else ""
        area = str(entry[2]).strip() if len(entry) > 2 and entry[2] is not None else None
        sito = str(entry[3]).strip() if len(entry) > 3 and entry[3] is not None else None
        out.append((edge_type, target_us, area, sito, swap))
    return out


def _coerce_to_list(value):
    """Internal: turn the various forms of a pyarchinit ``rapporti``
    value into a flat list of entries.

    Accepted shapes:

    * ``None`` or empty string / list → ``[]``
    * ``list`` → returned as-is (assumed to be the parsed list-of-lists)
    * ``str`` → ``ast.literal_eval`` round-trip; non-list results are
      treated as empty (defensive); ``ValueError`` / ``SyntaxError``
      bubble up as ``[]`` rather than raising (the caller is usually
      a row-by-row importer and one malformed row shouldn't break the
      whole batch).
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if not isinstance(value, str):
        return []
    if not value.strip():
        return []
    import ast
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return []
    if isinstance(parsed, list):
        return parsed
    return []


#: Arrow tokens emitted by :func:`select_rapporti_label` for
#: non-canonical endpoints. When the dispatch returns one of these we do
#: NOT override it with a verbose row term (virtual units keep ``>>`` /
#: ``<<``, continuity keeps ``>`` / ``<``).
_SHORTHAND_TOKENS: frozenset[str] = frozenset({">", "<", ">>", "<<"})


def _source_rapporti_label(src_node, target_us: str, edge_type: str):
    """Original pyArchInit ``rapporti`` term on *src_node* for *target_us*.

    The d13 packed string is wire format that should byte-match the
    originating ``us_table.rapporti``, so for a verbose relation we anchor
    the label on the source row's own stored term (in the site's UI
    language — "Covers" / "Couvre" / "Copre" / …) rather than the canonical
    Italian. The label language can't be reconstructed from ``edge_type``
    alone (e.g. "US" is shared by it / fr / ro), so the node's own term is
    the only reliable source.

    Returned in the canonical display casing (first letter upper, rest
    lower — the form pyArchInit shows). Only an entry whose label maps to
    the SAME canonical ``edge_type`` is taken. Returns ``None`` when there
    is none (no ``rapporti`` attribute, e.g. a yEd-imported graph, or no
    entry of that relation) — the caller then keeps the canonical label.

    MICRO-LG7: until then ANY verbose entry towards the same target was
    taken when none matched. A row that already carried a spurious
    «Copre» (an old export of an ``is_after``) would have given it back to
    the very ``is_after`` the fix sends out as ``>`` — and a row with
    «Coperto da» towards that target would have reversed it.
    """
    attrs = getattr(src_node, "attributes", None) or {}
    for entry in _coerce_to_list(attrs.get("rapporti")):
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        lbl = str(entry[0]).strip()
        tgt = str(entry[1]).strip()
        if tgt != str(target_us) or not lbl or lbl in _SHORTHAND_TOKENS:
            continue
        lbl = lbl.capitalize()
        if RAPPORTI_TO_EDGE_TYPE.get(lbl.lower()) == _as_written(edge_type):
            return lbl
    return None


#: The reverse VOICE of a rapporti voice (27 Nov 2026): what the target row
#: says of the same relation. The arrows flip; a verbose voice becomes the
#: voice of the reverse reading (Copre → Coperto da); the symmetric ones
#: (Uguale a, Si lega a) stay.
_INVERSE_ARROW: dict[str, str] = {">": "<", "<": ">", ">>": "<<", "<<": ">>"}


def inverse_rapporti_label(label: str) -> str | None:
    """The voice the TARGET row of a rapporto writes for the same relation:
    ``>`` ↔ ``<``, ``>>`` ↔ ``<<``, «Copre» ↔ «Coperto da» (in the label's
    own language, any of the ten of :data:`_REL_TERMS_BY_LANG`), «Uguale a» →
    «Uguale a». ``None`` for a voice this module does not read."""
    text = str(label or "").strip()
    if text in _INVERSE_ARROW:
        return _INVERSE_ARROW[text]
    low = text.lower()
    for terms in _REL_TERMS_BY_LANG.values():
        for i, term in enumerate(terms):
            if term.lower() != low:
                continue
            et = _REL_INDEX_EDGE_TYPE[i]
            rev = _REVERSE_EDGE_TYPE.get(et, et)
            j = _REL_INDEX_EDGE_TYPE.index(rev)
            return terms[j]
    et = RAPPORTI_TO_EDGE_TYPE.get(low)
    if et is None:
        return None
    rev = _REVERSE_EDGE_TYPE.get(et, et)
    return EDGE_TYPE_TO_RAPPORTI_IT.get(rev)


#: canonical ↔ reverse reading of the relations that have a voice
_REVERSE_EDGE_TYPE: dict[str, str] = {
    "overlies": "is_overlain_by", "cuts": "is_cut_by", "fills": "is_filled_by",
    "abuts": "is_abutted_by", "is_after": "is_before",
}
_REVERSE_EDGE_TYPE.update({v: k for k, v in list(_REVERSE_EDGE_TYPE.items())})


def rapporti_language(entries) -> str | None:
    """The UI language of a row's ``rapporti`` (a list or its string), read
    from its verbose voices: the language of :data:`_REL_TERMS_BY_LANG` with
    the most voices in it (Italian on a tie with it), or ``None`` when the
    row has no verbose voice."""
    counts: dict[str, int] = {}
    for entry in _coerce_to_list(entries):
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        low = str(entry[0] or "").strip().lower()
        if not low or low in _INVERSE_ARROW:
            continue
        for lang, terms in _REL_TERMS_BY_LANG.items():
            if low in (t.lower() for t in terms):
                counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return None
    best = max(counts.values())
    if counts.get("it") == best:
        return "it"
    return next(lang for lang, n in counts.items() if n == best)


def voice_in_language(label: str, lang: str | None) -> str:
    """*label* (a verbose voice in any language) said in *lang*; an arrow, an
    unknown voice or an unknown language unchanged."""
    if not lang or lang not in _REL_TERMS_BY_LANG:
        return label
    text = str(label or "").strip()
    if text in _INVERSE_ARROW:
        return label
    et = RAPPORTI_TO_EDGE_TYPE.get(text.lower())
    if et is None or et not in _REL_INDEX_EDGE_TYPE:
        return label
    return _REL_TERMS_BY_LANG[lang][_REL_INDEX_EDGE_TYPE.index(et)]


def serialize_rapporti_from_edges(graph, default_sito: str, report=None,
                                  inverse: bool = False):
    """Walk *graph*'s edges and produce per-US rapporti lists ready
    for the pyarchinit ``us_table.rapporti`` column.

    Output: a ``dict`` mapping source node id to a list of
    ``[label, target_us, area, sito]`` entries — the pyarchinit
    list-of-lists serialisation, with verbose-Italian or shorthand
    labels picked by :func:`select_rapporti_label`.

    *default_sito* is the site name to stamp into the 4th element of
    every entry, regardless of what the graph might carry — this
    matches the "import to a NEW sito" workflow consumers run
    (``GraphIngestor.populate_list`` passes the user's chosen site).

    Behaviour notes:

    * Only the edges of :func:`rapporti_edge_types` go out (a white
      list, MICRO-LG7): physical relations with their voice, ``is_after``
      / ``is_before`` as ``>`` / ``<``, the paradata chain as ``>>`` /
      ``<<``. Every other edge is left out — and COUNTED: pass a dict as
      *report* and it receives ``excluded`` (``{edge_type: n}``) and
      ``exported`` (n), and ``unnumbered`` the names of the units without a
      number the edges pointed at (MICRO-LG11: such an edge is left out,
      counted as ``unnumbered_target``; since MICRO-LG13 only a unit
      DECLARED so, ``data.unnumbered`` — a name with no digit is a warning,
      not a block). Until then a black list let ``is_in_activity``,
      ``has_author``… out as ``>>`` towards the target's name, and
      ``is_before`` / ``changed_from`` as their raw names.
    * Target US is read from ``tgt_node.attributes['us']`` when
      present, otherwise derived from ``tgt_node.name`` via
      :func:`strip_us_prefix`.
    * Area defaults to ``"1"`` (compatible with most legacy
      pyarchinit data).
    * Duplicates within a source are dropped — external graphml may
      carry redundant edges for the same ``(label, target)`` and we
      keep the column clean.
    * ``inverse=True`` (27 Nov 2026, E.D.; the way back to us_table,
      :class:`GraphIngestor`): the graph keeps ONE edge per relation, and a
      pyArchInit sheet expects the relation on BOTH rows — so every rapporto
      also goes on the TARGET's list with the reverse voice
      (:func:`inverse_rapporti_label`: «Coperto da» for «Copre», ``<`` for
      ``>``, ``<<`` for ``>>``), towards the source's number and area. The
      voice is the canonical Italian one; the ingestor says it in the row's
      language. A relation already said on that row (an older graph with
      both readings as two edges) is not said twice. *report* receives
      ``inverse`` (n).
    """
    by_id = {}
    for n in graph.nodes:
        nid = getattr(n, "node_id", None)
        if nid:
            by_id[nid] = n
    # 27 Nov 2026 · the target's number and area are read from the graph (its
    # name, its place), not from its attributes; a document the importer
    # GENERATED from a row's columns is not a row and no rapporto points at it
    # (until then «>> Fotografie», «>> zioni» went into every unit's rapporti)
    from .unit_row import RowReader, is_generated_document
    reader = RowReader(graph)
    allowed = rapporti_edge_types()
    excluded: dict[str, int] = {}
    unnumbered: set[str] = set()
    exported = 0
    inverses = 0
    out: dict[str, list[list]] = {}
    said: dict[str, set] = {}

    def _relation(label, target):
        low = str(label).strip()
        if low in RAPPORTI_SHORTHAND:
            return (RAPPORTI_SHORTHAND[low], str(target))
        et = RAPPORTI_TO_EDGE_TYPE.get(low.lower())
        return ((_as_written(et) if et else low, False), str(target))

    def _put(node_id, rapporto):
        bucket = out.setdefault(node_id, [])
        rel = _relation(rapporto[0], rapporto[1])
        seen = said.setdefault(node_id, set())
        if rel in seen:
            return False
        seen.add(rel)
        bucket.append(rapporto)
        return True
    for e in getattr(graph, "edges", None) or []:
        src = getattr(e, "edge_source", None)
        tgt = getattr(e, "edge_target", None)
        et = getattr(e, "edge_type", None)
        if not src or not tgt or not et:
            continue
        if _as_written(et) not in allowed and et not in allowed:
            excluded[et] = excluded.get(et, 0) + 1
            continue
        src_node = by_id.get(src)
        tgt_node = by_id.get(tgt)
        if tgt_node is None:
            continue
        # MICRO-LG11 / LG13: towards a unit DECLARED without a number
        # (data.unnumbered) there is no row to point at. Left out and
        # counted. A name with no digit (X_TOPSOIL) is only a warning of
        # the coherence check (diagnostics.unnumbered_hints), never a block:
        # it travels with its name, as it always has (MICRO-LG13, E.D.).
        if is_declared_unnumbered(tgt_node):
            excluded["unnumbered_target"] = excluded.get("unnumbered_target", 0) + 1
            unnumbered.add(str(getattr(tgt_node, "name", "") or tgt))
            continue
        if is_generated_document(tgt_node) or reader.is_layer_document(tgt_node):
            excluded["generated_document"] = excluded.get("generated_document", 0) + 1
            continue
        src_unita_tipo = resolve_unita_tipo_for_dispatch(src_node)
        tgt_unita_tipo = resolve_unita_tipo_for_dispatch(tgt_node)
        tgt_attrs = getattr(tgt_node, "attributes", None) or {}
        tgt_us = tgt_attrs.get("us")
        if not tgt_us:
            tgt_name = getattr(tgt_node, "name", None)
            if not tgt_name:
                continue
            tgt_us = strip_us_prefix(str(tgt_name))
        rapporti_label = select_rapporti_label(
            et, src_unita_tipo, tgt_unita_tipo)
        if rapporti_label is None:
            excluded[et] = excluded.get(et, 0) + 1
            continue
        # For a verbose (physical) relation anchor the term on the source
        # row's own rapporti column, only an entry of the SAME relation, so
        # the packed string byte-matches the DB in the site's UI language;
        # the canonical label otherwise. The arrows (time ``>`` / ``<``,
        # paradata ``>>`` / ``<<``) are never re-anchored.
        if rapporti_label not in _SHORTHAND_TOKENS:
            original = _source_rapporti_label(src_node, str(tgt_us), et)
            if original:
                rapporti_label = original
        tgt_area = str(reader.places(tgt_node).get("area")
                       or tgt_attrs.get("area") or "1")
        tgt_sito = default_sito
        rapporto = [rapporti_label, str(tgt_us), tgt_area, tgt_sito]
        if _put(src, rapporto):
            exported += 1
        if not inverse or src_node is None or is_declared_unnumbered(src_node):
            continue
        rev_label = inverse_rapporti_label(rapporti_label)
        if rev_label is None:
            continue
        src_attrs = getattr(src_node, "attributes", None) or {}
        src_us = src_attrs.get("us") or strip_us_prefix(
            str(getattr(src_node, "name", "") or ""))
        if not src_us:
            continue
        src_area = str(reader.places(src_node).get("area")
                       or src_attrs.get("area") or "1")
        if _put(tgt, [rev_label, str(src_us), src_area, tgt_sito]):
            inverses += 1
    if report is not None:
        report["excluded"] = excluded
        report["exported"] = exported
        report["unnumbered"] = sorted(unnumbered)
        if inverse:
            report["inverse"] = inverses
    return out


__all__ = [
    # Vocabulary constants (commit 1)
    "RAPPORTI_TO_EDGE_TYPE",
    "EDGE_TYPE_TO_RAPPORTI_IT",
    "RAPPORTI_SHORTHAND",
    "EDGE_TYPE_DIRECTION_FORWARD",
    "UNITA_TIPO_CANONICAL",
    "canonical_unita_tipo",
    "CANONICAL_UNIT_TYPES",
    "CONTINUITY_UNIT_TYPES",
    "NON_RAPPORTI_EDGE_TYPES",
    "TEMPORAL_RAPPORTI_EDGE_TYPES",
    "PARADATA_RAPPORTI_EDGE_TYPES",
    "rapporti_edge_types",
    "is_declared_unnumbered",
    "us_number_of",
    "is_unnumbered_unit",
    # Type / prefix helpers (commit 2)
    "S3DGRAPHY_TYPE_TO_UNITA_TIPO",
    "strip_us_prefix",
    "resolve_unita_tipo_for_dispatch",
    "select_rapporti_label",
    # Parser / serialiser (commit 2)
    "parse_rapporti",
    "serialize_rapporti_from_edges",
    "inverse_rapporti_label",
    "rapporti_language",
    "voice_in_language",
]


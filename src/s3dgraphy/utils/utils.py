# s3Dgraphy/utils/utils.py
import os
import json
from importlib.resources import files

"""
Utilities for the s3Dgraphy library.

This module includes helper functions for node type conversion based on YED node shapes and border styles.
"""

from ..nodes.stratigraphic_node import (
    StratigraphicNode,
    StratigraphicUnit,
    NegativeStratigraphicUnit,
    NeutralStratigraphicUnit,
    SeriesOfStratigraphicUnit,
    SeriesOfNonStructuralVirtualStratigraphicUnit,
    SeriesOfStructuralVirtualStratigraphicUnit,
    SeriesOfDocumentaryStratigraphicUnit,
    NonStructuralVirtualStratigraphicUnit,
    StructuralVirtualStratigraphicUnit,
    SpecialFindUnit,
    VirtualSpecialFindUnit,
    ReusedSpecialFind,
    DocumentaryStratigraphicUnit,
    TransformationStratigraphicUnit,
    WorkingUnit,
    StratigraphicEventNode,
    ContinuityNode
)


def debug_graph_structure(graph, node_id=None, max_depth=5, current_depth=0):
    """
    Stampa informazioni dettagliate sulla struttura del grafo.
    Se node_id è specificato, si concentra sulle relazioni di quel nodo.
    
    Args:
        graph: Il grafo da analizzare
        node_id: ID del nodo su cui concentrarsi (opzionale)
        max_depth: Profondità massima di ricorsione
        current_depth: Profondità corrente di ricorsione
    """
    # Prevent infinite recursion
    if current_depth >= max_depth:
        # print(f"Limite di profondità ricorsiva ({max_depth}) raggiunto.")
        return
        
    
    
    if node_id:
        # print("\n=== DEBUG NODE STRUCTURE ===")
        node = graph.find_node_by_id(node_id)
        if node:
            # print(f"\nNode details {node_id} ({node.node_type}):")
            # print(f"  Nome: {node.name}")
            
            out_edges = [e for e in graph.edges if e.edge_source == node_id]
            in_edges = [e for e in graph.edges if e.edge_target == node_id]
            
            # print(f"  Outgoing Edges: {len(out_edges)}")
            for e in out_edges:
                target = graph.find_node_by_id(e.edge_target)
                target_type = target.node_type if target else "Unknown"
                # print(f"    -> {e.edge_target} ({target_type}) via {e.edge_type}")
            
            # print(f"  Ingoing Edges: {len(in_edges)}")
            for e in in_edges:
                source = graph.find_node_by_id(e.edge_source)
                source_type = source.node_type if source else "Unknown"
                # print(f"    <- {e.edge_source} ({source_type}) via {e.edge_type}")
            
    else:
        # print("\n=== DEBUG GRAPH STRUCTURE ===")
        node_types = {}
        for node in graph.nodes:
            if node.node_type not in node_types:
                node_types[node.node_type] = []
            node_types[node.node_type].append(node)
        
        # print(f"Total number of nodes: {len(graph.nodes)}")
        for ntype, nodes in node_types.items():
            pass
            # print(f"  - {ntype}: {len(nodes)} nodes")
        
        # print(f"\nTotal number of edges: {len(graph.edges)}")
        edge_types = {}
        for edge in graph.edges:
            if edge.edge_type not in edge_types:
                edge_types[edge.edge_type] = 0
            edge_types[edge.edge_type] += 1
        
        for etype, count in edge_types.items():
            pass
            # print(f"  - {etype}: {count} edges")
    # print("=== END DEBUG ===\n")

def convert_shape2type(yedtype, border_style, border_type="line"):
    """
    Converts YED node shape and border style to a specific stratigraphic node type.

    Args:
        yedtype (str): The shape type of the node in YED.
        border_style (str): The border color of the node.
        border_type (str): The border line type ('line', 'dashed', etc.).

    Returns:
        tuple: A tuple with a short code for the node type and an extended description.
    """
    if yedtype == "rectangle":
        nodetype = ("US", "Stratigraphic Unit")
    elif yedtype == "parallelogram":
        nodetype = ("USVs", "Structural Virtual Stratigraphic Units")
    elif yedtype == "ellipse" and border_style == "#D86400":
        nodetype = ("serUSD", "Series of USD")
    elif yedtype == "ellipse" and border_style == "#31792D":
        nodetype = ("serUSVn", "Series of USVn")
    elif yedtype == "ellipse" and border_style == "#248FE7":
        nodetype = ("serUSVs", "Series of USVs")
    elif yedtype == "ellipse" and border_style == "#9B3333":
        nodetype = ("serSU", "Series of SU")
    elif yedtype == "hexagon":
        nodetype = ("USVn", "Non-Structural Virtual Stratigraphic Units")
    elif yedtype == "octagon" and border_style == "#D8BD30":
        nodetype = ("SF", "Special Find")
    elif yedtype == "octagon" and border_style == "#B19F61":
        nodetype = ("VSF", "Virtual Special Find")
    elif yedtype == "octagon" and border_style == "#9B3333":
        # Reused Special Find (spolia). Same red border as serSU but
        # serSU is an ellipse, so the shape disambiguates the two.
        nodetype = ("RSF", "Reused Special Find")
    elif yedtype == "roundrectangle" and border_type == "dashed":
        nodetype = ("TSU", "Transformation Stratigraphic Unit")
    elif yedtype == "roundrectangle":
        nodetype = ("USD", "Documentary Stratigraphic Unit")
    elif yedtype == "diamond":
        nodetype = ("BR", "Continuity Node")
    else:
        # print(f"Unrecognized node type and style: yedtype='{yedtype}', border_style='{border_style}'")
        nodetype = ("unknown", "Unrecognized node")
        
    return nodetype


# ──────────────────────────────────────────────────────────────────
# Stratigraphic type → Python class map.
#
# Keep this list aligned with the ``stratigraphic_nodes`` entries in
# ``JSON_config/s3Dgraphy_node_datamodel.json`` — the JSON is the
# source of truth for metadata (label, abbreviation, family, …); this
# dict is only the Python-level runtime factory.
#
# The paired test ``test_stratigraphic_classification.py`` verifies
# the two stay in sync: every class here has a datamodel entry, every
# entry has a class, and family/is_series obey the expected rules.
# ──────────────────────────────────────────────────────────────────
STRATIGRAPHIC_CLASS_MAP = {
    "US":      StratigraphicUnit,
    # The two VOIDS, one token each (POL6): "USN" is the NEGATIVE unit — the
    # historical spelling here and in pyArchInit, and it reads as the Italian
    # "US Negativa" — while the NEUTRAL one (a risparmio: window, door, niche) is
    # "USNt". POL5 had them the other way round for a few hours; a token that
    # spells "negativa" cannot mean "neutra".
    "USN":     NegativeStratigraphicUnit,
    "USNt":    NeutralStratigraphicUnit,
    "USVs":    StructuralVirtualStratigraphicUnit,
    "USVn":    NonStructuralVirtualStratigraphicUnit,
    "SF":      SpecialFindUnit,
    "VSF":     VirtualSpecialFindUnit,
    "RSF":     ReusedSpecialFind,
    "USD":     DocumentaryStratigraphicUnit,
    "TSU":     TransformationStratigraphicUnit,
    "UL":      WorkingUnit,
    "serSU":   SeriesOfStratigraphicUnit,
    "serUSVn": SeriesOfNonStructuralVirtualStratigraphicUnit,
    "serUSVs": SeriesOfStructuralVirtualStratigraphicUnit,
    "serUSD":  SeriesOfDocumentaryStratigraphicUnit,
    "SE":      StratigraphicEventNode,
    "BR":      ContinuityNode,
}

def get_stratigraphic_node_class(stratigraphic_type):
    """
    Returns the stratigraphic node class corresponding to the specified type.

    Args:
        stratigraphic_type (str): The type of stratigraphic unit.

    Returns:
        class: The corresponding stratigraphic node class.
    """
    # Usa StratigraphicUnit come fallback se il tipo non è nella mappa
    #
    # 1.6.12 · USM (and pyArchInit's localized codes for it) is a US + masonry,
    # not a type: its class is the US one, and `apply_legacy_kind` sets the
    # kind on the instance. Before, it fell through to the base
    # StratigraphicNode, a node the datamodel renders untyped.
    if stratigraphic_type in MASONRY_TYPE_CODES:
        return StratigraphicUnit
    return STRATIGRAPHIC_CLASS_MAP.get(stratigraphic_type, StratigraphicNode)


#: A type string that names a MASONRY unit: USM and pyArchInit's localized
#: codes for it (sync/rapporti.UNITA_TIPO_CANONICAL — WSU en/ar, MSE de,
#: UEM es/ca/pt, USZ ro, ΤΣΜ el).
MASONRY_TYPE_CODES = frozenset({"USM", "WSU", "MSE", "UEM", "USZ", "ΤΣΜ"})


def apply_legacy_kind(node, stratigraphic_type):
    """After a node was built from a TYPE STRING (an xlsx column, a pyArchInit
    ``unita_tipo``): a masonry code makes the US a masonry US. Returns the node.
    A node that already states a kind, or is not a US, is left alone."""
    from ..nodes.stratigraphic_node import MASONRY, STRATIGRAPHIC_KIND

    if (stratigraphic_type in MASONRY_TYPE_CODES
            and getattr(node, "node_type", None) == "US"
            and not getattr(node, STRATIGRAPHIC_KIND, None)):
        setattr(node, STRATIGRAPHIC_KIND, MASONRY)
    return node

#: The key the datamodel uses for the material colour, plus the legacy one.
#:
#: S8 unified the file on **`rgba_color`**: it was already the majority (21 of
#: 34 entries) and now it is all of them. `color` stays in the list as pure
#: tolerance — for a graph or a hand-edited rules file written before the
#: rename — and is no longer produced by anything we ship.
#:
#: Order matters only if an entry ever carries both, which none does;
#: `test_material_key_precedence_is_pinned` fixes the winner anyway, so the day
#: one does the outcome is a decision and not whichever key the loop saw first.
_MATERIAL_COLOR_KEYS = ("rgba_color", "color")

# Storico, perché non si ricaschi nel dubbio: fino a S8 il file usava DUE nomi
# per la stessa cosa — `color` sui 13 tipi stratigrafici, `rgba_color` sugli
# altri. Leggere entrambe (S1) era una difesa contro un bug reale
# (get_material_color restituiva None per 21 tipi su 38); unificare (S8) è la
# cura. Il fallback qui sotto resta solo per non rompere un file vecchio.
#
# Da non confondere con la qualia `color` di em_qualia_types.json, che è il
# colore PERCEPITO Munsell/AAT di una superficie reale: un dato archeologico,
# non un parametro di rendering. Vedi `_note_material_vs_qualia_color` in
# em_visual_rules.json.


def _material_rgba(style):
    """(R, G, B, A) from a node style's material, or None.

    Reads BOTH spellings — see :data:`_MATERIAL_COLOR_KEYS`. A style with no
    `material` at all legitimately has no colour (the four group containers are
    drawn as boxes, not materials) and returns None; so does a `material` whose
    payload is not a mapping, rather than raising into the caller.
    """
    material = (style or {}).get("material")
    if not isinstance(material, dict):
        return None
    for key in _MATERIAL_COLOR_KEYS:
        color = material.get(key)
        if isinstance(color, dict) and {"r", "g", "b"} <= set(color):
            return (color["r"], color["g"], color["b"], color.get("a", 1.0))
    return None


def get_material_color(matname, rules_path=None):
    """
    Ottiene i valori RGB per un dato tipo di materiale dal file di configurazione.

    La chiave autoritativa è `material.rgba_color` (unificata in S8); `color`
    è letta solo come tolleranza verso file scritti prima della rinomina.

    Args:
        matname (str): Nome del materiale/tipo di unità stratigrafica
        rules_path (str, optional): Percorso al file JSON delle regole. Se None,
            usa il path di default.

    Returns:
        tuple: (R, G, B, A) con valori tra 0 e 1 o None se il nodo non prevede
        un materiale
    """
    try:
        if rules_path is None:
            rules_resource = files("s3dgraphy").joinpath(
                "JSON_config/em_visual_rules.json"
            )
            with rules_resource.open('r', encoding='utf-8') as f:
                rules = json.load(f)
        else:
            with open(rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)

        node_style = rules["node_styles"].get(matname, {})
        return _material_rgba(node_style.get("style", {}))

    except (KeyError, FileNotFoundError, json.JSONDecodeError, ModuleNotFoundError) as e:
        print(f"[s3dgraphy] get_material_color('{matname}') fallback: {type(e).__name__}: {e}")
        # Fallback solo per i nodi che dovrebbero avere un materiale
        if matname in ['US', 'USVs', 'USVn', 'VSF', 'SF', 'USD']:
            return (0.5, 0.5, 0.5, 1.0)
        return None


# Cache for the loaded visual rules file. Loaded lazily; reloadable
# for tests via ``_reload_visual_rules``.
_VISUAL_RULES_CACHE = None


def _load_visual_rules():
    global _VISUAL_RULES_CACHE
    if _VISUAL_RULES_CACHE is not None:
        return _VISUAL_RULES_CACHE
    try:
        rules_resource = files("s3dgraphy").joinpath(
            "JSON_config/em_visual_rules.json")
        with rules_resource.open('r', encoding='utf-8') as f:
            _VISUAL_RULES_CACHE = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError,
            ModuleNotFoundError) as e:
        print(f"[s3dgraphy] _load_visual_rules fallback: "
              f"{type(e).__name__}: {e}")
        _VISUAL_RULES_CACHE = {}
    return _VISUAL_RULES_CACHE


#: Keys of ``document_variant_styles`` that are STYLES, not values of the
#: ``geometry`` axis. Both describe a border rather than a degree of metric
#: authority, and neither is a legal ``geometry``:
#:
#:   * ``default``           — thin black: a use-instance, i.e. not canonical.
#:   * ``canonical_unknown`` — thick black: canonical, geometry NOT yet
#:     classified. "Not classified" is the absence of a value on the axis, so
#:     admitting it as one would let a document declare that it has not
#:     declared anything.
#:
#: ``canonical_unknown`` used to leak into ``DOCUMENT_GEOMETRIES`` because the
#: filter only excluded ``default`` (cleanup E). The importer's colour→variant
#: map already special-cased it, which is the tell.
_STYLE_ONLY_VARIANT_KEYS = ("default", "canonical_unknown")


def get_document_vocabularies():
    """Derive the three canonical Master-Document vocabularies from
    ``em_visual_rules.json``.

    Returns ``(DOCUMENT_ROLES, DOCUMENT_CONTENT_NATURES,
    DOCUMENT_GEOMETRIES)`` as tuples, reading from:

    - ``document_roles`` → keys (e.g. ``analytical``, ``comparative``)
    - ``document_content_natures`` → keys (e.g. ``2d_object``)
    - ``document_variant_styles`` → keys *excluding* ``_comment`` and the
      **style-only** entries (e.g. ``reality_based``, ``observable``,
      ``asserted``, ``symbolic``, ``em_based``)

    The JSON is the single source of truth for the Master-Document
    classification vocabulary; adding a new value there flows through
    to constructor validation and UI dropdowns automatically.
    """
    _role_order = ("analytical", "comparative")
    _nature_order = ("2d_object", "3d_object")
    # Metric-authority ladder, most to least (Q-C). `em_based` trails it: it is
    # a provenance statement, not a rung — the asset IS an EM-derived
    # reconstruction, which says nothing about how well it is placed.
    _geometry_order = ("reality_based", "observable", "asserted", "symbolic",
                       "em_based")
    rules = _load_visual_rules()

    def _keys(section_name, drop=()):
        section = rules.get(section_name, {}) or {}
        return {k for k in section
                if k and not k.startswith("_") and k not in drop}

    roles = _keys("document_roles", _STYLE_ONLY_VARIANT_KEYS)
    natures = _keys("document_content_natures", _STYLE_ONLY_VARIANT_KEYS)
    geoms = _keys("document_variant_styles", _STYLE_ONLY_VARIANT_KEYS)

    def _ordered(values, preferred):
        return tuple(v for v in preferred if v in values) + tuple(
            sorted(v for v in values if v not in preferred))

    roles_t = _ordered(roles, _role_order) or _role_order
    natures_t = _ordered(natures, _nature_order) or _nature_order
    geoms_t = _ordered(geoms, _geometry_order) or _geometry_order
    return roles_t, natures_t, geoms_t


def get_dtc_kinds():
    """DATA-DRIVEN, expandable per-kind vocabulary for the DTC profile (ECHOES).

    Reads the ``dtc_kinds`` block of ``em_visual_rules.json`` (the single source
    of truth, mirroring the Master-Document axis vocabularies) and returns a dict
    mapping each base kind → a tuple of its specific-kind keys::

        {"input": ("photo", "laserscanner", "topographic"),
         "process": ("transformation",),
         "output": ("pointcloud", "mesh", "dem", ...)}

    Keys starting with ``_`` (e.g. ``_comment``) are skipped. Adding a new kind
    in the JSON flows through to the DTC node classes' ``kind`` validation with
    no code change.

    An axis that declares ``_alias_of: {axis, family}`` has no entries of its
    own and answers the kinds of that family on that axis. It is how ``input``
    still answers since 1.6.22, when its captures became the ``capture`` family
    of ``acquisition``: a reader asking the old axis gets the kinds it always
    got, and no kind is listed twice.
    """
    rules = _load_visual_rules()
    section = rules.get("dtc_kinds", {}) or {}
    out = {}
    aliases = {}
    for base, kinds in section.items():
        if base.startswith("_") or not isinstance(kinds, dict):
            continue
        alias = kinds.get("_alias_of")
        if isinstance(alias, dict):
            aliases[base] = alias
            continue
        out[base] = tuple(k for k in kinds if not k.startswith("_"))
    for base, alias in aliases.items():
        target = section.get(alias.get("axis"), {}) or {}
        family = alias.get("family")
        out[base] = tuple(
            k for k, spec in target.items()
            if not k.startswith("_") and isinstance(spec, dict)
            and (family is None or spec.get("family") == family))
    return out


def get_dtc_kind_family(kind, axis="acquisition"):
    """The ``family`` a DTC kind declares on ``axis`` — ``"capture"`` or
    ``"retrieval"`` on the acquisition axis — or ``None`` when the kind is not
    on that axis or states none."""
    rules = _load_visual_rules()
    spec = ((rules.get("dtc_kinds", {}) or {}).get(axis) or {}).get(kind)
    return spec.get("family") if isinstance(spec, dict) else None


def get_document_variant_style(variant_key: str) -> dict:
    """Return the render-style dict for a DocumentNode variant key.

    In EM 1.6 ``variant_key`` is a ``geometry`` value
    (``"reality_based"``, ``"observable"``, ``"asserted"``) or
    ``"default"`` when the document has no RM — see
    :meth:`DocumentNode.variant_style_key`.

    The returned dict includes at least ``border_color``,
    ``border_style`` and ``border_width``; callers consume whichever
    they need to emit yEd XML. An unknown key falls back to
    ``"default"`` so an exporter is never left without a style.
    """
    rules = _load_visual_rules()
    variants = rules.get("document_variant_styles", {}) or {}
    style = variants.get(variant_key)
    if style is None:
        style = variants.get("default", {})
    return {
        "border_color": style.get("border_color", "#000000"),
        "border_style": style.get("border_style", "solid"),
        "border_width": float(style.get("border_width", 1.0)),
    }


def get_original_node_id(node):
    """
    Recupera l'ID originale di un nodo.
    
    Args:
        node: Il nodo da cui estrarre l'ID originale
        
    Returns:
        str: L'ID originale o l'ID corrente se non disponibile
    """
    return node.attributes.get('original_id', node.node_id)

def get_original_node_name(node):
    """
    Recupera il nome originale di un nodo (senza prefisso del grafo).
    
    Args:
        node: Il nodo da cui estrarre il nome originale
        
    Returns:
        str: Il nome originale o il nome corrente se non disponibile
    """
    return node.attributes.get('original_name', node.name)

def get_graph_code_from_node(node):
    """
    Estrae il codice del grafo da un nodo.
    
    Args:
        node: Il nodo da cui estrarre il codice
        
    Returns:
        str: Il codice del grafo o None se non disponibile
    """
    # Se il nome è prefissato (contiene _)
    if '_' in node.name:
        return node.name.split('_', 1)[0]
    
    # Altrimenti, cerca negli attributi
    return node.attributes.get('graph_code')

def manage_id_prefix(name: str, graph_code: str = None, action: str = 'add', separator: str = '.') -> str:
    """
    Add or remove graph code prefix from element names.
    
    This utility is useful for managing unique names when working with multiple graphs,
    especially when mapping to external systems with unique name constraints
    (e.g., 3D object names in Blender, database primary keys, file systems).
    
    The function handles edge cases gracefully:
    - Adding a prefix when one already exists (replaces old prefix)
    - Removing prefix when none exists (returns name unchanged)
    - Handling empty or None values
    
    Args:
        name (str): The name to modify
        graph_code (str, optional): The graph code to use as prefix. 
                                   If None and action='remove', removes any existing prefix.
                                   Defaults to None.
        action (str): Operation to perform: 'add' or 'remove'. Defaults to 'add'.
        separator (str): Character(s) between prefix and name. Defaults to '.'.
    
    Returns:
        str: The modified name
        
    Raises:
        ValueError: If action is not 'add' or 'remove'
        
    Examples:
        >>> manage_id_prefix('US001', 'VDL16', 'add')
        'VDL16.US001'
        
        >>> manage_id_prefix('VDL16.US001', 'VDL16', 'remove')
        'US001'
        
        >>> manage_id_prefix('GT15.US001', None, 'remove')
        'US001'
        
        >>> manage_id_prefix('GT15.US001', 'VDL16', 'add')
        'VDL16.US001'
        
        >>> manage_id_prefix('US001', None, 'add')
        'US001'
        
        >>> manage_id_prefix('', 'VDL16', 'add')
        ''
    """
    # Validate action parameter
    if action not in ['add', 'remove']:
        raise ValueError(f"Invalid action '{action}'. Must be 'add' or 'remove'.")
    
    # Handle empty or None names
    if not name or name.strip() == '':
        return name
    
    # Remove action
    if action == 'remove':
        # If the name contains the separator, split and return the part after first separator
        if separator in name:
            parts = name.split(separator, 1)  # Split only on first occurrence
            return parts[1] if len(parts) > 1 else name
        # No separator found, return name as-is
        return name
    
    # Add action
    if action == 'add':
        # If no graph_code provided, return name unchanged
        if not graph_code or graph_code.strip() == '':
            return name

        # Check if name already has this graph_code as prefix
        if name.startswith(f"{graph_code}{separator}"):
            # Already has the correct prefix, return as-is
            return name

        # Simply prepend the graph code — do NOT strip internal separators
        # from the name. Names like "D.07" contain separators that are part
        # of the identifier, not a graph prefix to replace.
        return f"{graph_code}{separator}{name}"
    
    # Should never reach here due to validation above
    return name


def get_base_name(name: str, separator: str = '.') -> str:
    """
    Convenience function to extract base name without prefix.
    
    This is a wrapper around manage_id_prefix with action='remove'.
    
    Args:
        name (str): The name potentially containing a prefix
        separator (str): Character(s) between prefix and name. Defaults to '.'.
    
    Returns:
        str: The base name without prefix
        
    Examples:
        >>> get_base_name('VDL16.US001')
        'US001'
        
        >>> get_base_name('US001')
        'US001'
    """
    return manage_id_prefix(name, None, 'remove', separator)


def add_graph_prefix(name: str, graph_code: str, separator: str = '.') -> str:
    """
    Convenience function to add graph code prefix to a name.
    
    This is a wrapper around manage_id_prefix with action='add'.
    
    Args:
        name (str): The name to add prefix to
        graph_code (str): The graph code to use as prefix
        separator (str): Character(s) between prefix and name. Defaults to '.'.
    
    Returns:
        str: The name with prefix added
        
    Examples:
        >>> add_graph_prefix('US001', 'VDL16')
        'VDL16.US001'
    """
    return manage_id_prefix(name, graph_code, 'add', separator)


def _process_section(text: str, section_id: str, include: bool) -> str:
    """Include or remove a <!-- SECTION: X -->...<!-- /SECTION: X --> block."""
    import re
    open_tag  = f'<!-- SECTION: {section_id} -->'
    close_tag = f'<!-- /SECTION: {section_id} -->'
    if include:
        return text.replace(open_tag, '').replace(close_tag, '')
    pattern = re.escape(open_tag) + r'.*?' + re.escape(close_tag)
    return re.sub(pattern, '', text, flags=re.DOTALL)


def _process_flag(text: str, flag_id: str, include: bool) -> str:
    """Include or remove a <!-- FLAG: X -->...<!-- /FLAG: X --> block."""
    import re
    open_tag  = f'<!-- FLAG: {flag_id} -->'
    close_tag = f'<!-- /FLAG: {flag_id} -->'
    if include:
        return text.replace(open_tag, '').replace(close_tag, '')
    pattern = re.escape(open_tag) + r'.*?' + re.escape(close_tag)
    return re.sub(pattern, '', text, flags=re.DOTALL)


def _strip_html_comments(text: str) -> str:
    """Remove all remaining HTML comments from text."""
    import re
    return re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)


def get_ai_prompt(
    language: str = None,
    include_validation: bool = True,
    include_checklist: bool = True,
    include_stratigraphy_only: bool = False,
    documents_folder: str = None,
    document_list: list = None,
    dosco_in_place: bool = True,
    ai_has_filesystem_access: bool = True,
) -> str:
    """
    Build and return the StratiMiner extraction prompt (v5.1 schema).

    Reads ``StratiMiner_Extraction_Prompt.md`` bundled inside the s3dgraphy
    package and produces a ready-to-paste prompt that instructs an AI
    assistant (Claude, ChatGPT, Gemini, ...) to output a single
    ``em_data.xlsx`` file with the 5 typed sheets (Units, Epochs, Claims,
    Authors, Documents).

    The prompt is now fully written in English: meta-instructions are
    universal, while the AI's textual output (VALUE, EXTRACTOR excerpts,
    COMBINER_REASONING) is controlled by the ``language`` argument,
    substituted at the ``[OUTPUT_LANGUAGE]`` placeholder inside the
    prompt.

    Args:
        language: Output language for the values the AI writes into the
            xlsx (VALUE, EXTRACTOR, COMBINER_REASONING, DISPLAY_NAME).
            ``None`` / empty / "the same as the original document" →
            the AI is instructed to preserve each document's original
            language on a per-claim basis.
        include_validation: Include the embedded Python validation script.
            Default True.
        include_checklist: Include the end-of-session checklist. Default True.
        include_stratigraphy_only: Include the STRATIGRAPHY_ONLY appendix
            that describes the minimal flow for pre-existing archaeological
            databases (curator as sole author, no paradata chain). Default
            False.
        documents_folder: Optional path to a folder of source PDFs; when
            provided, appended to the SOURCES PROVIDED section so the AI
            knows where to look.
        document_list: Optional pre-catalogued document descriptors (each
            either a string or a dict with ``id`` / ``title`` / ``path``).
        dosco_in_place: When True (default) the AI renames files in place
            inside ``documents_folder`` with the ``D.NN_`` prefix and
            uses the folder as the DosCo. When False the AI must treat
            the folder as read-only and produce the document catalog
            without actually renaming — the user will copy+rename offline.
        ai_has_filesystem_access: When True (default) the AI is instructed
            to enumerate and read files from ``documents_folder``. When
            False, the AI is told it won't have filesystem access and
            should ask the user to upload the files into the conversation
            directly, with a data-sovereignty disclaimer.

    Returns:
        str: The assembled prompt ready to paste into an AI assistant.

    Raises:
        FileNotFoundError: If the bundled prompt file cannot be located.
    """
    prompt_resource = files("s3dgraphy").joinpath(
        'data/StratiMiner_Extraction_Prompt.md'
    )

    try:
        with prompt_resource.open('r', encoding='utf-8') as f:
            source_md = f.read()
    except (FileNotFoundError, ModuleNotFoundError) as e:
        raise FileNotFoundError(
            f"StratiMiner extraction prompt not found in s3dgraphy package "
            f"(data/StratiMiner_Extraction_Prompt.md): {e}. "
            "Ensure s3dgraphy is installed correctly."
        )

    # Resolve output language
    _default = "the same as the original document"
    lang = language.strip() if language else ""
    lang_str = lang if (lang and lang.lower() != _default.lower()) else _default

    # 1. Output-language placeholder
    result = source_md.replace('[OUTPUT_LANGUAGE]', lang_str)

    # 2. Sources block placeholder (replace regardless, even with empty)
    sources_text = _build_sources_block(
        documents_folder=documents_folder,
        document_list=document_list,
        dosco_in_place=dosco_in_place,
        ai_has_filesystem_access=ai_has_filesystem_access,
    )
    result = result.replace('[SOURCES_BLOCK]', sources_text)

    # 3. Optional sections
    for section_id, include in [
        ('VALIDATION',        include_validation),
        ('STRATIGRAPHY_ONLY', include_stratigraphy_only),
        ('CHECKLIST',         include_checklist),
    ]:
        result = _process_section(result, section_id, include)

    # 4. Strip any remaining HTML comment markers
    result = _strip_html_comments(result)

    return result.strip()


def _build_sources_block(documents_folder: str,
                          document_list: list,
                          dosco_in_place: bool,
                          ai_has_filesystem_access: bool) -> str:
    """Format the SOURCES PROVIDED body inserted at ``[SOURCES_BLOCK]``.

    Covers three degrees of information:

    * ``documents_folder`` alone: instruct the AI to enumerate the
      folder, respect existing ``D.NN_`` prefixes, fill gaps, and use
      1000+ for comparative sources.
    * ``document_list``: pre-catalogued entries take precedence over
      folder enumeration (the AI re-uses the declared IDs verbatim).
    * ``ai_has_filesystem_access = False``: replace the enumeration
      instructions with a request to upload files into the conversation
      and a data-sovereignty disclaimer.

    Returns a string ready to be dropped into the SOURCES PROVIDED
    section; it is always non-empty — if nothing is supplied, it
    contains a single line telling the AI that no documents have been
    attached yet.
    """
    lines = []

    if not documents_folder and not document_list:
        lines.append(
            "_No source documents have been attached to this prompt._ "
            "The user must either paste a documents-folder path into the "
            "prompt before sending it, or upload the files directly "
            "into this conversation."
        )
        return "\n".join(lines)

    if document_list:
        lines.append("### Pre-catalogued documents")
        lines.append("")
        lines.append(
            "Use these IDs verbatim; do not re-number. Additional "
            "documents discovered in the folder extend this list "
            "using the numbering rules below."
        )
        lines.append("")
        for item in document_list:
            if isinstance(item, dict):
                parts = []
                for key in ("id", "title", "path"):
                    val = item.get(key)
                    if val:
                        parts.append(f"{key}={val}")
                lines.append("- " + " | ".join(parts))
            else:
                lines.append(f"- {item}")
        lines.append("")

    if documents_folder and ai_has_filesystem_access:
        lines.append("### Source folder")
        lines.append("")
        lines.append("The source documents are in the folder:")
        lines.append("")
        lines.append(f"    {documents_folder}")
        lines.append("")
        if dosco_in_place:
            lines.append(
                "This folder is the **DosCo** (Document Corpus) for the "
                "project. Treat it in-place:"
            )
        else:
            lines.append(
                "This folder holds the raw source files. Do **not** "
                "rename or copy them — the user will perform a separate "
                "copy/rename pass after your output. Just enumerate."
            )
        lines.append("")
        lines.append("**Document numbering rules:**")
        lines.append("")
        lines.append(
            "1. If a filename already starts with `D.NN_` (e.g. "
            "`D.02_Diaconescu.pdf`), **re-use that number** as the "
            "`Documents.ID`. Do not re-number."
        )
        lines.append(
            "2. Otherwise, assign the next available integer in the "
            "`D.NN` sequence, **filling gaps**: if `D.01`, `D.02`, "
            "`D.04` exist, assign `D.03` to the next new document "
            "before going to `D.05`."
        )
        lines.append(
            "3. **Comparative / parallel sources** (documents about "
            "other sites, theoretical treatises, typological "
            "references — not about the site itself) use IDs from "
            "`D.1000` upward to keep them visibly separate from the "
            "analytical sources of the site."
        )
        if dosco_in_place:
            lines.append(
                "4. When you report each document in the `Documents` "
                "sheet, include a note in `TITLE` if you propose a "
                "rename (e.g. `TITLE = \"Diaconescu 2013 Templu Mare \""
                "— proposed rename D.03_Diaconescu_2013.pdf`). The "
                "user will apply the in-place rename after reviewing."
            )
        lines.append("")
    elif documents_folder and not ai_has_filesystem_access:
        lines.append("### Source documents")
        lines.append("")
        lines.append(
            f"The user has a documents folder at `{documents_folder}` "
            "but you do **not** have filesystem access in this "
            "conversation. Ask the user to upload the files directly "
            "into the chat."
        )
        lines.append("")
        lines.append("**Data-sovereignty notice to return to the user:**")
        lines.append("")
        lines.append(
            "> Before uploading archaeological PDFs into this "
            "conversation, verify that you have the rights to share "
            "them and that this AI provider is compliant with your "
            "organization's data-handling policies. Document content "
            "is processed by the AI vendor, not by StratiMiner."
        )
        lines.append("")
        lines.append(
            "Once the files are uploaded, apply the numbering rules "
            "below (same as for a filesystem folder):"
        )
        lines.append("")
        lines.append(
            "1. If a filename already starts with `D.NN_`, re-use that "
            "number."
        )
        lines.append(
            "2. Otherwise, next available integer, filling gaps."
        )
        lines.append(
            "3. Comparative sources from `D.1000` upward."
        )
        lines.append("")

    return "\n".join(lines)

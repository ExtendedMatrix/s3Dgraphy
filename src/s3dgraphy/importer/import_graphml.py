# s3Dgraphy/import_graphml.py

import xml.etree.ElementTree as ET
from ..graph import Graph
from ..nodes.stratigraphic_node import (
    Node, StratigraphicNode, StratigraphicUnit, DocumentaryStratigraphicUnit,
    VirtualSpecialFindUnit, ContinuityNode)
from ..nodes.paradata_node import ParadataNode
from ..nodes.document_node import DocumentNode
from ..nodes.combiner_node import CombinerNode
from ..nodes.extractor_node import ExtractorNode
from ..nodes.property_node import PropertyNode
from ..nodes.epoch_node import EpochNode
from ..nodes.group_node import GroupNode, ParadataNodeGroup, ActivityNodeGroup, TimeBranchNodeGroup
from ..nodes.resource_node import *
from ..nodes.author_node import AuthorNode, AuthorAINode
from ..nodes.license_node import LicenseNode
from ..nodes.embargo_node import EmbargoNode
from ..edges.edge import Edge, EDGE_TYPES
from ..edges import get_connections_datamodel
from ..utils.utils import convert_shape2type, get_stratigraphic_node_class
from ..nodes.stratigraphic_node import kind_of_name, set_kind
import re
import uuid
import os
import json

# Yworks XML namespace (used when scanning y:ImageNode elements)
_Y_NS = '{http://www.yworks.com/xml/graphml}'

# IMPKEYS · header-key aliases → canonical keys (single normalisation point).
# The graphml header vocabulary (e.g. "Site [ID:GT16; LICENCE:CC-BY; ...]") is
# authored by humans with US/UK spellings and casing; real files use e.g. UK
# `LICENCE` and uppercase `EMBARGO` (Aiano). We map recognised VARIANTS to the
# canonical keys the importer/materialiser read (MIG1-A/IMP1). Matching is
# case-insensitive; keys are inspected from the real files (Aiano, Templu Mare)
# plus common UK/US variants — not invented. Unknown keys pass through verbatim
# (no loss); absent keys stay absent (no fabricated values).
_HEADER_KEY_ALIASES = {
    "id": "ID", "em_id": "ID", "emid": "ID",
    "orcid": "ORCID",
    "author_name": "author_name", "author": "author_name", "authorname": "author_name",
    "author_surname": "author_surname", "surname": "author_surname",
    "license": "license", "licence": "license",
    "embargo": "embargo",
    "description": "description",
    "graph_id": "graph_id",
}


def _normalize_header_vocab(vocab):
    """Return ``vocab`` with recognised variant keys renamed to canonical keys
    (case-insensitive). An explicit canonical key already present is never
    clobbered by a variant; unknown keys are kept verbatim."""
    out = {}
    # canonical keys first, so a variant can't overwrite an explicit canonical
    for k, v in vocab.items():
        canon = _HEADER_KEY_ALIASES.get(str(k).strip().lower())
        if canon is not None and canon == k:
            out[canon] = v
    for k, v in vocab.items():
        canon = _HEADER_KEY_ALIASES.get(str(k).strip().lower())
        if canon is None:
            out.setdefault(k, v)
        elif canon != k:
            out.setdefault(canon, v)
    return out

# --- Deterministic ids for elements without an EMID (E2) --------------------
# A GraphML element that carries an ``EMID`` keeps it: that is the authored
# identity and nothing here touches it. Everything else used to get a fresh
# ``uuid4()`` on every import, so the SAME file produced DIFFERENT ids run
# after run — the re-import was not reproducible and any `positions` entry or
# external reference minted against a previous run went orphan.
#
# Instead we mint a **uuid5** over a key built from the file's own content, so
# the same GraphML always yields the same ids:
#
#     node / group / swimlane   kind | name | x | y
#     epoch row                 kind | swimlane id | row original id | index
#     edge                      kind | original edge id | source | target
#
# The (x, y) geometry is what disambiguates homonyms — two boxes both labelled
# ``USV138_PD`` are different nodes precisely because they sit in different
# places (the case that forced a manual re-pairing in F2). When even that is
# not enough (same kind, same name, same point), the duplicates are numbered
# by their order of appearance in the document, which is itself deterministic
# for a given file. Collisions are therefore resolved, never left to chance.
#
# Frozen namespace — uuid5(NAMESPACE_DNS,
# 's3dgraphy.graphml.deterministic-id.extendedmatrix.org'). NEVER change this
# value: it would re-mint every id in every graph imported so far.
DETERMINISTIC_ID_NAMESPACE = uuid.UUID("c6735a81-b2e2-5fbc-b972-a8a3f71d7a84")

# --- Paradata image node prefix registry (DP-51) ----------------------------
# Hash-based detection was dropped: palette PNGs may be redrawn or
# re-exported between versions. Label prefixes are instead the stable
# convention across the EM ecosystem (matches how ExtractorNode ``D.`` and
# CombinerNode ``C.`` are already identified).

def _load_palette_prefix_config():
    """Return the label_prefix → node_type map from em_palette_icons.json.

    Returns an empty dict if the config is missing or unreadable, in which
    case paradata image detection falls back to the explicit description
    marker only.
    """
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "JSON_config",
        "em_palette_icons.json",
    )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("label_prefixes", {})
    except (OSError, json.JSONDecodeError):
        return {}


_PALETTE_LABEL_PREFIXES = _load_palette_prefix_config()

# Inline description/URL marker used for explicit round-trip identification.
# Written by the s3Dgraphy GraphML exporter when it emits paradata image
# nodes; takes precedence over label-prefix detection on the import side.
_S3D_NODE_TYPE_MARKER = "_s3d_node_type:"

# --- Lossless physical-stratigraphic relations side-channel ----------------
# Companion to the write side in
# ``exporter/graphml/graphml_exporter.PHYSICAL_STRATIGRAPHIC_TYPES``. The
# exporter applies a transitive reduction (Harris convention) and emits only
# the minimal ``is_after`` / ``has_same_time`` edges in the GraphML body; the
# *original* physical relations (overlies, cuts, fills, abuts, is_before,
# bonded_to, equals, …) and their author / document attributes are
# preserved in a graph-level GraphML key called
# ``_s3d_physical_relations`` (a JSON-encoded list). On import we read that
# key and use it as the authoritative edge set. Legacy GraphML files
# without the key fall back to the current behaviour unchanged.
PHYSICAL_STRATIGRAPHIC_TYPES = (
    "overlies", "is_overlain_by",
    "cuts", "is_cut_by",
    "fills", "is_filled_by",
    "abuts", "is_abutted_by",
    "is_before", "is_after",
    "changed_from", "changed_to",
    "is_bonded_to", "bonded_to",
    "is_physically_equal_to", "equals",
    "has_same_time",
)

_S3D_PHYSICAL_RELATIONS_ATTR_NAME = "_s3d_physical_relations"

# Companion graph-level key carrying structured PropertyNode metadata
# (value / property_type / units / arbitrary attributes). Written by
# the GraphML exporter's ``_write_property_metadata_data``; required
# because the yEd PropertyNode encoding collapses ``value`` +
# ``attributes['units']`` into the description field and drops
# ``property_type`` entirely. Without this side channel, structured
# qualia get re-imported as opaque label strings.
_S3D_PROPERTY_METADATA_ATTR_NAME = "_s3d_property_metadata"

class GraphMLImporter:
    """
    Classe per importare grafi da file GraphML.

    Attributes:
        filepath (str): Percorso del file GraphML da importare.
        graph (Graph): Istanza della classe Graph in cui verrà caricato il grafo.
    """

    def __init__(self, filepath, graph=None):
        self.filepath = filepath
        self.graph = graph if graph is not None else Graph(graph_id="imported_graph")
        # Dizionario per la deduplicazione dei nodi documento
        self.document_nodes_map = {}  # nome documento -> node_id
        self.duplicate_id_map = {}    # id originale -> id deduplicated
        self.id_mapping = {}          # id originale -> uuid
        # Get connections datamodel for edge validation
        self._connections_datamodel = get_connections_datamodel()
        # Key mapping for dynamic GraphML parsing
        self.key_map = {'node': {}, 'edge': {}}  # Mappa attr_name -> key_id
        # Track if we need to update the GraphML file with generated UUIDs
        self.graphml_tree = None  # Will store the parsed XML tree for slipback
        # Map refid → SVG role (e.g. 'continuity'). yEd assigns refids in
        # serialization order, so the same logical SVG can be id=1 in one
        # file and id=3 in another — never hardcode the number.
        self.svg_resource_map = {}
        # E2 — occurrence counter per deterministic-id key, so homonyms at the
        # same coordinates are numbered by document order instead of colliding.
        self._det_id_counts = {}

    # --- Deterministic ids (E2) --------------------------------------------

    def _node_xy(self, node_element):
        """Return the yEd ``(x, y)`` of ``node_element`` as a rounded string
        pair, or ``("", "")`` when the element has no geometry.

        ``find('.//…Geometry')`` returns the FIRST geometry in document order,
        which for a group node is the group's own realizer (the nested
        ``<graph>`` with the children comes after ``<data>``). This mirrors
        what the swimlane parser already does.
        """
        try:
            geom = node_element.find(f'.//{_Y_NS}Geometry')
            if geom is None:
                return ("", "")
            return (f"{float(geom.attrib.get('x', 0.0)):.2f}",
                    f"{float(geom.attrib.get('y', 0.0)):.2f}")
        except (ValueError, TypeError, AttributeError):
            return ("", "")

    def _deterministic_id(self, kind, *parts):
        """Mint a stable uuid5 for an element without an EMID.

        ``kind`` is the element family ('node', 'group', 'swimlane',
        'epoch_row', 'edge', 'node_dup_emid') and ``parts`` the identifying
        key. Repeated keys get an ``#n`` occurrence suffix (n = 1, 2, …) in
        document order, so duplicates are separated deterministically rather
        than overwriting one another.
        """
        key = "|".join([kind] + [str(p) for p in parts])
        seen = self._det_id_counts.get(key, 0)
        self._det_id_counts[key] = seen + 1
        if seen:
            key = f"{key}#{seen}"
        return str(uuid.uuid5(DETERMINISTIC_ID_NAMESPACE, key))

    def build_key_mapping(self, tree):
        """
        Costruisce una mappa dinamica delle chiavi GraphML.
        Questo permette di gestire file GraphML con campi custom (EMID, URI)
        senza hardcodare i key ID (d4, d5, d6...).

        Args:
            tree: XML ElementTree del file GraphML

        Returns:
            dict: Mappa con struttura {'node': {attr_name: key_id}, 'edge': {attr_name: key_id}}
        """
        key_map = {
            'node': {},  # Per nodi
            'edge': {}   # Per edge
        }

        # Scansiona tutti gli elementi <key> nel GraphML
        for key_elem in tree.findall('.//{http://graphml.graphdrawing.org/xmlns}key'):
            key_id = key_elem.attrib.get('id')
            attr_name = key_elem.attrib.get('attr.name')
            yfiles_type = key_elem.attrib.get('yfiles.type')
            key_for = key_elem.attrib.get('for')

            # Gestisci chiavi con attr.name (url, description, EMID, URI)
            if attr_name and key_id:
                if key_for == 'node':
                    key_map['node'][attr_name] = key_id
                elif key_for == 'edge':
                    key_map['edge'][attr_name] = key_id

            # Gestisci chiavi yfiles (nodegraphics, edgegraphics, etc.)
            elif yfiles_type and key_id:
                if key_for == 'node' and yfiles_type == 'nodegraphics':
                    key_map['node']['nodegraphics'] = key_id
                elif key_for == 'edge' and yfiles_type == 'edgegraphics':
                    key_map['edge']['edgegraphics'] = key_id

        print(f"[GraphML Parser] Built key mapping:")
        print(f"  Node keys: {key_map['node']}")
        print(f"  Edge keys: {key_map['edge']}")

        return key_map

    def build_svg_resource_map(self, tree):
        """
        Scan ``<y:Resource>`` entries and map each refid to a logical role
        based on the embedded SVG (``sodipodi:docname="continuity.svg"`` →
        ``'continuity'``).

        yEd serialises Resource ids in the order they appear in the file,
        so the same continuity SVG can be id=1, id=3 or anything else
        depending on which palette items were dragged in (and in what
        order). Pre-building this map lets EM_check_node_continuity
        match on what the SVG *is*, not on a brittle hardcoded number.

        Returns:
            dict: ``{refid: role}`` — only resources whose SVG content
            matches a known role are listed.
        """
        y_ns = '{http://www.yworks.com/xml/graphml}'
        resource_map = {}

        for resource in tree.findall(f'.//{y_ns}Resource'):
            refid = resource.attrib.get('id')
            if not refid:
                continue
            content = resource.text or ''
            if 'continuity.svg' in content:
                resource_map[refid] = 'continuity'

        if resource_map:
            print(f"[GraphML Parser] SVG resource roles: {resource_map}")
        return resource_map

    def extract_custom_fields(self, element, entity_type='node'):
        """
        Estrae i campi custom EMID e URI se presenti nel GraphML.

        Args:
            element: Elemento XML (node o edge)
            entity_type: 'node' o 'edge'

        Returns:
            dict: {'EMID': valore, 'URI': valore} se presenti, altrimenti {}
        """
        custom_fields = {}
        ns = 'http://graphml.graphdrawing.org/xmlns'

        # Estrai EMID
        if 'EMID' in self.key_map[entity_type]:
            emid_key = self.key_map[entity_type]['EMID']
            emid_elem = element.find(f'./{{{ns}}}data[@key="{emid_key}"]')
            if emid_elem is not None and emid_elem.text:
                custom_fields['EMID'] = emid_elem.text.strip()

        # Estrai URI
        if 'URI' in self.key_map[entity_type]:
            uri_key = self.key_map[entity_type]['URI']
            uri_elem = element.find(f'./{{{ns}}}data[@key="{uri_key}"]')
            if uri_elem is not None and uri_elem.text:
                custom_fields['URI'] = uri_elem.text.strip()

        return custom_fields

    def extract_graph_id_and_code(self, tree):
        """
        Extracts the ID and code of the graph from the GraphML file.
        
        Args:
            tree: XML ElementTree of the GraphML file
            
        Returns:
            tuple: (graph_id, graph_code) where graph_id is the actual ID and graph_code is the
                human-readable code (e.g. VDL16). Both could be None if not found.
        """
        import uuid

        graph_id = None
        graph_code = None
        
        # Look for NodeLabel to find the graph header
        for nodelabel in tree.findall('.//{http://graphml.graphdrawing.org/xmlns}data/{http://www.yworks.com/xml/graphml}TableNode/{http://www.yworks.com/xml/graphml}NodeLabel'):
            RowNodeLabelModelParameter = nodelabel.find('.//{http://www.yworks.com/xml/graphml}RowNodeLabelModelParameter')
            ColumnNodeLabelModelParameter = nodelabel.find('.//{http://www.yworks.com/xml/graphml}ColumnNodeLabelModelParameter')
            
            if RowNodeLabelModelParameter is None and ColumnNodeLabelModelParameter is None:
                try:
                    stringa_pulita, vocabolario = self.estrai_stringa_e_vocabolario(nodelabel.text)
                    # IMPKEYS · normalise header-key VARIANTS to the canonical keys
                    # BEFORE anything reads them (one place, no scattered casing
                    # logic). e.g. a real Aiano header uses UK `LICENCE`/`EMBARGO`;
                    # without this its LicenseNode was silently never materialised.
                    vocabolario = _normalize_header_vocab(vocabolario)

                    # Extract ID if present in vocabulary
                    if 'ID' in vocabolario:
                        graph_code = vocabolario['ID']

                    # If there's a specific ID in the vocabulary, use it
                    if 'graph_id' in vocabolario:
                        graph_id = vocabolario['graph_id']

                    # Store graph header metadata for downstream use. These stay
                    # in graph.ATTRIBUTES (in-memory only — the emjson exporter
                    # serialises graph.data/name, not attributes), so the DP-19
                    # inference pass still sees the canvas author/license/embargo
                    # presence. They are NOT the source of truth any more.
                    header_keys = [
                        'ORCID', 'author_name', 'author_surname',
                        'license', 'embargo', 'description'
                    ]
                    for key in header_keys:
                        if key in vocabolario:
                            self.graph.attributes[key] = vocabolario[key]

                    # IMP1 (2026-08-07): the graph-scope author / licence /
                    # embargo + EM-ID are materialised as first-class NODES
                    # (MIG1-A / DP-65), NOT written to graph.data. Stash the
                    # header values; parse() builds the nodes once
                    # graph.graph_id is fixed (the GraphNode + member ids derive
                    # from it), reusing the shared materialize_graph_scope helper.
                    # The legacy graph.data path is gone from the importer — the
                    # one-shot migration stays only for old em.json files.
                    _an = vocabolario.get('author_name', '')
                    _as = vocabolario.get('author_surname', '')
                    _display = f"{_an} {_as}".strip()
                    self._graph_scope_meta = {
                        'author': _display or None,
                        'license': vocabolario.get('license'),
                        'embargo': vocabolario.get('embargo'),
                        'orcid': vocabolario.get('ORCID'),
                        'em_id': vocabolario.get('ID'),
                    }

                    # Name the graph from the HEADER (IMP1): graph.name drives the
                    # EMStudio slot label; the file name is only the fallback used
                    # downstream when this is empty.
                    if stringa_pulita:
                        self.graph.name = {'default': stringa_pulita}
                        self.graph.attributes['graph_label'] = stringa_pulita

                    break
                except Exception as e:
                    pass
                    # print(f"Error extracting graph ID from node label: {e}")
        
        # If we didn't find a graph_code, use MISSINGCODE
        if not graph_code or graph_code == "site_id":
            graph_code = "MISSINGCODE"
            #print(f"Using fallback graph code: {graph_code}")
        
        # If we don't have a graph_id, derive a DETERMINISTIC one (E2). The
        # GraphNode created in parse() takes ``graph.graph_id`` as its own
        # node_id, so a random value here would make the node set irreproducible
        # too. Key = graph code + graph label, i.e. the identity the header
        # itself declares.
        if not graph_id:
            graph_id = self._deterministic_id(
                'graph', graph_code,
                self.graph.attributes.get('graph_label', ''))
            #print(f"Derived deterministic graph ID: {graph_id}")

        return graph_id, graph_code

    def parse(self):
        """
        Esegue il parsing del file GraphML e popola l'istanza di Graph.

        Returns:
            Graph: Istanza di Graph popolata con nodi e archi dal file GraphML.
        """
        import uuid

        tree = ET.parse(self.filepath)

        # E2 — azzera i contatori degli id deterministici PRIMA di qualunque
        # conio, così ri-usare lo stesso importer non sposta le occorrenze.
        self._det_id_counts = {}

        # Salva il tree per lo slipback
        self.graphml_tree = tree

        # Costruisci la mappa dinamica delle chiavi GraphML
        self.key_map = self.build_key_mapping(tree)

        # Identifica i refid degli SVG di ruolo noto (continuity, …).
        # Deve precedere parse_nodes() così che EM_check_node_continuity
        # possa risolvere il refid del nodo guardando il contenuto SVG
        # invece di affidarsi a un numero fisso.
        self.svg_resource_map = self.build_svg_resource_map(tree)

        # Build the XML-level parent map (original_id → parent original_id)
        # so the post-import auto-edge inference can find the containing
        # node of every paradata image node.
        self._original_parent_of = self._build_original_parent_map(tree)

        # Prima estrai il codice del grafo
        graph_id, graph_code = self.extract_graph_id_and_code(tree)
        
        # Se abbiamo trovato un codice, aggiungilo come attributo al grafo
        if graph_code:
            self.graph.attributes['graph_code'] = graph_code
            
        # Genera un ID univoco per il grafo se non esiste
        if not graph_id:
            # E2 — ramo ormai irraggiungibile (extract_graph_id_and_code
            # restituisce sempre un id), tenuto deterministico per coerenza.
            graph_id = self._deterministic_id('graph', graph_code or '')

        # Imposta l'ID univoco nel grafo
        self.graph.graph_id = graph_id
        
        # Memorizza gli ID originali per la mappatura
        self.id_mapping = {}  # {original_id: uuid_id}

        # Pass 0 — pre-scan dei nodi documento per fissare l'identità
        # persistente di ogni documento. La regola è:
        #
        #     priorità (per ogni ``nodename``):
        #       1. EMID del Master            (se esiste un nodo Master
        #                                       con EMID per quel nome)
        #       2. EMID della prima istanza   (se esiste almeno
        #                                       un'istanza con EMID)
        #       3. (nessuna entry)            → fallback al parsing
        #                                       normale, UUID per-nodo
        #
        # Questo passo elimina il bug "Master dopo istanza": senza
        # pre-scan, la prima istanza in ordine XML genera/usa un UUID
        # che diventa canonical, e l'EMID del Master (che arriva dopo)
        # viene scartato dal branch di dedup. Con il pre-scan
        # l'identità è decisa prima ancora che il parser tocchi i nodi,
        # ed è indipendente dall'ordine XML.
        self.canonical_emids_by_name = self._collect_canonical_document_emids(tree)

        # Prosegui con il parsing normale
        self.parse_nodes(tree)
        self.parse_edges(tree)

        # Restore the full set of physical stratigraphic relations from
        # the lossless side-channel key written by the s3dgraphy GraphML
        # exporter. Legacy files without the key are left untouched (the
        # reduced is_after / has_same_time set from parse_edges remains
        # in place). See module-level docstring for the rationale.
        json_channel_applied = (
            self._restore_physical_relations_from_side_channel(tree))

        # Fallback for files NOT produced by the lossless exporter: read
        # per-node ``physical_relationships`` (d13) packed strings — the
        # EM 1.6 palette / pyArchInit-native list-of-lists format — and
        # rebuild canonical edges from them. Skipped when the
        # graph-level JSON side channel was present, since that's
        # strictly richer (carries per-edge attributes and edge_ids).
        if not json_channel_applied:
            self._restore_physical_relations_from_node_attribute(tree)

        # Re-apply structured PropertyNode metadata (value /
        # property_type / units / attributes) from the
        # ``_s3d_property_metadata`` side channel. The yEd encoding
        # only carries the rendered description; this restores the
        # structured form so the (xlsx | GraphML | JSON) triangle is
        # lossless for qualia-style properties.
        self._restore_property_metadata_from_side_channel(tree)

        # Arricchisci i master document con i valori delle PropertyNode collegate
        self._enrich_canonical_documents()

        # Aggiungi qui la nuova funzionalità per collegare PropertyNode dai ParadataNodeGroup
        # Impostare verbose=True per avere output dettagliati durante il debug
        stats = self.graph.connect_paradatagroup_propertynode_to_stratigraphic(verbose=False)
        if stats["connections_created"] > 0:
            pass
            # print(f"\nCreati {stats['connections_created']} nuovi collegamenti diretti tra unità stratigrafiche e PropertyNode")

        # Assign stratigraphic units (and free paradata groups) to epochs
        # based on their Y position in the swimlane layout. This must run
        # BEFORE _infer_paradata_image_edges so that a top-level SL_PD
        # gains the has_first_epoch edge to its swimlane Epoch; the DP-19
        # auto-edge pass then uses that edge to find the target of the
        # paradata nodes contained in the group.
        self.connect_nodes_to_epochs()

        # Infer has_author / has_license / has_embargo / has_property edges
        # from paradata image nodes living inside a free ParadataNodeGroup
        # (DP-19 pattern). Target is the first non-ParadataNodeGroup XML
        # ancestor, or (fallback) the node pointed to by has_first_epoch
        # from the group itself. Canvas-level free groups with no anchor
        # are skipped because graph.attributes already carries
        # author/license/embargo via DP-40.
        self._infer_paradata_image_edges()

        # Warn when an EpochNode carries two disagreeing declarations of
        # absolute_time_start / absolute_time_end (one from the swimlane
        # header, one from a PropertyNode inside SL_PD). The resolver
        # already prefers the PropertyNode; this warning gives the user
        # a chance to reconcile the yEd source.
        self._warn_on_epoch_chronology_mismatch()

        br_nodes = [n for n in self.graph.nodes if hasattr(n, 'node_type') and n.node_type == "BR"]
        #print(f"\nTotal BR nodes included in the graph: {len(br_nodes)}")
        for node in br_nodes:
            pass
            # print(f"  BR Node: UUID={node.node_id}, Original ID={node.attributes.get('original_id', 'Unknown')}, y_pos={node.attributes.get('y_pos', 'Unknown')}")

        # Verifica se i nodi BR esistono nel grafo
        if len(br_nodes) == 0:
            # print("\nWARNING: No BR (continuity) nodes found in the graph!")
            # print("Looking for nodes with _continuity in description...")
            
            for node in self.graph.nodes:
                if hasattr(node, 'description') and '_continuity' in node.description:
                    pass
                    # print(f"  Found node with _continuity in description: {node.node_id} (Type: {node.node_type if hasattr(node, 'node_type') else 'Unknown'})")

        # IMP1 · materialise the graph-scope metadata (author / licence / embargo
        # + EM-ID) as first-class nodes (MIG1-A / DP-65), reusing the SHARED
        # helper so GraphML import and the em.json one-shot migration produce the
        # SAME shape. Done here, after graph.graph_id is fixed (member ids derive
        # from it) and after node/edge parsing, so there is no graph.data
        # double-truth and no interference with the inference passes above.
        meta = getattr(self, '_graph_scope_meta', None)
        if meta and any(meta.get(k) for k in
                        ('author', 'license', 'embargo', 'em_id')):
            from .emjson_importer import materialize_graph_scope
            materialize_graph_scope(
                self.graph,
                author=meta.get('author'),
                license=meta.get('license'),
                embargo=meta.get('embargo'),
                em_id=meta.get('em_id'),
                orcid=meta.get('orcid'),
            )

        return self.graph

    def slipback_uuids_to_graphml(self):
        """
        FASE 2: Slipback immediato - Aggiorna il file GraphML con gli UUID generati/riutilizzati.
        Popola i campi EMID con gli UUID di nodi ed edge creati da s3Dgraphy.
        """
        if not self.graphml_tree:
            print("[GraphML Slipback] ERROR: No GraphML tree available for slipback")
            return

        # Namespace GraphML
        ns = {'gml': 'http://graphml.graphdrawing.org/xmlns'}

        # Assicurati che esistano le chiavi EMID e URI nel GraphML
        root = self.graphml_tree.getroot()
        self._ensure_custom_keys(root)

        # Conta aggiornamenti
        nodes_updated = 0
        edges_updated = 0

        # Aggiorna nodi
        nodes_checked = 0
        nodes_in_mapping = 0
        for node_elem in self.graphml_tree.findall('.//gml:node', ns):
            nodes_checked += 1
            original_id = node_elem.attrib.get('id')
            if original_id in self.id_mapping:
                nodes_in_mapping += 1
                uuid_val = self.id_mapping[original_id]
                # Cerca il nodo nel grafo per ottenere URI
                graph_node = self.graph.find_node_by_id(uuid_val)
                node_uri = graph_node.attributes.get('URI') if graph_node and hasattr(graph_node, 'attributes') else None

                # Aggiorna EMID e URI nel GraphML
                if self._update_node_custom_fields(node_elem, uuid_val, node_uri):
                    nodes_updated += 1

        # Aggiorna edge
        for edge_elem in self.graphml_tree.findall('.//gml:edge', ns):
            original_edge_id = edge_elem.attrib.get('id')
            # Trova l'edge nel grafo
            for edge in self.graph.edges:
                if hasattr(edge, 'attributes') and edge.attributes.get('original_edge_id') == original_edge_id:
                    edge_uuid = edge.edge_id
                    edge_uri = edge.attributes.get('URI')

                    # Aggiorna EMID e URI nel GraphML
                    if self._update_edge_custom_fields(edge_elem, edge_uuid, edge_uri):
                        edges_updated += 1
                    break

        # Salva il GraphML aggiornato
        output_path = self.filepath  # Sovrascrive il file originale
        try:
            self.graphml_tree.write(output_path, encoding='UTF-8', xml_declaration=True)
            print(f"[GraphML Slipback] SUCCESS: Updated {nodes_updated} nodes and {edges_updated} edges")
            print(f"[GraphML Slipback] Saved to: {output_path}")
        except Exception as e:
            print(f"[GraphML Slipback] ERROR saving file: {e}")

    def _ensure_custom_keys(self, root):
        """Assicura che le chiavi EMID e URI esistano nel GraphML."""
        ns = {'gml': 'http://graphml.graphdrawing.org/xmlns'}

        # Controlla se EMID e URI keys esistono già
        existing_keys = {}
        for key_elem in root.findall('.//gml:key', ns):
            attr_name = key_elem.attrib.get('attr.name')
            if attr_name:
                existing_keys[attr_name] = key_elem

        # Trova il prossimo ID disponibile
        all_keys = root.findall('.//gml:key', ns)
        max_id = 0
        for key_elem in all_keys:
            key_id = key_elem.attrib.get('id', '')
            if key_id.startswith('d'):
                try:
                    num = int(key_id[1:])
                    max_id = max(max_id, num)
                except ValueError:
                    pass

        # Crea EMID key se non esiste
        if 'EMID' not in existing_keys:
            emid_key_id = f"d{max_id + 1}"
            max_id += 1

            # Crea key per nodi
            emid_node_key = ET.Element('{http://graphml.graphdrawing.org/xmlns}key')
            emid_node_key.attrib['attr.name'] = 'EMID'
            emid_node_key.attrib['attr.type'] = 'string'
            emid_node_key.attrib['for'] = 'node'
            emid_node_key.attrib['id'] = emid_key_id
            default_elem = ET.SubElement(emid_node_key, '{http://graphml.graphdrawing.org/xmlns}default')
            default_elem.attrib['{http://www.w3.org/XML/1998/namespace}space'] = 'preserve'
            root.insert(list(root).index(root.find('.//gml:graph', ns)), emid_node_key)

            # IMPORTANTE: Aggiorna key_map con la nuova chiave EMID per nodi
            self.key_map['node']['EMID'] = emid_key_id

            # Crea key per edge
            emid_edge_key_id = f"d{max_id + 1}"
            max_id += 1
            emid_edge_key = ET.Element('{http://graphml.graphdrawing.org/xmlns}key')
            emid_edge_key.attrib['attr.name'] = 'EMID'
            emid_edge_key.attrib['attr.type'] = 'string'
            emid_edge_key.attrib['for'] = 'edge'
            emid_edge_key.attrib['id'] = emid_edge_key_id
            default_elem = ET.SubElement(emid_edge_key, '{http://graphml.graphdrawing.org/xmlns}default')
            default_elem.attrib['{http://www.w3.org/XML/1998/namespace}space'] = 'preserve'
            root.insert(list(root).index(root.find('.//gml:graph', ns)), emid_edge_key)

            # IMPORTANTE: Aggiorna key_map con la nuova chiave EMID per edge
            self.key_map['edge']['EMID'] = emid_edge_key_id
            print(f"[GraphML Slipback] Created EMID keys")

        # Crea URI key se non esiste (stessa logica)
        if 'URI' not in existing_keys:
            uri_node_key_id = f"d{max_id + 1}"
            max_id += 1
            uri_node_key = ET.Element('{http://graphml.graphdrawing.org/xmlns}key')
            uri_node_key.attrib['attr.name'] = 'URI'
            uri_node_key.attrib['attr.type'] = 'string'
            uri_node_key.attrib['for'] = 'node'
            uri_node_key.attrib['id'] = uri_node_key_id
            default_elem = ET.SubElement(uri_node_key, '{http://graphml.graphdrawing.org/xmlns}default')
            default_elem.attrib['{http://www.w3.org/XML/1998/namespace}space'] = 'preserve'
            root.insert(list(root).index(root.find('.//gml:graph', ns)), uri_node_key)

            # IMPORTANTE: Aggiorna key_map
            self.key_map['node']['URI'] = uri_node_key_id

            uri_edge_key_id = f"d{max_id + 1}"
            max_id += 1
            uri_edge_key = ET.Element('{http://graphml.graphdrawing.org/xmlns}key')
            uri_edge_key.attrib['attr.name'] = 'URI'
            uri_edge_key.attrib['attr.type'] = 'string'
            uri_edge_key.attrib['for'] = 'edge'
            uri_edge_key.attrib['id'] = uri_edge_key_id
            default_elem = ET.SubElement(uri_edge_key, '{http://graphml.graphdrawing.org/xmlns}default')
            default_elem.attrib['{http://www.w3.org/XML/1998/namespace}space'] = 'preserve'
            root.insert(list(root).index(root.find('.//gml:graph', ns)), uri_edge_key)

            # IMPORTANTE: Aggiorna key_map
            self.key_map['edge']['URI'] = uri_edge_key_id
            print(f"[GraphML Slipback] Created URI keys")

    def _update_node_custom_fields(self, node_elem, uuid_val, uri_val=None):
        """Aggiorna i campi EMID e URI di un nodo nel GraphML."""
        ns = 'http://graphml.graphdrawing.org/xmlns'

        # Trova le chiavi per EMID e URI
        emid_key = self.key_map['node'].get('EMID')
        uri_key = self.key_map['node'].get('URI')

        updated = False

        # Aggiorna EMID
        if emid_key:
            emid_data = node_elem.find(f'.//{{{ns}}}data[@key="{emid_key}"]')
            if emid_data is None:
                # Crea nuovo elemento data
                emid_data = ET.Element(f'{{{ns}}}data')
                emid_data.attrib['key'] = emid_key
                node_elem.insert(0, emid_data)  # Inserisci all'inizio
            emid_data.text = uuid_val
            updated = True

        # Aggiorna URI se presente
        if uri_val and uri_key:
            uri_data = node_elem.find(f'.//{{{ns}}}data[@key="{uri_key}"]')
            if uri_data is None:
                uri_data = ET.Element(f'{{{ns}}}data')
                uri_data.attrib['key'] = uri_key
                node_elem.insert(1 if emid_key else 0, uri_data)
            uri_data.text = uri_val
            updated = True

        return updated

    def _update_edge_custom_fields(self, edge_elem, uuid_val, uri_val=None):
        """Aggiorna i campi EMID e URI di un edge nel GraphML."""
        ns = 'http://graphml.graphdrawing.org/xmlns'

        # Trova le chiavi per EMID e URI
        emid_key = self.key_map['edge'].get('EMID')
        uri_key = self.key_map['edge'].get('URI')

        updated = False

        # Aggiorna EMID
        if emid_key:
            emid_data = edge_elem.find(f'.//{{{ns}}}data[@key="{emid_key}"]')
            if emid_data is None:
                emid_data = ET.Element(f'{{{ns}}}data')
                emid_data.attrib['key'] = emid_key
                edge_elem.insert(0, emid_data)
            emid_data.text = uuid_val
            updated = True

        # Aggiorna URI se presente
        if uri_val and uri_key:
            uri_data = edge_elem.find(f'.//{{{ns}}}data[@key="{uri_key}"]')
            if uri_data is None:
                uri_data = ET.Element(f'{{{ns}}}data')
                uri_data.attrib['key'] = uri_key
                edge_elem.insert(1 if emid_key else 0, uri_data)
            uri_data.text = uri_val
            updated = True

        return updated

    def parse_nodes(self, tree):
        """
        Esegue il parsing dei nodi dal file GraphML.
        """
        # Prima raccogli tutti gli ID dei nodi per identificare potenziali duplicati
        all_node_ids = {}  # {node_id: count}
        
        for node_element in tree.findall('.//{http://graphml.graphdrawing.org/xmlns}node'):
            node_id = self.getnode_id(node_element)
            all_node_ids[node_id] = all_node_ids.get(node_id, 0) + 1
        
        # Registra i nodi con più occorrenze
        duplicate_ids = {node_id for node_id, count in all_node_ids.items() if count > 1}
        if duplicate_ids:
            #print(f"Attenzione: rilevati {len(duplicate_ids)} ID di nodi duplicati nel file GraphML:")
            for node_id in duplicate_ids:
                pass
                # print(f"  - {node_id}")
        
        # Ora processa i nodi normalmente
        for node_element in tree.findall('.//{http://graphml.graphdrawing.org/xmlns}node'):
            node_type = self._check_node_type(node_element)
            if node_type == 'node_simple':
                self.process_node_element(node_element)
            elif node_type == 'node_swimlane':
                self.extract_epochs(node_element, self.graph)
            elif node_type == 'node_group':
                self.handle_group_node(node_element)

    def parse_edges(self, tree):
        """
        Esegue il parsing degli archi dal file GraphML.
        """
        alledges = tree.findall('.//{http://graphml.graphdrawing.org/xmlns}edge')
        #print(f"Found {len(alledges)} edges in GraphML")
        
        # Prima traccia tutti gli ID originali e le loro relazioni
        edge_original_mappings = []
        
        for edge in alledges:
            original_edge_id = str(edge.attrib['id'])
            original_source_id = str(edge.attrib['source'])
            original_target_id = str(edge.attrib['target'])
            edge_type = self.EM_extract_edge_type(edge)

            # Estrai campi custom EMID e URI per l'edge
            edge_custom_fields = self.extract_custom_fields(edge, 'edge')

            # Gestisci gli ID duplicati
            if original_source_id in self.duplicate_id_map:
                #print(f"Remapping source: {original_source_id} -> {self.duplicate_id_map[original_source_id]}")
                original_source_id = self.duplicate_id_map[original_source_id]
            if original_target_id in self.duplicate_id_map:
                #print(f"Remapping target: {original_target_id} -> {self.duplicate_id_map[original_target_id]}")
                original_target_id = self.duplicate_id_map[original_target_id]

            # Salva le mappature originali (source/target mantengono la direzione del GraphML)
            # GraphML ha già source=recent, target=ancient, che corrisponde a "is_after"
            edge_original_mappings.append({
                'original_edge_id': original_edge_id,
                'original_source_id': original_source_id,
                'original_target_id': original_target_id,
                'edge_type': edge_type,
                'custom_fields': edge_custom_fields
            })
        
        # Ora crea gli archi usando gli UUID
        for mapping in edge_original_mappings:
            original_edge_id = mapping['original_edge_id']
            original_source_id = mapping['original_source_id']
            original_target_id = mapping['original_target_id']
            base_edge_type = mapping['edge_type']
            edge_custom_fields = mapping.get('custom_fields', {})

            # Ottieni gli UUID corrispondenti
            source_uuid = self.id_mapping.get(original_source_id)
            target_uuid = self.id_mapping.get(original_target_id)

            if source_uuid is not None and target_uuid is not None:
                try:
                    # FASE 3: Se esiste EMID per l'edge, riutilizzalo come UUID, altrimenti generane uno nuovo
                    if 'EMID' in edge_custom_fields and edge_custom_fields['EMID']:
                        edge_uuid = edge_custom_fields['EMID']
                        print(f"[GraphML Parser] Reusing existing EMID as edge ID: {edge_uuid} for edge {original_edge_id}")
                    else:
                        # E2 — id d'arco deterministico: l'id yEd dell'arco più
                        # i due estremi già risolti. Senza questo l'em.json
                        # cambierebbe a ogni import anche a nodi stabili.
                        edge_uuid = self._deterministic_id(
                            'edge', original_edge_id, source_uuid, target_uuid)

                    # Get the source and target nodes for edge type enhancement
                    source_node = self.graph.find_node_by_id(source_uuid)
                    target_node = self.graph.find_node_by_id(target_uuid)

                    # Enhance the edge type based on node types
                    enhanced_edge_type = self.enhance_edge_type(base_edge_type, source_node, target_node)

                    # Crea l'arco con il tipo avanzato
                    edge = self.graph.add_edge(edge_uuid, source_uuid, target_uuid, enhanced_edge_type)

                    # Aggiungi attributi di tracciamento
                    edge.attributes = edge.attributes if hasattr(edge, 'attributes') else {}
                    edge.attributes['original_edge_id'] = original_edge_id
                    edge.attributes['original_source_id'] = original_source_id
                    edge.attributes['original_target_id'] = original_target_id

                    # Aggiungi URI se presente
                    if 'URI' in edge_custom_fields and edge_custom_fields['URI']:
                        edge.attributes['URI'] = edge_custom_fields['URI']
                    
                except Exception as e:
                    pass
                    # print(f"Error adding edge {original_edge_id} ({edge_type}): {e}")
            else:
                # Report specifico sulla mappatura mancante
                if source_uuid is None:
                    pass
                    # print(f"Missing source UUID for edge {original_edge_id}: {original_source_id}")
                if target_uuid is None:
                    pass
                    # print(f"Missing target UUID for edge {original_edge_id}: {original_target_id}")
                
                # print(f"Warning: Could not create edge {original_edge_id} - Source: {original_source_id} -> Target: {original_target_id}")

    def _restore_physical_relations_from_side_channel(self, tree) -> bool:
        """Restore the original physical stratigraphic edges from the
        ``_s3d_physical_relations`` graph-level GraphML key, if present.

        The exporter writes this key BEFORE applying the Harris-style
        transitive reduction, so it carries the *full* set of physical
        relations (overlies, cuts, fills, abuts, is_before, bonded_to,
        equals, …) with their per-edge attributes (AUTHOR_n,
        AUTHOR_KIND_n, DOCUMENT_n, URI, …). yEd only sees the reduced
        ``is_after`` set; this method makes round-tripping the GraphML
        lossless by switching back to the authoritative edge set.

        Behaviour matrix:
          - Key present, list non-empty: drop every edge whose type is
            in :data:`PHYSICAL_STRATIGRAPHIC_TYPES` (those came from the
            reduction and are stale), then re-emit the original
            relations from the side channel.
          - Key present, list empty: nothing to do (the graph genuinely
            had no physical relations at export time).
          - Key absent (legacy file): leave the parsed edge set
            untouched — backward-compatible fallback.

        Source/target IDs in the side channel are the s3dgraphy node
        UUIDs as written into the EMID slipback fields. Since the
        importer reuses EMID as the UUID when present (see
        ``parse_edges`` / ``process_node_element``), the UUIDs round-trip
        directly. Unknown UUIDs are skipped with a warning so a partial
        graph still imports cleanly.

        Returns:
            ``True`` if the graph-level key was *declared* on the file
            (regardless of payload size), ``False`` otherwise. Callers
            use this to gate the per-node ``physical_relationships``
            (d13) fallback: an authoritative JSON channel should not be
            shadowed by the strictly poorer per-node packed string.
        """
        root = tree.getroot()
        ns = 'http://graphml.graphdrawing.org/xmlns'

        # 1) Locate the key id whose attr.name matches our side-channel
        # name. We do not assume a fixed key id (``d_s3d_phys_rel``)
        # because some downstream tooling renumbers keys on patch.
        side_channel_key_id = None
        for key_elem in root.findall(f'.//{{{ns}}}key'):
            if (key_elem.attrib.get('attr.name')
                    == _S3D_PHYSICAL_RELATIONS_ATTR_NAME
                    and key_elem.attrib.get('for') == 'graph'):
                side_channel_key_id = key_elem.attrib.get('id')
                break

        if not side_channel_key_id:
            # Legacy file: no key declared, nothing to restore. The
            # per-node ``physical_relationships`` (d13) fallback may
            # still apply — callers gate on the return value.
            return False

        # 2) Find the graph-level <data> element carrying the payload.
        # We expect it directly under <graph id="G">. Scan all top-level
        # graphs and pick the first matching data child so we tolerate
        # files where multiple graphs share the same key declaration.
        side_channel_data = None
        for graph_elem in root.findall(f'{{{ns}}}graph'):
            candidate = graph_elem.find(
                f'./{{{ns}}}data[@key="{side_channel_key_id}"]')
            if candidate is not None:
                side_channel_data = candidate
                break

        # From here on, the key was declared — the file was authored by
        # the lossless exporter (or a tool that knows about it). Return
        # True at every exit point so the per-node fallback stays out of
        # the way; the JSON channel is authoritative.
        if side_channel_data is None or not (side_channel_data.text or "").strip():
            # Key declared but no payload — treat as "no relations" but
            # don't fall back to d13 (that would re-introduce stale data
            # if the producer intentionally cleared the channel).
            return True

        try:
            relations = json.loads(side_channel_data.text)
        except (ValueError, TypeError) as exc:
            print(f"[GraphML Parser] WARNING: could not parse "
                  f"{_S3D_PHYSICAL_RELATIONS_ATTR_NAME} payload: {exc}")
            return True

        if not isinstance(relations, list):
            print(f"[GraphML Parser] WARNING: "
                  f"{_S3D_PHYSICAL_RELATIONS_ATTR_NAME} payload is not a "
                  f"list (got {type(relations).__name__}); ignoring")
            return True

        if not relations:
            # Genuinely empty: drop reduced edges anyway, since the
            # exporter would not have written them either if the graph
            # had no physical relations. But to be safe, leave them.
            return True

        # 3) Drop the reduced-physical edges produced by the export-side
        # transitive reduction. They are stale once we re-add the
        # originals below.
        before = len(self.graph.edges)
        self.graph.edges = [
            e for e in self.graph.edges
            if e.edge_type not in PHYSICAL_STRATIGRAPHIC_TYPES
        ]
        dropped = before - len(self.graph.edges)
        # Mark the in-memory indices as dirty (Graph._indices_dirty is the
        # bookkeeping flag toggled by add_edge / add_node).
        if hasattr(self.graph, "_indices_dirty"):
            self.graph._indices_dirty = True

        # 4) Re-emit each physical relation. Use the original edge_id if
        # present to maximise round-trip fidelity, else generate a fresh
        # UUID. Skip relations that point to UUIDs not present in the
        # imported graph (e.g. partial GraphML, deleted nodes).
        restored = 0
        skipped_missing = 0
        skipped_invalid = 0
        seen_edge_ids = {e.edge_id for e in self.graph.edges}
        for rel in relations:
            if not isinstance(rel, dict):
                skipped_invalid += 1
                continue
            source = rel.get("source")
            target = rel.get("target")
            edge_type = rel.get("edge_type")
            if not (source and target and edge_type):
                skipped_invalid += 1
                continue

            # Ensure both endpoints exist in the imported graph.
            if (self.graph.find_node_by_id(source) is None
                    or self.graph.find_node_by_id(target) is None):
                skipped_missing += 1
                continue

            # Resolve edge_id, avoiding collisions with already-present
            # edges (e.g. a non-physical edge that happens to share the
            # same edge_id was kept by the filter above).
            # E2 — deterministico anche qui, così il restore degli archi
            # fisici non re-conia id a ogni import.
            edge_id = rel.get("edge_id") or self._deterministic_id(
                'edge_physical', source, edge_type, target)
            if edge_id in seen_edge_ids:
                edge_id = self._deterministic_id(
                    'edge_physical_collision', edge_id, source, edge_type, target)

            try:
                edge = self.graph.add_edge(edge_id, source, target,
                                           edge_type)
            except ValueError as exc:
                print(f"[GraphML Parser] WARNING: failed to restore "
                      f"physical edge {source} -[{edge_type}]-> {target}: "
                      f"{exc}")
                skipped_invalid += 1
                continue

            attrs = rel.get("attributes") or {}
            if isinstance(attrs, dict) and attrs:
                if not hasattr(edge, "attributes") or edge.attributes is None:
                    edge.attributes = {}
                edge.attributes.update(attrs)

            seen_edge_ids.add(edge_id)
            restored += 1

        print(f"[GraphML Parser] {_S3D_PHYSICAL_RELATIONS_ATTR_NAME}: "
              f"dropped {dropped} reduced edges, restored {restored} "
              f"physical edges"
              + (f", skipped {skipped_missing} (missing endpoints)"
                 if skipped_missing else "")
              + (f", skipped {skipped_invalid} (invalid payload)"
                 if skipped_invalid else ""))
        return True

    def _restore_physical_relations_from_node_attribute(self, tree):
        """Rebuild canonical physical-stratigraphic edges from per-node
        ``physical_relationships`` (d13) packed strings.

        This is the fallback for GraphML files NOT produced by the
        s3dgraphy lossless exporter — e.g. files hand-authored in yEd
        with the EM 1.6 palette, or files emitted by a pyArchInit-side
        bridge that only fills the per-node attribute. The packed
        string is the same list-of-lists Python-literal format used by
        the pyArchInit ``us_table.rapporti`` column, so the GraphML ↔
        pyArchInit transit is byte-identical when the graph between
        them is unmutated.

        Behaviour:
          - For each ``<node>`` in the GraphML tree, look for a
            ``<data>`` child whose key id resolves to the
            ``physical_relationships`` (d13) declaration.
          - Parse the string with
            :func:`s3dgraphy.sync.rapporti.parse_rapporti`, which yields
            canonical 5-tuples ``(edge_type, target_us, area, sito,
            swap)``.
          - Resolve target nodes by walking the imported graph's
            nodes-by-name index; drop the reduced-physical edges (same
            way the JSON channel does) before re-adding the canonical
            ones so the in-memory graph isn't doubled up.

        Called only when
        :meth:`_restore_physical_relations_from_side_channel` reports
        no graph-level JSON channel was present.
        """
        from ..rapporti import parse_rapporti

        root = tree.getroot()
        ns = 'http://graphml.graphdrawing.org/xmlns'

        # 1) Resolve the d13 key id from the file (don't assume "d13",
        # since downstream tools may renumber keys on patch).
        d13_key_id = None
        for key_elem in root.findall(f'.//{{{ns}}}key'):
            if (key_elem.attrib.get('attr.name')
                    == 'physical_relationships'
                    and key_elem.attrib.get('for') == 'node'):
                d13_key_id = key_elem.attrib.get('id')
                break

        if not d13_key_id:
            # Legacy file with no per-node packed string declaration —
            # the reduced ``is_after`` edges from parse_edges stand.
            return

        # 2) Gather (source_node_id, raw_string) pairs by EMID. The
        # GraphML node element's ``id`` is the nested layout id; the
        # ``EMID`` (d7) data carries the s3dgraphy UUID, which is what
        # the imported graph indexes by. parse_nodes has already
        # populated the EMID slipback; reuse the same lookup pattern.
        emid_key_id = None
        for key_elem in root.findall(f'.//{{{ns}}}key'):
            if (key_elem.attrib.get('attr.name') == 'EMID'
                    and key_elem.attrib.get('for') == 'node'):
                emid_key_id = key_elem.attrib.get('id')
                break

        per_node_raw: list[tuple[str, str]] = []
        for node_elem in root.findall(f'.//{{{ns}}}node'):
            d13 = node_elem.find(f'./{{{ns}}}data[@key="{d13_key_id}"]')
            if d13 is None or not (d13.text or "").strip():
                continue
            emid = None
            if emid_key_id:
                emid_data = node_elem.find(
                    f'./{{{ns}}}data[@key="{emid_key_id}"]')
                if emid_data is not None and emid_data.text:
                    emid = emid_data.text.strip()
            if not emid:
                # Fall back to the layout id — process_node_element
                # uses it as the UUID when EMID is missing.
                emid = node_elem.attrib.get('id')
            if emid:
                per_node_raw.append((emid, d13.text))

        if not per_node_raw:
            return

        # 3) Build a name → list-of-nodes index for target resolution.
        # parse_rapporti yields ``target_us`` as the bare unit number
        # (no "US " prefix); match against the imported nodes' .name
        # after applying the same strip the writer used.
        from ..rapporti import strip_us_prefix
        nodes_by_name: dict = {}
        for n in self.graph.nodes:
            key = strip_us_prefix(getattr(n, "name", "") or "")
            nodes_by_name.setdefault(key, []).append(n)

        # 4) Drop the reduced physical edges (parse_edges produced
        # them); the per-node packed strings carry the canonical set.
        before = len(self.graph.edges)
        self.graph.edges = [
            e for e in self.graph.edges
            if e.edge_type not in PHYSICAL_STRATIGRAPHIC_TYPES
        ]
        dropped = before - len(self.graph.edges)
        if hasattr(self.graph, "_indices_dirty"):
            self.graph._indices_dirty = True

        restored = 0
        skipped_missing = 0
        skipped_invalid = 0
        seen_edge_ids = {e.edge_id for e in self.graph.edges}
        for source_uuid, raw in per_node_raw:
            src_node = self.graph.find_node_by_id(source_uuid)
            if src_node is None:
                skipped_invalid += 1
                continue
            for (edge_type, target_us, _area, _sito, swap) in \
                    parse_rapporti(raw):
                candidates = nodes_by_name.get(target_us)
                if not candidates:
                    skipped_missing += 1
                    continue
                # No family-preference disambiguation here — the
                # per-node fallback is by definition shallow (no
                # PD/property targets); first match is fine.
                tgt_node = candidates[0]
                src, dst = ((tgt_node, src_node) if swap
                            else (src_node, tgt_node))
                edge_id = (f"rap_{src.node_id}_{dst.node_id}_"
                           f"{edge_type}")
                if edge_id in seen_edge_ids:
                    continue
                try:
                    self.graph.add_edge(edge_id, src.node_id,
                                        dst.node_id, edge_type)
                except ValueError as exc:
                    print(f"[GraphML Parser] WARNING: failed to restore "
                          f"physical edge {src.node_id} "
                          f"-[{edge_type}]-> {dst.node_id}: {exc}")
                    skipped_invalid += 1
                    continue
                seen_edge_ids.add(edge_id)
                restored += 1

        print(f"[GraphML Parser] physical_relationships (d13): "
              f"dropped {dropped} reduced edges, restored {restored} "
              f"physical edges"
              + (f", skipped {skipped_missing} (target unresolved)"
                 if skipped_missing else "")
              + (f", skipped {skipped_invalid} (invalid)"
                 if skipped_invalid else ""))

    def _restore_property_metadata_from_side_channel(self, tree):
        """Reapply structured PropertyNode metadata from the
        ``_s3d_property_metadata`` graph-level GraphML key.

        Companion to :meth:`GraphMLExporter._write_property_metadata_data`.
        Without this restore the yEd encoding flattens ``value`` +
        ``attributes['units']`` into the description and loses
        ``property_type``. With it, the (xlsx | GraphML | JSON)
        triangle is lossless for qualia PropertyNodes too.

        Behaviour matrix:
          - Key present, dict non-empty: for each ``node_id`` entry,
            look up the node in the imported graph (UUIDs round-trip
            via EMID slipback) and write the structured fields back.
          - Key present, payload empty / malformed: warn and continue.
          - Key absent (legacy file): no-op.
        """
        root = tree.getroot()
        ns = 'http://graphml.graphdrawing.org/xmlns'

        # Locate the key id whose attr.name matches our side-channel
        # name. The id is conventionally ``d_s3d_prop_meta`` but we
        # do not hard-code it (some tooling renumbers keys on patch).
        side_channel_key_id = None
        for key_elem in root.findall(f'.//{{{ns}}}key'):
            if (key_elem.attrib.get('attr.name')
                    == _S3D_PROPERTY_METADATA_ATTR_NAME
                    and key_elem.attrib.get('for') == 'graph'):
                side_channel_key_id = key_elem.attrib.get('id')
                break

        if not side_channel_key_id:
            return  # Legacy file: nothing to restore.

        side_channel_data = None
        for graph_elem in root.findall(f'{{{ns}}}graph'):
            candidate = graph_elem.find(
                f'./{{{ns}}}data[@key="{side_channel_key_id}"]')
            if candidate is not None:
                side_channel_data = candidate
                break

        if side_channel_data is None or not (side_channel_data.text or "").strip():
            return

        try:
            property_map = json.loads(side_channel_data.text)
        except (ValueError, TypeError) as exc:
            print(f"[GraphML Parser] WARNING: could not parse "
                  f"{_S3D_PROPERTY_METADATA_ATTR_NAME} payload: {exc}")
            return

        if not isinstance(property_map, dict) or not property_map:
            return

        restored = 0
        skipped_missing = 0
        for node_id, entry in property_map.items():
            if not isinstance(entry, dict):
                continue
            node = self.graph.find_node_by_id(node_id)
            if node is None:
                skipped_missing += 1
                continue
            if "value" in entry:
                node.value = entry["value"]
            if "property_type" in entry:
                node.property_type = entry["property_type"]
            attrs = entry.get("attributes") or {}
            if isinstance(attrs, dict) and attrs:
                if not hasattr(node, "attributes") or node.attributes is None:
                    node.attributes = {}
                node.attributes.update(attrs)
            restored += 1

        if restored or skipped_missing:
            print(f"[GraphML Parser] {_S3D_PROPERTY_METADATA_ATTR_NAME}: "
                  f"restored {restored} PropertyNode(s)"
                  + (f", skipped {skipped_missing} (unknown node_id)"
                     if skipped_missing else ""))

    def process_node_element(self, node_element):
        """
        Processa un elemento nodo dal file GraphML e lo aggiunge al grafo.

        Args:
            node_element (Element): Elemento nodo XML dal file GraphML.
        """

        node_counter = getattr(self, '_node_counter', 0)
        self._node_counter = node_counter + 1

        # Estrai l'ID originale
        original_id = self.getnode_id(node_element)

        # Se abbiamo già mappato questo ID originale, non creare un nuovo nodo
        if original_id in self.id_mapping:
            #print(f"Skipping already processed node with original ID: {original_id}")
            return

        # Salta nodi commento/nota di yEd (sfondo giallo, non sono nodi EM)
        _nodename_for_id, _, _, _, _, fillcolor, _, _ = self.EM_extract_node_name(node_element)
        if fillcolor and fillcolor.upper() in ('#FFCC00', '#FFFF00', '#FFFF99'):
            print(f"[GraphML Parser] Skipping comment/note node: '{_nodename_for_id}' (fill={fillcolor})")
            return

        # Estrai campi custom EMID e URI
        custom_fields = self.extract_custom_fields(node_element, 'node')

        # FASE 3: Se esiste EMID, riutilizzalo come UUID, altrimenti generane uno
        # DETERMINISTICO (E2) — mai casuale, o il re-import non è riproducibile.
        _x, _y = self._node_xy(node_element)
        if 'EMID' in custom_fields and custom_fields['EMID']:
            uuid_id = custom_fields['EMID']

            # ⚠️ VALIDAZIONE: Controlla se questo EMID è già stato usato (possibile duplicazione in yEd)
            if uuid_id in [v for k, v in self.id_mapping.items() if k != original_id]:
                print(f"⚠️  WARNING: Duplicate EMID detected! EMID {uuid_id[:20]}... is already used by another node.")
                print(f"   This usually happens when duplicating nodes in yEd (Ctrl+D).")
                print(f"   Generating NEW UUID for node {original_id} to avoid conflicts.")
                uuid_id = self._deterministic_id(
                    'node_dup_emid', custom_fields['EMID'],
                    _nodename_for_id, _x, _y)
            else:
                print(f"[GraphML Parser] Reusing existing EMID as node ID: {uuid_id} for node {original_id}")
        else:
            # Nessun EMID: id derivato dal contenuto (tipo|nome|x|y), stabile
            # fra import successivi dello stesso file. Vedi E2.
            uuid_id = self._deterministic_id('node', _nodename_for_id, _x, _y)
            print(f"[GraphML Parser] Generated deterministic UUID: {uuid_id} for node {original_id}")

        # Memorizza la mappatura per uso futuro
        self.id_mapping[original_id] = uuid_id

        # Estrai URI se presente
        node_uri = custom_fields.get('URI', None)

        if self.EM_check_node_us(node_element):
            # Creazione del nodo stratigrafico e aggiunta al grafo
            nodename, nodedescription, nodeurl, nodeshape, node_y_pos, fillcolor, borderstyle, bordertype = self.EM_extract_node_name(node_element)

            stratigraphic_type = convert_shape2type(nodeshape, borderstyle, bordertype)[0]
            node_class = get_stratigraphic_node_class(stratigraphic_type)  # Ottieni la classe usando la funzione
            stratigraphic_node = node_class(
                node_id=uuid_id,
                name=nodename,
                description=nodedescription
            )
            # 1.6.12 · a USM is a US + masonry, recognised from its NAME: the EM
            # palette draws it exactly as a US, so the name is all a yEd file
            # has. The name stays as it is (USM101). 1.6.13 · USR / USS the
            # same, a US + coating.
            kind, code = kind_of_name(nodename)
            if kind is not None:
                set_kind(stratigraphic_node, kind, code)

            # Aggiungi attributi di tracciamento
            stratigraphic_node.attributes['original_id'] = original_id
            stratigraphic_node.attributes['graph_id'] = self.graph.graph_id

            # Aggiunta di runtime properties
            stratigraphic_node.attributes['shape'] = nodeshape
            stratigraphic_node.attributes['y_pos'] = float(node_y_pos)
            stratigraphic_node.attributes['fill_color'] = fillcolor
            stratigraphic_node.attributes['border_style'] = borderstyle

            # Aggiungi URI se presente
            if node_uri:
                stratigraphic_node.attributes['URI'] = node_uri

            #print(f"Node {self._node_counter}: {stratigraphic_node.node_id} (Original ID: {original_id}, Type: {stratigraphic_node.node_type})")

            self.graph.add_node(stratigraphic_node)

        elif self.EM_check_node_document(node_element):
            # Creazione del nodo documento e aggiunta al grafo
            result = self.EM_extract_document_node(node_element)
            nodename = result[0]
            node_id = result[1]
            nodedescription = result[2]
            nodeurl = result[3]
            border_color = result[5]
            border_width = result[6]
            doc_y_pos = result[7]

            is_canonical = self._is_canonical_document(border_color, border_width)

            # Pre-scan override: if Pass 0 determined a canonical EMID
            # for this nodename (Master EMID or first-instance EMID),
            # use it instead of the per-node uuid_id computed earlier.
            # This guarantees that the canonical identity for a doc is
            # always the Master EMID when the Master exists in the
            # file, regardless of XML order.
            canonical_emid = (
                getattr(self, 'canonical_emids_by_name', {}) or {}
            ).get(nodename)
            if canonical_emid and canonical_emid != uuid_id:
                uuid_id = canonical_emid
                # Keep id_mapping aligned for the current original_id;
                # the document_nodes_map will also be set to this id
                # below when the first occurrence is created.
                self.id_mapping[original_id] = uuid_id

            if nodename in self.document_nodes_map:
                # Documento già presente nel grafo
                existing_uuid = self.document_nodes_map[nodename]
                existing_doc = self.graph.find_node_by_id(existing_uuid)

                if is_canonical and existing_doc and not existing_doc.attributes.get('is_canonical', False):
                    # Canonico incontrato dopo un'istanza: aggiorna il nodo esistente
                    # con i dati del canonico (descrizione, attributi visivi, posizione).
                    # The previous Instance state is preserved in the
                    # 'instances' list so the exporter can re-emit it.
                    prev_original_id = existing_doc.attributes.get('original_id')
                    prev_y_pos = existing_doc.attributes.get('y_pos', 0.0)
                    # Read the instance's own EMID off the file, if any —
                    # we want round-trip fidelity, not just position.
                    try:
                        prev_emid = (existing_doc.attributes
                                     .get('original_emid'))
                    except Exception:
                        prev_emid = None
                    self._append_instance_record(
                        existing_doc,
                        original_id=prev_original_id,
                        emid=prev_emid,
                        y_pos=prev_y_pos,
                    )

                    if nodedescription:
                        existing_doc.description = nodedescription
                    if nodeurl:
                        existing_doc.url = nodeurl
                    existing_doc.attributes['is_canonical'] = True
                    existing_doc.attributes['border_color'] = border_color
                    existing_doc.attributes['border_width'] = border_width
                    existing_doc.attributes['certainty_class'] = self._get_certainty_class(border_color)
                    try:
                        existing_doc.attributes['y_pos'] = float(doc_y_pos)
                    except (ValueError, TypeError):
                        existing_doc.attributes['y_pos'] = 0.0
                    # The Master takes over as the "primary" XML
                    # original_id of the merged DocumentNode — that's
                    # what the exporter will use for the master node.
                    existing_doc.attributes['original_id'] = original_id
                    # Mappa l'ID originale del master per il remapping degli edge
                    self.id_mapping[original_id] = existing_uuid
                    existing_original_id = prev_original_id
                    if existing_original_id:
                        self.duplicate_id_map[original_id] = existing_original_id
                    else:
                        self.duplicate_id_map[original_id] = existing_uuid
                    print(f"[GraphML Parser] Master document '{nodename}' upgraded existing instance node ({existing_uuid})")
                else:
                    # Deduplicazione standard: istanza dopo master, o istanza duplicata.
                    # Record the instance so the exporter can re-emit it
                    # at round-trip with the original geometry / EMID.
                    if existing_doc is not None:
                        custom = self.extract_custom_fields(
                            node_element, 'node')
                        instance_emid = (custom.get('EMID')
                                         if custom else None)
                        try:
                            y_val = float(doc_y_pos)
                        except (ValueError, TypeError):
                            y_val = 0.0
                        self._append_instance_record(
                            existing_doc,
                            original_id=original_id,
                            emid=instance_emid,
                            y_pos=y_val,
                        )

                    if existing_doc and hasattr(existing_doc, 'attributes'):
                        existing_original_id = existing_doc.attributes.get('original_id')
                        if existing_original_id:
                            self.duplicate_id_map[original_id] = existing_original_id
                        else:
                            self.duplicate_id_map[original_id] = existing_uuid
                    else:
                        self.duplicate_id_map[original_id] = existing_uuid
            else:
                # Prima occorrenza: crea nuovo DocumentNode
                document_node = DocumentNode(
                    node_id=uuid_id,
                    name=nodename,
                    description=nodedescription,
                    url=nodeurl
                )

                # Aggiungi attributi di tracciamento
                document_node.attributes['original_id'] = original_id
                document_node.attributes['graph_id'] = self.graph.graph_id

                # Remember the EMID this node carried on the file (may
                # differ from ``uuid_id`` when the pre-scan promoted a
                # Master EMID). Used by the exporter to round-trip
                # instance positions / EMIDs without losing fidelity.
                try:
                    _custom = self.extract_custom_fields(node_element, 'node')
                    _emid_on_file = _custom.get('EMID') if _custom else None
                    if _emid_on_file:
                        document_node.attributes['original_emid'] = _emid_on_file.strip()
                except Exception:
                    pass

                # Attributi canonical document
                document_node.attributes['is_canonical'] = is_canonical
                # Record y_pos for ALL document nodes (not just canonical ones)
                # — needed to position instances on export.
                try:
                    document_node.attributes['y_pos'] = float(doc_y_pos)
                except (ValueError, TypeError):
                    document_node.attributes['y_pos'] = 0.0
                if is_canonical:
                    document_node.attributes['border_color'] = border_color
                    document_node.attributes['border_width'] = border_width
                    document_node.attributes['certainty_class'] = self._get_certainty_class(border_color)

                # Aggiungi URI se presente
                if node_uri:
                    document_node.attributes['URI'] = node_uri

                # Aggiungi al grafo e memorizza UUID
                self.graph.add_node(document_node)
                self.document_nodes_map[nodename] = uuid_id
                # Se c'è un URL valido, crea un nodo Link
                if nodeurl and nodeurl.strip() != 'Empty':
                    resource_node = self._create_resource_node(document_node, nodeurl)

        elif self.EM_check_node_property(node_element):
            # Creazione del nodo proprietà e aggiunta al grafo
            nodename, node_id, nodedescription, nodeurl, _ = self.EM_extract_property_node(node_element)
            property_node = PropertyNode(
                node_id=uuid_id,
                name=nodename,
                description=nodedescription,
                value=nodeurl,
                data={},  # Popola 'data' se necessario
                url=nodeurl
            )

            # Per PropertyNode
            property_node.attributes['original_id'] = original_id
            property_node.attributes['graph_id'] = self.graph.graph_id

            # Aggiungi URI se presente
            if node_uri:
                property_node.attributes['URI'] = node_uri

            self.graph.add_node(property_node)

        elif self.EM_check_node_extractor(node_element):
            # Creazione del nodo extractor e aggiunta al grafo
            nodename, node_id, nodedescription, nodeurl, _ = self.EM_extract_extractor_node(node_element)
            extractor_node = ExtractorNode(
                node_id=uuid_id,
                name=nodename,
                description=nodedescription,
                source=nodeurl
            )
            # Per extractor_node
            extractor_node.attributes['original_id'] = original_id
            extractor_node.attributes['graph_id'] = self.graph.graph_id

            # Aggiungi URI se presente
            if node_uri:
                extractor_node.attributes['URI'] = node_uri

            self.graph.add_node(extractor_node)

            # Se c'è un URL valido, crea un nodo Link
            if nodeurl and nodeurl.strip() != 'Empty':
                resource_node = self._create_resource_node(extractor_node, nodeurl)


        elif self.EM_check_node_combiner(node_element):
            # Creazione del nodo combiner e aggiunta al grafo
            nodename, node_id, nodedescription, nodeurl, _ = self.EM_extract_combiner_node(node_element)
            combiner_node = CombinerNode(
                node_id=uuid_id,
                name=nodename,
                description=nodedescription,
                sources=[nodeurl]
            )

            # Per combiner_node
            combiner_node.attributes['original_id'] = original_id
            combiner_node.attributes['graph_id'] = self.graph.graph_id

            # Aggiungi URI se presente
            if node_uri:
                combiner_node.attributes['URI'] = node_uri

            self.graph.add_node(combiner_node)

        elif self.EM_check_node_continuity(node_element):
            # Creazione del nodo continuity e aggiunta al grafo
            nodedescription, node_y_pos, node_id = self.EM_extract_continuity(node_element)
            continuity_node = ContinuityNode(
                node_id=uuid_id,
                name="continuity_node",
                description=nodedescription
            )

            # Aggiungi attributi di tracciamento
            continuity_node.attributes['original_id'] = original_id
            continuity_node.attributes['graph_id'] = self.graph.graph_id
            continuity_node.attributes['y_pos'] = float(node_y_pos)

            # Aggiungi URI se presente
            if node_uri:
                continuity_node.attributes['URI'] = node_uri

            #print(f"Adding continuity node to graph: {continuity_node.node_id} (Original ID: {original_id})")
            self.graph.add_node(continuity_node)

        elif self.EM_check_node_paradata_image(node_element):
            # Paradata image nodes (AuthorNode / AuthorAINode / LicenseNode / EmbargoNode).
            # Detection uses explicit marker → palette icon hash → label prefix.
            detected_type, label_text, node_description, nodeurl = \
                self.EM_extract_paradata_image_node(node_element)
            self._create_paradata_image_node(
                detected_type=detected_type,
                uuid_id=uuid_id,
                label_text=label_text,
                node_description=node_description,
                nodeurl=nodeurl,
                original_id=original_id,
                node_uri=node_uri,
            )

        else:
            # Creazione di un nodo generico
            node_id = self.getnode_id(node_element)
            node_name = self.EM_extract_generic_node_name(node_element)
            generic_node = Node(
                node_id=uuid_id,
                name=node_name,
                #node_type="Generic",
                description=""
            )
            self.graph.add_node(generic_node)
            # The shape/colour did not match any EM node type, so this node has
            # no type at all. Its name often reveals the intent (`SF04.2`,
            # `D38.1`) but reading a type out of a label would be guessing: the
            # author is told instead. Every edge touching it stays untyped too —
            # an edge cannot be resolved when one endpoint has no type.
            self.graph.add_state_warning(
                "untyped_node", uuid_id,
                f"Node '{node_name or uuid_id}' has no recognised EM type (its "
                f"yEd shape/colour matches no node type): it and its connections "
                f"stay untyped. Classify it in the source graph.")



    def _create_resource_node(self, source_node, url):
        """
        Creates a Link node for a resource.

        Args:
            source_node (Node): The source node with which the link is associated
            url (str): The URL or path of the resource

        Returns:
            ResourceNode: The Link node created
        """
        from ..resources.files import add_resource
        
        resource_node_id = f"{source_node.node_id}_link"
        
        # Verifica se il nodo Link esiste già
        existing_resource_node = self.graph.find_node_by_id(resource_node_id)
        if existing_resource_node:
            return existing_resource_node
        
        # Se non esiste, crealo
        resource_node = add_resource(
            self.graph, resource_id=resource_node_id,
            name=f"Link to {source_node.name}",
            description=f"Link to {source_node.description}" if source_node.description else "",
            files=[{"path": url}] if url else [])
        
        # Crea l'edge solo se non esiste già
        edge_id = f"{source_node.node_id}_has_linked_resource_{resource_node_id}"
        if not self.graph.find_edge_by_id(edge_id):
            self.graph.add_edge(
                edge_id=edge_id,
                edge_source=source_node.node_id,
                edge_target=resource_node.node_id,
                edge_type="has_linked_resource"
            )
        
        return resource_node
        
    def handle_group_node(self, node_element):
        """
        Gestisce un nodo di tipo gruppo dal file GraphML.

        Args:
            node_element (Element): Elemento nodo XML dal file GraphML.
        """

        # Estrarre l'ID originale, il nome e la descrizione del gruppo
        original_id = self.getnode_id(node_element)

        # Estrai campi custom EMID e URI
        custom_fields = self.extract_custom_fields(node_element, 'node')

        # FASE 3: Se esiste EMID, riutilizzalo come UUID, altrimenti generane uno nuovo
        if 'EMID' in custom_fields and custom_fields['EMID']:
            uuid_id = custom_fields['EMID']
            print(f"[GraphML Parser] Reusing existing EMID as group node ID: {uuid_id} for node {original_id}")
        else:
            # E2 — deterministico: nome del gruppo + geometria del suo realizer.
            _gx, _gy = self._node_xy(node_element)
            uuid_id = self._deterministic_id(
                'group', self.EM_extract_group_node_name(node_element), _gx, _gy)
            print(f"[GraphML Parser] Generated deterministic UUID for group node: {uuid_id} for node {original_id}")

        self.id_mapping[original_id] = uuid_id

        # Estrai URI se presente
        node_uri = custom_fields.get('URI', None)        
        
        # Estrarre l'ID, il nome e la descrizione del gruppo
        group_name = self.EM_extract_group_node_name(node_element)
        group_description = self.EM_extract_group_node_description(node_element)
        group_background_color = self.EM_extract_group_node_background_color(node_element)
        group_y_pos = self.EM_extract_group_node_y_pos(node_element)

        # Determinare il tipo di nodo gruppo basandoci sul background color
        group_node_type = self.determine_group_node_type_by_color(group_background_color)

        # US/USD Container: crea un nodo stratigrafico regolare (non un GroupNode)
        # La contenitorialità è espressa tramite edge is_part_of, non tramite tipo di nodo
        if group_node_type in ('USContainer', 'USDContainer', 'VSFContainer'):
            self._handle_stratigraphic_container(
                group_node_type, uuid_id, original_id, group_name,
                group_description, group_y_pos, node_uri, node_element
            )
            return

        if group_node_type == 'ActivityNodeGroup':
            group_node = ActivityNodeGroup(
                node_id=uuid_id,
                name=group_name,
                description=group_description,
                y_pos=group_y_pos
            )
        elif group_node_type == 'ParadataNodeGroup':
            group_node = ParadataNodeGroup(
                node_id=uuid_id,
                name=group_name,
                description=group_description,
                y_pos=group_y_pos
            )
        elif group_node_type == 'TimeBranchNodeGroup':
            group_node = TimeBranchNodeGroup(
                node_id=uuid_id,
                name=group_name,
                description=group_description,
                y_pos=group_y_pos
            )
        else:
            group_node = GroupNode(
                node_id=uuid_id,
                name=group_name,
                description=group_description,
                y_pos=group_y_pos
            )
            # No palette colour, so no EM role: the file simply does not say what
            # this box means. We neither guess it nor silently drop it — the
            # author is told, and can classify it (or leave it organisational).
            # Its members keep their membership edges; see the report's
            # "author warnings" column.
            self.graph.add_state_warning(
                "unclassified_group", uuid_id,
                f"Group '{group_name}' has no EM role (not a ParadataNodeGroup / "
                f"ActivityNodeGroup / TimeBranch / US-USD-VSF container): it is "
                f"kept as an organisational box. Classify it with a palette "
                f"colour if it should carry meaning.")

        # Aggiungi attributi di tracciamento
        group_node.attributes['original_id'] = original_id
        group_node.attributes['graph_id'] = self.graph.graph_id

        # Aggiungi URI se presente
        if node_uri:
            group_node.attributes['URI'] = node_uri

        # Aggiungere il nodo gruppo al grafo
        self.graph.add_node(group_node)

        # Processare i nodi contenuti nel gruppo
        subgraph = node_element.find('{http://graphml.graphdrawing.org/xmlns}graph')
        if subgraph is not None:
            subnodes = subgraph.findall('{http://graphml.graphdrawing.org/xmlns}node')
            for subnode in subnodes:
                subnode_original_id = self.getnode_id(subnode)
                subnode_type = self._check_node_type(subnode)
                if subnode_type == 'node_simple':
                    # Processare e aggiungere il nodo al grafo
                    self.process_node_element(subnode)
                elif subnode_type == 'node_group':
                    # Gestire ricorsivamente il sottogruppo
                    self.handle_group_node(subnode)
                elif subnode_type == 'node_swimlane':
                    # Gestire i nodi EpochNode se necessario
                    self.extract_epochs(subnode, self.graph)

                # Qui devi usare la mappatura UUID per creare l'arco
                if subnode_original_id in self.id_mapping:
                    subnode_uuid = self.id_mapping[subnode_original_id]

                    # Creare l'arco appropriato in base al tipo di gruppo
                    edge_type = "generic_connection"  # Fallback sicuro

                    if group_node_type == "ActivityNodeGroup":
                        edge_type = "is_in_activity"
                        edge_id_prefix = "is_in_activity"
                    elif group_node_type == "ParadataNodeGroup":
                        edge_type = "is_in_paradata_nodegroup"
                        edge_id_prefix = "is_in_paradata_nodegroup"
                    elif group_node_type == "TimeBranchNodeGroup":
                        edge_type = "is_in_timebranch"
                        edge_id_prefix = "is_in_timebranch"
                    else:
                        # Per altri tipi di gruppo non specificati
                        edge_id_prefix = "grouped_in"

                    # Crea l'edge con gli UUID
                    edge_id = f"{subnode_uuid}_{edge_id_prefix}_{uuid_id}"
                    try:
                        self.graph.add_edge(
                            edge_id=edge_id,
                            edge_source=subnode_uuid,  # Usa UUID
                            edge_target=uuid_id,      # Usa UUID
                            edge_type=edge_type
                        )
                    except Exception as e:
                        pass
                        # print(f"Error creating edge from {subnode_uuid} to {uuid_id}: {e}")

    def _handle_stratigraphic_container(self, group_node_type, uuid_id, original_id,
                                         group_name, group_description, group_y_pos,
                                         node_uri, node_element):
        """
        Gestisce un nodo gruppo GraphML che rappresenta una US, USD o VSF contenitrice.
        Crea un nodo stratigrafico regolare (StratigraphicUnit, DocumentaryStratigraphicUnit
        o VirtualSpecialFindUnit) e collega i nodi figli tramite edge is_part_of.

        La contenitorialità non è un tipo di nodo diverso: è una relazione (is_part_of).
        Questo permette al nodo container di mantenere tutte le proprietà stratigrafiche
        (epoca, attività, representation model, etc.).
        """
        # Crea il nodo stratigrafico appropriato
        if group_node_type == 'USContainer':
            container_node = StratigraphicUnit(
                node_id=uuid_id,
                name=group_name,
                description=group_description
            )
            container_node.attributes['shape'] = 'rectangle'
            container_node.attributes['border_style'] = '#9B3333'
            container_node.attributes['fill_color'] = '#FFFFFF'
            print(f"[GraphML Parser] Created US container node: {group_name} ({uuid_id})")
        elif group_node_type == 'USDContainer':
            container_node = DocumentaryStratigraphicUnit(
                node_id=uuid_id,
                name=group_name,
                description=group_description
            )
            container_node.attributes['shape'] = 'roundrectangle'
            container_node.attributes['border_style'] = '#D86400'
            container_node.attributes['fill_color'] = '#FFFFFF'
            print(f"[GraphML Parser] Created USD container node: {group_name} ({uuid_id})")
        else:  # VSFContainer
            container_node = VirtualSpecialFindUnit(
                node_id=uuid_id,
                name=group_name,
                description=group_description
            )
            container_node.attributes['shape'] = 'octagon'
            container_node.attributes['border_style'] = '#B19F61'
            container_node.attributes['fill_color'] = '#000000'
            print(f"[GraphML Parser] Created VSF container node: {group_name} ({uuid_id})")

        # Attributi di tracciamento
        container_node.attributes['original_id'] = original_id
        container_node.attributes['graph_id'] = self.graph.graph_id
        container_node.attributes['y_pos'] = float(group_y_pos)
        container_node.attributes['is_container'] = True

        if node_uri:
            container_node.attributes['URI'] = node_uri

        self.graph.add_node(container_node)

        # Processa i nodi figli contenuti nel gruppo
        subgraph = node_element.find('{http://graphml.graphdrawing.org/xmlns}graph')
        if subgraph is not None:
            subnodes = subgraph.findall('{http://graphml.graphdrawing.org/xmlns}node')
            for subnode in subnodes:
                subnode_original_id = self.getnode_id(subnode)
                subnode_type = self._check_node_type(subnode)

                if subnode_type == 'node_simple':
                    self.process_node_element(subnode)
                elif subnode_type == 'node_group':
                    self.handle_group_node(subnode)
                elif subnode_type == 'node_swimlane':
                    self.extract_epochs(subnode, self.graph)

                # Crea edge is_part_of: figlio -> container
                if subnode_original_id in self.id_mapping:
                    subnode_uuid = self.id_mapping[subnode_original_id]
                    edge_id = f"{subnode_uuid}_is_part_of_{uuid_id}"
                    try:
                        self.graph.add_edge(
                            edge_id=edge_id,
                            edge_source=subnode_uuid,
                            edge_target=uuid_id,
                            edge_type="is_part_of"
                        )
                        print(f"[GraphML Parser] Created is_part_of edge: {subnode_uuid} -> {uuid_id}")
                    except Exception as e:
                        print(f"Error creating is_part_of edge from {subnode_uuid} to {uuid_id}: {e}")

    def extract_epochs(self, node_element, graph):
        """
        Estrae gli EpochNode dal nodo swimlane nel file GraphML.
        """
        # FASE 2 SLIPBACK: Aggiungi il nodo swimlane stesso a id_mapping
        swimlane_original_id = self.getnode_id(node_element)

        # Estrai campi custom EMID e URI per il nodo swimlane
        custom_fields = self.extract_custom_fields(node_element, 'node')

        # Se esiste EMID, riutilizzalo, altrimenti genera nuovo UUID
        if 'EMID' in custom_fields and custom_fields['EMID']:
            swimlane_uuid = custom_fields['EMID']
            print(f"[GraphML Parser] Reusing existing EMID for swimlane node: {swimlane_uuid} for node {swimlane_original_id}")
        else:
            # E2 — deterministico. Lo swimlane è unico nel file: la sua
            # geometria basta come chiave (il nome non è esposto qui).
            _sx, _sy = self._node_xy(node_element)
            swimlane_uuid = self._deterministic_id(
                'swimlane', swimlane_original_id, _sx, _sy)
            print(f"[GraphML Parser] Generated deterministic UUID for swimlane node: {swimlane_uuid} for node {swimlane_original_id}")

        # Aggiungi alla mappatura
        self.id_mapping[swimlane_original_id] = swimlane_uuid

        # Mappa per tenere traccia delle righe per ID
        row_id_to_index = {}
        epoch_nodes = []

        geometry = node_element.find('.//{http://www.yworks.com/xml/graphml}Geometry')
        y_start = float(geometry.attrib['y'])

        y_min = y_start
        y_max = y_start

        # Crea prima tutti i nodi epoca
        # print(f"Creazione nodi epoca iniziali...")
        rows = node_element.findall('./{http://graphml.graphdrawing.org/xmlns}data/{http://www.yworks.com/xml/graphml}TableNode/{http://www.yworks.com/xml/graphml}Table/{http://www.yworks.com/xml/graphml}Rows/{http://www.yworks.com/xml/graphml}Row')
        for i, row in enumerate(rows):
            original_id = row.attrib['id']
            # E2 — le righe della tabella non hanno geometria propria: la
            # chiave è swimlane + id di riga + indice, tutti stabili nel file.
            uuid_id = self._deterministic_id(
                'epoch_row', swimlane_uuid, original_id, i)
            self.id_mapping[original_id] = uuid_id
            row_id_to_index[original_id] = i
            
            h_row = float(row.attrib['height'])
            y_min = y_max
            y_max += h_row

            epoch_node = EpochNode(
                node_id=uuid_id,
                name=f"temp_{i}",  # Nome temporaneo con indice per debug
                # BUGFIX-EPOCH (2026-08-06): UNDATED until the label proves a real
                # date. A fabricated -10000/10000 made every undated epoch read as
                # "10000 BC", so it sank to the bottom of a date sort and the
                # from-sketch relayout re-imposed that order over a manual move.
                # None → the emjson exporter omits start_time/end_time → the
                # consumer keeps the epoch in document/manual order.
                start_time=None,
                end_time=None
            )
        
            epoch_node.attributes['original_id'] = original_id
            epoch_node.min_y = y_min
            epoch_node.max_y = y_max
            self.graph.add_node(epoch_node)
            epoch_nodes.append(epoch_node)
            #print(f"Creato nodo epoca {i}: ID orig: {original_id}, UUID: {uuid_id}")

        # Aggiorna i nomi e i colori delle epoche
        # print(f"Aggiornamento nomi epoche...")
        for nodelabel in node_element.findall('./{http://graphml.graphdrawing.org/xmlns}data/{http://www.yworks.com/xml/graphml}TableNode/{http://www.yworks.com/xml/graphml}NodeLabel'):
            try:
                row_param = nodelabel.find('.//{http://www.yworks.com/xml/graphml}RowNodeLabelModelParameter')
                if row_param is not None:
                    label_text = nodelabel.text
                    original_id = str(row_param.attrib['id'])
                    
                    # Ottieni il colore se presente
                    e_color = nodelabel.attrib.get('backgroundColor', "#BCBCBC")
                    
                    #print(f"Processando etichetta con ID orig: {original_id}")
                    
                    # Cerca l'UUID corrispondente
                    uuid_id = self.id_mapping.get(original_id)
                    if not uuid_id:
                        # print(f"WARNING: UUID non trovato per ID originale {original_id}")
                        continue
                    
                    # Cerca il nodo epoca usando l'UUID
                    epoch_node = self.graph.find_node_by_id(uuid_id)
                    if not epoch_node:
                        # Fallback: cerca usando l'indice se disponibile
                        row_index = row_id_to_index.get(original_id)
                        if row_index is not None and row_index < len(epoch_nodes):
                            epoch_node = epoch_nodes[row_index]
                            # print(f"Trovato epoch_node usando indice di fallback: {row_index}")
                        else:
                            # print(f"WARNING: Nodo epoca non trovato per UUID {uuid_id} o indice {row_index}")
                            continue
                    
                    # Aggiorna le proprietà del nodo epoca
                    try:
                        stringa_pulita, vocabolario = self.estrai_stringa_e_vocabolario(label_text)
                        epoch_node.set_name(stringa_pulita)
                        
                        # BUGFIX-EPOCH (2026-08-06): keep the epoch UNDATED unless
                        # the label carries a real NUMERIC date. A missing key, the
                        # 'XX'/'X' placeholder, or any non-numeric value all mean
                        # "no date" → None, NEVER a fabricated -10000/10000. Real
                        # numeric dates (estrai_stringa_e_vocabolario returns int)
                        # pass through unchanged, so dated epochs are untouched.
                        start_raw = vocabolario.get('start')
                        end_raw = vocabolario.get('end')
                        start_value = start_raw if isinstance(start_raw, (int, float)) else None
                        end_value = end_raw if isinstance(end_raw, (int, float)) else None
                        epoch_node.set_start_time(start_value)
                        epoch_node.set_end_time(end_value)
                        #print(f"Aggiornato nodo epoca: '{stringa_pulita}' (start={start_value}, end={end_value})")
                    except Exception as e:
                        epoch_node.set_name(label_text)
                        # print(f"Fallback al nome completo: {label_text}: {str(e)}")                    
                    epoch_node.set_color(e_color)
                    #print(f"Impostato colore: {e_color}")
            except Exception as e:
                pass
                # print(f"ERROR durante l'elaborazione dell'etichetta: {e}")

    # IMPKEYS (2026-08-08): process_general_data was DEAD CODE after IMP1
    # (the graph name + graph-scope nodes are set in extract_graph_id_and_code
    # and materialize_graph_scope). Removed; header handling lives in one place.

    def _enrich_canonical_documents(self):
        """
        Dopo il parsing degli edge, copia i valori delle PropertyNode collegate
        ai canonical document nel loro dict 'data'.
        Es: D.70 canonical connesso a PropertyNode 'absolute_time_start' con valore '1870'
        -> document_node.data['absolute_time_start'] = '1870'
        """
        canonical_count = 0
        enriched_count = 0
        for node in self.graph.nodes:
            if not isinstance(node, DocumentNode):
                continue
            if not node.attributes.get('is_canonical', False):
                continue
            canonical_count += 1

            # Cerca edge uscenti da questo documento verso PropertyNode
            for edge in self.graph.edges:
                if edge.edge_source == node.node_id:
                    target = self.graph.find_node_by_id(edge.edge_target)
                    if isinstance(target, PropertyNode):
                        prop_name = target.name  # es: "absolute_time_start"
                        prop_value = target.description  # es: "1870"
                        if prop_name and prop_value:
                            node.data[prop_name] = prop_value
                            enriched_count += 1

        if canonical_count > 0:
            print(f"[GraphML Parser] Found {canonical_count} master document(s), enriched with {enriched_count} property value(s)")

    def connect_nodes_to_epochs(self):
        """
        Assegna le epoche ai nodi nel grafo in base alla posizione Y e gestisce i nodi continuity.
        """
        # print("\n=== Connecting nodes to epochs ===")
        
        # Verifica se ci sono nodi BR (continuity)
        br_nodes = [n for n in self.graph.nodes if hasattr(n, 'node_type') and n.node_type == "BR"]
        # print(f"Found {len(br_nodes)} BR (continuity) nodes for connection process")
        
        # Esegui una ricerca manuale nelle classi dei nodi per verificare che ContinuityNode esista e sia correttamente definito
        
        # print(f"ContinuityNode class node_type: {ContinuityNode.node_type}")

        # Tipi che, di default, vivono fino all'ultima epoca (continuità
        # implicita senza BR). Single source of truth in classification.py —
        # deve restare allineato con materialize_continuity (export). Ogni
        # altro tipo (special find, USD, virtuali, …) è birth-only.
        from ..classification import CONTINUITY_PERSISTENT_TYPES
        list_of_physical_stratigraphic_nodes = list(CONTINUITY_PERSISTENT_TYPES)

        # Crea indici per accesso rapido
        epochs = [n for n in self.graph.nodes if hasattr(n, 'node_type') and n.node_type == "EpochNode"]

        # print(f"Numero totale di epoche trovate: {len(epochs)}")
        if len(epochs) == 0:
            # print("AVVISO: Nessuna epoca trovata nel grafo")
            return

        # Crea un dizionario inverso per mappare UUID a ID originali
        reverse_mapping = {}
        for orig_id, uuid in self.id_mapping.items():
            reverse_mapping[uuid] = orig_id

        # print(f"Numero totale di epoche trovate: {len(epochs)}")
        if len(epochs) == 0:
            # print("AVVISO: Nessuna epoca trovata nel grafo")
            return

        # Debug info
        # print(f"Connect nodes to epochs: {len(self.graph.nodes)} nodes, {len(epochs)} epochs")
        
        # Usa una mappatura diretta per trovare i nodi continuity collegati a nodi stratigrafici
        continuity_connections = {}  # node_id -> continuity_node

        # Prima identifica le connessioni continuity dagli archi
        for edge in self.graph.edges:
            # Usa direttamente source e target degli edge
            source_id = edge.edge_source
            target_id = edge.edge_target
            
            # Verifica se il source è un nodo continuity
            source_node = self.graph.find_node_by_id(source_id)
            if source_node and hasattr(source_node, 'node_type') and source_node.node_type == "BR":
                continuity_connections[target_id] = source_node
                # print(f"Found continuity connection: {source_node.node_id} -> {target_id}")
        
        # Per ogni nodo stratigrafico
        for node in self.graph.nodes:
            if not hasattr(node, 'attributes') or not 'y_pos' in node.attributes:
                continue
                
            connected_continuity_node = None

            # Cerca il nodo continuity collegato direttamente con l'UUID
            connected_continuity_node = continuity_connections.get(node.node_id)
            
            if connected_continuity_node:
                pass
                # print(f"Found continuity for node {node.name} ({node.node_id}): {connected_continuity_node.node_id}")
            
            # A node only gets its swimlane epoch if the datamodel admits
            # has_first_epoch for its type. A role-less base GroupNode does not:
            # it is an organisational box, its members already carry their own
            # epoch, and the edge would only be rewritten to generic_connection.
            # The author is told about the group itself (handle_group_node), not
            # about the edge that could not exist.
            from ..edges.connection_resolver import connection_allowed_by_type
            if not connection_allowed_by_type(getattr(node, 'node_type', ''),
                                              "EpochNode", "has_first_epoch"):
                continue

            # Connetti alle epoche appropriate
            for epoch in epochs:
                if epoch.min_y < node.attributes['y_pos'] < epoch.max_y:
                    edge_id = f"{node.node_id}_{epoch.node_id}_first_epoch"
                    try:
                        self.graph.add_edge(edge_id, node.node_id, epoch.node_id, "has_first_epoch")
                        #print(f"Connected node {node.name} to epoch {epoch.name} (first)")
                    except Exception as e:
                        pass
                        # print(f"Error connecting node {node.name} to epoch {epoch.name} (first): {e}")
                    
                elif connected_continuity_node and hasattr(connected_continuity_node, 'attributes') and 'y_pos' in connected_continuity_node.attributes:
                    y_pos = node.attributes['y_pos']
                    continuity_y_pos = connected_continuity_node.attributes['y_pos']
                    # print(f"Node {node.name} (y_pos: {y_pos}) connected to continuity node {connected_continuity_node.node_id} (y_pos: {continuity_y_pos})")

                    if epoch.max_y < y_pos and epoch.max_y > continuity_y_pos:
                        try:
                            edge_id = f"{node.node_id}_{epoch.node_id}_survive"
                            self.graph.add_edge(edge_id, node.node_id, epoch.node_id, "survive_in_epoch")
                            #print(f"Connected node {node.name} to epoch {epoch.name} yeee (survive with continuity)")
                        except Exception as e:
                            pass
                            # print(f"Error connecting node {node.name} to epoch {epoch.name} (survive): {e}")
                    
                elif hasattr(node, 'node_type') and node.node_type in list_of_physical_stratigraphic_nodes:
                    # L'epoca è più recente del nodo (cioè il max_y dell'epoca è più basso del y_pos del nodo)
                    if epoch.max_y < node.attributes['y_pos']:
                        edge_id = f"{node.node_id}_{epoch.node_id}_survive"
                        try:
                            self.graph.add_edge(edge_id, node.node_id, epoch.node_id, "survive_in_epoch")
                            #print(f"Connected node {node.name} to epoch {epoch.name} (physical)")
                        except Exception as e:
                            pass
                            # print(f"Error connecting node {node.name} to epoch {epoch.name} (physical): {e}")

    # Funzioni di supporto per l'estrazione dei dati dai nodi

    def EM_extract_generic_node_name(self, node_element):
        node_name = ''
        ng_key = self.key_map.get('node', {}).get('nodegraphics', 'd6')
        ns = 'http://graphml.graphdrawing.org/xmlns'
        data_ng = node_element.find(f'./{{{ns}}}data[@key="{ng_key}"]')
        if data_ng is not None:
            node_label = data_ng.find('.//{http://www.yworks.com/xml/graphml}NodeLabel')
            if node_label is not None:
                node_name = self._check_if_empty(node_label.text)
        return node_name

    def EM_extract_group_node_name(self, node_element):
        group_name = ''
        ng_key = self.key_map.get('node', {}).get('nodegraphics', 'd6')
        ns = 'http://graphml.graphdrawing.org/xmlns'
        data_ng = node_element.find(f'./{{{ns}}}data[@key="{ng_key}"]')
        if data_ng is not None:
            node_label = data_ng.find('.//{http://www.yworks.com/xml/graphml}NodeLabel')
            if node_label is not None:
                group_name = self._check_if_empty(node_label.text)
        return group_name

    def EM_extract_group_node_description(self, node_element):
        group_description = ''
        description_key = self.key_map['node'].get('description')
        ns = 'http://graphml.graphdrawing.org/xmlns'
        if description_key:
            data_desc = node_element.find(f'./{{{ns}}}data[@key="{description_key}"]')
            if data_desc is not None and data_desc.text is not None:
                group_description = self.clean_comments(data_desc.text)
        return group_description

    def EM_extract_group_node_background_color(self, node_element):
        background_color = None
        ng_key = self.key_map.get('node', {}).get('nodegraphics', 'd6')
        ns = 'http://graphml.graphdrawing.org/xmlns'
        data_ng = node_element.find(f'./{{{ns}}}data[@key="{ng_key}"]')
        if data_ng is not None:
            node_label = data_ng.find('.//{http://www.yworks.com/xml/graphml}NodeLabel')
            if node_label is not None:
                background_color = node_label.attrib.get('backgroundColor')
        return background_color

    def EM_extract_group_node_y_pos(self, node_element):
        y_pos = 0.0
        ng_key = self.key_map.get('node', {}).get('nodegraphics', 'd6')
        ns = 'http://graphml.graphdrawing.org/xmlns'
        data_ng = node_element.find(f'./{{{ns}}}data[@key="{ng_key}"]')
        if data_ng is not None:
            geometry = data_ng.find('.//{http://www.yworks.com/xml/graphml}Geometry')
            if geometry is not None:
                y_pos = float(geometry.attrib.get('y', 0.0))
        return y_pos

    def determine_group_node_type_by_color(self, background_color):
        if background_color == '#CCFFFF':
            return 'ActivityNodeGroup'
        elif background_color == '#FFCC99':
            return 'ParadataNodeGroup'
        elif background_color == '#99CC00':
            return 'TimeBranchNodeGroup'
        elif background_color == '#9B3333':
            return 'USContainer'
        elif background_color == '#D86400':
            return 'USDContainer'
        elif background_color == '#B19F61':
            return 'VSFContainer'
        else:
            return 'GroupNode'

    # Funzioni per estrarre e verificare i vari tipi di nodi

    def EM_check_node_us(self, node_element):
        US_nodes_list = ['rectangle', 'parallelogram', 'ellipse', 'hexagon', 'octagon', 'roundrectangle']
        nodename, _, _, nodeshape, _, _, _, _ = self.EM_extract_node_name(node_element)
        return nodeshape in US_nodes_list

    def EM_extract_node_name(self, node_element):
        node_y_pos = None
        nodeshape = None
        nodeurl = ''
        nodedescription = ''
        nodename = None
        fillcolor = None
        borderstyle = None
        bordertype = 'line'

        # Usa key_map dinamico per trovare le chiavi corrette
        url_key = self.key_map['node'].get('url')
        description_key = self.key_map['node'].get('description')
        nodegraphics_key = self.key_map['node'].get('nodegraphics')

        for subnode in node_element.findall('.//{http://graphml.graphdrawing.org/xmlns}data'):
            attrib = subnode.attrib
            key = attrib.get('key')

            # Estrai URL usando la chiave dinamica
            if url_key and key == url_key:
                nodeurl = subnode.text if subnode.text else ''

            # Estrai description usando la chiave dinamica
            if description_key and key == description_key:
                if not subnode.text:
                    nodedescription = ''
                else:
                    nodedescription = self.clean_comments(subnode.text)

            # Estrai nodegraphics usando la chiave dinamica
            if nodegraphics_key and key == nodegraphics_key:
                for USname in subnode.findall('.//{http://www.yworks.com/xml/graphml}NodeLabel'):
                    nodename = self._check_if_empty(USname.text)
                for fill_color in subnode.findall('.//{http://www.yworks.com/xml/graphml}Fill'):
                    fillcolor = fill_color.attrib['color']
                for border_style in subnode.findall('.//{http://www.yworks.com/xml/graphml}BorderStyle'):
                    borderstyle = border_style.attrib['color']
                    bordertype = border_style.attrib.get('type', 'line')
                for USshape in subnode.findall('.//{http://www.yworks.com/xml/graphml}Shape'):
                    nodeshape = USshape.attrib['type']
                for geometry in subnode.findall('.//{http://www.yworks.com/xml/graphml}Geometry'):
                    node_y_pos = geometry.attrib['y']

        return nodename, nodedescription, nodeurl, nodeshape, node_y_pos, fillcolor, borderstyle, bordertype

    # Colour → geometry-axis variant key, loaded from the DATAMODEL
    # (em_visual_rules.json → document_variant_styles). The taxonomy lives
    # in one place only; this importer no longer hardcodes it (curation of
    # 12 July 2026). Values are the variant keys themselves
    # (reality_based / observable / asserted / em_based); a thick black
    # border (canonical_unknown) and unrecognised colours map to "unknown".
    # NOTE: legacy values direct/reconstructed/hypothetical are superseded.
    _variant_by_color = None

    @classmethod
    def _master_variant_colors(cls):
        if cls._variant_by_color is None:
            from ..nodes.base_node import load_json_mapping
            styles = (load_json_mapping("em_visual_rules.json")
                      .get("document_variant_styles") or {})
            out = {}
            for key, st in styles.items():
                if key.startswith("_") or not isinstance(st, dict):
                    continue
                try:
                    width = float(st.get("border_width", 0))
                except (TypeError, ValueError):
                    width = 0.0
                color = str(st.get("border_color", "")).upper()
                if width >= 3.0 and color and key != "canonical_unknown":
                    out[color] = key
            cls._variant_by_color = out
        return cls._variant_by_color

    def _is_canonical_document(self, border_color, border_width):
        """A master document has a thick border (width >= 3.0).

        The previous rule additionally required the border to be
        non-black (``border_color != "#000000"``). That excluded the
        case of a Master that is recognised as Master but has no
        geometry classification yet — the natural neutral colour for
        which is black. With this widened rule the *thickness*
        identifies the Master ROLE while the *colour* classifies the
        Master's geometry-axis category (reality_based / observable /
        asserted / em_based / unknown). A thin border, regardless of
        colour, is always an Instance.
        """
        if not border_width:
            return False
        try:
            return float(border_width) >= 3.0
        except (ValueError, TypeError):
            return False

    def _get_certainty_class(self, border_color):
        """Map border color to a semantic certainty class.

        Unknown / unrecognised colours (including pure black, used by
        unclassified Masters) map to ``"unknown"``.
        """
        if not border_color:
            return "unknown"
        return self._master_variant_colors().get(border_color.upper(), "unknown")

    @staticmethod
    def _append_instance_record(doc_node, original_id, emid, y_pos):
        """Record an Instance occurrence on its DocumentNode.

        ``doc_node.attributes['instances']`` is a list of dicts that
        the exporter consults to re-emit all yEd nodes the Master was
        deduplicated with. Each entry holds:

            {'original_id': <yEd xml id>,
             'emid':        <file EMID or None>,
             'y_pos':       <float for vertical position>}

        Duplicates by ``original_id`` are skipped so repeated calls
        don't bloat the list (idempotent in practice).
        """
        if doc_node is None:
            return
        instances = doc_node.attributes.get('instances')
        if instances is None:
            instances = []
            doc_node.attributes['instances'] = instances
        if original_id and any(r.get('original_id') == original_id for r in instances):
            return
        instances.append({
            'original_id': original_id,
            'emid': emid,
            'y_pos': float(y_pos) if y_pos is not None else 0.0,
        })

    def _collect_canonical_document_emids(self, tree):
        """Pre-scan dei nodi documento per fissare l'identità per nome.

        Costruisce e ritorna un ``dict`` ``{nodename: canonical_emid}``.
        Per ogni nome:

        - se almeno un nodo per quel nome è un Master *con* EMID nel
          file, vince l'EMID del primo Master incontrato;
        - altrimenti, se la **prima** occorrenza (in ordine XML) di
          quel nome ha un EMID sul file, vince quello;
        - in tutti gli altri casi la chiave non viene inserita (il
          parsing normale userà l'EMID per-nodo se presente o un fresh
          UUID, e l'identità si stabilizza al primo save).

        Perché solo la *prima* occorrenza? Perché ``parse_nodes``
        processa i nodi in ordine XML e la prima occorrenza fornisce
        ``node.attributes['original_id']``. Lo slipback poi scrive
        l'EMID canonical su QUELLA XML node. Se il pre-scan promuovesse
        l'EMID di un'istanza successiva, lo slipback creerebbe due
        nodi XML con lo stesso EMID (la prima occorrenza eredita
        l'EMID promosso, l'istanza successiva mantiene il suo): un
        conflitto. Restringere il fallback alla "prima" elimina il
        conflitto e mantiene l'invariante "EMID per nodo XML".

        L'ordine di lettura è quello restituito da ``tree.iter('node')``
        (depth-first, document order), deterministico per struttura.
        """
        canonical: dict = {}
        master_locked: set = set()
        # Track which names have already had their "first occurrence"
        # processed for the fallback path. Subsequent non-Master
        # occurrences cannot overwrite it.
        first_seen: set = set()

        nodes_xpath = '{http://graphml.graphdrawing.org/xmlns}node'
        for node_elem in tree.iter(nodes_xpath):
            # Skip group / swimlane nodes (yEd folders). Their XML
            # carries a ``yfiles.foldertype`` attribute and their
            # descendant ``<data>`` elements include children that
            # are real documents. If we run ``EM_extract_document_node``
            # on a group node it reaches into the children with a
            # recursive XPath and incorrectly reports the parent as
            # a "document" with the deepest child's label and the
            # parent's own EMID — which would then become the
            # canonical EMID for that child's name, colliding with
            # the parent group's UUID at add_node time. The downstream
            # ``parse_nodes`` already gates groups via ``_check_node_type``
            # and never calls ``EM_check_node_document`` on them; the
            # pre-scan must follow the same rule.
            if self._check_node_type(node_elem) != 'node_simple':
                continue

            try:
                (nodename, _node_id, _desc, _url, is_doc,
                 border_color, border_width, _y) = \
                    self.EM_extract_document_node(node_element=node_elem)
            except Exception:
                continue
            if not is_doc or not nodename:
                continue

            is_canonical = self._is_canonical_document(border_color, border_width)

            if nodename in master_locked:
                # Master EMID already fixed; nothing to do.
                continue

            custom = self.extract_custom_fields(node_elem, 'node')
            emid_on_file = custom.get('EMID') if custom else None
            if emid_on_file:
                emid_on_file = emid_on_file.strip() or None

            if is_canonical:
                if emid_on_file:
                    canonical[nodename] = emid_on_file
                    master_locked.add(nodename)
                # Master without EMID on file: don't insert. The
                # parser's normal flow will handle this — at first
                # save the Master XML node will receive a stable
                # EMID via slipback and subsequent loads will hit
                # the master branch here.
                continue

            # Non-Master (instance) branch. The fallback only fires
            # for the FIRST occurrence of the name; subsequent
            # occurrences cannot donate their EMID. See docstring.
            if nodename in first_seen:
                continue
            first_seen.add(nodename)
            if emid_on_file:
                canonical[nodename] = emid_on_file

        return canonical

    def EM_check_node_document(self, node_element):
        try:
            result = self.EM_extract_document_node(node_element)
            subnode_is_document = result[4]
        except (TypeError, IndexError):
            subnode_is_document = False
        return subnode_is_document

    def EM_extract_document_node(self, node_element):
        node_id = node_element.attrib['id']
        nodename = ""
        node_description = ""
        nodeurl = ""
        subnode_is_document = False
        border_color = "#000000"
        border_width = "1.0"
        doc_y_pos = "0"

        # Usa key_map dinamico
        url_key = self.key_map['node'].get('url')
        description_key = self.key_map['node'].get('description')
        nodegraphics_key = self.key_map['node'].get('nodegraphics')

        # Prima verifica se è un document node cercando le proprietà yfiles
        for subnode in node_element.findall('.//{http://graphml.graphdrawing.org/xmlns}data'):
            key = subnode.attrib.get('key')
            # Cerca nodegraphics usando la chiave dinamica
            if nodegraphics_key and key == nodegraphics_key:
                for USname in subnode.findall('.//{http://www.yworks.com/xml/graphml}NodeLabel'):
                    nodename = USname.text
                for nodetype in subnode.findall('.//{http://www.yworks.com/xml/graphml}Property'):
                    if nodetype.attrib.get('name') == 'com.yworks.bpmn.dataObjectType' and nodetype.attrib.get('value') == 'DATA_OBJECT_TYPE_PLAIN':
                        subnode_is_document = True
                # Estrai border color, width e posizione Y (per master detection)
                for border_style in subnode.findall('.//{http://www.yworks.com/xml/graphml}BorderStyle'):
                    border_color = border_style.attrib.get('color', '#000000')
                    border_width = border_style.attrib.get('width', '1.0')
                for geometry in subnode.findall('.//{http://www.yworks.com/xml/graphml}Geometry'):
                    doc_y_pos = geometry.attrib.get('y', '0')

        if subnode_is_document:
            for subnode in node_element.findall('.//{http://graphml.graphdrawing.org/xmlns}data'):
                key = subnode.attrib.get('key')
                if url_key and key == url_key:
                    if subnode.text is not None:
                        nodeurl = subnode.text
                if description_key and key == description_key:
                    node_description = self.clean_comments(subnode.text) if subnode.text else ''

        return nodename, node_id, node_description, nodeurl, subnode_is_document, border_color, border_width, doc_y_pos

    def EM_check_node_property(self, node_element):
        try:
            _, _, _, _, subnode_is_property = self.EM_extract_property_node(node_element)
        except UnboundLocalError:
            subnode_is_property = False
        return subnode_is_property

    def EM_extract_property_node(self, node_element):
        node_id = node_element.attrib['id']
        subnode_is_property = False
        nodeurl = ""
        nodename = ""
        node_description = ""

        # Usa key_map dinamico
        url_key = self.key_map['node'].get('url')
        description_key = self.key_map['node'].get('description')
        nodegraphics_key = self.key_map['node'].get('nodegraphics')

        # Prima verifica se è un property node
        for subnode in node_element.findall('.//{http://graphml.graphdrawing.org/xmlns}data'):
            key = subnode.attrib.get('key')
            if nodegraphics_key and key == nodegraphics_key:
                for USname in subnode.findall('.//{http://www.yworks.com/xml/graphml}NodeLabel'):
                    nodename = self._check_if_empty(USname.text)
                for nodetype in subnode.findall('.//{http://www.yworks.com/xml/graphml}Property'):
                    if nodetype.attrib.get('name') == 'com.yworks.bpmn.type' and nodetype.attrib.get('value') == 'ARTIFACT_TYPE_ANNOTATION':
                        subnode_is_property = True

        if subnode_is_property:
            for subnode in node_element.findall('.//{http://graphml.graphdrawing.org/xmlns}data'):
                key = subnode.attrib.get('key')
                if url_key and key == url_key:
                    if subnode.text is not None:
                        nodeurl = subnode.text
                if description_key and key == description_key:
                    node_description = self.clean_comments(subnode.text) if subnode.text else ''

        return nodename, node_id, node_description, nodeurl, subnode_is_property

    def _explicit_node_type(self, node_element):
        """Return the class name declared by an explicit ``_s3d_node_type:``
        marker in this node's URL or description, or ``None``.

        The marker is the ecosystem's escape hatch for "the drawing cannot say
        what this is, so I am telling you outright". It was already read for
        paradata image nodes (see :meth:`_detect_paradata_image_type`, signal 1)
        and is written by the s3Dgraphy GraphML exporter; C1 extends the same
        channel to extractors, combiners and continuity nodes, which until now
        could ONLY be recognised by their ``D.`` / ``C.`` label prefix.

        That prefix is a naming convention, not a type. An old EM graph whose
        author named an extractor after the unit it reads from (``SF04.2``)
        drew a perfectly unambiguous extractor icon and still came out
        untyped. The EMTools converter now writes the marker for those nodes,
        reading the type off the SVG resource — the type the FILE records —
        and this is where that lands.

        Being an explicit declaration, the marker takes precedence over every
        shape/label heuristic; it is only consulted when the heuristics have
        already failed, so nothing that used to resolve can change.
        """
        url_key = self.key_map.get('node', {}).get('url')
        description_key = self.key_map.get('node', {}).get('description')
        for subnode in node_element.findall(
                './/{http://graphml.graphdrawing.org/xmlns}data'):
            if not subnode.text:
                continue
            if subnode.attrib.get('key') not in (url_key, description_key):
                continue
            idx = subnode.text.find(_S3D_NODE_TYPE_MARKER)
            if idx < 0:
                continue
            tail = subnode.text[idx + len(_S3D_NODE_TYPE_MARKER):]
            match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", tail)
            if match:
                return match.group(1)
        return None

    def EM_check_node_extractor(self, node_element):
        try:
            _, _, _, _, subnode_is_extractor = self.EM_extract_extractor_node(node_element)
        except TypeError:
            subnode_is_extractor = False
        return subnode_is_extractor

    def EM_extract_extractor_node(self, node_element):
        node_id = node_element.attrib['id']
        subnode_is_extractor = False
        nodeurl = ""
        nodename = ""
        node_description = ""

        # Usa key_map dinamico
        url_key = self.key_map['node'].get('url')
        description_key = self.key_map['node'].get('description')
        nodegraphics_key = self.key_map['node'].get('nodegraphics')

        # Prima verifica se è un extractor node (nome inizia con "D.")
        for subnode in node_element.findall('.//{http://graphml.graphdrawing.org/xmlns}data'):
            key = subnode.attrib.get('key')
            if nodegraphics_key and key == nodegraphics_key:
                for USname in subnode.findall('.//{http://www.yworks.com/xml/graphml}NodeLabel'):
                    nodename = self._check_if_empty(USname.text)
                if nodename.startswith("D."):
                    subnode_is_extractor = True
                    # Warning if an extractor with the same name already exists
                    existing = self.graph.find_node_by_name(nodename)
                    if existing and hasattr(existing, 'node_type') and existing.node_type == 'extractor':
                        self.graph.add_warning(
                            f"Duplicate extractor name '{nodename}': "
                            f"already exists in the graph. "
                            f"Each extractor should have a unique sequential name. "
                            f"Please rename one of the '{nodename}' nodes in yEd."
                        )

        # C1 — the label convention did not match, but the node may declare its
        # type outright. Consulted only here, after the prefix test, so nothing
        # that already resolved can change.
        if not subnode_is_extractor and \
                self._explicit_node_type(node_element) == "ExtractorNode":
            subnode_is_extractor = True

        if subnode_is_extractor:
            for subnode in node_element.findall('.//{http://graphml.graphdrawing.org/xmlns}data'):
                key = subnode.attrib.get('key')
                if url_key and key == url_key:
                    if subnode.text is not None:
                        nodeurl = self._check_if_empty(subnode.text)
                if description_key and key == description_key:
                    node_description = self.clean_comments(self._check_if_empty(subnode.text)) if subnode.text else ''
        # The `_s3d_node_type:` marker is machinery, not prose: keep it out of
        # the description the author reads.
        node_description = self._strip_s3d_marker(node_description)

        return nodename, node_id, node_description, nodeurl, subnode_is_extractor

    def EM_check_node_combiner(self, node_element):
        try:
            _, _, _, _, subnode_is_combiner = self.EM_extract_combiner_node(node_element)
        except TypeError:
            subnode_is_combiner = False
        return subnode_is_combiner

    def EM_extract_combiner_node(self, node_element):
        node_id = node_element.attrib['id']
        subnode_is_combiner = False
        nodeurl = ""
        nodename = ""
        node_description = ""

        # Usa key_map dinamico
        url_key = self.key_map['node'].get('url')
        description_key = self.key_map['node'].get('description')
        nodegraphics_key = self.key_map['node'].get('nodegraphics')

        # Prima verifica se è un combiner node (nome inizia con "C.")
        for subnode in node_element.findall('.//{http://graphml.graphdrawing.org/xmlns}data'):
            key = subnode.attrib.get('key')
            if nodegraphics_key and key == nodegraphics_key:
                for USname in subnode.findall('.//{http://www.yworks.com/xml/graphml}NodeLabel'):
                    nodename = self._check_if_empty(USname.text)
                if nodename.startswith("C."):
                    subnode_is_combiner = True

        # C1 — same escape hatch as the extractor: an explicit declaration wins
        # where the label convention was never followed.
        if not subnode_is_combiner and \
                self._explicit_node_type(node_element) == "CombinerNode":
            subnode_is_combiner = True

        if subnode_is_combiner:
            for subnode in node_element.findall('.//{http://graphml.graphdrawing.org/xmlns}data'):
                key = subnode.attrib.get('key')
                if url_key and key == url_key:
                    if subnode.text is not None:
                        nodeurl = self._check_if_empty(subnode.text)
                if description_key and key == description_key:
                    node_description = self.clean_comments(self._check_if_empty(subnode.text)) if subnode.text else ''
        node_description = self._strip_s3d_marker(node_description)

        return nodename, node_id, node_description, nodeurl, subnode_is_combiner

    def EM_check_node_continuity(self, node_element):
        """
        Verifica se un nodo è un nodo di continuità (BR).
        Usa una detection multi-segnale:

        A) '_continuity' nel campo URL o description
        B) ShapeNode con shape type 'diamond'
        C) SVGNode il cui SVGContent refid punta alla risorsa
           ``continuity.svg`` (refid risolto dinamicamente, vedi
           build_svg_resource_map — yEd numera le Resource per ordine
           di serializzazione, non c'è un id fisso)
        D) marcatore esplicito ``_s3d_node_type:ContinuityNode`` (C1)

        Args:
            node_element: Elemento XML del nodo

        Returns:
            bool: True se il nodo è di tipo continuity
        """
        url_key = self.key_map.get('node', {}).get('url')
        description_key = self.key_map.get('node', {}).get('description')
        nodegraphics_key = self.key_map.get('node', {}).get('nodegraphics')

        # Signal A: '_continuity' marker nel campo URL o description
        for subnode in node_element.findall('.//{http://graphml.graphdrawing.org/xmlns}data'):
            key = subnode.attrib.get('key')
            if subnode.text and "_continuity" in subnode.text:
                if key == url_key or key == description_key:
                    return True

        # Signal B: ShapeNode con shape type 'diamond'
        _, _, _, nodeshape, _, _, _, _ = self.EM_extract_node_name(node_element)
        if nodeshape == "diamond":
            return True

        # Signal C: SVGNode che referenzia la risorsa continuity.svg
        y_ns = '{http://www.yworks.com/xml/graphml}'
        for subnode in node_element.findall('.//{http://graphml.graphdrawing.org/xmlns}data'):
            if subnode.attrib.get('key') == nodegraphics_key:
                svg_content = subnode.find(f'.//{y_ns}SVGNode/{y_ns}SVGModel/{y_ns}SVGContent')
                if svg_content is not None:
                    refid = svg_content.attrib.get('refid')
                    if refid and self.svg_resource_map.get(refid) == 'continuity':
                        return True

        # Signal D: explicit `_s3d_node_type:ContinuityNode` marker (C1) — for
        # a graph whose continuity SVG carries no recognisable docname.
        if self._explicit_node_type(node_element) == "ContinuityNode":
            return True

        return False

    def EM_extract_continuity(self, node_element):
        """
        Estrae informazioni da un nodo continuity.
        Supporta sia SVGNode che ShapeNode (diamond).

        Args:
            node_element: Elemento XML del nodo

        Returns:
            tuple: (descrizione, posizione y, id)
        """
        is_url_found = False
        node_y_pos = 0.0
        nodedescription = None
        node_id = node_element.attrib['id']

        # Use dynamic key mapping
        url_key = self.key_map.get('node', {}).get('url')
        description_key = self.key_map.get('node', {}).get('description')
        ng_key = self.key_map.get('node', {}).get('nodegraphics')

        y_ns = '{http://www.yworks.com/xml/graphml}'

        for subnode in node_element.findall('.//{http://graphml.graphdrawing.org/xmlns}data'):
            key = subnode.attrib.get('key')

            # Estrai descrizione dal campo url o description
            if key == url_key and subnode.text:
                is_url_found = True
                nodedescription = subnode.text
            elif key == description_key and subnode.text and not is_url_found:
                nodedescription = subnode.text

            # Estrai y_pos dal nodegraphics (supporta SVGNode e ShapeNode)
            if key == ng_key:
                # SVGNode geometry
                svg_geom = subnode.find(f'.//{y_ns}SVGNode/{y_ns}Geometry')
                if svg_geom is not None:
                    try:
                        node_y_pos = float(svg_geom.attrib.get('y', '0.0'))
                    except (ValueError, TypeError):
                        node_y_pos = 0.0

                # ShapeNode geometry (fallback per nodi diamond nativi yEd)
                shape_geom = subnode.find(f'.//{y_ns}ShapeNode/{y_ns}Geometry')
                if shape_geom is not None:
                    try:
                        node_y_pos = float(shape_geom.attrib.get('y', '0.0'))
                    except (ValueError, TypeError):
                        node_y_pos = 0.0

                # Fallback generico: qualsiasi Geometry nel data block
                if node_y_pos == 0.0:
                    generic_geom = subnode.find(f'.//{y_ns}Geometry')
                    if generic_geom is not None:
                        try:
                            node_y_pos = float(generic_geom.attrib.get('y', '0.0'))
                        except (ValueError, TypeError):
                            node_y_pos = 0.0

        if not is_url_found and nodedescription is None:
            nodedescription = ''

        return nodedescription, node_y_pos, node_id

    # ------------------------------------------------------------------
    # Paradata image nodes (AuthorNode / AuthorAINode / LicenseNode /
    # EmbargoNode) — multi-signal detection
    # ------------------------------------------------------------------

    def _detect_paradata_image_type(self, node_element):
        """Return the paradata node_type for an ImageNode, or ``None``.

        Signals, in order of strength:
          1. Description / URL carries ``_s3d_node_type:<NodeType>`` marker
             (explicit round-trip, written by the s3Dgraphy exporter).
          2. ``<y:ImageNode>`` + label starts with a known prefix from
             ``em_palette_icons.json`` (``AI.``, ``A.``, ``LI.``, ``EB.``).
             Longest-first to avoid ``A.`` shadowing ``AI.``.
        """
        url_key = self.key_map.get('node', {}).get('url')
        description_key = self.key_map.get('node', {}).get('description')

        # Signal 1: explicit marker
        for subnode in node_element.findall(
                './/{http://graphml.graphdrawing.org/xmlns}data'):
            if not subnode.text:
                continue
            key = subnode.attrib.get('key')
            if key not in (url_key, description_key):
                continue
            idx = subnode.text.find(_S3D_NODE_TYPE_MARKER)
            if idx >= 0:
                tail = subnode.text[idx + len(_S3D_NODE_TYPE_MARKER):]
                explicit = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", tail)
                if explicit:
                    return explicit.group(1)

        # Signal 2: ImageNode + label prefix
        image_nodes = node_element.findall(f'.//{_Y_NS}ImageNode')
        if not image_nodes:
            return None
        image_node = image_nodes[0]

        label_elem = image_node.find(f'.//{_Y_NS}NodeLabel')
        label_text = (label_elem.text or "").strip() if label_elem is not None else ""
        # Longest prefix first so "AI." wins over "A."
        for prefix in sorted(_PALETTE_LABEL_PREFIXES.keys(), key=len, reverse=True):
            if label_text.startswith(prefix):
                return _PALETTE_LABEL_PREFIXES[prefix]

        return None

    def EM_check_node_paradata_image(self, node_element):
        """True if this element is an Author/AuthorAI/License/Embargo node."""
        return self._detect_paradata_image_type(node_element) is not None

    def EM_extract_paradata_image_node(self, node_element):
        """Extract (detected_type, label, description, url) for a paradata image node.

        The caller is expected to have already confirmed the type via
        :meth:`EM_check_node_paradata_image` (or, equivalently, by calling
        :meth:`_detect_paradata_image_type` directly).
        """
        detected_type = self._detect_paradata_image_type(node_element)
        url_key = self.key_map.get('node', {}).get('url')
        description_key = self.key_map.get('node', {}).get('description')
        nodegraphics_key = self.key_map.get('node', {}).get('nodegraphics')

        label_text = ""
        node_description = ""
        nodeurl = ""

        for subnode in node_element.findall(
                './/{http://graphml.graphdrawing.org/xmlns}data'):
            key = subnode.attrib.get('key')
            if nodegraphics_key and key == nodegraphics_key:
                label_elem = subnode.find(f'.//{_Y_NS}NodeLabel')
                if label_elem is not None and label_elem.text:
                    label_text = label_elem.text.strip()
            elif url_key and key == url_key and subnode.text:
                nodeurl = self._check_if_empty(subnode.text)
            elif description_key and key == description_key and subnode.text:
                node_description = self.clean_comments(
                    self._check_if_empty(subnode.text)
                )

        return detected_type, label_text, node_description, nodeurl

    def _build_original_parent_map(self, tree):
        """Return ``{original_id: parent_original_id}`` built from the XML
        tree. Used by the post-import auto-edge inference to find the
        containing node of each paradata image node.
        """
        parent_of = {}
        graphml_ns = '{http://graphml.graphdrawing.org/xmlns}'
        node_tag = f'{graphml_ns}node'

        def walk(elem, current_parent):
            new_parent = current_parent
            if elem.tag == node_tag:
                nid = elem.attrib.get('id')
                if nid is not None:
                    if current_parent is not None:
                        parent_of[nid] = current_parent
                    new_parent = nid
            for child in elem:
                walk(child, new_parent)

        walk(tree.getroot(), None)
        return parent_of

    def _infer_paradata_image_edges(self):
        """Emit has_author / has_license / has_embargo / has_property edges
        for paradata nodes that live inside a **free** ParadataNodeGroup.

        Two kinds of ParadataNodeGroup coexist in an EM graph:

        1. **Claimed** (node-level, DP-43 pattern). The group is attached to
           a specific stratigraphic unit / document via an explicit
           ``has_paradata_nodegroup`` edge drawn by the author in yEd.
           The existing ``Graph.connect_paradatagroup_propertynode_to_stratigraphic``
           already wires PropertyNodes in these groups to the claimer. We
           **skip** these groups here to avoid double-wiring.

        2. **Free** (swimlane- or canvas-level, DP-19 pattern). The group
           has NO incoming ``has_paradata_nodegroup`` edge. By convention
           its name starts with ``SL_`` (e.g. ``SL_PD``, ``SL_Metadata``).
           For each paradata image / PropertyNode inside, we emit the
           corresponding ``has_*`` edge from the target node of the group.

        Two yEd layouts are supported, both interoperable:

        * **XML-nested layout**: paradata items are visually placed inside
          the SL_PD group in yEd (the group contains them in the XML tree).
          The target node is the first non-ParadataNodeGroup XML ancestor
          (typically an EpochNode in a swimlane column).
        * **Top-level layout**: the SL_PD sits at canvas top level and
          draws a ``has_first_epoch`` edge towards its target Epoch;
          children are connected via ``is_in_paradata_nodegroup`` edges.
          In this case the target is the node pointed to by that
          ``has_first_epoch`` edge.

        Edge type per paradata-node class:
          - AuthorNode / AuthorAINode → ``has_author``
          - LicenseNode              → ``has_license``
          - EmbargoNode              → ``has_embargo``
          - PropertyNode             → ``has_property``  (DP-32 Layer A,
            feeds chronology and other propagation rules.)

        Duplicate edges (same source/target/type) are silently skipped.
        """
        nodes_by_uuid = {n.node_id: n for n in self.graph.nodes}
        original_by_uuid = {v: k for k, v in self.id_mapping.items()}

        edge_type_by_target_cls = {
            "AuthorNode":   "has_author",
            "AuthorAINode": "has_author",
            "LicenseNode":  "has_license",
            "EmbargoNode":  "has_embargo",
            "PropertyNode": "has_property",
        }

        # Pre-compute "claimed" ParadataNodeGroup uuids: any PD group that
        # is the *target* of an incoming has_paradata_nodegroup edge is
        # considered node-level and is skipped here.
        claimed_groups = set()
        for edge in self.graph.edges:
            if edge.edge_type == "has_paradata_nodegroup":
                claimed_groups.add(edge.edge_target)

        def _is_free_pd_group(uuid_id):
            """True if the node is a ParadataNodeGroup with no incoming
            has_paradata_nodegroup AND whose name starts with 'SL_'.
            """
            node = nodes_by_uuid.get(uuid_id)
            if node is None or node.__class__.__name__ != "ParadataNodeGroup":
                return False
            if uuid_id in claimed_groups:
                return False
            name = (getattr(node, "name", "") or "").upper()
            return name.startswith("SL_")

        # --- Step 1: find the containing PD group for every candidate ---
        # A candidate node (AuthorNode/AuthorAINode/LicenseNode/EmbargoNode/
        # PropertyNode) belongs to at most one PD group, via either the XML
        # nesting chain (immediate parent) or an is_in_paradata_nodegroup
        # edge (top-level layout). XML nesting wins if both are present.
        parent_of = self._original_parent_of or {}

        containing_group = {}  # candidate_uuid -> pd_group_uuid
        for node in self.graph.nodes:
            if node.__class__.__name__ not in edge_type_by_target_cls:
                continue
            candidate_original = original_by_uuid.get(node.node_id)
            if candidate_original is None:
                continue
            parent_original = parent_of.get(candidate_original)
            if parent_original is None:
                continue
            parent_uuid = self.id_mapping.get(parent_original)
            if parent_uuid is None:
                continue
            parent_node = nodes_by_uuid.get(parent_uuid)
            if parent_node is not None and parent_node.__class__.__name__ == "ParadataNodeGroup":
                containing_group[node.node_id] = parent_uuid

        for edge in self.graph.edges:
            if edge.edge_type != "is_in_paradata_nodegroup":
                continue
            src_uuid = edge.edge_source
            if src_uuid in containing_group:
                continue  # XML nesting already assigned
            src_node = nodes_by_uuid.get(src_uuid)
            if src_node is None or src_node.__class__.__name__ not in edge_type_by_target_cls:
                continue
            tgt_uuid = edge.edge_target
            tgt_node = nodes_by_uuid.get(tgt_uuid)
            if tgt_node is None or tgt_node.__class__.__name__ != "ParadataNodeGroup":
                continue
            containing_group[src_uuid] = tgt_uuid

        # --- Step 2: find the target node for every free PD group ---
        # Target resolution order:
        #   (a) XML ancestor walk: first non-ParadataNodeGroup ancestor
        #   (b) has_first_epoch outgoing edge from the group
        target_by_group = {}
        free_groups = {g for g in set(containing_group.values()) if _is_free_pd_group(g)}
        for group_uuid in free_groups:
            group_original = original_by_uuid.get(group_uuid)
            target_uuid = None

            # (a) XML ancestor walk
            ancestor_original = parent_of.get(group_original) if group_original else None
            while ancestor_original is not None:
                candidate_uuid = self.id_mapping.get(ancestor_original)
                if candidate_uuid is not None:
                    candidate_node = nodes_by_uuid.get(candidate_uuid)
                    if candidate_node is not None and candidate_node.__class__.__name__ != "ParadataNodeGroup":
                        target_uuid = candidate_uuid
                        break
                ancestor_original = parent_of.get(ancestor_original)

            # (b) has_first_epoch outgoing from the group itself
            if target_uuid is None:
                for edge in self.graph.edges:
                    if edge.edge_source == group_uuid and edge.edge_type == "has_first_epoch":
                        target_uuid = edge.edge_target
                        break

            if target_uuid is not None:
                target_by_group[group_uuid] = target_uuid

        # --- Step 3: emit the auto-edges ---
        existing = {
            (e.edge_source, e.edge_target, e.edge_type) for e in self.graph.edges
        }

        created = 0
        for node in list(self.graph.nodes):
            edge_type = edge_type_by_target_cls.get(node.__class__.__name__)
            if not edge_type:
                continue
            group_uuid = containing_group.get(node.node_id)
            if group_uuid is None or group_uuid not in free_groups:
                continue
            source_uuid = target_by_group.get(group_uuid)
            if source_uuid is None:
                # Canvas-level free group with no Epoch anchor: DP-40
                # attributes already cover it.
                continue

            key = (source_uuid, node.node_id, edge_type)
            if key in existing:
                continue

            try:
                self.graph.add_edge(
                    edge_id=f"{source_uuid}_{edge_type}_{node.node_id}",
                    edge_source=source_uuid,
                    edge_target=node.node_id,
                    edge_type=edge_type,
                )
                existing.add(key)
                created += 1
            except Exception as exc:
                self.graph.add_warning(
                    f"[paradata auto-edge] Could not create "
                    f"{edge_type} from {source_uuid[:8]} to {node.node_id[:8]}: {exc}"
                )

        if created:
            self.graph.add_warning(
                f"[paradata auto-edge] Inferred {created} has_author / "
                f"has_license / has_embargo / has_property edges from "
                f"free (SL_*) paradata groups."
            )

    def _warn_on_epoch_chronology_mismatch(self):
        """Check each EpochNode for a disagreeing pair of declarations.

        Header start/end (``epoch.start_time`` / ``epoch.end_time``) comes
        from the yEd swimlane title; PropertyNode values come from a
        PropertyNode connected via ``has_property`` (typically inside an
        SL_PD, auto-edged by :meth:`_infer_paradata_image_edges`).

        When both are declared AND disagree, the resolver already keeps
        the PropertyNode as the winner (node-level beats swimlane-level);
        this method emits a warning so the user can reconcile the source
        in yEd.
        """
        from ..nodes.epoch_node import EpochNode
        from ..resolvers.builtin_rules import _node_temporal_property

        for n in self.graph.nodes:
            if not isinstance(n, EpochNode):
                continue

            header_start = getattr(n, "start_time", None)
            header_end = getattr(n, "end_time", None)
            prop_start = _node_temporal_property(
                self.graph, n, "absolute_time_start")
            prop_end = _node_temporal_property(
                self.graph, n, "absolute_time_end")

            def _disagree(a, b):
                if a is None or b is None:
                    return False
                try:
                    return float(a) != float(b)
                except (ValueError, TypeError):
                    return False

            if _disagree(header_start, prop_start):
                self.graph.add_warning(
                    f"[chronology mismatch] EpochNode "
                    f"'{getattr(n, 'name', n.node_id)}' has start_time="
                    f"{header_start} from the swimlane header but a "
                    f"PropertyNode 'absolute_time_start'={prop_start} from "
                    f"SL_PD. Resolver prefers the PropertyNode. Reconcile "
                    f"in yEd to remove the warning."
                )
            if _disagree(header_end, prop_end):
                self.graph.add_warning(
                    f"[chronology mismatch] EpochNode "
                    f"'{getattr(n, 'name', n.node_id)}' has end_time="
                    f"{header_end} from the swimlane header but a "
                    f"PropertyNode 'absolute_time_end'={prop_end} from "
                    f"SL_PD. Resolver prefers the PropertyNode. Reconcile "
                    f"in yEd to remove the warning."
                )

    @staticmethod
    def _strip_s3d_marker(text):
        """Remove the round-trip ``_s3d_node_type:<Name>`` marker so that
        the cleaned text is safe to show in UIs as the human description.
        """
        if not text:
            return text
        cleaned = re.sub(
            r"\s*" + re.escape(_S3D_NODE_TYPE_MARKER) + r"[A-Za-z_][A-Za-z0-9_]*\s*",
            " ",
            text,
        )
        return cleaned.strip(" \t\r\n")

    def _create_paradata_image_node(self, detected_type, uuid_id, label_text,
                                    node_description, nodeurl,
                                    original_id, node_uri):
        """Instantiate the correct node class for ``detected_type`` and add
        it to the graph. Returns the created node (or ``None`` for unknown
        types).
        """
        # The ``name`` is kept verbatim from the yEd label (e.g. the
        # short code "A.01" defined by the 1.5 dev9 palette convention).
        # The description is the human-readable content — we strip only
        # the round-trip ``_s3d_node_type:`` marker so it does not leak
        # into UIs.
        clean_name = (label_text or "").strip() or detected_type
        clean_description = self._strip_s3d_marker(node_description)

        if detected_type == "AuthorNode":
            node = AuthorNode(node_id=uuid_id, name=clean_name,
                              description=clean_description)
        elif detected_type == "AuthorAINode":
            node = AuthorAINode(node_id=uuid_id, name=clean_name,
                                description=clean_description)
        elif detected_type == "LicenseNode":
            node = LicenseNode(node_id=uuid_id, name=clean_name,
                               description=clean_description, url=nodeurl)
        elif detected_type == "EmbargoNode":
            node = EmbargoNode(node_id=uuid_id, name=clean_name,
                               description=clean_description)
        else:
            return None

        node.attributes['original_id'] = original_id
        node.attributes['graph_id'] = self.graph.graph_id
        if node_uri:
            node.attributes['URI'] = node_uri
        self.graph.add_node(node)
        return node

    _STRAT_TYPES_CACHE = None

    @classmethod
    def _stratigraphic_types(cls):
        """The stratigraphic node_types, from the datamodel's own classification
        rather than a hand-kept list.

        ``ALL_US_TYPES`` is the canonical set (US, USD, USN, USVn, USVs, SF, VSF,
        RSF, TSU, SE, UL, BR and the four series). ``StratigraphicNode`` is added
        because it is the legacy node_type ``VirtualStratigraphicUnit`` registers
        itself under, and real graphs still carry it. ``unknown`` is deliberately
        NOT here: an UnknownNode is not a stratigraphic unit, and treating it as
        one made the reclassification below fire on nodes it knew nothing about."""
        if cls._STRAT_TYPES_CACHE is None:
            from ..classification import ALL_US_TYPES
            cls._STRAT_TYPES_CACHE = set(ALL_US_TYPES) | {"StratigraphicNode"}
        return cls._STRAT_TYPES_CACHE

    def _reclassify_by_endpoints(self, source_node, target_node, declared):
        """Re-read a mis-typed connector from its endpoints alone.

        First the curated endpoint rules (the same ones a dashed connector goes
        through). If the outcome is still something the datamodel refuses, fall
        back to the datamodel itself: when exactly ONE edge type is admitted
        between those two endpoints, that type is the only possible reading and
        is used. When several are admitted, or none, nothing is invented — the
        declared type is returned and `add_edge` will degrade it with a warning,
        which is the honest outcome for an authorial anomaly."""
        from ..edges.connection_resolver import (candidate_edge_types,
                                                 connection_allowed)
        guess = self.enhance_edge_type("has_data_provenance", source_node, target_node)
        if guess != "has_data_provenance" and connection_allowed(source_node,
                                                                 target_node, guess):
            return guess
        if connection_allowed(source_node, target_node, guess):
            return guess          # the dashed default itself is valid here
        candidates = candidate_edge_types(source_node, target_node)
        if len(candidates) == 1:
            return candidates[0]
        return declared

    def enhance_edge_type(self, edge_type, source_node, target_node):
        """
        Enhances the edge type based on the types of the connected nodes.
        
        Args:
            edge_type (str): The basic edge type from GraphML style.
            source_node (Node): The source node.
            target_node (Node): The target node.
            
        Returns:
            str: The enhanced edge type.
        """
        if not source_node or not target_node:
            return edge_type

        stratigraphic_types = self._stratigraphic_types()

        source_type = source_node.node_type if hasattr(source_node, 'node_type') else ""
        target_type = target_node.node_type if hasattr(target_node, 'node_type') else ""

        # A solid line typed `is_after` whose endpoints are NOT both stratigraphic
        # is a mis-drawn connector, not a stratigraphic relation: yEd carries the
        # style, and the style was wrong. The endpoints tell the truth, so it is
        # re-read through the same endpoint rules as a dashed connector. Valid
        # stratigraphic `is_after` is never touched.
        if edge_type == "is_after" and not (source_type in stratigraphic_types
                                            and target_type in stratigraphic_types):
            return self._reclassify_by_endpoints(source_node, target_node,
                                                 declared="is_after")
        
        # print(f"Enhancing edge type {edge_type}: {source_type} -> {target_type}")

        # Logica per has_data_provenance
        if edge_type == "has_data_provenance":
            # v1.5 dev10 (DP-51): the yEd palette has no dedicated connector
            # style for has_author / has_license / has_embargo, so the generic
            # dashed ``has_data_provenance`` is reclassified here based on the
            # paradata image target. AuthorAINode is a subclass of AuthorNode
            # and is covered by the same branch.
            if isinstance(target_node, AuthorNode):
                edge_type = "has_author"
            elif isinstance(target_node, LicenseNode):
                edge_type = "has_license"
            elif isinstance(target_node, EmbargoNode):
                edge_type = "has_embargo"
            # Se il source è un nodo stratigrafico e il target è una property
            elif source_type in stratigraphic_types and target_type == "property":
                edge_type = "has_property"
                # print(f"Enhanced to has_property: {source_type} -> PropertyNode")

            # Unità stratigrafica collegata a ParadataNodeGroup
            elif source_type in stratigraphic_types and target_type == "ParadataNodeGroup":
                edge_type = "has_paradata_nodegroup"
                # print(f"Enhanced to has_paradata_nodegroup: {source_type} -> ParadataNodeGroup")
            
            # ParadataNodeGroup collegato a unità stratigrafica (direzione invertita)
            elif source_type == "ParadataNodeGroup" and target_type in stratigraphic_types:
                edge_type = "has_paradata_nodegroup"
                # print(f"Enhanced to has_paradata_nodegroup (direzione invertita): ParadataNodeGroup -> {target_type}")

            # ExtractorNode -> DocumentNode
            elif (isinstance(source_node, ExtractorNode) and 
                isinstance(target_node, DocumentNode)):
                edge_type = "extracted_from"
                # print(f"Enhanced to extracted_from: ExtractorNode -> DocumentNode")
                
            # CombinerNode -> ExtractorNode
            elif (isinstance(source_node, CombinerNode) and
                isinstance(target_node, ExtractorNode)):
                edge_type = "combines"
                # print(f"Enhanced to combines: CombinerNode -> ExtractorNode")

            # DocumentNode -> PropertyNode: the document's own property (its
            # dating, `absolute_time_start` drawn beside a master document),
            # the reading `_enrich_canonical_documents` already gives it.
            # Measured on Templu Mare (4 Oct 2026): five of these came out
            # generic_connection and reached the room that way.
            elif (isinstance(source_node, DocumentNode)
                  and isinstance(target_node, PropertyNode)):
                edge_type = "has_property"

            # PropertyNode -> DocumentNode. BUGFIX-CONN3: this is read as
            # has_documentation (P70i_is_documented_in) — the honest shortcut
            # when a legacy yEd dashed connector links a property to a source
            # document. It is NO LONGER has_visual_reference: CONN2 moved that to
            # PropertyNode->ResourceNode (a visual reference illustrates via an image
            # resource, not a source document). has_documentation.source was
            # widened to include PropertyNode for exactly this reading (v1.6.7).
            elif (isinstance(source_node, PropertyNode)
                  and isinstance(target_node, DocumentNode)):
                edge_type = "has_documentation"

            # CombinerNode / bare ParadataNode -> DocumentNode. BUGFIX-CONN3:
            # there is no honest single relation here — a combiner aggregates
            # extractors and cites no document, and the modern evidence path is
            # the DTC chain (property<-combiner<-extractor->document), which the
            # importer cannot synthesise. Rather than assert a relation the model
            # does not support (and NOT the now-illegal has_visual_reference), the
            # edge is left as a generic_connection with a warning so the author
            # can reclassify it; the import stays non-destructive.
            elif (isinstance(source_node, (CombinerNode, ParadataNode))
                  and isinstance(target_node, DocumentNode)):
                self.graph.add_warning(
                    f"{source_type} -> DocumentNode has no single datamodel "
                    f"relation (a combiner/paradata does not 'document' a "
                    f"source); left as generic_connection — reclassify if needed."
                )
                edge_type = "generic_connection"
        
        # Post-processing per generic_connection
        elif edge_type == "generic_connection":
            # ✅ v1.5.3: StratigraphicNode -> DocumentNode = has_documentation
            if (source_type in stratigraphic_types and
                isinstance(target_node, DocumentNode)):
                edge_type = "has_documentation"
                # print(f"Enhanced to has_documentation: {source_type} -> DocumentNode")

            # ✅ v1.5.3: DocumentNode -> StratigraphicNode = is_documentation_of (reverse)
            elif (isinstance(source_node, DocumentNode) and
                  target_type in stratigraphic_types):
                edge_type = "is_documentation_of"
                # print(f"Enhanced to is_documentation_of: DocumentNode -> {target_type}")

            # StratigraphicNode → ParadataNodeGroup = has_paradata_nodegroup
            elif (source_type in stratigraphic_types and
                  target_type == "ParadataNodeGroup"):
                edge_type = "has_paradata_nodegroup"

            # PropertyNode → ParadataNodeGroup = is_in_paradata_nodegroup
            elif (source_type == "property" and
                  target_type == "ParadataNodeGroup"):
                edge_type = "is_in_paradata_nodegroup"

            # Nodi ParadataNode (e sottoclassi) collegati a ParadataNodeGroup
            elif (isinstance(source_node, (DocumentNode, ExtractorNode, CombinerNode, ParadataNode)) and
                target_type == "ParadataNodeGroup"):
                edge_type = "is_in_paradata_nodegroup"
                # print(f"Enhanced to is_in_paradata_nodegroup: {source_type} -> ParadataNodeGroup")
            
            # ParadataNodeGroup collegato a ActivityNodeGroup
            elif source_type == "ParadataNodeGroup" and target_type == "ActivityNodeGroup":
                edge_type = "has_paradata_nodegroup"
                # print(f"Enhanced to has_paradata_nodegroup: ParadataNodeGroup -> ActivityNodeGroup")
            
            # Puoi aggiungere altre regole specifiche qui

        return edge_type

    def EM_extract_edge_type(self, edge):
        """
        Extracts the basic semantic type of the edge from the GraphML line style.

        Note: For stratigraphic relations, "is_after" is now used as the canonical direction.
        In v1.5.3+, "is_after" (source more recent than target) is canonical,
        while "is_before" (source older than target) is the reverse direction.

        GraphML convention in Extended Matrix has arrows pointing from recent to ancient:
        - Source node = more recent unit (positioned higher in the matrix)
        - Target node = more ancient unit (positioned lower in the matrix)
        - Visual arrow = points downward (from recent to ancient)

        This matches perfectly with "is_after" canonical direction, so no reversal is needed.

        Args:
            edge_element (Element): XML element for the edge.

        Returns:
            str: The edge type representing the semantic relationship.
        """
        edge_type = "generic_connection"  # Default edge type

        # Use dynamic key mapping instead of hardcoded "d10"
        edge_graphics_key = self.key_map.get('edge', {}).get('edgegraphics', 'd10')
        ns = 'http://graphml.graphdrawing.org/xmlns'
        data_element = edge.find(f'./{{{ns}}}data[@key="{edge_graphics_key}"]')

        if data_element is not None:
            # Extract graphical line style and map it to a semantic relationship
            line_style = data_element.find('.//{http://www.yworks.com/xml/graphml}LineStyle')
            if line_style is not None:
                style_type = line_style.attrib.get("type")
                # Map each graphical style to its semantic meaning
                if style_type == "line":
                    # v1.5.3: Use canonical "is_after" direction (recent → ancient)
                    # GraphML already has source=recent, target=ancient (arrow points down)
                    # This matches the canonical direction perfectly, no reversal needed
                    edge_type = "is_after"
                elif style_type == "double_line":
                    edge_type = "has_same_time"
                elif style_type == "dotted":
                    edge_type = "changed_from"
                elif style_type == "dashed":
                    edge_type = "has_data_provenance"
                elif style_type == "dashed_dotted":
                    edge_type = "contrasts_with"
                else:
                    edge_type = "generic_connection"

        return edge_type


    # Funzioni di utilità

    def _check_node_type(self, node_element):
        id_node = str(node_element.attrib)
        if "yfiles.foldertype" in id_node:
            tablenode = node_element.find('.//{http://www.yworks.com/xml/graphml}TableNode')
            if tablenode is not None:
                return 'node_swimlane'
            else:
                return 'node_group'
        else:
            return 'node_simple'

    def estrai_stringa_e_vocabolario(self, s):
        match = re.search(r'\[(.*?)\]', s)
        vocabolario = {}
        if match:
            contenuto = match.group(1)
            coppie = contenuto.split(';')
            for coppia in coppie:
                coppia = coppia.strip()
                if not coppia:
                    continue
                if ':' in coppia:
                    parti = coppia.split(':', 1)
                    if len(parti) != 2 or not parti[0] or not parti[1]:
                        raise ValueError(f"Coppia chiave:valore malformata: '{coppia}'")
                    chiave, valore = parti
                    chiave = chiave.strip()
                    valore = valore.strip()
                    try:
                        valore = int(valore)
                    except ValueError:
                        pass
                    vocabolario[chiave] = valore
                else:
                    raise ValueError(f"Coppia senza separatore ':': '{coppia}'")
            stringa_pulita = re.sub(r'\[.*?\]', '', s).strip()
        else:
            stringa_pulita = s.strip()
        return stringa_pulita, vocabolario

    def clean_comments(self, multiline_str):
        newstring = ""
        for line in multiline_str.splitlines():
            if line.startswith("«") or line.startswith("#"):
                pass
            else:
                newstring += line + " "
        return newstring.strip()

    def getnode_id(self, node_element):
        return str(node_element.attrib['id'])

    def _check_if_empty(self, name):
        return name if name is not None else ""

    # Aggiungi ulteriori metodi di supporto se necessario

import json
import os
from typing import List, Dict, Any, Optional
from ..graph import Graph
from .emjson_exporter import CALCULATED_KEYS
from ..multigraph.multigraph import get_all_graph_ids, get_graph

class JSONExporter:
    """
    Export s3Dgraphy graphs to JSON format.
    Supports exporting single graphs or multiple graphs with context.
    """
    
    def __init__(self, output_path: str):
        """
        Initialize the JSON exporter.
        
        Args:
            output_path (str): Path where the JSON file will be saved
        """
        self.output_path = output_path
        self.context = self._init_context()
        
    def _init_context(self) -> Dict[str, Any]:
        """Initialize the context section with default time Epochs."""
        return {
            "absolute_time_Epochs": {
                "roman_kingdom": {
                    "name": "Epoca regia romana",
                    "start": -753,
                    "end": -509,
                    "color": "#FFD700"
                },
                "roman_republic": {
                    "name": "Epoca repubblicana romana",
                    "start": -509,
                    "end": -27,
                    "color": "#CD5C5C"
                },
                "roman_empire": {
                    "name": "Epoca imperiale romana",
                    "start": -27,
                    "end": 476,
                    "color": "#800020"
                },
                "early_middle_ages": {
                    "name": "Alto Medioevo",
                    "start": 476,
                    "end": 1000,
                    "color": "#4B0082"
                }
            }
        }



    def export_graphs(self, graph_ids: Optional[List[str]] = None) -> None:
        """
        Export specified graphs to JSON. If no graph_ids provided, exports all graphs.
        
        Args:
            graph_ids (List[str], optional): List of graph IDs to export. Defaults to None.
        """
        if graph_ids is None:
            graph_ids = get_all_graph_ids()
                
        # Schema version 1.6 (lossless): preserves edge.attributes /
        # edge.edge_type, PropertyNode.value/property_type/units,
        # ExtractorNode.source, EpochNode.fill_color,
        # RepresentationModelNode.url, StratigraphicNode class-level
        # symbol/label/detailed_description, every node.attributes dict,
        # and the full graph.data payload (previously only 4 keys).
        # 1.6 is a strict superset of 1.5: all 1.5 fields remain.
        export_data = {
            "version": "1.6",
            "graphs": {}
        }
            
        for graph_id in graph_ids:
            graph = get_graph(graph_id)
            if graph and hasattr(graph, 'graph_id'):
                # Usa l'ID effettivo del grafo come chiave
                actual_id = graph.graph_id  # 
                #print(f"Exporting graph with ID: {actual_id}")
                export_data["graphs"][actual_id] = self._process_graph(graph)
                
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=4, ensure_ascii=False)

    def _process_graph(self, graph: Graph) -> Dict[str, Any]:
        """Process a single graph into its JSON representation."""

        # The Heriverse payload is a DISSEMINATION surface: a deleted US must
        # be ABSENT from the scene, not marked in it. Filtered once here, at
        # the entrance, so every pass below (nodes, edges, and the
        # ``has_linked_resource`` scan inside ``_process_nodes``) sees the same
        # live graph. Policy and predicate: ``s3dgraphy.dissemination``.
        from ..dissemination import live_view
        graph, _hidden = live_view(graph, surface="heriverse")


        #print(f"\nProcessing graph for JSON export:")
        #print(f"Graph name: {graph.name}")
        #print(f"Graph description: {graph.description}")
        #print(f"Graph data: {graph.data}")

        # Raccogli gli ID degli autori dal grafo
        authors = graph.data.get('authors', [])
        if not authors:
            # Se non ci sono autori in graph.data, cerca negli edges
            for edge in graph.edges:
                if edge.edge_type in ['has_author', 'generic_connection']:
                    if edge.edge_target == graph.graph_id:
                        author_node = graph.find_node_by_id(edge.edge_source)
                        if author_node and author_node.node_type == 'author':
                            authors.append(edge.edge_source)
                            #print(f"Found author from edge: {edge.edge_source}")

        # Build the ``defaults`` block as a strict superset of the 1.5
        # schema: the four well-known keys keep their previous shape and
        # defaults (so a 1.5 reader still finds what it expects), then
        # every remaining key from ``graph.data`` is folded in so the
        # export is lossless. Known keys are not overwritten by raw
        # ``graph.data`` values because they already carry the 1.5
        # defaults (e.g. license falls back to 'CC-BY-NC-ND').
        defaults = {
            "license": graph.data.get('license', 'CC-BY-NC-ND'),
            "authors": authors,
            "embargo_until": graph.data.get('embargo_until'),
            "panorama": graph.data.get('panorama', 'panorama/defsky.jpg')
        }
        if isinstance(graph.data, dict):
            for key, value in graph.data.items():
                if key not in defaults:
                    defaults[key] = value

        result = {
            "name": graph.name.get('default', ''),
            "description": graph.description.get('default', ''),
            "defaults": defaults,
            "nodes": self._process_nodes(graph),
            "edges": self._process_edges(graph)
        }
        
        #print(f"\nJSON output for graph metadata:")
        #print(f"Name: {result['name']}")
        #print(f"Description: {result['description']}")
        #print(f"Defaults: {result['defaults']}")
        
        return result

        
    def _process_nodes(self, graph: Graph) -> Dict[str, Dict[str, Any]]:
        """Process all nodes in the graph, organizing them by type."""
        nodes = {
            # ``authors`` carries both human (AuthorNode → node_type
            # "author") and AI-authored agents (AuthorAINode →
            # node_type "author_ai"). Downstream consumers distinguish
            # by the ``type`` field inside each entry. AuthorAINode's
            # extra data fields (``model`` / ``prompt_reference``) flow
            # through ``node.data.copy()`` automatically.
            "authors": {},
            "stratigraphic": {"US": {}, "USVs": {}, "SF": {}, "VSF": {}, "RSF": {}, "USVn": {}, "USD": {}, "serSU": {}, "serUSVn": {}, "serUSVs": {}, "serUSD": {}, "TSU": {}, "UL": {}, "USN": {}, "USNt": {}, "BR": {}, "SE": {}, "unknown": {}},
            "epochs": {},
            "groups": {},
            # LocationNodeGroup is a spatial / locational membership
            # container (toponym / study / functional). It is orthogonal
            # to ActivityNodeGroup (intention) and EpochNode (time), so it
            # gets its own bucket instead of being lumped into ``groups``.
            # See nodes/group_node.py for the CIDOC-CRM mapping.
            "location_node_groups": {},
            "properties": {},
            "documents": {},
            "extractors": {},
            "combiners": {},
            # New paradata-image buckets to mirror AuthorNode: they
            # already get emitted as has_license / has_embargo edges,
            # so the target nodes need a concrete home in the JSON.
            "licenses": {},
            "embargoes": {},
            "links": {},
            "geo": {},
            "semantic_shapes": {},
            "representation_models": {},
            "representation_model_doc": {},
            "representation_model_sf": {},
            # EM16-RMNG: the named sets of representation models (RM
            # containers). Its own bucket, for the same reason
            # `location_node_groups` got one: a consumer that groups models by
            # container should not have to tell it apart from an activity or a
            # time branch inside a shared "groups" dict. Empty on every graph
            # that has no containers, so nothing changes for existing readers.
            "representation_model_groups": {}
        }
        
        # R4 (13/14-09-2026) · qui c'era `rm_links`, una mappa RM → risorse
        # costruita attraversando ogni arco `has_linked_resource`.
        #
        # È stata tolta, e la ragione è più forte di «nessuno la legge»:
        # **non veniva scritta da nessuna parte.** Era una variabile locale
        # riempita e poi buttata via — un giro completo su tutti gli archi a
        # ogni export, il cui unico effetto era il tempo che costava. Chi
        # sospettava che Heriverse la aspettasse aveva un dubbio ragionevole e
        # una risposta sbagliata: Heriverse prende il modello attraversando
        # `has_linked_resource` (`src/Heriverse.js`), che è il modo nativo del
        # grafo, e quella mappa non è mai arrivata in nessun project.json.
        #
        # Scriverla adesso darebbe due fonti per lo stesso fatto, destinate a
        # divergere alla prima modifica di una delle due (decisione 16).

        # Ora elabora tutti i nodi
        for node in graph.nodes:
            # Gestisci ogni tipo di nodo in modo specifico
            if node.node_type in ("author", "author_ai"):
                # AuthorAINode (node_type "author_ai") is a subclass of
                # AuthorNode; both go into the same bucket. The ``type``
                # field inside the entry keeps the distinction.
                node_data = self._prepare_node_data(node)
                nodes["authors"][node.node_id] = node_data

            elif node.node_type == "license":
                node_data = self._prepare_node_data(node)
                nodes["licenses"][node.node_id] = node_data

            elif node.node_type == "embargo":
                node_data = self._prepare_node_data(node)
                nodes["embargoes"][node.node_id] = node_data

            elif node.node_type in ["US", "USVs", "SF", "USVn", "USD", "VSF", "RSF", "serSU", "serUSVn", "serUSVs", "serUSD", "TSU", "UL", "USN", "USNt", "BR", "SE", "unknown"]:
                node_data = self._prepare_node_data(node)
                nodes["stratigraphic"][node.node_type][node.node_id] = node_data
                
            elif node.node_type == "EpochNode":
                # EpochNode keeps its hand-rolled ``data`` block (which is
                # the 1.5 shape downstream consumers expect) but now also
                # carries:
                #   * ``attributes`` — full base attributes dict, so
                #     ``fill_color`` (set by the GraphML importer) and
                #     any future importer-side metadata survive.
                #     (perdite 5 + 8)
                #   * top-level ``fill_color`` — convenience mirror so
                #     readers don't have to dig into ``attributes``.
                epoch_attributes = dict(
                    getattr(node, "attributes", {}) or {}
                )
                node_data = {
                    "type": node.node_type,
                    "name": node.name,
                    "description": node.description,
                    "data": {
                        "start_time": node.start_time if hasattr(node, 'start_time') else None,
                        "end_time": node.end_time if hasattr(node, 'end_time') else None,
                        "color": node.color if hasattr(node, 'color') else None,
                        "min_y": node.min_y if hasattr(node, 'min_y') else None,
                        "max_y": node.max_y if hasattr(node, 'max_y') else None
                    },
                    "attributes": epoch_attributes,
                    "fill_color": epoch_attributes.get("fill_color"),
                }
                nodes["epochs"][node.node_id] = node_data
                
            elif node.node_type in ["ActivityNodeGroup", "TimeBranchNodeGroup", "ParadataNodeGroup"]:
                node_data = self._prepare_node_data(node)
                nodes["groups"][node.node_id] = node_data

            elif node.node_type == "LocationNodeGroup":
                # LocationNodeGroup nodes were previously silently dropped
                # from the Heriverse JSON export because the elif chain had
                # no branch for them. The fix is conservative: prepare the
                # node like any other group, but write it to its own
                # ``location_node_groups`` bucket so downstream consumers
                # (e.g. the WebGL viewer) can treat spatial membership
                # distinctly from activity / time-branch / paradata groups.
                # ``kind`` and ``propagation`` flow through via
                # ``node.data`` / ``node.attributes`` automatically.
                node_data = self._prepare_node_data(node)
                nodes["location_node_groups"][node.node_id] = node_data

            elif node.node_type == "RepresentationModelNodeGroup":
                # EM16-RMNG. Same shape as the LocationNodeGroup branch just
                # above, and added for the same reason it was: without a branch
                # of its own the node falls off the end of this elif chain and
                # is SILENTLY DROPPED from the export. A group is written even
                # when it is empty and even when no Document points at it —
                # both are legal states of a container (the "grey" one the RM
                # Manager already shows), and a reader is better served by an
                # empty named set than by its absence.
                node_data = self._prepare_node_data(node)
                nodes["representation_model_groups"][node.node_id] = node_data

            elif node.node_type == "property":
                node_data = self._prepare_node_data(node)
                nodes["properties"][node.node_id] = node_data
                
            elif node.node_type == "document":
                node_data = self._prepare_node_data(node)
                nodes["documents"][node.node_id] = node_data
                
            elif node.node_type == "extractor":
                node_data = self._prepare_node_data(node)
                nodes["extractors"][node.node_id] = node_data
                
            elif node.node_type == "combiner":
                node_data = self._prepare_node_data(node)
                nodes["combiners"][node.node_id] = node_data
                
            elif node.node_type == "resource":
                node_data = self._prepare_node_data(node)
                nodes["links"][node.node_id] = node_data
                #print(f"Added link node to JSON: {node.node_id}")
                
            elif node.node_type == "geo_position":
                node_data = self._prepare_node_data(node)
                nodes["geo"][node.node_id] = node_data
                
            elif node.node_type == "semantic_shape":
                node_data = self._prepare_node_data(node)
                # connections 1.6.28 · the proxy's .glb is a proxy_model
                # RESOURCE, no longer the shape's own url. Heriverse loads a
                # proxy from `semantic_shapes[id].data.url` (Heriverse.js,
                # createSemanticNodeFromShape), so this surface PROJECTS the
                # resource's path back there: a derived copy for the viewer,
                # the graph keeps one home for it.
                if not node_data["data"].get("url"):
                    from ..geometry.proxy import linked_proxy_resources
                    linked = linked_proxy_resources(graph, node.node_id)
                    url = (getattr(linked[0], "data", None) or {}).get("url") if linked else None
                    if url:
                        node_data["data"]["url"] = url
                nodes["semantic_shapes"][node.node_id] = node_data
                
            elif node.node_type == "representation_model":
                # Schema 1.6: stop stripping ``url`` from the
                # RepresentationModelNode export (perdita 6). The
                # previous behaviour silently dropped the 3D asset
                # pointer, making the JSON un-rehydratable. We now go
                # through the standard ``_prepare_node_data`` path so
                # ``url`` (whether on ``node.data`` or
                # ``node.attributes``) round-trips, alongside the new
                # base ``attributes`` catch-all.
                node_data = self._prepare_node_data(node)
                nodes["representation_models"][node.node_id] = node_data

            elif node.node_type == "representation_model_doc":
                # Prepare the node data similar to other types
                node_data = self._prepare_node_data(node)
                
                # Add the node to the collection
                nodes["representation_model_doc"][node.node_id] = node_data

            elif node.node_type == "representation_model_sf":
                # Prepare the node data similar to other types
                node_data = self._prepare_node_data(node)
                
                # Add the node to the collection
                nodes["representation_model_sf"][node.node_id] = node_data

        return nodes

    # Stratigraphic subtype node_types whose class-level
    # ``symbol`` / ``label`` / ``detailed_description`` (declared on the
    # subclass, not the instance) used to vanish on export. We enumerate
    # the public node_type strings so the test stays in sync with
    # ``_process_nodes``' stratigraphic branch.
    _STRATIGRAPHIC_NODE_TYPES = frozenset({
        "US", "USVs", "SF", "VSF", "RSF", "USVn", "USD",
        "serSU", "serUSVn", "serUSVs", "serUSD",
        "TSU", "UL", "USN", "USNt", "BR", "SE", "unknown",
    })

    def _prepare_node_data(self, node):
        """Helper method to prepare standard node data.

        As of schema 1.6 this helper is the central catch-all for
        lossless export. On top of the 1.5 fields
        (``type`` / ``name`` / ``description`` / ``data``) it also emits:

        * ``attributes`` — every ``node.attributes`` dict (perdita 8),
          which carries importer-side metadata such as ``units`` for
          PropertyNode or ``fill_color`` for EpochNode.
        * Type-specific attributes that live directly on the instance
          (not inside ``data``) and were therefore dropped by the
          previous ``data.copy()``-only path:
            - PropertyNode → ``value``, ``property_type``  (perdita 2)
              plus ``units`` lifted from ``attributes`` (perdita 3)
            - ExtractorNode → ``source``                    (perdita 4)
            - StratigraphicNode subclasses → class-level
              ``symbol`` / ``label`` / ``detailed_description``
              (perdita 7)
        """
        node_data = {
            "type": node.node_type,
            "name": node.name,
            "description": node.description,
            "data": node.data.copy() if hasattr(node, 'data') else {},
            # Base catch-all: every importer that stashes metadata on
            # ``node.attributes`` now round-trips through JSON 1.6 — except
            # the computed chronology (CALCUL_*), which is derived state and
            # never part of an export (emjson_exporter.CALCULATED_KEYS).
            "attributes": {k: v for k, v in (getattr(node, "attributes", {}) or {}).items()
                           if k not in CALCULATED_KEYS},
        }

        # PropertyNode — value / property_type are instance attrs, units
        # is stored under ``attributes`` by the unified xlsx importer.
        if node.node_type == "property":
            node_data["value"] = getattr(node, "value", None)
            node_data["property_type"] = getattr(node, "property_type", None)
            node_data["units"] = node_data["attributes"].get("units")

        # ExtractorNode — ``source`` is a first-class instance attribute.
        elif node.node_type == "extractor":
            node_data["source"] = getattr(node, "source", None)

        # StratigraphicNode subtypes — ``symbol`` / ``label`` /
        # ``detailed_description`` are declared on the subclass body.
        # ``getattr`` on an instance returns the class-level default
        # when no instance override exists, which is exactly what we
        # want here.
        if node.node_type in self._STRATIGRAPHIC_NODE_TYPES:
            node_data["symbol"] = getattr(node, "symbol", None)
            node_data["label"] = getattr(node, "label", None)
            node_data["detailed_description"] = getattr(
                node, "detailed_description", None
            )

        return node_data
        
    def _process_edges(self, graph: Graph) -> Dict[str, List[Dict[str, Any]]]:
        """Process all edges in the graph, organizing them by type.

        The bucket set is built from the canonical source of truth —
        ``JSON_config/s3Dgraphy_connections_datamodel.json`` — via the
        :class:`ConnectionsDatamodel` singleton. Both canonical edge
        names (e.g. ``bonded_to``, ``equals``, ``has_first_epoch``) and
        their non-symmetric reverses (e.g. ``is_before`` as the reverse
        of ``is_after``) are pre-initialised so the serializer never
        drops an edge silently. A ``generic_connection`` fallback is
        kept for any edge type that slipped in outside the datamodel.
        """
        from ..edges.connections_loader import get_connections_datamodel

        datamodel = get_connections_datamodel()
        edges: Dict[str, List[Dict[str, Any]]] = {
            name: [] for name in datamodel.get_all_edge_names(canonical_only=False)
        }
        edges.setdefault("generic_connection", [])

        for edge in graph.edges:
            # Schema 1.6: edges now carry their full payload.
            #   * ``edge_type`` is added explicitly so a future reader
            #     can rebuild the typed Edge without inferring the type
            #     from the bucket key (1.5 omitted the type entirely).
            #   * ``attributes`` preserves the per-edge metadata dict
            #     (AUTHOR_n / AUTHOR_KIND_n / DOCUMENT_n etc.) that the
            #     stratigraphic importers attach. This was perdita 1
            #     and the single most damaging silent drop in 1.5.
            edge_data = {
                "id": edge.edge_id,
                "from": edge.edge_source,
                "to": edge.edge_target,
                "edge_type": edge.edge_type,
                "attributes": dict(getattr(edge, "attributes", {}) or {}),
            }

            # Add edge to appropriate category
            if edge.edge_type in edges:
                edges[edge.edge_type].append(edge_data)
            else:
                # Log unknown edge types for debugging
                print(f"WARNING: Unknown edge type '{edge.edge_type}' for edge {edge.edge_id} ({edge.edge_source} -> {edge.edge_target})")
                edges["generic_connection"].append(edge_data)

        return edges


def export_to_json(output_path: str, graph_ids: Optional[List[str]] = None) -> None:
    """
    Convenience function to export graphs to JSON.
    
    Args:
        output_path (str): Path where to save the JSON file
        graph_ids (List[str], optional): List of graph IDs to export. If None, exports all graphs.
    """
    exporter = JSONExporter(output_path)
    exporter.export_graphs(graph_ids)

# s3Dgraphy/graph.py

"""
Graph module for s3Dgraphy, responsible for managing nodes and edges in the knowledge graph.
"""

import json
import os
from .nodes.base_node import Node
from .nodes.epoch_node import EpochNode
from .nodes.stratigraphic_node import StratigraphicNode
from .nodes.property_node import PropertyNode
from .nodes.geo_position_node import GeoPositionNode
from .edges import Edge, get_connections_datamodel
from typing import List
from .indices import GraphIndices


# Connection rules are managed via s3Dgraphy_connections_datamodel.json
# (loaded by edges/connections_loader.py)
_connections_datamodel = get_connections_datamodel()

class Graph:
    """
    Class representing a graph containing nodes and edges.

    Attributes:
        graph_id (str): Unique identifier for the graph.
        name (dict): Dictionary of graph name translations.
        description (dict): Dictionary of graph description translations.
        audio (dict): Dictionary of audio file lists by language.
        video (dict): Dictionary of video file lists by language.
        data (dict): Additional metadata like geographical position.
        nodes (List[Node]): List of nodes in the graph.
        edges (List[Edge]): List of edges in the graph.
        warnings (List[str]): List to accumulate warning messages during operations.
    """

    def __init__(self, graph_id, name=None, description=None, audio=None, video=None, data=None):
        self.graph_id = graph_id
        self.name = name if name is not None else {}
        self.description = description if description is not None else {}
        self.audio = audio if audio is not None else {}
        self.video = video if video is not None else {}
        self.data = data if data is not None else {}
        self.nodes = []
        self.edges = []
        self.warnings = []
        #: Structured counterpart of the state warnings —
        #: ``{kind, node_id, message}`` records, filled by
        #: ``edges.connection_resolver.recompute_warnings`` at load. Empty until
        #: then: warnings are a function of the graph's state, derived on
        #: demand, never persisted. Only the state families have records; a
        #: free-form warning appended via :meth:`add_warning` lives in
        #: ``warnings`` alone, because nothing here knows what it points at.
        self.warning_records = []
        self.attributes = {}

        # Initialize graph indices
        self._indices = None
        self._indices_dirty = True

        # Initialize and add geo_position node if not already present
        if not any(node.node_type == "geo_position" for node in self.nodes):
            geo_node = GeoPositionNode(node_id=f"geo_{graph_id}")
            self.add_node(geo_node, overwrite=True)

    @property
    def indices(self):
        """Lazy loading degli indici con rebuild automatico se necessario"""
        if self._indices is None:
            self._indices = GraphIndices()
        if self._indices_dirty:
            self._rebuild_indices()
        return self._indices
    
    def _rebuild_indices(self):
        """Ricostruisce gli indici del grafo"""
        if self._indices is None:
            self._indices = GraphIndices()

        self._indices.clear()

        # ✅ OPTIMIZATION: Use add_node() which populates both node_id and type indices
        for node in self.nodes:
            self._indices.add_node(node)

            # Indicizzazione speciale per property nodes
            node_type = getattr(node, 'node_type', None)
            if node_type == 'property' and hasattr(node, 'name'):
                self._indices.add_property_node(node.name, node)
        
        # Indicizza edges
        for edge in self.edges:
            self._indices.add_edge(edge)

            # Indicizzazione speciale per has_property edges
            # ✅ FIX: Use newly built index instead of find_node_by_id() to avoid recursion
            if edge.edge_type == 'has_property':
                source_node = self._indices.nodes_by_id.get(edge.edge_source)
                target_node = self._indices.nodes_by_id.get(edge.edge_target)
                if source_node and target_node and hasattr(target_node, 'name'):
                    prop_value = getattr(target_node, 'description', 'empty')
                    self._indices.add_property_relation(
                        target_node.name,
                        edge.edge_source,
                        prop_value
                    )
        
        self._indices_dirty = False


    @staticmethod
    def validate_connection(source_node_type, target_node_type, edge_type):
        """
        Validates if a connection type between two nodes is allowed by the rules.

        The connections datamodel is the only authority: an edge is allowed when
        both endpoints are instances of the classes its ``allowed_connections``
        name (inheritance included, so ``StratigraphicUnit`` satisfies
        ``StratigraphicNode``).

        Two DIFFERENT lookups are involved and must not be conflated — that
        conflation was the bug this method used to carry. The endpoints arrive as
        **node_type** strings (``US``, ``extractor``) and resolve through
        ``Node.node_type_map``, which is keyed by node_type. The datamodel's
        allowed entries are **class names** (``StratigraphicNode``,
        ``SpecialFindUnit``) and resolve through
        :func:`~s3dgraphy.edges.connection_resolver.resolve_node_class`, which
        scans the registered classes and their MRO. Resolving the class names
        through the node_type map instead made every unmatched name fall back to
        ``object`` (accepting anything) and — worse — made
        ``"StratigraphicNode"`` resolve to ``VirtualStratigraphicUnit``, whose
        node_type happens to be that string: so ``is_after`` between two REAL
        stratigraphic units was refused and :meth:`add_edge` rewrote it to
        ``generic_connection``. Fourteen edge types — the whole stratigraphic
        vocabulary — were affected.

        Args:
            source_node_type (str): The type of the source node.
            target_node_type (str): The type of the target node.
            edge_type (str): The type of edge connecting the nodes.

        Returns:
            bool: True if the connection is allowed, False otherwise. An unknown
            node_type or an unknown edge type is refused.
        """
        from .edges.connection_resolver import connection_allowed_by_type
        return connection_allowed_by_type(source_node_type, target_node_type,
                                          edge_type)

    def add_state_warning(self, kind, node_id, message, **extra):
        """Append a warning that KNOWS what it is about.

        The plain :meth:`add_warning` takes a sentence and nothing else, so a UI
        can show it but not act on it. A producer that has the element in hand —
        the GraphML importer, mid-parse — should say so: the record is what lets
        a panel offer "go and look at it" (click-to-node), and it costs one
        argument. ``kind`` comes from
        ``edges.connection_resolver.WARNING_KINDS``.
        """
        self.warnings.append(message)
        record = {"kind": kind, "node_id": node_id, "message": message}
        record.update({k: v for k, v in extra.items() if v is not None})
        self.warning_records.append(record)
        return record

    def add_warning(self, message):
        """Adds a warning message to the warnings list."""
        self.warnings.append(message)

    def add_node(self, node: Node, overwrite=False) -> Node:
        """Adds a node to the graph."""
        existing_node = self.find_node_by_id(node.node_id)
        if existing_node:
            if overwrite:
                self.nodes.remove(existing_node)
                self.add_warning(f"Node '{node.node_id}' overwritten.")
            else:
                return existing_node
        self.nodes.append(node)
        self._indices_dirty = True  # ← Aggiunto per invalidare gli indici
        return node

    def add_edge(self, edge_id: str, edge_source: str, edge_target: str, edge_type: str) -> Edge:
        """
        Adds an edge to the graph with connection validation.

        Args:
            edge_id (str): Unique ID of the edge.
            edge_source (str): Source node ID.
            edge_target (str): Target node ID.
            edge_type (str): Type of edge, must be defined in the connection rules.

        Returns:
            Edge: The added edge.

        Raises:
            ValueError: If the source or target node does not exist or if the edge is a duplicate.
        """
        source_node = self.find_node_by_id(edge_source)
        target_node = self.find_node_by_id(edge_target)
        
        if not source_node or not target_node:
            raise ValueError(f"Both nodes with IDs '{edge_source}' and '{edge_target}' must exist.")

        # Validate connection using connection rules
        if not self.validate_connection(source_node.node_type, target_node.node_type, edge_type):
            self.add_warning(f"Connection '{edge_type}' not allowed between '{source_node.node_type}' (name:{source_node.name}) and '{target_node.node_type}' (name:'{target_node.name}'). Using 'generic_connection' instead.")
            edge_type = "generic_connection"

        if self.find_edge_by_id(edge_id):
            raise ValueError(f"An edge with ID '{edge_id}' already exists.")

        edge = Edge(edge_id, edge_source, edge_target, edge_type)
        self.edges.append(edge)
        self._indices_dirty = True  # ← Aggiunto per invalidare gli indici
        return edge

    def connect_paradatagroup_propertynode_to_stratigraphic(self, verbose=False):
        """
        Identifica le relazioni tra unità stratigrafiche e ParadataNodeGroup,
        poi collega direttamente le unità stratigrafiche ai PropertyNode 
        contenuti nel ParadataNodeGroup.
        
        Questa funzione permette due modalità di collegamento:
        1. Collegamento diretto: Unità Stratigrafica -> PropertyNode
        (modalità già supportata nel codice esistente)
        2. Collegamento indiretto: Unità Stratigrafica -> ParadataNodeGroup -> PropertyNode
        In questo caso, crea anche collegamenti diretti tra Unità Stratigrafica e PropertyNode
        
        Il risultato è una rete semantica più ricca, dove ogni unità stratigrafica
        può accedere direttamente alle sue proprietà, indipendentemente dalla
        struttura organizzativa scelta dall'utente (collegamento diretto o tramite gruppo).
        
        Args:
            verbose (bool): Se True, stampa messaggi dettagliati durante l'esecuzione.
                        Utile per debug. Default: True
        
        Returns:
            dict: Statistiche sulle operazioni eseguite (gruppi analizzati, collegamenti creati, ecc.)
        """
        if verbose:
            pass
            # print("\n=== Connessione PropertyNode dai ParadataNodeGroup alle Unità Stratigrafiche ===")

        # Inizializza statistiche
        stats = {
            "paradata_groups_found": 0,
            "property_nodes_found": 0,
            "stratigraphic_nodes_found": 0,
            "connections_created": 0,
            "connections_already_existing": 0,
            "errors": 0,
            # how many times the LEGACY generic_connection branch had to guess —
            # non-zero means the graph was imported with the pre-Se1 resolver
            "legacy_generic_guesses": 0,
        }
        
        # Definisci i tipi di unità stratigrafiche riconosciuti
        stratigraphic_types = ['US', 'USVs', 'SF', 'USVn', 'USD', 'VSF', 'serSU',
                            'serUSVn', 'serUSVs', 'TSU', 'UL', 'SE', 'BR', 'unknown']
        
        # Identifica tutti i nodi ParadataNodeGroup
        paradata_groups = [node for node in self.nodes
                        if hasattr(node, 'node_type') and node.node_type == "ParadataNodeGroup"]
        stats["paradata_groups_found"] = len(paradata_groups)

        if verbose:
            pass
            # print(f"Trovati {stats['paradata_groups_found']} gruppi ParadataNodeGroup")

        # Per ogni ParadataNodeGroup, trova le property contenute e le unità stratigrafiche collegate
        for group in paradata_groups:
            if verbose:
                pass
                # print(f"\nAnalisi del gruppo: {group.name} (ID: {group.node_id})")
            
            # Trova i PropertyNode contenuti nel gruppo
            property_nodes = []
            for edge in self.edges:
                if edge.edge_target == group.node_id and edge.edge_type == "is_in_paradata_nodegroup":
                    source_node = self.find_node_by_id(edge.edge_source)
                    if source_node and hasattr(source_node, 'node_type') and source_node.node_type == "property":
                        property_nodes.append(source_node)
                        if verbose:
                            pass
                            # print(f"  - PropertyNode {source_node.name} trovato nel gruppo (ID: {group.name})")
            
            stats["property_nodes_found"] += len(property_nodes)
            
            # Se non ci sono PropertyNode nel gruppo, passa al prossimo
            if not property_nodes:
                if verbose:
                    pass
                    # print(f"  Nessun PropertyNode trovato nel gruppo {group.name}")
                continue
            
            # Trova le unità stratigrafiche collegate al ParadataNodeGroup
            stratigraphic_nodes = []
            
            # Cerchiamo prima con edge_type "has_paradata_nodegroup"
            for edge in self.edges:
                if edge.edge_target == group.node_id and edge.edge_type == "has_paradata_nodegroup":
                    source_node = self.find_node_by_id(edge.edge_source)
                    if source_node and hasattr(source_node, 'node_type'):
                        if source_node.node_type in stratigraphic_types:
                            stratigraphic_nodes.append(source_node)
                            if verbose:
                                pass
                                # print(f"  - Unità stratigrafica collegata al gruppo: {source_node.name} (Tipo: {source_node.node_type})")

            # LEGACY ONLY — graphs degraded by the old connection resolver.
            # `has_paradata_nodegroup` names `StratigraphicNode` as its source;
            # until Se1 that name resolved to the wrong class, so every such edge
            # was rewritten to `generic_connection` at import and the canonical
            # loop above found nothing. This branch was the workaround: it reads
            # UNTYPED edges as if they were the paradata link, which is a guess by
            # definition. It is no longer a normal path — re-import the GraphML
            # with the fixed core and it stops firing. Guesses are counted in
            # `stats["legacy_generic_guesses"]` so a caller can see it happened.
            if not stratigraphic_nodes:
                for edge in self.edges:
                    if edge.edge_target == group.node_id and edge.edge_type == "generic_connection":
                        source_node = self.find_node_by_id(edge.edge_source)
                        if source_node and hasattr(source_node, 'node_type'):
                            if source_node.node_type in stratigraphic_types:
                                stratigraphic_nodes.append(source_node)
                                stats["legacy_generic_guesses"] += 1
                                if verbose:
                                    pass
                                    # print(f"  - Unità stratigrafica collegata al gruppo (generic_connection): {source_node.name} (Tipo: {source_node.node_type})")
            
            stats["stratigraphic_nodes_found"] += len(stratigraphic_nodes)
            
            # Se non ci sono unità stratigrafiche collegate al gruppo, passa al prossimo
            if not stratigraphic_nodes:
                if verbose:
                    pass
                    # print(f"  Nessuna unità stratigrafica collegata al gruppo {group.name}")
                continue
            
            # Crea collegamenti diretti tra le unità stratigrafiche e i PropertyNode
            for strat_node in stratigraphic_nodes:
                for prop_node in property_nodes:
                    # Verifica se esiste già un collegamento diretto
                    existing_edge = None
                    for edge in self.edges:
                        if (edge.edge_source == strat_node.node_id and 
                            edge.edge_target == prop_node.node_id and 
                            edge.edge_type == "has_property"):
                            existing_edge = edge
                            break
                    
                    if existing_edge:
                        stats["connections_already_existing"] += 1
                        if verbose:
                            pass
                            # print(f"  Collegamento già esistente: {strat_node.name} -> {prop_node.name}")
                    else:
                        pass
                        # Crea un nuovo edge per collegare direttamente
                        edge_id = f"{strat_node.node_id}_has_property_{prop_node.node_id}"
                        try:
                            new_edge = self.add_edge(edge_id, strat_node.node_id, prop_node.node_id, "has_property")
                            # This edge is DERIVED, not authored: it materialises
                            # "US → group → property" as a direct link so every
                            # consumer can read properties the same way. Marking it
                            # keeps three things true — it can be recomputed without
                            # duplicating, it can be told apart from an authored
                            # has_property, and it does not lose WHICH paradata
                            # group justified it (the direct edge alone throws that
                            # away). In-memory only for now: the em.json edge
                            # payload has no attributes field yet (that is the
                            # schema step), and the propagation re-runs at every
                            # import, so the mark is always regenerated.
                            new_edge.attributes["derived"] = True
                            new_edge.attributes["derived_from"] = group.node_id
                            stats["connections_created"] += 1
                            if verbose:
                                pass
                                # print(f"  ✅ Nuovo collegamento creato: {strat_node.name} -> {prop_node.name}")
                        except Exception as e:
                            stats["errors"] += 1
                            if verbose:
                                pass
                                # print(f"  ❌ Errore nella creazione del collegamento: {str(e)}")
        
        if verbose:
            pass
            # print("\n=== Statistiche dell'operazione ===")
            # print(f"Gruppi ParadataNodeGroup trovati: {stats['paradata_groups_found']}")
            # print(f"PropertyNode trovati nei gruppi: {stats['property_nodes_found']}")
            # print(f"Unità stratigrafiche collegate ai gruppi: {stats['stratigraphic_nodes_found']}")
            # print(f"Nuovi collegamenti creati: {stats['connections_created']}")
            # print(f"Collegamenti già esistenti: {stats['connections_already_existing']}")
            # print(f"Errori: {stats['errors']}")
            # print("=== Completata la connessione PropertyNode dai ParadataNodeGroup ===")
        
        return stats



    def display_warnings(self):
        """Displays all accumulated warning messages."""
        for warning in self.warnings:
            #print("Warning:", warning)
            pass

    def find_node_by_id(self, node_id):
        """Finds a node by ID.

        ✅ OPTIMIZATION: O(1) lookup using indices instead of O(n) iteration
        """
        # Use index if available (O(1) lookup)
        if not self._indices_dirty and self._indices is not None:
            return self._indices.nodes_by_id.get(node_id)

        # Fallback to linear search if indices not ready
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def find_edge_by_id(self, edge_id):
        """Finds an edge by ID."""
        for edge in self.edges:
            if edge.edge_id == edge_id:
                return edge
        return None

    def get_connected_nodes(self, node_id):
        """Gets all nodes connected to a given node."""
        connected_nodes = []
        for edge in self.edges:
            if edge.edge_source == node_id:
                target_node = self.find_node_by_id(edge.edge_target)
                if target_node:
                    connected_nodes.append(target_node)
            elif edge.edge_target == node_id:
                source_node = self.find_node_by_id(edge.edge_source)
                if source_node:
                    connected_nodes.append(source_node)
        return connected_nodes

    def get_connected_edges(self, node_id):
        """Gets all edges connected to a given node."""
        return [edge for edge in self.edges if edge.edge_source == node_id or edge.edge_target == node_id]

    def filter_nodes_by_connection_to_type(self, node_id, node_type):
        """Filters nodes connected to a given node by node type."""
        connected_nodes = self.get_connected_nodes(node_id)
        return [node for node in connected_nodes if node.node_type == node_type]

    def get_nodes_by_type(self, node_type):
        """Gets all nodes of a given type.

        ✅ OPTIMIZATION: O(1) lookup using type index instead of O(n) iteration
        """
        # Use index if available (O(1) lookup)
        if not self._indices_dirty and self._indices is not None:
            return self._indices.nodes_by_type.get(node_type, [])

        # Fallback to linear search if indices not ready
        return [node for node in self.nodes if node.node_type == node_type]

    def remove_node(self, node_id):
        """Removes a node and all edges connected to it."""
        self.nodes = [node for node in self.nodes if node.node_id != node_id]
        self.edges = [edge for edge in self.edges if edge.edge_source != node_id and edge.edge_target != node_id]
        # print(f"Node '{node_id}' and its edges removed successfully.")

    def remove_edge(self, edge_id):
        """Removes an edge from the graph."""
        self.edges = [edge for edge in self.edges if edge.edge_id != edge_id]
        # print(f"Edge '{edge_id}' removed successfully.")

    def update_node(self, node_id, **kwargs):
        """Updates attributes of an existing node."""
        node = self.find_node_by_id(node_id)
        if not node:
            raise ValueError(f"Node with ID '{node_id}' not found.")
        for key, value in kwargs.items():
            setattr(node, key, value)
        # print(f"Node '{node_id}' updated successfully.")

    def update_edge(self, edge_id, **kwargs):
        """Updates attributes of an existing edge."""
        edge = self.find_edge_by_id(edge_id)
        if not edge:
            raise ValueError(f"Edge with ID '{edge_id}' not found.")
        for key, value in kwargs.items():
            setattr(edge, key, value)
        # print(f"Edge '{edge_id}' updated successfully.")


    def find_node_by_name(self, name):
        """
        Cerca un nodo per nome.

        Args:
            name (str): Nome del nodo da cercare.

        Returns:
            Node: Il nodo trovato, o None se non esiste.
        """
        for node in self.nodes:
            if node.name == name:
                return node
        return None
    
    def find_edge_by_nodes(self, source_id, target_id):
        """
        Cerca un arco basato sugli ID dei nodi sorgente e destinazione.

        Args:
            source_id (str): ID del nodo sorgente.
            target_id (str): ID del nodo destinazione.

        Returns:
            Edge: L'arco trovato, o None se non esiste.
        """
        for edge in self.edges:
            if edge.edge_source == source_id and edge.edge_target == target_id:
                return edge
        return None

    def get_connected_node_by_type(self, node, node_type):
        """
        Ottiene un nodo collegato di un determinato tipo.

        Args:
            node (Node): Nodo di partenza.
            node_type (str): Tipo di nodo da cercare.

        Returns:
            Node: Il nodo collegato del tipo specificato, o None se non trovato.
        """
        for edge in self.edges:
            if edge.edge_source == node.node_id:
                target_node = self.find_node_by_id(edge.edge_target)
                if target_node and target_node.node_type == node_type:
                    return target_node
            elif edge.edge_target == node.node_id:
                source_node = self.find_node_by_id(edge.edge_source)
                if source_node and source_node.node_type == node_type:
                    return source_node
        return None


    def get_connected_epoch_node_by_edge_type(self, node, edge_type: str):
        """
        Ottiene il nodo EpochNode connesso tramite un arco di tipo specifico.

        Args:
            node (Node): Il nodo da cui partire.
            edge_type (str): Il tipo di arco da filtrare.

        Returns:
            EpochNode | None: Il nodo EpochNode connesso, oppure None se non trovato.

        ✅ OPTIMIZATION: O(1) lookup using composite index instead of O(E) iteration
        """
        # Use composite index if available (O(1) lookup)
        if not self._indices_dirty and self._indices is not None:
            # Check outgoing edges (source -> target)
            source_key = (node.node_id, edge_type)
            for edge in self._indices.edges_by_source_type.get(source_key, []):
                target_node = self.find_node_by_id(edge.edge_target)
                if target_node and target_node.node_type == "EpochNode":
                    return target_node

            # Check incoming edges (target <- source)
            target_key = (node.node_id, edge_type)
            for edge in self._indices.edges_by_target_type.get(target_key, []):
                source_node = self.find_node_by_id(edge.edge_source)
                if source_node and source_node.node_type == "EpochNode":
                    return source_node

            return None

        # Fallback to linear search if indices not ready
        for edge in self.edges:
            if (edge.edge_source == node.node_id and edge.edge_type == edge_type):
                target_node = self.find_node_by_id(edge.edge_target)
                if target_node and target_node.node_type == "EpochNode":
                    return target_node
                else:
                    pass
                    # print(f"NOT found any epochnode for {node.name} con id {node.node_id}")
            elif (edge.edge_target == node.node_id and edge.edge_type == edge_type):
                source_node = self.find_node_by_id(edge.edge_source)
                if source_node and source_node.node_type == "EpochNode":
                    return source_node
                else:
                    pass
                    # print(f"NOT found any epochnode for {node.name} con id {node.id}")

        return None


    def get_connected_epoch_nodes_list_by_edge_type(self, node, edge_type: str):
        """
        Ottiene una lista di nodi EpochNode connessi tramite un arco di tipo specifico.

        Args:
            node (Node): Il nodo da cui partire.
            edge_type (str): Il tipo di arco da filtrare.

        Returns:
            List[EpochNode]: Lista di nodi EpochNode connessi.

        ✅ OPTIMIZATION: O(1) lookup using composite index instead of O(E) iteration
        """
        connected_epoch_nodes = []

        # Use composite index if available (O(1) lookup)
        if not self._indices_dirty and self._indices is not None:
            # Check outgoing edges (source -> target)
            source_key = (node.node_id, edge_type)
            for edge in self._indices.edges_by_source_type.get(source_key, []):
                target_node = self.find_node_by_id(edge.edge_target)
                if target_node and target_node.node_type == "EpochNode":
                    connected_epoch_nodes.append(target_node)

            # Check incoming edges (target <- source)
            target_key = (node.node_id, edge_type)
            for edge in self._indices.edges_by_target_type.get(target_key, []):
                source_node = self.find_node_by_id(edge.edge_source)
                if source_node and source_node.node_type == "EpochNode":
                    connected_epoch_nodes.append(source_node)

            return connected_epoch_nodes

        # Fallback to linear search if indices not ready
        for edge in self.edges:
            if (edge.edge_source == node.node_id and edge.edge_type == edge_type):
                target_node = self.find_node_by_id(edge.edge_target)
                if target_node and target_node.node_type == "EpochNode":
                    # print(f"Found connected EpochNode '{target_node.node_id}' via edge type '{edge_type}'.")
                    connected_epoch_nodes.append(target_node)
            elif (edge.edge_target == node.node_id and edge.edge_type == edge_type):
                source_node = self.find_node_by_id(edge.edge_source)
                if source_node and source_node.node_type == "EpochNode":
                    # print(f"Found connected EpochNode '{source_node.node_id}' via edge type '{edge_type}'.")
                    connected_epoch_nodes.append(source_node)
        return connected_epoch_nodes


    # =========================================================================
    # CHRONOLOGY CALCULATION & TEMPORAL PROPAGATION (TPQ/TAQ)
    # =========================================================================

    # Relations where source is MORE RECENT than target
    _SOURCE_IS_MORE_RECENT = {'cuts', 'overlies', 'fills', 'is_after'}
    # Relations where target is MORE RECENT than source
    _TARGET_IS_MORE_RECENT = {'is_cut_by', 'is_overlain_by', 'is_filled_by', 'is_before'}

    #: Every stratigraphic type the chronology dates: the datamodel's proper
    #: units (``family`` real or virtual in s3Dgraphy_node_datamodel.json) plus
    #: the legacy ``USM`` spelling some importers still produce. ``BR`` and
    #: ``SE`` are helper nodes (``family`` None): they are not seeded, only
    #: reached as neighbours of the propagation, exactly as before.
    #: RSF, TSU, UL, USN, USNt were missing until 1.6 (MICRO-cronologia § 2).
    CHRONOLOGY_TYPES = ('US', 'USVs', 'USVn', 'VSF', 'SF', 'USD',
                        'serSU', 'serUSD', 'serUSVn', 'serUSVs', 'USM',
                        'RSF', 'TSU', 'UL', 'USN', 'USNt')

    #: Where a bound can come from, in :meth:`chronology`'s ``rule`` field.
    CHRONOLOGY_RULES = ('written', 'epoch', 'contained', 'tpq', 'taq')

    def _chronology_nodes(self):
        nodes = []
        for t in self.CHRONOLOGY_TYPES:
            nodes.extend(self.get_nodes_by_type(t))
        return nodes

    def chronology(self, warnings=None):
        """The propagated chronology, COMPUTED IN MEMORY — nothing is written.

        Returns ``{node_id: entry}`` for every node that ends up with a bound::

            {"start": 1100.0, "end": 1300.0,
             "start_rule": "tpq", "start_source": "USM101",
             "start_relation": "is_after",
             "end_rule": "epoch", "end_source": "EP_MED",
             "end_relation": "has_first_epoch",
             "rule": "tpq",                  # the start's rule (end's if no start)
             "contained": {"start": 100.0, "source": "RSF1", "original": "SF100",
                           "via": ["is_part_of", "changed_from"]}}

        THE PROVENANCE OF A PROPAGATED DATE IS THE RELATION IT TRAVELS ALONG
        (E.D., 29 Sep 2026): ``is_after`` with that unit, ``is_part_of``,
        ``changed_from``. The graph already holds those relations, so the date
        gets no field of its own and is never written — anyone can recompute it,
        a triple store included. ``*_relation`` and ``*_source`` are only the
        answer's EXPLANATION, for an interface to say «≥ 1100 · is_after
        USM101»: the edge type through which the bound reached this node, and
        the node at its other end.

        ``*_rule`` is one of :data:`CHRONOLOGY_RULES`:

        ``written``    a PropertyNode ``absolute_time_start/end`` on the node
                       itself (relation ``has_property``, source that
                       PropertyNode).
        ``epoch``      the node's epochs (min start / max end over
                       ``has_first_epoch`` + ``survive_in_epoch``); the source is
                       the epoch that gives the bound.
        ``contained``  the latest start among what the node contains
                       (``is_part_of``, recursive; a member without a date of its
                       own is read on its original through ``changed_from``); the
                       source is the member, ``contained.original`` the original,
                       ``contained.via`` the relations walked.
        ``tpq`` / ``taq``  pushed along the stratigraphic sequence; the source is
                       the NEIGHBOUR it came from and the relation is the edge
                       between them, so a chain reads back step by step.

        A WRITTEN bound is never moved. When what the node contains says it is
        younger than it declares, ``contained`` is still reported beside it and a
        warning says so — intrusive material, a misattributed find, or a date to
        revise, and choosing among the three is not the library's job. Same Hard
        policy as before for ``tpq``/``taq`` against a written seed.

        ``warnings``: pass a list to receive the cycle / paradox / contradiction
        messages; nothing is appended to ``self.warnings`` here, so a call has no
        side effect at all. :meth:`calculate_chronology` is the in-memory writer
        EM-tools reads.
        """
        from .resolvers.builtin_rules import containment_tpq_detail

        sink = warnings if warnings is not None else []
        strat_nodes = self._chronology_nodes()

        # Pass 0: stratigraphic cycles (AI-extracted graphs can close loops).
        self._warn_on_stratigraphic_cycles(sink)

        # Pass 1: base bounds — written on the node, else its epochs.
        state = {}
        written_start, written_end = {}, {}
        for node in strat_nodes:
            st = state.setdefault(node.node_id, self._blank_bounds())
            for side, written in (("start", written_start), ("end", written_end)):
                found = self._base_bound(node, side)
                if found is None:
                    continue
                self._set_bound(st, side, *found)
                if found[1] == "written":
                    written[node.node_id] = found[0]

        # Pass 2: what the node contains (a container is not older than its
        # contents). Beside a written start, never over it.
        for node in strat_nodes:
            found = containment_tpq_detail(self, node)
            if found is None:
                continue
            value, member, original = found
            st = state[node.node_id]
            st["contained"] = {
                "start": value, "source": member.node_id,
                "original": original.node_id if original is not None else None,
                "via": ["is_part_of"] + (["changed_from"] if original is not None else [])}
            if st["start_rule"] == "written":
                if st["start"] < value:
                    label = getattr(node, "name", None) or node.node_id
                    via = getattr(member, "name", None) or member.node_id
                    if original is not None:
                        via += f" ← {getattr(original, 'name', None) or original.node_id}"
                    sink.append(
                        f"[chronology contained] node '{label}' declares "
                        f"absolute_time_start={st['start']} but contains '{via}' "
                        f"whose start is {value}. Keeping the declared value.")
            elif st["start"] is None or value > st["start"]:
                self._set_bound(st, "start", value, "contained", member.node_id, "is_part_of")

        # Pass 3: TPQ/TAQ along the stratigraphic sequence.
        self._propagate_bounds(strat_nodes, state, written_start, written_end, sink)

        out = {}
        for nid, st in state.items():
            if st["start"] is None and st["end"] is None:
                continue
            entry = {k: st[k] for k in self._BOUND_KEYS}
            entry["rule"] = st["start_rule"] or st["end_rule"]
            if "contained" in st:
                entry["contained"] = st["contained"]
            out[nid] = entry
        return out

    def calculate_chronology(self, graph=None):
        """
        Calculate chronology for all stratigraphic nodes and WRITE it on them.

        The in-memory form EM-tools has always used: ``CALCUL_START_T`` /
        ``CALCUL_END_T`` on ``node.attributes``, warnings on ``self.warnings``.
        It is now a wrapper of :meth:`chronology`, which computes the same thing
        without writing. These attributes are in-memory state and never part of
        a document: the em.json exporter leaves them out
        (``emjson_exporter.CALCULATED_KEYS``).

        A node the chronology no longer dates loses a stale ``CALCUL_*`` from an
        earlier run — the old writer never cleared, and a deleted date lingered.

        Args:
            graph: Deprecated, ignored. Kept for backwards compatibility.
        """
        warnings = []
        chron = self.chronology(warnings=warnings)
        self.warnings.extend(warnings)
        for node in self._chronology_nodes():
            if node.node_id not in chron:
                node.attributes.pop("CALCUL_START_T", None)
                node.attributes.pop("CALCUL_END_T", None)
        for nid, entry in chron.items():
            node = self.find_node_by_id(nid)
            if node is None:
                continue
            for side, key in (("start", "CALCUL_START_T"), ("end", "CALCUL_END_T")):
                if entry[side] is not None:
                    node.attributes[key] = entry[side]
                else:
                    node.attributes.pop(key, None)
        return chron

    _BOUND_KEYS = ("start", "end", "start_rule", "end_rule", "start_source",
                   "end_source", "start_relation", "end_relation")

    @classmethod
    def _blank_bounds(cls):
        return dict.fromkeys(cls._BOUND_KEYS)

    @staticmethod
    def _set_bound(st, side, value, rule, source, relation):
        st[side] = value
        st[side + "_rule"] = rule
        st[side + "_source"] = source
        st[side + "_relation"] = relation

    def _base_bound(self, node, side):
        """``(value, rule, source_id, relation)`` for one side, or None.

        The same order as the resolver (``absolute_time_*`` rules): the node's
        own PropertyNode, then its epochs aggregated (min start / max end). No
        graph-level default exists for chronology.
        """
        from .resolvers import get_rule
        from .resolvers.builtin_rules import _node_temporal_property_found

        prop_type = "absolute_time_" + side
        found = _node_temporal_property_found(self, node, prop_type)
        if found is not None:
            return found[0], "written", found[1].node_id, "has_property"
        rule = get_rule(prop_type)
        values, seen = [], set()
        for edge_type in ("has_first_epoch", "survive_in_epoch"):
            for epoch in self.get_connected_epoch_nodes_list_by_edge_type(node, edge_type):
                if epoch.node_id in seen:
                    continue
                seen.add(epoch.node_id)
                v = rule.swimlane_getter(self, epoch)
                if v is not None:
                    values.append((float(v), epoch, edge_type))
        if not values:
            return None
        best = rule.swimlane_aggregate([v for v, _, _ in values])
        _, epoch, edge_type = next(x for x in values if x[0] == best)
        return best, "epoch", epoch.node_id, edge_type

    def _warn_on_stratigraphic_cycles(self, sink=None):
        """Detect cycles in the stratigraphic ``is_after`` / ``cuts`` /
        ``overlies`` / ``fills`` partial order and emit a warning per
        cycle, including per-node attribution (who claimed which end of
        each offending relation). Into ``sink`` when given, else
        ``self.warnings``.
        """
        if sink is None:
            sink = self.warnings
        from .diagnostics import detect_stratigraphic_cycles, format_attribution

        cycles = detect_stratigraphic_cycles(self)
        for cycle in cycles:
            names = []
            for nid in cycle:
                n = self.find_node_by_id(nid)
                label = getattr(n, "name", None) or nid
                attr = ""
                if n is not None:
                    # Attribute by the start-date claim on this node
                    # (end-date attribution would be symmetric; one side
                    # is enough to point the user at the extractor).
                    attr = format_attribution(self, n, "absolute_time_start")
                names.append(f"{label}{attr}")
            if len(cycle) == 1:
                sink.append(
                    f"[stratigraphic cycle] self-loop on {names[0]}. "
                    f"Physically impossible; review the extraction."
                )
            else:
                chain = " → ".join(names) + f" → {names[0]}"
                sink.append(
                    f"[stratigraphic cycle] {chain}. "
                    f"Physically impossible; review the extractors involved."
                )

    def _find_temporal_property(self, node, property_type):
        """
        Find a property node of a given type connected to a stratigraphic node.

        Searches via 'has_property' edges for PropertyNode with matching
        property_type OR name (GraphML imports may store the type as the node name
        while property_type defaults to "string").

        The temporal value may be in `value` or `description` (GraphML stores
        annotation text in description).

        Args:
            node: The stratigraphic node to search from.
            property_type: The property type to find (e.g. "absolute_time_start").

        Returns:
            PropertyNode or None (with value guaranteed set if found)
        """
        for edge in self.get_connected_edges(node.node_id):
            if edge.edge_type == "has_property" and edge.edge_source == node.node_id:
                prop_node = self.find_node_by_id(edge.edge_target)
                if not prop_node or not isinstance(prop_node, PropertyNode):
                    continue
                # Match by property_type OR by node name
                if prop_node.property_type == property_type or prop_node.name == property_type:
                    # Ensure value is populated (GraphML may store it in description)
                    if (not prop_node.value or prop_node.value == "") and prop_node.description:
                        try:
                            float(prop_node.description)
                            prop_node.value = prop_node.description
                        except (ValueError, TypeError):
                            pass
                    return prop_node
        return None

    def get_property(self, node, rule_id, default=None):
        """Resolve a propagative property on ``node`` via the registered rule.

        Convenience wrapper around :func:`s3dgraphy.resolvers.resolve`.
        Walks the 3-level hierarchy (node > swimlane > graph) and returns
        the first non-null value, or ``default``.

        Example::

            author = graph.get_property(node, "author")
            start  = graph.get_property(node, "absolute_time_start")

        Args:
            node: The node to resolve the property for.
            rule_id: Id of a registered PropagationRule (see
                :func:`s3dgraphy.resolvers.list_rules`).
            default: Value to return when no level yields a non-null value.

        Raises:
            KeyError: If ``rule_id`` is not registered.
        """
        from .resolvers import resolve, get_rule
        return resolve(self, node, get_rule(rule_id), default=default)

    def _propagate_bounds(self, strat_nodes, state, written_start, written_end, sink):
        """
        Propagate Terminus Post Quem (TPQ) and Terminus Ante Quem (TAQ) constraints
        with coherence checking (DP-32 Layer B, Hard paradox policy), on the
        ``state`` map of :meth:`chronology` — nothing is written on the nodes.

        TPQ (propagates upward to more recent nodes):
            If node A starts at X, no node MORE RECENT than A starts before X.

        TAQ (propagates downward to more ancient nodes):
            If node A ends at Y, no node MORE ANCIENT than A ends after Y.

        Only restricts (tightens) derived values; never widens them. A tightened
        bound records the NEIGHBOUR it came from and the edge between them —
        its provenance is that relation.

        Paradox policy (Hard):
            If a node carries a WRITTEN seed (a PropertyNode absolute_time_start /
            absolute_time_end) and the incoming stratigraphic constraint would
            modify it, propagation is *blocked* at that node: the written seed is
            kept, a warning goes to ``sink``, and BFS does not traverse further
            through the conflicting node.
        """
        from .diagnostics import format_attribution

        # node_id -> [(neighbour_id, edge_type)]
        more_recent_of = {}
        more_ancient_of = {}
        for edge in self.edges:
            et = edge.edge_type
            if et in self._SOURCE_IS_MORE_RECENT:
                more_recent_of.setdefault(edge.edge_target, []).append((edge.edge_source, et))
                more_ancient_of.setdefault(edge.edge_source, []).append((edge.edge_target, et))
            elif et in self._TARGET_IS_MORE_RECENT:
                more_recent_of.setdefault(edge.edge_source, []).append((edge.edge_target, et))
                more_ancient_of.setdefault(edge.edge_target, []).append((edge.edge_source, et))

        passes = (
            # side, adjacency, written seeds, rule, "tighter?", wording
            ("start", more_recent_of, written_start, "tpq",
             lambda new, cur: cur is None or cur < new,
             "more recent", "TPQ"),
            ("end", more_ancient_of, written_end, "taq",
             lambda new, cur: cur is None or cur > new,
             "more ancient", "TAQ"),
        )
        for side, adjacency, written, rule, tighter, wording, short in passes:
            for node in strat_nodes:
                value = state[node.node_id][side]
                if value is None:
                    continue

                visited = {node.node_id}
                # (neighbour, the node it is reached from, the edge between them)
                queue = [(nid, node.node_id, et)
                         for nid, et in adjacency.get(node.node_id, [])]
                while queue:
                    neighbor_id, via_id, edge_type = queue.pop(0)
                    if neighbor_id in visited:
                        continue
                    visited.add(neighbor_id)

                    neighbor = self.find_node_by_id(neighbor_id)
                    if not neighbor or not hasattr(neighbor, 'node_type'):
                        continue

                    declared = written.get(neighbor_id)
                    if declared is not None and tighter(value, declared):
                        attr = format_attribution(self, neighbor, "absolute_time_" + side)
                        neighbor_label = getattr(neighbor, "name", None) or neighbor_id
                        node_label = getattr(node, "name", None) or node.node_id
                        sink.append(
                            f"[chronology paradox] node '{neighbor_label}' declares "
                            f"absolute_time_{side}={declared}{attr} but is stratigraphically "
                            f"{wording} than '{node_label}' whose {side}_time={value}. "
                            f"Keeping declared value; {short} propagation is stopped at this node."
                        )
                        # Hard policy: do not overwrite, do not traverse further.
                        continue

                    nst = state.setdefault(neighbor_id, self._blank_bounds())
                    if tighter(value, nst[side]):
                        self._set_bound(nst, side, value, rule, via_id, edge_type)

                    for next_id, et in adjacency.get(neighbor_id, []):
                        if next_id not in visited:
                            queue.append((next_id, neighbor_id, et))

    def filter_nodes_by_time_range(self, *args):
        """
        Filter stratigraphic nodes that overlap with a given time range.

        Accepts:
            filter_nodes_by_time_range(start_time, end_time)       - new API
            filter_nodes_by_time_range(graph, start_time, end_time) - old API (graph ignored)
        """
        if len(args) == 3:
            # Old API: (graph, start_time, end_time) - ignore graph
            start_time, end_time = float(args[1]), float(args[2])
        elif len(args) == 2:
            start_time, end_time = float(args[0]), float(args[1])
        else:
            return []
        return self._filter_nodes_by_time_range(start_time, end_time)

    def _filter_nodes_by_time_range(self, start_time, end_time):
        """
        Filter stratigraphic nodes that overlap with a given time range.

        A node is included if its [CALCUL_START_T, CALCUL_END_T] interval
        overlaps with [start_time, end_time].

        Args:
            start_time (float): Start of the time range.
            end_time (float): End of the time range.

        Returns:
            list: StratigraphicNodes within the specified time range.
        """
        filtered_nodes = []
        for node in self.get_nodes_by_type("StratigraphicNode"):
            node_start = node.attributes.get("CALCUL_START_T")
            node_end = node.attributes.get("CALCUL_END_T")
            if node_start is not None and node_end is not None:
                if start_time <= node_end and end_time >= node_start:
                    filtered_nodes.append(node)
        return filtered_nodes

    def print_node_connections(self, node):

        # print(f"Node: {node.name}, Type: {node.node_type}")
        # print("Connections:")

        for edge in self.edges:
            if edge.edge_source == node.node_id:
                target_node = self.find_node_by_id(edge.edge_target)
                if target_node:
                    pass
                    # print(f"  Connection Type: {edge.edge_type} ({edge.label})")
                    # print(f"    - Target Node: {target_node.name}, Type: {target_node.node_type}")
            elif edge.edge_target == node.node_id:
                source_node = self.find_node_by_id(edge.edge_source)
                if source_node:
                    pass
                    # print(f"  Connection Type: {edge.edge_type} ({edge.label})")
                    # print(f"    - Source Node: {source_node.name}, Type: {source_node.node_type}")


    def get_connected_nodes_by_filters(self, node, target_node_type="all", edge_type="all"):
        """
        Ottiene una lista di nodi collegati in base ai filtri specificati su target_node_type ed edge_type.

        Args:
            node (Node): Nodo di partenza.
            target_node_type (str): Tipo di nodo target da cercare ("all" per nessun filtro).
            edge_type (str): Tipo di edge da cercare ("all" per nessun filtro).

        Returns:
            list[Node]: Lista di nodi collegati che soddisfano i criteri specificati.
        """
        connected_nodes = []

        for edge in self.edges:
            # Filtra per edge_type se specificato
            if edge_type != "all" and edge.edge_type != edge_type:
                continue

            # Verifica se il nodo di partenza è source o target dell'edge
            if edge.edge_source == node.node_id:
                target_node = self.find_node_by_id(edge.edge_target)
                # Filtra per target_node_type se specificato
                if target_node and (target_node_type == "all" or target_node.node_type == target_node_type):
                    connected_nodes.append(target_node)
            elif edge.edge_target == node.node_id:
                source_node = self.find_node_by_id(edge.edge_source)
                # Filtra per target_node_type se specificato
                if source_node and (target_node_type == "all" or source_node.node_type == target_node_type):
                    connected_nodes.append(source_node)

        return connected_nodes


    # ── containment (DP-36) and functional membership (DP-72) ────────────────
    # Two axes, deliberately distinct even though both project to P46i:
    #   `is_part_of`             NESTING — physical containment, one primary
    #                            parent, drawn as a box, propagates the epoch
    #                            lane. Per the manual, "containment is a
    #                            relationship (edge), not a change in node type:
    #                            the presence of is_part_of edges is the only
    #                            discriminant".
    #   `is_in_functional_unit`  TAG — m:n membership in a Functional Unit,
    #                            which legitimately spans epochs and therefore
    #                            cannot be a swimlane box.
    def chronology_now(self, node):
        """What this node's chronology is AT THIS MOMENT. Computes, stores nothing.

        ``calculate_chronology`` is the other thing: it walks the graph once and
        writes ``CALCUL_START_T`` / ``CALCUL_END_T`` onto the nodes. Until
        MICRO-cronologia (29 Sep 2026) those attributes were lifted into
        ``em.json`` by the exporter — measured on Yavneh Area M4, 482 start
        values and 381 end values landed in the document — so a value computed
        there stopped being a consequence of the graph and travelled as if
        someone had asserted it. The exporter now leaves them out; the date's
        provenance is the relations the document already holds.
        :meth:`chronology` is the whole-graph form of this reader.

        This reader answers the same question without leaving a trace. Move a
        find to another locus, correct an epoch, delete a sherd, and the next
        call says something different, because it reads the graph rather than a
        stamp of what the graph used to say.

        Returns a dict:

        ``start`` / ``end``
            the effective bounds right now. ``start`` is the later of what the
            node declares (or inherits from its epochs) and what the objects
            inside it require.
        ``start_from``
            ``"node"`` or ``"swimlane"`` when the declared value stands,
            ``"contains"`` when the objects inside are what push it later.
        ``tpq`` / ``tpq_from``
            the containment terminus post quem on its own, and the name of the
            object that carries it — so a reader can say WHICH find dates the
            unit, which is the first thing an excavator asks.
        ``conflict``
            set when the node DECLARES a start earlier than the objects inside
            it allow. The declared value is returned unchanged: that case is
            intrusive material, or a find attributed to the wrong unit, or a
            date to revise, and none of the three is a library's to decide.
        """
        from .resolvers import resolve_with_source, get_rule
        from .resolvers.builtin_rules import containment_tpq

        start, start_from = resolve_with_source(
            self, node, get_rule("absolute_time_start"))
        end, _ = resolve_with_source(self, node, get_rule("absolute_time_end"))
        found = containment_tpq(self, node)

        out = {"start": start, "start_from": start_from if start is not None else None,
               "end": end, "tpq": None, "tpq_from": None, "conflict": None}
        if found is None:
            return out

        tpq, witness = found
        out["tpq"] = tpq
        out["tpq_from"] = getattr(witness, "name", witness.node_id)

        if start is None:
            out["start"], out["start_from"] = tpq, "contains"
        elif tpq > start:
            if start_from == "node":
                out["conflict"] = (
                    f"declared start {start}, but it contains "
                    f"'{out['tpq_from']}' which starts at {tpq}")
            else:
                out["start"], out["start_from"] = tpq, "contains"
        return out

    CONTAINMENT_EDGE = "is_part_of"
    FUNCTIONAL_UNIT_EDGE = "is_in_functional_unit"
    RM_GROUP_EDGE = "is_in_representation_model_group"

    def _edges_by(self, node_id, edge_type, incoming):
        """The `edge_type` edges where `node_id` is the target (incoming) or the
        source (outgoing). Uses the composite index when it is warm."""
        if not self._indices_dirty and self._indices is not None:
            index = (self._indices.edges_by_target_type if incoming
                     else self._indices.edges_by_source_type)
            return list(index.get((node_id, edge_type), []))
        return [e for e in self.edges if e.edge_type == edge_type
                and (e.edge_target if incoming else e.edge_source) == node_id]

    def get_contained_nodes(self, container_id, node_type=None):
        """The members of `container_id` — the nodes pointing at it with
        `is_part_of`. Optionally filtered by `node_type`. Works the same for a
        stratigraphic container (DP-36) and a Functional Unit (DP-72)."""
        out = []
        for edge in self._edges_by(container_id, self.CONTAINMENT_EDGE, incoming=True):
            node = self.find_node_by_id(edge.edge_source)
            if node is not None and (node_type is None or node.node_type == node_type):
                out.append(node)
        return out

    def get_containers_of(self, node_id, node_type=None):
        """The container(s) `node_id` is `is_part_of`. Multi-membership is legal
        (a US inside a container AND part of a Functional Unit), hence a list;
        pass `node_type` to keep only one kind of container."""
        out = []
        for edge in self._edges_by(node_id, self.CONTAINMENT_EDGE, incoming=False):
            node = self.find_node_by_id(edge.edge_target)
            if node is not None and (node_type is None or node.node_type == node_type):
                out.append(node)
        return out

    def is_container(self, node_id):
        """True if anything is `is_part_of` this node — the manual's discriminant."""
        return bool(self._edges_by(node_id, self.CONTAINMENT_EDGE, incoming=True))

    def get_functional_units(self):
        """Every FunctionalUnitNodeGroup in the graph (DP-72)."""
        from .nodes.group_node import FunctionalUnitNodeGroup
        return self.get_nodes_by_type(FunctionalUnitNodeGroup.node_type)

    def get_functional_unit_members(self, fu_id, node_type=None):
        """The members of a Functional Unit — the nodes tagged into it with
        `is_in_functional_unit`. Optionally filtered by `node_type`."""
        out = []
        for edge in self._edges_by(fu_id, self.FUNCTIONAL_UNIT_EDGE, incoming=True):
            node = self.find_node_by_id(edge.edge_source)
            if node is not None and (node_type is None or node.node_type == node_type):
                out.append(node)
        return out

    def get_functional_units_of(self, node_id):
        """The Functional Unit(s) a node belongs to. Membership is a TAG: m:n and
        additive, so a unit may serve several components at once."""
        out = []
        for edge in self._edges_by(node_id, self.FUNCTIONAL_UNIT_EDGE, incoming=False):
            node = self.find_node_by_id(edge.edge_target)
            if node is not None:
                out.append(node)
        return out

    # ── RM containers (EM16-RMNG) ────────────────────────────────────────
    #
    # Mirrors the Functional-Unit accessors above, with ONE difference that is
    # semantic and not stylistic: membership here is 1:1, not m:n. A mesh
    # belongs to exactly one container — the rule already in force on the
    # Blender side — so the question "which group is this model in?" has one
    # answer, and the accessor says so by returning a node or None instead of a
    # list. Returning a list would have invited callers to handle a case the
    # model forbids.

    def get_representation_model_groups(self):
        """Every RepresentationModelNodeGroup in the graph (EM16-RMNG)."""
        from .nodes.group_node import RepresentationModelNodeGroup
        return self.get_nodes_by_type(RepresentationModelNodeGroup.node_type)

    def get_representation_model_group_members(self, group_id, node_type=None):
        """The models tagged into this container with
        `is_in_representation_model_group`. Optionally filtered by node_type."""
        out = []
        for edge in self._edges_by(group_id, self.RM_GROUP_EDGE, incoming=True):
            node = self.find_node_by_id(edge.edge_source)
            if node is not None and (node_type is None or node.node_type == node_type):
                out.append(node)
        return out

    def get_representation_model_group_of(self, node_id):
        """The container a model belongs to, or None.

        Singular by design: one mesh, one container. When a graph somehow
        carries more than one membership edge (a hand-edited file, a merge),
        the FIRST is returned and the anomaly is left visible to the caller
        rather than silently reconciled here — `sync_rm_containers` on the
        Blender side is the place that reports divergences.
        """
        for edge in self._edges_by(node_id, self.RM_GROUP_EDGE, incoming=False):
            node = self.find_node_by_id(edge.edge_target)
            if node is not None:
                return node
        return None

    def get_functional_unit_epochs(self, fu_id):
        """The epochs a Functional Unit spans — DERIVED from its members, since a
        Functional Unit has no formation event and no epoch of its own. Returns
        the EpochNodes reached by the members' `has_first_epoch` /
        `survive_in_epoch`, in graph order, deduplicated."""
        seen, out = set(), []
        for member in self.get_functional_unit_members(fu_id):
            for edge_type in ("has_first_epoch", "survive_in_epoch"):
                for edge in self._edges_by(member.node_id, edge_type, incoming=False):
                    if edge.edge_target in seen:
                        continue
                    epoch = self.find_node_by_id(edge.edge_target)
                    if epoch is not None:
                        seen.add(edge.edge_target)
                        out.append(epoch)
        return out

    def get_connected_nodes_by_edge_type(self, node_id, edge_type):
        """
        Ottiene tutti i nodi connessi a un nodo specifico tramite un tipo di edge.

        Args:
            node_id (str): ID del nodo di partenza
            edge_type (str): Tipo di edge da filtrare

        Returns:
            list: Lista di nodi connessi attraverso il tipo di edge specificato

        ✅ OPTIMIZATION: O(1) lookup using composite index instead of O(E) iteration
        """
        connected_nodes = []

        # Use composite index if available (O(1) lookup)
        if not self._indices_dirty and self._indices is not None:
            # Check outgoing edges (source -> target)
            source_key = (node_id, edge_type)
            for edge in self._indices.edges_by_source_type.get(source_key, []):
                target_node = self.find_node_by_id(edge.edge_target)
                if target_node:
                    connected_nodes.append(target_node)

            # Check incoming edges (target <- source)
            target_key = (node_id, edge_type)
            for edge in self._indices.edges_by_target_type.get(target_key, []):
                source_node = self.find_node_by_id(edge.edge_source)
                if source_node:
                    connected_nodes.append(source_node)

            return connected_nodes

        # Fallback to linear search if indices not ready
        for edge in self.edges:
            if edge.edge_type == edge_type:
                if edge.edge_source == node_id:
                    target_node = self.find_node_by_id(edge.edge_target)
                    if target_node:
                        connected_nodes.append(target_node)
                elif edge.edge_target == node_id:
                    source_node = self.find_node_by_id(edge.edge_source)
                    if source_node:
                        connected_nodes.append(source_node)

        return connected_nodes

    def get_property_nodes_for_node(self, node_id):
        """
        Ottiene tutti i nodi proprietà connessi a un nodo specifico.
        
        Args:
            node_id (str): ID del nodo di partenza
            
        Returns:
            list: Lista di nodi proprietà connessi
        """
        #return [node for node in self.get_connected_nodes_by_edge_type(node_id, "has_property") 
        #        if node.node_type == "property"]

        return [node for node in self.get_connected_nodes_by_edge_type(node_id, "has_property") 
                if node.node_type == "property"]


    def get_combiner_nodes_for_property(self, property_node_id):
        """
        Ottiene tutti i nodi combiner connessi a un nodo proprietà.

        Args:
            property_node_id (str): ID del nodo proprietà

        Returns:
            list: Lista di nodi combiner connessi

        ✅ OPTIMIZATION: O(1) lookup using source index instead of O(E) iteration
        """
        combiners = []

        # Use index if available (O(1) lookup)
        if not self._indices_dirty and self._indices is not None:
            for edge in self._indices.edges_by_source.get(property_node_id, []):
                target_node = self.find_node_by_id(edge.edge_target)
                if target_node and target_node.node_type == "combiner":
                    combiners.append(target_node)
            return combiners

        # Fallback to linear search
        for edge in self.edges:
            if edge.edge_source == property_node_id:
                target_node = self.find_node_by_id(edge.edge_target)
                if target_node and target_node.node_type == "combiner":
                    combiners.append(target_node)

        return combiners

    def get_extractor_nodes_for_node(self, node_id):
        """
        Ottiene tutti i nodi extractor connessi a un nodo (proprietà o combiner).
        
        Args:
            node_id (str): ID del nodo di partenza
            
        Returns:
            list: Lista di nodi extractor connessi
        """
        extractors = []
        node = self.find_node_by_id(node_id)
        # print(f"\nCercando estrattori per nodo: {node_id} (tipo: {node.node_type if node else 'sconosciuto'})")
        
        # Lista di edge types da considerare
        edge_types = ["has_data_provenance", "extracted_from", "combines", "generic_connection"]
        
        # Check per estrattori che sono source delle relazioni (estrattore -> nodo)
        for edge in self.edges:
            if edge.edge_source in edge_types and edge.edge_target == node_id:
                source_node = self.find_node_by_id(edge.edge_source)
                if source_node and source_node.node_type == "extractor":
                    extractors.append(source_node)
                    # print(f"  Trovato estrattore (source): {source_node.name} (edge: {edge.edge_type})")
        
        # Check per estrattori che sono target delle relazioni (nodo -> estrattore)
        for edge in self.edges:
            if edge.edge_type in edge_types and edge.edge_source == node_id:
                target_node = self.find_node_by_id(edge.edge_target)
                if target_node and target_node.node_type == "extractor":
                    extractors.append(target_node)
                    # print(f"  Trovato estrattore (target): {target_node.name} (edge: {edge.edge_type})")
        
        # Verifica le relazioni inverse (estrattore è source e questo nodo è target)
        for edge in self.edges:
            if edge.edge_target == node_id:
                source_node = self.find_node_by_id(edge.edge_source)
                if source_node and source_node.node_type == "extractor":
                    extractors.append(source_node)
                    # print(f"  Trovato estrattore (rel inverse): {source_node.name} (edge: {edge.edge_type})")
        
        # Nel caso specifico dei combiner, verifica anche relazioni di tipo "combines"
        node = self.find_node_by_id(node_id)
        if node and node.node_type == "combiner":
            # Se questo è un combiner, cerca estrattori che ha combinato
            # print(f"  Verifico relazioni speciali per combiner: {node.name}")
            
            # Verifica attributo sources se il nodo è un combiner
            if hasattr(node, 'sources'):
                for source_id in node.sources:
                    source_node = self.find_node_by_id(source_id)
                    if source_node and source_node.node_type == "extractor":
                        extractors.append(source_node)
                        # print(f"  Trovato estrattore da sources: {source_node.name}")
        
        # Rimuovi duplicati
        unique_extractors = []
        seen = set()
        for extractor in extractors:
            if extractor.node_id not in seen:
                seen.add(extractor.node_id)
                unique_extractors.append(extractor)
        
        # print(f"  Totale estrattori trovati: {len(unique_extractors)}")
        return unique_extractors
    
    def get_document_nodes_for_extractor(self, extractor_node_id):
        """
        Ottiene tutti i nodi documento connessi a un nodo extractor.
        
        Args:
            extractor_node_id (str): ID del nodo extractor
            
        Returns:
            list: Lista di nodi documento connessi
        """
        documents = []
        
        extractor = self.find_node_by_id(extractor_node_id)
        # print(f"Cercando documenti per estrattore: {extractor_node_id} (tipo: {extractor.node_type if extractor else 'sconosciuto'})")
        # print(f"Numero totale di edges: {len(self.edges)}")
        
        # Verifica tutti i tipi di edge possibili
        edge_types = ["extracted_from", "has_data_provenance", "generic_connection"]
        
        # Cerca relazioni (estrattore -> documento)
        for edge in self.edges:
            if edge.edge_type in edge_types and edge.edge_source == extractor_node_id:
                target_node = self.find_node_by_id(edge.edge_target)
                if target_node and target_node.node_type == "document":
                    documents.append(target_node)
                    # print(f"  Trovato documento (target): {target_node.name} (edge: {edge.edge_type})")
        
        # Cerca relazioni (documento -> estrattore)
        for edge in self.edges:
            if edge.edge_type in edge_types and edge.edge_target == extractor_node_id:
                source_node = self.find_node_by_id(edge.edge_source)
                if source_node and source_node.node_type == "document":
                    documents.append(source_node)
                    # print(f"  Trovato documento (source): {source_node.name} (edge: {edge.edge_type})")
        
        # Rimuovi duplicati
        unique_documents = []
        seen = set()
        for doc in documents:
            if doc.node_id not in seen:
                seen.add(doc.node_id)
                unique_documents.append(doc)
        
        # print(f"  Totale documenti trovati: {len(unique_documents)}")
        return unique_documents

    def get_paradata_chain(self, strat_node_id):
        """
        Ottiene la catena completa di paradata per un nodo stratigrafico.
        
        Args:
            strat_node_id (str): ID del nodo stratigrafico
            
        Returns:
            dict: Dizionario con le catene di paradata strutturate
        """
        result = {
            "properties": [],
            "combiners": [],
            "extractors": [],
            "documents": []
        }
        
        # Ottieni le proprietà
        properties = self.get_property_nodes_for_node(strat_node_id)
        result["properties"] = properties
        
        # Per ogni proprietà, ottieni combiners ed extractors
        for prop in properties:
            combiners = self.get_combiner_nodes_for_property(prop.node_id)
            extractors = self.get_extractor_nodes_for_node(prop.node_id)
            
            result["combiners"].extend(combiners)
            result["extractors"].extend(extractors)
            
            # Per ogni combiner, ottieni extractors
            for combiner in combiners:
                comb_extractors = self.get_extractor_nodes_for_node(combiner.node_id)
                result["extractors"].extend(comb_extractors)
            
            # Per ogni extractor, ottieni documents
            for extractor in extractors + [ext for comb in combiners for ext in self.get_extractor_nodes_for_node(comb.node_id)]:
                documents = self.get_document_nodes_for_extractor(extractor.node_id)
                result["documents"].extend(documents)
        
        # Rimuovi duplicati (preservando l'ordine)
        for key in result:
            seen = set()
            result[key] = [x for x in result[key] if not (x.node_id in seen or seen.add(x.node_id))]
        
        return result

    def refine_edge_types(self, verbose=False):
        """
        Refines placeholder edge types to more specific semantic types
        based on the types of connected nodes.

        This method applies the same logic as the GraphML importer's enhance_edge_type()
        to edges that are already in memory, transforming placeholders into
        semantic edge types according to the s3Dgraphy datamodel.

        Refines both:
        - 'has_data_provenance' (placeholder for GraphML 'dashed' edges)
        - 'generic_connection' (placeholder for runtime-created edges)

        Args:
            verbose (bool): If True, prints details about refined edges

        Returns:
            int: Number of edges that were refined
        """
        from .nodes.document_node import DocumentNode
        from .nodes.extractor_node import ExtractorNode
        from .nodes.combiner_node import CombinerNode
        from .nodes.paradata_node import ParadataNode

        # Stratigraphic node types
        stratigraphic_types = ['US', 'USVs', 'USVn', 'VSF', 'SF', 'USD', 'serSU',
                              'serUSVn', 'serUSVs', 'TSU', 'UL', 'SE', 'BR', 'unknown']

        refined_count = 0

        for edge in self.edges:
            # Only process placeholder edge types
            if edge.edge_type not in ("has_data_provenance", "generic_connection"):
                continue

            # Find source and target nodes
            source_node = self.find_node_by_id(edge.edge_source)
            target_node = self.find_node_by_id(edge.edge_target)

            if not source_node or not target_node:
                continue

            source_type = source_node.node_type if hasattr(source_node, 'node_type') else ""
            target_type = target_node.node_type if hasattr(target_node, 'node_type') else ""

            original_type = edge.edge_type
            new_type = None

            # Refinement rules (same as import_graphml.py enhance_edge_type)

            if edge.edge_type == "has_data_provenance":
                # StratigraphicNode -> PropertyNode
                if source_type in stratigraphic_types and target_type == "property":
                    new_type = "has_property"
                # StratigraphicNode -> ParadataNodeGroup
                elif source_type in stratigraphic_types and target_type == "ParadataNodeGroup":
                    new_type = "has_paradata_nodegroup"
                # ExtractorNode -> DocumentNode
                elif isinstance(source_node, ExtractorNode) and isinstance(target_node, DocumentNode):
                    new_type = "extracted_from"
                # CombinerNode -> ExtractorNode
                elif isinstance(source_node, CombinerNode) and isinstance(target_node, ExtractorNode):
                    new_type = "combines"
                # ✅ StratigraphicNode -> DocumentNode = has_documentation
                elif source_type in stratigraphic_types and isinstance(target_node, DocumentNode):
                    new_type = "has_documentation"
                # ✅ DocumentNode -> StratigraphicNode = is_documentation_of
                elif isinstance(source_node, DocumentNode) and target_type in stratigraphic_types:
                    new_type = "is_documentation_of"

            elif edge.edge_type == "generic_connection":
                # ✅ StratigraphicNode -> DocumentNode = has_documentation
                if source_type in stratigraphic_types and isinstance(target_node, DocumentNode):
                    new_type = "has_documentation"
                # ✅ DocumentNode -> StratigraphicNode = is_documentation_of (reverse)
                elif isinstance(source_node, DocumentNode) and target_type in stratigraphic_types:
                    new_type = "is_documentation_of"
                # ParadataNode (and subclasses) -> ParadataNodeGroup
                elif isinstance(source_node, (DocumentNode, ExtractorNode, CombinerNode, ParadataNode)) and target_type == "ParadataNodeGroup":
                    new_type = "is_in_paradata_nodegroup"
                # ParadataNodeGroup -> ActivityNodeGroup
                elif source_type == "ParadataNodeGroup" and target_type == "ActivityNodeGroup":
                    new_type = "has_paradata_nodegroup"

            # Apply refinement if a rule matched
            if new_type:
                edge.edge_type = new_type
                refined_count += 1
                if verbose:
                    print(f"✅ Refined edge {edge.edge_id}: {original_type} -> {new_type} ({source_type} -> {target_type})")

        if verbose and refined_count > 0:
            print(f"\n🔄 Total edges refined: {refined_count}")
        elif verbose:
            print("ℹ️  No placeholder edges found to refine")

        return refined_count

    # Legacy alias for backwards compatibility
    def refine_generic_connections(self, verbose=False):
        """Deprecated: Use refine_edge_types() instead."""
        return self.refine_edge_types(verbose=verbose)


'''
Esempio di utilizzo:
graph = get_graph()  # Ottieni il grafo caricato
graph.calculate_chronology()  # Calcola la cronologia

# Filtra i nodi in un intervallo di tempo specifico
filtered_nodes = graph.filter_nodes_by_time_range(50, 100)
for node in filtered_nodes:
    pass
    # print(f"Node {node.node_id}: Start = {node.attributes.get('CALCUL_START_T')}, End = {node.attributes.get('CALCUL_END_T')}")
'''

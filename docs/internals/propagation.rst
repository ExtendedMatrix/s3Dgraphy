Property Propagation
====================

.. versionadded:: 1.5.0

.. module:: s3dgraphy.resolvers

The :mod:`s3dgraphy.resolvers` package implements the **3-level property
resolver** introduced in s3dgraphy 1.5 (DP-32 Layer A). Given a node and
a property name, the resolver walks the graph and returns the value plus
the source level it came from, so callers no longer need to know which
edges to traverse.

Conceptually
------------

For every *propagative* property — ``author``, ``license``, ``embargo``,
``absolute_time_start``, ``absolute_time_end`` — the resolver tries
three lookups in order and returns the first non-null result:

#. **Node-level**
   :func:`PropagationRule.node_getter` reads a value attached directly
   to the input node (typically a :class:`PropertyNode` reachable via
   ``has_property`` or an :class:`AuthorNode` reachable via
   ``has_author``).

#. **Swimlane-level**
   For every :class:`EpochNode` connected to the input node via
   ``has_first_epoch`` or ``survive_in_epoch``, the resolver calls
   :func:`PropagationRule.swimlane_getter`. If
   :attr:`PropagationRule.swimlane_aggregate` is provided (``min`` for
   start dates, ``max`` for end dates), it is applied to the non-null
   values; otherwise the first non-null value wins.

#. **Graph-level**
   :func:`PropagationRule.graph_getter` reads a value from the canvas
   header (``graph.attributes['author_name'|'license'|'embargo']``,
   populated by the DP-40 Canvas Header loader).

When the input itself is an :class:`EpochNode`, the resolver
short-circuits to the swimlane-level lookup — for an epoch, "node level"
and "swimlane level" are the same thing.

PropagationRule
---------------

Every propagative property is declared once as a
:class:`PropagationRule`::

    from s3dgraphy.resolvers import PropagationRule, register_rule

    AUTHOR_RULE = PropagationRule(
        id="author",
        label="Author",
        node_getter=_author_node_level,
        swimlane_getter=_author_swimlane_level,
        graph_getter=_author_graph_level,
    )
    register_rule(AUTHOR_RULE)

The four ship-standard rules are registered at module-import time in
:mod:`s3dgraphy.resolvers.builtin_rules`:

================================  ============================  ==========
Rule id                            What it returns                Aggregate
================================  ============================  ==========
``absolute_time_start``            TPQ — earliest year             ``min``
``absolute_time_end``              TAQ — latest year               ``max``
``author``                         joined display string           none
``license``                        license string                  none
``embargo``                        embargo end date                none
================================  ============================  ==========

The author rule follows **every** ``has_author`` edge (not just the
first one) and joins the display values with ``" ; "``. Duplicates are
de-duplicated while preserving edge order.

The author display string is read from
:attr:`AuthorNode.description` (1.5 dev9 yEd palette convention:
``AuthorNode.name = "A.01"``,
``AuthorNode.description = "Giulia Rossi | ORCID:… | affiliation"``),
falling back to ``data["name"] + data["surname"]`` and lastly to the
short code in :attr:`AuthorNode.name`.

resolve() / resolve_with_source()
---------------------------------

Two entry points::

    from s3dgraphy.resolvers import resolve, resolve_with_source

    val = resolve(graph, node, AUTHOR_RULE)                  # → "Giulia Rossi ; AI Tool"
    val, src = resolve_with_source(graph, node, AUTHOR_RULE) # → ("Giulia Rossi", "swimlane")

``src`` is one of ``"node"`` / ``"swimlane"`` / ``"graph"`` /
``"none"`` — and since 1.6 ``"master"``, ``"publisher"``, ``"container"``,
``"members"``, ``"life"`` (see *Own or inherited* below). Use it to tag UI labels (em-graph paints node-level values
black, swimlane-level grey, graph-level grey-italic).

Worked example — author resolution
----------------------------------

.. code-block:: text

   US001  --has_author-->  AuthorNode  (A.01, "Giulia Rossi")
   US001  --has_first_epoch-->  EP_ROMAN

   EP_ROMAN  <--has_first_epoch--  SL_PD_ROMAN  (paradata group)
   SL_PD_ROMAN  --has_author-->  AuthorNode  (A.02, "Marco Bianchi")

For ``resolve(graph, US001, AUTHOR_RULE)``:

#. Node-level: US001 has a direct ``has_author`` edge → ``"Giulia Rossi"``.
   First non-null value wins, ``src = "node"``.

For ``resolve(graph, US002, AUTHOR_RULE)`` (a unit with no direct
``has_author``):

#. Node-level: nothing → ``None``.
#. Swimlane-level: US002's epoch is ``EP_ROMAN``, which has the SL_PD
   author A.02. Resolver returns ``"Marco Bianchi"``, ``src = "swimlane"``.

For an isolated unit US003 with no edges:

#. Node-level: nothing.
#. Swimlane-level: nothing.
#. Graph-level: ``graph.attributes["author_name"]`` from the DP-40
   canvas header → ``"Project lead"``.

Own or inherited, and from which node
-------------------------------------

.. versionadded:: 1.6
   MICRO-A-PROPRIO-EREDITATO (14 Nov 2026). «La catena dei valori propri del
   nodo o ereditati da altro nodo è essenziale nell'esperienza utente» (E.D.).

:func:`s3dgraphy.resolvers.provenance.resolve_provenance` answers the same
question as :func:`resolve_with_source` and also says **from which node**::

    from s3dgraphy.resolvers import get_rule, resolve_provenance

    r = resolve_provenance(graph, "X1", get_rule("absolute_time_start"))
    # {"value": 100.0, "level": "master", "origin": "II", "via": "SU1",
    #  "chain": ["X1", "C1", "P1", "SU1", "II"], "from_level": "swimlane"}

``origin`` is the node the value is WRITTEN on (the node itself, an epoch, a
continuity, the graph node); ``chain`` the ids walked from the node to it;
``via`` the first node of an inherited hop (the master, the Document, the
container, the member). :func:`resolve_with_source` keeps its signature and
returns the level of this walk, so its callers see the new levels too.
:func:`~s3dgraphy.resolvers.provenance.provenance_table` resolves many nodes
and rules with one edge index.

The levels, by kind of node:

=======================  ====================================================
Kind                     Order
=======================  ====================================================
epoch                    swimlane → graph
servile                  node → **master** → (its own epochs, only when it
                         serves nobody) → graph
continuity (BR)          node → its epoch → **master** (its unit) → graph
activity group           node → **members** (start = min, end = max) →
                         swimlane → graph
model (RM, RMDoc, RMSF)  node → swimlane (the epochs reaching it with
                         ``has_representation_model``, or its own lanes) →
                         **publisher** (the Document) → **container** → graph
container                node → swimlane → **publisher** (author, licence;
                         never a date: MICRO-D-GIS-DOCUMENTI) → graph
resource, file           node → swimlane → **set** (the set it is part of:
                         ``is_sub_resource_of``, ``is_file_of``) →
                         **publisher** (the Document linking it) → graph
unit, end                node → **life** (the continuity rule) → graph
anything else            node → swimlane → graph
=======================  ====================================================

**The servile nodes** (:func:`~s3dgraphy.resolvers.provenance.masters_of`)
follow the node they serve and have no epoch of their own: a paradata group
the node of its ``has_paradata_nodegroup`` (an orphan group drawn inside an
activity, the activity); a property its owner (``has_property``, the original
owner first); an extractor or a combiner the unit(s) it feeds through a
property's ``has_data_provenance`` or a combiner's ``combines`` — several
units, their union (``min`` / ``max`` for the dates); a proxy
(``semantic_shape``) the unit of its geometry property; an annotated region
the Document of the resource it lies on. The walk stops at the first node that
is not servile. A master whose answer is the graph's is reported as the graph
level, not «via» the master.

**Sets of files** (MICRO-B-DOCUMENTI-MEDIA, 14 Nov 2026): an entry of a
catalogue (the folder of a piece, a set inside a set) inherits the dates, the
authors and the licences of the catalogue — through its parents to the set the
Document links — unless it has its own; a file of a set, once a node, inherits
from its set first. The level says ``set``; ``from_level`` the level that
answered up there (``publisher`` for the catalogue).

**Time that is not an epoch's.** An author lives (``absolute_time_start`` /
``absolute_time_end``: birth and death, node datamodel ``spatiotemporal``); an
extractor or a combiner is dated as the ACT of its author,
``data.act_start`` / ``data.act_end`` (node datamodel 1.6.45,
:func:`~s3dgraphy.resolvers.provenance.act_time`) — never the node's creation
in the software, which is the DTC's, and never invented.

**The life of a unit** (:mod:`s3dgraphy.unit_life`): a real unit — the
``family`` the node datamodel declares for its subtype (US, SF, RSF, serSU,
serUSD, USD, TSU, UL, USN, USNt) — lives until a continuity closes it — «still
existing» otherwise, never «unknown»; any other unit (the virtual family)
lives in its epoch and a continuity extends it. The epochs of the life are
computed (a new phase between birth and end is inherited without ticking it);
a continuity is dated by its own ``absolute_time_end`` (or
``absolute_time_start``), else «chiusa nell'epoca X, data della fine non
indicata».

**The limit of an epoch is not an end** (MICRO-C-CORREZIONI-ED): when a
unit «ends» because its epoch ends, the year is the limit of the epoch —
``unit_life`` says ``end_kind == "epoch_limit"`` and ``end_limit_of``, the
resolver ``bound: "epoch_limit"`` and ``limit_of`` («vive nell'epoca II A.D.
(limite dell'epoca: 199)»); ``end_kind == "dated"`` / ``bound: "date"`` only
for a date written somewhere (a dated continuity). The chronology says where
a pushed TPQ / TAQ was born (``start_root`` / ``end_root``): «TAQ · is_after
USV101 — limite dell'epoca II A.D.». :mod:`s3dgraphy.attribution` reads the same rules for the
epochs a node is attributed to (``epoch_attribution``), the redundant lane
edges and the bulk clean (``redundancy_report``, ``plan_clean``,
``clean_redundant``) and the dating warnings (``dating_warnings``).

**The Document's date never passes to the container** (MICRO-D-GIS-DOCUMENTI,
E.D. 15 Nov 2026): the Document that publishes a container gives it its author
and its licence, never its date nor its epochs — a container's own epoch is
an epoch reaching it (``alternatives.container_own_epochs``, em_visual_rules
1.6.47); :mod:`s3dgraphy.attribution` reads no epoch of a container from its
publisher either.

**Licences that keep a node in the study** (MICRO-D-GIS-DOCUMENTI): the value
``EM-STUDY-ONLY`` («uso di studio, non pubblicabile»,
:data:`s3dgraphy.rights.STUDY_ONLY_LICENSE`) is written on a Document — a
cadastre lent by an archive — and read with this walk:
:func:`s3dgraphy.rights.publishable` answers for a sheet (a file of the
Document's GIS set: ``set`` → ``publisher``) as for the Document, and
:func:`s3dgraphy.dissemination.publishable_view` leaves those nodes out of the
Heriverse payload (``withheld`` says which and why).

**One door, a document always dated** (MICRO-E-PORTA-VERSIONI-COLORI, E.D.
15–16 Nov 2026): :func:`s3dgraphy.door.bring_in` brings files into ONE
Document — a new ``D.nn`` or one there — and refuses one without a date
(``data.absolute_time_start``, «Quando è stato fatto questo documento?»). The
epoch a model represents is another answer: it goes to the model
(``EpochNode ──has_representation_model──▶ RM``), never to the Document, so the
walk above never reads a model's epoch as its Document's date (D.09: made in
2026, representing the II A.D.). A file already in the graph is published by
the Document, not duplicated; a mesh brought in with a tileset can be its
source (a ``tiling`` step, :func:`~s3dgraphy.resources.graph_compose.declare_tileset_master`).

**A master replaced** (MICRO-E): :func:`s3dgraphy.resources.master_swap.replace_master`
points the model at a new master and records it with the DTC's own
``transformation`` (``technique: "master replacement"``, who and when); the old
master stays with the Documents that published the model (``has_linked_resource``),
and its versions carry ``data.regenerate`` — every target counts them missing,
never the master in their place. :func:`~s3dgraphy.resources.master_swap.promote_version`
makes the richest version the master.

**Colour schemes** (MICRO-E): :mod:`s3dgraphy.color_schemes` reads and writes
EM Tools' ``.emc`` (``{metadata: {property_name, …}, color_mapping: {value:
[r, g, b, a]}}``, Blender's scene-linear floats, gamma 2.2) and spreads its
scales (``em_color_ramps.json``) as EM Tools does; a property scheme is a VIEW,
never written in the graph. The epochs' colours are the graph's
(``data.color``).

**One way of numbering the Documents** (MICRO-F-BUCKET-E-TILESET, E.D. 16 Nov
2026): :func:`s3dgraphy.document_names.next_document_name` is the highest
``D.nn`` + 1, never the first free one, in the graph's spelling (D.01…D.70 →
D.71). A number used and then deleted does not come back: when a numbered
Document leaves the graph (:meth:`~s3dgraphy.graph.Graph.remove_node`) its
number is kept in ``graph.data["document_number_max"]``. The door, the GIS
documents and the series hints all ask it; EMStudio's ``naming.ts`` replicates
it with a parity check.

**A tileset dropped passes by the door** (MICRO-F): what its preview read — the
packaging (an archive, a folder's ``tileset.json``), the digest (a resource
with one is resident), the size, a name only when the drop came with no path —
travels with the file into :func:`s3dgraphy.door.bring_in`; the epoch it
represents goes to its model as for any model. A bucket's object
(:meth:`~s3dgraphy.resources.object_store.ObjectStore.listing`: one level, a
page at a time, a search by name) enters by its ``s3://`` address and stays in
the bucket.

**The sheet says where it writes** (MICRO-J-SCHEDA-SPEC-VOCABOLARI, E.D. 17 Nov
2026; nodes 1.6.47, qualia 1.6.12, translations 1.17). Recording and revision
are ACTS to trace: an ``ActivityNodeGroup`` with ``data.act_kind`` (excavation,
recording, revision — the module em-documentation-act of
ExtendedMatrix/vocabularies), ``data.act_start`` (the time of the act, as on
extractors and combiners) and its author by ``has_author``; the unit
``is_in_activity`` of it. An activity without ``act_kind`` is a narrative one,
as before, and a view that draws activities as boxes leaves an act out. The
unit carries its record's status (``data.record_status``: from_field, revised).
The sign of a recording-sheet box (``data.scheda``, ``data.scheda_links``) is
declared on the node datamodel (kind ``sheet_sign``). The levels of a place
(``LocationNodeGroup.level``) have their names in em-place-level, ``ambiente``
among them (kind functional).

**One node, two texts** (MICRO-K-DEFINIZIONE-E-PASSI, E.D. 17 Nov 2026;
nodes 1.6.48, qualia 1.6.13 — withdraws the rule of MICRO-J §C): the
DEFINITION is the VALUE of the unit's PropertyNode ``definition``, a short
sentence with its chain; a term may classify it on the same node
(``data.concept``); the INTERPRETATION is the DESCRIPTION of that node, none
while it equals the value; the DESCRIPTION of the unit is its own field. The
element ``data.definition`` is deprecated and still read. Read by
:mod:`s3dgraphy.definition`; RDF types the unit from the concept.

**The chronology reads the life** (MICRO-K §B2): ``Graph.chronology`` takes a
unit's base bounds from :func:`s3dgraphy.unit_life.unit_life` (relation
``unit_life``), so a unit still existing ends at the limit of the latest
epoch, not of the epochs ticked by hand.

Custom rules
------------

Add a project-specific propagative property without touching s3dgraphy
core::

    MATERIAL_RULE = PropagationRule(
        id="material",
        label="Material",
        node_getter=lambda g, n: _read_prop(g, n, "material_type"),
        swimlane_getter=lambda g, e: _read_prop(g, e, "material_type"),
        graph_getter=lambda g: g.attributes.get("project_material"),
    )
    register_rule(MATERIAL_RULE)

    val = resolve(graph, node, MATERIAL_RULE)

Use :func:`register_rule` / :func:`unregister_rule` / :func:`get_rule` /
:func:`list_rules` from :mod:`s3dgraphy.resolvers` to manage the
registry.

See also
--------

- :doc:`/internals/temporal` — the Temporal Inference Engine (Layer B)
  that uses the temporal rules registered here to seed TPQ/TAQ closure
  through stratigraphic relations.
- :doc:`/internals/transforms` — the ``compact`` transform that
  *promotes* per-node declarations to swimlane-level once the resolver
  reports they are redundant.
- :doc:`/api/diagnostics` — ``attribute_property_node`` /
  ``attribute_temporal_claim`` walk the same provenance chain to
  attribute a value to *who* asserted it.

API Reference
-------------

.. autodata:: s3dgraphy.resolvers.PropagationRule
   :annotation:

See :doc:`/api/resolvers` for the full autodoc of
:mod:`s3dgraphy.resolvers.property_resolver` and
:mod:`s3dgraphy.resolvers.builtin_rules`.

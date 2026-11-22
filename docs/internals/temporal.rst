Temporal Inference Engine
=========================

.. versionadded:: 1.5.0

.. module:: s3dgraphy.temporal

The :mod:`s3dgraphy.temporal` package implements *Layer B* of DP-32 —
the **TPQ / TAQ closure** that converts topological stratigraphic
relations (``cuts``, ``overlies``, ``fills``) into temporal direction
(``is_after`` / ``is_before``) and computes the earliest / latest
plausible date of every stratigraphic unit by BFS over the resulting
DAG.

Two cooperating components
--------------------------

:class:`s3dgraphy.temporal.inference_engine.TemporalInferenceEngine`
    Topology-to-temporal mapping plus transitive reduction (NetworkX).
    Given a graph with ``cuts`` / ``overlies`` / ``fills`` edges, the
    engine returns the minimal set of ``is_after`` edges that captures
    the same temporal order, dropping the redundant ones.

:meth:`Graph.calculate_chronology`
    The high-level entry point used by chronology consumers. Internally:

    #. Seeds **node-level** TPQ/TAQ from PropertyNodes named
       ``absolute_time_start`` / ``absolute_time_end`` via the
       resolver registered in :doc:`/internals/propagation`.
    #. Seeds **swimlane-level** TPQ/TAQ from EpochNode
       ``start_time`` / ``end_time`` (header) or from a PropertyNode
       attached to the epoch (SL_PD override — the resolver prefers
       this over the header).
    #. Runs BFS over the inferred temporal DAG, propagating
       ``CALCUL_START_T`` (max of upstream TPQs) and ``CALCUL_END_T``
       (min of downstream TAQs) until fixpoint.
    #. Surfaces ``[chronology paradox]`` warnings with attribution
       (see :doc:`/api/diagnostics`) when propagation forces a node's
       window to be empty or inverted.

Topological-to-temporal mapping
-------------------------------

The current canonical table lives in
:attr:`TemporalInferenceEngine.TOPOLOGICAL_TO_TEMPORAL`:

================================  =========================================
Edge type                          Temporal direction
================================  =========================================
``cuts``                           source is more recent
``is_cut_by``                      target is more recent
``overlies``                       source is more recent
``is_overlain_by``                 target is more recent
``fills``                          source is more recent
``is_filled_by``                   target is more recent
``abuts``                          source is more recent (1.6.58)
``is_abutted_by``                  target is more recent (1.6.58)
``is_bonded_to`` / ``bonded_to``   contemporary (no temporal direction)
``is_physically_equal_to`` /       contemporary (no temporal direction)
``equals``
================================  =========================================

Edges that are already ``is_after`` (or ``is_before``) are absorbed
into the DAG without re-derivation. The contemporary relations
(``bonded_to``, ``equals``: ``implies has_same_time``, 1.6.48) give a
``has_same_time``, never an order. ``abuts`` was among them from 1.6.48 to
1.6.57; since 1.6.58 (E.D., 22 Nov 2026, MICRO-LG3b) it is POSTERIORITY: the
unit that abuts leans against one already there, so it is more recent.

attribute_temporal_claim
------------------------

The temporal layer relies on :func:`attribute_temporal_claim` (in
:mod:`s3dgraphy.diagnostics`) to answer the question *"who asserted
this temporal seed?"* whenever a paradox is detected. Resolution order:

#. Direct ``has_author`` on the temporal PropertyNode.
#. A sibling :class:`ExtractorNode` in the containing
   :class:`ParadataNodeGroup` and *its* ``has_author``.
#. The PropertyNode's host swimlane (epoch).

The returned tuple ``(display, kind, author_uuid)`` is appended to the
``[chronology paradox]`` warning as
``[attributed to <name> (<kind>)]`` so the user can tell whether to
audit the original document author (``kind = "author"``) or the AI
extractor that produced the bad inference
(``kind = "extractor"``).

Stratigraphic cycle detection
-----------------------------

``Graph.calculate_chronology()`` runs
:func:`s3dgraphy.diagnostics.detect_stratigraphic_cycles` before the
TPQ/TAQ propagation pass. The detector runs Tarjan SCC over
``is_after`` / ``cuts`` / ``overlies`` / ``fills`` / ``is_before``
edges and appends one ``[stratigraphic cycle]`` warning per loop, with
per-node attribution. The propagation BFS already survived cycles via
a visited set, but the user must be notified — AI extractors
occasionally close these loops.

Worked example — temporal closure
---------------------------------

.. code-block:: text

   US005  --overlies-->  US003           # construction order
   US005  --has_property-->  PN("absolute_time_start" = -80)
   US001  --has_property-->  PN("absolute_time_end"   = -120)
   US005  --cuts-->     US001             # foundation trench cuts US001
   US001  --has_first_epoch-->  EP_HELLENISTIC (end_time = -100)

For ``graph.calculate_chronology()``:

#. Engine maps ``overlies`` → US005 more recent than US003;
   ``cuts`` → US005 more recent than US001.
#. Seeds: US005 TPQ = −80; US001 TAQ = −120 (node-level);
   US001 TAQ also constrained by swimlane to −100.
#. BFS: US005 inherits ``CALCUL_END_T`` no later than −80 (own TPQ
   becomes the floor); US003 inherits no later than US005's end;
   US001 inherits no earlier than US005's start (TPQ propagates
   backward via ``is_after``).
#. Paradox check: US001 has TPQ ≤ −80 (from cuts ▸ US005) but TAQ
   = −120 — the unit's window is empty. A
   ``[chronology paradox]`` warning is emitted with attribution.

Why a Layer B at all?
---------------------

Topological edges are *what archaeologists see in the trench*;
temporal direction is *what we infer about time*. Keeping them as
separate edge types in s3dgraphy (``cuts`` vs ``is_after``) lets the
graph faithfully record both layers — the engine derives one from
the other on demand, with transitive reduction so the DAG stays
readable.

API Reference
-------------

.. automodule:: s3dgraphy.temporal.inference_engine
   :members:
   :undoc-members:
   :show-inheritance:

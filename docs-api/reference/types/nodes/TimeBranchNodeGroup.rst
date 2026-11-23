.. _type-TimeBranchNodeGroup:

TimeBranchNodeGroup
===================

.. note::

   Generated from the datamodels (nodes 1.6.56, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*An alternative timeline aggregating a set of mutually exclusive beliefs about a temporal interval.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``TimeBranchNodeGroup``
   * - node_type
     - ``TimeBranchNodeGroup``
   * - Parent
     - :ref:`GroupNode <type-GroupNode>`
   * - Label (en)
     - Time Branch Node Group
   * - Label (it)
     - Gruppo di ramo temporale
   * - CIDOC
     - ``E4 Period``

Description
-----------

An alternative timeline aggregating a set of mutually exclusive beliefs about a temporal interval. Two TimeBranch instances can be connected via em:contrastsWith (symmetric) to express alternative reconstructions of the same period. The Period nature (E4) anchors temporal identity; the alternative-set semantic is captured by contrastsWith.

*Italiano*: Una linea temporale alternativa che aggrega un insieme di convinzioni mutuamente esclusive su un intervallo temporale. Due istanze di TimeBranch possono essere collegate tramite em:contrastsWith (simmetrica) per esprimere ricostruzioni alternative dello stesso periodo. La natura di Period (E4) ancora l'identità temporale; la semantica di insieme alternativo è espressa da contrastsWith.

Fields
------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Field
     - Mapping / note
   * - ``name``
     - P1\_is\_identified\_by
   * - ``description``
     - P3\_has\_note

Edges
-----

**Outgoing** (this node is the source): :ref:`contrasts_with <edge-contrasts_with>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_property <edge-has_property>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`contrasts_with <edge-contrasts_with>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_timebranch <edge-has_timebranch>`, :ref:`is_in_timebranch <edge-is_in_timebranch>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='TimeBranchNodeGroup'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a TimeBranchNodeGroup") as tx:        # create: one step of undo
       nid = tx.add_node('TimeBranchNodeGroup', "name", description="…")


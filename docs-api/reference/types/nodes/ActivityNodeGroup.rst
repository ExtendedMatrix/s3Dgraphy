.. _type-ActivityNodeGroup:

ActivityNodeGroup
=================

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Group node for activities.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``ActivityNodeGroup``
   * - node_type
     - ``ActivityNodeGroup``
   * - Parent
     - :ref:`GroupNode <type-GroupNode>`
   * - Label (en)
     - Activity Node Group
   * - Label (it)
     - Gruppo di attività
   * - CIDOC
     - ``E7 Activity``

Description
-----------

Group node for activities. An activity is a logical group of actions that are kept together for a narrative purpose and information order (e.g., construction of a room of a building in year x, restoration activities of various parts of that room 20 years later).

*Italiano*: Nodo di gruppo per le attività. Un'attività è un raggruppamento logico di azioni tenute insieme per uno scopo narrativo e per l'ordinamento dell'informazione (ad es. la costruzione di un ambiente di un edificio nell'anno x, gli interventi di restauro su varie parti dello stesso ambiente 20 anni dopo).

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
   * - ``act_kind``
     - key
   * - ``act_start``
     - date
   * - ``act_end``
     - date

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`is_in_activity <edge-is_in_activity>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='ActivityNodeGroup'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a ActivityNodeGroup") as tx:        # create: one step of undo
       nid = tx.add_node('ActivityNodeGroup', "name", description="…")


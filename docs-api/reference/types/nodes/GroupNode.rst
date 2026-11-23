.. _type-GroupNode:

GroupNode
=========

.. note::

   Generated from the datamodels (nodes 1.6.55, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Node that represents a group of nodes.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``GroupNode``
   * - node_type
     - ``Group``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - GroupNode
   * - Label (it)
     - —
   * - CIDOC
     - ``E73 Information Object``

Description
-----------

Node that represents a group of nodes. These groups can be of various types: see subclasses below.

*Italiano*: Nodo che rappresenta un gruppo di nodi. Questi gruppi possono essere di vario tipo: vedi le sottoclassi qui sotto.

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

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='Group'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a Group") as tx:        # create: one step of undo
       nid = tx.add_node('Group', "name", description="…")


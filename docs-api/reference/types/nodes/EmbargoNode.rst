.. _type-EmbargoNode:

EmbargoNode
===========

.. note::

   Generated from the datamodels (nodes 1.6.56, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Represents a temporal embargo on access or distribution of a node, license, or whole graph.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``EmbargoNode``
   * - node_type
     - ``embargo``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Embargo
   * - Label (it)
     - Embargo
   * - CIDOC
     - ``E30 Right``

Description
-----------

Represents a temporal embargo on access or distribution of a node, license, or whole graph. Carries embargo\_start, embargo\_end (optional, indefinite if absent), and reason. Connected via has\_embargo edge to a Node, LicenseNode, or GraphNode.

*Italiano*: Rappresenta un embargo temporale sull'accesso o sulla diffusione di un nodo, di una licenza o dell'intero grafo. Porta embargo\_start, embargo\_end (facoltativo; se assente l'embargo è a tempo indeterminato) e reason. Collegato tramite l'arco has\_embargo a un Node, a un LicenseNode o a un GraphNode.

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
   * - ``embargo_start``
     - P82a\_begin\_of\_the\_begin
   * - ``embargo_end``
     - P82b\_end\_of\_the\_end
   * - ``reason``
     - P3\_has\_note

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_paradata_nodegroup <edge-is_in_paradata_nodegroup>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='embargo'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a embargo") as tx:        # create: one step of undo
       nid = tx.add_node('embargo', "name", description="…")


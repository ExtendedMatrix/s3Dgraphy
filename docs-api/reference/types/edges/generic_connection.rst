.. _edge-generic_connection:

generic_connection
==================

.. note::

   Generated from the datamodels (nodes 1.6.56, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Represents a non-specific connection between two nodes.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Generic connection
   * - Label (it)
     - Connessione generica
   * - Reverse
     - —
   * - Source
     - :ref:`Node <type-Node>`
   * - Target
     - :ref:`Node <type-Node>`
   * - CIDOC
     - ``P130_shows_features_of · AP11_has_physical_relation_to (is_physical_relation_from)``

Description
-----------

Represents a non-specific connection between two nodes. This is a symmetric relation.

From em
-------

.. code-block:: python

   em.graph.edges(type='generic_connection')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'generic_connection', target)    # the contract checks the pair


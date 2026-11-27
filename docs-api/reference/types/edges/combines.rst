.. _edge-combines:

combines
========

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.62) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that a node combines information from various sources.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Combines
   * - Label (it)
     - Combina
   * - Reverse
     - ``is_combined_by``
   * - Source
     - :ref:`CombinerNode <type-CombinerNode>`
   * - Target
     - :ref:`ExtractorNode <type-ExtractorNode>`
   * - CIDOC
     - ``P16_used_specific_object · J1_used_as_premise (was_premise_for)``

Description
-----------

Indicates that a node combines information from various sources.

From em
-------

.. code-block:: python

   em.graph.edges(type='combines')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'combines', target)    # the contract checks the pair


.. _edge-is_in_activity:

is_in_activity
==============

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that a node is part of a specific activity.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is in activity
   * - Label (it)
     - È nell'attività
   * - Reverse
     - ``includes_in_activity``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`ParadataNode <type-ParadataNode>`, :ref:`ParadataNodeGroup <type-ParadataNodeGroup>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`ExtractorNode <type-ExtractorNode>`, :ref:`CombinerNode <type-CombinerNode>`, :ref:`PropertyNode <type-PropertyNode>`, :ref:`AuthorNode <type-AuthorNode>`
   * - Target
     - :ref:`ActivityNodeGroup <type-ActivityNodeGroup>`
   * - CIDOC
     - ``em:isInActivity``

Description
-----------

Indicates that a node is part of a specific activity.

From em
-------

.. code-block:: python

   em.graph.edges(type='is_in_activity')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_in_activity', target)    # the contract checks the pair


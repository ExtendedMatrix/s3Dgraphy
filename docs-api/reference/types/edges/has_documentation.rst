.. _edge-has_documentation:

has_documentation
=================

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.57) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that the element has an associated documentation node.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has documentation
   * - Label (it)
     - Ha documentazione
   * - Reverse
     - ``is_documentation_of``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`SpecialFindUnit <type-SpecialFindUnit>`, :ref:`VirtualStratigraphicUnit <type-VirtualStratigraphicUnit>`, :ref:`PropertyNode <type-PropertyNode>`
   * - Target
     - :ref:`DocumentNode <type-DocumentNode>`
   * - CIDOC
     - ``P70i_is_documented_in · em:derivedFromDocument``

Description
-----------

Indicates that the element has an associated documentation node.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_documentation')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_documentation', target)    # the contract checks the pair


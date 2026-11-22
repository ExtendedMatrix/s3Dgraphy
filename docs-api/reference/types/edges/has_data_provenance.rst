.. _edge-has_data_provenance:

has_data_provenance
===================

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.57) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates the provenance of data, often linking to source nodes.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has data provenance
   * - Label (it)
     - Ha provenienza del dato
   * - Reverse
     - ``is_data_provenance_of``
   * - Source
     - :ref:`PropertyNode <type-PropertyNode>`
   * - Target
     - :ref:`ExtractorNode <type-ExtractorNode>`, :ref:`CombinerNode <type-CombinerNode>`
   * - CIDOC
     - ``P70i_is_documented_in · L22_created_derivative (was_derivative_created_by)``

Description
-----------

Indicates the provenance of data, often linking to source nodes.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_data_provenance')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_data_provenance', target)    # the contract checks the pair


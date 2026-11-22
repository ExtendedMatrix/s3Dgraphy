.. _edge-heritage_part_of:

heritage_part_of
================

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.60) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Part-whole BETWEEN Heritage Entities (HC1): the source entity forms part of the target entity — e.g.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is part of heritage entity
   * - Label (it)
     - Fa parte dell'entità patrimoniale
   * - Reverse
     - ``heritage_has_part``
   * - Source
     - :ref:`HeritageEntityNode <type-HeritageEntityNode>`
   * - Target
     - :ref:`HeritageEntityNode <type-HeritageEntityNode>`
   * - CIDOC
     - ``crm:P46i_forms_part_of · P46i_forms_part_of``

Description
-----------

Part-whole BETWEEN Heritage Entities (HC1): the source entity forms part of the target entity — e.g. the porphyry Tetrarchs (HC1) forms part of San Marco (HC1). D7.1 declares no HC1->HC1 part-whole property; modelled with CIDOC-CRM crm:P46i\_forms\_part\_of via the extension mechanism.

From em
-------

.. code-block:: python

   em.graph.edges(type='heritage_part_of')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'heritage_part_of', target)    # the contract checks the pair


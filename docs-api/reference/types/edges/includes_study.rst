.. _edge-includes_study:

includes_study
==============

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Links an HC13 Project to an HC9 Study carried out within it.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Includes study
   * - Label (it)
     - Include lo studio
   * - Reverse
     - ``is_study_of_project``
   * - Source
     - :ref:`ProjectNode <type-ProjectNode>`
   * - Target
     - :ref:`StudyNode <type-StudyNode>`
   * - CIDOC
     - ``crm:P9_consists_of · P9_consists_of``

Description
-----------

Links an HC13 Project to an HC9 Study carried out within it. D7.1 defines no direct HC13->HC9 property; modelled with CIDOC-CRM crm:P9\_consists\_of (activity/period composition) via the extension mechanism — consistent with HDT-O HP20 'was carried out under' being a subproperty of crm:P9i.

From em
-------

.. code-block:: python

   em.graph.edges(type='includes_study')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'includes_study', target)    # the contract checks the pair


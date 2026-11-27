.. _edge-study_about_heritage:

study_about_heritage
====================

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.62) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Links an HC9 Study to the HC1 Heritage Entity it investigated.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Study is about heritage entity
   * - Label (it)
     - Lo studio riguarda l'entità patrimoniale
   * - Reverse
     - ``was_subject_of_study``
   * - Source
     - :ref:`StudyNode <type-StudyNode>`
   * - Target
     - :ref:`HeritageEntityNode <type-HeritageEntityNode>`
   * - CIDOC
     - ``hdto:HP23_was_about · P16_used_specific_object``

Description
-----------

Links an HC9 Study to the HC1 Heritage Entity it investigated. HDT-O HP23 per ECHOES D7.1.

From em
-------

.. code-block:: python

   em.graph.edges(type='study_about_heritage')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'study_about_heritage', target)    # the contract checks the pair


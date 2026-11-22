.. _edge-study_produced_proposition_set:

study_produced_proposition_set
==============================

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.60) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Links an HC9 Study to the documentary output it created — in EM the proposition set (HC16 / em:EMGraph / GraphNode).*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Study produced proposition set
   * - Label (it)
     - Lo studio ha prodotto un insieme di proposizioni
   * - Reverse
     - ``was_created_by_study``
   * - Source
     - :ref:`StudyNode <type-StudyNode>`
   * - Target
     - :ref:`GraphNode <type-GraphNode>`
   * - CIDOC
     - ``hdto:HP25_has_created · P94_has_created``

Description
-----------

Links an HC9 Study to the documentary output it created — in EM the proposition set (HC16 / em:EMGraph / GraphNode). HDT-O HP25 per ECHOES D7.1.

From em
-------

.. code-block:: python

   em.graph.edges(type='study_produced_proposition_set')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'study_produced_proposition_set', target)    # the contract checks the pair


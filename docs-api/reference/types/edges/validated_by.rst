.. _edge-validated_by:

validated_by
============

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A HUMAN author endorses a piece of content: they have read it and put their name to it.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Validated by
   * - Label (it)
     - Validato da
   * - Reverse
     - ``validated``
   * - Source
     - :ref:`NarrativeNode <type-NarrativeNode>`
   * - Target
     - :ref:`AuthorNode <type-AuthorNode>`
   * - CIDOC
     - ``prov:wasInfluencedBy · em:validatedBy``

Description
-----------

A HUMAN author endorses a piece of content: they have read it and put their name to it. Introduced for EM Narrative (N4) to carry the act at the heart of 'Who Made This?': a machine may draft, but only a person can vouch. Until this edge exists, AI-authored content is a draft and says so — the absence of the edge IS the unendorsed state, so nothing can claim endorsement it has not received.

From em
-------

.. code-block:: python

   em.graph.edges(type='validated_by')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'validated_by', target)    # the contract checks the pair


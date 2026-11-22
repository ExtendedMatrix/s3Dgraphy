.. _edge-has_gcp_set:

has_gcp_set
===========

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A RegistrationTransform was solved from a GCPSet — the evidence behind the placement.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Solved from control points
   * - Label (it)
     - Risolto da punti di controllo
   * - Reverse
     - ``controlled_registration``
   * - Source
     - :ref:`RegistrationTransformNode <type-RegistrationTransformNode>`
   * - Target
     - :ref:`GCPSetNode <type-GCPSetNode>`
   * - CIDOC
     - ``L21_used_as_derivation_source · prov:wasDerivedFrom``

Description
-----------

A RegistrationTransform was solved from a GCPSet — the evidence behind the placement. Present ONLY in absolute mode: a transform with no such edge is a site-local frame, and the missing edge is what tells a reader so without having to trust a flag.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_gcp_set')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_gcp_set', target)    # the contract checks the pair


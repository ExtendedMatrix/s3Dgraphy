.. _edge-has_registration_transform:

has_registration_transform
==========================

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.57) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A produced RESOURCE (a reconstructed model) is placed in space by a RegistrationTransform — the 7-parameter similarity solved for it.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Placed by
   * - Label (it)
     - Posizionato da
   * - Reverse
     - ``places``
   * - Source
     - :ref:`ResourceNode <type-ResourceNode>`
   * - Target
     - :ref:`RegistrationTransformNode <type-RegistrationTransformNode>`
   * - CIDOC
     - ``P67i_is_referred_to_by``

Description
-----------

A produced RESOURCE (a reconstructed model) is placed in space by a RegistrationTransform — the 7-parameter similarity solved for it. The absence of this edge is a statement too: a model nobody placed. Re-registration adds a NEW transform node and a new edge; the superseded one stays, because moving a model is provenance, not an edit.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_registration_transform')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_registration_transform', target)    # the contract checks the pair


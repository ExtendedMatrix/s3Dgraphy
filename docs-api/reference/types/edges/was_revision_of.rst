.. _edge-was_revision_of:

was_revision_of
===============

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A RESOURCE is a REVISION of an earlier resource (E.D.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Was revision of
   * - Label (it)
     - È una revisione di
   * - Reverse
     - ``had_revision``
   * - Source
     - :ref:`ResourceNode <type-ResourceNode>`, :ref:`TranslationNode <type-TranslationNode>`
   * - Target
     - :ref:`ResourceNode <type-ResourceNode>`, :ref:`TranslationNode <type-TranslationNode>`
   * - CIDOC
     - ``crmdig:L21_used_as_derivation_source · prov:wasRevisionOf``

Description
-----------

A RESOURCE is a REVISION of an earlier resource (E.D. 2026-09-30, «la revisione della risorsa»): the same thing, with one file replaced — a corrected texture. The newer resource is the source, the older the target. The older one stays as it was and citable; the revision is a new ResourceNode with the same fields and the same files but the replaced one, and the new file declares dtc\_derived\_from the old file. What pointed at the old resource (a Representation Model, a property, a document) is NOT moved by the edge nor by replace\_file: whoever calls decides. The chain is read with s3dgraphy.api.revisions\_of / current\_revision. Same name as ProjectVersion.was\_revision\_of in the em.json container, which says the same thing of a document version.

From em
-------

.. code-block:: python

   em.graph.edges(type='was_revision_of')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'was_revision_of', target)    # the contract checks the pair


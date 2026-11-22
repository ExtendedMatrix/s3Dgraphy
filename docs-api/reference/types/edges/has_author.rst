.. _edge-has_author:

has_author
==========

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Represents the connection of a node with its author.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has author
   * - Label (it)
     - Ha autore
   * - Reverse
     - ``is_author_of``
   * - Source
     - :ref:`GraphNode <type-GraphNode>`, :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`ParadataNode <type-ParadataNode>`, :ref:`GroupNode <type-GroupNode>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`ExtractorNode <type-ExtractorNode>`, :ref:`CombinerNode <type-CombinerNode>`, :ref:`PropertyNode <type-PropertyNode>`, :ref:`EpochNode <type-EpochNode>`, :ref:`DTCNode <type-DTCNode>`, :ref:`NarrativeNode <type-NarrativeNode>`, :ref:`ResourceNode <type-ResourceNode>`, :ref:`TranslationNode <type-TranslationNode>`
   * - Target
     - :ref:`AuthorNode <type-AuthorNode>`, :ref:`AuthorAINode <type-AuthorAINode>`
   * - CIDOC
     - ``prov:wasAttributedTo · em:hasAuthor``

Description
-----------

Represents the connection of a node with its author. Target can be an AuthorNode (human) or AuthorAINode (AI-assisted authoring). Source covers the full range of EM node types so that the resolver can walk from any scope level down to the author. SOURCE WIDENED 2026-08-16 (asset DTC protocol): ResourceNode joins the list. 'Who took this photograph' is exactly prov:wasAttributedTo on an information object, and the mapping is already domain-neutral — the omission was an oversight of scope, not a semantic boundary: the list exists so the resolver can walk from ANY scope down to the author, and a resource is a scope somebody attributes. It is also the shape the asset enrichment protocol needs, where the AUTHOR of the bytes (possibly absent, possibly dead) is declared by an ATTRIBUTOR who is somebody else (s3dgraphy.rights.enrich\_asset\_dtc, docs/asset-dtc-protocol.md).

From em
-------

.. code-block:: python

   em.graph.edges(type='has_author')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_author', target)    # the contract checks the pair


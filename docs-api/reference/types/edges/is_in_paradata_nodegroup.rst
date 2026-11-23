.. _edge-is_in_paradata_nodegroup:

is_in_paradata_nodegroup
========================

.. note::

   Generated from the datamodels (nodes 1.6.55, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that a node is included into a paradata node group.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is in paradata nodegroup
   * - Label (it)
     - È nel gruppo di paradati
   * - Reverse
     - ``contains_paradata_node``
   * - Source
     - :ref:`PropertyNode <type-PropertyNode>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`ExtractorNode <type-ExtractorNode>`, :ref:`CombinerNode <type-CombinerNode>`, :ref:`ParadataNode <type-ParadataNode>`, :ref:`GeoPositionNode <type-GeoPositionNode>`, :ref:`AuthorNode <type-AuthorNode>`, :ref:`LicenseNode <type-LicenseNode>`, :ref:`EmbargoNode <type-EmbargoNode>`, :ref:`RepresentationModelDocNode <type-RepresentationModelDocNode>`
   * - Target
     - :ref:`ParadataNodeGroup <type-ParadataNodeGroup>`
   * - CIDOC
     - ``P106i_forms_part_of``

Description
-----------

Indicates that a node is included into a paradata node group. Standard members are the paradata-chain nodes (PropertyNode/DocumentNode/ExtractorNode/CombinerNode/ParadataNode); GeoPositionNode is additionally admitted so the per-graph georeferencing shift can be a member of the graph-scope ParadataNodeGroup (DP-65) — semantically valid only at graph scope. v1.6.8 (MIG1-A): source widened further with AuthorNode/LicenseNode/EmbargoNode so the graph-scope rights metadata (author/license/embargo) live as first-class member nodes of the graph-scope ParadataNodeGroup (DP-65), replacing the legacy graph.data['author\_name'/'license'/'embargo'] fields — again meaningful at graph scope (anchored on the GraphNode via has\_paradata\_nodegroup).

From em
-------

.. code-block:: python

   em.graph.edges(type='is_in_paradata_nodegroup')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_in_paradata_nodegroup', target)    # the contract checks the pair


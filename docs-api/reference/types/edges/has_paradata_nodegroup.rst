.. _edge-has_paradata_nodegroup:

has_paradata_nodegroup
======================

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that a node belongs to a paradata node group.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has paradata nodegroup
   * - Label (it)
     - Ha gruppo di paradati
   * - Reverse
     - ``is_paradata_nodegroup_of``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`EpochNode <type-EpochNode>`, :ref:`GraphNode <type-GraphNode>`
   * - Target
     - :ref:`ParadataNodeGroup <type-ParadataNodeGroup>`
   * - CIDOC
     - ``P129i_is_subject_of``

Description
-----------

Indicates that a node belongs to a paradata node group. v1.6.8 (MIG1-A): source widened with GraphNode so the graph itself (GraphNode = the graph-self node) can own the graph-scope ParadataNodeGroup (DP-65) that holds the author/license/embargo member nodes — mirroring how a StratigraphicNode or an EpochNode carries its own paradata group.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_paradata_nodegroup')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_paradata_nodegroup', target)    # the contract checks the pair


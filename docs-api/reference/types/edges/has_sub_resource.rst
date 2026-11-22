.. _edge-has_sub_resource:

has_sub_resource
================

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.60) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A SET of files (a ResourceNode: a directory, a logical group) HAS A SET of files AS ITS PART (E.D.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has sub-resource
   * - Label (it)
     - Ha come parte l'insieme
   * - Reverse
     - ``is_sub_resource_of``
   * - Source
     - :ref:`ResourceNode <type-ResourceNode>`
   * - Target
     - :ref:`ResourceNode <type-ResourceNode>`
   * - CIDOC
     - ``P106_is_composed_of · prov:hadMember``

Description
-----------

A SET of files (a ResourceNode: a directory, a logical group) HAS A SET of files AS ITS PART (E.D. 2026-11-14, «insiemi dentro insiemi»): the folder of a piece is part of its category, the category of the lapidary; a logical group (a selection made in the viewer, with a name and a role) can be part of a set. The edge carries in its \`attributes\` the PATH of the child under its parent (\`path\`, e.g. 'Blocchi/18383'), as has\_file carries a file's. The tree is read by s3dgraphy.resources.sets (sub\_resources, set\_tree, tree\_rows) and is the tree of a CATALOGUE (s3dgraphy.resources.catalog): the document links the root, the leaves are its entries, cited «D.30 · 18383». Never a cycle.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_sub_resource')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_sub_resource', target)    # the contract checks the pair


.. _edge-has_file:

has_file
========

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.60) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A RESOURCE (the set, the handle a person stamps, cites and opens) has ONE OF ITS FILES (E.D.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has file
   * - Label (it)
     - Ha il file
   * - Reverse
     - ``is_file_of``
   * - Source
     - :ref:`ResourceNode <type-ResourceNode>`
   * - Target
     - :ref:`ResourceFileNode <type-ResourceFileNode>`
   * - CIDOC
     - ``P106_is_composed_of · prov:hadMember``

Description
-----------

A RESOURCE (the set, the handle a person stamps, cites and opens) has ONE OF ITS FILES (E.D. 2026-09-30, «la risorsa e i suoi file»). The edge — not the file — carries in its \`attributes\` the ROLE (\`entry\_point\`: the file a reader opens first, e.g. the obj or tileset.json; \`member\`: a file the entry point calls, e.g. the mtl and the textures) and the PATH relative to the entry point's location (\`path\`, e.g. 'textures/T\_OB\_PODIO\_LOD1.jpg'), because the same file sits in N resources under N different paths. With ONE file the edge is implicit and not written: the ResourceNode's own url and checksum are that file.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_file')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_file', target)    # the contract checks the pair


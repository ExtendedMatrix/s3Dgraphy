.. _type-ResourceFileNode:

ResourceFileNode
================

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*ONE FILE of a resource (E.D.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``ResourceFileNode``
   * - node_type
     - ``resource_file``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Resource file
   * - Label (it)
     - File della risorsa
   * - CIDOC
     - ``crmdig:D1_Digital_Object``

Description
-----------

ONE FILE of a resource (E.D. 2026-09-30, «la risorsa e i suoi file»): the ResourceNode is the SET — the handle a person stamps, cites and opens, with name, kind, scope, residency, role, tier, packaging and rights — and the ResourceFileNode is each member: an obj, its mtl and its textures are three files of one resource. Reached by has\_file (reverse is\_file\_of); the ROLE (entry\_point \| member) and the RELATIVE PATH travel on the EDGE, because the same file (a corrected texture) sits in N resources under N paths. With ONE file the node is IMPLICIT: a ResourceNode with url (and checksum) and no has\_file is a resource of one file, and s3dgraphy.resources.files.resource\_files shows that file anyway; the node is written only when there are several files or the one file has a stamp or an identity of its own. Fields: url (a path, a file:// / s3:// / http(s):// URI or a blend:// locator), checksum ('sha256:<hex>'; 'emstruct1:<hex>' for a datablock, comparable not verifiable), size\_bytes, media\_type. For a datablock blend\_file and datablock are READ from the blend:// locator (resources/resolver.py, the one place that knows its form), never stored twice. The same file in several resources is ONE node, recognised by its checksum.

*Italiano*: UN FILE di una risorsa (E.D. 30 set 2026, «la risorsa e i suoi file»): il ResourceNode è l'INSIEME — la maniglia che si timbra, si cita e si apre — e il ResourceFileNode è ogni membro: un obj, il suo mtl e le sue texture sono tre file di una risorsa sola. Raggiunto da has\_file; il RUOLO (entry\_point \| member) e il PERCORSO RELATIVO stanno sull'ARCO, perché lo stesso file sta in più risorse con percorsi diversi. Con UN file il nodo è IMPLICITO: url e checksum restano sul ResourceNode. Per un datablock blend\_file e datablock si leggono dal locator blend://, mai scritti due volte.

Fields
------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Field
     - Mapping / note
   * - ``media_role``
     - —
   * - ``name``
     - P1\_is\_identified\_by
   * - ``description``
     - P3\_has\_note
   * - ``url``
     - P1\_is\_identified\_by
   * - ``checksum``
     - em:checksum
   * - ``media_type``
     - P2\_has\_type

Edges
-----

**Outgoing** (this node is the source): :ref:`dtc_derived_from <edge-dtc_derived_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`dtc_derived_from <edge-dtc_derived_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_file <edge-has_file>`, :ref:`is_on_resource <edge-is_on_resource>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='resource_file'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a resource_file") as tx:        # create: one step of undo
       nid = tx.add_node('resource_file', "name", description="…")


.. _type-AnnotationRegionNode:

AnnotationRegionNode
====================

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.62) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*The PLACE A READING LOOKED AT, in the source it read (geometry\_kind): a region of one image or page in NORMALISED image coordinates [0,1] (region2d, the default: shape\_kind rect\|polygon, rect [x,y,w,h] or points [[x,y], ...], page index), a passage of a text (passage: start, end, text — character offsets plus the quoted words), or a point, a line or an open polyline on a 3D model (point\|line\|poly…*

.. list-table::
   :widths: 25 75

   * - Class
     - ``AnnotationRegionNode``
   * - node_type
     - ``annotation_region``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Annotation Region
   * - Label (it)
     - Regione di annotazione
   * - CIDOC
     - ``E36 Visual Item``

Description
-----------

The PLACE A READING LOOKED AT, in the source it read (geometry\_kind): a region of one image or page in NORMALISED image coordinates [0,1] (region2d, the default: shape\_kind rect\|polygon, rect [x,y,w,h] or points [[x,y], ...], page index), a passage of a text (passage: start, end, text — character offsets plus the quoted words), or a point, a line or an open polyline on a 3D model (point\|line\|polyline), or a volume on it (volume: an annotation on the asset whose convex hulls and spheres are the SemanticShape it reaches with has\_semantic\_shape, node datamodel 1.6.16). For the 3D kinds the vertices ARE in the node (node datamodel 1.6.15): data.coords with crs and, for a line or a polyline, the length with its unit — up to coords.inline\_max\_vertices, above which they go to a .glb resource (has\_linked\_resource). Attached to what it is on (the image, the document, the model) with is\_on\_resource, read by an extractor with extracted\_from, and the precise target of has\_visual\_reference from a PropertyNode.

*Italiano*: Il LUOGO IN CUI UNA LETTURA HA GUARDATO, nella fonte che ha letto (geometry\_kind): una regione di un'immagine o di una pagina in coordinate immagine NORMALIZZATE [0,1] (region2d, il predefinito: shape\_kind rect\|polygon, rect [x,y,w,h] o points [[x,y], ...], indice di pagina), un passo di un testo (passage: start, end, text — offset dei caratteri più le parole citate), oppure un punto, una linea o una polilinea aperta su un modello 3D (point\|line\|polyline). Per i tipi 3D le coordinate NON stanno nel nodo: sono un .glb collegato con has\_semantic\_shape, come il payload di un proxy; il nodo conserva vertex\_count e, per una linea o una polilinea, la lunghezza con la sua unità e il suo crs. Collegato a ciò su cui si trova (l'immagine, il documento, il modello) con is\_on\_resource, letto da un estrattore con extracted\_from, ed è il bersaglio preciso di has\_visual\_reference da un PropertyNode.

Fields
------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Field
     - Mapping / note
   * - ``name``
     - P1\_is\_identified\_by
   * - ``description``
     - P3\_has\_note
   * - ``shape_kind``
     - P2\_has\_type
   * - ``selector``
     - em:hasSelector
   * - ``page``
     - em:onPage
   * - ``resource_id``
     - P106i\_forms\_part\_of
   * - ``geometry_kind``
     - P2\_has\_type
   * - ``start``
     - em:hasSelector (char=start,end)
   * - ``end``
     - em:hasSelector (char=start,end)
   * - ``text``
     - oa:hasSelector -> oa:TextQuoteSelector (oa:exact), at <region>/quote
   * - ``coords``
     - geo:hasGeometry -> geo:Geometry at <region>/geometry, geo:asWKT '<CRS IRI> POINT Z (x y z)' \| 'MULTIPOINT Z (...)' \| 'LINESTRING Z (...)'^^geo:wktLiteral (GeoSPARQL 1.1); the CRS IRI is em:LocalSceneFrame for crs 'local', http://www.opengis.net/def/crs/EPSG/0/<n> for 'EPSG:<n>'
   * - ``vertex_count``
     - em:vertexCount
   * - ``length``
     - crm:P43\_has\_dimension -> crm:E54\_Dimension at <region>/length (P2\_has\_type 'length', P90\_has\_value xsd:double)
   * - ``unit``
     - P91\_has\_unit on the E54 -> QUDT unit IRI (m, cm, mm, km), else s3d:unit\_<u>
   * - ``crs``
     - em:crs
   * - ``area``
     - 1.6.50 · surface: crm:P43\_has\_dimension -> crm:E54\_Dimension at <region>/area (P2\_has\_type 'area', P90\_has\_value xsd:double, P91\_has\_unit the area\_unit -> QUDT M2 \| CentiM2 \| MilliM2 \| KiloM2)
   * - ``perimeter``
     - 1.6.50 · surface: crm:P43\_has\_dimension -> crm:E54\_Dimension at <region>/perimeter (P2\_has\_type 'perimeter', P91\_has\_unit the unit)
   * - ``area_unit``
     - 1.6.50 · the unit of the area: the unit squared (m2)

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_on_resource <edge-is_on_resource>`

**Incoming** (this node is the target): :ref:`extracted_from <edge-extracted_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_visual_reference <edge-has_visual_reference>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='annotation_region'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a annotation_region") as tx:        # create: one step of undo
       nid = tx.add_node('annotation_region', "name", description="…")


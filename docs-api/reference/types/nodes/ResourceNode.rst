.. _type-ResourceNode:

ResourceNode
============

.. note::

   Generated from the datamodels (nodes 1.6.55, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Class to represent a link node (ResourceNode) in the graph.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``ResourceNode``
   * - node_type
     - ``resource``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Link
   * - Label (it)
     - Collegamento
   * - CIDOC
     - ``E73 Information Object``

Description
-----------

Class to represent a link node (ResourceNode) in the graph. Attributes: url (str): URL of the link. url\_type (str): Type of URL (e.g., 'External link', 'Image'). description (str): Description of the link.

*Italiano*: Classe che rappresenta un nodo collegamento (ResourceNode) nel grafo. Attributi: url (str): URL del collegamento. url\_type (str): tipo di URL (ad es. 'External link', 'Image'). description (str): descrizione del collegamento.

Fields
------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Field
     - Mapping / note
   * - ``members``
     - —
   * - ``members_from``
     - —
   * - ``media_role``
     - —
   * - ``name``
     - P1\_is\_identified\_by
   * - ``description``
     - P3\_has\_note
   * - ``url``
     - P1\_is\_identified\_by
   * - ``url_type``
     - P2\_has\_type
   * - ``checksum``
     - em:checksum
   * - ``scope``
     - em:resourceScope
   * - ``residency``
     - em:residency
   * - ``packaging``
     - em:packaging
   * - ``tier``
     - em:tier
   * - ``master_kind``
     - em:masterKind
   * - ``digest_covers``
     - em:digestCovers
   * - ``members_digest``
     - em:membersDigest
   * - ``content_digest``
     - em:contentDigest
   * - ``addresses``
     - em:hasAddress
   * - ``addresses.locator``
     - em:locator
   * - ``addresses.checked_at``
     - em:checkedAt
   * - ``addresses.ok``
     - em:reachable
   * - ``checksum_at``
     - em:checksumAt
   * - ``lang``
     - dcterms:language
   * - ``lod_level``
     - em:lodLevel
   * - ``use``
     - em:use
   * - ``tris_per_m2``
     - em:trisPerM2
   * - ``texel_density_dd``
     - em:texelDensityDD
   * - ``texture_count``
     - em:textureCount
   * - ``texture_side_px``
     - em:textureSidePx
   * - ``uv_ratio``
     - em:uvRatio
   * - ``reduction_from_lod0``
     - em:reductionFromLod0
   * - ``geometric_error_m``
     - em:geometricErrorM
   * - ``frame``
     - —
   * - ``gis_format``
     - —
   * - ``crs``
     - —
   * - ``bbox``
     - —
   * - ``bbox_wgs84``
     - —
   * - ``layer``
     - —
   * - ``feature_key``
     - —
   * - ``z_field``
     - —
   * - ``geometry_type``
     - —
   * - ``feature_count``
     - —
   * - ``z_range``
     - —
   * - ``raster``
     - —

Edges
-----

**Outgoing** (this node is the source): :ref:`dtc_derived_from <edge-dtc_derived_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_file <edge-has_file>`, :ref:`has_license <edge-has_license>`, :ref:`has_registration_transform <edge-has_registration_transform>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_sub_resource <edge-has_sub_resource>`, :ref:`has_translation <edge-has_translation>`, :ref:`was_revision_of <edge-was_revision_of>`

**Incoming** (this node is the target): :ref:`dtc_derived_from <edge-dtc_derived_from>`, :ref:`dtc_had_input <edge-dtc_had_input>`, :ref:`dtc_had_output <edge-dtc_had_output>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_digital_object_part <edge-has_digital_object_part>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_sub_resource <edge-has_sub_resource>`, :ref:`has_visual_reference <edge-has_visual_reference>`, :ref:`is_on_resource <edge-is_on_resource>`, :ref:`was_revision_of <edge-was_revision_of>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='resource'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a resource") as tx:        # create: one step of undo
       nid = tx.add_node('resource', "name", description="…")


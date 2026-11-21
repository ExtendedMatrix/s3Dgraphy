.. _type-PropertyNode:

PropertyNode
============

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Node representing a property (qualia) of another node.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``PropertyNode``
   * - node_type
     - ``property``
   * - Parent
     - :ref:`ParadataNode <type-ParadataNode>`
   * - Label (en)
     - Property
   * - Label (it)
     - Proprietà
   * - CIDOC
     - ``E1 CRM Entity``

Description
-----------

Node representing a property (qualia) of another node. The CIDOC class is CONDITIONAL on the qualia type — looked up at serialization time in em\_qualia\_types.json: dimensional qualia (height/width/weight) → E54\_Dimension, typology qualia (color/style) → E55\_Type, material → E57\_Material, interpretive qualia (aesthetic\_value) → crminf:I4\_Proposition\_Set. PropertyNode itself is the structural shell (em:Qualia); the semantic class comes from the qualia type catalogue.

*Italiano*: Nodo che rappresenta una proprietà (qualia) di un altro nodo. La classe CIDOC è CONDIZIONATA dal tipo di qualia — ricavata al momento della serializzazione in em\_qualia\_types.json: qualia dimensionali (altezza/larghezza/peso) → E54\_Dimension, qualia tipologici (colore/stile) → E55\_Type, materiale → E57\_Material, qualia interpretativi (aesthetic\_value) → crminf:I4\_Proposition\_Set. PropertyNode in sé è l'involucro strutturale (em:Qualia); la classe semantica proviene dal catalogo dei tipi di qualia.

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
   * - ``url``
     - P1\_is\_identified\_by
   * - ``value``
     - P90\_has\_value
   * - ``property_type``
     - em:hasQualiaType
   * - ``concept``
     - 1.6.48 (MICRO-K §A, E.D.
   * - ``description_of_definition``
     - 1.6.48 (MICRO-K §A): on the PropertyNode \`definition\` the description is the INTERPRETATION — the argued text of the ICCD sheet box INTERPRETAZIONE — once it differs from the value.
   * - ``measure``
     - —
   * - ``unit``
     - —
   * - ``valid_from``
     - number (year, negative before the common era)
   * - ``valid_to``
     - number (year)

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_data_provenance <edge-has_data_provenance>`, :ref:`has_documentation <edge-has_documentation>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`has_visual_reference <edge-has_visual_reference>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_in_paradata_nodegroup <edge-is_in_paradata_nodegroup>`

**Incoming** (this node is the target): :ref:`extracted_from <edge-extracted_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_property <edge-has_property>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='property'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a property") as tx:        # create: one step of undo
       nid = tx.add_node('property', "name", description="…")


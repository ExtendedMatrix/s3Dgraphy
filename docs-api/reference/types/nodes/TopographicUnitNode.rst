.. _type-TopographicUnitNode:

TopographicUnitNode
===================

.. note::

   Generated from the datamodels (nodes 1.6.56, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Topographic unit: what a survey finds on the ground — a scatter of sherds, a structure cropping out, a concentration of building material.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``TopographicUnitNode``
   * - node_type
     - ``UT``
   * - Parent
     - :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`
   * - Label (en)
     - UT
   * - Label (it)
     - UT
   * - CIDOC
     - ``E26 Physical Feature``

Description
-----------

Topographic unit: what a survey finds on the ground — a scatter of sherds, a structure cropping out, a concentration of building material. OBSERVED («the topographic unit is an objective element», Landscape Matrix 2017). It is the counterpart of the stratigraphic unit at the scale of the territory but not a stratigraphic unit: it lies in secondary deposition (the ploughsoil) and has no physical relation with anything. Its extent is a geometry (a footprint property, a GIS layer); its dating is a property or an epoch, with its paradata, like a unit's.

*Italiano*: Unità topografica: ciò che il survey trova a terra — uno spargimento di frammenti, una struttura affiorante, una concentrazione di materiale edilizio. OSSERVATA («l'unità topografica è un elemento oggettivo», Landscape Matrix 2017). È il corrispettivo dell'unità stratigrafica alla scala del territorio ma non è un'unità stratigrafica: sta in giacitura secondaria (l'arativo) e non ha relazioni fisiche con nulla. La sua estensione è una geometria (una proprietà impronta, un layer GIS); la sua datazione è una proprietà o un'epoca, con i suoi paradati, come per un'unità.

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

Edges
-----

**Outgoing** (this node is the source): :ref:`changed_from <edge-changed_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_property <edge-has_property>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_in_district <edge-is_in_district>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`changed_from <edge-changed_from>`, :ref:`extracted_from <edge-extracted_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_observed_in <edge-is_observed_in>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='UT'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a UT") as tx:        # create: one step of undo
       nid = tx.add_node('UT', "name", description="…")


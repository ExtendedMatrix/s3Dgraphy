.. _type-StratigraphicUnit:

StratigraphicUnit
=================

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Stratigraphic Unit (SU) or negative stratigraphic unit.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``StratigraphicUnit``
   * - node_type
     - ``US``
   * - Parent
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Label (en)
     - US (or SU)
   * - Label (it)
     - US (o UStr)
   * - CIDOC
     - ``A2 Stratigraphic Volume Unit``

Description
-----------

Stratigraphic Unit (SU) or negative stratigraphic unit. Represents a physical stratigraphic unit (positive or negative). It corresponds to an identifiable physical layer or interface in archaeological documentation.

*Italiano*: Unità stratigrafica (US): deposito o interfaccia negativa.

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
   * - ``stratigraphic_kind``
     - The GENRE of a US, when it has one.
   * - ``source_code``
     - The CODE a US of a kind came in with, when it is not its kind's \`default\_code\` (USS for a coating, WSU for a masonry…).

Edges
-----

**Outgoing** (this node is the source): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_digital_twin <edge-has_digital_twin>`, :ref:`has_documentation <edge-has_documentation>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_paradata_nodegroup <edge-has_paradata_nodegroup>`, :ref:`has_property <edge-has_property>`, :ref:`has_representation_model <edge-has_representation_model>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_timebranch <edge-has_timebranch>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_functional_unit <edge-is_in_functional_unit>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_in_timebranch <edge-is_in_timebranch>`, :ref:`is_part_of <edge-is_part_of>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`extracted_from <edge-extracted_from>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_part_of <edge-is_part_of>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='US'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a US") as tx:        # create: one step of undo
       nid = tx.add_node('US', "name", description="…")


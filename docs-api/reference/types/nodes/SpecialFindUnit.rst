.. _type-SpecialFindUnit:

SpecialFindUnit
===============

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.60) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Movable physical object, found erratic or inside a layer and taken out during the excavation, documented WHERE IT WAS FOUND.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``SpecialFindUnit``
   * - node_type
     - ``SF``
   * - Parent
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Label (en)
     - Special Find
   * - Label (it)
     - Reperto speciale
   * - CIDOC
     - ``E19 Physical Object``

Description
-----------

Movable physical object, found erratic or inside a layer and taken out during the excavation, documented WHERE IT WAS FOUND. The definition is positive: the SF is what was observed, not an object «whose original position is unknown». The way it lay when found is an ATTRIBUTE of the find, not a class: in situ, redeposited (a process moved it there), or fallen in position (a collapse found where it fell — an accidental position, but a measurable one). A collapse found in position is an SF, never a repositioned find. Invariant against RSF: the SF is MOVABLE. Uncertain pertinence to the site is carried by paradata edges, not by class.

*Italiano*: Oggetto fisico mobile, trovato erratico o dentro uno strato e tolto durante lo scavo, documentato DOVE È STATO TROVATO. La definizione è in positivo: lo SF è ciò che si è osservato, non un oggetto «la cui posizione originaria è ignota». Il modo in cui giaceva al ritrovamento è un ATTRIBUTO del reperto, non una classe: in situ, ridepositato (un processo lo ha portato lì) o crollato in posizione (un crollo trovato dove è caduto — una posizione accidentale, ma misurabile). Un crollo trovato in posizione è uno SF, mai un reperto riposizionato. Invariante rispetto a RSF: lo SF è MOBILE. La pertinenza incerta al sito è portata dagli archi di paradati, non dalla classe.

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

**Outgoing** (this node is the source): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_digital_twin <edge-has_digital_twin>`, :ref:`has_documentation <edge-has_documentation>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_paradata_nodegroup <edge-has_paradata_nodegroup>`, :ref:`has_property <edge-has_property>`, :ref:`has_representation_model <edge-has_representation_model>`, :ref:`has_representation_model_sf <edge-has_representation_model_sf>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_timebranch <edge-has_timebranch>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_functional_unit <edge-is_in_functional_unit>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_in_timebranch <edge-is_in_timebranch>`, :ref:`is_observed_in <edge-is_observed_in>`, :ref:`is_part_of <edge-is_part_of>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`extracted_from <edge-extracted_from>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='SF'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a SF") as tx:        # create: one step of undo
       nid = tx.add_node('SF', "name", description="…")


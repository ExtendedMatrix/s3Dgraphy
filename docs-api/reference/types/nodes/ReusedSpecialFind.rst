.. _type-ReusedSpecialFind:

ReusedSpecialFind
=================

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Repositioned Special Find: a physical object, FIXED and IMMOVABLE, INTENTIONALLY put back into a stable unit — a wall (spolia: a Roman column in a medieval church wall) — or into a new functional placement (a column drum set as street furniture).*

.. list-table::
   :widths: 25 75

   * - Class
     - ``ReusedSpecialFind``
   * - node_type
     - ``RSF``
   * - Parent
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Label (en)
     - Repositioned Special Find
   * - Label (it)
     - Reperto speciale riposizionato
   * - CIDOC
     - ``E19 Physical Object``

Description
-----------

Repositioned Special Find: a physical object, FIXED and IMMOVABLE, INTENTIONALLY put back into a stable unit — a wall (spolia: a Roman column in a medieval church wall) — or into a new functional placement (a column drum set as street furniture). A historical PHYSICAL anastylosis is an RSF too. Reuse (spolia) is one case within this definition. Invariant against SF: the RSF is IMMOVABLE. Originating Development Project: DP-26 (spolia, last DP before the EM 1.5 cut).

*Italiano*: Reperto Speciale Riposizionato: un oggetto fisico, FISSO e INAMOVIBILE, rimesso INTENZIONALMENTE in un'unità stabile — un muro (spolia: una colonna romana nel muro di una chiesa medievale) — o in una nuova collocazione funzionale (un rocchio di colonna come arredo urbano). Anche un'anastilosi FISICA storica è un RSF. Il reimpiego (spolia) è un caso dentro questa definizione. Invariante rispetto a SF: l'RSF è INAMOVIBILE. Development Project di origine: DP-26 (spolia, ultimo DP prima del taglio di EM 1.5).

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

**Outgoing** (this node is the source): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_digital_twin <edge-has_digital_twin>`, :ref:`has_documentation <edge-has_documentation>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_paradata_nodegroup <edge-has_paradata_nodegroup>`, :ref:`has_property <edge-has_property>`, :ref:`has_representation_model <edge-has_representation_model>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_timebranch <edge-has_timebranch>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_functional_unit <edge-is_in_functional_unit>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_in_timebranch <edge-is_in_timebranch>`, :ref:`is_part_of <edge-is_part_of>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`extracted_from <edge-extracted_from>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='RSF'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a RSF") as tx:        # create: one step of undo
       nid = tx.add_node('RSF', "name", description="…")


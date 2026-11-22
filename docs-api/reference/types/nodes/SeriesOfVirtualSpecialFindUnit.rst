.. _type-SeriesOfVirtualSpecialFindUnit:

SeriesOfVirtualSpecialFindUnit
==============================

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Series of Virtual Special Finds: the REPETITION of one and the same object.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``SeriesOfVirtualSpecialFindUnit``
   * - node_type
     - ``serVSF``
   * - Parent
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Label (en)
     - VSF series
   * - Label (it)
     - Serie di VSF
   * - CIDOC
     - ``E89 Propositional Object``

Description
-----------

Series of Virtual Special Finds: the REPETITION of one and the same object. The series IS itself a unit, as for serSU, serUSD, serUSVn and serUSVs. Use: a broken tile repaired with a VSF and then instanced over the whole roof with a serVSF. NOT for pieces that are all different — the drums of a column that tapers: each is its own VSF (or SF) inside the column's VSF.

*Italiano*: Serie di Reperti Speciali Virtuali: la RIPETIZIONE di uno stesso oggetto. La serie è essa stessa un'unità, come per serSU, serUSD, serUSVn e serUSVs. Uso: una tegola rotta riparata con una VSF e poi istanziata su tutto il tetto con una serVSF. NON per pezzi tutti diversi — i rocchi di una colonna che si restringe: ciascuno è una sua VSF (o un suo SF) dentro la VSF della colonna.

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

**Incoming** (this node is the target): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`extracted_from <edge-extracted_from>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_part_of <edge-is_part_of>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='serVSF'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a serVSF") as tx:        # create: one step of undo
       nid = tx.add_node('serVSF', "name", description="…")


.. _type-VirtualSpecialFindUnit:

VirtualSpecialFindUnit
======================

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Virtual Special Find: the object as it was, a hypothesis supported by paradata.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``VirtualSpecialFindUnit``
   * - node_type
     - ``VSF``
   * - Parent
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Label (en)
     - Virtual Special Find
   * - Label (it)
     - Reperto speciale virtuale
   * - CIDOC
     - ``E89 Propositional Object``

Description
-----------

Virtual Special Find: the object as it was, a hypothesis supported by paradata. TWO ROLES. (a) The VSF that HOLDS the fragments: the SF are part of it (\`is\_part\_of\`, read in RDF as <VSF> em:reconstructsFrom <SF>) — the column from its drums, one whole proxy, no boolean. (b) The VSF that COMPLETES what was restored: the missing part around the piece that survives. Two schools of work are both correct: restore the block, or remodel the ancient version under control (correct topology, splines…); in both, the difference between the piece that survives (SF) and the intact ancient one (VSF) is obtained by a boolean. An anastylosis is always a VSF, a whole block put back virtually included (a VSF with one member).

*Italiano*: Reperto Speciale Virtuale: l'oggetto com'era, un'ipotesi sostenuta dai paradati. DUE RUOLI. (a) La VSF che ACCOGLIE i frammenti: gli SF ne sono parte (\`is\_part\_of\`, letto in RDF come <VSF> em:reconstructsFrom <SF>) — la colonna dai suoi rocchi, un unico proxy intero, nessuna booleana. (b) La VSF che COMPLETA ciò che è stato restaurato: la parte mancante attorno al pezzo che sopravvive. Due scuole di lavoro sono entrambe corrette: restaurare il blocco, oppure rimodellare in modo controllato la versione antica (topologia corretta, spline…); in entrambi i casi la differenza tra il pezzo che sopravvive (SF) e quello antico integro (VSF) si ottiene per booleana. Un'anastilosi è sempre una VSF, anche per un blocco intero rimesso in posto virtualmente (una VSF con un solo membro).

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

   for n in em.graph.nodes(type='VSF'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a VSF") as tx:        # create: one step of undo
       nid = tx.add_node('VSF', "name", description="…")


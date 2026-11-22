.. _type-ContinuityNode:

ContinuityNode
==============

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*The end of a unit (SU, USV, any stratigraphic unit).*

.. list-table::
   :widths: 25 75

   * - Class
     - ``ContinuityNode``
   * - node_type
     - ``BR``
   * - Parent
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Label (en)
     - continuity node
   * - Label (it)
     - Nodo di continuità
   * - CIDOC
     - ``E64 End of Existence``

Description
-----------

The end of a unit (SU, USV, any stratigraphic unit). Marks the moment a unit ceases to be present here, as a whole: a cut that takes away only a part leaves no BR, the unit continues. HOW it ends is a type (\`end\_reason\`: destroyed, transformed, removed, relocated, unknown — the default), and the type decides its CIDOC class. The BR is a spatiotemporal unit like the others: it has paradata, a start and an end of its own (absolute\_time\_start / absolute\_time\_end); its epoch is INHERITED — the last epoch the unit lives in — until it has a date of its own. When a cut takes the whole unit away, the BR and the USN are one act: the BR takes the date of the cut, and the cut is its observed trace.

*Italiano*: La fine di un'unità (US, USV, qualunque unità stratigrafica). Segna il momento in cui un'unità cessa di essere presente qui, tutta intera: un taglio che ne toglie solo una parte non lascia BR, l'unità continua. COME finisce è un tipo (\`end\_reason\`: distrutta, trasformata, rimossa, delocalizzata, ignota — il default), e il tipo decide la sua classe CIDOC. Il BR è un'unità spaziotemporale come le altre: ha paradati, un inizio e una fine propri (absolute\_time\_start / absolute\_time\_end); la sua epoca è EREDITATA — l'ultima in cui l'unità vive — finché non ha una data sua. Quando un taglio toglie l'unità tutta, BR e USN sono lo stesso atto: il BR prende la data del taglio, e il taglio ne è la traccia osservata.

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
   * - ``label``
     - continuity node
   * - ``end_reason``
     - HOW the unit ends (E.D., 23 Oct 2026): a TYPE of the EM vocabulary, not a class — the BR stays one class.

Edges
-----

**Outgoing** (this node is the source): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_digital_twin <edge-has_digital_twin>`, :ref:`has_documentation <edge-has_documentation>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_paradata_nodegroup <edge-has_paradata_nodegroup>`, :ref:`has_property <edge-has_property>`, :ref:`has_representation_model <edge-has_representation_model>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_timebranch <edge-has_timebranch>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_in_timebranch <edge-is_in_timebranch>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`extracted_from <edge-extracted_from>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='BR'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a BR") as tx:        # create: one step of undo
       nid = tx.add_node('BR', "name", description="…")


.. _type-StratigraphicEventNode:

StratigraphicEventNode
======================

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*An event that creates, modifies, or destroys a stratigraphic unit (e.g.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``StratigraphicEventNode``
   * - node_type
     - ``SE``
   * - Parent
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Label (en)
     - stratigraphic event node
   * - Label (it)
     - Evento stratigrafico
   * - CIDOC
     - ``A5 Stratigraphic Modification``

Description
-----------

An event that creates, modifies, or destroys a stratigraphic unit (e.g. an earthquake causing a plaster collapse, an act of demolition, the start of construction). Distinct from the resulting unit itself: an SE is the PROCESS, the SU is the result. Can be enriched by a 3D simulation (em:RepresentationModel) of the event. May be paired with its resulting unit to provide a temporal range bracketing the action.

*Italiano*: Un evento che crea, modifica o distrugge un'unità stratigrafica (ad es. un terremoto che causa il crollo di un intonaco, un atto di demolizione, l'avvio di una costruzione). Distinto dall'unità risultante: un SE è il PROCESSO, la US è il risultato. Può essere arricchito da una simulazione 3D (em:RepresentationModel) dell'evento. Può essere accoppiato alla sua unità risultante per fornire un intervallo temporale che racchiude l'azione.

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
     - stratigraphic event node

Edges
-----

**Outgoing** (this node is the source): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_digital_twin <edge-has_digital_twin>`, :ref:`has_documentation <edge-has_documentation>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_paradata_nodegroup <edge-has_paradata_nodegroup>`, :ref:`has_property <edge-has_property>`, :ref:`has_representation_model <edge-has_representation_model>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_timebranch <edge-has_timebranch>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_in_timebranch <edge-is_in_timebranch>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`extracted_from <edge-extracted_from>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='SE'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a SE") as tx:        # create: one step of undo
       nid = tx.add_node('SE', "name", description="…")


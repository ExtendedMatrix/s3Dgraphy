.. _type-DistrictNode:

DistrictNode
============

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*District: the declared portion of territory that holds what stands on it — sites, virtual sites, topographic units, other districts — as a TRAY holds its objects («il rapporto fra terreno e resti è quello fra un vassoio e gli oggetti che ci sono sopra», 2017).*

.. list-table::
   :widths: 25 75

   * - Class
     - ``DistrictNode``
   * - node_type
     - ``district``
   * - Parent
     - :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`
   * - Label (en)
     - District
   * - Label (it)
     - Distretto
   * - CIDOC
     - ``crmgeo:SP6_Declarative_Place``

Description
-----------

District: the declared portion of territory that holds what stands on it — sites, virtual sites, topographic units, other districts — as a TRAY holds its objects («il rapporto fra terreno e resti è quello fra un vassoio e gli oggetti che ci sono sopra», 2017). URBAN (the Forum of Pompeii, holding temples and monuments) or RURAL (a villa rustica, holding the graphs of its single buildings or of the anthropic transformations). DECLARED: its border is an interpretation of pertinence, argued by its paradata; it approximates the real place (the true fundus nobody saw whole). A UNIT, not a group: it has a geometry (a footprint), a time (it changes with the villa: VTU1 in epoch 1, VTU2 in epoch 2) and paradata. Replaces the UTV / VTU of 2017.

*Italiano*: Distretto: la porzione di territorio dichiarata che tiene ciò che vi sta sopra — siti, siti virtuali, unità topografiche, altri distretti — come un VASSOIO tiene i suoi oggetti («il rapporto fra terreno e resti è quello fra un vassoio e gli oggetti che ci sono sopra», 2017). URBANO (il Foro di Pompei, che tiene templi e monumenti) o RURALE (una villa rustica, che tiene i grafi dei singoli edifici o delle trasformazioni antropiche). DICHIARATO: il suo confine è un'interpretazione di pertinenza, argomentata dai suoi paradati; approssima il luogo reale (il vero fundus che nessuno ha visto intero). Un'UNITÀ, non un gruppo: ha una geometria (un'impronta), un tempo (cambia con la villa: VTU1 nell'epoca 1, VTU2 nella 2) e paradati. Sostituisce UTV / VTU del 2017.

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
   * - ``district_kind``
     - The kind of the district (E.D., roadmap §14, 24 Oct 2026): a TYPE of the EM vocabulary, not a class — «a species is a type, P2\_has\_type, and it is free» (filter of the note, §9).

Edges
-----

**Outgoing** (this node is the source): :ref:`changed_from <edge-changed_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_property <edge-has_property>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_in_district <edge-is_in_district>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`changed_from <edge-changed_from>`, :ref:`extracted_from <edge-extracted_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_in_district <edge-is_in_district>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='district'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a district") as tx:        # create: one step of undo
       nid = tx.add_node('district', "name", description="…")


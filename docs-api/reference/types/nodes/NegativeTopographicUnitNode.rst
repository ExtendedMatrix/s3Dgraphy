.. _type-NegativeTopographicUnitNode:

NegativeTopographicUnitNode
===========================

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Negative topographic unit (−UT, token UT0): the area a survey walked where nothing was found, with the conditions of the observation (visibility, season, coverage).*

.. list-table::
   :widths: 25 75

   * - Class
     - ``NegativeTopographicUnitNode``
   * - node_type
     - ``UT0``
   * - Parent
     - :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`
   * - Label (en)
     - −UT
   * - Label (it)
     - −UT
   * - CIDOC
     - ``crmsci:S4_Observation``

Description
-----------

Negative topographic unit (−UT, token UT0): the area a survey walked where nothing was found, with the conditions of the observation (visibility, season, coverage). OBSERVED: an absence of evidence is an observation. It makes silence informative — without it an empty district in an horizon cannot tell «there was nothing» from «nobody looked» — and it is the base of the «mapping of the gaps» (2017). What is concluded from it («no settlement here») belongs to its paradata, not to the unit.

*Italiano*: Unità topografica negativa (−UT, token UT0): l'area battuta dal survey dove non si è trovato niente, con le condizioni dell'osservazione (visibilità, stagione, copertura). OSSERVATA: un'assenza di evidenza è un'osservazione. Rende informativo il silenzio — senza di essa un distretto vuoto in un orizzonte non distingue «non c'era niente» da «nessuno ha guardato» — ed è la base della «mappatura delle lacune» (2017). Ciò che se ne conclude («qui non c'era insediamento») sta nei suoi paradati, non nell'unità.

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

**Incoming** (this node is the target): :ref:`changed_from <edge-changed_from>`, :ref:`extracted_from <edge-extracted_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='UT0'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a UT0") as tx:        # create: one step of undo
       nid = tx.add_node('UT0', "name", description="…")


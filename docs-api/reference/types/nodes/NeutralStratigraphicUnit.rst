.. _type-NeutralStratigraphicUnit:

NeutralStratigraphicUnit
========================

.. note::

   Generated from the datamodels (nodes 1.6.56, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Neutral Stratigraphic Unit (Unità Stratigrafica Neutra, USNt) — a void that is part of the DESIGN and not the product of a destruction: the \`risparmi\` of masonry, a window or door opening, a niche, the empty volume of a room.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``NeutralStratigraphicUnit``
   * - node_type
     - ``USNt``
   * - Parent
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Label (en)
     - USNt
   * - Label (it)
     - USNt
   * - CIDOC
     - ``A3 Stratigraphic Interface``

Description
-----------

Neutral Stratigraphic Unit (Unità Stratigrafica Neutra, USNt) — a void that is part of the DESIGN and not the product of a destruction: the \`risparmi\` of masonry, a window or door opening, a niche, the empty volume of a room. The wall was built around it, so nothing was ever removed. The distinction from the negative unit (USN, displayed 'US-') is stratigraphic and not cosmetic: a demolition void is evidence of an ACT, a risparmio is evidence of an INTENTION, and reading one as the other dates the void to a removal that never happened. Added in POL5 (2026-08-04) on E.D.'s explicit authorisation; the token became USNt in POL6, when USN went back to the negativa.

*Italiano*: Unità Stratigrafica Neutra (USNt) — un vuoto che fa parte del PROGETTO e non è il prodotto di una distruzione: i \`risparmi\` della muratura, una finestra o un vano di porta, una nicchia, il volume vuoto di un ambiente. Il muro è stato costruito intorno a esso, quindi nulla è mai stato asportato. La distinzione dall'unità negativa (USN, visualizzata 'US-') è stratigrafica e non estetica: un vuoto di demolizione è prova di un ATTO, un risparmio è prova di un'INTENZIONE, e leggere l'uno come l'altro data il vuoto a un'asportazione mai avvenuta. Aggiunta in POL5 (2026-08-04) su esplicita autorizzazione di E.D.; il token è diventato USNt in POL6, quando USN è tornato alla negativa.

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

**Outgoing** (this node is the source): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_digital_twin <edge-has_digital_twin>`, :ref:`has_documentation <edge-has_documentation>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_paradata_nodegroup <edge-has_paradata_nodegroup>`, :ref:`has_property <edge-has_property>`, :ref:`has_representation_model <edge-has_representation_model>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_timebranch <edge-has_timebranch>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_in_timebranch <edge-is_in_timebranch>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`extracted_from <edge-extracted_from>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='USNt'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a USNt") as tx:        # create: one step of undo
       nid = tx.add_node('USNt', "name", description="…")


.. _type-NegativeStratigraphicUnit:

NegativeStratigraphicUnit
=========================

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Negative Stratigraphic Unit (US negativa, displayed 'US-') — a lacuna produced by a SUBTRACTION of matter: a pit cut, an opening broken through a wall, an erosion surface, a levelling.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``NegativeStratigraphicUnit``
   * - node_type
     - ``USN``
   * - Parent
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Label (en)
     - US-
   * - Label (it)
     - US-
   * - CIDOC
     - ``A3 Stratigraphic Interface``

Description
-----------

Negative Stratigraphic Unit (US negativa, displayed 'US-') — a lacuna produced by a SUBTRACTION of matter: a pit cut, an opening broken through a wall, an erosion surface, a levelling. What defines it is the destructive act, which is what separates it from the NEUTRAL unit (USNt), a void that was never filled because it was never meant to be. Equally observable on the ground as a positive unit, hence the \`real\` family. POL6 (2026-08-04): the token is USN again — the historical spelling of this library and of what pyArchInit vendors, and the one that reads as the Italian 'US Negativa'. POL5 had briefly moved it to 'USNeg' to free USN for the neutral unit; that made a token spell one thing and mean another, and put the two projects in disagreement about a three-letter word.

*Italiano*: Unità Stratigrafica Negativa (US negativa, visualizzata 'US-') — una lacuna prodotta da una SOTTRAZIONE di materia: il taglio di una fossa, un'apertura praticata in un muro, una superficie di erosione, uno spianamento. A definirla è l'atto distruttivo, ed è questo a separarla dall'unità NEUTRA (USNt), un vuoto che non è mai stato riempito perché non doveva esserlo. Osservabile sul terreno quanto un'unità positiva, da cui l'appartenenza alla famiglia \`real\`. POL6 (2026-08-04): il token torna a essere USN — la grafia storica di questa libreria e di ciò che pyArchInit incorpora, e quella che si legge come l'italiano «US Negativa». POL5 l'aveva spostato per breve tempo a 'USNeg' per liberare USN per l'unità neutra; questo faceva sì che un token si scrivesse in un modo e significasse altro, e metteva i due progetti in disaccordo su una parola di tre lettere.

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

   for n in em.graph.nodes(type='USN'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a USN") as tx:        # create: one step of undo
       nid = tx.add_node('USN', "name", description="…")


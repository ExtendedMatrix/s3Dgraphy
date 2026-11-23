.. _type-TranslationNode:

TranslationNode
===============

.. note::

   Generated from the datamodels (nodes 1.6.55, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*ONE TRANSLATION of one text field of one node (E.D.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``TranslationNode``
   * - node_type
     - ``translation``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Translation
   * - Label (it)
     - Traduzione
   * - CIDOC
     - ``E33 Linguistic Object``

Description
-----------

ONE TRANSLATION of one text field of one node (E.D. 2026-10-01, «Le traduzioni»). The ORIGINAL stays a string in its own field, in the language it was written in — data.lang on the node says which, else the study's working language — and a translation never overwrites it: the original is testimony. Each translation is a node of its own, reached from the translated node by has\_translation (reverse is\_translation\_of). Fields in data: lang (the language of ARRIVAL, BCP 47 — the same key as every node's data.lang, so its own text takes its tag by the ordinary cascade); from\_lang (the language of DEPARTURE, the original's WHEN it was translated: written, because the original can change); field (the translated field in the CRDT's vocabulary: description, or data.<key> — a PropertyNode's value is data.value; name is never translated, names are invariant identities); text; method (manual \| ai \| edition); source\_digest ('sha256:<hex>' of the original text translated, NFC + UTF-8: when the original changes the digests differ and the translation is «da riallineare», which no signature clears); review\_requested (true when the translator asks for a review, «da rivedere»). WHO translated is has\_author (an AuthorNode); WHEN is the editorial stamp created\_at. An AI translation carries data.ai\_assisted and stays among the warnings until a person verifies it (data.validated\_by / validated\_at, the same two fields that close a requested review: ai\_validation.verify). A translation from a published EDITION reaches the DocumentNode of that edition with extracted\_from: a published translation is a source, Vitruvius read through a translator is an interpretation.

*Italiano*: UNA TRADUZIONE di un campo di testo di un nodo (E.D. 1 ott 2026, «Le traduzioni»). L'ORIGINALE resta una stringa nel suo campo, nella lingua in cui è nato (data.lang del nodo, altrimenti la lingua dello studio), e una traduzione non lo sovrascrive mai: l'originale è testimonianza. Ogni traduzione è un nodo, raggiunto da has\_translation, con lang (arrivo), from\_lang (partenza, scritta perché l'originale può cambiare), field (description o data.<chiave>; il nome non si traduce), text, method (manual \| ai \| edition), source\_digest (sha256 dell'originale tradotto: se cambia, la traduzione è «da riallineare») e review\_requested («da rivedere»). Chi ha tradotto: has\_author; una traduzione AI resta tra gli avvisi finché una persona non la verifica (validated\_by); da un'edizione: extracted\_from verso il DocumentNode.

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
   * - ``text``
     - P190\_has\_symbolic\_content
   * - ``lang``
     - P72\_has\_language
   * - ``from_lang``
     - em:sourceLanguage
   * - ``field``
     - em:translatedField
   * - ``method``
     - em:translationMethod
   * - ``source_digest``
     - em:sourceDigest
   * - ``review_requested``
     - em:reviewRequested

Edges
-----

**Outgoing** (this node is the source): :ref:`extracted_from <edge-extracted_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`was_revision_of <edge-was_revision_of>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_translation <edge-has_translation>`, :ref:`was_revision_of <edge-was_revision_of>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='translation'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a translation") as tx:        # create: one step of undo
       nid = tx.add_node('translation', "name", description="…")


.. _edge-has_translation:

has_translation
===============

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A node has a TRANSLATION of one of its text fields (E.D.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has translation
   * - Label (it)
     - Ha la traduzione
   * - Reverse
     - ``is_translation_of``
   * - Source
     - :ref:`Node <type-Node>`
   * - Target
     - :ref:`TranslationNode <type-TranslationNode>`
   * - CIDOC
     - ``P73_has_translation``

Description
-----------

A node has a TRANSLATION of one of its text fields (E.D. 2026-10-01, «Le traduzioni»): the source is the node whose original stays in its field, the target the TranslationNode that holds the text in another language, with who, when, how and of which original (data.field, data.lang, data.from\_lang, data.method, data.source\_digest). The original is never overwritten: a translation is testimony beside it. A node may have many translations — several languages, several translators of the same language, a manual one beside an edition's.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_translation')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_translation', target)    # the contract checks the pair


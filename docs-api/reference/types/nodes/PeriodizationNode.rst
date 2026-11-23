.. _type-PeriodizationNode:

PeriodizationNode
=================

.. note::

   Generated from the datamodels (nodes 1.6.56, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A set of horizons: one way of cutting time into named, ordered spans, shared by every graph of the project.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``PeriodizationNode``
   * - node_type
     - ``periodization``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Periodization
   * - Label (it)
     - Periodizzazione
   * - CIDOC
     - ``E32 Authority Document``

Description
-----------

A set of horizons: one way of cutting time into named, ordered spans, shared by every graph of the project. Several periodizations may coexist (a regional chronology, the one of a publication, the one of a museum display) and the reader chooses which to apply. It lists its horizons through is\_in\_periodization (horizon → periodization). It is NOT an epoch and does not date anything: it is a reference against which what the graphs compute is read.

*Italiano*: Un insieme di orizzonti: un modo di tagliare il tempo in intervalli nominati e ordinati, condiviso da tutti i grafi del progetto. Più periodizzazioni possono convivere e chi legge sceglie quale applicare. Elenca i suoi orizzonti con is\_in\_periodization (orizzonte → periodizzazione). Non è un'epoca e non data nulla: è un riferimento su cui si legge ciò che i grafi calcolano.

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
   * - ``source``
     - P70i\_is\_documented\_in (a literal: where the periodization comes from — «EM-tools CronoFilter», a PeriodO id, a publication)

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`is_in_periodization <edge-is_in_periodization>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='periodization'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a periodization") as tx:        # create: one step of undo
       nid = tx.add_node('periodization', "name", description="…")


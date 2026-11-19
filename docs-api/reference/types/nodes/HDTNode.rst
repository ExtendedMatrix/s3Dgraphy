.. _type-HDTNode:

HDTNode
=======

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Represents an HC2 Heritage Digital Twin (HDT-O, ECHOES D7.1).*

.. list-table::
   :widths: 25 75

   * - Class
     - ``HDTNode``
   * - node_type
     - ``hdt``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Heritage Digital Twin
   * - Label (it)
     - Gemello digitale del patrimonio
   * - CIDOC
     - ``hdto:HC2_Heritage_Digital_Twin``

Description
-----------

Represents an HC2 Heritage Digital Twin (HDT-O, ECHOES D7.1). An HDT is a named container that aggregates Heritage Proposition Sets (em:EMGraph instances) about a heritage entity (HC1). HDTs can be nested hierarchically via has\_digital\_twin\_component (HP3 inverse) — e.g. Colosseo\_HDT\_overall has component Colosseo\_HDT\_Flavian. An EM graph attaches to an HDT via contains\_proposition\_set (HP33). The HDT is linked to its real-world heritage entity (HC1) via has\_digital\_twin (HP1).

*Italiano*: Rappresenta un HC2 Heritage Digital Twin (HDT-O, ECHOES D7.1). Un HDT è un contenitore nominato che aggrega Heritage Proposition Set (istanze di em:EMGraph) relativi a un'entità patrimoniale (HC1). Gli HDT possono essere annidati gerarchicamente tramite has\_digital\_twin\_component (inverso di HP3) — ad es. Colosseo\_HDT\_overall ha come componente Colosseo\_HDT\_Flavian. Un grafo EM si collega a un HDT tramite contains\_proposition\_set (HP33). L'HDT è collegato alla sua entità patrimoniale reale (HC1) tramite has\_digital\_twin (HP1).

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

**Outgoing** (this node is the source): :ref:`contains_proposition_set <edge-contains_proposition_set>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_digital_object_part <edge-has_digital_object_part>`, :ref:`has_digital_twin_component <edge-has_digital_twin_component>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_digital_twin <edge-has_digital_twin>`, :ref:`has_digital_twin_component <edge-has_digital_twin_component>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='hdt'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a hdt") as tx:        # create: one step of undo
       nid = tx.add_node('hdt', "name", description="…")


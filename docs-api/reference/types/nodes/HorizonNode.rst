.. _type-HorizonNode:

HorizonNode
===========

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*One span of a periodization: a label, a start and an end in years (negative = BC), a colour and its order in the periodization.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``HorizonNode``
   * - node_type
     - ``horizon``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Horizon
   * - Label (it)
     - Orizzonte
   * - CIDOC
     - ``crmgeo:SP10_Declarative_Time-Span``

Description
-----------

One span of a periodization: a label, a start and an end in years (negative = BC), a colour and its order in the periodization. A unit, an epoch or a graph is IN the horizon when its absolute interval (Graph.chronology) intersects [start\_time, end\_time]: overlap is enough, containment is not required. enabled says whether the horizon is in use (EM Tools' CronoFilter flag, same name).

*Italiano*: Un intervallo di una periodizzazione: etichetta, inizio e fine in anni (negativi = a.C.), colore e posto nella periodizzazione. Un'unità, un'epoca o un grafo è DENTRO l'orizzonte se il suo intervallo assoluto (Graph.chronology) lo interseca: basta la sovrapposizione. enabled dice se l'orizzonte è in uso (lo stesso flag del CronoFilter di EM Tools).

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
   * - ``start_time``
     - P82a\_begin\_of\_the\_begin
   * - ``end_time``
     - P82b\_end\_of\_the\_end
   * - ``color``
     - P90\_has\_value (layout that travels with the data)
   * - ``order``
     - em:order (its place in the periodization, 0 first)
   * - ``enabled``
     - not projected (a working flag of the tools)

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_periodization <edge-is_in_periodization>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='horizon'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a horizon") as tx:        # create: one step of undo
       nid = tx.add_node('horizon', "name", description="…")


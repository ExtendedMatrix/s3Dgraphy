.. _type-ProjectNode:

ProjectNode
===========

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.60) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*HC13 Project (HDT-O, ECHOES D7.1): the coordinated activities of institutions/research groups producing heritage-related outcomes; the organizational context under which studies are carried out and under which HDTs are created and curated (HC11 maintenance is carried out under a project, HP20).*

.. list-table::
   :widths: 25 75

   * - Class
     - ``ProjectNode``
   * - node_type
     - ``project``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Project
   * - Label (it)
     - Progetto
   * - CIDOC
     - ``hdto:HC13_Project``

Description
-----------

HC13 Project (HDT-O, ECHOES D7.1): the coordinated activities of institutions/research groups producing heritage-related outcomes; the organizational context under which studies are carried out and under which HDTs are created and curated (HC11 maintenance is carried out under a project, HP20). Includes studies via crm:P9\_consists\_of (D7.1 defines no direct HC13->HC9 property). HDT-O-view node: not shown in the stratigrapher palette.

*Italiano*: HC13 Project (HDT-O, ECHOES D7.1): le attività coordinate di istituzioni/gruppi di ricerca che producono risultati relativi al patrimonio; il contesto organizzativo nel quale si svolgono gli studi e si creano e curano gli HDT (la manutenzione HC11 è svolta nell'ambito di un progetto, HP20). Include gli studi tramite crm:P9\_consists\_of (D7.1 non definisce alcuna proprietà diretta HC13->HC9). Nodo della vista HDT-O: non mostrato nella palette dello stratigrafo.

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

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`includes_study <edge-includes_study>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='project'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a project") as tx:        # create: one step of undo
       nid = tx.add_node('project', "name", description="…")


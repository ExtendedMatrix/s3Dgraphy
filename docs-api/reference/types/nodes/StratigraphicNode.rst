.. _type-StratigraphicNode:

StratigraphicNode
=================

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Base class for all stratigraphic units within the graph structure.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``StratigraphicNode``
   * - node_type
     - ``StratigraphicNode``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - StratigraphicNode
   * - Label (it)
     - —
   * - CIDOC
     - ``A8 Stratigraphic Unit``

Description
-----------

Base class for all stratigraphic units within the graph structure. Inherits from Node and provides additional functionality specific to stratigraphy.

*Italiano*: Classe base per tutte le unità stratigrafiche all'interno della struttura del grafo. Eredita da Node e fornisce funzionalità aggiuntive specifiche della stratigrafia.

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
   * - ``definition``
     - DEPRECATED 1.6.48 (MICRO-K §A, E.D. (deprecated 1.6.48)

Edges
-----

**Outgoing** (this node is the source): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_digital_twin <edge-has_digital_twin>`, :ref:`has_documentation <edge-has_documentation>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_paradata_nodegroup <edge-has_paradata_nodegroup>`, :ref:`has_property <edge-has_property>`, :ref:`has_representation_model <edge-has_representation_model>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_timebranch <edge-has_timebranch>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_in_timebranch <edge-is_in_timebranch>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`abuts <edge-abuts>`, :ref:`bonded_to <edge-bonded_to>`, :ref:`changed_from <edge-changed_from>`, :ref:`cuts <edge-cuts>`, :ref:`equals <edge-equals>`, :ref:`extracted_from <edge-extracted_from>`, :ref:`fills <edge-fills>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_bonded_to <edge-is_bonded_to>`, :ref:`is_physically_equal_to <edge-is_physically_equal_to>`, :ref:`overlies <edge-overlies>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='StratigraphicNode'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a StratigraphicNode") as tx:        # create: one step of undo
       nid = tx.add_node('StratigraphicNode', "name", description="…")


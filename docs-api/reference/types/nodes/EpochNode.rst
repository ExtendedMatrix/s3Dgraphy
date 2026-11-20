.. _type-EpochNode:

EpochNode
=========

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Node representing a temporal epoch.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``EpochNode``
   * - node_type
     - ``EpochNode``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Epoch
   * - Label (it)
     - Epoca
   * - CIDOC
     - ``E4 Period``

Description
-----------

Node representing a temporal epoch. It is a convenient grouping that allows attributing a series of actions to a temporal delta. Once the specific chronology data, expressed as start\_time and end\_time properties of individual SUs, is defined through dating elements, these epoch nodes are ignored where such specific data are available.

*Italiano*: Nodo che rappresenta un'epoca temporale. È un raggruppamento di comodo che permette di attribuire una serie di azioni a un intervallo temporale. Una volta definiti, tramite elementi di datazione, i dati cronologici specifici espressi come proprietà start\_time ed end\_time delle singole US, questi nodi epoca vengono ignorati laddove tali dati specifici siano disponibili.

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
     - P90\_has\_value

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_paradata_nodegroup <edge-has_paradata_nodegroup>`, :ref:`has_property <edge-has_property>`, :ref:`has_representation_model <edge-has_representation_model>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_sub_epoch <edge-has_sub_epoch>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_sub_epoch <edge-has_sub_epoch>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='EpochNode'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a EpochNode") as tx:        # create: one step of undo
       nid = tx.add_node('EpochNode', "name", description="…")


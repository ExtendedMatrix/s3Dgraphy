.. _type-NarrativeNode:

NarrativeNode
=============

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A narrative over the EM graph: an ordered sequence of chapters, each anchored to a lane (epoch, activity, area) or standing outside the stratigraphy (introduction, geographic placement), and each composed of prose blocks and embed blocks.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``NarrativeNode``
   * - node_type
     - ``narrative``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Narrative
   * - Label (it)
     - Narrazione
   * - CIDOC
     - ``E33 Linguistic Object``

Description
-----------

A narrative over the EM graph: an ordered sequence of chapters, each anchored to a lane (epoch, activity, area) or standing outside the stratigraphy (introduction, geographic placement), and each composed of prose blocks and embed blocks. An embed references an EM resource by its stable id and declares a view\_type (matrix, scene3d, us, rm, document, source, paradata, map, timeline, table, un\_scene; 'epoch3d' is the retired spelling of 'scene3d' and is still accepted on read) saying how it should be shown. Metadata follows the existing conventions: author / license / embargo (DP-32), lang (DP-63), version, and template\_id recording which scaffolder produced the first draft.

*Italiano*: Una narrazione sul grafo EM: una sequenza ordinata di capitoli, ciascuno ancorato a una corsia (epoca, attività, area) o collocato al di fuori della stratigrafia (introduzione, inquadramento geografico), e ciascuno composto da blocchi di prosa e blocchi incorporati. Un blocco incorporato fa riferimento a una risorsa EM tramite il suo id stabile e dichiara un view\_type (matrix, scene3d, us, rm, document, source, paradata, map, timeline, table, un\_scene; 'epoch3d' è la grafia dismessa di 'scene3d' ed è ancora accettata in lettura) che indica come deve essere mostrata. I metadati seguono le convenzioni esistenti: author / license / embargo (DP-32), lang (DP-63), version, e template\_id che registra quale generatore di struttura ha prodotto la prima bozza.

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
   * - ``author``
     - P94i\_was\_created\_by
   * - ``lang``
     - P72\_has\_language

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`validated_by <edge-validated_by>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='narrative'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a narrative") as tx:        # create: one step of undo
       nid = tx.add_node('narrative', "name", description="…")


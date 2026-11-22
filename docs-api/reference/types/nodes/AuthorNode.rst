.. _type-AuthorNode:

AuthorNode
==========

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Human author of one or more nodes.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``AuthorNode``
   * - node_type
     - ``author``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Author (human)
   * - Label (it)
     - Autore (umano)
   * - CIDOC
     - ``E21 Person``

Description
-----------

Human author of one or more nodes. Identified by ORCID where possible. Python: AuthorNode (node\_type='author'). The AI-assisted variant is AuthorAINode (subclass of AuthorNode). An isinstance check against AuthorNode matches both at the code level; the node\_type discriminator and the em\_extension.uri distinguish them semantically.

*Italiano*: Autore umano di uno o più nodi. Identificato tramite ORCID ove possibile. Python: AuthorNode (node\_type='author'). La variante assistita dall'IA è AuthorAINode (sottoclasse di AuthorNode). Un controllo isinstance su AuthorNode riconosce entrambe a livello di codice; il discriminatore node\_type e em\_extension.uri le distinguono sul piano semantico.

Fields
------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Field
     - Mapping / note
   * - ``name``
     - P1\_is\_identified\_by
   * - ``orcid``
     - P48\_has\_preferred\_identifier
   * - ``surname``
     - P1\_is\_identified\_by
   * - ``verified``
     - em:orcidVerified

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_license <edge-has_license>`, :ref:`has_property <edge-has_property>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_paradata_nodegroup <edge-is_in_paradata_nodegroup>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`validated_by <edge-validated_by>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='author'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a author") as tx:        # create: one step of undo
       nid = tx.add_node('author', "name", description="…")


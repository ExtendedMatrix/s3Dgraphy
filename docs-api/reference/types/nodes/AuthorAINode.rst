.. _type-AuthorAINode:

AuthorAINode
============

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*AI agent (model + prompt\_reference) responsible for asserting or refining one or more nodes.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``AuthorAINode``
   * - node_type
     - ``author_ai``
   * - Parent
     - :ref:`AuthorNode <type-AuthorNode>`
   * - Label (en)
     - AI Author
   * - Label (it)
     - Autore IA
   * - CIDOC
     - ``E39 Actor``

Description
-----------

AI agent (model + prompt\_reference) responsible for asserting or refining one or more nodes. Python: AuthorAINode (node\_type='author\_ai'), subclass of AuthorNode. Already referenced as target in connections\_datamodel.json has\_author edge. The Python class carries 'model' and 'prompt\_reference' in node.data for reproducibility.

*Italiano*: Agente di IA (modello + prompt\_reference) responsabile dell'asserzione o del perfezionamento di uno o più nodi. Python: AuthorAINode (node\_type='author\_ai'), sottoclasse di AuthorNode. Già referenziato come destinazione dell'arco has\_author in connections\_datamodel.json. La classe Python conserva 'model' e 'prompt\_reference' in node.data per garantire la riproducibilità.

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
   * - ``verified``
     - em:orcidVerified
   * - ``model``
     - em:modelIdentifier
   * - ``prompt_reference``
     - em:promptReference

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_license <edge-has_license>`, :ref:`has_property <edge-has_property>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_paradata_nodegroup <edge-is_in_paradata_nodegroup>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`validated_by <edge-validated_by>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='author_ai'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a author_ai") as tx:        # create: one step of undo
       nid = tx.add_node('author_ai', "name", description="…")


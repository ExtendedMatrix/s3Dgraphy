.. _type-Node:

Node
====

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Base class for all nodes in the graph with CIDOC mapping*

.. list-table::
   :widths: 25 75

   * - Class
     - ``Node``
   * - node_type
     - ``Node``
   * - Parent
     - —
   * - Label (en)
     - Node
   * - Label (it)
     - —
   * - CIDOC
     - ``E1 CRM Entity``

Description
-----------

Base class for all nodes in the graph with CIDOC mapping

*Italiano*: Classe base per tutti i nodi del grafo, con mappatura CIDOC

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
     - —
   * - ``created_by``
     - em:createdBy
   * - ``created_at``
     - prov:generatedAtTime
   * - ``modified_by``
     - em:lastEditedBy
   * - ``modified_at``
     - em:modifiedAt
   * - ``removed.ts``
     - em:removedAt
   * - ``removed.by``
     - em:removedBy
   * - ``ai_assisted.by``
     - em:aiAssistedBy
   * - ``ai_assisted.model``
     - em:aiModel
   * - ``ai_assisted.prompt_ref``
     - em:aiPromptRef
   * - ``ai_assisted.fields``
     - em:aiAssistedField
   * - ``validated_by``
     - em:validatedBy
   * - ``validated_at``
     - em:validatedAt
   * - ``lang``
     - em:originalLanguage
   * - ``created_auth``
     - em:createdVia
   * - ``modified_auth``
     - em:modifiedVia
   * - ``validated_auth``
     - em:validatedVia
   * - ``created_auth.mode``
     - em:authMode
   * - ``created_auth.attested_by``
     - em:attestedBy
   * - ``scheda``
     - —

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='Node'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a Node") as tx:        # create: one step of undo
       nid = tx.add_node('Node', "name", description="…")


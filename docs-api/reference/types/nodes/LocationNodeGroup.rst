.. _type-LocationNodeGroup:

LocationNodeGroup
=================

.. note::

   Generated from the datamodels (nodes 1.6.56, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Group node for spatial / locational membership of stratigraphic units and paradata.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``LocationNodeGroup``
   * - node_type
     - ``LocationNodeGroup``
   * - Parent
     - :ref:`GroupNode <type-GroupNode>`
   * - Label (en)
     - Location Node Group
   * - Label (it)
     - Gruppo di luogo
   * - CIDOC
     - ``E53 Place``

Description
-----------

Group node for spatial / locational membership of stratigraphic units and paradata. Orthogonal to ActivityNodeGroup (intention) and EpochNode (time): a Location answers the question 'what (named) place is this in?'. Three required kinds coexist on the same axis: 'toponym' (external/administrative identity, e.g. Pompei), 'study' (operational/procedural identity, e.g. Saggio4/A2) and 'functional' (interpretive/semantic identity, e.g. Casa del Fauno / Room 12). Propagation is additive: multiple memberships compose, none overrides — distinct from EpochNode which is substitutive (finest-grained wins). Membership is m:n via multiple is\_in\_location edges; the optional 'is\_primary: true' attribute on one edge marks the membership rendered as a yEd group folder in em-graph. Locations are hierarchical: a LocationNodeGroup can itself be is\_in\_location of another LocationNodeGroup. A Location is identitary, not geometric: for coordinates / EPSG / shifts use GeoPositionNode (linked at the CIDOC level via P161).

*Italiano*: Nodo di gruppo per l'appartenenza spaziale / di luogo di unità stratigrafiche e paradati. Ortogonale ad ActivityNodeGroup (intenzione) ed EpochNode (tempo): un Luogo risponde alla domanda «in quale luogo (nominato) si trova?». Tre tipi obbligatori coesistono sullo stesso asse: 'toponym' (identità esterna/amministrativa, ad es. Pompei), 'study' (identità operativa/procedurale, ad es. Saggio4/A2) e 'functional' (identità interpretativa/semantica, ad es. Casa del Fauno / Ambiente 12). La propagazione è additiva: più appartenenze si compongono, nessuna prevale — a differenza di EpochNode, che è sostitutivo (vince il livello più fine). L'appartenenza è m:n tramite più archi is\_in\_location; l'attributo facoltativo 'is\_primary: true' su un arco indica l'appartenenza resa come cartella di gruppo yEd in em-graph. I luoghi sono gerarchici: un LocationNodeGroup può a sua volta essere is\_in\_location di un altro LocationNodeGroup. Un Luogo è identitario, non geometrico: per coordinate / EPSG / traslazioni si usa GeoPositionNode (collegato a livello CIDOC tramite P161).

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

**Outgoing** (this node is the source): :ref:`changed_from <edge-changed_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_property <edge-has_property>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_in_district <edge-is_in_district>`, :ref:`is_in_location <edge-is_in_location>`

**Incoming** (this node is the target): :ref:`changed_from <edge-changed_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`study_took_place_at <edge-study_took_place_at>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='LocationNodeGroup'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a LocationNodeGroup") as tx:        # create: one step of undo
       nid = tx.add_node('LocationNodeGroup', "name", description="…")


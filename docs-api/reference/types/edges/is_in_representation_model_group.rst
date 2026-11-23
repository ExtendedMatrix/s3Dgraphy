.. _edge-is_in_representation_model_group:

is_in_representation_model_group
================================

.. note::

   Generated from the datamodels (nodes 1.6.56, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Membership of a representation model in a RepresentationModelNodeGroup (EM16-RMNG): the models that together form one named set published under a single Document — «Survey 2015» under D.01, «Reconstruction» under D.09.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is in representation model group
   * - Label (it)
     - È nel contenitore RM
   * - Reverse
     - ``includes_representation_model``
   * - Source
     - :ref:`RepresentationModelNode <type-RepresentationModelNode>`, :ref:`RepresentationModelDocNode <type-RepresentationModelDocNode>`, :ref:`RepresentationModelSpecialFindNode <type-RepresentationModelSpecialFindNode>`, :ref:`RepresentationModelNodeGroup <type-RepresentationModelNodeGroup>`
   * - Target
     - :ref:`RepresentationModelNodeGroup <type-RepresentationModelNodeGroup>`
   * - CIDOC
     - ``P46i_forms_part_of``

Description
-----------

Membership of a representation model in a RepresentationModelNodeGroup (EM16-RMNG): the models that together form one named set published under a single Document — «Survey 2015» under D.01, «Reconstruction» under D.09. THE GROUP SITS BESIDE, IT DOES NOT REPLACE: every member keeps its own epoch edges (has\_first\_epoch / survive\_in\_epoch) and the Document keeps its DIRECT has\_representation\_model edges to each model. This edge is added on top and never put in between, so a consumer that ignores it reads exactly what it read before. Membership is a TAG axis like is\_in\_functional\_unit and is\_in\_location — the member carries the edge and the group claims nothing of it — and m:n like them (E.D., 23 Oct 2026; 1:1 until connections 1.6.42): a model may belong to SEVERAL containers — a model of «Survey 2015» can also be in «Reconstruction, 2nd c. AD». The epochs stay on each model: the default epochs an EM Tools container carries are a convenience of the scene, written on its models, never a statement of the group. A group may legally be EMPTY and may legally have no Document: both are states the RM Manager UI already shows, and neither is validated away.

From em
-------

.. code-block:: python

   em.graph.edges(type='is_in_representation_model_group')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_in_representation_model_group', target)    # the contract checks the pair


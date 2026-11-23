.. _edge-contains_proposition_set:

contains_proposition_set
========================

.. note::

   Generated from the datamodels (nodes 1.6.56, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Links an HDT (HDTNode) to a Heritage Proposition Set (GraphNode / em:EMGraph) it currently aggregates.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Contains proposition set
   * - Label (it)
     - Contiene insieme di proposizioni
   * - Reverse
     - ``is_proposition_set_of``
   * - Source
     - :ref:`HDTNode <type-HDTNode>`
   * - Target
     - :ref:`GraphNode <type-GraphNode>`
   * - CIDOC
     - ``hdto:HP33_contains``

Description
-----------

Links an HDT (HDTNode) to a Heritage Proposition Set (GraphNode / em:EMGraph) it currently aggregates. HDT-O HP33 per ECHOES D7.1 §4.2. This is the canonical way to attach an EM graph to an HDT. An EM graph can be a proposition set of multiple HDTs (many-to-many).

From em
-------

.. code-block:: python

   em.graph.edges(type='contains_proposition_set')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'contains_proposition_set', target)    # the contract checks the pair


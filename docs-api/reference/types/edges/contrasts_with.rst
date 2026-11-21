.. _edge-contrasts_with:

contrasts_with
==============

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Represents contrasting or mutually exclusive properties.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Contrasts with
   * - Label (it)
     - In contrasto con
   * - Reverse
     - —
   * - Source
     - :ref:`TimeBranchNodeGroup <type-TimeBranchNodeGroup>`
   * - Target
     - :ref:`TimeBranchNodeGroup <type-TimeBranchNodeGroup>`
   * - CIDOC
     - ``em:contrastsWith``

Description
-----------

Represents contrasting or mutually exclusive properties. This is a symmetric relation.

From em
-------

.. code-block:: python

   em.graph.edges(type='contrasts_with')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'contrasts_with', target)    # the contract checks the pair


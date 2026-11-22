.. _edge-has_embargo:

has_embargo
===========

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that an element is subject to a temporal embargo.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has embargo
   * - Label (it)
     - Ha embargo
   * - Reverse
     - ``is_embargo_of``
   * - Source
     - :ref:`Node <type-Node>`, :ref:`GraphNode <type-GraphNode>`, :ref:`LicenseNode <type-LicenseNode>`
   * - Target
     - :ref:`EmbargoNode <type-EmbargoNode>`
   * - CIDOC
     - ``P104_is_subject_to``

Description
-----------

Indicates that an element is subject to a temporal embargo. Source can be any node (GraphNode for canvas-wide embargo, LicenseNode for license-scoped embargo, or any node for node-scoped embargo), mirroring has\_license.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_embargo')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_embargo', target)    # the contract checks the pair


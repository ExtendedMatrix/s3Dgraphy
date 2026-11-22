.. _edge-has_license:

has_license
===========

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that a resource is subject to a specific license.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has license
   * - Label (it)
     - Ha licenza
   * - Reverse
     - ``is_license_of``
   * - Source
     - :ref:`Node <type-Node>`, :ref:`GraphNode <type-GraphNode>`
   * - Target
     - :ref:`LicenseNode <type-LicenseNode>`
   * - CIDOC
     - ``P104_is_subject_to``

Description
-----------

Indicates that a resource is subject to a specific license.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_license')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_license', target)    # the contract checks the pair


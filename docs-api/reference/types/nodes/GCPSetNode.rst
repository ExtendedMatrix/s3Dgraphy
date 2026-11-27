.. _type-GCPSetNode:

GCPSetNode
==========

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*The set of ground control points a registration was (or will be) solved from.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``GCPSetNode``
   * - node_type
     - ``gcp_set``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Ground control points
   * - Label (it)
     - Punti di controllo a terra
   * - CIDOC
     - ``crm:E73_Information_Object``

Description
-----------

The set of ground control points a registration was (or will be) solved from. data.points is a list of {id, world:[x,y,z], observations:[{image, pixel:[x,y]}], uncertainty?}; data.crs names the frame the world coordinates are in (null = a site-local grid, which is a different statement from absent). Minimum 3 observed non-collinear points for a similarity to be determined — reported by \`solvable\`, enforced by the runner, never at construction (a set being assembled in the field is legitimately incomplete). 1.6.24 (dev30, decided by E.D. 2 Oct 2026, D7): data.control says WHAT the points are — ground\_control\_points (default, not written) or camera\_positions: the GPS positions of the cameras themselves, each point {id, world, image, uncertainty?} with no pixel observation (the camera is where the photograph was taken from, not something seen in it), solvable with three; data.accuracy\_m is the accuracy the project records for the cameras. A chunk referenced only by its cameras' GPS is placed absolute with such a set, and validate warns «georeferenced only by camera GPS»: absolute without the control said would claim more than the data.

*Italiano*: L'insieme dei punti di controllo a terra (GCP) da cui una registrazione è stata (o sarà) calcolata. data.points è una lista di {id, world:[x,y,z], observations:[{image, pixel:[x,y]}], uncertainty?}; data.crs indica il sistema di riferimento delle coordinate world (null = una griglia locale di sito, che è un'affermazione diversa dall'assenza). Servono almeno 3 punti osservati non allineati perché una similitudine sia determinata — lo segnala \`solvable\`, lo impone il runner, mai in fase di costruzione (un insieme che si sta raccogliendo sul campo è legittimamente incompleto).

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_gcp_set <edge-has_gcp_set>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='gcp_set'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a gcp_set") as tx:        # create: one step of undo
       nid = tx.add_node('gcp_set', "name", description="…")


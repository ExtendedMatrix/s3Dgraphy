.. _type-RegistrationTransformNode:

RegistrationTransformNode
=========================

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*The 7-parameter similarity (rotation 3x3 row-major, translation [x,y,z], positive scale) that places a produced model, with data.rms and data.residuals — the error bar, stored beside the claim rather than in a log nobody keeps.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``RegistrationTransformNode``
   * - node_type
     - ``registration_transform``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Registration transform
   * - Label (it)
     - Trasformazione di registrazione
   * - CIDOC
     - ``crm:E73_Information_Object``

Description
-----------

The 7-parameter similarity (rotation 3x3 row-major, translation [x,y,z], positive scale) that places a produced model, with data.rms and data.residuals — the error bar, stored beside the claim rather than in a log nobody keeps. data.crs is the frame the model lands IN; null means a site-local frame (mode 'local'), which is NOT the same sentence as an absent transform. Re-registration is a NEW node produced by a NEW crmdig:D7; the superseded one is never edited.

*Italiano*: La similitudine a 7 parametri (rotazione 3x3 per righe, traslazione [x,y,z], scala positiva) che colloca un modello prodotto, con data.rms e data.residuals — la barra d'errore, conservata accanto all'affermazione anziché in un log che nessuno tiene. data.crs è il sistema di riferimento IN cui il modello si colloca; null indica un sistema locale di sito (modalità 'local'), che NON equivale a una trasformazione assente. Una nuova registrazione è un NUOVO nodo prodotto da un NUOVO crmdig:D7; quello superato non viene mai modificato.

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_gcp_set <edge-has_gcp_set>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_registration_transform <edge-has_registration_transform>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='registration_transform'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a registration_transform") as tx:        # create: one step of undo
       nid = tx.add_node('registration_transform', "name", description="…")


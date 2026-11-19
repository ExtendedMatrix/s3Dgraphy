.. _overview:

API overview
============

*Four things: the document, the graph, the selection, and the writes.*

The document and the graph
--------------------------

A study is a **document** (an ``.em.json``) that holds one or more **graphs**.
``em.graph`` is the graph the host shows: in EMStudio the open study, in EM
Tools the active graph of EM Setup, in a script the file given to ``em.open``.
It is read again at every access, so it is always the current one.

What ``em.graph`` returns are **views**, read-only:

* :class:`~s3dgraphy.em.GraphView` — ``node(ref)``, ``nodes(type=, name=,
  where=)``, ``edges(source=, target=, type=)``, ``chronology()``;
* :class:`~s3dgraphy.em.NodeView` — ``id``, ``name``, ``type``,
  ``description``, ``data``, ``props()`` and ``property(quale)`` with the
  chain each value comes from, ``edges()``, ``neighbours()``;
* :class:`~s3dgraphy.em.EdgeView` — ``type``, ``source``, ``target``.

The types of nodes and edges are those of the EM language:
:doc:`reference/types/index`.

The selection and the application
---------------------------------

``em.app`` is the application half (:doc:`reference/context`): the selection
(``em.app.selection()``, ``em.app.select(ids)``), the views, the Space and
its camera, the commands of the menus (``em.app.commands.run(id)``, the
equivalent of ``bpy.ops``: :doc:`reference/commands/index`), and
``em.app.notify``. With no application ``em.app.available`` is ``False`` and
its calls say so.

Writing: through the contract
-----------------------------

There is one way to change a study:

.. code-block:: python

   with em.write("Integrations after SU007") as tx:
       tx.add_edge("SU002", "is_after", "SU007")

The block becomes a **delta** that passes the contract of the connectors: the
four refusals (who writes, what is declared, the slots, the author) and the
rules of the EM language (an edge the datamodel does not allow is refused).
Then the host applies it as **one step** of undo, with one line in the Log and
its **DTC** chain: who wrote, when, with which code. If anything is refused,
nothing is written and :class:`~s3dgraphy.em.Refused` says why.

``node.raw`` gives the s3Dgraphy node itself, for whoever needs it — changing
it writes nothing that counts (no step, no Log, no author).

Events
------

``em.on(event, fn)`` listens to the closed set of events in
:data:`s3dgraphy.em.EVENTS`: ``selection-changed``, ``graph-changed``,
``document-opened``, ``document-saved``, ``document-closed``, ``locale-changed``. A write opened inside a listener runs after the delivery.

Derived artifacts
-----------------

``em.stamp(file, inputs=[…])`` gives a derived file (a picture, a table, a
model) its **stamp**: what it was made from, by whom, with which code — the
same stamp EMStudio and EM Tools write. See :doc:`info_best_practice`.

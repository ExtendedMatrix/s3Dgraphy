.. _gotchas:

Gotchas
=======

*Things that surprise once.*

``em.graph`` is read each time
   It is the host's current graph. A variable ``g = em.graph`` keeps the view
   of that moment; after a write or a change of study, read ``em.graph``
   again.

Views are not nodes
   ``NodeView`` and ``PropertyView`` are read-only; the values they return are
   copies. Changing them changes nothing.

A refused write writes nothing
   One refusal in a block and the whole block is refused
   (:class:`~s3dgraphy.em.Refused`, with the sentence of the contract). An edge
   the EM language does not allow between two types is a refusal, not a
   warning.

No author, no write
   Outside an application, set the author once: ``em.use(graph, author=…)``
   or ``--author`` (or ``S3DGRAPHY_AUTHOR``). The author is the session's,
   never an argument of a write.

``em.app`` with no application
   In a script ``em.app.available`` is ``False``; its calls raise
   :class:`~s3dgraphy.em.NotAvailable`. Check before using it in code meant to
   run everywhere.

``em.app.commands.run`` clicks the menu
   A command runs only when its entry is enabled at that moment (a document
   open, a selection…). Slots passed to an EMStudio menu command are not used
   yet: see :doc:`reference/commands/index`.

A write inside a listener comes after
   ``em.write`` opened in an ``em.on`` listener is deferred until the event is
   delivered.

Two ``em`` on PyPI
   ``import em`` is s3dgraphy's. An unrelated package also called ``em`` exists;
   if both are installed, ``import s3dgraphy.em as em`` is the sure form.

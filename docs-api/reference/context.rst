.. _context:

Context — ``em.app`` and ``ctx``
================================

*What the host gives: the application, the open document, the plugin's handle.*
Generated for em API |api|.

The open document and graph
---------------------------

``em.graph`` is the graph the host shows (a :class:`~s3dgraphy.em.GraphView`),
read again at every access. In EMStudio it is the open study, in EM Tools the
active graph of EM Setup, in a script the one of ``em.open`` / ``em.use``.
With none, reading it raises ``AttributeError`` with a sentence that says so.

``em.app`` — the application
----------------------------

.. autoclass:: s3dgraphy.em._App
   :members:
   :no-index:

.. autoclass:: s3dgraphy.em._App._Space
   :members:
   :no-index:

.. autoclass:: s3dgraphy.em._App._Commands
   :members:
   :no-index:

What a host implements behind ``em.app`` (EMStudio, EM Tools, the «no
application» host of a script) is :class:`s3dgraphy.em.host.App`. A host may
give more: ``em.app.space`` is then the host's own, and ``em.app.<name>``
reaches what its application adds — in EMStudio :doc:`app/space` (layers,
epoch, profile), :doc:`app/workspaces` and :doc:`app/windows`; ``dir(em.app)``
lists them, and ``em.app.commands.list()`` the commands and actions with their
parameters.

``ctx`` — in a plugin
---------------------

``setup(ctx)`` receives a :class:`s3dgraphy.em.plugins.Context`.

.. autoclass:: s3dgraphy.em.plugins.Context
   :members:
   :no-index:

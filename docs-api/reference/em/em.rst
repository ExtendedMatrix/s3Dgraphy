``em`` — the module
===================

.. module:: s3dgraphy.em

``import em`` (or ``from s3dgraphy import em``). Generated for em API |api|.

.. autodata:: s3dgraphy.em.API_VERSION
   :annotation:

.. autodata:: s3dgraphy.em.EVENTS
   :annotation:

.. data:: graph
   :no-index:

   The host's current graph, a :class:`GraphView`; read at every access.

.. data:: vocab
   :no-index:

   The vocabularies, a :class:`~s3dgraphy.em.vocab.Vocab`.

.. data:: profiles
   :no-index:

   The packages of the document, a :class:`~s3dgraphy.em.vocab.Profiles`.

.. data:: extensions
   :no-index:

   Install, list, enable from disk: :class:`~s3dgraphy.em.extensions.Extensions`.

.. data:: ext
   :no-index:

   What the active plugins expose to the console (``em.ext.<plugin>.<name>``).

.. data:: app
   :no-index:

   The application half: :doc:`../context`.

Functions
---------

.. autofunction:: s3dgraphy.em.open
.. autofunction:: s3dgraphy.em.use
.. autofunction:: s3dgraphy.em.save
.. autofunction:: s3dgraphy.em.help
.. autofunction:: s3dgraphy.em.write
   :no-index:
.. autofunction:: s3dgraphy.em.stamp
   :no-index:
.. autofunction:: s3dgraphy.em.on
   :no-index:
.. autofunction:: s3dgraphy.em.off
   :no-index:

Errors
------

:class:`~s3dgraphy.em.errors.EmError`, :class:`~s3dgraphy.em.errors.NotAvailable`,
:class:`~s3dgraphy.em.errors.Refused`, :class:`~s3dgraphy.em.graph.NodeNotFound`,
:class:`~s3dgraphy.em.graph.AmbiguousNode`, :class:`~s3dgraphy.em.vocab.ConceptNotFound`,
:class:`~s3dgraphy.em.stamps.StampError` — all importable from ``em``.

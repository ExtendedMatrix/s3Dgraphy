.. _change-log:

Change log
==========

*What changed in* ``em`` *between versions.* A plugin reads these numbers
through ``em_api_min`` / ``em_api_max`` in its manifest; they are the API's
own, distinct from s3dgraphy's and EMStudio's.

1.2.0 — 19 November 2026
------------------------

* ``em.stamp(artifact, inputs=[…])`` and, in plugins, ``ctx.stamp``: the stamp
  of a derived artifact (:mod:`s3dgraphy.em.stamps`), the same in every host.
* Slots ``door.reader@2`` (folders, claimed extensions, a panel) and
  ``space.layer@1`` (a layer of the Space described by a read-only command).
  Slots have their own versions: a plugin for a newer slot sees that entry
  off, not itself.
* A plugin that uses ``ctx.stamp`` declares ``em_api_min = "1.2"``.

1.1.0 — 18 November 2026
------------------------

* ``em.plugins``: plugins loaded from disk, checked before running
  (``em_api_min``/``max``, the wheels' Python, the descriptor), ``setup(ctx)``
  / ``teardown(ctx)``.
* ``em.ext``: what the active plugins expose to the console (slot
  ``console@1``); ``em.help()`` lists their commands.
* The event ``document-saved``.
* Phase 2 slots drawn: ``inspector.section@1``, ``tabular.column@1``,
  ``statusbar@1``, ``space.tool@1``, ``panel@1`` (no change of the API number:
  slots have their own versions).
* EM Tools becomes a host: ``em`` in Blender reads EM Setup's active graph.

1.0.0 — 18 November 2026
------------------------

* ``em``: ``em.graph`` (views), ``em.vocab``, ``em.profiles``, ``em.write``
  (one act, one step, through the contract), ``em.extensions``, ``em.on`` /
  ``em.off``, ``em.app`` (selection, views, Space, commands, notify),
  ``em.open`` / ``em.use`` / ``em.save`` and ``python -m s3dgraphy.em run``.

Not yet numbered (this site)
----------------------------

* ``import em`` works as ``from s3dgraphy import em``, and ``python -m em``
  as ``python -m s3dgraphy.em``.

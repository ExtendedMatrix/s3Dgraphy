.. _app-windows:

``em.app.windows`` — the windows
================================

*The windows of the workspace in front, the detached ones, and the types an
area can show.* EMStudio only.

.. code-block:: python

   from s3dgraphy import em

   for w in em.app.windows:                # the same as em.app.windows.list()
       print(w["id"], w["type"], w["active"], w["detached"])
   wid = em.app.windows.open("console")    # a Python console beside the active window
   em.app.windows.open("scene", area=wid)  # …and that area turned into a 3D Space
   em.app.windows.active = wid

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Name
     - What it is
   * - ``list()``
     - every window: ``{id, type, label, active, detached}``
   * - ``active``
     - the id of the active window; **set** it to make another one active
   * - ``types``
     - the window types: ``graph``, ``scene``, ``table``, ``inspector``,
       ``outliner``, ``viewer``, ``console``, ``script``, …
   * - ``open(type, area=None, split="row")``
     - a window of ``type``: in the area ``area`` (a window id, which changes
       type), else beside the active window (``split``: ``row`` or ``col``);
       its id

``em.app.view(name)`` brings the first window of a type to the front (the
console and the Script Editor included); the action
:doc:`../commands/magnify` magnifies one.

Every window can be detached into a window of the system (another screen) and
put back. The Python console and the Script Editor keep, detached, the same
Python session, the same history, the same script open: «Run Script» (Alt+P)
writes in the console wherever it is.

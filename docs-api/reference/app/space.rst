.. _app-space:

``em.app.space`` — the Space
============================

*The 3D Space of EMStudio as an object: what it shows, the epoch, the hardware
profile, the camera.* EMStudio only (in EM Tools and in a script with no
application, ``em.app.space`` has the four calls of every host —
``camera``, ``set_camera``, ``frame``, ``pick`` — and nothing else).

.. code-block:: python

   from s3dgraphy import em

   sp = em.app.space
   for layer in sp.layers:                 # the models and tilesets
       print(layer.name, layer.kind, layer.visible, layer.epochs, layer.bytes)
   sp.layer("Rilievo 2026").visible = False
   sp.epoch = "Medioevo"                   # an epoch's id or name
   print(sp.epoch["name"], sp.profile["profile"])
   sp.profile = "web"                      # the versions a browser loads; None: read from the machine

Every reading asks the page: the Space is the one in front of the person,
read when the line runs (nothing is cached in Python). A reading that needs a
Space with none open answers what there is (``[]`` for the layers) or raises
``em.NotAvailable`` with the page's words.

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Name
     - What it is
   * - ``layers``
     - the models and tilesets of the Space, a list of ``Layer``
   * - ``layer(ref)``
     - one layer by its id or its name (``None``: not in the Space)
   * - ``epochs``
     - the epochs the Space can show: ``{id, name, start, end}``
   * - ``epoch``
     - the epoch shown, ``{id, name}``; **set** it with an id or a name
   * - ``profile``
     - the hardware profile the Space loads for: ``{profile, chosen, read, why}``
       (``desktop``, ``web``, ``mobile``); **set** it, or ``None`` to read it
       from the machine again
   * - ``camera()``
     - the camera of the first Space open: ``{pos, target, …}``
   * - ``set_camera(camera)``
     - move it (the shape ``camera()`` returns)
   * - ``frame(ids)``
     - frame these nodes (their proxies, their models)
   * - ``pick(prompt, primitive="point")``
     - ask the person for a point in the Space

``Layer``
---------

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Name
     - What it is
   * - ``name``, ``id``, ``key``
     - its name, the id of its model node, its key in the Space (``rm:<id>``)
   * - ``kind``
     - ``model`` or ``tileset``
   * - ``visible``
     - shown or hidden; **set** it to hide or show the layer (the eye of the Outliner)
   * - ``epochs``
     - the names of the epochs it depicts
   * - ``bytes``
     - the weight of its file, when known (``None`` otherwise)
   * - ``file``
     - its file's address

The commands of the Space with an id of their own — the aligned views, the
orthographic switch, framing the selection or everything, the 3D cursor —
are actions: :doc:`../commands/spaceView`, :doc:`../commands/spaceToggleOrtho`,
:doc:`../commands/spaceFrameSelected`, :doc:`../commands/spaceFrameAll`,
:doc:`../commands/spaceCursorReset`.

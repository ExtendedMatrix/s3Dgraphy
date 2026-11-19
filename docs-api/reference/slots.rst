.. _slots:

Slots
=====

.. note::

   Generated from ``s3dgraphy.extensions.slots`` for em API 1.2.0 by ``docs-api/_tools/gen_slots.py``.

A **slot** is a place of the interface or of the flow where a host accepts something from a plugin, with a name and a version: ``in = ["context.node@1", "menu.tools@1"]`` in the plugin's manifest. A slot newer than the host's turns that entry off, not the plugin.

.. list-table::
   :header-rows: 1
   :widths: 22 16 40 22

   * - Slot
     - State
     - Where
     - Notes
   * - ``check@1``
     - drawn
     - a read-only check that returns warnings
     - takes a command, read only (``writes = false``)
   * - ``console@1``
     - drawn
     - functions exposed to the console as ``em.ext.<id>``
     - —
   * - ``context.edge@1``
     - declared, not drawn yet
     - the context menu of an edge
     - —
   * - ``context.node@1``
     - drawn
     - the context menu of a node or of the selection (Matrix, Space); offered by ``when``
     - takes a command
   * - ``context.outliner@1``
     - declared, not drawn yet
     - the context menu of the Outliner
     - —
   * - ``door.reader@2``
     - drawn
     - «Bring in…»: a reader of a kind of file or of a folder; may claim known extensions
     - takes a command
   * - ``event@1``
     - drawn
     - listening to the events (``ctx.on``)
     - —
   * - ``export.narrative@1``
     - drawn
     - Narrative ▸ Export (the command returns a file)
     - takes a command, returns a file (``ctx.file``)
   * - ``inspector.section@1``
     - drawn
     - a section of the Inspector for a type of node: values (read only) and buttons
     - takes a command, read only (``writes = false``)
   * - ``keymap@1``
     - declared, not drawn yet
     - a keyboard shortcut
     - —
   * - ``menu.file.export@1``
     - drawn
     - File ▸ Export ▸ … (the command returns a file)
     - takes a command, returns a file (``ctx.file``)
   * - ``menu.file.import@1``
     - drawn
     - File ▸ Import ▸ …
     - takes a command
   * - ``menu.tools@1``
     - drawn
     - Tools ▸ Plugin ▸ <plugin> ▸ <command>
     - takes a command
   * - ``palette@1``
     - declared, not drawn yet
     - the command palette
     - —
   * - ``panel@1``
     - drawn
     - a declarative panel (``[[code.panels]]``): fields, values, buttons — never HTML
     - —
   * - ``space.layer@1``
     - drawn
     - a layer of the Space described by a read-only command, drawn by the host
     - takes a command, read only (``writes = false``)
   * - ``space.pick@1``
     - drawn
     - asking the person to place a point in the Space (``em.app.space.pick``)
     - —
   * - ``space.tool@1``
     - drawn
     - a tool of the Space's bar: a primitive placed, then the command with the geometry
     - takes a command
   * - ``statusbar@1``
     - drawn
     - a zone of text in the status bar
     - takes a command, read only (``writes = false``)
   * - ``tabular.column@1``
     - drawn
     - a computed, read-only column of a sheet of the Tabular
     - takes a command, read only (``writes = false``)
   * - ``workspace@1``
     - declared, not drawn yet
     - a workspace
     - —

Kinds of a command's slot (what the host fills, never invents): ``id``, ``ids``, ``string``, ``number``, ``path``, ``geometry``, ``bool``.

Kinds of a panel's field: ``number``, ``text``, ``choice``, ``node``, ``check``, ``value``, ``button``; at most 40 fields. Panels open at: ``right``, ``left``, ``below``, ``window``.

Primitives of ``space.tool``: ``point`` (1–1 clicks), ``line`` (2–2 clicks), ``polyline`` (2–n clicks), ``surface`` (3–n clicks).

Sheets a ``tabular.column`` may join: ``Units``, ``Epochs``, ``Documents``, ``Claims``, ``Authors``.

When a ``context.node`` command is offered (``when``)
--------------------------------------------------------

.. code-block:: text

   when   := clause ( " and " clause )*        (empty: always)
   clause := "document"                        a document is open
           | "selection:none" | "selection:any" | "selection:one" | "selection:many"
           | "selection:" TYPE ( "|" TYPE )*   at least one selected, every one of these types


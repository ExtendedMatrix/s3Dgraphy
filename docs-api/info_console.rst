The console and its completion
==============================

*Python in EMStudio as in Blender: a console, a script editor, Tab.*

The **Python console** (*Tools ▸ Python console*, or any area turned into a
console from its type selector) and the **Script Editor** are windows of
EMStudio; the workspace **Scripting** holds both, beside the Matrix. They share
ONE Python session on the open document: ``em`` imported, ``g`` the graph,
``sel`` the selection.

Tab, as in Blender
------------------

In the console, **Tab** (or **Ctrl+Space**, for whom Tab is taken) completes
what is before the cursor:

* one possibility: it is completed;
* more: their common start is completed and **the list is printed in the
  output**, each name with the mark of its kind — ``▣`` module, ``◆`` class,
  ``ƒ`` function or method, ``•`` property, ``=`` value, ``k`` a Python
  keyword — and the first line of what it is;
* after a callable and its ``(`` — ``g.node(``, ``em.app.commands.run(`` —
  its **signature** and the first lines of its docstring;
* inside ``em.app.commands.run("open", `` the command's own parameters
  (``path=``, ``replace=``) and its signature;
* inside a string, the values of the domain: the command ids in
  ``commands.run("…``, the ids and names of the nodes in ``g.node("…``, the
  node types in ``g.nodes("…`` or ``type="…``, the epochs' names in
  ``epoch="…``, the choices of a parameter that has them
  (``spaceView``'s ``side="…``).

.. code-block:: text

   >>> em.app.
     • available      • commands     ƒ notify       ƒ on
     ƒ select         ƒ selection    • space        ƒ view
     • windows        • workspaces
   >>> g.node(
   node(ref: NodeRef) -> NodeView
     By id or by name. Two nodes with that name: AmbiguousNode (use the id) — never the first one found.

A Tab never runs anything that asks the page: the names of ``em.app.space``
are listed without reading the layers.

In the **Script Editor** the same answer comes as a list under the cursor
while typing after a name or a dot, and on **Ctrl+Space**: the kind as an
icon, the first line of the docstring beside it, the signature as the first
row when a call is open. Enter accepts.

One source
----------

Both read the live session (``dir``, ``inspect.signature``, the docstrings)
and the parameters EMStudio declares for its commands — the table
``frontend/src/script-commands.json`` that the :doc:`reference/commands/index`
pages are generated from, and that ``em.app.commands.list()`` returns.

Commands with parameters
------------------------

``em.app.commands.run(id, **params)`` reaches a command of the menus or a
named action (``addUnitAbove``, ``connect``, ``moveToEpoch``, ``fold``,
``frameNode``…). As Blender's operators: with its values given a command
runs **without its window**; without them its window opens, filled with what
was given:

.. code-block:: python

   em.app.commands.run("saveAs", path="/studi/templu/EM/templu-v12.em.json")
   em.app.commands.run("door", paths=["/studi/templu/foto/D_12.jpg"], date="2024", confirm=True)
   new = em.app.commands.run("addUnitAbove", of="US102", name="US900")
   em.app.commands.run("moveToEpoch", ids=[new], epoch="Età moderna")

A name a command does not take, a wrong type, a value not among the choices
are refused with ``em.NotAvailable`` in the page's language — never dropped.

The Space, the workspaces and the windows are objects:
:doc:`reference/app/space`, :doc:`reference/app/workspaces`,
:doc:`reference/app/windows`.

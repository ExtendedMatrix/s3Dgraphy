.. _quickstart:

Quickstart
==========

*Three lines of Python on Templu Mare, in EMStudio and outside it.*

``import em``
-------------

Everything starts with one line, as ``import bpy`` in Blender:

.. code-block:: python

   import em

``em`` is the same in the three places it lives:

* **in EMStudio** — the Python console, the Script Editor and the plugins:
  ``em`` is already imported and its graph is the open study;
* **in EM Tools** — Blender's console and scripts, beside ``bpy``: its graph is
  the active graph of EM Setup;
* **in a script or a notebook** — with s3dgraphy installed
  (``pip install s3dgraphy``), on a file: ``em.open(path)``, then
  ``em.save()``. No application is needed, as Blender «as a module».

``import em`` and ``from s3dgraphy import em`` are the same module.

Open the console in EMStudio
----------------------------

#. Open a study — here, Templu Mare.
#. ``Tools ▸ Python console…``. A **Python Console** window opens under the
   window you are in (a second time, the same one comes forward). It is a
   window like the others, as in Blender: any area of any workspace becomes a
   console from the type selector at the head of the window. Its head says
   **Python · em on «…»** and **beta**. ``em`` is imported, ``g`` is
   ``em.graph`` and ``sel`` is the selection.

Three first commands
--------------------

**Read a unit.** A node is found by its name or its id; its edges say what it
is connected to.

.. literalinclude:: examples/quickstart_read.py
   :language: python

**Look at the whole study.** ``nodes()`` filters by type, name or property.

.. literalinclude:: examples/quickstart_find.py
   :language: python

**Write.** Every change is a block opened by ``em.write`` with a label: the
block is one step of ``Edit ▸ Undo``, one line of the Log, and an act whose
chain keeps the code that ran.

.. literalinclude:: examples/quickstart_write.py
   :language: python

In the console, press **Try** first: the same code runs as a proof and shows
what it would change, applying nothing.

Scripts: the Script Editor
--------------------------

A few lines are typed in the console; a script that lasts is written in the
**Script Editor**, the other Python window of EMStudio (Blender's Text Editor
beside its Python Console):

#. Choose **Script Editor** from the type selector at the head of a window —
   or open the **Scripting** workspace: the **+** at the end of the workspace
   tabs ▸ *From a model* ▸ **Scripting** (the Script Editor on the left, the
   console under it, the Matrix on the right).
#. **Templates ▾** starts from an example of this reference: the units of an
   epoch, a rename in series, a table exported as CSV, a property added to the
   selection.
#. **▶ Run Script** (:kbd:`Alt+P`, as in Blender) runs the script in the
   console's session — the same interpreter: what the script defines, the
   console sees — and its output goes to the console. **Try**
   (:kbd:`Alt+Shift+P`) runs it as a proof.
#. **Save** (:kbd:`⌘S` / :kbd:`Ctrl+S`) writes ``<name>.py`` in the
   ``scripts/`` folder beside the study's ``.em.json``; **Open ▾** lists the
   scripts there. A study with no folder (a room, a document never saved)
   keeps its scripts in the browser, for that project. A script changed and
   not saved shows **●** in the window's title.

A script saved there runs outside EMStudio as it is (next section).

The same, outside EMStudio
--------------------------

Save the three blocks as files and run them on a copy of the study:

.. code-block:: console

   $ python -m em run quickstart_read.py --file templu-mare.em.json
   $ python -m em run quickstart_write.py --file templu-mare.em.json \
         --author https://orcid.org/0000-0000-0000-0000 --save

``--author`` is who writes (in EMStudio it is the person signed in);
``--save`` writes the file back; ``--dry-run`` turns every write into a proof.
Or in a notebook, with the author set once for the session:

.. literalinclude:: examples/notebook.py
   :language: python

``em.help()`` prints what ``em`` offers where you are.

Next: :doc:`info_overview`.

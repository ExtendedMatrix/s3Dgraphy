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

* **in EMStudio** — the Python console and the plugins: ``em`` is already
  imported and its graph is the open study;
* **in EM Tools** — Blender's console and scripts, beside ``bpy``: its graph is
  the active graph of EM Setup;
* **in a script or a notebook** — with s3dgraphy installed
  (``pip install s3dgraphy``), on a file: ``em.open(path)``, then
  ``em.save()``. No application is needed, as Blender «as a module».

``import em`` and ``from s3dgraphy import em`` are the same module.

Open the console in EMStudio
----------------------------

#. ``Settings… ▸ Advanced``: tick **Turn on the experimental functions on this
   machine**, press **Save**, and reload EMStudio when it asks.
#. Open a study — here, Templu Mare.
#. ``Tools ▸ Python console…``. The head says **Python · em on «…»**. ``em`` is
   imported, ``g`` is ``em.graph`` and ``sel`` is the selection.

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

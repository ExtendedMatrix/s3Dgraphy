EMStudio Python API
===================

*The Python of Extended Matrix: one library,* ``em``, *in EMStudio, in EM Tools
for Blender and in a script of your own.*

This is the reference of ``em`` |api| (s3dgraphy |s3d|). The manual of
EMStudio says how to use the application; this site says what Python can do
with a study: read its graph, write into it as one step of undo, call the
application's commands, and extend it with plugins.

.. code-block:: python

   import em

   em.open("templu-mare.em.json")           # in EMStudio the study is already open
   for su in em.graph.nodes(type="US"):
       print(su.name, su.description)

.. seealso::

   - `The EMStudio manual
     <https://docs.extendedmatrix.org/projects/emstudio-doc/en/1.6/>`__ — how
     to use the application, the Python console included.
   - `Extending EMStudio
     <https://docs.extendedmatrix.org/projects/emstudio-doc/en/1.6/extending/index.html>`__
     — the guide for whoever builds a package: data first, then commands in
     Python through ``em``.
   - `docs.extendedmatrix.org <https://docs.extendedmatrix.org>`__ — all the
     documentation of the Extended Matrix.

Documentation
-------------

.. toctree::
   :maxdepth: 1

   info_quickstart
   info_overview
   info_plugins
   info_console
   info_best_practice
   info_gotchas
   change_log

Reference
---------

.. toctree::
   :maxdepth: 2

   reference/index

* :ref:`genindex` — every name, as Blender's index
* :ref:`modindex` — the modules
* :ref:`search`

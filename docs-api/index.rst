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

Documentation
-------------

.. toctree::
   :maxdepth: 1

   info_quickstart
   info_overview
   info_plugins
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

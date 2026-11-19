.. _reference:

Reference
=========

*Every public name of* ``em`` |api|, *generated from the code.*

As Blender's ``bpy.ops``, ``bpy.types`` and ``bpy.context``:

.. list-table::
   :widths: 30 70

   * - :doc:`commands/index`
     - ``em.app.commands.run(id)`` — every command of EMStudio (our ``bpy.ops``)
   * - :doc:`types/index`
     - the types of nodes and edges of the EM language (our ``bpy.types``)
   * - :doc:`context`
     - ``em.app``, ``ctx`` in a plugin, the open document and graph (our ``bpy.context``)
   * - :doc:`slots`
     - where a plugin's command is drawn

The modules:

.. toctree::
   :maxdepth: 1

   em/em
   em/graph
   em/write
   em/vocab
   em/stamps
   em/extensions
   em/plugins
   em/events
   em/errors
   em/messages
   em/host

.. toctree::
   :hidden:

   context
   commands/index
   types/index
   slots

.. _plugins:

Plugins and slots
=================

*A plugin is Python that EMStudio and EM Tools load from disk, with the same*
``em``.

A plugin is the ``[code]`` section of an ``em-extension.toml``: it names its
module, the ``em`` versions it works with (``em_api_min``, ``em_api_max``) and
its **commands**, each with the **slots** where the host draws it
(``in = ["context.node@1"]``) and whether it writes (``writes``). Its module
has a ``setup(ctx)``:

.. code-block:: python

   import em

   def setup(ctx):
       @ctx.command("count-units")
       def count_units(slots):
           n = len(list(em.graph.nodes(type="US")))
           em.app.notify(f"{n} units")

       ctx.on("document-saved", lambda payload: em.app.notify("saved"))
       ctx.expose("count", count_units)        # em.ext.<plugin>.count in the console

``ctx`` (:class:`~s3dgraphy.em.plugins.Context`) is the plugin's handle:
``command``, ``on``, ``expose``, ``file`` (a file returned to the host),
``stamp`` (the stamp of a derived artifact), ``data_dir``. Inside a command,
``em.write`` writes **as the plugin**: a command declared ``writes = false``
cannot write at all.

* The slots, with their versions and what each draws: :doc:`reference/slots`.
* The loader and its checks: :mod:`s3dgraphy.em.plugins`.
* Installing, enabling and removing from Python: :mod:`s3dgraphy.em.extensions`.

How to install packages and plugins, repositories and signatures, is in the
EMStudio manual, *How-to ▸ Extensions*
(`docs.extendedmatrix.org/projects/emstudio-doc
<https://docs.extendedmatrix.org/projects/emstudio-doc/en/1.6/how-to/extensions/index.html>`_);
the guide «Extending EMStudio» there tells how to write one.

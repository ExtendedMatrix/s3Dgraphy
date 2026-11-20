.. _app-workspaces:

``em.app.workspaces`` — the workspaces
======================================

*The tabs of EMStudio's bar.* EMStudio only.

.. code-block:: python

   from s3dgraphy import em

   for w in em.app.workspaces:             # the same as em.app.workspaces.list()
       print(w["id"], w["label"], w["active"])
   em.app.workspaces.active = "scripting"  # an id or a label

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Name
     - What it is
   * - ``list()``
     - every workspace: ``{id, label, builtin, active}``, in the bar's order
   * - ``active``
     - the id of the workspace in front; **set** it (an id or a label) to switch

The seven built-in workspaces are ``canvas`` (Stratigraphy), ``provenance``
(Sources), ``assets`` (Contents), ``narrative``, ``space``, ``sheets`` and
``scripting`` — the Script Editor, the Python console under it and the Matrix
beside them. The person's own workspaces follow, with their own ids.

"""``import em`` — Extended Matrix's scripting API, by its short name.

As ``import bpy`` in Blender::

    import em

    em.open("scavo.em.json")
    print(em.graph.node("US12").description)

``em`` IS :mod:`s3dgraphy.em` — the same module object, not a copy:
``import em`` and ``from s3dgraphy import em`` give one ``em``, one host, one
set of listeners. This file only puts the library's module under the short
name; it holds nothing else and never will.

The name ``em`` is also taken on PyPI by an unrelated terminal highlighter
(``em`` 0.4.0). If both are installed the one installed last owns ``em/``;
``import s3dgraphy.em as em`` always works and means the same thing.
"""
import sys as _sys

from s3dgraphy import em as _em

_sys.modules[__name__] = _em

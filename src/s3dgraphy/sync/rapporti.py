"""Re-export of :mod:`s3dgraphy.rapporti`, its home since dev29.

The parser of the ``rapporti`` packed string has no database in it, and it
lived here, so importing a .graphml went through this package's
``__init__`` — which requires SQLAlchemy. Measured with a plain
``pip install s3dgraphy`` on San Pietro (1 Oct 2026): ``import_graphml``
failed. The module moved one level up; this name stays for the callers
(pyArchInit among them) that import it from here, private names included.
"""

from .. import rapporti as _home

globals().update({k: v for k, v in vars(_home).items()
                  if not (k.startswith("__") and k.endswith("__"))})
__all__ = list(_home.__all__)

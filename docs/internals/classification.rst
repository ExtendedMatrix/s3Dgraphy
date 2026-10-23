Stratigraphic Classification
============================

.. versionadded:: 0.1.41
.. versionchanged:: 1.5.0

The :mod:`s3dgraphy.classification` module is the **single source of
truth** for the stratigraphic type taxonomy in s3dgraphy 1.5. It is
JSON-driven: the canonical metadata for every type lives in
``JSON_config/s3Dgraphy_node_datamodel.json``, and Python code reads
from that file rather than hardcoding type lists.

Why it exists
-------------

Pre-1.5, downstream tools (EM-blender-tools UI pickers, GraphML
importer BR-handling, filter chains, material maps) each maintained
their own list of "what counts as a real US" or "what counts as a
series". Inevitably they drifted from each other and from the EM
formalism. The classification module collapses the question into a
single API backed by the JSON datamodel: every consumer asks the
*same* question and gets the *same* answer.

The two axes
------------

Every stratigraphic subtype carries two classification fields in the
JSON datamodel:

``family``
    One of ``"real"``, ``"virtual"``, or ``null``.

    - ``"real"`` — empirically observed in the field
      (``US``, ``USD``, ``SF``, ``RSF``, ``TSU``, ``USN``, ``UL``).
    - ``"virtual"`` — reconstructed / inferred
      (``USVs``, ``USVn``, ``VSF``).
    - ``null`` — helper nodes that are not proper stratigraphic
      units (``BR``, ``SE``).

``is_series``
    True iff the abbreviation starts with ``ser`` (``serSU``,
    ``serUSD``, ``serUSVs``, ``serUSVn``, ``serVSF``). A *series* groups multiple
    stratigraphic units with the same archaeological semantics into a
    single conceptual entity.

A test (``test_stratigraphic_classification.py``) locks the invariant:
every entry in :data:`STRATIGRAPHIC_CLASS_MAP` has a matching subtype
in the JSON; the abbreviation convention is honoured; the accessors
agree with the JSON.

Public API
----------

Imported from ``s3dgraphy`` directly::

    from s3dgraphy import (
        get_family, is_real, is_virtual, is_series,
        REAL_US_TYPES, VIRTUAL_US_TYPES,
        SERIES_US_TYPES, ALL_US_TYPES,
    )

    get_family("US")       # → "real"
    get_family("USVn")     # → "virtual"
    get_family("BR")       # → None  (helper node)

    is_real("RSF")         # → True
    is_virtual("VSF")      # → True
    is_series("serUSVn")   # → True
    is_series("USVn")      # → False

    "USVs" in VIRTUAL_US_TYPES  # → True

The frozenset constants (``REAL_US_TYPES``, ``VIRTUAL_US_TYPES``,
``SERIES_US_TYPES``, ``ALL_US_TYPES``) are computed from the JSON on
first access and cached process-wide.

Iteration::

    from s3dgraphy.classification import iter_subtypes, get_subtype_info

    for abbr, info in iter_subtypes():
        print(abbr, info["label"], info["family"], info["is_series"])

    info = get_subtype_info("RSF")
    # {'label': 'Reused Special Find',
    #  'family': 'real',
    #  'is_series': False,
    #  'cidoc_mapping': ...,
    #  ...}

Worked example — adding a new subtype
-------------------------------------

Suppose you want to add a ``USP`` (Pottery Stratigraphic Unit) subtype
without writing any Python:

#. Open ``JSON_config/s3Dgraphy_node_datamodel.json``.
#. Add a new entry under
   ``stratigraphic_nodes.StratigraphicNode.subtypes``::

       "USP": {
         "label": "Pottery Stratigraphic Unit",
         "family": "real",
         "is_series": false,
         "abbreviation": "USP",
         "cidoc_mapping": "A8 Stratigraphic Unit",
         "description": "Stratigraphic unit composed entirely of pottery sherds."
       }

#. Register a Python class in
   :data:`s3dgraphy.utils.utils.STRATIGRAPHIC_CLASS_MAP`::

       STRATIGRAPHIC_CLASS_MAP["USP"] = PotteryStratigraphicUnit

#. Add a visual rule in ``JSON_config/em_visual_rules.json`` so the
   GraphML exporter knows how to render USP.

After step 1 the classification API immediately recognises USP:

.. code-block:: python

   from s3dgraphy import is_real, REAL_US_TYPES
   is_real("USP")              # → True
   "USP" in REAL_US_TYPES      # → True

Every consumer that uses the accessors picks up the new type
*automatically*, without a code change.

Currently registered types
--------------------------

.. note::
   The table below is the **v1.5.4 baseline** propagated from the 1.5
   documentation push. On the 1.6dev branch the JSON datamodel may have
   evolved; regenerate this table from
   ``src/s3dgraphy/data/stratigraphic_types.json`` (or the equivalent
   1.6 location) before tagging a 1.6 release. See CHANGELOG for
   per-version additions.

As of datamodel JSON v1.5.4 (s3dgraphy 1.5.1):

================  ==========  =========  ==================================
Abbreviation       family      series     Class
================  ==========  =========  ==================================
``US``             real        no         ``StratigraphicUnit``
``USD``            real        no         ``DocumentaryStratigraphicUnit``
``SF``             real        no         ``SpecialFindUnit``
``RSF``            real        no         ``ReusedSpecialFind`` (Repositioned)
``TSU``            real        no         ``TransformationStratigraphicUnit``
``USN``            real        no         ``NegativeStratigraphicUnit``
``UL``             real        no         ``WorkingUnit``
``USVs``           virtual     no         ``StructuralVirtualStratigraphicUnit``
``USVn``           virtual     no         ``NonStructuralVirtualStratigraphicUnit``
``VSF``            virtual     no         ``VirtualSpecialFindUnit``
``serSU``          real        yes        ``SeriesOfStratigraphicUnit``
``serUSD``         real        yes        ``SeriesOfDocumentaryStratigraphicUnit``
``serUSVs``        virtual     yes        ``SeriesOfStructuralVirtualStratigraphicUnit``
``serUSVn``        virtual     yes        ``SeriesOfNonStructuralVirtualStratigraphicUnit``
``serVSF``         virtual     yes        ``SeriesOfVirtualSpecialFindUnit``
``BR``             (none)      –          ``ContinuityNode``
``SE``             (none)      –          ``StratigraphicEventNode``
================  ==========  =========  ==================================

Use the API rather than copying this table — it can drift between
releases as the JSON evolves.

Where classification flows
--------------------------

The classification API powers (non-exhaustive):

- **GraphML importer BR-handling** — REAL types live forever by
  default, VIRTUAL types live only in their birth epoch
  (see :doc:`/internals/transforms` ``materialize_continuity``).
- **Compact transform** — series types are excluded from the SL_PD
  hoist (their semantics are aggregate, not unit-level).
- **EM-blender-tools** — UI pickers, filter chains, material maps
  consume the frozensets instead of hardcoded lists.
- **Palette dispatch** — :mod:`exporter.graphml.node_registry` cross-
  references the JSON for required-stencil enforcement.

API Reference
-------------

See :doc:`/api/classification` for the full module autodoc.

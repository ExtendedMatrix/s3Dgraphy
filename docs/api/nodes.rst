Node Types
==========

This section documents every node type in s3dgraphy. All nodes inherit
from :class:`s3dgraphy.nodes.base_node.Node` (documented in
:doc:`/api/core`) and register their ``node_type`` string in the global
``Node.node_type_map`` on import.

.. note::

   The ``node_type`` *string* — not the Python class name — is what is
   stored on the node, written to GraphML/JSON, and matched by
   :meth:`Graph.get_nodes_by_type` and the connection-validation rules.
   The class hierarchy (``real`` vs ``virtual`` families, ``is_series``
   membership) is driven by ``JSON_config/s3Dgraphy_node_datamodel.json``;
   use the helpers in :doc:`/api/classification` rather than hard-coding
   these strings.

Node type reference
-------------------

.. list-table::
   :header-rows: 1
   :widths: 22 16 62

   * - Class
     - ``node_type``
     - Meaning
   * - ``StratigraphicNode``
     - ``StratigraphicNode``
     - Abstract base for all stratigraphic units.
   * - ``StratigraphicUnit``
     - ``US``
     - Stratigraphic Unit — positive matter layer/context.
   * - ``NegativeStratigraphicUnit``
     - ``USN``
     - Negative unit — a cut, lacuna or interface (absence of matter).
   * - ``StructuralVirtualStratigraphicUnit``
     - ``USVs``
     - Structural Virtual unit — reconstructed structural element.
   * - ``NonStructuralVirtualStratigraphicUnit``
     - ``USVn``
     - Non-structural Virtual unit — hypothetical non-structural element.
   * - ``SpecialFindUnit``
     - ``SF``
     - Special Find — a not-in-situ element needing repositioning.
   * - ``VirtualSpecialFindUnit``
     - ``VSF``
     - Hypothetical reconstruction of a fragmented Special Find.
   * - ``ReusedSpecialFind``
     - ``RSF``
     - Re-used architectural/decorative element (spolia).
   * - ``DocumentaryStratigraphicUnit``
     - ``USD``
     - Documentary unit — based on historical/archival evidence.
   * - ``TransformationStratigraphicUnit``
     - ``TSU``
     - Transformation unit — toolmarks/reworkings on a surface.
   * - ``WorkingUnit``
     - ``UL``
     - Working unit — labour-related traces or interventions.
   * - ``SeriesOfStratigraphicUnit``
     - ``serSU``
     - Series of Stratigraphic Units.
   * - ``SeriesOfDocumentaryStratigraphicUnit``
     - ``serUSD``
     - Series of Documentary Stratigraphic Units.
   * - ``SeriesOfStructuralVirtualStratigraphicUnit``
     - ``serUSVs``
     - Series of Structural Virtual units.
   * - ``SeriesOfNonStructuralVirtualStratigraphicUnit``
     - ``serUSVn``
     - Series of non-structural Virtual units.
   * - ``SeriesOfVirtualSpecialFindUnit``
     - ``serVSF``
     - Series of Virtual Special Finds: one equal object repeated (not pieces all different).
   * - ``ContinuityNode``
     - ``BR``
     - End-of-life ("continuity"/break) marker for a US/USV.
   * - ``StratigraphicEventNode``
     - ``SE``
     - The process/event that formed or altered a unit.
   * - ``UnknownNode``
     - ``unknown``
     - Fallback for unrecognised types.
   * - ``ParadataNode``
     - ``ParadataNode``
     - Abstract base for interpretation/provenance nodes.
   * - ``PropertyNode``
     - ``property``
     - A qualia/attribute (``value``, ``property_type``, ``units``).
   * - ``DocumentNode``
     - ``document``
     - A source document (role / content_nature / geometry axes).
   * - ``ExtractorNode``
     - ``extractor``
     - An extraction of information from a single source.
   * - ``CombinerNode``
     - ``combiner``
     - A reasoning that combines several sources.
   * - ``GroupNode``
     - ``Group``
     - Abstract base for grouping nodes.
   * - ``ActivityNodeGroup``
     - ``ActivityNodeGroup``
     - Logical grouping of related actions/activities.
   * - ``ParadataNodeGroup``
     - ``ParadataNodeGroup``
     - Container for a unit's paradata (``[US]_PD``).
   * - ``TimeBranchNodeGroup``
     - ``TimeBranchNodeGroup``
     - Alternative temporal interpretation branch.
   * - ``LocationNodeGroup``
     - ``LocationNodeGroup``
     - Spatial/locational membership plane (``kind``: toponym/study/functional).
   * - ``EpochNode``
     - ``EpochNode``
     - A chronological period (``start_time`` / ``end_time`` / ``color``).
   * - ``AuthorNode``
     - ``author``
     - Human creator/contributor.
   * - ``AuthorAINode``
     - ``author_ai``
     - AI-assisted creator (``model`` / ``prompt_reference``).
   * - ``GeoPositionNode``
     - ``geo_position``
     - Identitary geographic position (``epsg`` + shifts).
   * - ``ResourceNode``
     - ``resource``
     - The resource-layer hinge to an external file or URL (auto-typed by
       extension). Named ``LinkNode`` before 1.6.
   * - ``LicenseNode``
     - ``license``
     - Licence metadata.
   * - ``EmbargoNode``
     - ``embargo``
     - Time-bound access restriction.
   * - ``GraphNode``
     - ``graph``
     - Represents the graph itself (for graph-level authorship/licence).
   * - ``HDTNode``
     - ``hdt``
     - Heritage Digital Twin (HDT-O ``HC2``) aggregation node.
   * - ``SemanticShapeNode``
     - ``semantic_shape``
     - 3D geometry (convex hulls / spheres, or a ``.glb`` in ``url``). Since
       1.6.3 it is the **payload** of a ``geometry`` property, not a standalone
       proxy — see :ref:`proxy-as-property` below.
   * - ``AnnotationRegionNode``
     - ``annotation_region``
     - A region of ONE image, in normalised [0,1] coordinates: the geometry of a
       2D annotation.
   * - ``RepresentationModelNode``
     - ``representation_model``
     - 3D model / spatialised image for stratigraphic units.
   * - ``RepresentationModelDocNode``
     - ``representation_model_doc``
     - 3D model / spatialised image for documents & extractors.
   * - ``RepresentationModelSpecialFindNode``
     - ``representation_model_sf``
     - 3D model for special finds (anastylosis hypotheses).

Stratigraphic nodes
-------------------

The stratigraphic family carries the ``symbol`` / ``label`` /
``detailed_description`` class attributes used by the visual layer and
the JSON/GraphML exporters.

.. automodule:: s3dgraphy.nodes.stratigraphic_node
   :members:
   :undoc-members:
   :show-inheritance:

Epoch nodes
-----------

.. automodule:: s3dgraphy.nodes.epoch_node
   :members:
   :undoc-members:
   :show-inheritance:

Paradata nodes
--------------

The paradata family encodes the *interpretation chain*: a
:class:`PropertyNode` (a claim) is justified by an
:class:`ExtractorNode` (extraction from one source) or a
:class:`CombinerNode` (a reasoning over several sources), which in turn
references :class:`DocumentNode` sources.

.. automodule:: s3dgraphy.nodes.paradata_node
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: s3dgraphy.nodes.property_node
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: s3dgraphy.nodes.document_node
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: s3dgraphy.nodes.extractor_node
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: s3dgraphy.nodes.combiner_node
   :members:
   :undoc-members:
   :show-inheritance:

Grouping nodes
--------------

Group nodes organise other nodes along orthogonal planes: by activity,
by paradata container, by alternative time branch, or by spatial
location. In GraphML they are rendered as yEd group folders.

.. automodule:: s3dgraphy.nodes.group_node
   :members:
   :undoc-members:
   :show-inheritance:

Authorship nodes
----------------

.. automodule:: s3dgraphy.nodes.author_node
   :members:
   :undoc-members:
   :show-inheritance:

Representation & geometry nodes
-------------------------------

These nodes attach 3D geometry and spatial information to any node. A
:class:`GeoPositionNode` is *identitary* (where the object is on Earth)
and is distinct from the *geometric* representation models.

.. automodule:: s3dgraphy.nodes.representation_node
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: s3dgraphy.nodes.semantic_shape_node
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: s3dgraphy.nodes.geo_position_node
   :members:
   :undoc-members:
   :show-inheritance:

Reference, rights & link nodes
------------------------------

.. automodule:: s3dgraphy.nodes.resource_node
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: s3dgraphy.nodes.license_node
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: s3dgraphy.nodes.embargo_node
   :members:
   :undoc-members:
   :show-inheritance:

Graph & Heritage Digital Twin nodes
-----------------------------------

.. automodule:: s3dgraphy.nodes.graph_node
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: s3dgraphy.nodes.hdt_node
   :members:
   :undoc-members:
   :show-inheritance:

.. _proxy-as-property:

Geometry: the proxy is a property, the shape is its payload
-----------------------------------------------------------

**Introduced at nodes datamodel 1.6.3 · connections 1.6.10.** These are the
versions in which the change below landed, not the current ones: for the
declared coherence horizon see :doc:`../generated-report`.

A *proxy* is the geometry-without-material of a unit: the shape US101 has,
without asserting what it is made of. Until 1.6.3 it was a
``SemanticShapeNode`` hanging off the unit on its own — and a lone node cannot
say where it came from. "The proxy of US101" could not be traced to a
measurement, a photograph or a reprojection, because it had no paradata chain to
be traced through.

The proxy is now a ``PropertyNode`` whose ``property_type`` is ``geometry``, and
the SemanticShape is what that property points at::

    US ──has_property──▶ Property(geometry) ──has_semantic_shape──▶ SemanticShape
                              ▲                                    (hulls | spheres | .glb)
                              │ has_data_provenance
                        Extractor(s) ──combines──◀── Combiner

Two things follow, and both are the point: the proxy inherits the chain every
other quale has, so it can say *how* it is known; and ONE proxy can be
synthesised from SEVERAL sources — a photogrammetric mesh and a 1931 photograph —
instead of one node per source with nothing to join them.

``SemanticShapeNode`` itself did not change: same fields, same CIDOC mapping.
What changed is **who points at it**. Its ``type='proxy'`` option now names the
ROLE OF THE CARRIER ("this shape is the geometry of something"), not a standalone
proxy node.

.. warning::

   This is a **breaking change** for readers that expect a lone
   ``SemanticShapeNode`` attached to the unit (EM-blender-tools, Heriverse). See
   ``docs/deprecations.md`` for the migration.

Building one::

    from s3dgraphy import api

    api.create_geometry_proxy(
        graph, "US101",
        {"convexshapes": [[0, 0, 0, 1, 0, 0, 1, 1, 0]]},   # or {"url": "US101.glb"}
        extractor_sources=["D1", region_id],               # a document, a 2D region
    )

With one source the call creates one extractor and no combiner — an inference
node between a single extractor and a property would assert a reasoning step
nobody performed. With several, a ``CombinerNode`` joins them and the property
hangs off it, because the property is the *conclusion* of the chain.

2D annotation
-------------

``AnnotationRegionNode`` is a region of ONE image — or of one page of a
multi-page resource — in NORMALISED [0,1] coordinates. It is an
``E36_Visual_Item`` (a region of a visual item is a visual item), attached to its
image with ``is_on_resource`` (P106i) and cited by a property with
``has_visual_reference`` (P138i).

It is **interpretation, not raw evidence**: tracing "this and not that" is
already interpreting, so a region never appears bare — it is created inside a
chain, by ``api.create_annotation_paradata``.

Do NOT confuse it with ``SemanticShapeNode``: that one is 3D geometry of the
SCENE (``crmgeo:SP5``, expressing *where* a thing is), while a region makes no
claim about where anything is — it says *which part of which picture* was looked
at. They are separate classes because they answer different questions in
different coordinate systems; one field set with a kind flag would force every
reader to work out which meaning it was holding before it could use the numbers.

Coordinates are normalised because a pixel region is only readable next to the
resolution it was drawn at, and the same photograph is routinely re-exported at
another size; normalised coordinates are a statement about the picture rather
than about a file, and they express directly as a W3C Media Fragment (the
selector the RDF projection emits, ``em:hasSelector``).

.. automodule:: s3dgraphy.nodes.annotation_region_node
   :members:
   :undoc-members:
   :show-inheritance:

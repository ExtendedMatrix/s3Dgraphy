Unified XLSX Importer
=====================

.. versionadded:: 1.5.0

The :class:`~s3dgraphy.importer.unified_xlsx_importer.UnifiedXLSXImporter`
reads a single ``em_data.xlsx`` workbook produced by *StratiMiner* (or
hand-authored against the shipped template at
``s3dgraphy/templates/em_data_template.xlsx``) and builds a complete
s3dgraphy :class:`~s3dgraphy.graph.Graph` in memory: stratigraphic units,
epochs, qualia, relations, and the full paradata chain
(``PropertyNode → ExtractorNode → DocumentNode``, with ``AuthorNode`` /
``AuthorAINode`` attached to the extractor or directly to the
``PropertyNode``).

It is the **default workflow for s3dgraphy 1.5** and supersedes the
legacy two-file pipeline
(:class:`MappedXLSXImporter` + :class:`QualiaImporter`). Use the unified
importer for any new project.

.. seealso::

   - :doc:`/exporters/unified_xlsx_exporter` for the inverse round-trip.
   - :doc:`mapping_schema` for the **other** XLSX/SQLite import path:
     :class:`MappedXLSXImporter` / :class:`PyArchInitImporter` and the
     JSON mapping schema (``column_mappings``, ``table_settings``,
     ``relations``, and the 1.6 ``is_filter`` flags). The Unified
     importer is schema-less; it reads its own fixed 5-sheet layout
     and is **not** driven by a mapping JSON.

The 5-sheet canonical schema
----------------------------

``em_data.xlsx`` ships **five typed sheets**. The importer fails fast if
any is missing.

Units
~~~~~

Stratigraphic-unit declarations — *the skeleton*.

==========  =======================================================
Column      Meaning
==========  =======================================================
``ID``      Unit identifier (e.g. ``US001``, ``USV014``). Used as
            ``edge_source`` / ``edge_target`` in Claims rows.
``TYPE``    Stratigraphic abbreviation (``US``, ``USVs``, ``USVn``,
            ``SF``, ``VSF``, ``USD``, ``TSU``, ``RSF``, ``USN``,
            ``UL``, ``serSU``, ``serUSD``, ``serUSVn``,
            ``serUSVs``). Mapped via
            :data:`s3dgraphy.utils.utils.STRATIGRAPHIC_CLASS_MAP`.
``NAME``    Free-text label rendered in graph editors.
==========  =======================================================

.. admonition:: Aliases

   The importer normalises common AI-agent drift on load:
   ``UNIT_ID`` / ``UNITS_ID`` → ``ID``; ``UNIT_TYPE`` → ``TYPE``.

Epochs
~~~~~~

Swimlane / chronology declarations.

==========  =================================================
Column      Meaning
==========  =================================================
``ID``      Epoch identifier (e.g. ``EP_ROMAN``,
            ``EP_MEDIEVAL``). Referenced from Claims rows.
``NAME``    Display label.
``START``   Earliest TPQ (signed integer year — ``-44`` for
            44 BCE). Optional.
``END``     Latest TAQ (signed integer year). Optional.
``COLOR``   Hex colour for yEd swimlane rendering. Optional.
``PARENT``  ``ID`` of the epoch this one falls within.
            Optional (aliases ``PARENT_ID``, ``PARENT_EPOCH``).
==========  =================================================

**Sub-epochs.** A row with ``PARENT`` becomes ``has_sub_epoch`` PARENT →
epoch (the Marcomannic Wars, 166–180, inside the 2nd century AD,
101–200). The nesting is an assertion of the table and is **never
inferred** from ``START``/``END``: the same two rows without ``PARENT``
stay two top-level epochs. A ``PARENT`` that is not an ``ID`` of the
sheet, the epoch itself, or a loop of parents is a warning and no edge.
A parent may be declared on a later row than its child.

Claims
~~~~~~

The heart of the workbook: **one row per asserted fact**. Each row
declares (a) a *claim target* (a unit, possibly with a secondary target
for relational claims), (b) the *property/relation type*, (c) the
*value*, and (d) up to **two attribution triples**
(``EXTRACTOR_i`` / ``SOURCE_i`` / ``AUTHOR_i`` / ``AUTHOR_KIND_i``).

============================  ======================================
Column                         Meaning
============================  ======================================
``TARGET_ID``                  Unit (or epoch) the claim is about.
``TARGET2_ID``                 Secondary target for relational
                               claims (e.g. *X is_after Y*).
``PROPERTY_TYPE``              Semantic class of the claim
                               (see *Dispatch* below).
``VALUE``                      Claim payload (string or numeric).
``UNITS``                      Unit of measure for numeric qualia
                               (``cm``, ``m``, …). Optional.
``COMBINER_REASONING``         Free-text justification for
                               multi-source (Combiner) claims.
                               Triggers Combiner insertion when
                               both extractor slots are populated.
``EXTRACTOR_1`` /              Free text describing what the AI
``EXTRACTOR_2``                extractor (or human reasoning step)
                               concluded from the source document.
``SOURCE_1`` /                 What the extractor read: a
``SOURCE_2``                   Documents ID (e.g. ``D.01``) or
                               a Units ID (e.g. ``US5``). The
                               importer resolves the kind from
                               the id, a document first. The
                               extractor is named
                               ``<source>.<nn>`` either way.
                               ``DOCUMENT_1`` / ``DOCUMENT_2``
                               is the older name of the same
                               column, still read as
                               ``SOURCE_i``; the exporter
                               writes ``SOURCE_i``.
``AUTHOR_1`` /                 Authors catalog ID
``AUTHOR_2``                   (e.g. ``A.01`` or ``AI.01``).
``AUTHOR_KIND_1`` /            ``"author"`` (transcribed from the
``AUTHOR_KIND_2``              document author — the claim is
                               already in the source) **or**
                               ``"extractor"`` (newly derived by an
                               AI tool — the claim is new).
============================  ======================================

An id in ``SOURCE_i`` that is neither a Documents ID nor a Units ID is
a warning, and the extractor stays without its source. An annotation
region is a legitimate source in the graph, but no sheet of the
workbook declares one, so its id cannot resolve from a workbook alone.

Dispatch
~~~~~~~~

The importer dispatches a Claims row by the semantic class of
``PROPERTY_TYPE``:

- **Scalar qualia** (``definition``, ``material_type``, ``length``,
  ``width``, ``height``, ``shape``, ``conservation_state``,
  ``comparanda``, ``interpretation``, …) — create a
  :class:`PropertyNode` attached to ``TARGET_ID`` via ``has_property``.
  ``VALUE`` is the claim content.

- **Temporal qualia** (``absolute_time_start``, ``absolute_time_end``)
  — same as scalar but the PropertyNode's ``property_type`` is set so
  the DP-32 resolver and A.1 compaction pick it up. See
  :doc:`/internals/temporal`.

  When ``TARGET_ID`` is an **epoch**, the property is the epoch's own,
  attached directly — ``EpochNode —has_property→ PropertyNode`` with the
  same extractor / document / author / combiner chain as a unit's
  claim (connections datamodel 1.6.21). The importer creates **no**
  ParadataNodeGroup: a group is a grouping a consumer may add later, not
  a passage (see the coherence rule in :func:`s3dgraphy.api.validate`).
  Before 1.6.21 these edges degraded to ``generic_connection``.

- **Epoch membership** (``has_first_epoch`` / ``belongs_to_epoch``) —
  create a ``has_first_epoch`` edge from ``TARGET_ID`` (unit) to the
  Epochs row identified by ``VALUE`` or ``TARGET2_ID``. The deprecated
  alias ``belongs_to_epoch`` is accepted for backward compat with
  prompt versions ≤ v5.2.

- **Stratigraphic relation** (``is_after``, ``overlies``, ``cuts``,
  ``fills``, ``abuts``, ``bonded_to``, ``equals``, ``has_same_time``,
  ``contrasts_with``, ``changed_from``, plus their reverses) — create
  a directed edge from ``TARGET_ID`` to ``TARGET2_ID`` with that
  ``edge_type``. The attribution chain hangs off the edge's
  ``attributes`` dict (``authored_by_id``, ``authored_by_kind``,
  ``document_id``) rather than creating PropertyNodes — edges are
  the natural subject of a relational claim's attribution.

Authors
~~~~~~~

Normalized catalog of claim authors.

================  =====================================
Column            Meaning
================  =====================================
``ID``            Short code (``A.01``, ``AI.01``).
``KIND``          ``"human"`` → :class:`AuthorNode`;
                  ``"ai"`` → :class:`AuthorAINode`.
``DISPLAY_NAME``  Human label.
``ORCID``         ORCID identifier (optional).
``AFFILIATION``   Institution (optional).
================  =====================================

The Authors catalog feeds the ``has_author`` resolution: per-claim
attribution triples reference rows by ``ID``; the importer reuses one
``AuthorNode`` per ID, avoiding catalog duplication.

Documents
~~~~~~~~~

Normalized catalog of source PDFs / reports.

================  =====================================
Column            Meaning
================  =====================================
``ID``            Short code (``D.01``).
``FILENAME``      On-disk filename.
``TITLE``         Document title.
``YEAR``          Year of publication.
``AUTHOR_IDS``    Comma-separated list of ``Authors.ID``
                  values (semantic only, no FK).
================  =====================================

Three-axis document classification (``ROLE`` / ``CONTENT_NATURE`` /
``GEOMETRY``) is accepted on input under the 1.6 nomenclature but is
*not* required by the 1.5 importer.

Combiner row pattern
--------------------

When **both** ``EXTRACTOR_1`` / ``EXTRACTOR_2`` and
``COMBINER_REASONING`` are populated, the importer inserts a
:class:`CombinerNode` between the ``PropertyNode`` and the two
:class:`ExtractorNode` instances::

    PropertyNode  --has_data_provenance-->  CombinerNode
                                                |
                              combines / combines
                                                |
                              ExtractorNode_1, ExtractorNode_2

This is the canonical pattern for *Combiner-mediated synthesis* (one
qualia value supported by two independent extractions). The
``COMBINER_REASONING`` text is stored on
:attr:`CombinerNode.description`.

Workflow
--------

.. code-block:: python

   from s3dgraphy.importer.unified_xlsx_importer import UnifiedXLSXImporter

   importer = UnifiedXLSXImporter(
       "em_data.xlsx",
       graph_id="great_temple",
   )
   graph = importer.parse()

   print(f"Loaded {len(graph.nodes)} nodes, {len(graph.edges)} edges")
   print("Per-sheet stats:", importer.stats)
   for w in graph.warnings:
       print(f"  ! {w}")

Public attributes after :meth:`parse`:

- ``importer.graph`` — populated :class:`Graph` (also the return value).
- ``importer.warnings`` — non-fatal issues (unknown references, duplicate
  declarations, …). Mirrored into ``graph.warnings`` for downstream
  consumers.
- ``importer.stats`` — per-sheet row counts plus ``nodes_total`` /
  ``edges_total``.

Mapping registry interaction
----------------------------

Unlike :class:`MappedXLSXImporter`, the unified importer is **schema-fixed**
— it does *not* consult ``mapping_registry``. The 5-sheet schema is
the mapping. Use :class:`MappedXLSXImporter` only for legacy free-form
spreadsheets that pre-date the unified workbook; new projects should
emit ``em_data.xlsx`` directly.

API Reference
-------------

.. automodule:: s3dgraphy.importer.unified_xlsx_importer
   :members:
   :undoc-members:
   :show-inheritance:

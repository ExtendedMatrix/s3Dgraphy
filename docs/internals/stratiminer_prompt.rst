StratiMiner Extraction Prompt
=============================

.. versionadded:: 1.5.0

s3dgraphy ships a frozen copy of the **StratiMiner AI extraction
prompt** inside the wheel at
``s3dgraphy/data/StratiMiner_Extraction_Prompt.md`` (761 lines as of
1.5.1). The prompt is the operational spec that LLM-driven extractors
(Claude, GPT, Gemini, …) follow to convert a free-form
archaeological PDF into a complete ``em_data.xlsx`` workbook with the
5-sheet canonical schema described in
:doc:`/importers/unified_xlsx_importer`.

This page explains **why the prompt ships in the wheel**, **how
code reaches it**, and **how a user / tool runs it**.

Why ship the prompt inside the package?
---------------------------------------

The unified-xlsx pipeline (DP-02 / DP-49) gives s3dgraphy two
inputs for the same data:

#. A *human* author hand-fills ``em_data.xlsx`` from the template
   in ``templates/em_data_template.xlsx``.
#. An *AI* extractor (StratiMiner) reads a PDF and emits the same
   ``em_data.xlsx``, structurally compatible with the importer.

Shipping the prompt **with the library** keeps the two inputs in
*lock-step*: when the importer schema changes (a new column, a new
``PROPERTY_TYPE``, a new ``AUTHOR_KIND``), the prompt that the AI
extractor sees moves with it. There is no out-of-band synchronisation
between the library version and the extractor instructions.

This is the same rationale as bundling the GraphML palette template
(``templates/em_palette_template.graphml``) in the wheel.

Wheel location
--------------

The prompt lives under the data resources directory::

   src/s3dgraphy/data/StratiMiner_Extraction_Prompt.md

It is declared in ``pyproject.toml`` (``package-data``) and verified
present in ``SOURCES.txt``. The legacy filename
``AI_EXTRACTION_PROMPT_v4.md`` is kept as an importable alias for
backward compatibility (consumers that pinned the old name keep
working through the file lookup in :mod:`s3dgraphy.utils.utils`).

Programmatic access
-------------------

s3dgraphy exposes the prompt via :func:`get_ai_prompt` from
:mod:`s3dgraphy.utils`::

    from s3dgraphy import get_ai_prompt
    prompt = get_ai_prompt(language="EN")

The helper:

#. Resolves the file inside the package data directory via
   :mod:`importlib.resources`.
#. Substitutes the ``[OUTPUT_LANGUAGE]`` placeholder at the top of
   the prompt with the language code passed in (``EN``, ``IT``, …).
#. Returns the full prompt body as a string.

The substituted prompt is what the user feeds into the LLM along
with the source PDF. The LLM produces an ``em_data.xlsx`` that
:class:`UnifiedXLSXImporter` reads directly.

How users / tools run it
------------------------

End-to-end loop:

#. Pick an archaeological PDF (excavation report, monograph, …).
#. Get the prompt: ``prompt = get_ai_prompt(language="EN")``.
#. In a Claude / GPT / Gemini chat, paste the prompt as the system
   message, attach the PDF.
#. The LLM emits ``em_data.xlsx`` as a downloadable artefact
   (Claude side) or as base64 / structured output (API side).
#. Save the xlsx locally and import::

       from s3dgraphy.importer.unified_xlsx_importer import UnifiedXLSXImporter
       graph = UnifiedXLSXImporter("em_data.xlsx").parse()

Round-trip with the exporter::

       from s3dgraphy.exporter.unified_xlsx_exporter import UnifiedXLSXExporter
       UnifiedXLSXExporter(graph).export("em_data.roundtrip.xlsx")

   The re-emitted xlsx is structurally identical (up to the canonical
   direction normalisation described in
   :doc:`/exporters/unified_xlsx_exporter`).

Prompt contract highlights
--------------------------

.. note::
   The prompt was at **v5.4** in s3dgraphy 1.5.1 when this page was
   written. On the 1.6dev branch the bundled prompt may have been
   bumped; inspect the current version by running
   ``s3dgraphy.get_ai_prompt()`` (or reading the header of
   ``src/s3dgraphy/data/StratiMiner_Extraction_Prompt.md``). The
   contract described below documents the v5.4 baseline.

The contract the prompt imposes on the LLM:

**Schema fixed**
    The output workbook has exactly 5 sheets:
    ``Units``, ``Epochs``, ``Claims``, ``Authors``, ``Documents``.
    Column names are fixed (no drift); the importer accepts a small
    set of aliases for AI-induced renames (see
    :doc:`/importers/unified_xlsx_importer`).

**Per-claim attribution**
    Every ``Claims`` row carries up to two attribution triples
    ``(EXTRACTOR_i, SOURCE_i, AUTHOR_i, AUTHOR_KIND_i)``.
    ``AUTHOR_KIND_i`` is one of:

    - ``"author"`` — the claim is *transcribed* from the document
      author (the claim already exists in the source).
    - ``"extractor"`` — the claim is *newly derived* by the AI
      (StratiMiner inferred it from raw text or images).

    This distinction lets diagnostics
    (:func:`attribute_temporal_claim`) tell a curator whether to
    audit the document or the extractor when a paradox surfaces.

**Combiner rows**
    When both ``EXTRACTOR_1`` and ``EXTRACTOR_2`` are populated AND
    ``COMBINER_REASONING`` is non-empty, the importer inserts a
    :class:`CombinerNode` between the PropertyNode and the two
    ExtractorNode instances. The reasoning text is preserved
    verbatim on :attr:`CombinerNode.description`.

**Stratigraphy-only mode**
    The prompt also documents a *legacy* mode for archaeological
    databases that do not yet carry paradata attribution: the curator
    is the sole author, no extractor chain. Useful for migrating
    pre-DP-02 datasets.

**Controlled vocabularies**
    ``PROPERTY_TYPE`` and ``AUTHOR_KIND`` stay in **English** even
    when the workbook output language is something else — they are
    controlled vocabularies that the importer matches case-sensitively.
    Localisation applies only to free-text fields (``VALUE``,
    ``DISPLAY_NAME``, document titles, ``COMBINER_REASONING``,
    ``EXTRACTOR_i`` verbatim excerpts).

Validation
----------

The prompt ships **with** a validation procedure that the LLM is
asked to run before returning the xlsx:

- Cross-sheet referential integrity (every ``Author_ID`` /
  ``Document_ID`` / epoch id referenced in ``Claims`` exists in the
  matching catalog sheet).
- Duplicate-triple detection.
- ``COMBINER_REASONING`` non-empty when two extractors are populated.
- Stratigraphic cycle detection.

These checks mirror the post-import diagnostics in
:mod:`s3dgraphy.diagnostics` — catching errors at extraction time is
cheaper than fixing them after the importer warns.

Updating the prompt
-------------------

When the importer schema evolves:

#. Edit ``src/s3dgraphy/data/StratiMiner_Extraction_Prompt.md`` (bump
   the version header at the top).
#. Update the importer in
   ``src/s3dgraphy/importer/unified_xlsx_importer.py`` to recognise
   the new columns / vocabulary, ideally keeping a backward-compatible
   alias.
#. Bump the s3dgraphy package version
   (``pyproject.toml`` + ``src/s3dgraphy/__init__.py``).
#. Run the test suite — ``tests/test_unified_xlsx_importer.py``
   exercises the schema contract.
#. Add a changelog entry.

The prompt is **not** a separate semver track — it inherits the
package version. Consumers that pin the package automatically pin
the prompt.

See also
--------

- :doc:`/importers/unified_xlsx_importer` — the schema the prompt
  produces.
- :doc:`/exporters/unified_xlsx_exporter` — round-trip back to xlsx.
- :doc:`/api/diagnostics` — the runtime checks that mirror the
  prompt's pre-emit validation.

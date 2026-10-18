.. _development:

Development and contribution
============================

This page describes how s3dgraphy is tested and what state that testing is
actually in. It is level two of the two-level account of quality begun in
:doc:`data-quality`: not *is this graph sound*, but *do the checks that answer
that question still work*.

It describes the real state, including the parts that are not what they should
be. A documentation page that describes the intended arrangement rather than the
existing one is itself a defect, and a more expensive one than the arrangement it
misdescribes.

.. contents::
   :local:
   :depth: 2


.. _development-ci:

What continuous integration runs today: nothing
-----------------------------------------------

.. warning::

   **There is no automated test run.** The repository contains two GitHub
   Actions workflows. Only one is active, and it does not run tests.

   * ``.github/workflows/publish.yml`` — **active**. Manual dispatch only
     (``workflow_dispatch``), publishes a named tag to TestPyPI or PyPI. It
     builds the package and runs ``twine check``; it does not run ``pytest``.
   * ``.github/workflows/test.yml.disabled`` — **disabled**, by the ``.disabled``
     suffix. It was renamed by commit ``99c5ea9`` on **11 September 2025**, with
     the message *"Temporarily disable test workflow (no tests yet)"*.

   **That reason is no longer true.** The repository now contains 155 test
   modules and roughly 1,890 collected tests. The workflow has been disabled for
   a year against a justification that expired.

The disabled workflow, if re-enabled unchanged, would run ``pytest --cov`` across
a matrix of three operating systems (Ubuntu, Windows, macOS) and five Python
versions (3.8 through 3.12), followed by a package-build job. Two things would
have to be fixed first, and they are named here so that re-enabling is a decision
and not a surprise:

#. **The matrix includes Python 3.8**, which ``pyproject.toml`` excludes
   (``requires-python = ">=3.9"``). That leg would fail on install.
#. **The suite is not green** (see below). Turning the workflow on as-is turns
   every push red, which teaches everyone to ignore it.

A third item, smaller but in the same family: the script that verifies every
CIDOC-family IRI the datamodels cite against the official ontology releases lives
at ``.claude/wip/verify_cidoc_iris.py`` and is run by hand. It is described in
project notes as a permanent check; it is not wired to the suite or to any
workflow. See :doc:`mapping-update-procedure`, step 4.


The regression suite
--------------------

What it is
~~~~~~~~~~

.. list-table::
   :header-rows: 0
   :widths: 40 60

   * - Location
     - ``tests/`` (89 modules) and ``tests/sync/`` (66 modules)
   * - Total
     - **155 test modules**
   * - Configuration
     - ``[tool.pytest.ini_options]`` in ``pyproject.toml``:
       ``testpaths = ["tests"]``, ``python_files = ["test_*.py"]``
   * - Runner
     - ``pytest`` (declared ``>=7.0`` in the ``dev`` extra)

The suite is not a smoke test. It covers the RDF round trip, the reverse-edge
directions, the connection resolver, the mapping authoring surface, the em.json
round trip and its schema version, the DTC projection and corpus, the HDT-O
projection, the CRDT layer, the shelf, the narrative subsystem, the importers
(GraphML, XLSX, CSV, FileMaker XML, pyArchInit over SQLite and PostgreSQL), the
exporters, and the two drift guards.

Three of the modules deserve naming because they are structural guards rather
than feature tests:

``tests/test_node_datamodel_registry.py``
   Runs ``sync_node_datamodel --check``, so the generated node registry can never
   drift from the Python classes.

``tests/test_wheel_drift.py``
   Compares, **by content**, the s3dgraphy bundled into a consumer against this
   checkout. A version string is a claim and a claim can be false: on one
   occasion a bundled copy was days out of date while declaring an identical
   version, and the version-based check passed the whole time — it was comparing
   two identical strings.

``tests/test_consumer_drift.py``
   Reports which consumers are behind on the connections datamodel, failing only
   for consumers this project owns.

Running it locally
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   git clone https://github.com/ExtendedMatrix/s3Dgraphy.git
   cd s3dgraphy
   python -m venv .venv && source .venv/bin/activate

   pip install -e ".[dev]"          # pytest, coverage, linters
   pip install -e ".[rdf,sync]"     # what the suite needs to COLLECT

   pytest -q

The second install line is not optional, and the failure it prevents is not
obvious. Several subsystems import optional third-party libraries at module
level and raise a guided ``ImportError`` when they are missing. Without
``sqlalchemy``, the 35 modules under ``tests/sync/`` fail at **collection**, and
pytest aborts the whole run before executing a single test — so the suite appears
catastrophically broken when it is merely under-provisioned.

Useful subsets:

.. code-block:: bash

   pytest -q tests/test_rdf_roundtrip.py      # one module
   pytest -q tests/sync                       # the pyArchInit bridge
   pytest -q -k "mapping or connection"       # by name
   pytest --cov=s3dgraphy --cov-report=term   # with coverage

Other checks, all run by hand today:

.. code-block:: bash

   python -m s3dgraphy.tools.sync_node_datamodel --check   # registry vs classes
   python -m s3dgraphy.tools.consumer_drift --check        # consumers behind
   python -m s3dgraphy.tools.wheel_drift --check           # bundled wheel stale
   python .claude/wip/verify_cidoc_iris.py .               # every IRI exists
   black --check src/ && flake8 src/                       # style

Its current state, measured
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Measured on the working tree, 21 September 2026, Python 3.10.12 on Linux, with
the base package plus the ``rdf`` extra and ``sqlalchemy`` installed:

.. code-block:: text

   1800 passed, 28 failed, 63 skipped, 728 warnings in 17.40s

**The suite is not green, and the 28 failures are a known standing baseline
rather than a fresh breakage.** They were counted before and after the September
2026 CIDOC repair pass and were the same set both times, verified by comparing
the two lists. They concentrate almost entirely in one area:

.. list-table::
   :header-rows: 1
   :widths: 60 12 28

   * - Module
     - Failures
     - Area
   * - ``tests/sync/test_groups_export_em_template.py``
     - 10
     - yEd group export
   * - ``tests/sync/`` (nine further modules)
     - 12
     - pyArchInit bridge, projectors, round trips
   * - ``tests/test_lossless_roundtrip.py``
     - 2
     - XLSX → graph → GraphML round trip
   * - ``tests/test_narrative_node.py``, ``tests/test_narrative_authorship.py``
     - 2
     - fixture re-export identity
   * - ``tests/test_wheel_drift.py``
     - 1
     - stale bundled wheel (environmental)

Twenty-two of the twenty-eight are under ``tests/sync/``. Reducing that baseline
to zero is the precondition for re-enabling the test workflow; until then, the
honest statement is that the suite is a **regression detector run by hand
against a known baseline**, not a gate.

The 63 skips are mostly environmental — a PostgreSQL server, an S3 endpoint or
an optional library not present — and are expected in a default checkout.


.. _development-supported-versions:

Supported versions
------------------

This is the table step 8 of :doc:`mapping-update-procedure` requires to be
updated whenever a reference version moves.

Runtime and toolchain
~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 26 44

   * - Item
     - Declared
     - Verified
   * - Python
     - ``>=3.9``; classifiers list 3.9, 3.10, 3.11, 3.12
     - **3.10 only.** No automated multi-version run exists (see
       :ref:`development-ci`), so 3.9, 3.11 and 3.12 are declared support, not
       measured support.
   * - Operating systems
     - "OS Independent" (classifier); the disabled matrix names Ubuntu, Windows
       and macOS
     - **Linux only.** Same reason.
   * - ``black`` target
     - ``py38``
     - Inconsistent with ``requires-python = ">=3.9"``; harmless, but it should
       be moved to ``py39``.
   * - License
     - GPL-3.0-or-later
     - —

Library, datamodels and ontologies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These are **not tabulated by hand anywhere in this documentation.** They are read
off the datamodels and the installed package and rendered by a generator — see
:doc:`generated-report` for the current library version, the three datamodel
versions, and the version of every CIDOC-family and external ontology in force.

Optional dependency groups
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Extra
     - What it enables
   * - ``rdf``
     - RDF export: Turtle, N-Triples, JSON-LD, TriG, RDF/XML
   * - ``sync``
     - The pyArchInit bridge over SQLite (**needed for the suite to collect**)
   * - ``postgres``
     - The PostgreSQL backend of the same bridge
   * - ``visualization``
     - Layout generation
   * - ``geo``
     - Coordinate handling and reprojection
   * - ``s3``
     - Object-store backend for the resource layer (``boto3``; any
       S3-compatible endpoint, RustFS in the dev stack)
   * - ``pdf`` / ``docx``
     - Reading PDF text layers; narrative export to Word
   * - ``dev``
     - pytest, coverage, black, flake8, mypy, build, twine, bump2version
   * - ``docs``
     - Sphinx, the RTD theme, MyST
   * - ``full`` / ``all``
     - Aggregates; ``all`` adds dev, docs and postgres


Building the documentation
--------------------------

.. code-block:: bash

   pip install -e ".[docs]"
   pip install -r docs/requirements.txt

   make html                  # → docs/_build/html
   make latexpdf              # → docs/_build/latex  (the format deposited for DOI)
   make check-docs            # -W: warnings become errors

The PDF build is not decorative: it is the format deposited in a repository and
cited by version DOI, so a change that breaks it breaks a citation path. It needs
a LaTeX toolchain (``texlive-latex-recommended``, ``texlive-latex-extra``,
``texlive-fonts-recommended``, ``latexmk``) which the HTML build does not.

Read the Docs builds from ``.readthedocs.yaml``: Ubuntu 22.04, Python 3.11,
``pip install .[docs]`` plus ``docs/requirements.txt``, HTML with PDF and EPUB as
additional formats, ``fail_on_warning: false``.

.. important::

   **Two constraints on this documentation, both about URLs.**

   Versioned builds are **not** enabled on Read the Docs and must not be enabled:
   help links inside already-distributed Blender add-ons point into this address
   space, and inserting a version segment breaks software that is already in
   people's hands.

   For the same reason, **pages are not moved or renamed.** If a page must be
   renamed, the old address keeps a redirect. New pages are free; moved ones are
   not.


Contributing a change
---------------------

#. Branch from the current development branch.
#. Make the change. If it touches the datamodels or the ontology alignment,
   follow :doc:`mapping-update-procedure` rather than this section.
#. Run ``pytest -q`` and compare the failure list against the baseline above. A
   contribution is accepted when it adds no *new* red; it is not required to fix
   the standing 28.
#. Run ``python -m s3dgraphy.tools.sync_node_datamodel --check`` if you touched a
   node class.
#. Run ``black --check src/`` and ``flake8 src/``.
#. Update the documentation in the same commit as the behaviour. Where a number
   is involved, prefer pointing at :doc:`generated-report` over writing the
   number down.
#. Open a pull request describing what was measured, not only what was intended.

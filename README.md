# s3dgraphy

[![PyPI version](https://badge.fury.io/py/s3dgraphy.svg)](https://badge.fury.io/py/s3dgraphy)
[![Python versions](https://img.shields.io/pypi/pyversions/s3dgraphy.svg)](https://pypi.org/project/s3dgraphy/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Downloads](https://pepy.tech/badge/s3dgraphy)](https://pepy.tech/project/s3dgraphy)
[![Publish to PyPI](https://github.com/ExtendedMatrix/s3Dgraphy/actions/workflows/publish.yml/badge.svg)](https://github.com/ExtendedMatrix/s3Dgraphy/actions/workflows/publish.yml)

<!-- documentation-map:start -->
## Where the documentation lives

Every tool of the two families keeps its manual beside its code, and publishes it at one of the two addresses below. A manual is changed in the repository of its own tool, never here.

| Tool | Code | Manual | Published at |
| --- | --- | --- | --- |
| **Extended Matrix** | | | |
| Extended Matrix (the language) | [`zalmoxes-laran/ExtendedMatrix`](https://github.com/zalmoxes-laran/ExtendedMatrix) | [`zalmoxes-laran/ExtendedMatrix-doc`](https://github.com/zalmoxes-laran/ExtendedMatrix-doc) | <https://docs.extendedmatrix.org/en/1.5/> |
| EMStudio (editor) | [`ExtendedMatrix/EMStudio`](https://github.com/ExtendedMatrix/EMStudio) | [`ExtendedMatrix/EMStudio-doc`](https://github.com/ExtendedMatrix/EMStudio-doc) | <https://docs.extendedmatrix.org/projects/emstudio-doc/en/1.6/> |
| EM Tools (Blender add-on) | [`zalmoxes-laran/EM-blender-tools`](https://github.com/zalmoxes-laran/EM-blender-tools) | [`zalmoxes-laran/EM-blender-tools-doc`](https://github.com/zalmoxes-laran/EM-blender-tools-doc) | <https://docs.extendedmatrix.org/projects/EM-tools/en/1.5/> |
| s3Dgraphy (library) | [`ExtendedMatrix/s3Dgraphy`](https://github.com/ExtendedMatrix/s3Dgraphy) | same repository, `docs/` | <https://docs.extendedmatrix.org/projects/s3dgraphy/en/v1.5/> |
| 3D Survey Collection | [`zalmoxes-laran/3D-survey-collection`](https://github.com/zalmoxes-laran/3D-survey-collection) | [`zalmoxes-laran/3D-survey-collection-doc`](https://github.com/zalmoxes-laran/3D-survey-collection-doc) | <https://docs.extendedmatrix.org/projects/3DSC/en/1.7.0/> |
| Heriverse (web runtime) | [`StratiGraph-ECCCH/Heriverse`](https://github.com/StratiGraph-ECCCH/Heriverse) | [`StratiGraph-ECCCH/Heriverse-doc`](https://github.com/StratiGraph-ECCCH/Heriverse-doc) | <https://docs.extendedmatrix.org/projects/heriverse/en/1.5/> |
| **StratiGraph** | | | |
| The node, and its catalogue | [`StratiGraph-ECCCH/stratigraph-server`](https://github.com/StratiGraph-ECCCH/stratigraph-server) | same repository, `docs/` | <https://docs.stratigraph-eccch.eu/projects/node/en/latest/> |
| StratiField (field assistant) | [`StratiGraph-ECCCH/stratigraph-stratifield`](https://github.com/StratiGraph-ECCCH/stratigraph-stratifield) | same repository, `docs/` | <https://docs.stratigraph-eccch.eu/projects/field/en/latest/> |
| Recording templates | [`StratiGraph-ECCCH/stratigraph-templates`](https://github.com/StratiGraph-ECCCH/stratigraph-templates) | same repository, `docs/` | <https://docs.stratigraph-eccch.eu/projects/templates/en/v0.1.0/> |
| The welcome page of the manuals | — | [`StratiGraph-ECCCH/stratigraph-docs`](https://github.com/StratiGraph-ECCCH/stratigraph-docs) | <https://docs.stratigraph-eccch.eu> |
| The StratiGraph Academy | — | [`StratiGraph-ECCCH/stratigraph-academy`](https://github.com/StratiGraph-ECCCH/stratigraph-academy) | <https://academy.stratigraph-eccch.eu> |

<!-- documentation-map:end -->

## 3D Stratigraphic Graph Management Library

s3dgraphy is a Python library for creating and managing multitemporal, 3D knowledge graphs, with a focus on archaeological and heritage applications. It provides tools for stratigraphic data management, temporal modeling, and graph-based analysis of archaeological contexts.

Part of the [Extended Matrix Framework](https://www.extendedmatrix.org), s3dgraphy implements the formal language Extended Matrix (EM) for archaeological documentation and 3D reconstruction workflows.

## 🚀 Installation

```bash
# From PyPI (stable releases)
pip install s3dgraphy

# From TestPyPI (development versions)
pip install --index-url https://test.pypi.org/simple/ s3dgraphy

# With optional dependencies
pip install s3dgraphy[visualization]  # For plotting features
pip install s3dgraphy[full]          # All optional dependencies
```

## 🔧 Quick Start

```python
from s3dgraphy import Graph
from s3dgraphy.nodes import StratigraphicUnit, DocumentNode

# Create a new stratigraphic graph (graph_id is required)
graph = Graph("my_excavation")

# Build node objects, then add them with add_node()
wall = StratigraphicUnit("US001", name="US001", description="Stone wall foundation")
floor = StratigraphicUnit("US002", name="US002", description="Mosaic floor")
graph.add_node(wall)
graph.add_node(floor)

# Add a stratigraphic relationship.
# Canonical direction is recent -> ancient: the floor (US002) is more
# recent than the wall (US001), so US002 is_after US001.
graph.add_edge("e1", "US002", "US001", "is_after")

# Attach documentation
doc = DocumentNode("DOC001", name="DOC001", description="Field photo")
graph.add_node(doc)
graph.add_edge("e2", "US001", "DOC001", "has_documentation")

# Query the graph
print(f"Graph contains {len(graph.nodes)} nodes and {len(graph.edges)} edges")
us_units = graph.get_nodes_by_type("US")

# Export to GraphML (yEd round-trip) — the exporter takes the graph directly
from s3dgraphy.exporter.graphml import GraphMLExporter
GraphMLExporter(graph).export("my_excavation.graphml")
```

> **Note on the API.** Nodes are *objects* (`StratigraphicUnit`,
> `DocumentNode`, …) created first and then added with `graph.add_node()`.
> Edges are created with `graph.add_edge(edge_id, source_id, target_id,
> edge_type)` using a **canonical** edge type from the connections
> datamodel (e.g. `is_after`, `has_property`, `has_documentation`). Invalid
> connections are downgraded to `generic_connection` with a warning rather
> than silently accepted. See the
> [API reference](https://docs.extendedmatrix.org/projects/s3dgraphy/) for
> the full node and edge catalogs.

## 📚 Core Features

### 🏛️ Archaeological Stratigraphic Modeling
- **Stratigraphic Units (US)**: Physical layers and contexts
- **Stratigraphic Volumes (USV)**: 3D spatial representations
- **Surfaces (SF)**: Interface documentation
- **Temporal Relationships**: Before/after, contemporary, uncertain

### 🔗 Extended Matrix Integration
- **EM Language Support**: Full implementation of Extended Matrix formal language
- **Visual Rules**: JSON-based styling and visualization rules
- **CIDOC-CRM Mapping**: Semantic web compatibility
- **Connection Rules**: Automated relationship inference

### 📊 Graph Operations
- **Multitemporal Analysis**: Handle complex temporal sequences
- **Graph Traversal**: Navigate stratigraphic relationships
- **Filtering & Querying**: Find specific contexts and relationships
- **Validation**: Check stratigraphic consistency

### 💾 Data Exchange
- **GraphML Import/Export**: Industry standard graph format
- **JSON/YAML Support**: Lightweight data exchange
- **Excel Integration**: Tabular data import
- **3D Model Integration**: GLTF/GLB support for 3D contexts

## 🎯 Use Cases

### Archaeological Projects
- **Excavation Documentation**: Record stratigraphic sequences
- **Site Analysis**: Understand temporal relationships
- **3D Reconstruction**: Link physical evidence to 3D models
- **Publication**: Generate stratigraphic matrices and diagrams

### Heritage Applications
- **Monument Analysis**: Document construction phases
- **Conservation Planning**: Track intervention history
- **Virtual Archaeology**: Create interactive 3D experiences
- **Research Integration**: Connect archaeological data with other disciplines

## Mapping JSON files

The `src/s3dgraphy/mappings/` folder contains JSON templates that describe how
to import data from external tabular sources (SQLite tables from PyArchInit,
XLSX files from EMdb, generic CSVs, etc.) into an s3dgraphy graph.

Two template files live at the root of the folder for reference:

- `template_pyarchinit_mapping.json` — for SQLite-based tables (PyArchInit-style)
- `template_emdb_mapping.json` — for XLSX-based tables (EMdb-style)

These templates are NOT loaded automatically by `MappingRegistry`, which only
scans the `pyarchinit/`, `emdb/`, and `generic/` subdirectories. To use one as
a starting point, copy it to the appropriate subdirectory and adapt it to your
table structure.

The templates document the schema inline. In addition to `is_id`,
`is_description`, `is_attribute`, and `node_type`, 1.6 introduces two new
optional flags on each `column_mappings` entry:

- `is_filter` — marks the column as a candidate filter. Importers expose these
  via `get_filter_columns()` so a consumer application can present a dropdown
  before triggering the import.
- `filter_required` — when `true`, the consumer is expected to force the user
  to pick a value (no "All values" option). When `false`, the filter is
  optional.

Each importer (`PyArchInitImporter`, `MappedXLSXImporter`, `XLSXImporter`) now
accepts a `filters={col: value, ...}` kwarg with AND semantics, and exposes a
`get_distinct_values(col)` helper for populating the dropdown. The semantics
are deliberately library-side and make no assumption about who renders the
filter UI.

**Full schema reference:**
[Mapping JSON Schema Reference](https://docs.extendedmatrix.org/projects/s3dgraphy/en/latest/importers/mapping_schema.html)
documents every key (`table_settings`, `column_mappings`, `relations`) and the
1.6 filter flags in detail.

### Consumer-side quick start

```python
from s3dgraphy.importer.pyarchinit_importer import PyArchInitImporter

# 1) Probe the mapping: discover filter columns and their values.
probe = PyArchInitImporter(
    filepath="excavation.sqlite",
    mapping_name="pyarchinit_us_mapping",
)
for spec in probe.get_filter_columns():
    column = spec["column"]
    label = spec["display_name"]
    required = spec["filter_required"]
    values = probe.get_distinct_values(column)
    print(f"{label} ({'required' if required else 'optional'}): {values}")

# 2) Import only the subset the user picked.
importer = PyArchInitImporter(
    filepath="excavation.sqlite",
    mapping_name="pyarchinit_us_mapping",
    filters={"sito": "Pompei", "area": "A"},
)
graph = importer.parse()
```

`filters` defaults to `None` (no filtering), so all existing code continues
to work unchanged. Multiple entries are combined with logical AND; values
match exactly and case-sensitively. The same flow applies to
`MappedXLSXImporter` and `XLSXImporter` for XLSX sources.

## 📖 Documentation

- **[User Guide](https://docs.extendedmatrix.org/projects/s3dgraphy/)** - Complete documentation
- **[API Reference](https://docs.extendedmatrix.org/projects/s3dgraphy/api.html)** - Detailed API docs
- **[Examples](https://github.com/ExtendedMatrix/s3Dgraphy/tree/main/examples)** - Code examples and tutorials
- **[Extended Matrix](https://www.extendedmatrix.org)** - Framework overview

## Where this sits

s3Dgraphy is the **language** of the StratiGraph ecosystem, and its only
authority on meaning: it defines the `em.json` format, merges two versions of a
study, and produces every projection (RDF/CIDOC-CRM, GraphML, IIIF, the Heriverse
payload, LaTeX/DOCX). Everything else — the editor, the Blender addon, the
services — speaks through it and does not re-derive it.

The rule the other repos inherit, in one line: *if an endpoint needs to compute
something about a graph, that something belongs here.* This library has no web
framework and no socket on purpose — what it does can be proved on a table.

**The whole map:** [`ARCHITECTURE-SYSTEM.md`](../stratigraph-server/docs/ARCHITECTURE-SYSTEM.md).

---

## 🔧 Development

### Setting up Development Environment

```bash
git clone https://github.com/ExtendedMatrix/s3Dgraphy.git
cd s3dgraphy
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Run the tests — from the repo root, with `src/` on the path:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests -q
```

> **About the failures you will see.** The suite is **~1250 passing and 25
> failing**, and those 25 are a *known baseline*, not a broken checkout: they are
> long-standing round-trip gaps, tracked separately. What matters when you change
> something is that **the LIST does not change** — compare the names, not the
> count:
>
> ```bash
> PYTHONPATH=src .venv/bin/python -m pytest tests -q 2>&1 | grep '^FAILED' | sort > /tmp/after.txt
> diff /tmp/baseline.txt /tmp/after.txt
> ```
>
> A new name in that diff is your regression; the same 25 names are the weather.

### The CLI — the fastest way to see what the library does

Every operation on the access surface is also a subcommand, with no web
dependency. Given any `.em.json`:

```bash
PYTHONPATH=src .venv/bin/python -m s3dgraphy.api open      study.em.json   # {"nodes": 3, "edges": 1}
PYTHONPATH=src .venv/bin/python -m s3dgraphy.api validate  study.em.json   # {"ok": true, …}
PYTHONPATH=src .venv/bin/python -m s3dgraphy.api project-ttl study.em.json # Turtle on stdout
PYTHONPATH=src .venv/bin/python -m s3dgraphy.api graphml   study.em.json   # GraphML for yEd
```

`--help` lists the rest (GraphML import and conversion, narrative export to
LaTeX/DOCX, authority resolution, the resource shelf, acquisition).

### Release Process

```bash
# Bump version and create tag
bump2version patch  # or minor, major

# Push to GitHub
git push --follow-tags

# Create release on GitHub to auto-publish to PyPI
```

## 🤝 Contributing

We welcome contributions. Open an issue or a pull request on
[GitHub](https://github.com/ExtendedMatrix/s3Dgraphy) — and see the
[Development](#-development) section above for how to run the suite and read its
known baseline.

### Areas for Contribution
- **New Node Types**: Archaeological contexts, dating methods
- **Import/Export Formats**: Additional data exchange formats  
- **Visualization**: Enhanced 3D layouts and rendering
- **Analysis Tools**: Statistical analysis, pattern recognition
- **Documentation**: Examples, tutorials, case studies

## 🏛️ Extended Matrix Ecosystem

s3dgraphy is part of a larger ecosystem:

- **[EM-tools for Blender](https://github.com/zalmoxes-laran/EM-blender-tools)** - 3D visualization and modeling
- **[3D Survey Collection (3DSC)](https://docs.extendedmatrix.org/projects/3DSC/)** - 3D model preparation
- **[ATON Framework](https://www.aton3d.org)** - Web-based 3D presentation
- **[Extended Matrix Documentation](https://github.com/zalmoxes-laran/ExtendedMatrix)** - Formal language specification

## 🏛 Production users & integrations

**[PyArchInit](https://github.com/pyarchinit/pyarchinit)** — first production
consumer of s3Dgraphy. PyArchInit is an open-source QGIS plugin for
archaeological data management with particular strength in **2D GIS
visualization of stratigraphic data**, maintained by an active community led
by [Luca Mandolesi](https://github.com/pyarchinit). It is used in production
by archaeology teams across Europe, and brings existing PyArchInit projects
into the Extended Matrix workflow as an auxiliary data source through
s3Dgraphy — referencing records live or baking them into the graph.

The PyArchInit integration drove the design of the LocationNodeGroup in
s3Dgraphy 0.1.41 (insight from
[issue #5](https://github.com/ExtendedMatrix/s3Dgraphy/issues/5) by
[Enzo Cocca](https://github.com/enzococca)).

To request inclusion in this list, see the [Ecosystem page](https://docs.extendedmatrix.org/en/latest/ecosystem.html) of the Extended Matrix manual.

### Open invitation

s3Dgraphy is designed to be consumed by independent tools. **Revit**,
**Unreal Engine**, **Houdini**, **PostgreSQL/PostGIS**, and other
domain-specific tools are natural candidates for similar bridges into the
Extended Matrix ecosystem. If you maintain such a project and want to
explore an integration, open a discussion at
[github.com/ExtendedMatrix/s3Dgraphy/discussions](https://github.com/ExtendedMatrix/s3Dgraphy/discussions)
or look at the PyArchInit integration as a worked example.

## Pubblicare su PyPI

Il rilascio è **manuale** — Actions → *Publish to PyPI* → *Run workflow*, con il
tag e il bersaglio (`testpypi` o `pypi`) — e **non usa nessun token**.

### Perché non un token

Un token API di lunga vita nei segreti del repository è una chiave di una
persona che tiene in ostaggio un artefatto del progetto, e non dice **da dove**
viene la wheel. Misurato il 22 settembre 2026 sulla versione che i servizi
installano davvero:

```
curl https://pypi.org/integrity/s3dgraphy/1.6.0.dev18/\
     s3dgraphy-1.6.0.dev18-py3-none-any.whl/provenance
→ 404  {"message":"No provenance available for …"}
```

Tre servizi installano questa libreria e finisce dentro le immagini Docker che
consegniamo a un partner: chi le specchia può risalire al Dockerfile, al commit
e al tag — e poi arriva alla wheel, e la catena si interrompe lì.

Il **Trusted Publisher** toglie il token e dà l'attestazione, perché sono la
stessa cosa vista dai due lati: PyPI si fida di un'identità — questo
repository, questo workflow — invece che di un segreto, e quell'identità è
esattamente ciò che l'attestazione afferma.

### I campi da mettere su PyPI (una volta, e li mette E.D.)

PyPI → *Your projects* → **s3dgraphy** → *Settings* → **Publishing** → *Add a
new publisher* → **GitHub**. Quattro campi, e questi sono i valori esatti:

| campo | valore |
|---|---|
| **Owner** | `ExtendedMatrix` |
| **Repository name** | `s3Dgraphy` |
| **Workflow name** | `publish.yml` |
| **Environment name** | *(vuoto)* |

`Environment name` resta vuoto perché il workflow non dichiara nessun
`environment:`. Se un giorno gliene si dà uno — è il modo di chiedere
un'approvazione umana prima del push su PyPI — quel campo va compilato con lo
stesso nome, e i due devono restare d'accordo.

Su **TestPyPI** la procedura è identica, sul sito `test.pypi.org`, con gli
stessi quattro valori: sono due indici diversi e ciascuno tiene la sua lista.

Finché quei campi non ci sono, il workflow **fallisce** al passo di publish con
un errore di PyPI che dice che il publisher non è configurato — che è il modo
giusto di fallire.

### Il cancello

Dopo ogni rilascio in produzione il workflow interroga l'indice:

```bash
./scripts/verifica-provenance.sh 1.6.0.dev19
```

Un publish riuscito senza provenance è un publish che ha fatto metà del lavoro
e lo dichiara riuscito. Lo script distingue i due guasti — l'attestazione che
**manca** e quella che nomina un **altro repository**, che è il più grave dei
due perché sembra una garanzia — e si può lanciare a mano su qualunque versione
già pubblicata, inclusa una di un altro progetto:

```bash
PACCHETTO=sigstore GITHUB_REPOSITORY=sigstore/sigstore-python \
  ./scripts/verifica-provenance.sh 4.5.0
```

## 📄 License

This project is licensed under the **GNU General Public License v3.0** - see the [LICENSE](LICENSE) file for details.

The GPL-3.0 license ensures that s3dgraphy remains free and open source, promoting transparency and collaboration in archaeological research and heritage preservation.

## 🏛️ Citation

If you use s3dgraphy in your research, please cite:

```bibtex
@software{s3dgraphy,
  title={s3dgraphy: 3D Stratigraphic Graph Management Library},
  author={Demetrescu, Emanuel},
  year={2026},
  url={https://github.com/ExtendedMatrix/s3Dgraphy},
  version={1.6.0},
  institution={CNR-ISPC (National Research Council - Institute of Heritage Science)}
}
```

## 👥 Credits

**Author & Maintainer**: [Emanuel Demetrescu](https://github.com/zalmoxes-laran) (CNR-ISPC)

**Institution**: National Research Council of Italy - Institute of Heritage Science (CNR-ISPC)

**Funding**: This research has been supported by various archaeological and heritage preservation projects.

## 🔗 Links

- **GitHub Repository**: https://github.com/ExtendedMatrix/s3Dgraphy
- **PyPI Package**: https://pypi.org/project/s3dgraphy/
- **Documentation**: https://docs.extendedmatrix.org/projects/s3dgraphy/
- **Extended Matrix Website**: https://www.extendedmatrix.org
- **Bug Reports**: https://github.com/ExtendedMatrix/s3Dgraphy/issues

---

*s3dgraphy - Bringing archaeological stratigraphy into the digital age* 🏛️✨
# em.json — specification, schemas, conformance suite

The single home of the em.json format: EMStudio and the other tools receive the
schemas from here (`./em.sh sync` in EMStudio), and the site publishes them.

| File | What |
|---|---|
| `SPEC.md` | The specification, version 1.1, Editor's Draft. Editor: Emanuel Demetrescu (CNR-ISPC). |
| `em.v1.1.schema.json` | JSON Schema of the container (em.json 1.1). |
| `em.v1.schema.json` | JSON Schema of the flat form (em.json 1.0), frozen 11 July 2026 — kept intact for the old files. |
| `conformance/` | Sample files, their expected reading, and `reference_reading.py`. |
| `CITATION.cff` | How to cite the specification (ready for Zenodo). |
| `w3id-alias-em/` | `.htaccess` and README for the `/em` legacy alias on w3id (PR not opened). |
| `tools/publish_site.py` | Writes the published copies into the ExtendedMatrix-site checkout. |

Canonical IRIs:

- <https://w3id.org/extendedmatrix/spec/em-json/>
- <https://w3id.org/extendedmatrix/schemas/em.v1.1.schema.json>
- <https://w3id.org/extendedmatrix/schemas/em.v1.schema.json>

## Licences

- The **text** of the specification (`SPEC.md`) is licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): reuse it, cite it.
- The **schemas**, the **conformance suite** and the **examples** are dedicated
  to the public domain under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/):
  anyone must be able to implement em.json — copy a schema into a product, a
  sample into a test — without attribution clauses to carry. Authorship stays
  where it belongs, in the specification that is cited.

The rest of the s3Dgraphy repository keeps its own licence (`LICENSE` at the
root); this directory's licences are those above.

# Tre `.3tz` piccoli, scritti una volta (MICRO-REVISIONE, 30 set 2026)

s3Dgraphy non scrive più `.3tz` (decisione di E.D. del 30 set 2026: è preparazione dei dati; scrivono 3DSC ed EMStudio). I test leggono questi tre file.

Tutti e tre impacchettano lo **stesso albero** di tre file, lo stesso `MEMBERS` di `tests/test_tileset_resource.py`:

| percorso | byte |
|---|---|
| `tileset.json` | il JSON di `TILESET` in quel test (radice che punta a `Data/c01/e0001.b3dm`) |
| `Data/c01/e0001.b3dm` | `b"b3dm" + b"\x01" * 100` |
| `Data/c02/e0002.b3dm` | `b"b3dm" + b"\x02" * 200` |

## `small_3dsc.3tz` — il profilo canonico

Scritto con il modulo di 3DSC, `3D-survey-collection/cesium_exporter/archive_3tz.py` (commit `1430128`, ramo `3DSC-dev-1.7.0`, sha256 del file `3309db817b14134b81c5da186bba02170b016d1e6c792c1198758ec965209afd`), importato dal suo percorso senza modificarlo:

```python
import archive_3tz
archive_3tz.write_3tz("small", "small_3dsc.3tz")   # compress=False, il default
```

sha256 `75b111b73bbd230e5083091304a53e19d1ad4495763b16f318c803bdec86f0bf`, 1027 B. Una seconda scrittura ha dato lo stesso digest; `verify_3tz` di 3DSC: `ok`.

## `small_3dtilestools_a.3tz`, `small_3dtilestools_b.3tz` — non canonici

Scritti con `3d-tiles-tools` 0.5.4 (installato con `npm install --ignore-scripts`, perché il suo `better-sqlite3` non compila su Node 26), sullo stesso albero, a due secondi di distanza:

```bash
3d-tiles-tools convert -i small -o small_3dtilestools_a.3tz
```

| file | sha256 | data di ogni voce |
|---|---|---|
| `_a` | `f2f020c8b840334f6ec09769b4f3c2295ef26dcd108ee2dc434a753342c9f269` | 2026-09-30 20:05:54 |
| `_b` | `7086f47152d6909b941353d8740a06e2a341de1f89eb7aa76c658d18146b744e` | 2026-09-30 20:05:56 |

Stesso contenuto, due digest: ogni voce porta l’ora in cui è stata scritta (in UTC: la console diceva 22:05 locali), e `create_version` 45 invece di 20. Negli attributi, in più, il bit «archivio» del DOS: `external_attr` `0x81a40020` invece di `0x81a40000`. Per il resto, stored, in ordine, `create_system` 3, nessun campo extra, indice ordinato: come quello di 3DSC.

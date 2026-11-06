"""Il **timbro**: il verbale immutabile di un passo, scritto per stare da solo.

Un agente, con un processo e dei parametri, consuma uno o più ingressi e produce
**un** artefatto. Non è un formato nuovo e non introduce nessun tipo di nodo: i
nodi che cita — risorsa, processo con parametri, agente, licenza, embargo — sono
già tipi di s3Dgraphy, e il substrato DTC (`nodes/dtc_node.py`) dice da sempre
che un nodo è un anello e la provenienza assemblata è la catena. **Tre referenti,
tre parole**: la *chain* è l'insieme, uno **step** è la singola trasformazione,
uno **stamp** è il file che ne registra uno — *a stamp attests one step of a
chain*. Il timbro è quello step, scritto per uscire dal perimetro.

## Metà di questo pacchetto vive altrove, e la riga che li divide

Il **formato** — leggere, scrivere, validare, confrontare, risalire, e la forza
di un'identità — è in **`dtcstamp`**: un modulo solo, senza dipendenze, che si
copia accanto al proprio codice. Chi scrive un addon per Blender o uno script
per Metashape non installerà mai pandas, lxml e networkx per scrivere due
kilobyte di JSON, ed è tutta lì la ragione dell'estrazione.

Quello che resta qui è **ciò che ha bisogno di un grafo**, e sono due cose:
costruire un timbro leggendo nodi e archi, e rifonderlo dentro un grafo. Il
resto è importato e ri-esportato con gli stessi nomi, perché `from
s3dgraphy.stamp import …` è un import che qualcuno ha scritto.

Tre moduli e una divisione che è un contratto:

* :mod:`.emit` — grafo → timbro. Funzione **pura**: niente filesystem, niente
  orologio. Chi scrive su disco è un'altra funzione.
* :mod:`.absorb` — timbro → grafo, come **merge per UUID** (quello che la
  libreria già fa, `container.merge_graph_into`). Due timbri che si
  contraddicono nella sostanza non sono un errore: sono una scoperta, e qui
  **non si sceglie un vincitore**.
* :mod:`.hints` — le piste, che sono un'altra cosa: un registro mutevole, plurale
  e non autorevole, in un file separato e **mai coperto da nessun digest**. Una
  pista `private` non esce mai. **Traslocato in `dtcstamp`**: non ha mai avuto
  bisogno di un grafo.
* :mod:`.identity` — quanto è forte un'identità: `sha256:` **dimostra**,
  `emstruct1:` **confronta**. La differenza fra «è lei» e «è cambiata», chiesta a
  una funzione invece che a un `startswith`. **Traslocato in `dtcstamp`**.

I nomi dei file sono `<asset>.stamp.json` e `<asset>.hints.json`, in inglese
perché escono da casa nostra. Non `em.json` (specie diversa: inviterebbe a
fondere, editare, versionare un verbale) e non `dtc.json` (prometterebbe una
catena e consegna un anello).
"""

from .absorb import (AbsorbResult, BadStamp, Disagreement, absorb_stamp,
                     absorb_stamp_file, compare_stamps, read_stamp,
                     stamp_to_graph, substance, validate_stamp)
from .emit import (NotAnArtifact, STAMP_VERSION, clean_stamp, emit_stamp,
                   is_verifiable_stamp, stamp_filename, stamp_identity,
                   write_stamp)
from .hints import (HINTS_VERSION, file_digest, for_export, hints_filename,
                    new_hints, note_seen, private_locators, read_hints,
                    scan_directory, write_hints, write_public_hints)
from .identity import (COMPARABLE, UNKNOWN, VERIFIABLE, describe_identity,
                       identity_strength, is_comparable, is_verifiable,
                       split_identity)
# MICRO-TIMBRA-MASTER · what a format reader needs to write stamps, through the
# library (a reader imports nothing but the stdlib and s3dgraphy)
from dtcstamp import (content_digest, new_tree_stamp, now_iso,
                      parse_psx_locator)

__all__ = [
    "AbsorbResult", "BadStamp", "COMPARABLE", "Disagreement", "HINTS_VERSION",
    "NotAnArtifact", "STAMP_VERSION", "UNKNOWN", "VERIFIABLE", "absorb_stamp",
    "absorb_stamp_file", "clean_stamp", "compare_stamps", "describe_identity",
    "emit_stamp", "file_digest", "for_export", "hints_filename",
    "identity_strength", "is_comparable", "is_verifiable",
    "is_verifiable_stamp", "new_hints", "note_seen", "private_locators",
    "read_hints", "read_stamp", "scan_directory", "split_identity",
    "stamp_filename", "stamp_identity", "stamp_to_graph", "substance",
    "validate_stamp", "write_hints", "write_public_hints", "write_stamp",
    "content_digest", "new_tree_stamp", "now_iso", "parse_psx_locator",
]

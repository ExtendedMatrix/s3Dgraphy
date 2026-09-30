"""La cattura è un'acquisizione: la forma definitiva, e la lettura della provvisoria.

Dal 1.6.22 di `em_visual_rules.json` l'asse `acquisition` di `dtc_kinds` ha due
famiglie: **capture** (la cosa digitale nasce dall'atto — fotografia, scansione,
rilievo, disegno, scheda) e **retrieval** (arriva già fatta — download, import
locale, riferimento URI, ingest). Nessun tipo di nodo nuovo: una cattura è il
`dtc_kind` di un `DTCAcquisitionNode`.

## La forma definitiva

Una sola: **`dtc_kind` è la cattura.** Nel grafo `data.dtc_kind = "photo"` sul
nodo di acquisizione; nel timbro `how.dtc_kind = "photo"`. La famiglia non si
scrive da nessuna parte: si legge dal vocabolario (`get_dtc_kind_family`), e un
dato ricavabile scritto accanto alla sua fonte è una seconda verità che prima o
poi dice un'altra cosa.

## La forma provvisoria, che si legge ancora

Fino a qui EMStudio non poteva dare una cattura come genere di un'acquisizione,
e la portava accanto: il genere era il default della libreria (`local_import`)
e la cattura stava in `how.acquisition.capture` nel timbro, cioè in
`data.capture` sul nodo (è la strada di `bucket_acquisition(metadata=…)`).

Quel `local_import` **non l'ha detto nessuno**: lo metteva il bridge perché il
campo era validato e la cattura non ci entrava. Per questo la lettura lo scarta
e tiene la cattura. Un genere di recupero diverso dal default (`download`,
`ingest`…) accanto a una cattura è invece una dichiarazione di qualcuno, e non
si tocca: la cattura resta scritta dov'era.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

#: Il default che il bridge scriveva al posto della cattura. Lo stesso di
#: `dtc.ingest.DEFAULT_ACQUISITION_KIND`, ripetuto qui per non importare il
#: modulo dell'ingestione da quello che lo legge.
PLACEHOLDER_KIND = "local_import"

#: La chiave della forma provvisoria: `how.acquisition.capture` nel timbro,
#: `data.capture` sul nodo.
CAPTURE_KEY = "capture"


def is_capture(kind: Any) -> bool:
    from ..utils.utils import get_dtc_kind_family

    return isinstance(kind, str) and get_dtc_kind_family(kind) == "capture"


def definitive(dtc_kind: Optional[str],
               facts: Optional[Dict[str, Any]]) -> Tuple[Optional[str], Dict[str, Any]]:
    """(genere, fatti dell'atto) nella forma definitiva.

    `facts` è il blocco aperto dell'acquisizione — `how.acquisition` di un timbro
    o i campi liberi del nodo. Se porta una `capture` del vocabolario e il genere
    è assente o è il segnaposto, la cattura diventa il genere e sparisce dai
    fatti. Altrimenti torna tutto com'era. Non modifica gli argomenti.
    """
    out = dict(facts or {})
    capture = out.get(CAPTURE_KEY)
    if is_capture(capture) and (not dtc_kind or dtc_kind == PLACEHOLDER_KIND):
        out.pop(CAPTURE_KEY)
        return capture, out
    return dtc_kind, out


def upgrade_stamp(stamp: Dict[str, Any]) -> Dict[str, Any]:
    """Il timbro con `how` nella forma definitiva — una copia, e lo stesso
    oggetto quando non c'è niente da cambiare."""
    how = stamp.get("how")
    if not isinstance(how, dict):
        return stamp
    acquisition = how.get("acquisition")
    if not isinstance(acquisition, dict) or CAPTURE_KEY not in acquisition:
        return stamp
    kind, facts = definitive(how.get("dtc_kind"), acquisition)
    if kind == how.get("dtc_kind"):
        return stamp
    new_how = dict(how)
    new_how["dtc_kind"] = kind
    if facts:
        new_how["acquisition"] = facts
    else:
        new_how.pop("acquisition")
    return {**stamp, "how": new_how}


def migrate_provisional_captures(graph: Any) -> int:
    """All'apertura: ogni `DTCAcquisitionNode` con `data.capture` e il genere
    segnaposto diventa un'acquisizione di quella cattura. Idempotente;
    restituisce quanti nodi ha cambiato."""
    changed = 0
    for node in list(getattr(graph, "nodes", []) or []):
        if getattr(node, "node_type", None) != "dtc_acquisition":
            continue
        data = getattr(node, "data", None)
        if not isinstance(data, dict) or CAPTURE_KEY not in data:
            continue
        kind, _ = definitive(data.get("dtc_kind"), {CAPTURE_KEY: data[CAPTURE_KEY]})
        if kind != data.get("dtc_kind"):
            data["dtc_kind"] = kind
            data.pop(CAPTURE_KEY)
            changed += 1
    return changed

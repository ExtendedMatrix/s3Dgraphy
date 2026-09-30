"""Riassorbire il timbro: un verbale torna a essere grafo.

Un timbro è un frammento di em.json scritto in miniatura, quindi riattaccarlo è
**un merge per UUID** — e quello la libreria lo sa già fare. Qui non se ne scrive
un secondo: si costruisce il frammento come `Graph` e lo si piega dentro con
`container.merge_graph_into`, che è l'algebra CRDT di P4.1 (OR-Set per la
presenza, LWW-per-campo per il contenuto, i timbri editoriali come orologi).

## La regola che vale più di tutte le altre

**Due timbri per lo stesso digest che si contraddicono nella sostanza — genitori
diversi, processo diverso — non sono un errore: sono una scoperta.**

Quindi qui non c'è nessuna politica di risoluzione e **non si sceglie un
vincitore**. Quando i due contenuti non vanno d'accordo il grafo **non viene
toccato** e il risultato consegna i due timbri interi a chi legge — quello che il
grafo dice adesso e quello che è arrivato — con l'elenco dei punti in cui
divergono. Chi decide è una persona, e non stanotte.

È anche il motivo per cui il confronto non è «i due file sono uguali byte per
byte»: il timbro **non ha identità di contenuto propria** (è chiavato dal digest
della sua uscita), quindi due implementazioni possono serializzare gli stessi
fatti in modi diversi. Si confrontano i **fatti**, e si confrontano generando dal
grafo il timbro che quel grafo emetterebbe — cioè con la funzione di T1, nella
stessa lingua.

## Cosa è sostanza e cosa no

Non è sostanza l'**istante** (`by.at`, `declared.as_of`): due timbri che
differiscono solo lì sono lo stesso fatto registrato due volte, e si
deduplicano. Non lo è il `registry`, che il formato dichiara «un indizio per
ritrovare, non un'autorità»: lo stesso artefatto può stare in due stanze. Non lo
sono le `label`, «cortesia per un umano, non identità».

**Tutto il resto lo è.** Genitori, processo, tecnica, parametri, software,
operatore, misure. Anche il software: lo stesso algoritmo in due versioni non
produce gli stessi byte, quindi due versioni per lo stesso digest sono due
affermazioni che non possono essere entrambe vere.

## E il silenzio non è un disaccordo

Un campo che una parte dice e l'altra tace non è una contraddizione: è
un'aggiunta, e il merge la assorbe. Serve che **entrambe** parlino e dicano cose
diverse. Senza questa regola un timbro ricco non potrebbe mai atterrare su un
grafo povero — che è il caso normale.

Con una eccezione misurata, ed è il punto più sottile del formato: `"from": []`
**è** una dichiarazione («nato qui») quando c'è un `how` che la firma, e **non è
niente** quando il `how` manca — lì significa solo «di questo artefatto non so
come è stato fatto». Trattare i due casi allo stesso modo farebbe gridare al
disaccordo ogni volta che un timbro con genitori arriva su una risorsa nuda.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from dtcstamp import (BadStamp, Disagreement, STAMP_VERSION, clean_stamp,
                      compare_stamps, read_stamp, stamp_description,
                      stamp_title, substance, validate_stamp)

from ..dtc.capture import upgrade_stamp
from .emit import (EDGE_HAD_INPUT, EDGE_HAD_OUTPUT, SIZE_KEY, emit_stamp,
                   find_resource)

#: I campi del nodo che portano una COPIA delle parole del timbro
#: (`self.label` → `name`, `self.description` → `description`). Il marchio sta
#: in `data`, accanto al contenuto: dice a chi legge — e al prossimo
#: riassorbimento — che quel testo non l'ha scritto una persona su questo nodo,
#: e che quindi un timbro successivo può aggiornarlo. Un campo che non è qui e
#: che ha un testo è di una persona, e un timbro non lo tocca.
COPIED_FROM_STAMP = "copied_from_stamp"

#: L'arco diretto uscita → ingresso, la scorciatoia che il substrato scrive
#: accanto alla coppia input/output. Stesso nome di `dtc.residency`.
EDGE_DERIVED_FROM = "dtc_derived_from"

#: Il genere di processo da usare quando il timbro non ne porta uno. Lo stesso
#: che `publication.promote_resource` scrive: un timbro che non dichiara l'asse
#: non deve far nascere un nodo senza `dtc_kind`, perché quel campo è validato.
DEFAULT_PROCESS_KIND = "transformation"

#: I percorsi che **non** fanno sostanza. Vedi il docstring del modulo.
IGNORED_PATHS = ("by.at", "declared.as_of", "registry", "_notes")


# ── quello che il FORMATO sa fare, e che non sta più qui ─────────────────────
#
# `BadStamp`, `validate_stamp`, `read_stamp`, `substance`, `compare_stamps` e
# `Disagreement` sono importati da `dtcstamp` e **ri-esportati con questi nomi**:
# non hanno mai avuto bisogno di un grafo — leggono e confrontano JSON — e chi
# scrive un addon per Blender non deve installare pandas per confrontare due
# verbali. I nomi restano raggiungibili da qui perché `from
# s3dgraphy.stamp.absorb import BadStamp` è un import che qualcuno ha scritto.
#
# Quello che resta in questo modulo ha bisogno di un grafo, ed è la ragione per
# cui il modulo esiste ancora: costruire il frammento e fonderlo.

@dataclass
class AbsorbResult:
    """Cosa è successo, detto in modo che si possa controllare.

    `applied` è falso in due casi diversi e il chiamante deve poterli
    distinguere: **deduplicato** (lo stesso fatto già registrato: non c'era
    niente da fare) e **in disaccordo** (c'era qualcosa da fare e non tocca a noi
    decidere cosa). Un booleano solo li avrebbe confusi, e sono l'opposto l'uno
    dell'altro.
    """

    digest: Optional[str] = None
    resource_id: Optional[str] = None
    applied: bool = False
    deduplicated: bool = False
    disagreements: List[Disagreement] = field(default_factory=list)
    #: I due contenuti interi, quando c'è un disaccordo: chi legge deve avere in
    #: mano tutti e due, non un elenco di differenze da cui ricostruirli.
    mine: Optional[Dict[str, Any]] = None
    theirs: Optional[Dict[str, Any]] = None
    added_nodes: int = 0
    merged_nodes: int = 0
    added_edges: int = 0
    #: i campi del nodo (`name`, `description`) che hanno ricevuto una COPIA di
    #: titolo e descrizione del timbro; vuoto se non ne portava o se una persona
    #: li aveva già scritti
    courtesy: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def in_disagreement(self) -> bool:
        return bool(self.disagreements)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "digest": self.digest,
            "resource_id": self.resource_id,
            "applied": self.applied,
            "deduplicated": self.deduplicated,
            "in_disagreement": self.in_disagreement,
            "disagreements": [d.as_dict() for d in self.disagreements],
            "mine": self.mine,
            "theirs": self.theirs,
            "added_nodes": self.added_nodes,
            "merged_nodes": self.merged_nodes,
            "courtesy": list(self.courtesy),
            "added_edges": self.added_edges,
            "warnings": list(self.warnings),
        }


# ── costruire il frammento ───────────────────────────────────────────────────

def stamp_to_graph(stamp: Dict[str, Any], *, graph_id: Optional[str] = None):
    """Il timbro come `Graph` — il frammento di em.json che è sempre stato.

    Nessun tipo di nodo nuovo: una `ResourceNode` per l'uscita, una per ogni
    ingresso che sia un file, un `DTCAcquisitionNode` per un ingresso che sia una
    campagna, un `DTCProcessNode` per il passo. Gli archi sono i tre che il
    substrato già usa, con la stessa disciplina di `declare_derivation`: la
    scorciatoia `dtc_derived_from` si scrive **solo** fra file, perché fra un file
    e una campagna non c'è una derivazione da scrivere — c'è un evento.
    """
    from ..graph import Graph
    from ..nodes import DTCAcquisitionNode, DTCProcessNode, ResourceNode

    validate_stamp(stamp)
    stamp = upgrade_stamp(stamp)
    itself = dict(stamp.get("self") or {})
    resource_id = str(itself["resource_id"])
    fragment = Graph(graph_id=graph_id or f"stamp:{resource_id}")
    _strip_born_with(fragment)

    output = ResourceNode(resource_id, name=resource_id)
    _apply_self(output, itself)
    _apply_courtesy(output, stamp)
    fragment.add_node(output)

    how = dict(stamp.get("how") or {})
    parents = [p for p in (stamp.get("from") or []) if isinstance(p, dict)]
    if not how and not parents:
        # Il passo vuoto SENZA how: c'è solo l'artefatto e ciò che dichiara.
        # Un processo inventato qui sarebbe un evento che nessuno ha compiuto.
        _apply_declared(output, stamp)
        return fragment

    process_id = str(how.get("process_id") or "").strip() \
        or f"{resource_id}::step"
    if _is_origin_acquisition(how, parents):
        # UN'ORIGINE È UN'ACQUISIZIONE, e torna a esserlo. Fino al 1.6.22 questo
        # ramo non c'era: un timbro emesso da un `DTCAcquisitionNode` rientrava
        # come un `DTCProcessNode` di genere `transformation` — il genere
        # dichiarato cadeva sul default, i fatti del lotto si perdevano, e il
        # secondo riassorbimento dello STESSO timbro era in disaccordo con il
        # primo (`how.dtc_kind`: transformation contro local_import). Misurato.
        process = DTCAcquisitionNode(
            process_id,
            name=str(how.get("technique") or "Acquisition"),
            description="",
            dtc_kind=str(how["dtc_kind"]))
        facts = {k: v for k, v in (how.get("acquisition") or {}).items()
                 if k not in ("device", "location") or not isinstance(v, dict)}
        if facts:
            process.data["acquisition"] = facts
    else:
        process = DTCProcessNode(
            process_id,
            name=str(how.get("technique") or "step"),
            description="",
            dtc_kind=_process_kind(how))
    _apply_how(process, how)
    _apply_by(process, stamp.get("by") or {})
    _apply_declared(process, stamp)
    fragment.add_node(process)
    fragment.add_edge(f"{process_id}->{resource_id}", process_id, resource_id,
                      EDGE_HAD_OUTPUT)
    # HW1 · IL CORPO TORNA A ESSERE UN NODO. È qui che si vede il vincolo che
    # tiene in piedi l'estrazione: `dtcstamp` porta VALORI — un id, un'etichetta,
    # marca e modello — e non sa e non deve sapere che esista una classe
    # `DTCDeviceNode`. È questo lato, che il grafo ce l'ha, a trasformarli in un
    # nodo tipizzato e in un arco.
    #
    # DOPO `add_node(process)`, e non prima: `Graph.add_edge` pretende che
    # entrambi i capi esistano già, e la prima versione di questa riga stava
    # sopra — l'arco cercava un processo che nel frammento non c'era ancora.
    _absorb_device(fragment, process, how)

    for parent in parents:
        pid = str(parent.get("resource_id") or "").strip()
        if not pid:
            continue
        if str(parent.get("kind") or "") == "acquisition":
            node = DTCAcquisitionNode(pid, name=str(parent.get("label") or pid))
            fragment.add_node(node)
            fragment.add_edge(f"{process_id}->{pid}", process_id, pid,
                              EDGE_HAD_INPUT)
            continue
        node = ResourceNode(pid, name=str(parent.get("label") or pid))
        digest = str(parent.get("digest") or "").strip()
        if digest:
            node.data["checksum"] = digest
        fragment.add_node(node)
        fragment.add_edge(f"{process_id}->{pid}", process_id, pid,
                          EDGE_HAD_INPUT)
        fragment.add_edge(f"{resource_id}~>{pid}", resource_id, pid,
                          EDGE_DERIVED_FROM)
    return fragment


def _strip_born_with(fragment: Any) -> None:
    """Toglie dal frammento quello che `Graph.__init__` gli mette addosso da solo.

    **Misurato, e non è un dettaglio.** Ogni `Graph` nasce con un
    `GeoPositionNode` di nome `geo_<graph_id>` (`graph.py:64`), perché un grafo di
    studio ha un posto sulla terra. Un frammento di timbro **non è un grafo di
    studio**: è un anello di catena. Senza questa riga, riassorbire un timbro
    piegava dentro al grafo di chi lo riceve un nodo `geo_stamp:res:mesh` — una
    posizione geografica **vuota e altrui**, arrivata per posta insieme a un
    verbale che non parlava di geografia.

    Non si cancella niente al ricevente: si toglie dal frammento, prima che parta.
    """
    for node in list(getattr(fragment, "nodes", []) or []):
        if getattr(node, "node_type", None) == "geo_position":
            fragment.remove_node(node.node_id)


def _is_origin_acquisition(how: Dict[str, Any], parents: List[Any]) -> bool:
    """Il passo è un'acquisizione: nessun genitore, e un genere dell'asse
    `acquisition` — una cattura o un recupero.

    Con dei genitori resta un processo anche se il genere è di acquisizione: il
    substrato scrive `dtc_had_input` solo da un processo, e un'acquisizione con
    degli ingressi non è un'origine. Il genere, allora, cade sul default come ha
    sempre fatto.
    """
    from ..nodes.dtc_node import DTC_KINDS

    if parents:
        return False
    return str(how.get("dtc_kind") or "").strip() in DTC_KINDS.get("acquisition", ())


def _process_kind(how: Dict[str, Any]) -> str:
    """L'asse controllato, e il ripiego quando il timbro non lo porta.

    `dtc_kind` è **validato** contro il vocabolario dei dati, quindi un valore
    che non c'è farebbe sollevare il costruttore e il timbro non atterrerebbe
    affatto. Un timbro che porta una `technique` fine ma non l'asse coarse cade
    sul genere di default — lo stesso che scrive `promote_resource` — e la
    `technique` resta scritta per intero in `data`: niente si perde, e nessun
    vocabolario si allarga per sbaglio a partire da un file arrivato da fuori.
    """
    from ..nodes.dtc_node import DTC_KINDS

    stated = str(how.get("dtc_kind") or "").strip()
    allowed = DTC_KINDS.get("process", ())
    return stated if stated in allowed else DEFAULT_PROCESS_KIND


def _apply_self(node: Any, itself: Dict[str, Any]) -> None:
    data = node.data
    for key in ("digest_covers", "media_type", "format", "packaging", "tier"):
        value = itself.get(key)
        if value not in (None, ""):
            data[key] = value
    digest = itself.get("digest")
    if digest:
        data["checksum"] = digest
    measures = itself.get("measures")
    if isinstance(measures, dict):
        # La chiave riservata torna al suo campo, tutto il resto ai `primitives`:
        # è l'inverso esatto dell'appiattimento che l'emissione fa, e per questo
        # il giro torna senza un secondo campo nel formato.
        primitives = {k: v for k, v in measures.items() if k != SIZE_KEY}
        if measures.get(SIZE_KEY) is not None:
            data[SIZE_KEY] = measures[SIZE_KEY]
        if primitives:
            data["primitives"] = primitives


def _get_text(node: Any, field_name: str) -> str:
    """`name` è un attributo; la `description` di una `ResourceNode` sta in
    `data` (è lì che il costruttore la scrive), e l'attributo di `Node` è il
    ripiego."""
    if field_name == "description":
        data = getattr(node, "data", None) or {}
        return str(data.get("description") or getattr(node, "description", "")
                   or "").strip()
    return str(getattr(node, field_name, "") or "").strip()


def _set_text(node: Any, field_name: str, value: str) -> None:
    setattr(node, field_name, value)
    if field_name == "description" and isinstance(getattr(node, "data", None), dict):
        node.data["description"] = value


def _written_by_a_person(node: Any, field_name: str) -> bool:
    """Il campo ha un testo che nessun timbro ha messo lì.

    Un `name` uguale all'id non conta: è il segnaposto che ogni costruttore
    scrive quando non sa come chiamare la risorsa, non una scelta di qualcuno.
    """
    copied = (getattr(node, "data", None) or {}).get(COPIED_FROM_STAMP) or []
    if field_name in copied:
        return False
    text = _get_text(node, field_name)
    if not text:
        return False
    if field_name == "name" and text == str(getattr(node, "node_id", "")):
        return False
    return True


def _apply_courtesy(node: Any, stamp: Dict[str, Any],
                    host: Optional[Any] = None) -> List[str]:
    """Porta titolo e descrizione del timbro nel nodo, **come copia marcata**.

    `host` è il nodo che il grafo ricevente ha già per quella risorsa, se c'è:
    è lui a dire che cosa ha scritto una persona. Un campo scritto da una
    persona non si sovrascrive mai — il nodo tiene il suo testo, e il timbro
    resta il timbro. Un timbro senza titolo né descrizione non tocca niente.
    Restituisce i campi copiati.
    """
    judge = host if host is not None else node
    words = (("name", stamp_title(stamp)),
             ("description", stamp_description(stamp)))
    copied = list((getattr(judge, "data", None) or {}).get(COPIED_FROM_STAMP) or [])
    done: List[str] = []
    for field_name, value in words:
        if not value:
            continue
        if _written_by_a_person(judge, field_name):
            if judge is not node:
                # il frammento porta il testo della persona, così il merge
                # non ha niente da cambiare
                _set_text(node, field_name, _get_text(judge, field_name))
            continue
        _set_text(node, field_name, value)
        if field_name not in copied:
            copied.append(field_name)
        done.append(field_name)
    if copied:
        node.data[COPIED_FROM_STAMP] = copied
    return done


def _apply_how(node: Any, how: Dict[str, Any]) -> None:
    data = node.data
    for key in ("technique", "parameters"):
        value = how.get(key)
        if value not in (None, "", {}):
            data[key] = value
    # HW1 · LA POSIZIONE torna dov'era: valori sull'evento. NON diventa un nodo,
    # e la ragione è misurata e non scelta — l'unico E53 di questo datamodel è
    # `GeoPositionNode`, che il suo stesso docstring dichiara essere l'ANCORA
    # della scena, UNA PER GRAFO, e «non è dove va il puntino sulla mappa».
    # Scrivere lì dentro dove è stata scattata una foto sovrascriverebbe lo
    # shift del grafo con una coordinata di campo. Il tipo per «dove è avvenuto
    # un passo» non esiste ancora: vedi l'END OF di HW1.
    acquisition = how.get("acquisition")
    if isinstance(acquisition, dict):
        location = acquisition.get("location")
        if isinstance(location, dict) and location:
            data["location"] = dict(location)
    software = how.get("software")
    if isinstance(software, list) and software:
        data["software"] = software
        # `tool` resta scritto accanto perché `dtc.ingest._event_card` e le
        # schede che già esistono lo leggono: un riassorbimento che lasciasse
        # quel campo vuoto renderebbe muta un'interfaccia che funzionava.
        first = software[0]
        if isinstance(first, dict) and first.get("name"):
            data["tool"] = dict(first)


def _absorb_device(fragment: Any, process: Any, how: Dict[str, Any]) -> None:
    """`how.acquisition.device` → un `DTCDeviceNode` e il suo arco.

    **L'id arriva dal timbro e non si ricalcola.** Chi ha emesso l'ha derivato
    dal descrittore, e rifare il conto qui vorrebbe dire avere due derivazioni
    per una cosa sola — che è come due copie di una regola smettono di
    coincidere. Se il timbro porta l'id, quello è l'id; il descrittore che
    l'accompagna si scrive sul nodo perché è il modo in cui una persona lo
    riconosce, non perché serva a ricostruirlo.

    Un timbro che porta un `device` come STRINGA — quelli emessi prima di oggi —
    non produce nessun nodo e non è un errore: era una stringa, resta la stringa
    che era, e finisce dove finiva prima (`data.acquisition`). Inventare un id
    per lei vorrebbe dire coniare un apparecchio che nessuno ha dichiarato.
    """
    from ..nodes.dtc_device_node import DTCDeviceNode
    from ..dtc.devices import EDGE_HAPPENED_ON_DEVICE

    acquisition = how.get("acquisition")
    if not isinstance(acquisition, dict):
        return
    device = acquisition.get("device")
    if not isinstance(device, dict):
        return
    device_id = str(device.get("id") or "").strip()
    if not device_id:
        return

    data = {k: device[k] for k in ("make", "model", "serial", "distinguishes")
            if device.get(k) not in (None, "")}
    kind = str(device.get("dtc_kind") or "").strip() or None
    try:
        node = DTCDeviceNode(device_id,
                             name=str(device.get("label") or device_id),
                             dtc_kind=kind, data=data)
    except ValueError:
        # UN GENERE SCONOSCIUTO NON ALLARGA IL VOCABOLARIO, e non fa nemmeno
        # cadere il riassorbimento: il nodo nasce senza genere e il resto del
        # descrittore arriva lo stesso. Un file di qualcun altro non decide
        # quali apparecchi esistono, e non decide nemmeno se il suo timbro è
        # leggibile.
        node = DTCDeviceNode(device_id,
                             name=str(device.get("label") or device_id),
                             data=data)
    fragment.add_node(node)
    fragment.add_edge(f"edge:device:{process.node_id}:{device_id}",
                      process.node_id, device_id, EDGE_HAPPENED_ON_DEVICE)


def _apply_by(node: Any, by: Dict[str, Any]) -> None:
    """Chi e quando, **senza inventare un autore**.

    L'ORCID va nel timbro editoriale, che è il posto dove questo ecosistema
    registra la mano che ha scritto. L'operatore intero resta accanto in
    `data.operator` perché l'etichetta — il nome della persona — nel timbro
    editoriale non ci sta: quello tiene un'identità, non un nome.

    **Non si crea un `AuthorNode`.** Sarebbe il modo del substrato per un agente
    con un nome, ma il suo costruttore ha dei valori-sentinella (`noorcid`,
    `nosurname`) e farne nascere uno da un timbro vorrebbe dire scrivere quelle
    parole nel grafo di qualcuno. E `has_author` è responsabilità
    **interpretativa**: chi ha decimato una mesh non è chi risponde della lettura
    archeologica, e confondere le due è esattamente ciò contro cui `editorial.py`
    mette in guardia in testa.
    """
    from ..editorial import normalize_instant, normalize_orcid

    operator = by.get("operator")
    if isinstance(operator, dict) and operator:
        node.data["operator"] = dict(operator)
        orcid = normalize_orcid(operator.get("id"))
        if orcid:
            node.data["created_by"] = orcid
    at = normalize_instant(by.get("at"))
    if at:
        node.data["created_at"] = at


def _apply_declared(node: Any, stamp: Dict[str, Any]) -> None:
    """`declared` si registra, **non si applica**.

    Il formato è esplicito: è storia con il suo `as_of`, non una regola. Farne un
    `LicenseNode` collegato con `has_license` vorrebbe dire trasformare «allora
    diceva CC-BY-NC» in «adesso la licenza è CC-BY-NC» — cioè far decidere il
    cancello vivo a un file arrivato per posta.

    Resta scritto sul nodo del passo (o sull'artefatto, quando passo non ce n'è),
    dove un lettore lo trova insieme al resto del verbale e dove l'emissione lo
    ritrova se il grafo non ha niente di più fresco da dire. È anche ciò che
    chiude il giro completo senza toccare i diritti vivi.
    """
    declared = stamp.get("declared")
    if isinstance(declared, dict) and declared:
        node.data["declared"] = dict(declared)


# ── il riassorbimento ────────────────────────────────────────────────────────

def absorb_stamp(graph: Any, stamp: Dict[str, Any], *,
                 dry_run: bool = False) -> AbsorbResult:
    """Riattacca un timbro a un grafo, o dice perché non l'ha fatto.

    Tre esiti, e sono diversi fra loro:

    * **applicato** — il frammento è stato piegato dentro con il merge per UUID;
    * **deduplicato** — il grafo diceva già questo, a meno dell'istante: lo stesso
      fatto registrato due volte, niente da fare;
    * **in disaccordo** — il grafo dice un'altra cosa nella sostanza. Il grafo
      **non viene toccato**, e il risultato porta i due timbri interi più
      l'elenco dei punti in cui divergono. **Non si sceglie un vincitore**:
      questa funzione non ha una politica di risoluzione perché la decisione non
      è sua.

    `dry_run` risponde senza scrivere — serve a un'interfaccia che voglia
    chiedere «che cosa succederebbe» prima di proporlo a una persona.
    """
    from ..container import merge_graph_into

    validate_stamp(stamp)
    itself = dict(stamp.get("self") or {})
    result = AbsorbResult(digest=itself.get("digest"),
                          resource_id=str(itself.get("resource_id")))

    existing = find_resource(graph, result.resource_id)
    if existing is None and result.digest:
        existing = find_resource(graph, result.digest)
    if existing is not None:
        mine = clean_stamp(emit_stamp(graph, existing.node_id))
        # la forma provvisoria di una cattura si legge come la definitiva: due
        # timbri dello stesso atto non sono in disaccordo perché uno dei due è
        # stato scritto prima del 1.6.22
        theirs = clean_stamp(upgrade_stamp(stamp))
        differences = compare_stamps(mine, theirs)
        if differences:
            result.disagreements = differences
            result.mine = mine
            result.theirs = theirs
            return result
        # Nessun disaccordo. Resta una domanda sola: l'entrante porta qualcosa
        # che il grafo tace? Se no è lo stesso fatto registrato due volte.
        if _says_as_much(mine, theirs):
            result.deduplicated = True
            result.mine = mine
            result.theirs = theirs
            # Lo stesso fatto: la sostanza non cambia. Titolo e descrizione non
            # sono sostanza, e una copia si può ancora portare — mai sopra il
            # testo di una persona, mai in un dry run.
            if not dry_run:
                result.courtesy = _apply_courtesy(existing, stamp)
            mine_at = (mine.get("by") or {}).get("at")
            theirs_at = (theirs.get("by") or {}).get("at")
            if mine_at != theirs_at:
                result.warnings.append(
                    "the same fact recorded twice at different instants "
                    f"({mine_at!r} and {theirs_at!r}): deduplicated, and the "
                    "graph keeps the instant it had")
            return result

    if dry_run:
        result.warnings.append("dry run: nothing was written")
        return result

    fragment = stamp_to_graph(stamp)
    if existing is not None:
        # Il frammento ha giudicato da solo; è il nodo che il grafo ha già a
        # sapere che cosa ha scritto una persona.
        output = fragment.find_node_by_id(result.resource_id)
        if output is not None and output.node_id == existing.node_id:
            output.data.pop(COPIED_FROM_STAMP, None)
            output.name = getattr(existing, "name", output.name)
            _set_text(output, "description", _get_text(existing, "description"))
            result.courtesy = _apply_courtesy(output, stamp, host=existing)
    else:
        output = fragment.find_node_by_id(result.resource_id)
        result.courtesy = list((getattr(output, "data", None) or {})
                               .get(COPIED_FROM_STAMP) or [])
    report = merge_graph_into(graph, fragment)
    result.applied = True
    result.added_nodes = report.added_nodes
    result.merged_nodes = report.merged_nodes
    result.added_edges = report.added_edges
    result.warnings.extend(report.warnings)
    return result


def _says_as_much(mine: Dict[str, Any], theirs: Dict[str, Any]) -> bool:
    """Il grafo dice già **almeno quanto** il timbro entrante.

    La sostanza confrontabile può coincidere mentre l'entrante porta qualcosa che
    il grafo tace — un `how` su una risorsa che non ne aveva. Quello non è un
    duplicato: è un'aggiunta, e va assorbita. Senza questa riga un timbro con un
    processo atterrato su una risorsa nuda verrebbe scartato come «già visto».
    """
    said = substance(mine)
    for key, value in substance(theirs).items():
        if value in (None, "", {}, []):
            continue
        if said.get(key) in (None, "", {}, []):
            return False
    return True


def absorb_stamp_file(graph: Any, path: str, **kwargs: Any) -> AbsorbResult:
    """Come :func:`absorb_stamp`, partendo dal file."""
    return absorb_stamp(graph, read_stamp(path), **kwargs)

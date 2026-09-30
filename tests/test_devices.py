"""HW1 — l'apparecchio è un nodo, e il luogo viaggia come valori.

Le prove di questa notte, e per ogni asserzione strutturale un controesempio
deliberato che deve farla fallire.
"""

import json
import pathlib

import pytest

from s3dgraphy import api
from s3dgraphy.dtc.devices import (EDGE_HAPPENED_ON_DEVICE, attach_device,
                                   device_identity)
from s3dgraphy.nodes import DTCDeviceNode

_JSON_CONFIG = (pathlib.Path(__file__).resolve().parents[1]
                / "src" / "s3dgraphy" / "JSON_config")


def _grafo(nodo="res:a", digest="a"):
    doc = {"header": {"format": "em.json", "version": "1.0"},
           "graph": {"graph_id": "g", "nodes": [
               {"id": nodo, "node_type": "resource", "name": "DSC_0001.jpg",
                "data": {"checksum": "sha256:" + digest * 64,
                         "size_bytes": 9012}}], "edges": []}}
    grafo, _ = api.load_emjson(doc)
    report = api.declare_derivation(grafo, nodo, [], process_id="proc:1",
                                    dtc_kind="photogrammetry",
                                    at="2026-09-16T09:00:00Z")
    return grafo, report["process_id"]


# ── H3 · i generi vengono dai dati ──────────────────────────────────────────

def test_H3_l_asse_device_esiste_e_si_legge_dal_VOCABOLARIO():
    """Letto dal JSON, non asserito qui: se un giorno l'asse sparisse, il
    difetto si vedrebbe in questa prova e non in un nodo che rifiuta tutto."""
    from s3dgraphy.utils.utils import get_dtc_kinds

    rules = json.loads((_JSON_CONFIG / "em_visual_rules.json")
                       .read_text(encoding="utf-8"))
    asse = {k for k in rules["dtc_kinds"]["device"] if not k.startswith("_")}
    assert asse == set(get_dtc_kinds()["device"])
    # i sette che il disegno nomina, e nessuno inventato dal codice
    assert asse == {"camera", "sensor", "drone", "computer", "scanner",
                    "total_station", "gnss"}


def test_H3_aggiungerne_uno_resta_UNA_VOCE_JSON(tmp_path, monkeypatch):
    """Nessuna modifica di codice: si scrive nel JSON e il nodo lo accetta.

    Provato spostando il file delle regole, non ragionandoci sopra.
    """
    from s3dgraphy.utils import utils as U

    rules = json.loads((_JSON_CONFIG / "em_visual_rules.json")
                       .read_text(encoding="utf-8"))
    rules["dtc_kinds"]["device"]["georadar"] = {
        "label": "Ground-penetrating radar", "glyph": "11_device_sensor",
        "description": "inventato da questa prova"}
    finto = tmp_path / "em_visual_rules.json"
    finto.write_text(json.dumps(rules), encoding="utf-8")

    monkeypatch.setattr(U, "_load_visual_rules",
                        lambda: json.loads(finto.read_text(encoding="utf-8")))
    assert "georadar" in U.get_dtc_kinds()["device"]

    # …e la classe lo accetta senza che una riga di Python sia cambiata
    monkeypatch.setattr("s3dgraphy.nodes.dtc_device_node.DTC_KINDS",
                        U.get_dtc_kinds())
    nodo = DTCDeviceNode("dev:gpr", name="MALÅ", dtc_kind="georadar")
    assert nodo.data["dtc_kind"] == "georadar"


def test_H3_IL_CONTROESEMPIO_un_genere_inventato_NON_entra():
    """Il vocabolario non si allarga da una chiamata. Se questa prova passasse
    senza sollevare, l'asse sarebbe decorativo."""
    with pytest.raises(ValueError) as caduta:
        DTCDeviceNode("dev:x", name="qualcosa", dtc_kind="macchina_da_scrivere")
    assert "must be one of" in str(caduta.value)
    # …e l'elenco citato nel rifiuto è quello del vocabolario, non uno a mano
    assert "camera" in str(caduta.value)


def test_H3_laserscanner_ha_cambiato_asse_e_NON_chiave():
    """Stava sull'asse `input`. Dal 1.6.22 è una cattura dell'asse `acquisition`
    (decisione di E.D., 30 set) — con la STESSA chiave, perché è la chiave che i
    timbri e i nodi già scritti portano: l'asse in un timbro non c'è. `input`
    resta un alias in lettura delle catture, così chi lo chiede trova ancora
    `laserscanner`. E con l'apparecchio non si confonde: quello è `scanner`."""
    from s3dgraphy.utils.utils import get_dtc_kind_family, get_dtc_kinds

    kinds = get_dtc_kinds()
    assert "laserscanner" in kinds["acquisition"]
    assert get_dtc_kind_family("laserscanner") == "capture"
    assert "laserscanner" in kinds["input"], "l'alias in lettura non risponde"
    assert "laserscanner" not in kinds["device"]
    assert "scanner" in kinds["device"], "l'apparecchio ha la sua voce, distinta"


# ── H4 · l'identità è stabile fra grafi ─────────────────────────────────────

def test_H4_lo_stesso_apparecchio_in_DUE_grafi_ha_lo_STESSO_id():
    """È la ragione per cui il nodo esiste: se «Nikon D850» fosse un nodo
    diverso in ogni studio, «quali rilievi hanno usato quello scanner» non
    risponderebbe niente."""
    uno, proc_uno = _grafo("res:a", "a")
    due, proc_due = _grafo("res:b", "b")
    a = attach_device(uno, proc_uno, make="Nikon", model="D850",
                      serial="3018522", dtc_kind="camera")
    b = attach_device(due, proc_due, make="Nikon", model="D850",
                      serial="3018522", dtc_kind="camera")
    assert a["device_id"] == b["device_id"]
    # …e il grafo NON entra nella chiave: è la differenza voluta rispetto
    # all'id di un'acquisizione, che è un evento di QUESTO studio
    assert "g" not in a["device_id"]


def test_H4_IL_CONTROESEMPIO_due_seriali_diversi_sono_due_apparecchi():
    """Se questo fallisse, l'id starebbe fondendo corpi che il descrittore
    distingue — cioè starebbe buttando via l'informazione che gli era stata
    data, che è peggio di non averla."""
    primo = device_identity(make="Nikon", model="D850", serial="3018522")
    secondo = device_identity(make="Nikon", model="D850", serial="3018523")
    assert primo["id"] != secondo["id"]
    assert primo["distinguishes"] == secondo["distinguishes"] == "serial"


def test_H4_senza_seriale_due_corpi_identici_SI_FONDONO_ed_e_dichiarato():
    """La perdita è reale e va detta, non nascosta: due D850 dello stesso
    dipartimento diventano un nodo solo. `distinguishes` è il modo in cui chi
    legge lo sa senza doverlo dedurre."""
    primo = device_identity(make="Nikon", model="D850")
    secondo = device_identity(make="Nikon", model="D850")
    assert primo["id"] == secondo["id"], "si fondono, ed è il comportamento"
    assert primo["distinguishes"] == "make+model"
    # …e il nodo se lo porta scritto addosso
    grafo, proc = _grafo()
    attach_device(grafo, proc, make="Nikon", model="D850")
    nodo = grafo.find_node_by_id(primo["id"])
    assert nodo.data["distinguishes"] == "make+model"


def test_H4_una_differenza_di_sola_battitura_non_e_una_differenza():
    assert (device_identity(make="Nikon", model="D850")["id"]
            == device_identity(make="  nikon ", model="d850")["id"])


def test_H4_un_apparecchio_senza_nessun_descrittore_non_prende_un_id():
    """Coniarne uno fonderebbe in un nodo solo ogni apparecchio anonimo del
    corpus, che è il difetto opposto e più grave."""
    assert device_identity() is None
    grafo, proc = _grafo()
    with pytest.raises(ValueError) as caduta:
        attach_device(grafo, proc)
    assert "make / model / serial" in str(caduta.value)


def test_H4_attaccarlo_due_volte_non_raddoppia_niente():
    grafo, proc = _grafo()
    primo = attach_device(grafo, proc, make="Nikon", model="D850",
                          dtc_kind="camera")
    secondo = attach_device(grafo, proc, make="Nikon", model="D850",
                            dtc_kind="camera")
    assert primo["created"] is True and primo["attached"] is True
    assert secondo["created"] is False and secondo["attached"] is False
    archi = [e for e in grafo.edges
             if getattr(e, "edge_type", None) == EDGE_HAPPENED_ON_DEVICE]
    assert len(archi) == 1


def test_H4_una_descrizione_piu_POVERA_non_e_una_correzione():
    """Un secondo studio che conosce solo il modello non deve cancellare il
    seriale e il genere che il primo aveva dichiarato."""
    grafo, proc = _grafo()
    ricco = attach_device(grafo, proc, make="Nikon", model="D850",
                          serial="3018522", dtc_kind="camera")
    nodo = grafo.find_node_by_id(ricco["device_id"])
    assert nodo.data["serial"] == "3018522"
    # lo stesso id si ottiene solo ripassando il seriale; con il solo modello è
    # un altro apparecchio (un modello, non un corpo) — e il nodo ricco resta
    povero = attach_device(grafo, proc, make="Nikon", model="D850")
    assert povero["device_id"] != ricco["device_id"]
    assert grafo.find_node_by_id(ricco["device_id"]).data["serial"] == "3018522"


# ── H2 · si attacca al processo, ed è CONTESTO e non catena ─────────────────

def test_H2_l_arco_e_dichiarato_nelle_regole_con_la_sua_ragione():
    regole = json.loads((_JSON_CONFIG / "s3Dgraphy_connections_datamodel.json")
                        .read_text(encoding="utf-8"))
    voce = regole["edge_types"][EDGE_HAPPENED_ON_DEVICE]
    assert voce["mapping"]["cidoc"] == "crmdig:L12_happened_on_device"
    assert voce["allowed_connections"]["source"] == ["DTCNode"]
    assert voce["allowed_connections"]["target"] == ["DTCDeviceNode"]
    # la ragione c'è, e nomina la distinzione che l'arco esiste per tenere
    assert "L10_had_input" in voce["mapping"]["rationale"]
    # …e la cronologia degli allargamenti porta la sua riga, come le altre
    assert "HW1" in regole["description"]


def test_H2_la_risalita_di_provenienza_NON_lo_percorre():
    """Senza scrivere una riga per ottenerlo: l'arco non porta `dtc_role`, e il
    datamodel dice una volta sola quali archi sono catena."""
    from s3dgraphy.dtc.neighbourhood import _chain_edges

    regole = json.loads((_JSON_CONFIG / "s3Dgraphy_connections_datamodel.json")
                        .read_text(encoding="utf-8"))
    assert "dtc_role" not in regole["edge_types"][EDGE_HAPPENED_ON_DEVICE]
    assert EDGE_HAPPENED_ON_DEVICE not in _chain_edges()


def test_H2_IL_CONTROESEMPIO_i_tre_archi_della_catena_SONO_percorsi():
    """Se la prova sopra passasse perché `_chain_edges()` è vuota, non
    direbbe niente."""
    from s3dgraphy.dtc.neighbourhood import _chain_edges

    catena = _chain_edges()
    assert {"dtc_had_input", "dtc_had_output",
            "dtc_derived_from"} <= set(catena)


def test_H2_il_device_NON_e_un_DTCNode():
    """Un nodo DTC è un PASSO; un apparecchio è una cosa del mondo. Ereditare
    l'avrebbe messo nella catena per costruzione."""
    from s3dgraphy.nodes import DTCNode

    assert not issubclass(DTCDeviceNode, DTCNode)


# ── H6 · nel formato: identità e valori ─────────────────────────────────────

def _timbro_con_apparecchio(**kwargs):
    grafo, proc = _grafo()
    attach_device(grafo, proc, **kwargs)
    grafo.find_node_by_id(proc).data["location"] = {
        "lat": 43.1102, "lon": 11.8423, "alt": 412.0,
        "crs": "EPSG:4326", "source": "exif"}
    timbro = api.emit_stamp(grafo, "res:a")
    return grafo, timbro


def test_H6_device_e_un_IDENTITA_e_non_una_stringa():
    _, timbro = _timbro_con_apparecchio(make="Nikon", model="D850",
                                        serial="3018522", dtc_kind="camera")
    device = timbro["how"]["acquisition"]["device"]
    assert isinstance(device, dict)
    assert device["id"].startswith("dev:")
    assert device["label"] == "Nikon D850"
    assert device["make"] == "Nikon" and device["model"] == "D850"
    assert device["distinguishes"] == "serial"


def test_H6_IL_CONTROESEMPIO_una_label_che_RIPETE_l_id_si_omette():
    """La regola già in vigore per le altre etichette del timbro, applicata a
    questa. Il controesempio è la riga sopra: un nome vero sopravvive."""
    grafo, proc = _grafo()
    esito = attach_device(grafo, proc, make="Nikon", model="D850")
    # …qualcuno rinomina il nodo con il proprio id, che è il caso che la regola
    # esiste per intercettare
    grafo.find_node_by_id(esito["device_id"]).name = esito["device_id"]
    timbro = api.emit_stamp(grafo, "res:a")
    device = timbro["how"]["acquisition"]["device"]
    assert device["id"] == esito["device_id"]
    assert "label" not in device


def test_H6_location_porta_VALORI_e_dice_chi_l_ha_detta():
    _, timbro = _timbro_con_apparecchio(make="Nikon", model="D850")
    posizione = timbro["how"]["acquisition"]["location"]
    assert posizione["lat"] == 43.1102 and posizione["lon"] == 11.8423
    assert posizione["crs"] == "EPSG:4326"
    assert posizione["source"] == "exif"


def test_H6_il_blocco_della_posizione_e_CHIUSO_e_non_fa_uscire_ombre_di_nodi():
    """LA PROVA CHE MISURA L'ELENCO, non un esempio.

    La prima versione asseriva che *questa* posizione non contenesse chiavi che
    finiscono in `_id` — e una mutazione che aggiungeva `geo_position_id`
    all'elenco dei campi ammessi la faceva passare lo stesso, perché la fixture
    quella chiave non ce l'aveva. Una prova che può solo passare.

    Qui si misurano due cose vere: che l'elenco ammesso non contenga il nome di
    un nodo, e che un campo NON ammesso venga **buttato dall'emissione** anche
    se qualcuno l'ha scritto sul grafo. È la regola di ammissione del formato —
    entra solo ciò che serve a capire il passo quando il grafo non è
    raggiungibile — resa una misura invece di una promessa.
    """
    from s3dgraphy.stamp.emit import _LOCATION_FIELDS

    assert not [k for k in _LOCATION_FIELDS
                if k == "id" or k.endswith("_id") or "node" in k]

    grafo, proc = _grafo()
    grafo.find_node_by_id(proc).data["location"] = {
        "lat": 43.1, "lon": 11.8, "crs": "EPSG:4326", "source": "exif",
        # l'ombra di un nodo, scritta sul grafo da qualcuno in buona fede
        "geo_position_id": "geo_g", "part_of": "site:aiano"}
    posizione = api.emit_stamp(grafo, "res:a")["how"]["acquisition"]["location"]
    assert set(posizione) == {"lat", "lon", "crs", "source"}
    assert "geo_position_id" not in posizione, "il grafo è uscito dal timbro"
    assert "part_of" not in posizione


def test_H6_stated_e_exif_sono_due_statuti_diversi():
    from s3dgraphy.stamp.emit import LOCATION_SOURCES

    assert set(LOCATION_SOURCES) == {"exif", "stated"}
    grafo, proc = _grafo()
    grafo.find_node_by_id(proc).data["location"] = {
        "lat": 43.1, "lon": 11.8, "crs": "EPSG:4326", "source": "stated"}
    timbro = api.emit_stamp(grafo, "res:a")
    assert timbro["how"]["acquisition"]["location"]["source"] == "stated"


def test_H6_il_giro_completo_riporta_corpo_e_luogo_UGUALI():
    """Grafo → timbro → grafo → timbro. Se il ritorno non fosse identico, il
    campo sarebbe utile una volta sola."""
    _, timbro = _timbro_con_apparecchio(make="Nikon", model="D850",
                                        serial="3018522", dtc_kind="camera")
    pulito = {k: v for k, v in timbro.items() if not k.startswith("_")}

    altro, _ = api.load_emjson({"header": {"format": "em.json", "version": "1.0"},
                                "graph": {"graph_id": "h", "nodes": [],
                                          "edges": []}})
    api.absorb_stamp(altro, pulito)

    # il corpo è tornato a essere un NODO TIPIZZATO, con il suo arco
    apparecchi = [n for n in altro.nodes
                  if getattr(n, "node_type", None) == "dtc_device"]
    assert len(apparecchi) == 1
    assert apparecchi[0].data["make"] == "Nikon"
    assert any(getattr(e, "edge_type", None) == EDGE_HAPPENED_ON_DEVICE
               for e in altro.edges)

    riemesso = api.emit_stamp(altro, "res:a")["how"]["acquisition"]
    assert riemesso["device"] == pulito["how"]["acquisition"]["device"]
    assert riemesso["location"] == pulito["how"]["acquisition"]["location"]


def test_H6_un_timbro_VECCHIO_col_device_come_stringa_non_si_rompe():
    """Quelli emessi prima di stanotte. Non nasce nessun nodo — coniare un id
    per una stringa vorrebbe dire inventare un apparecchio che nessuno ha
    dichiarato — e il riassorbimento non cade."""
    vecchio = {
        "stamp": 1,
        "self": {"resource_id": "res:a", "digest": "sha256:" + "a" * 64},
        "from": [],
        "how": {"process_id": "proc:1", "dtc_kind": "photogrammetry",
                "acquisition": {"device": "Nikon D850", "lens": "24mm"}},
    }
    grafo, _ = api.load_emjson({"header": {"format": "em.json", "version": "1.0"},
                                "graph": {"graph_id": "h", "nodes": [],
                                          "edges": []}})
    api.absorb_stamp(grafo, vecchio)
    assert not [n for n in grafo.nodes
                if getattr(n, "node_type", None) == "dtc_device"]


def test_H6_un_genere_sconosciuto_in_arrivo_non_allarga_il_vocabolario():
    """Un timbro di qualcun altro non decide quali apparecchi esistono — e non
    decide nemmeno se il proprio timbro sia leggibile: il nodo nasce senza
    genere e il resto del descrittore arriva lo stesso."""
    from s3dgraphy.utils.utils import get_dtc_kinds

    forestiero = {
        "stamp": 1,
        "self": {"resource_id": "res:a", "digest": "sha256:" + "a" * 64},
        "from": [],
        "how": {"process_id": "proc:1", "dtc_kind": "photogrammetry",
                "acquisition": {"device": {"id": "dev:forestiero",
                                           "label": "Apparecchio X",
                                           "make": "Acme",
                                           "dtc_kind": "teletrasporto"}}},
    }
    grafo, _ = api.load_emjson({"header": {"format": "em.json", "version": "1.0"},
                                "graph": {"graph_id": "h", "nodes": [],
                                          "edges": []}})
    api.absorb_stamp(grafo, forestiero)
    nodo = grafo.find_node_by_id("dev:forestiero")
    assert nodo is not None
    assert nodo.data.get("make") == "Acme"
    assert "dtc_kind" not in nodo.data
    assert "teletrasporto" not in get_dtc_kinds()["device"]

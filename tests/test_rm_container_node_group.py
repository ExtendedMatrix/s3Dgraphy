"""L'RM Container come nodo di gruppo del grafo (EM16-RMNG).

════════════════════════════════════════════════════════════════════════════════
## PERCHÉ ESISTE

Un RM Container raggruppa più modelli sotto un unico Document — «Survey 2015»
sotto D.01, «Reconstruction» sotto D.09. Fino al 10-09-2026 il container viveva
SOLO come PropertyGroup di Blender (`scene.rm_containers`): il raggruppamento
che dà senso all'insieme era invisibile a chiunque leggesse il grafo.

## LA REGOLA CHE GOVERNA TUTTO, E LA PROVA CHE LA RECINTA

**Il gruppo si affianca, non sostituisce.** Ogni RM conserva i suoi archi verso
l'epoca esattamente come prima; il Document conserva gli archi DIRETTI verso
ogni modello. Il gruppo si aggiunge sopra e non si mette mai in mezzo.

`test_INTRODURRE_IL_GRUPPO_non_tocca_un_solo_arco_epoca_RM` è la prova che
recinta quella frase, ed è scritta in modo ESPLICITO e non implicito: si
fotografa l'insieme degli archi prima, si introduce il gruppo, si confronta.

## COSA NON È PROVATO QUI, E PERCHÉ

Il round-trip **GraphML** non c'è, e non è una dimenticanza: i
RepresentationModelNode non entrano nel GraphML, per decisione dichiarata nel
codice stesso —

    exporter/graphml/graphml_patcher.py:85
    # Node types that should not be exported to GraphML (internal to s3dgraphy)
    INTERNAL_NODE_TYPES = {..., 'representation_model',
                           'representation_model_doc',
                           'representation_model_special_find', ...}

    exporter/graphml/graphml_patcher.py:77
    # Representation/scene-data edges — auxiliary, not formal EM in GraphML
    'has_representation_model', ...

Misurato eseguendo: un grafo con un Document e un RM, esportato in GraphML,
produce un file che non contiene il nome del modello. Mettere un BOX di gruppo
in un file dove i membri non possono esistere sarebbe un box che promette un
contenuto che il file non ha — quindi non è stato fatto, e la questione è nel
report. Vedi `test_IL_GRAPHML_NON_PORTA_GLI_RM_ed_e_dichiarato`, che recinta la
premessa: se un giorno gli RM entrassero nel GraphML, quella prova diventa
rossa ed è il momento di rifare questa scelta.
"""

import json

import pytest

from s3dgraphy.graph import Graph
from s3dgraphy.nodes.group_node import (
    GroupNode, RepresentationModelNodeGroup, ActivityNodeGroup,
    ParadataNodeGroup, TimeBranchNodeGroup, LocationNodeGroup,
)
from s3dgraphy.nodes.base_node import Node
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.representation_node import (
    RepresentationModelNode, RepresentationModelDocNode,
    RepresentationModelSpecialFindNode,
)
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.importer.emjson_importer import parse_emjson

MEMBERSHIP = "is_in_representation_model_group"
DOC_EDGE = "has_representation_model"


def _archi(g):
    """L'insieme degli archi, come terne confrontabili."""
    return {(e.edge_source, e.edge_target, e.edge_type) for e in g.edges}


def _fixture_prima_del_gruppo():
    """Un grafo come quelli di oggi: un'epoca, un Document, tre RM appesi.

    Esattamente la forma che EM Tools 1.6 scrive già — compreso il dettaglio
    del commit `c46b365`: `has_representation_model` porta ANCHE l'arco
    Documento→RM, e non solo Epoca→RM.
    """
    g = Graph(graph_id="rmg")
    g.add_node(EpochNode("EP1", "Roman", -27, 476))
    g.add_node(EpochNode("EP2", "Late", 476, 800))
    g.add_node(DocumentNode("D01", "D.01"))
    for i in (1, 2, 3):
        g.add_node(RepresentationModelNode(f"rm{i}", f"mesh_0{i}"))
        # gli archi d'epoca di OGNI singolo RM, da entrambi i capi come li
        # cerca `rm_manager/epoch_edges.py`
        g.add_edge(f"fe{i}", f"rm{i}", "EP1", "has_first_epoch")
        g.add_edge(f"se{i}", f"rm{i}", "EP2", "survive_in_epoch")
        g.add_edge(f"ep{i}", "EP1", f"rm{i}", DOC_EDGE)
        # …e l'arco documentale diretto
        g.add_edge(f"dr{i}", "D01", f"rm{i}", DOC_EDGE)
    return g


# ═══ 1 · LA CLASSE, COME LE SORELLE ══════════════════════════════════════════

def test_LA_CLASSE_e_una_sorella_a_tutti_gli_effetti():
    assert issubclass(RepresentationModelNodeGroup, GroupNode)
    assert RepresentationModelNodeGroup.node_type == "RepresentationModelNodeGroup"
    #: la stessa firma delle sorelle, verificata eseguendola
    for cls in (ActivityNodeGroup, ParadataNodeGroup, TimeBranchNodeGroup,
                RepresentationModelNodeGroup):
        n = cls("id1", "etichetta", description="d", y_pos=12.5)
        assert n.node_id == "id1" and n.name == "etichetta"
        assert n.description == "d"
        assert n.attributes["y_pos"] == 12.5


def test_E_SI_REGISTRA_DA_SE_nel_node_type_map():
    """È ciò che rende gratuito il round-trip em.json: `__init_subclass__` in
    `base_node.py` registra ogni sottoclasse per `node_type`."""
    assert (Node.node_type_map["RepresentationModelNodeGroup"]
            is RepresentationModelNodeGroup)


def test_ED_E_ESPORTATA_dai_due_punti_di_ingresso():
    import s3dgraphy
    from s3dgraphy.nodes import RepresentationModelNodeGroup as dai_nodi
    assert dai_nodi is RepresentationModelNodeGroup
    assert "RepresentationModelNodeGroup" in s3dgraphy.__all__


# ═══ 2 · LA PROPRIETÀ CHIAVE · SI AFFIANCA, NON SOSTITUISCE ══════════════════

def test_INTRODURRE_IL_GRUPPO_non_tocca_un_solo_arco_epoca_RM():
    """LA prova di questo lavoro, e dice la regola invece di elencare i casi.

    Esplicita e non implicita: si fotografa l'insieme degli archi PRIMA, si
    introduce il gruppo con i suoi membri e il suo Document, e si confronta.
    Nessun arco preesistente può essere sparito o cambiato.
    """
    g = _fixture_prima_del_gruppo()
    prima = _archi(g)
    assert len(prima) == 12, prima            # 3 RM × 4 archi

    #: ora il gruppo, popolato e collegato al Document
    g.add_node(RepresentationModelNodeGroup("GRP", "Survey 2015"))
    for i in (1, 2, 3):
        g.add_edge(f"m{i}", f"rm{i}", "GRP", MEMBERSHIP)
    g.add_edge("dg", "D01", "GRP", DOC_EDGE)

    dopo = _archi(g)
    #: NIENTE è stato rimosso né modificato
    assert prima <= dopo, f"archi sparsi o cambiati: {prima - dopo}"
    #: …e ciò che è stato aggiunto è SOLO il gruppo
    aggiunti = dopo - prima
    assert aggiunti == {
        ("rm1", "GRP", MEMBERSHIP), ("rm2", "GRP", MEMBERSHIP),
        ("rm3", "GRP", MEMBERSHIP), ("D01", "GRP", DOC_EDGE),
    }, aggiunti

    #: e la verifica dal punto di vista che conta per l'utente: le epoche di
    #: OGNI singolo RM sono esattamente quelle di prima
    for i in (1, 2, 3):
        fe = {e.edge_target for e in g.edges
              if e.edge_source == f"rm{i}" and e.edge_type == "has_first_epoch"}
        se = {e.edge_target for e in g.edges
              if e.edge_source == f"rm{i}" and e.edge_type == "survive_in_epoch"}
        assert fe == {"EP1"} and se == {"EP2"}


def test_E_IL_DOCUMENTO_conserva_gli_archi_DIRETTI_verso_ogni_modello():
    """Il dettaglio del commit c46b365: `has_representation_model` porta anche
    il legame Documento→RM, e quel legame deve sopravvivere al gruppo."""
    g = _fixture_prima_del_gruppo()
    g.add_node(RepresentationModelNodeGroup("GRP", "Survey 2015"))
    for i in (1, 2, 3):
        g.add_edge(f"m{i}", f"rm{i}", "GRP", MEMBERSHIP)
    g.add_edge("dg", "D01", "GRP", DOC_EDGE)

    diretti = {e.edge_target for e in g.edges
               if e.edge_source == "D01" and e.edge_type == DOC_EDGE}
    assert diretti == {"rm1", "rm2", "rm3", "GRP"}, (
        "il Document deve puntare ai singoli modelli E al gruppo: il gruppo si "
        "affianca, non si mette in mezzo")


# ═══ 3 · L'ARCO DI APPARTENENZA, SULLA CONVENZIONE ESISTENTE ═════════════════

def test_L_ARCO_E_REGISTRATO_e_non_degrada_a_generic_connection():
    """`Graph.add_edge` declassa in SILENZIO un tipo che non conosce a
    `generic_connection` — misurato. Quindi «registrato nel datamodel» non è
    burocrazia: è la differenza fra un'appartenenza e un arco generico."""
    g = Graph(graph_id="t")
    g.add_node(RepresentationModelNodeGroup("GRP", "S"))
    g.add_node(RepresentationModelNode("rm1", "m"))
    e = g.add_edge("e1", "rm1", "GRP", MEMBERSHIP)
    assert e.edge_type == MEMBERSHIP, (
        "declassato: l'edge type non è nel connections datamodel")


def test_E_STA_NELLA_FAMIGLIA_is_in_():
    """Si riusa la convenzione, non si inventa: l'appartenenza a un node group
    si scrive `is_in_<gruppo>`, dal membro verso il gruppo."""
    from s3dgraphy.edges.connections_loader import get_connections_datamodel
    dm = get_connections_datamodel()
    famiglia = sorted(k for k in dm.get_all_edge_names()
                      if k.startswith("is_in_"))
    assert MEMBERSHIP in famiglia, famiglia
    #: le cinque sorelle c'erano prima: la sesta segue lo stesso stampo
    for sorella in ("is_in_activity", "is_in_location", "is_in_timebranch",
                    "is_in_paradata_nodegroup", "is_in_functional_unit"):
        assert sorella in famiglia
    #: …e le direzioni sono quelle della convenzione: membro → gruppo
    assert "RepresentationModelNodeGroup" in dm.get_allowed_targets(MEMBERSHIP)
    assert "RepresentationModelNode" in dm.get_allowed_sources(MEMBERSHIP)
    #: …e il Document può puntare ANCHE al gruppo, senza perdere i modelli
    bersagli = dm.get_allowed_targets(DOC_EDGE)
    assert {"RepresentationModelNode", "RepresentationModelNodeGroup"} <= set(bersagli)


@pytest.mark.parametrize("cls,nome", [
    (RepresentationModelNode, "rm"),
    (RepresentationModelDocNode, "rmdoc"),
    (RepresentationModelSpecialFindNode, "rmsf"),
])
def test_OGNI_CLASSE_DELLA_FAMIGLIA_RM_puo_essere_membro(cls, nome):
    g = Graph(graph_id="t")
    g.add_node(RepresentationModelNodeGroup("GRP", "S"))
    g.add_node(cls(nome, nome))
    e = g.add_edge("e", nome, "GRP", MEMBERSHIP)
    assert e.edge_type == MEMBERSHIP, f"{cls.__name__} rifiutato come membro"


def test_UNA_MESH_STA_IN_UN_SOLO_GRUPPO():
    """1:1 e non m:n — la regola già in vigore lato Blender, dove `mesh_names`
    è autoritativo. L'accessore è SINGOLARE di proposito: restituire una lista
    inviterebbe chi chiama a gestire un caso che il modello vieta."""
    g = Graph(graph_id="t")
    g.add_node(RepresentationModelNodeGroup("A", "Survey"))
    g.add_node(RepresentationModelNodeGroup("B", "Reconstruction"))
    g.add_node(RepresentationModelNode("rm1", "mesh_01"))
    g.add_edge("e1", "rm1", "A", MEMBERSHIP)
    assert g.get_representation_model_group_of("rm1").node_id == "A"
    #: e l'accessore resta singolare anche in un grafo anomalo (file editato a
    #: mano, merge): ritorna il primo e NON riconcilia in silenzio
    g.add_edge("e2", "rm1", "B", MEMBERSHIP)
    scelto = g.get_representation_model_group_of("rm1")
    assert scelto is not None and scelto.node_id in ("A", "B")


# ═══ 4 · GLI STATI LEGALI · VUOTO, E SENZA DOCUMENT ══════════════════════════

def test_UN_GRUPPO_VUOTO_e_legale():
    g = Graph(graph_id="t")
    g.add_node(RepresentationModelNodeGroup("GRP", "appena creato"))
    assert g.get_representation_model_group_members("GRP") == []
    assert [n.node_id for n in g.get_representation_model_groups()] == ["GRP"]


def test_UN_GRUPPO_SENZA_DOCUMENT_e_legale():
    """Lo stato «grigio» che la UI già mostra, e che deve essere
    rappresentabile anche nel grafo."""
    g = Graph(graph_id="t")
    g.add_node(RepresentationModelNodeGroup("GRP", "Survey 2015"))
    g.add_node(RepresentationModelNode("rm1", "mesh_01"))
    g.add_edge("e1", "rm1", "GRP", MEMBERSHIP)
    verso_il_gruppo = [e for e in g.edges
                       if e.edge_target == "GRP" and e.edge_type == DOC_EDGE]
    assert verso_il_gruppo == []
    assert len(g.get_representation_model_group_members("GRP")) == 1


# ═══ 5 · ROUND-TRIP em.json ══════════════════════════════════════════════════

def _giro(g):
    doc = build_emjson(g)
    tornato, avvisi = parse_emjson(json.loads(json.dumps(doc)))
    return tornato, avvisi


def test_ROUND_TRIP_EMJSON_gruppo_popolato():
    g = _fixture_prima_del_gruppo()
    g.add_node(RepresentationModelNodeGroup("GRP", "Survey 2015",
                                            description="il rilievo del 2015"))
    for i in (1, 2, 3):
        g.add_edge(f"m{i}", f"rm{i}", "GRP", MEMBERSHIP)
    g.add_edge("dg", "D01", "GRP", DOC_EDGE)

    tornato, avvisi = _giro(g)
    assert not [a for a in avvisi if "RepresentationModelNodeGroup" in a], avvisi

    grp = tornato.find_node_by_id("GRP")
    assert grp is not None
    assert type(grp) is RepresentationModelNodeGroup, type(grp)
    assert grp.name == "Survey 2015"
    assert grp.description == "il rilievo del 2015"
    #: e il grafo è isomorfo sugli archi
    assert _archi(tornato) == _archi(g)
    assert sorted(n.name for n in
                  tornato.get_representation_model_group_members("GRP")) == \
        ["mesh_01", "mesh_02", "mesh_03"]


def test_ROUND_TRIP_EMJSON_gruppo_vuoto():
    g = Graph(graph_id="t")
    g.add_node(RepresentationModelNodeGroup("GRP", "appena creato"))
    tornato, _ = _giro(g)
    grp = tornato.find_node_by_id("GRP")
    assert type(grp) is RepresentationModelNodeGroup
    assert tornato.get_representation_model_group_members("GRP") == []


def test_ROUND_TRIP_EMJSON_gruppo_senza_document():
    g = Graph(graph_id="t")
    g.add_node(RepresentationModelNodeGroup("GRP", "Survey 2015"))
    g.add_node(RepresentationModelNode("rm1", "mesh_01"))
    g.add_edge("e1", "rm1", "GRP", MEMBERSHIP)
    tornato, _ = _giro(g)
    assert _archi(tornato) == {("rm1", "GRP", MEMBERSHIP)}
    assert type(tornato.find_node_by_id("GRP")) is RepresentationModelNodeGroup


def test_ROUND_TRIP_EMJSON_non_perde_gli_archi_d_epoca():
    """La proprietà chiave, ripetuta ATTRAVERSO la serializzazione: non basta
    che il grafo in memoria li conservi, devono sopravvivere al giro."""
    g = _fixture_prima_del_gruppo()
    prima = _archi(g)
    g.add_node(RepresentationModelNodeGroup("GRP", "Survey 2015"))
    for i in (1, 2, 3):
        g.add_edge(f"m{i}", f"rm{i}", "GRP", MEMBERSHIP)
    tornato, _ = _giro(g)
    assert prima <= _archi(tornato), f"persi nel giro: {prima - _archi(tornato)}"


def test_UN_EMJSON_LEGACY_SENZA_GRUPPI_si_apre_senza_errori():
    """Additivo puro: un documento scritto prima che questa classe esistesse
    non deve accorgersi di niente."""
    g = _fixture_prima_del_gruppo()
    doc = build_emjson(g)
    #: la forma è {header, graph}, misurata — non {nodes}
    nodi = doc["graph"]["nodes"]
    #: nessun gruppo dentro, per costruzione
    assert not [n for n in nodi
                if n.get("type") == "RepresentationModelNodeGroup"]
    tornato, avvisi = parse_emjson(json.loads(json.dumps(doc)))
    assert not [a for a in avvisi if "unknown node_type" in a], avvisi
    assert _archi(tornato) == _archi(g)
    assert tornato.get_representation_model_groups() == []


# ═══ 6 · L'EXPORT HERIVERSE NON LO LASCIA CADERE ═════════════════════════════

def test_L_EXPORT_HERIVERSE_scrive_il_gruppo_nel_suo_secchiello():
    """Aggiunto per la ragione per cui fu aggiunto quello di LocationNodeGroup:
    senza un ramo suo il nodo cade in fondo alla catena `elif` e viene
    SILENZIOSAMENTE scartato dall'export."""
    from s3dgraphy.exporter.json_exporter import JSONExporter
    g = Graph(graph_id="t")
    g.add_node(RepresentationModelNodeGroup("GRP", "Survey 2015"))
    g.add_node(RepresentationModelNodeGroup("VUOTO", "Reconstruction"))
    g.add_node(RepresentationModelNode("rm1", "mesh_01"))
    g.add_node(DocumentNode("D01", "D.01"))
    g.add_edge("e1", "rm1", "GRP", MEMBERSHIP)
    g.add_edge("e2", "D01", "GRP", DOC_EDGE)

    reso = JSONExporter("/dev/null")._process_graph(g)
    gruppi = reso["nodes"]["representation_model_groups"]
    assert set(gruppi) == {"GRP", "VUOTO"}, gruppi
    assert gruppi["GRP"]["name"] == "Survey 2015"
    #: …e i modelli restano dove stavano
    assert set(reso["nodes"]["representation_models"]) == {"rm1"}
    #: …e i due archi ci sono
    assert [(e["from"], e["to"]) for e in reso["edges"][MEMBERSHIP]] == [("rm1", "GRP")]


# ═══ 7 · LE REGOLE VISIVE ════════════════════════════════════════════════════

def _regole():
    import pathlib
    import s3dgraphy
    p = (pathlib.Path(s3dgraphy.__file__).parent / "JSON_config"
         / "em_visual_rules.json")
    return json.loads(p.read_text())


def test_LO_STILE_C_E_ed_e_quello_della_famiglia_gruppo():
    r = _regole()
    s = r["node_styles"]["RepresentationModelNodeGroup"]["style"]
    #: la FORMA è quella dei gruppi, non una nuova — il vincolo del prompt
    for sorella in ("ActivityNodeGroup", "ParadataNodeGroup",
                    "TimeBranchNodeGroup"):
        ss = r["node_styles"][sorella]["style"]
        for chiave in ("shape", "fill_color", "border_color", "border_style",
                       "label_position"):
            assert s[chiave] == ss[chiave], (
                f"{chiave} diverso da {sorella}: la forma dei gruppi non si "
                f"reinventa, cambia solo la linguetta")
    #: …e ciò che distingue è la linguetta, che nessun altro stile usa
    altri = [k for k, v in r["node_styles"].items()
             if k != "RepresentationModelNodeGroup"
             and (v.get("style") or {}).get("label_background") == s["label_background"]]
    assert altri == [], f"linguetta in collisione con {altri}"


def test_E_LA_VERSIONE_E_STATA_BUMPATA_con_la_sua_riga_di_changelog():
    r = _regole()
    # «almeno», non «uguale»: la versione continua a salire (1.6.18 = 2d_glyphs)
    # e ciò che questa prova difende è la riga di 1.6.17, non l'ultimo numero
    assert tuple(map(int, r["version"].split("."))) >= (1, 6, 17), r["version"]
    cl = r["_changelog"]
    riga = cl["1.6.17"] if isinstance(cl, dict) else str(cl[-1])
    assert "RepresentationModelNodeGroup" in riga
    assert "EM16-RMNG" in riga


def test_E_L_ARCO_HA_IL_SUO_STILE():
    r = _regole()
    assert MEMBERSHIP in r["edge_style"]


# ═══ 8 · LA PREMESSA CHE HA FERMATO IL GRAPHML ═══════════════════════════════

def test_IL_GRAPHML_NON_PORTA_GLI_RM_ed_e_dichiarato():
    """Questa prova RECINTA una premessa, non un comportamento desiderato.

    Il round-trip GraphML che il prompt chiedeva non è stato fatto perché i
    RepresentationModelNode non entrano nel GraphML — decisione DICHIARATA nel
    codice. Se un giorno gli RM entrassero, questa prova diventa rossa: è il
    segnale che la scelta di non emettere il gruppo va rifatta.
    """
    from s3dgraphy.exporter.graphml.graphml_patcher import (
        INTERNAL_NODE_TYPES, STRUCTURAL_EDGE_TYPES)
    for t in ("representation_model", "representation_model_doc",
              "representation_model_special_find"):
        assert t in INTERNAL_NODE_TYPES, (
            f"{t} non è più escluso dal GraphML: rileggi la scelta di EM16-RMNG")
    assert DOC_EDGE in STRUCTURAL_EDGE_TYPES


def test_E_MISURATO_ESEGUENDO_un_RM_non_arriva_nel_graphml(tmp_path):
    """Non solo la costante: la cosa. Un grafo con un RM esportato in GraphML
    non contiene il nome del modello."""
    from s3dgraphy.exporter.graphml.graphml_exporter import GraphMLExporter
    g = Graph(graph_id="t")
    g.add_node(DocumentNode("D01", "D.01"))
    g.add_node(RepresentationModelNode("rm1", "mesh_unica_01"))
    g.add_edge("e", "D01", "rm1", DOC_EDGE)
    out = tmp_path / "t.graphml"
    GraphMLExporter(g).export(str(out))
    assert out.is_file()
    assert "mesh_unica_01" not in out.read_text(), (
        "gli RM ADESSO arrivano nel GraphML: la scelta di non emettere il "
        "gruppo di gruppo va rifatta, e con essa il round-trip che il prompt "
        "chiedeva")


# ═══ 9 · IL NODE DATAMODEL · IL FILE DIMENTICATO CHE BLENDER LEGGE ═══════════

def test_LA_VOCE_NEL_NODE_DATAMODEL_c_e():
    """Questo file l'avevo dimenticato, e l'ho trovato misurando in Blender.

    Il Graph Editor di EM Tools NON genera le sue classi di nodo dalle classi
    Python: le genera da `s3Dgraphy_node_datamodel.json`, categoria
    `group_nodes` (`graph_editor/dynamic_nodes.py::get_all_node_types_from_datamodel`).
    Senza una voce là il gruppo esiste nel grafo e **non si disegna**: nessun
    errore, nessun avviso, semplicemente un nodo che `populate_tree` salta.

    Verificato in un Blender vero dopo la vendorizzazione: la classe generata è
    `EMGraphRepresentationModelNodeGroupNodeType`, etichetta «RM Container».
    """
    import pathlib
    import s3dgraphy
    p = (pathlib.Path(s3dgraphy.__file__).parent / "JSON_config"
         / "s3Dgraphy_node_datamodel.json")
    d = json.loads(p.read_text())
    sub = d["group_nodes"]["GroupNode"]["subtypes"]
    assert "RepresentationModelNodeGroup" in sub, (
        "senza questa voce il gruppo non si disegna nel Graph Editor di EM Tools")
    voce = sub["RepresentationModelNodeGroup"]
    #: la stessa forma delle sorelle, chiave per chiave
    sorella = sub["FunctionalUnitNodeGroup"]
    for chiave in ("class", "parent", "abbreviation", "label", "description",
                   "s3Dgraphy_file", "mapping", "em_extension", "properties"):
        assert chiave in voce, f"manca {chiave}, che {sorella['class']} ha"
    assert voce["parent"] == "GroupNode"
    assert voce["class"] == "RepresentationModelNodeGroup"
    #: …e la versione è stata bumpata. Confronto >=, non ==: questa voce è
    #: entrata in 1.6.7 e ci resta, mentre il numero si muove per ogni altra
    #: ragione (1.6.8: SF/RSF, redeposited vs repositioned). Un == qui fa
    #: fallire un test sul nodo per un motivo che col nodo non c'entra.
    _ver = tuple(int(x) for x in d["s3Dgraphy_data_model_version"].split("."))
    assert _ver >= (1, 6, 7), d["s3Dgraphy_data_model_version"]


def test_E_IL_MAPPING_TIENE_la_classe_del_genitore_con_la_sua_ragione():
    """L'unico sottotipo di gruppo che NON sovrascrive la classe del genitore,
    e la ragione è scritta: un container RM È un insieme curatoriale — ciò che
    qualcuno ha raccolto e pubblicato sotto un documento.

    Dal 21 set 2026 quella classe non è più E78 Collection, che CIDOC CRM 7.1.3
    non dichiara più (rinominata E78_Curated_Holding, e fisica): il genitore
    porta E73 Information Object. Ciò che questo test difende non è il nome
    della classe ma l'invariante — il container NON sovrascrive il genitore —
    quindi si asserisce l'uguaglianza fra i due, non una costante.
    """
    import pathlib
    import s3dgraphy
    d = json.loads((pathlib.Path(s3dgraphy.__file__).parent / "JSON_config"
                    / "s3Dgraphy_node_datamodel.json").read_text())
    sub = d["group_nodes"]["GroupNode"]["subtypes"]
    voce = sub["RepresentationModelNodeGroup"]
    genitore = d["group_nodes"]["GroupNode"]
    assert voce["mapping"]["cidoc"] == genitore["mapping"]["cidoc"]
    #: …e non è più la classe morta: E78 Collection non esiste in CRM 7.1.3
    assert "E78" not in voce["mapping"]["cidoc"]
    assert genitore["mapping"]["cidoc"] == "E73 Information Object"
    #: …e la ragione nomina il caso da cui si distingue
    r = voce["mapping"]["rationale"]
    assert "FunctionalUnitNodeGroup" in r and "E24" in r
    #: …e dichiara che D3 resta aperta
    assert "D3" in r and "digital representation of" in r


def test_E_IL_SIDECAR_DELLE_TRADUZIONI_e_in_sync():
    """Un altro file che tocca le sorelle: `datamodel_translations.json`.
    L'inglese è la sorgente e il tool lo semina — qui si verifica che sia
    stato seminato, perché `--check` è già un test del ramo e diventerebbe
    rosso la prossima volta."""
    from s3dgraphy.tools import datamodel_i18n as t
    assert t.check() == 0
    doc = json.loads(t.TRANSLATIONS.read_text())
    assert "RepresentationModelNodeGroup" in doc["entries"]
    assert doc["entries"]["RepresentationModelNodeGroup"]["label"]["en"] == \
        "RM Container"

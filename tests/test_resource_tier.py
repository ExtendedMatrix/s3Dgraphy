"""R1 · `tier`, l'impacchettamento e le misure — gli assi che rendono una
risorsa SCEGLIIBILE senza un flag per-strumento.

Il principio che questi campi servono: **il grafo dichiara fatti, il
consumatore sceglie per capacità.** Un flag per-strumento sarebbe una
configurazione travestita — andrebbe modificato ogni volta che nasce un
software, e obbligherebbe a rimettere le mani nei grafi già scritti. La risorsa
dice *cosa è* (formato, tier, residenza, impacchettamento, peso) e ogni
consumatore prende ciò che sa aprire.

Quattro cose sono difese qui, e ognuna per un modo preciso in cui il dato
potrebbe mentire:

* **`tier` è una COPPIA, non una scala.** Una catena può contenere più master
  (l'originale fotogrammetrico su disco esterno *e* la mesh di lavoro nel
  .blend). «Pubblicata» non è un terzo valore: è lo stato di una distribution.
* **`role` non è il posto per questo** e non si tocca: è già
  `comparandum`/`internal_source` per decisione di E.D. del 24-08-2026.
* **L'impacchettamento si dichiara, non si indovina.** Un tileset viaggia come
  zip; leggerlo dall'estensione funziona finché qualcuno non serve un archivio
  senza `.zip` nel nome, e allora fallisce in silenzio.
* **Le misure sono fatti, non un'enumerazione di livelli.** `lod0/lod1/lod2`
  invecchia il giorno che qualcuno aggiunge un livello in mezzo; un peso e un
  conteggio no.
"""

import json

import pytest

from s3dgraphy.graph import Graph
from s3dgraphy.nodes.resource_node import ResourceNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit


# ── gli assi, e il rifiuto dei valori inventati ─────────────────────────────

def test_i_due_tier_vengono_dalla_classe_che_li_valida():
    assert ResourceNode.TIERS == ("master", "distribution")
    assert ResourceNode.PACKAGINGS == ("file", "directory", "archive",
                                       "file_set", "datablock")


@pytest.mark.parametrize("inventato", ["intermedio", "published", "lod1", "", None])
def test_un_tier_inventato_e_rifiutato_invece_che_tenuto(inventato):
    """Un terzo tier a un call site sarebbe una parola che nessun filtro può
    mai incontrare — la stessa ragione per cui `scope`, `residency` e `role`
    sollevano."""
    r = ResourceNode("x")
    with pytest.raises(ValueError) as exc:
        r.set_tier(inventato)
    assert "master" in str(exc.value) and "distribution" in str(exc.value)


@pytest.mark.parametrize("inventato", ["zip", "folder", "tar", ""])
def test_un_impacchettamento_inventato_e_rifiutato(inventato):
    with pytest.raises(ValueError):
        ResourceNode("x").set_packaging(inventato)


def test_published_NON_e_un_tier():
    """È lo stato di una distribution — locator raggiungibile più checksum —
    non una terza casella. Un terzo valore avrebbe reso la pubblicazione una
    proprietà dei byte invece che di dove sono arrivati."""
    assert "published" not in ResourceNode.TIERS
    pubblicata = ResourceNode("p", url="https://x/y.glb",
                              checksum="sha256:aa", tier="distribution")
    assert pubblicata.tier() == "distribution"
    assert pubblicata.data.get("checksum")


def test_il_role_non_e_stato_toccato():
    """Decisione di E.D. del 24-08-2026, e la docstring di `ROLES` dice che un
    terzo valore inventato a un call site sarebbe «una parola»."""
    assert ResourceNode.ROLES == ("comparandum", "internal_source")
    r = ResourceNode("x", tier="master", role="internal_source")
    assert r.role() == "internal_source" and r.tier() == "master"


def test_una_catena_puo_avere_PIU_master():
    """Non è una scala a tre gradini: è un ruolo in una coppia.

    L'originale fotogrammetrico su un disco esterno e la mesh di lavoro dentro
    il .blend sono **tutti e due** master, legati da una derivazione. Chiedere
    «su che gradino sta questo» non ha risposta; chiedere «è la fonte o la cosa
    fatta da lei» ce l'ha sempre.
    """
    originale = ResourceNode("orig", url="/Volumi/esterno/rilievo.obj",
                             tier="master")
    lavoro = ResourceNode("lav", url="blend://rilievo.blend#Object/muro",
                          tier="master")
    servita = ResourceNode("serv", url="models/muro.glb", tier="distribution")
    assert [n.tier() for n in (originale, lavoro, servita)] == \
        ["master", "master", "distribution"]


# ── le letture, e perché ce n'è una per il tier e non per il role ───────────

def test_una_risorsa_senza_tier_non_lo_dichiara_ma_si_puo_LEGGERE():
    muta = ResourceNode("m", url="models/a.gltf")
    assert muta.tier() is None, "il documento non dichiara niente"
    assert muta.effective_tier() == "distribution", "…ma il consumatore legge"
    assert "tier" not in muta.data, "e la lettura non si scrive nel dato"


def test_la_lettura_del_tier_mette_i_blend_fra_i_master():
    """Quei byte esistono perché Blender ci rifaccia sopra le cose, e nessun
    viewer li può servire."""
    dentro = ResourceNode("d", url="blend://studio.blend#Object/muro")
    assert dentro.effective_tier() == "master"
    #: e una dichiarazione esplicita vince sulla lettura, sempre
    dentro.set_tier("distribution")
    assert dentro.effective_tier() == "distribution"


def test_non_esiste_una_lettura_del_ROLE_e_e_giusto_cosi():
    """La differenza vale la pena scriverla: un role è una pretesa sull'ARGOMENTO
    di qualcuno, e risponderne una che nessuno ha fatto gli mette parole in
    bocca. Un tier è un fatto sui BYTE che ogni consumatore deve comunque
    decidere prima di aprire qualcosa."""
    muta = ResourceNode("m", url="models/a.gltf")
    assert muta.role() is None
    assert not hasattr(muta, "effective_role")


def test_la_lettura_dell_impacchettamento_e_debole_ed_e_il_punto():
    assert ResourceNode("a", url="tiles.zip").effective_packaging() == "archive"
    assert ResourceNode("b", url="tiles/").effective_packaging() == "directory"
    assert ResourceNode("c", url="m.gltf").effective_packaging() == "file"
    #: un archivio servito senza `.zip` nel nome qui si legge «file», e l'unica
    #: cura è che chi l'ha fatto lo DICA
    bugiardo = ResourceNode("d", url="https://x/servizio/tileset")
    assert bugiardo.effective_packaging() == "file"
    bugiardo.set_packaging("archive")
    assert bugiardo.effective_packaging() == "archive"


# ── le misure ───────────────────────────────────────────────────────────────

def test_le_misure_sono_fatti_e_le_chiavi_non_sono_enumerate():
    mesh = ResourceNode("m", size_bytes=104857,
                        primitives={"vertices": 1200, "faces": 2400})
    nuvola = ResourceNode("n", primitives={"points": 5_000_000})
    tileset = ResourceNode("t", primitives={"tiles": 1843})
    assert mesh.data["size_bytes"] == 104857
    assert nuvola.data["primitives"] == {"points": 5000000}
    assert tileset.data["primitives"] == {"tiles": 1843}


def test_uno_zero_e_una_misura_e_un_assenza_no():
    vuoto = ResourceNode("v", size_bytes=0)
    assert vuoto.data["size_bytes"] == 0
    non_misurato = ResourceNode("nm")
    assert "size_bytes" not in non_misurato.data


@pytest.mark.parametrize("sbagliato", [-1, "grosso", 1.5e400])
def test_un_peso_che_non_e_un_numero_di_byte_e_rifiutato(sbagliato):
    with pytest.raises(ValueError):
        ResourceNode("x").set_measures(size_bytes=sbagliato)


def test_conteggi_negativi_o_non_numerici_sono_rifiutati():
    r = ResourceNode("x")
    with pytest.raises(ValueError):
        r.set_measures(primitives={"faces": -3})
    with pytest.raises(ValueError):
        r.set_measures(primitives={"faces": "molte"})
    with pytest.raises(ValueError):
        r.set_measures(primitives=["faces", 3])


def test_le_misure_distinguono_i_LOD_fratelli_senza_enumerarli():
    """Il caso per cui esistono: due distribuzioni ugualmente valide, e un
    consumatore con un budget di banda che deve sceglierne una."""
    grande = ResourceNode("g", url="models/muro_hi.glb", tier="distribution",
                          size_bytes=52_428_800, primitives={"faces": 1_200_000})
    piccola = ResourceNode("p", url="models/muro_lo.glb", tier="distribution",
                           size_bytes=1_048_576, primitives={"faces": 24_000})
    budget = 8 * 1024 * 1024
    scelte = [n for n in (grande, piccola) if n.data["size_bytes"] <= budget]
    assert [n.node_id for n in scelte] == ["p"]


# ── preferred: un suggerimento, mai un cancello ────────────────────────────

def test_preferred_si_scrive_solo_quando_e_vero():
    """Un `preferred: false` su tutte le altre trasformerebbe un suggerimento
    in un voto, e un suggerimento assente in uno negativo."""
    suggerita = ResourceNode("s", preferred=True)
    assert suggerita.data["preferred"] is True and suggerita.is_preferred()
    normale = ResourceNode("n", preferred=False)
    assert "preferred" not in normale.data and not normale.is_preferred()
    suggerita.set_preferred(False)
    assert "preferred" not in suggerita.data


def test_un_consumatore_che_ignora_preferred_non_si_rompe():
    """La prova che è un suggerimento: la scelta fatta senza guardarlo deve
    restare valida."""
    a = ResourceNode("a", url="models/a.glb", tier="distribution")
    b = ResourceNode("b", url="models/b.glb", tier="distribution", preferred=True)
    candidate = [n for n in (a, b) if n.effective_tier() == "distribution"]
    assert len(candidate) == 2, "il suggerimento non toglie nessuno dal mazzo"
    assert candidate[0].node_id == "a", "chi lo ignora prende la prima e vive"


# ── il round-trip em.json ───────────────────────────────────────────────────

def test_round_trip_emjson_isomorfo_con_tier_impacchettamento_e_misure(tmp_path):
    """Scritto, riletto e riscritto: lo stesso documento, campi nuovi compresi.

    Il secondo giro conta quanto il primo. È lì che si era visto il difetto di
    NIGHT-RIM3/B3.3 — una sentinella che al secondo round-trip diventava un
    dato — e da quel digest dipende il calcolo della staleness.
    """
    from s3dgraphy.exporter.emjson_exporter import export_emjson
    from s3dgraphy.importer.emjson_importer import import_emjson

    g = Graph(graph_id="prova_tier")
    g.add_node(StratigraphicUnit("US101", "US101"))
    g.add_node(ResourceNode(
        node_id="US101_master", name="il datablock",
        url="blend://rilievo 2015.blend#Object/muro", url_type="3d_model",
        tier="master", packaging="file"))
    g.add_node(ResourceNode(
        node_id="US101_tileset", name="il tileset servito",
        url="tilesets/US101.zip", url_type="3d_model",
        tier="distribution", packaging="archive",
        size_bytes=734_003_200, primitives={"tiles": 1843}, preferred=True))
    g.add_edge("e1", "US101", "US101_master", "has_linked_resource")
    g.add_edge("e2", "US101", "US101_tileset", "has_linked_resource")

    primo = export_emjson(g, str(tmp_path / "a.em.json"))
    riletto, warnings = import_emjson(primo)
    assert not warnings

    tornate = {n.node_id: n for n in riletto.nodes
               if getattr(n, "node_type", "") == "resource"}
    assert set(tornate) == {"US101_master", "US101_tileset"}
    assert tornate["US101_master"].tier() == "master"
    t = tornate["US101_tileset"]
    assert (t.tier(), t.packaging()) == ("distribution", "archive")
    assert t.data["size_bytes"] == 734_003_200
    assert t.data["primitives"] == {"tiles": 1843}
    assert t.is_preferred()

    secondo = export_emjson(riletto, str(tmp_path / "b.em.json"))
    a = json.load(open(primo, encoding="utf-8"))
    b = json.load(open(secondo, encoding="utf-8"))

    def risorse(doc):
        nodi = doc["graphs"]["prova_tier"]["nodes"]
        return {n["id"]: n for n in nodi if n.get("type") == "resource"}

    assert risorse(a) == risorse(b), "il secondo giro deve essere identico"
    #: e i campi sono nel FILE, non solo nell'oggetto: è quello che legge un
    #: altro strumento
    testo = json.dumps(a)
    assert '"tier": "master"' in testo and '"packaging": "archive"' in testo


def test_un_documento_scritto_PRIMA_di_questa_notte_non_dichiara_niente(tmp_path):
    """Retro-compatibilità, e nel verso giusto: assente vuol dire SCONOSCIUTO,
    non «file, distribution, non preferita» — tre affermazioni che nessuno ha
    fatto."""
    from s3dgraphy.exporter.emjson_exporter import export_emjson

    g = Graph(graph_id="vecchio")
    g.add_node(ResourceNode("r", url="models/casa.gltf", url_type="3d_model"))
    doc = json.load(open(export_emjson(g, str(tmp_path / "v.em.json")),
                         encoding="utf-8"))
    risorsa = next(n for n in doc["graphs"]["vecchio"]["nodes"]
                   if n["id"] == "r")
    for campo in ("tier", "packaging", "size_bytes", "primitives", "preferred"):
        assert campo not in risorsa["data"], f"{campo} non l'ha scritto nessuno"


# ── promote_resource: il tier, e la derivazione N:1 ─────────────────────────

def test_promote_resource_dichiara_la_distribution_e_l_impacchettamento():
    """Pubblicare vuol dire, normalmente, produrre la cosa che qualcun altro
    consuma. Il tier lo DICHIARA invece di lasciarlo dedurre: Heriverse
    indovinava con «ha il checksum, quindi è la pubblicata», che è giusto per
    caso e sbagliato la prima volta che il bake registra un digest per un file
    di lavoro — e lo fa già."""
    from s3dgraphy.publication import promote_resource

    g = Graph(graph_id="pub")
    promote_resource(g, "tileset_res", url="https://x/t.zip",
                     sha256="aa" * 32, packaging="archive",
                     size_bytes=734_003_200, primitives={"tiles": 1843})
    r = g.find_node_by_id("tileset_res")
    assert r.tier() == "distribution" and r.packaging() == "archive"
    assert r.data["size_bytes"] == 734_003_200
    assert r.data["checksum"].startswith("sha256:")


def test_promuovere_un_master_non_lo_trasforma_in_distribution():
    """Archiviare un master in uno store è un gesto vero — un originale
    fotogrammetrico che va al sicuro — e forzargli `distribution` scriverebbe
    una falsità. `tier=None` vuol dire «non toccarlo»."""
    from s3dgraphy.publication import promote_resource

    g = Graph(graph_id="pub2")
    g.add_node(ResourceNode("orig", url="/Volumi/esterno/rilievo.obj",
                            tier="master"))
    promote_resource(g, "orig", url="s3://archivio/rilievo.obj",
                     sha256="bb" * 32, tier=None)
    assert g.find_node_by_id("orig").tier() == "master"


def test_la_derivazione_N_a_1_di_un_tileset():
    """Un tileset Cesium fa le veci di un RM container: accorpa N mesh in
    un'entità rigida, quindi la genesi ha N ingressi — e il DTC li regge
    nativamente. Riportare una sola sorgente nominerebbe un vincitore che
    nessuno ha scelto."""
    from s3dgraphy.publication import promote_resource

    g = Graph(graph_id="pub3")
    for i in (1, 2, 3):
        g.add_node(ResourceNode(f"m{i}", url=f"blend://s.blend#Object/m{i}",
                                tier="master"))
    esito = promote_resource(g, "tileset_res", url="https://x/t/tileset.json",
                             sha256="cc" * 32,
                             source_ids=["m1", "m2", "m3"],
                             packaging="directory")
    assert esito.source_ids == ["m1", "m2", "m3"]
    ingressi = sorted(e.edge_target for e in g.edges
                      if e.edge_type == "dtc_had_input")
    assert ingressi == ["m1", "m2", "m3"]
    assert not esito.warnings


def test_source_id_e_source_ids_non_fanno_due_affermazioni():
    """`source_id` è la scorciatoia a una sorgente sola: un chiamante che passa
    tutti e due non sta dicendo due cose, e un ingresso duplicato nel DTC
    sarebbe un fatto inventato."""
    from s3dgraphy.publication import promote_resource

    g = Graph(graph_id="pub4")
    g.add_node(ResourceNode("m1", url="blend://s.blend#Object/m1"))
    esito = promote_resource(g, "d", url="https://x/d.glb", sha256="dd" * 32,
                             source_id="m1", source_ids=["m1"])
    assert esito.source_ids == ["m1"]
    assert [e.edge_target for e in g.edges
            if e.edge_type == "dtc_had_input"] == ["m1"]

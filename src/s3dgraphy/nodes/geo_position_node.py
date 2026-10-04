# s3Dgraphy/nodes/geo_position_node.py

from .base_node import Node

#: D2 (E.D., 4 Oct 2026) · the north the scene's ``rotation`` is measured from:
#: the GRID north of the CRS ``epsg``, never the geographic one.
ROTATION_REFERENCE = "grid"


class GeoPositionNode(Node):
    """
    Classe per rappresentare un nodo GeoPosition all'interno del grafo.

    **Uno per GRAFO, non per epoca.** ``Graph.__init__`` ne crea uno con id
    ``geo_<graph_id>``: il georiferimento è una proprietà del *grafo* — come
    nome, autore, licenza, id-HR, cioè i metadati di grafo — non di una singola
    epoca né di una singola geometria. Lo stesso ancoraggio serve tutte le
    epoche, e può essere condiviso fra grafi che descrivono lo stesso luogo.

    **Lo shift è l'ancora, non la posizione.** ``shift_x/y/z`` sono l'origine del
    sistema locale di scena, espressa nel CRS dichiarato da ``epsg``: il punto
    che in scena vale (0, 0, 0). Può stare **fuori dalla geometria** — è normale
    che sia un vertice tondo della griglia, a centinaia di metri dal monumento —
    e per questo **non è dove va il puntino sulla mappa**: quello va sul
    centroide della geometria (vedi :func:`s3dgraphy.api.georeference_scene`).
    Gemello lato-grafo di ``scene.em_georef`` in EMTools (``georef_manager``),
    che propaga gli stessi valori a BlenderGIS e 3DSC.

    Attributi:
        type (str): Tipo di nodo, impostato su "geo_position".
        data (dict): ``epsg``, ``shift_x``, ``shift_y``, ``shift_z``, ``rotation``,
            ``rotation_reference`` (``"grid"``: D2).
    """
    node_type = "geo_position"
    def __init__(self, node_id, epsg=None, shift_x=0.0, shift_y=0.0, shift_z=0.0,
                 rotation=0.0):
        """
        Inizializza una nuova istanza di GeoPositionNode.

        Args:
            node_id (str): Identificativo univoco del nodo.
            epsg (int, opzionale): Codice EPSG del sistema di riferimento delle
                coordinate. **None = non dichiarato** (dev29): un grafo nuovo o
                importato non è georiferito, e lo dice con l'assenza di ``epsg``
                in ``data``. Fino alla dev28 il default era 4326 con shift 0,
                cioè «WGS84 a 0,0»: una posizione che nessuno aveva dichiarato
                (misurato su ogni GraphML importato, San Pietro compreso).
            shift_x (float, opzionale): Spostamento lungo l'asse X. Defaults to 0.0.
            shift_y (float, opzionale): Spostamento lungo l'asse Y. Defaults to 0.0.
            shift_z (float, opzionale): Spostamento lungo l'asse Z. Defaults to 0.0.
            rotation (float, opzionale): **Azimut della scena in gradi**, rotazione
                oraria dal **nord del reticolo** (grid north) del CRS ``epsg`` —
                D2, decisione di E.D. del 4 ottobre 2026. Non dal nord geografico:
                con ``rotation = 0`` gli assi locali SONO gli assi del CRS meno lo
                shift, che è come si costruisce un modello shiftato (3DSC,
                BlenderGIS); fra nord geografico e nord del reticolo c'è la
                convergenza del meridiano, che un grafo da solo non applica mai
                e che fra due grafi conta solo come convergenza RELATIVA
                (EMtools ``georef_manager/graph_align.py``). Lo dice anche il
                dato: ``data.rotation_reference = "grid"``. ``0`` = nord in alto:
                è il default e il caso normale; un valore diverso da zero dice
                che la scena locale è ruotata rispetto al nord del reticolo
                (allineata a un muro, a una griglia di scavo, a una pianta
                storica). Additivo in 1.6 — un grafo che non lo porta si legge
                come 0, cioè come si comportava prima. Defaults to 0.0.
        """
        super().__init__(node_id=node_id, name="geo_position")
        self.data = {
            **({"epsg": epsg} if epsg is not None else {}),
            "shift_x": shift_x,
            "shift_y": shift_y,
            "shift_z": shift_z,
            "rotation": rotation,
            # D2 · da quale nord si misura la rotazione: sempre il reticolo
            "rotation_reference": ROTATION_REFERENCE,
        }
    
    def to_dict(self):
        """
        Converte l'istanza di GeoPositionNode in un dizionario.
        
        Returns:
            dict: Rappresentazione del GeoPositionNode come dizionario.
        """
        return {
            "type": self.node_type,
            "name": self.name,
            "data": self.data
        }

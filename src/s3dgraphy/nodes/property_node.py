import re

from .paradata_node import ParadataNode

#: The property whose value is its shape: ``value`` is the uuid of the
#: SemanticShape and ``description`` stays what it is (MICRO valore-proprietà,
#: E.D. 28 Oct 2026). Same spelling as ``geometry.proxy.GEOMETRY_PROPERTY_TYPE``.
GEOMETRY_PROPERTY = "geometry"

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def is_uuid_pointer(value) -> bool:
    """True when ``value`` is a bare uuid: a pointer to a node, not a datum."""
    return isinstance(value, str) and bool(_UUID_RE.match(value.strip()))


def _as_text(value):
    """The text a value mirrors to: ``""`` for nothing, the string of a scalar,
    ``None`` for what has no single text (a dict, a list) and is not mirrored."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bool, int, float)):
        return str(value)
    return None


# PropertyNode Class - Subclass of ParadataNode
class PropertyNode(ParadataNode):
    """
    Nodo che rappresenta una proprietà associata a un altro nodo.

    Più proprietari (E.D., revisione della scrivania v7). Una PropertyNode può
    avere più ``has_property`` entranti: un'unità può ISTANZIARE la proprietà
    di un'altra (una USV/s prende il ``material`` della US che completa). La
    proprietà resta UNA — un valore, una catena di paradata — con più
    proprietari. L'eredità è dichiarata, mai automatica: il secondo
    ``has_property`` porta ``attributes["inherited"] = True``
    (``s3dgraphy.ownership.inherit_property``). La proprietà resta nel
    ParadataNodeGroup del proprietario ORIGINARIO, quello che l'ha creata; gli
    altri la riferiscono con il loro ``has_property`` e mai con un gruppo.
    Chi è l'originario lo dice ``ownership.original_owner`` (la marca, poi il
    gruppo, poi il timbro ``created_at``; altrimenti non è dichiarato).

    Il valore in due posti (E.D., 28 ott 2026). Il valore storico di EM sta in
    ``description`` (yEd/GraphML, i lettori vecchi); ``value`` (``data.value``
    in em.json) lo specchia. Ogni assegnazione di uno dei due riscrive l'altro;
    alla nascita, se arriva uno solo, l'altro lo copia; se arrivano tutti e due
    diversi vince ``value`` (chi passa entrambi diversi usa ``description``
    come commento: il dato è ``value``). Svuotare uno svuota l'altro se erano
    allineati. Eccezioni: la proprietà ``geometry`` (il valore è l'uuid della
    shape) e ogni ``value`` che è un uuid nudo (un puntatore): lì i due campi
    restano indipendenti. Se ``data`` porta già una chiave ``value`` (la
    esporta l'em.json al posto dell'attributo) la si tiene uguale a ``value``.

    Attributes:
        value (any): Valore della proprietà.
        property_type (str): Tipo di proprietà (es. "Height", "Length", etc.).
        data (dict): Metadati aggiuntivi, come 'author', 'time_start', 'time_end'.
    """

    # Vocabolario delle proprietà
    PROPERTY_TYPES = {
        "Height": {
            "symbol": "↕",
            "label": "Height",
            "description": "The height of the object, typically measured in meters."
        },
        "Width": {
            "symbol": "⬌",
            "label": "Width",
            "description": "The width of the object, typically measured in meters."
        },
        "Depth": {
            "symbol": "⇵",
            "label": "Depth",
            "description": "The depth of the object, typically measured in meters."
        },
        "Length": {
            "symbol": "↔",
            "label": "Length",
            "description": "The length of the object, typically measured in meters."
        },
        "Diameter": {
            "symbol": "⬤",
            "label": "Diameter",
            "description": "The diameter of circular objects, typically measured in meters."
        },
        "Upper Diameter": {
            "symbol": "⬤",
            "label": "Upper Diameter",
            "description": "The diameter at the top of the object, typically measured in meters."
        },
        "Lower Diameter": {
            "symbol": "⬤",
            "label": "Lower Diameter",
            "description": "The diameter at the bottom of the object, typically measured in meters."
        },
        "Material": {
            "symbol": "🔨",
            "label": "Material",
            "description": "The material the object is made from (e.g., stone, wood)."
        },
        "Morphology": {
            "symbol": "🔄",
            "label": "Morphology",
            "description": "The shape and structure of the object."
        },
        "Style": {
            "symbol": "🎨",
            "label": "Style",
            "description": "The architectural or artistic style of the object."
        },
        "Location": {
            "symbol": "📍",
            "label": "Location",
            "description": "The spatial position or general location of the object."
        },
        "Find Spot": {
            "symbol": "🗺️",
            "label": "Find Spot",
            "description": "The stratigraphic unit where the object was found."
        },
        "Restoration": {
            "symbol": "🛠️",
            "label": "Restoration",
            "description": "Details on any restorations performed on the object."
        },
        "Reworking": {
            "symbol": "🔧",
            "label": "Reworking",
            "description": "Information on any modifications or reworkings of the object."
        },
        "Reuse": {
            "symbol": "♻️",
            "label": "Reuse",
            "description": "Indications of whether the object has been reused."
        },
        "Archaeometric Data": {
            "symbol": "📏",
            "label": "Archaeometric Data",
            "description": "Scientific measurements or analyses related to the object."
        },
        "Existence": {
            "symbol": "✅",
            "label": "Existence",
            "description": "Indicates whether the object exists or has existed."
        },
        "Upper Diameter at Apophyge": {
            "symbol": "⬤",
            "label": "Upper Diameter at Apophyge",
            "description": "Diameter measured at the apophyge of the upper section."
        },
        "Lower Diameter at Apophyge": {
            "symbol": "⬤",
            "label": "Lower Diameter at Apophyge",
            "description": "Diameter measured at the apophyge of the lower section."
        },
        "Documentation 2D-3D": {
            "symbol": "📸",
            "label": "Documentation",
            "description": "Details on 2D or 3D documentation of the object."
        },
        "Bibliography": {
            "symbol": "📚",
            "label": "Bibliography",
            "description": "References or literature associated with the object."
        },
        "Field Compilation Responsible": {
            "symbol": "👤",
            "label": "Field Compilation Responsible",
            "description": "Person responsible for data collection in the field."
        }
    }

    node_type = "property"

    def __init__(self, node_id, name, description="", value=None, property_type="string", data=None, url=None):
        super().__init__(node_id, name, description, url)
        object.__setattr__(self, "value", value)
        self.property_type = property_type  # Definisce il tipo della proprietà
        self.data = data if data is not None else {}
        self._align_at_birth()
        
        # Validazione del tipo di proprietà
        #self.validate_property_type()

    # ── il valore in due posti ──────────────────────────────────────────────

    def mirror_exempt(self) -> bool:
        """The geometry property keeps ``value`` (the shape) and ``description``
        apart."""
        d = self.__dict__
        return (d.get("property_type") == GEOMETRY_PROPERTY
                or d.get("name") == GEOMETRY_PROPERTY)

    def _raw(self, attr, value):
        object.__setattr__(self, attr, value)
        if attr == "value":
            data = self.__dict__.get("data")
            if isinstance(data, dict) and "value" in data:
                data["value"] = value

    def _align_at_birth(self):
        if self.mirror_exempt():
            return
        v, d = self.__dict__.get("value"), self.__dict__.get("description")
        if is_uuid_pointer(v) or is_uuid_pointer(d):
            return
        tv, td = _as_text(v), _as_text(d)
        if tv is None or td is None:
            return
        if tv and tv != td:
            self._raw("description", tv)
        elif td and not tv:
            self._raw("value", td)

    def __setattr__(self, attr, value):
        d = self.__dict__
        if (attr not in ("value", "description") or "value" not in d
                or "property_type" not in d):
            # anything else, or the node is still being built (Node.__init__
            # writes description before value exists): a plain write
            object.__setattr__(self, attr, value)
            return
        old_v, old_d = d.get("value"), d.get("description")
        self._raw(attr, value)
        if self.mirror_exempt():
            return
        tv_old, td_old = _as_text(old_v), _as_text(old_d)
        was_aligned = tv_old is not None and tv_old == (td_old or "")
        if attr == "value":
            if is_uuid_pointer(value):
                return
            t = _as_text(value)
            if t is None:
                return
            if t:
                object.__setattr__(self, "description", t)
            elif was_aligned:
                object.__setattr__(self, "description", "")
        else:
            # a pointer in value stays: the description is its own text
            if tv_old is None or is_uuid_pointer(old_v) or is_uuid_pointer(value):
                return
            t = _as_text(value)
            if t is None:
                return
            if t:
                if tv_old != t:
                    self._raw("value", t)
            elif was_aligned:
                self._raw("value", "")

    def set_value(self, value):
        """Write the value in both places (the same as ``self.value = value``)."""
        self.value = value

    def validate_property_type(self):
        """
        Valida il tipo di proprietà in base al vocabolario. Stampa un avviso se il tipo non è valido.
        """
        if self.property_type not in self.PROPERTY_TYPES:
            # print(f"Warning: Property type '{self.property_type}' is not recognized for node '{self.name}' (ID: {self.node_id}).")
            pass

    def get_property_info(self):
        """
        Restituisce le informazioni sul tipo e valore della proprietà.
        """
        return {
            "name": self.name,
            "value": self.value,
            "type": self.property_type,
            "description": self.description
        }

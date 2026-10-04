from .base_node import Node

class ResourceNode(Node):
    """
    A RESOURCE node — the resource-layer hinge to an external file/URL (image,
    document, 3D model, point cloud, web page…). Renamed from ``ResourceNode`` in
    MIG1 (2026-08-06); ``node_type`` is now ``"resource"`` (was ``"link"``).

    Attributi:
        url (str): URL del collegamento.
        url_type (str): Tipo di URL (es. "External link", "Image").
        description (str): Descrizione del collegamento.
    """
    node_type="resource"

    # Valid resource types
    RESOURCE_TYPES = {
        "3d_model": ["gltf", "obj", "fbx", "3ds", "blend"],
        "proxy_model": ["glb"],  # Typically GLB for proxies
        "image": ["jpg", "jpeg", "png", "tif", "tiff", "bmp"],
        "document": ["pdf", "doc", "docx", "txt"],
        "web_page": ["http", "https"],
        "video": ["mp4", "avi", "mov"],
        "point_cloud": ["e57", "pts", "las", "laz"]
    }

    #: Where a resource comes from, in order of distance (the shelf's THREE
    #: FENCES). Not a technical detail: it is the axis the search must be able
    #: to filter on and the UI must show, because "is this mine, my twin's, or
    #: another site's?" changes what a comparison means.
    SCOPES = ("own-study", "own-HDT", "other-HDT")

    #: Whether the bytes live here or elsewhere (Tropy's linked/managed).
    #: `reference` = I keep the URI, it stays at home; `resident` = I copied it
    #: into my own store, so the comparison travels with my study, offline too.
    RESIDENCIES = ("reference", "resident")

    #: WHAT THIS RESOURCE IS FOR, in the argument. Two values, and **orthogonal
    #: to everything else about it** (E.D. 2026-08-24):
    #:
    #: * `comparandum` — brought in to be compared against. A photograph of
    #:   another site, yes; but equally a model of *my own* study that I am
    #:   holding up next to this one;
    #: * `internal_source` — evidence inside this study's own reasoning. A URI
    #:   on somebody else's server can be exactly that.
    #:
    #: So the role is **not derivable** from `scope` (the three fences) nor from
    #: `residency` (where the bytes are): an own-study asset can be a
    #: comparandum, an external URI can be an internal source. That is why it is
    #: written and never computed — and why there is no `effective_role`: a role
    #: nobody stated is UNSET, not a default. Guessing one would put a claim
    #: about somebody's argument into their file.
    ROLES = ("comparandum", "internal_source")

    #: WHICH SIDE OF A DERIVATION this resource is on (E.D. 2026-09-13, §15).
    #:
    #: * `master` — kept because it is the source the others are made FROM.
    #:   Losing it is losing something: nothing can remake it.
    #: * `distribution` — made so that somebody else can consume it. Losing it
    #:   costs a button: it is remade from its master.
    #:
    #: **It is not a three-rung ladder.** It is a role in a PAIR, and a chain
    #: can hold several masters: the photogrammetric original on an external
    #: disk *and* the working mesh inside the .blend are both masters, tied to
    #: each other by a derivation. Asking "which rung is this on" has no answer;
    #: asking "is this the source or the thing made from it" always does.
    #:
    #: **«Published» is not a tier**: it is the STATE of a distribution whose
    #: locator resolves to something reachable and which carries a checksum. A
    #: third value would have made publication a property of the bytes instead
    #: of a property of where they got to.
    #:
    #: Why the axis has to exist at all: the contract must **declare** what a
    #: resource is instead of letting every consumer deduce it. Heriverse was
    #: guessing with "it has a checksum, so it is the published one" — a rule
    #: that is right by accident and wrong the first time somebody records a
    #: digest for a working file.
    #:
    #: Orthogonal to `scope`, `residency` and `role`, and `role` is NOT the
    #: place for it: that axis is already `comparandum` / `internal_source` by
    #: E.D.'s decision of 24-08-2026, and its own docstring says a third value
    #: invented at a call site would be "a word".
    TIERS = ("master", "distribution")

    #: HOW THE BYTES ARE SHAPED, because a consumer has to know before it can
    #: decide whether it can open them.
    #:
    #: * `file` — one file;
    #: * `directory` — a tree, served as it lies;
    #: * `archive` — a tree in a container (a zip).
    #:
    #: The zip is a first-class citizen and not a packaging accident: **a
    #: tileset travels as a zip**, because a directory of some thousands of
    #: tiles destroys disks and bandwidth alike. A consumer must read that from
    #: the data, not guess it from an extension — guessing from `.zip` works
    #: until the day somebody serves an archive without one, and fails silently.
    #:
    #: Two more (E.D. 2026-09-30, *la risorsa e i suoi file*):
    #:
    #: * `file_set` — a FEW files that call each other: an obj that names its
    #:   mtl (`mtllib`), a mtl that names its textures (`map_Kd`), a gltf and
    #:   its bin, a shp and its companions. Not a `directory`: the folder does
    #:   not bound the set, the references do — two tiles can share a
    #:   `textures/` folder and still be two resources. Its members are the
    #:   ``ResourceFileNode`` s the resource reaches with ``has_file``, one of
    #:   them the `entry_point`.
    #: * `datablock` — ONE object inside a file: a mesh inside a ``.blend``,
    #:   reached by a ``blend://`` locator. It has no canonical bytes of its own
    #:   (its digest is structural, ``emstruct1:…``, comparable and not
    #:   verifiable — dtcstamp conformance case 05), and that is what a reader
    #:   has to know before it tries to open it: no viewer can serve it, Blender
    #:   can.
    #:
    #: A viewer chooses between the REPRESENTATIONS of a thing (sibling
    #: resources tied by ``dtc_derived_from``) by reading this axis and `tier`
    #: — see :func:`s3dgraphy.resources.files.pick_representation`.
    PACKAGINGS = ("file", "directory", "archive", "file_set", "datablock")

    def __init__(self, node_id, name="Unnamed Link", url="", url_type="External link",
                 description="", checksum=None, scope=None,
                 residency=None, role=None, tier=None, packaging=None,
                 size_bytes=None, primitives=None, preferred=None):
        """
        Inizializza una nuova istanza di ResourceNode.

        Args:
            node_id (str): Identificatore univoco del nodo.
            name (str, opzionale): Nome del collegamento. Defaults to "Unnamed Link".
            url (str, opzionale): URL del collegamento. Defaults to "".
            url_type (str, opzionale): Tipo di URL. Defaults to "External link".
            description (str, opzionale): Descrizione del collegamento.
                Default **vuoto**, e nessun auto-riempimento (NIGHT-RIM3/B3.3,
                decisione 11 di E.D.). Prima il default era la sentinella
                `"No description"` e il costruttore scriveva
                `description or f"Link to {name}"`: due modi diversi di
                inventare un dato che nessuno aveva scritto.

                Perché conta più di quanto sembri: quella sentinella finiva
                su disco come se fosse un valore, e al SECONDO giro di
                round-trip em.json non sopravviveva — diventava
                «Link to <nome>». Cambiando la descrizione cambia l'impronta
                sha256 del documento, e da quel checksum dipende il calcolo
                della staleness (B4). Un campo che si riscrive da solo
                rendeva "stantio" un documento che nessuno aveva toccato.

                Vale per i nodi NUOVI: i dati esistenti non si migrano.
            checksum (str, opzionale): content digest, ``"sha256:<hex>"``. The
                ALGORITHM travels with the value on purpose — a bare hex string
                is unreadable in two years, and a checksum nobody can verify is
                worse than none. Absent for a pure URI/LOD resource: there are no
                bytes here to hash, and its identity is already the URI.
            scope (str, opzionale): one of :attr:`SCOPES`.
            residency (str, opzionale): one of :attr:`RESIDENCIES`.
            role (str, opzionale): one of :attr:`ROLES` — what the resource is
                FOR in the argument, orthogonal to scope and residency.
            tier (str, opzionale): one of :attr:`TIERS` — the source side or
                the made-from side of a derivation.
            packaging (str, opzionale): one of :attr:`PACKAGINGS` — file,
                directory or archive.
            size_bytes (int, opzionale): the weight. A measured fact, and one of
                the two things that let a consumer pick between LOD siblings.
            primitives (dict, opzionale): counts of whatever this is made of —
                ``{"vertices": n, "faces": n}`` for a mesh, ``{"points": n}``
                for a cloud, ``{"tiles": n}`` for a tileset. Recorded only when
                it is known at zero cost; an open dict rather than two fixed
                fields **on purpose**, because a point cloud has no faces and a
                fixed pair would be the same ageing enumeration in disguise.
            preferred (bool, opzionale): a SUGGESTION between candidates that
                are equally valid — never a gate. See :meth:`set_preferred`.

        Why measures and not a level enumeration: `lod0`/`lod1`/`lod2` is a
        vocabulary that ages the moment somebody adds a level in the middle, and
        it means different things in different pipelines. A weight and a
        primitive count are measured facts, they never age, and they are what a
        consumer with a bandwidth budget actually needs to compare.

        That reason still holds with D1 (E.D., 4 Oct 2026), and it is why the
        level a version now has (``lod_level``: ``lod0`` the first workable
        version made from the master, ``lod1…lodN`` the ``lod_generation``
        steps from it) is NOT a field of this node: it is an ORDINAL INSIDE ONE
        CHAIN, COMPUTED from the chain (``resources.versions.lod_level_of``),
        written only when the graph leaves and checked when it comes back. The
        etiquette orders one chain; the NUMBERS — ``size_bytes``,
        ``primitives`` and the measures of a version (``tris_per_m2``,
        ``texel_density_dd``…, ``resources.versions.LOD_MEASURES``) — are what
        compares different chains. The master is ``tier = master`` and has no
        level. What a version is for is ``data.use``, a list
        (``resources.versions.USES``).

        The three new fields are **additive and optional**, and they are written
        ONLY when given. Absent means UNKNOWN, not false: every resource written
        before these existed must keep saying nothing rather than start claiming
        it is un-hashed, own-study and by-reference — three assertions nobody
        made. (Reading is a different matter: see :meth:`effective_scope`.)
        """
        super().__init__(node_id=node_id, name=name)

        # Dati del collegamento
        self.data = {
            "url": url,
            "url_type": url_type or self._determine_url_type(url),
            #: nessun `or`: vuoto vuol dire vuoto, non «inventane una»
            "description": description
        }
        if checksum:
            self.data["checksum"] = str(checksum)
        if scope is not None:
            self.set_scope(scope)
        if residency is not None:
            self.set_residency(residency)
        if role is not None:
            self.set_role(role)
        if tier is not None:
            self.set_tier(tier)
        if packaging is not None:
            self.set_packaging(packaging)
        if size_bytes is not None or primitives is not None:
            self.set_measures(size_bytes=size_bytes, primitives=primitives)
        if preferred is not None:
            self.set_preferred(preferred)

    # ── the three fences, and where the bytes live ──────────────────────────

    def set_scope(self, scope):
        """Set the provenance fence. Raises on an unknown value: a scope outside
        the three is not a scope, and silently keeping it would put a word into
        the search filters that nothing can ever match."""
        if scope not in self.SCOPES:
            raise ValueError(
                f"scope must be one of {list(self.SCOPES)}, got {scope!r}")
        self.data["scope"] = scope

    def set_residency(self, residency):
        """Set where the bytes live. Raises on an unknown value, same reason."""
        if residency not in self.RESIDENCIES:
            raise ValueError(
                f"residency must be one of {list(self.RESIDENCIES)}, got {residency!r}")
        self.data["residency"] = residency

    def set_role(self, role):
        """Set what this resource is FOR. Raises on an unknown value, same reason
        as the other two: a third role invented at a call site would be a word
        the filters can never match, and this axis is deliberately two-valued —
        if a third case turns up it gets declared, not slipped in."""
        if role not in self.ROLES:
            raise ValueError(
                f"role must be one of {list(self.ROLES)}, got {role!r}")
        self.data["role"] = role

    def role(self):
        """The stated role, or None. **No fallback on purpose** — unlike
        :meth:`effective_scope`, there is no sane reading of an unstated role:
        neither "comparandum" nor "internal source" is what a resource is by
        default, and answering one would invent the claim."""
        return self.data.get("role") or None

    # ── which side of a derivation, and how the bytes are shaped ────────────

    def set_tier(self, tier):
        """Set the derivation side. Raises on an unknown value, same reason as
        the other axes: a third tier invented at a call site would be a word no
        filter can ever match, and this axis is deliberately a PAIR — if a third
        case turns up it gets declared, not slipped in."""
        if tier not in self.TIERS:
            raise ValueError(
                f"tier must be one of {list(self.TIERS)}, got {tier!r}")
        self.data["tier"] = tier

    def set_packaging(self, packaging):
        """Set how the bytes are shaped. Raises on an unknown value, same reason."""
        if packaging not in self.PACKAGINGS:
            raise ValueError(
                f"packaging must be one of {list(self.PACKAGINGS)}, "
                f"got {packaging!r}")
        self.data["packaging"] = packaging

    def set_measures(self, size_bytes=None, primitives=None):
        """Record the weight and, when it is free to know, the primitive counts.

        Both are optional and written only when given: a zero is a measurement
        and an absence is not, and an empty file and an unmeasured one are not
        the same thing.

        Counts are validated as non-negative integers but the KEYS are not
        enumerated: "vertices"/"faces" for a mesh, "points" for a cloud,
        "tiles" for a tileset. Fixing the keys here would be the ageing
        enumeration this axis exists to avoid; requiring them to be counts is
        what keeps the field comparable.
        """
        if size_bytes is not None:
            try:
                weight = int(size_bytes)
            except (TypeError, ValueError, OverflowError):
                # OverflowError is in the list because `int(float("inf"))`
                # raises it and not ValueError: without this an infinity would
                # leave this method by a door it does not document, and a
                # caller catching ValueError would never see it.
                raise ValueError(
                    f"size_bytes must be an integer number of bytes, "
                    f"got {size_bytes!r}")
            if weight < 0:
                raise ValueError(f"size_bytes cannot be negative, got {weight}")
            self.data["size_bytes"] = weight
        if primitives is not None:
            if not isinstance(primitives, dict):
                raise ValueError(
                    f"primitives must be a dict of counts, got {primitives!r}")
            counted = {}
            for what, how_many in primitives.items():
                try:
                    n = int(how_many)
                except (TypeError, ValueError, OverflowError):
                    raise ValueError(
                        f"primitives[{what!r}] must be a count, got {how_many!r}")
                if n < 0:
                    raise ValueError(
                        f"primitives[{what!r}] cannot be negative, got {n}")
                counted[str(what)] = n
            self.data["primitives"] = counted

    def set_preferred(self, preferred=True):
        """Mark this one as the suggestion between equally valid candidates.

        **A suggestion, never a gate.** A consumer must be able to ignore it and
        still work: it exists for the case where two distributions are both
        loadable and somebody who knows the study has an opinion about which one
        to open first. Written only when True — a `preferred: false` on every
        other resource would turn a hint into a vote, and an absent hint into a
        negative one.
        """
        if preferred:
            self.data["preferred"] = True
        else:
            self.data.pop("preferred", None)

    def tier(self):
        """The stated tier, or None. No invention — see :meth:`effective_tier`
        for the reading a consumer may make."""
        return self.data.get("tier") or None

    def packaging(self):
        """The stated packaging, or None."""
        return self.data.get("packaging") or None

    def is_preferred(self):
        """Whether somebody suggested this one. A hint, and never a gate."""
        return bool(self.data.get("preferred"))

    def effective_tier(self):
        """The tier to USE when none was recorded.

        The reading: a locator into a .blend is a **master** — those bytes exist
        so that Blender can remake things from them, and no viewer can serve
        them — and anything else is a **distribution**, because what a study
        pointed at before this axis existed was the thing it had exported to be
        consumed.

        **Why this has a fallback and :meth:`role` does not.** A role is a claim
        about somebody's ARGUMENT, and answering one nobody made would put words
        in their mouth. A tier is a fact about BYTES that every consumer has to
        decide about anyway before it can open anything — Heriverse was already
        deciding it, privately, with "it has a checksum". Refusing to read one
        here does not prevent the guess: it only scatters it, differently, into
        each consumer.

        Like :meth:`effective_scope`, this is a READING made by the caller and
        not a default written into ``data``: the document still says nothing.
        """
        recorded = self.data.get("tier")
        if recorded:
            return recorded
        return "master" if str(self.data.get("url") or "").startswith(("blend://", "psx://")) \
            else "distribution"

    def effective_packaging(self):
        """The packaging to USE when none was recorded — a reading, from the
        shape of the locator: a `blend://` locator is a datablock, a `.zip` or
        a `.3tz` (the 3D Tiles archive, a zip by specification) is an archive, a
        trailing slash is a directory, everything else is one file.

        Deliberately weak, and that is the point of `set_packaging` existing: an
        archive served without a `.zip` in its name reads as a file here, and
        the only cure is for whoever made it to SAY so.
        """
        recorded = self.data.get("packaging")
        if recorded:
            return recorded
        url = str(self.data.get("url") or "")
        # A `blend://` locator names ONE datablock by construction — its form is
        # `blend://<file>#<Type>/<name>` (resources/resolver.py) — so reading it
        # as a datablock is not a guess from an extension: it is the locator's
        # own grammar. The same reading `effective_tier` makes («master»).
        # The same for `psx://<project>#<chunk>/<type>/<key>`: an asset inside a
        # Metashape project (MICRO-IL-LETTORE-DI-METASHAPE), the master.
        if url.startswith(("blend://", "psx://")):
            return "datablock"
        if url.lower().endswith((".zip", ".3tz")):
            return "archive"
        return "directory" if url.endswith("/") else "file"

    def effective_scope(self):
        """The scope to USE when none was recorded.

        ``own-study`` is the sane reading of a resource somebody put in their own
        shelf before the field existed — but it is a reading, made here, by the
        consumer. The document itself still says nothing, which is why this is a
        method and not a default written into ``data``.
        """
        return self.data.get("scope") or "own-study"

    def effective_residency(self):
        """The residency to USE when none was recorded: a remote URI is a
        reference (the bytes are somebody else's), anything else is resident.

        NIGHT-RIM2/B1 · un locator ``blend://`` (i byte dentro un file
        .blend) è **resident**: il file ce l'ho, i byte sono miei. Lo dice
        già il ripiego — non è remoto, quindi cade nel ramo giusto — ma
        adesso è scritto invece che dedotto dal fatto che l'elenco dei
        remoti non lo contiene: il giorno che qualcuno aggiunge uno schema a
        quell'elenco, non deve farlo per sbaglio anche per questo.

        NON deciso, e non l'ho deciso io (elenco delle questioni aperte,
        voce C): se una risorsa dentro un .blend **non ancora pubblicata**
        meriti uno stato terzo, tipo «solo qui, non pubblicabile», invece di
        essere una ``resident`` come le altre. Qui c'è il minimo che non
        pregiudica quella scelta.
        """
        recorded = self.data.get("residency")
        if recorded:
            return recorded
        url = str(self.data.get("url") or "")
        if url.startswith("blend://"):
            return "resident"
        return "reference" if url.startswith(("http://", "https://", "s3://")) else "resident"

    @property
    def url(self):
        """Property for convenient access to URL from data dict"""
        return self.data.get("url", "")

    @url.setter
    def url(self, value):
        """Property setter for URL"""
        self.data["url"] = value


    # ── the image layer (IIIF), DERIVED and never stored ────────────────────

    def iiif_service(self, base):
        """The IIIF Image API service for this resource, or None if it is not an
        image (or carries no checksum to be addressed by).

        Derived at call time from the asset's own digest — the object store is
        content-addressed, so the image server needs no identifier of its own.
        NOT written into ``data``: a service URL in the document would pin one
        deployment's hostname into the study, and the day the server moves every
        project would carry a dead address. See :mod:`s3dgraphy.iiif`.
        """
        from ..iiif import image_service
        return image_service(self, base)

    def iiif_thumbnail(self, base, width=400):
        """A thumbnail URL — a size request, not a file we generate."""
        from ..iiif import thumbnail_url
        return thumbnail_url(self, base, width)

    def _determine_url_type(self, url):
        """
        Automatically determine the resource type from the URL/path
        """
        # Check if it's a web URL
        if url.startswith(("http://", "https://")):
            return "web_page"
            
        # Get extension
        ext = url.lower().split('.')[-1] if '.' in url else ''
        
        # Check extension against known types
        for res_type, extensions in self.RESOURCE_TYPES.items():
            if ext in extensions:
                return res_type
                
        # Special case for proxies
        if ext == "glb" and "proxy" in url.lower():
            return "proxy_model"
            
        return "unknown"

    def to_dict(self):
        """
        Converte l'istanza di ResourceNode in un dizionario.

        Returns:
            dict: Rappresentazione del ResourceNode come dizionario.
        """
        return {
            "id": self.node_id,
            "type": self.node_type,
            "name": self.name,
            "description": self.data.get("description", ""),
            "data": {
                "url": self.data.get("url", ""),
                "url_type": self.data.get("url_type", "unknown")
            }
        }




'''
# Creazione di un ResourceNode per un URL Zenodo
resource_node_zenodo = ResourceNode(
    node_id="USM04.zenodo",
    name="ZENODO URL",
    url="https://zenodo.org/record/28917",
    url_type="External link",
    description="Zenodo repository entry"
)

# Creazione di un ResourceNode per un’immagine a risoluzione completa
resource_node_image = ResourceNode(
    node_id="D.01.image",
    name="FullRES Image",
    url="http://aton.ispc.it/image.jpeg",
    url_type="Image",
    description="Full resolution image"
)

# Aggiunta dei nodi al grafo e connessione (esempio con edge tipo "generic")
graph = Graph(graph_id="example_graph")
graph.add_node(resource_node_zenodo)
graph.add_node(resource_node_image)
graph.add_edge(edge_id="link_edge_1", edge_source=resource_node_zenodo.node_id, edge_target="some_target_node", edge_type="generic")
graph.add_edge(edge_id="link_edge_2", edge_source=resource_node_image.node_id, edge_target="some_target_node", edge_type="generic")

'''
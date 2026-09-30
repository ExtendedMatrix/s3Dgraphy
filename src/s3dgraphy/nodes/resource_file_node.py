from .base_node import Node


class ResourceFileNode(Node):
    """ONE FILE of a resource — the resource is the set, this is each member.

    Decided by E.D. on 30 Sep 2026 (brain: *La risorsa e i suoi file*): a
    ``ResourceNode`` is the HANDLE a person stamps, cites and opens — name,
    kind, scope, residency, role, tier, packaging, rights — and a
    ``ResourceFileNode`` is one of the bytes it is made of: an obj, its mtl and
    its textures are three files of ONE resource, not three resources.

    Reached from its resource by ``has_file`` (reverse ``is_file_of``), and the
    edge — not this node — carries the **role** (``entry_point`` | ``member``)
    and the **relative path**. That is the whole reason the file is a node of
    its own: the same corrected texture sits in N resources under N different
    paths, and a path written here would have to be one of them.

    **With one file the node is IMPLICIT.** A resource with ``url`` (and maybe
    ``checksum``) and no ``has_file`` is a resource of one file, and every graph
    written before this class existed stays exactly as it is: see
    :func:`s3dgraphy.resources.files.resource_files`, which shows that file
    anyway. The node is written only when there is more than one file, or when
    the one file has a stamp or an identity of its own.

    Fields (all in ``data``, written only when given — absent means UNKNOWN):

    * ``url`` — where the bytes are: a relative path, a ``file://`` /
      ``s3://`` / ``http(s)://`` URI, or a ``blend://`` locator;
    * ``checksum`` — ``"sha256:<hex>"``, the algorithm travelling with the value
      as on :class:`ResourceNode` (a datablock carries ``emstruct1:…``, which is
      comparable and not verifiable: see dtcstamp conformance case 05);
    * ``size_bytes`` — the weight, a measured fact;
    * ``media_type`` — the IANA type (``model/obj``, ``image/jpeg``…);
    * for a **datablock** (an object inside a ``.blend``): ``blend_file`` and
      ``datablock`` are NOT stored twice. They are read from the ``blend://``
      locator, whose one form is owned by
      :func:`s3dgraphy.resources.resolver.make_blend_locator` — two copies of
      the same address are two addresses the day one of them is edited.
    """

    node_type = "resource_file"

    def __init__(self, node_id, name="", url="", checksum=None,
                 size_bytes=None, media_type=None, blend_file=None,
                 datablock=None, datablock_type="Object", description=""):
        super().__init__(node_id=node_id, name=name or node_id,
                         description=description)
        self.data = {}
        if not url and blend_file and datablock:
            from ..resources.resolver import make_blend_locator
            url = make_blend_locator(blend_file, datablock_type, datablock)
        if url:
            self.data["url"] = str(url)
        if checksum:
            self.data["checksum"] = str(checksum)
        if size_bytes is not None:
            try:
                weight = int(size_bytes)
            except (TypeError, ValueError, OverflowError):
                raise ValueError(
                    f"size_bytes must be an integer number of bytes, "
                    f"got {size_bytes!r}")
            if weight < 0:
                raise ValueError(f"size_bytes cannot be negative, got {weight}")
            self.data["size_bytes"] = weight
        if media_type:
            self.data["media_type"] = str(media_type)

    @property
    def url(self):
        return self.data.get("url", "")

    @url.setter
    def url(self, value):
        self.data["url"] = value

    @property
    def checksum(self):
        return self.data.get("checksum") or None

    def _blend(self):
        from ..resources.resolver import parse_blend_locator
        return parse_blend_locator(self.url)

    @property
    def blend_file(self):
        """The ``.blend`` holding the datablock, read from the locator, or None."""
        parsed = self._blend()
        return parsed[0] if parsed else None

    @property
    def datablock(self):
        """The datablock's name, read from the locator, or None."""
        parsed = self._blend()
        return parsed[2] if parsed else None

    def to_dict(self):
        return {
            "id": self.node_id,
            "type": self.node_type,
            "name": self.name,
            "description": self.description,
            "data": dict(self.data),
        }

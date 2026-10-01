from .base_node import Node


class TranslationNode(Node):
    """ONE TRANSLATION of one text field of one node — a text, not a value.

    Decided by E.D. on 1 Oct 2026 (brain: *La lingua dei dati*, «Le
    traduzioni»): the ORIGINAL stays a string in its own field, in the language
    it was written in (``data.lang`` on the node, else the study's), and is never
    overwritten; every translation is a node of its own, with who, when, how and,
    when it comes from a published edition, which one. CIDOC has both terms:
    the class is ``crm:E33_Linguistic_Object`` and the relation from the
    translated thing is ``crm:P73_has_translation`` (edge ``has_translation``,
    reverse ``is_translation_of``).

    Fields (all in ``data``):

    * ``lang`` — the language of ARRIVAL, a BCP 47 tag. The same key and the
      same meaning as every node's ``data.lang``, so the translation's own text
      takes its tag by the ordinary cascade;
    * ``from_lang`` — the language of DEPARTURE, i.e. of the original WHEN it
      was translated. Written, not read off the original later, because the
      original can change;
    * ``field`` — the translated field, in the CRDT's field vocabulary:
      ``description`` or ``data.<key>`` (a PropertyNode's value is
      ``data.value``). ``name`` is never a field: names are invariant;
    * ``text`` — the translation;
    * ``method`` — ``manual`` | ``ai`` | ``edition``;
    * ``source_digest`` — ``sha256:<hex>`` of the original text that was
      translated (NFC, UTF-8). When the original changes the digests differ and
      the translation is «da riallineare»: :func:`s3dgraphy.translation.is_stale`;
    * ``review_requested`` — ``true`` when the translator asks for a review
      («da rivedere»); closed by ``validated_by`` / ``validated_at``, the same
      two fields that close an AI marker (``ai_validation``).

    Who translated is the ``has_author`` edge (an AuthorNode); an AI translation
    also carries ``data.ai_assisted`` and stays among the warnings until a
    person verifies it. A translation taken from an edition reaches the
    DocumentNode of that edition with ``extracted_from``: a published
    translation is a source, read through a translator.
    """

    node_type = "translation"

    METHODS = ("manual", "ai", "edition")

    def __init__(self, node_id, name="", description="", lang=None,
                 from_lang=None, field=None, text="", method="manual",
                 source_digest=None, review_requested=False):
        super().__init__(node_id=node_id, name=name or node_id,
                         description=description)
        self.data = {}
        if lang:
            self.data["lang"] = str(lang)
        if from_lang:
            self.data["from_lang"] = str(from_lang)
        if field:
            self.data["field"] = str(field)
        if text:
            self.data["text"] = str(text)
        if method:
            if method not in self.METHODS:
                raise ValueError(
                    f"method must be one of {list(self.METHODS)}, got {method!r}")
            self.data["method"] = method
        if source_digest:
            self.data["source_digest"] = str(source_digest)
        if review_requested:
            self.data["review_requested"] = True

    # Read AND written through ``data``: ``api.set_field`` mirrors a data key
    # onto an attribute of the same name (``_write_back``), so each one needs a
    # setter or a field write would fail on the attribute.
    def _data_property(key, default=None):
        def fget(self):
            return self.data.get(key, default)

        def fset(self, value):
            if value is None:
                self.data.pop(key, None)
            else:
                self.data[key] = value
        return property(fget, fset)

    lang = _data_property("lang")
    from_lang = _data_property("from_lang")
    field = _data_property("field")
    text = _data_property("text", "")
    method = _data_property("method")
    source_digest = _data_property("source_digest")
    del _data_property

    def to_dict(self):
        return {
            "id": self.node_id,
            "type": self.node_type,
            "name": self.name,
            "description": self.description,
            "data": dict(self.data),
        }

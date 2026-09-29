"""s3dgraphy.shelf — the Shelf substrate (Shelf v2 core, Session A).

A **shelf-graph** is a first-class collection of **un-hatted resources**
(un-instantiated LinkNodes = R0 stable IDs not yet referenced by a Document/RM).
It is representable in two interchangeable ways, both reusing the existing
machinery — NO new node type, NO datamodel change:

  * as a **member of the multigraph** — a plain :class:`~s3dgraphy.graph.Graph`
    tagged as a shelf (``graph.data["em_collection"] == "ShelfGraph"``), the
    Heriverse **ShelfGraph** convention;
  * as a **standalone, reusable em.json file** — a shelf is a file in its own
    right, importable into any study (save/load via the existing em.json I/O).

Each shelf entry is a ResourceNode (E73) carrying its resource identity (the stable
ID, R0) PLUS its **capability/origin** (repo, resource type, and any acquisition
scope) on ``node.data["origin"]`` — preserved end-to-end so a downstream UI can
badge the source tier. This substrate never strips it.

Pure library: no UI, no connectors, no OpenShelf/web. Instantiation is
reference-by-stable-ID (reuse-not-duplicate): the same resource is referenced
into a study graph by its ID, never cloned under a new ID.
"""

from .core import (
    DEFAULT_SHELF_ID,
    FACETS,
    SHELF_COLLECTION,
    SHELF_COLUMNS,
    add_to_shelf,
    attach_candidates,
    hat_as_document,
    hat_as_representation_model,
    hat_as_rmdoc,
    hat_as_rmsf,
    hat_as_visual_resource,
    instantiate_from_shelf,
    is_shelf,
    list_shelf,
    load_shelf,
    new_shelf,
    remove_from_shelf,
    referrers,
    remove_resource,
    save_shelf,
    shelf_entry_status,
    shelf_table,
    shelve_stamp,
    STAMP_RECEIPT_KEY,
)

__all__ = [
    "SHELF_COLLECTION",
    "DEFAULT_SHELF_ID",
    "new_shelf",
    "is_shelf",
    "add_to_shelf",
    "shelve_stamp",
    "STAMP_RECEIPT_KEY",
    "list_shelf",
    "remove_from_shelf",
    "remove_resource",
    "save_shelf",
    "load_shelf",
    "instantiate_from_shelf",
    "hat_as_representation_model",
    "hat_as_rmsf",
    "hat_as_rmdoc",
    "hat_as_document",
    "hat_as_visual_resource",
    "FACETS",
    "attach_candidates",
    # derived reads (Traccia A): what a row is FOR and whether it is used
    "shelf_entry_status",
    "referrers",
    "shelf_table",
    "SHELF_COLUMNS",
]

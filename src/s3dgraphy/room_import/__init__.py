"""A study into a room, from a folder: ONE engine, three doors.

E.D., 15 Oct 2026: «mi manca un importer secco per i dataset di Extended
Matrix, con tutti i suoi dati locali». Until today the gesture existed twice —
«Bring into a room…» in EM Tools (`sync_manager/bring.py`, Python inside
Blender) and in EMStudio (`seedOpsForContainer` and the inventory, in
TypeScript) — and the two diverged: different resources seen, different
resolving, the graph seated first in one and last in the other (the table is
in the report of MICRO-ROOM-IMPORT). Two implementations of one gesture are two
behaviours to correct.

So: **one engine, here**, pure Python, no Blender, testable with a fake node;
**three doors** that call it — the command (`python -m s3dgraphy room-import`,
:func:`s3dgraphy.api.room_import`), EMStudio through its bridge, EM Tools'
Files and «Bring into a room» (where only the SCENE stays: exporting a model
from the scene before it goes up, materialising what comes down). It also
works on a folder nobody ever opened in Blender — a dataset from Zenodo.

The parts of EM Tools without `bpy` were MOVED here, not copied
(`inventory`, `node` ← `asset_upload` + `rooms_list` + `room_access` +
`handoff`, `access`, `trust`): EM Tools imports them from s3Dgraphy.

THE RULES

1. **What is in the folder goes up.** What the graph cites outside it
   (`onedrive://`, `smb://`, the NAS, http, `blend://`) becomes a reference by
   digest: its locator and checksum stay, `residency: reference`. **A file
   goes up once**: if the node has it (HEAD by sha256) it is not sent again,
   and a file the study names twice is one upload.
2. **Restart.** A second run uploads nothing and duplicates nothing: files are
   asked for by digest, the operations are idempotent, and the journal
   (`.em_room_import.json` beside the em.json) remembers what was hashed and
   what was seeded. A cut run starts again where it was.
3. **The graph is seated last**, as in `bring.py`: the room receives the
   resources already hosted, in one seeding, through `POST …/ops` in parts —
   the same operations `dev-stack/seed_rooms.py` and EMStudio send.
4. **Stamps travel with their files**: a `<file>.stamp.json` beside a file
   goes up with it (`data.stamp_asset` on the resource).
5. **The report says everything**: uploaded N (size), already on the node,
   references M, missing K, the room's link — json and md.

A hosted resource keeps its path: `data.url` becomes the room's address and
the old locator stays as a second address of the same bytes (`addresses`); a
`resource_file` keeps it in `data.path`, as EMStudio writes it. A file at home
in ANOTHER room of the node (F1, `X-EM-Home-Room`) is not moved without a
person's yes: it becomes a reference to the room it lives in.

A TILESET in a folder (`packaging: directory`, thousands of files) goes up
file by file, with a list of its members (`members_manifest`, dtcstamp's
canonical form) — or, with `--pack-tilesets 3tz`, as ONE canonical `.3tz`
written by dtcstamp (s3Dgraphy stays a reader), a sibling representation
(`dtc_derived_from` the folder, a DTC step `packing` with its stamp); the
folder stays as a reference. See :mod:`.pack`.

A CLIENT WITH A DIALOG (EM Tools' «Bring into a room») calls the two halves:
:func:`prepare` (the room, then the plan, from the study it holds in memory:
`container=`, `base_dirs=`), shows the rows, and :func:`execute` with the
person's choices (:func:`apply_choices` per group / batch / item, `move` for
«Move here», the confirmed `lots`) and its hook for what only the client can
make (`before_seed`: EM Tools publishes the scene's models there, so they are
in the one seeding).

Defaults to confirm (E.D.): the name `room_import` / `room-import`, a new
room's visibility `restricted`.
"""

from .engine import (JOURNAL_NAME, Interrupted, Journal, apply_choices,
                     birth_sections, execute, make_plan, markdown, plan_report,
                     prepare, room_import, summarise_plan)
from .errors import RoomError

__all__ = ["JOURNAL_NAME", "Interrupted", "Journal", "RoomError", "apply_choices",
           "birth_sections", "execute", "make_plan", "markdown", "plan_report",
           "prepare", "room_import", "summarise_plan"]

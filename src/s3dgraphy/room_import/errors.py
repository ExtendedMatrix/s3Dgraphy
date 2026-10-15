"""The one error of a talk with a node.

Moved from EM Tools (`sync_manager/room.py::RoomError`, 3bfdb93): EM Tools
raises it, catches it and reads its `status`, so the class is the same object
in both places once EM Tools imports it from here.
"""

from __future__ import annotations

from typing import Optional


class RoomError(RuntimeError):
    """The room refused, or could not be reached. Carries a sentence a user can
    act on rather than an HTTP number nobody reads.

    …and, when there was one, the **status** beside the sentence. Not for
    display: for the one caller that must tell refusals apart. A 403 on an asset
    is the embargo gate doing its job (the study is closed and this token is not
    an editor of it) while a 404 is a missing file — the first is a row to skip
    with an explanation, the second is something wrong. A consumer that could
    only read the sentence would have to match on English.
    """

    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status

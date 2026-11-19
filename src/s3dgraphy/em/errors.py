"""The two things ``em`` raises (SPEC-plugin §2.3, §11)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from .messages import both, language


class EmError(Exception):
    """Base: carries the sentence in EN and IT (``.messages``); ``str()`` is
    the host's language."""

    def __init__(self, messages: Dict[str, str], **data: Any):
        self.messages = dict(messages)
        self.data = data
        super().__init__(self.messages.get(language(), next(iter(self.messages.values()))))


class NotAvailable(EmError, NotImplementedError):
    """``em.app`` asked for something this host does not have — every call with
    no application (the command line), ``view`` in Blender. A
    ``NotImplementedError`` too, so ``except NotImplementedError`` keeps working."""

    def __init__(self, feature: str, host: str = "none", *, key: Optional[str] = None):
        key = key or ("no_application" if host == "none" else "not_in_host")
        super().__init__(both(key, feature=feature, host=host), feature=feature, host=host)
        self.feature, self.host = feature, host


class Refused(EmError):
    """The contract said no — and NOTHING was applied. ``.result`` is the
    contract's :class:`~s3dgraphy.contract.Result` (``.data["reason"]``: the
    refusal's name: ``no-author``, ``capability-not-declared``,
    ``connection-not-allowed``, ``ops-in-proposal``…)."""

    def __init__(self, result: Any, messages: Optional[Dict[str, str]] = None):
        self.result = result
        text = getattr(result, "message", "") or "refused"
        super().__init__(messages or {"en": text, "it": text},
                         reason=(getattr(result, "data", None) or {}).get("reason"))
        self.reason = self.data.get("reason")


__all__ = ["EmError", "NotAvailable", "Refused"]

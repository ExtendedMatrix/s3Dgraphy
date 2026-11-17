"""Migrations of a graph's content from one spelling of the language to the next.

A migration here is a PLAN first — what would change, node by node, so a person
can read it before anything happens — then a delta in the CRDT vocabulary
(``update_field``), and the delta that undoes it. It never changes an id.

* :mod:`.definition_to_interpretation` — the PropertyNodes ``definition`` of
  the EM 1.5 GraphML templates are interpretations (em_qualia_types 1.6.12,
  ``property_names._rule``): renamed ``interpretation`` in place.
"""

from .definition_to_interpretation import (OLD_NAME, NEW_NAME, is_legacy_definition,
                                           plan, plan_emjson, delta, undo_delta,
                                           apply, apply_emjson)

__all__ = ["OLD_NAME", "NEW_NAME", "is_legacy_definition", "plan", "plan_emjson",
           "delta", "undo_delta", "apply", "apply_emjson"]

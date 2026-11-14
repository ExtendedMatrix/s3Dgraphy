"""
Hierarchical property resolvers for propagative metadata (DP-32).

A property declared on an Extended Matrix graph can live at three scope levels:

    node  >  swimlane (EpochNode)  >  graph (canvas header)

This subpackage exposes a generic 3-level resolver and a registry of
``PropagationRule`` objects. Each rule describes how to look up a specific
property at each level. Resolving a property walks the levels in order and
returns the first non-null value.

Built-in rules live in :mod:`s3dgraphy.resolvers.builtin_rules` and cover
chronology (``absolute_time_start``, ``absolute_time_end``) and authorship
(``author``). Consumers can register their own rules via
:func:`register_rule`.
"""

from .property_resolver import (
    PropagationRule,
    resolve,
    resolve_with_source,
    register_rule,
    unregister_rule,
    get_rule,
    list_rules,
)

from .provenance import (
    resolve_provenance,
    provenance_table,
    masters_of,
    servile_kind,
)

# Importing builtin_rules has the side effect of registering the default rules.
from . import builtin_rules  # noqa: F401

__all__ = [
    "PropagationRule",
    "resolve",
    "resolve_with_source",
    "register_rule",
    "unregister_rule",
    "get_rule",
    "list_rules",
    "resolve_provenance",
    "provenance_table",
    "masters_of",
    "servile_kind",
]

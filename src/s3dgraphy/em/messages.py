"""The sentences of ``em``, in English and Italian (the interface's two languages).

One table, so a host that speaks Italian says the same things as one that
speaks English. The language is the HOST's (``Host.language()``), else
``S3DGRAPHY_LANG``, else English — the project's reference language.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

MESSAGES: Dict[str, Dict[str, str]] = {
    "no_application": {
        "en": "no application: «{feature}» needs EMStudio or Blender (this is {host})",
        "it": "nessuna applicazione: «{feature}» richiede EMStudio o Blender (qui c'è {host})",
    },
    "not_in_host": {
        "en": "«{feature}» does not exist in {host}",
        "it": "«{feature}» non esiste in {host}",
    },
    "no_graph": {
        "en": "no graph is open: em.open(path) or em.use(graph) first",
        "it": "nessun grafo aperto: prima em.open(percorso) o em.use(grafo)",
    },
    "no_node": {
        "en": "no node «{ref}» in the graph",
        "it": "nessun nodo «{ref}» nel grafo",
    },
    "many_nodes": {
        "en": "«{ref}» names {count} nodes: use the id ({ids})",
        "it": "«{ref}» nomina {count} nodi: usa l'id ({ids})",
    },
    "unknown_event": {
        "en": "unknown event «{event}» (the events: {known})",
        "it": "evento sconosciuto «{event}» (gli eventi: {known})",
    },
    "listener_failed": {
        "en": "a listener of {event} failed ({listener}): {error}",
        "it": "un ascoltatore di {event} è fallito ({listener}): {error}",
    },
    "tx_closed": {
        "en": "this transaction is closed: open another em.write(...)",
        "it": "questa transazione è chiusa: aprine un'altra con em.write(...)",
    },
    "tx_failed": {
        "en": "nothing was applied: the block raised {error}",
        "it": "niente è stato applicato: il blocco ha sollevato {error}",
    },
    "no_profile": {
        "en": "no active package declares «{ref}»",
        "it": "nessun pacchetto attivo dichiara «{ref}»",
    },
    "no_concept": {
        "en": "no installed vocabulary knows «{uri}»",
        "it": "nessun vocabolario installato conosce «{uri}»",
    },
    "partial": {
        "en": "applied with {count} part(s) refused: {first}",
        "it": "applicato con {count} parte/i rifiutate: {first}",
    },
    "nothing_to_write": {
        "en": "«{label}»: nothing to write",
        "it": "«{label}»: niente da scrivere",
    },
    "written": {
        "en": "«{label}»: {nodes} node(s), {edges} relation(s), {ops} change(s)",
        "it": "«{label}»: {nodes} nodo/i, {edges} relazione/i, {ops} modifica/he",
    },
    "raw_warning": {
        "en": "node.raw is the live node: changing it writes NOTHING (no undo, no Log, no author) — use em.write",
        "it": "node.raw è il nodo vero: cambiarlo NON scrive niente (né annulla, né Log, né autore): usa em.write",
    },
}


def language(lang: Optional[str] = None) -> str:
    if lang:
        return "it" if str(lang).lower().startswith("it") else "en"
    try:
        from . import host as _host
        h = _host.current()
        return language(h.language()) if h.language() else _env_language()
    except Exception:                                # noqa: BLE001 — before a host: env
        return _env_language()


def _env_language() -> str:
    return "it" if os.environ.get("S3DGRAPHY_LANG", "").lower().startswith("it") else "en"


def message(key: str, lang: Optional[str] = None, **kw: Any) -> str:
    table = MESSAGES[key]
    return table[language(lang)].format(**kw)


def both(key: str, **kw: Any) -> Dict[str, str]:
    """The sentence in the two languages — what an exception carries, so a host
    may show the other one."""
    return {lang: text.format(**kw) for lang, text in MESSAGES[key].items()}

"""What the validator says, in English and in Italian.

A problem is a code, a level (``error`` refuses the package, ``warning`` does
not), the place it was found (``where``: a file, a key path) and the values
its sentence needs. The two sentences come from the same template, so the
window (W6), the command line (W19) and the CI of em-profiles show the same
words; ``str(problem)`` is the English one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

ERROR = "error"
WARNING = "warning"

#: code → (English, Italian). Placeholders are ``{name}`` of ``params``.
MESSAGES: Dict[str, Tuple[str, str]] = {
    # reading
    "not_a_package": ("not a package: no profile.json and no em-extension.toml",
                      "non è un pacchetto: manca profile.json e manca em-extension.toml"),
    "unreadable": ("cannot be read: {why}", "non si legge: {why}"),
    "missing_file": ("{path}: the file is not in the package", "{path}: il file non è nel pacchetto"),
    "bad_json": ("{path}: not JSON ({why})", "{path}: non è JSON ({why})"),
    "schema": ("{message}", "{message}"),
    "schema_unchecked": ("the JSON schema was not checked: jsonschema is not installed (the coherence checks ran)",
                         "lo schema JSON non è stato controllato: jsonschema non è installato (i controlli di coerenza sì)"),
    "format_unknown": ("profile_format {value!r} is not a version this library reads (0.1, 0.2)",
                       "profile_format {value!r} non è una versione che questa libreria legge (0.1, 0.2)"),
    "required": ("{key} is required", "{key} è obbligatorio"),
    # identity
    "name_folder": ("name {name!r} is not the name of its folder {folder!r}",
                    "name {name!r} non è il nome della sua cartella {folder!r}"),
    "prefix_bad": ("prefix {prefix!r}: 2–16 lowercase letters or digits, a letter first",
                   "prefix {prefix!r}: da 2 a 16 lettere minuscole o cifre, prima una lettera"),
    "version_bad": ("{key} {value!r} is not a semantic version (MAJOR.MINOR.PATCH)",
                    "{key} {value!r} non è una versione semantica (MAJOR.MINOR.PATCH)"),
    "prefix_missing": ("{type}: a type of the profile carries its prefix {prefix!r}",
                       "{type}: un tipo del pacchetto porta il suo prefisso {prefix!r}"),
    "core_redefined": ("{type}: an id of the core cannot be redefined by a package",
                       "{type}: un id del nucleo non si ridefinisce da un pacchetto"),
    "duplicate_type": ("{type}: declared twice", "{type}: dichiarato due volte"),
    "label_language": ("{where}: no label in {lang!r}, a language the profile declares",
                       "{where}: manca l'etichetta in {lang!r}, una lingua che il pacchetto dichiara"),
    "unverified_not_declared": ("unverified_languages: {lang!r} is not in languages",
                                "unverified_languages: {lang!r} non è tra le lingue (languages)"),
    # types
    "node_types_suspended": ("{type}: node and edge types of packages are suspended in EM 1.6 (D-1); "
                             "tools draw it as the core type it specialises",
                             "{type}: i tipi di nodo e d'arco dei pacchetti sono sospesi nella EM 1.6 (D-1); "
                             "gli strumenti lo disegnano come il tipo del nucleo che specializza"),
    "not_core_node": ("{type}: {parent!r} is not a core node type", "{type}: {parent!r} non è un tipo di nodo del nucleo"),
    "not_core_edge": ("{type}: {parent!r} is not a core edge type", "{type}: {parent!r} non è un tipo d'arco del nucleo"),
    "unknown_node_type": ("{where}: {type!r} is neither a type of the package nor of the core",
                          "{where}: {type!r} non è un tipo del pacchetto né del nucleo"),
    "unknown_quale": ("{where}: {quale!r} is neither a quale of the package nor of the core",
                      "{where}: {quale!r} non è un quale del pacchetto né del nucleo"),
    "unknown_edge": ("{where}: {type!r} is not an edge type of the package nor of the core",
                     "{where}: {type!r} non è un tipo d'arco del pacchetto né del nucleo"),
    "rule_undeclared": ("visual_rules.{block}.{key}: not a {what} of the package",
                        "visual_rules.{block}.{key}: non è un {what} del pacchetto"),
    "writes_false": ("plugin {id}: declares a writing capability with writes=false",
                     "plugin {id}: dichiara una capability di scrittura con writes=false"),
    # 3D, combiners, landmarks
    "geometry_produces": ("{type}: a {primitive} cannot produce {produces} (it produces: {allowed})",
                          "{type}: una primitiva {primitive} non produce {produces} (produce: {allowed})"),
    "geometry_vertices": ("{type}: vertices.min {min} is greater than vertices.max {max}",
                          "{type}: vertices.min {min} è maggiore di vertices.max {max}"),
    "landmark_extractor": ("{set}: extractor_type {type!r} is not an extractor type of the package with primitive point",
                           "{set}: extractor_type {type!r} non è un tipo di estrattore del pacchetto con primitiva point"),
    "landmark_file": ("{path}: {why}", "{path}: {why}"),
    "landmark_mirror": ("{set}/{point}: mirror {mirror!r} is not a point of the set",
                        "{set}/{point}: mirror {mirror!r} non è un punto dell'insieme"),
    "landmark_unknown": ("{where}: landmark {ref!r} is not a point of a landmark set of the package",
                         "{where}: il punto {ref!r} non è un punto di un insieme del pacchetto"),
    "combiner_arity": ("{type}: {operation} takes {want}, here {got}", "{type}: {operation} vuole {want}, qui {got}"),
    "combiner_inputs": ("{type}: {operation} takes {want} inputs", "{type}: {operation} vuole come ingressi {want}"),
    # files, readers, forms, colours, texts
    "reader_plugin": ("{type}: reader {reader!r} names a plugin the package does not require",
                      "{type}: il lettore {reader!r} nomina un plugin che il pacchetto non richiede"),
    "reader_builtin": ("{type}: {reader!r} is not a reader the tools have (builtin: {known})",
                       "{type}: {reader!r} non è un lettore degli strumenti (builtin: {known})"),
    "form_digest": ("forms {id}: the compiled form's digest is {got}, the manifest says {want}",
                    "forms {id}: il digest della scheda compilata è {got}, il manifesto dice {want}"),
    "vocab_file": ("{path}: {why}", "{path}: {why}"),
    "vocab_version": ("{path}: owl:versionInfo {got!r}, the manifest says {want!r}",
                      "{path}: owl:versionInfo {got!r}, il manifesto dice {want!r}"),
    "vocab_not_carried": ("{property}: the scheme {scheme} is neither carried by the package ([[data.vocabularies]]) "
                          "nor required ([requires].vocabularies)",
                          "{property}: lo schema {scheme} non è portato dal pacchetto ([[data.vocabularies]]) "
                          "né richiesto ([requires].vocabularies)"),
    "vocab_version_mismatch": ("{scheme}: the profile uses version {profile}, the envelope carries {envelope}",
                               "{scheme}: il profilo usa la versione {profile}, la busta porta la {envelope}"),
    "no_example": ("no example document (examples/*.em.json): a package shows how it is used",
                   "manca un documento d'esempio (examples/*.em.json): un pacchetto mostra come si usa"),
    "example_undeclared": ("{path}: the example does not declare the profile in header.profiles",
                           "{path}: l'esempio non dichiara il pacchetto in header.profiles"),
    "example_fallback": ("{path}: {why}", "{path}: {why}"),
    "part_missing": ("parts: {path!r} is not in the package", "parts: {path!r} non è nel pacchetto"),
    "range_bad": ("{where}: {value!r} is not a version nor a range", "{where}: {value!r} non è una versione né un intervallo"),
    "datamodel_checked": ("verified against {key} {checked}, here {current}: it is read all the same",
                          "verificato contro {key} {checked}, qui c'è la {current}: si legge lo stesso"),
    # envelope
    "env_key": ("em-extension.toml: {key} is required", "em-extension.toml: {key} è obbligatorio"),
    "env_id": ("em-extension.toml: id {value!r} — lowercase letters, digits, '-', '_' or '.', 2–64",
               "em-extension.toml: id {value!r} — lettere minuscole, cifre, '-', '_' o '.', da 2 a 64"),
    "env_schema_version": ("em-extension.toml: schema_version {value!r} — this library reads 1.x",
                           "em-extension.toml: schema_version {value!r} — questa libreria legge la 1.x"),
    "env_no_section": ("em-extension.toml: neither [data] nor [code]: a package has at least one",
                       "em-extension.toml: né [data] né [code]: un pacchetto ne ha almeno una"),
    "env_type": ("em-extension.toml: type {value!r} does not match the sections ({want})",
                 "em-extension.toml: type {value!r} non coincide con le sezioni ({want})"),
    "env_root": ("em-extension.toml: [{section}].root is required when the package has both sections",
                 "em-extension.toml: [{section}].root è obbligatoria quando il pacchetto ha tutte e due le sezioni"),
    "env_roots_overlap": ("em-extension.toml: the roots of [data] and [code] overlap ({data}, {code})",
                          "em-extension.toml: le radici di [data] e [code] si sovrappongono ({data}, {code})"),
    "env_profile_id": ("the envelope's id {env!r} is not the profile's name {name!r}",
                       "l'id della busta {env!r} non è il nome del profilo {name!r}"),
    "env_profile_version": ("[data].version {env!r} is not the profile's version {profile!r}",
                            "[data].version {env!r} non è la versione del profilo {profile!r}"),
    "env_license": ("em-extension.toml: license is a list of SPDX:<id>", "em-extension.toml: license è un elenco di SPDX:<id>"),
    "partition_code_in_data": ("{path}: an executable file in the data section — the data of a package carry no code",
                               "{path}: un file eseguibile nella sezione dati — i dati di un pacchetto non portano codice"),
    "partition_outside": ("{path}: outside the roots of the sections (only the envelope, LICENSE*, README*, CHANGELOG.md)",
                          "{path}: fuori dalle radici delle sezioni (solo la busta, LICENSE*, README*, CHANGELOG.md)"),
    "requires_part": ("[requires] {id}: part {part!r} — data, code or any", "[requires] {id}: part {part!r} — data, code o any"),
    "requires_code_optional": ("[requires] {id}: a dependency on code is always optional — the data are read without plugins",
                               "[requires] {id}: una dipendenza da codice è sempre facoltativa — i dati si leggono senza plugin"),
    "requires_self": ("[requires] {id}: a package cannot require itself", "[requires] {id}: un pacchetto non richiede se stesso"),
    "code_entry": ("[code]: entry is required (module:object)", "[code]: entry è obbligatoria (modulo:oggetto)"),
    "code_hosts": ("[code]: hosts {value!r} — emstudio, blender, server", "[code]: hosts {value!r} — emstudio, blender, server"),
    "permission_reason": ("[code.permissions] {name}: the reason is one sentence of at most 64 characters, without a final full stop",
                          "[code.permissions] {name}: il perché è una frase di al più 64 caratteri, senza punto finale"),
    "permission_unknown": ("[code.permissions] {name}: not a permission (files, network, clipboard, processes)",
                           "[code.permissions] {name}: non è un permesso (files, network, clipboard, processes)"),
    "tagline": ("em-extension.toml: tagline — at most 64 characters, without a final full stop",
                "em-extension.toml: tagline — al più 64 caratteri, senza punto finale"),
    "data_vocabulary": ("{message}", "{message}"),
    # installing and activating
    "version_reused": ("{name} {version} is already installed with other content: a version is not reused",
                       "{name} {version} è già installato con un contenuto diverso: una versione non si riusa"),
    "invalid": ("{name} {version}: the package has errors and is not installed", "{name} {version}: il pacchetto ha errori e non si installa"),
    "profile_missing": ("the file uses the community package {iri} {version}, which is not installed: it opens all the same, "
                        "with the labels saved in the values",
                        "il file usa il pacchetto di comunità {iri} {version}, che non è installato: si apre lo stesso, "
                        "con le etichette salvate nei valori"),
    "profile_other_version": ("the file uses {name} {version}; {installed} is installed and is read in its place",
                              "il file usa {name} {version}; è installata la {installed}, che si legge al suo posto"),
    "prefix_clash": ("{name} and {other} both use the prefix {prefix!r}: {name} is not activated",
                     "{name} e {other} usano tutti e due il prefisso {prefix!r}: {name} non si attiva"),
    "code_not_installed": ("the code section is installed apart, by s3dgraphy.extensions, with the trust question",
                           "la sezione di codice si installa a parte, da s3dgraphy.extensions, con la domanda di fiducia"),
    # installing by parts (s3dgraphy.extensions, W21)
    "ext_not_installed": ("{id} is not installed", "{id} non è installato"),
    "ext_no_source": ("{id}: the archive it came from is no longer at {origin}: choose it again",
                      "{id}: l'archivio da cui è arrivato non è più in {origin}: sceglilo di nuovo"),
    "ext_data_first": ("{id}: the code of a package needs its data {version} installed first",
                       "{id}: il codice di un pacchetto vuole prima i suoi dati {version} installati"),
    "code_trust_required": ("code not installed: the trust question was not answered",
                            "codice non installato: manca la risposta alla domanda di fiducia"),
    "code_user_choice": ("code not installed: the user's choice (data only)",
                         "codice non installato: scelta dell'utente (solo i dati)"),
    "code_removed": ("code removed by the user: the package is data only",
                     "codice rimosso dall'utente: il pacchetto è solo dati"),
    "code_invalid": ("code not installed: {problems}", "codice non installato: {problems}"),
    "code_platform": ("code not installed: it runs on {platforms}, this machine is {platform}",
                      "codice non installato: gira su {platforms}, questa macchina è {platform}"),
    "code_wheel_missing": ("[code] wheels: {path} is not in the package", "[code] wheels: {path} non è nel pacchetto"),
    "code_no_wheel": ("code not installed: no wheel of {dist} for {platform}",
                      "codice non installato: nessuna ruota di {dist} per {platform}"),
    "code_version_reused": ("code not installed: {id} code {version} is already installed with other content — a version is not reused",
                            "codice non installato: il codice {version} di {id} è già installato con un contenuto diverso — una versione non si riusa"),
    "code_updated": ("code updated {old} → {new}", "codice aggiornato {old} → {new}"),
    "data_beside": ("data {new} installed beside {old}: each file keeps the version it declares",
                    "dati {new} installati accanto a {old}: ogni file tiene la versione che dichiara"),
    "module_collision": ("the module {module} is already loaded by {other} {version}: disable it first",
                         "il modulo {module} è già caricato da {other} {version}: disattivalo prima"),
    "trust_changed": ("the code asks again: {changes} changed since the last trust",
                      "il codice chiede di nuovo: dall'ultima fiducia sono cambiati {changes}"),
    "requires_missing_data": ("incomplete: the data of {id} {range} are missing", "incompleto: mancano i dati di {id} {range}"),
    "requires_missing_code": ("incomplete: the code of {id} {range} is missing", "incompleto: manca il codice di {id} {range}"),
    "requires_missing_any": ("incomplete: {id} {range} is missing", "incompleto: manca {id} {range}"),
    "requires_missing_vocabulary": ("incomplete: the vocabulary {scheme} {range} is not installed",
                                    "incompleto: il vocabolario {scheme} {range} non è installato"),
    "requires_core": ("asks for EM {range}; this library is {version}", "chiede EM {range}; questa libreria è la {version}"),
    "requires_optional": ("optional function available: {id} {range} ({part}, not installed)",
                          "funzione facoltativa disponibile: {id} {range} ({part}, non installato)"),
    "requires_cycle": ("[requires]: a cycle — {cycle}", "[requires]: un ciclo — {cycle}"),
    "required_by": ("the data of {id} are required by {others}: confirm to remove them",
                    "i dati di {id} sono richiesti da {others}: conferma per rimuoverli"),
    "data_removes_code": ("removing the data of {id} removes its code {version} too",
                          "rimuovere i dati di {id} rimuove anche il suo codice {version}"),
}


@dataclass
class Problem:
    code: str
    level: str = ERROR
    where: str = ""
    params: Dict[str, Any] = field(default_factory=dict)

    def text(self, lang: str = "en") -> str:
        en, it = MESSAGES.get(self.code, ("{code}", "{code}"))
        tpl = it if str(lang).lower().startswith("it") else en
        try:
            body = tpl.format(**self.params)
        except (KeyError, IndexError, ValueError):
            body = f"{self.code} {self.params}"
        return f"{self.where}: {body}" if self.where and not body.startswith(self.where) else body

    def as_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "level": self.level, "where": self.where,
                "en": self.text("en"), "it": self.text("it")}

    def __str__(self) -> str:
        return self.text("en")


class Report:
    """The answer of a validation: errors and warnings, in order found."""

    def __init__(self) -> None:
        self.problems: List[Problem] = []

    def error(self, code: str, at: str = "", **params: Any) -> None:
        self.problems.append(Problem(code, ERROR, at, params))

    def warn(self, code: str, at: str = "", **params: Any) -> None:
        self.problems.append(Problem(code, WARNING, at, params))

    def extend(self, other: "Report") -> None:
        self.problems.extend(other.problems)

    @property
    def errors(self) -> List[Problem]:
        return [p for p in self.problems if p.level == ERROR]

    @property
    def warnings(self) -> List[Problem]:
        return [p for p in self.problems if p.level == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def codes(self, level: Optional[str] = None) -> List[str]:
        return [p.code for p in self.problems if level is None or p.level == level]

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "errors": [p.as_dict() for p in self.errors],
                "warnings": [p.as_dict() for p in self.warnings]}


class ProfileError(ValueError):
    """Raised when a package cannot be installed or read; carries the report."""

    def __init__(self, message: str, report: Optional[Report] = None):
        super().__init__(message)
        self.report = report if report is not None else Report()


__all__ = ["ERROR", "WARNING", "MESSAGES", "Problem", "Report", "ProfileError"]

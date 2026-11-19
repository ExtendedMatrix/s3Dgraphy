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
    # the vocabularies a package carries, one by one (W19: the tier against the licence)
    "vocab_entry_key": ("scheme and version are required", "scheme e version sono obbligatori"),
    "vocab_license_missing": ("{scheme}: no license — the tier is checked against it",
                              "{scheme}: manca license — la fascia si controlla contro di lei"),
    "vocab_tier_bad": ("{scheme}: fascia {value!r} — A, B or C (the licence allows {allowed})",
                       "{scheme}: fascia {value!r} — A, B o C (la licenza permette la {allowed})"),
    "vocab_tier_less_prudent": ("{scheme}: fascia {tier} is less prudent than the licence {license} allows (fascia {allowed})",
                                "{scheme}: la fascia {tier} è meno prudente di quanto permette la licenza {license} (fascia {allowed})"),
    "vocab_tier_c_file": ("{scheme}: fascia C is not redistributed — the package carries a pointer (fetch), not the file {path}",
                          "{scheme}: la fascia C non si ridistribuisce — il pacchetto porta un puntatore (fetch), non il file {path}"),
    "vocab_tier_c_fetch": ("{scheme}: fascia C needs fetch.url (where the source is)",
                           "{scheme}: la fascia C vuole fetch.url (dove sta la fonte)"),
    "vocab_path_missing": ("{scheme}: fascia {tier} — the file (path) is missing", "{scheme}: fascia {tier} — manca il file (path)"),
    "vocab_digest_missing": ("{scheme}: no digest (python -m s3dgraphy.extensions build computes it)",
                             "{scheme}: manca il digest (lo calcola python -m s3dgraphy.extensions build)"),
    "vocab_digest_mismatch": ("{scheme}: the digest does not match the file ({got}; build computes it again)",
                              "{scheme}: il digest non corrisponde al file ({got}; build lo ricalcola)"),
    # the archive as a whole (W19, the validator of the window and of the command line)
    "type_missing": ("em-extension.toml: no type — build writes {want!r}",
                     "em-extension.toml: manca type — build scrive {want!r}"),
    "vocab_path_in_profile": ("{scheme}: the file is named in qualia_vocabularies[].path (0.1) — build moves it to [[data.vocabularies]]",
                              "{scheme}: il file è nominato in qualia_vocabularies[].path (0.1) — build lo sposta in [[data.vocabularies]]"),
    "bare_profile": ("a bare profile, without em-extension.toml: it is read, but installed and distributed as an archive after build",
                     "un profilo nudo, senza em-extension.toml: si legge, ma si installa e si distribuisce come archivio dopo build"),
    "code_wheel_name": ("[code] wheels: {path} is not a wheel name (name-version-python-abi-platform.whl)",
                        "[code] wheels: {path} non è il nome di una ruota (nome-versione-python-abi-piattaforma.whl)"),
    "code_platform_unknown": ("[code] platforms: {value!r} — {known}", "[code] platforms: {value!r} — {known}"),
    "code_platform_wheel": ("[code]: declares {platform}, but no wheel of {dist} runs there",
                            "[code]: dichiara {platform}, ma nessuna ruota di {dist} gira lì"),
    "code_platforms_undeclared": ("[code]: platform wheels ({dists}) and no platforms — the archive would claim every platform",
                                  "[code]: ruote per piattaforma ({dists}) e nessuna platforms — l'archivio direbbe di girare ovunque"),
    "code_outside_root": ("[code]: the code root {root} is not in the archive", "[code]: la radice del codice {root} non è nell'archivio"),
    # the index of a repository (X1, python -m s3dgraphy.extensions server-generate)
    "index_no_folder": ("{path}: not a folder", "{path}: non è una cartella"),
    "index_unreadable": ("the archive cannot be read: {why}", "l'archivio non si legge: {why}"),
    "index_no_envelope": ("a bare profile is not listed: build it first (python -m s3dgraphy.extensions build)",
                          "un profilo nudo non si elenca: prima build (python -m s3dgraphy.extensions build)"),
    "index_file_name": ("the archive is usually named {want}", "di solito l'archivio si chiama {want}"),
    "index_blocked": ("{id} is in the blocklist: not listed", "{id} è tra i ritirati: non si elenca"),
    "index_list_unreadable": ("{path}: not JSON ({why})", "{path}: non è JSON ({why})"),
    "index_list_shape": ("{path}: a list of objects with id (or {{\"{key}\": [...]}})",
                         "{path}: un elenco di oggetti con id (o {{\"{key}\": [...]}})"),
    "index_block_reason": ("blocklist: {id} has no reason (the window shows it)",
                           "ritirati: {id} non ha reason (la finestra la mostra)"),
    "index_review_shape": ("reviewed: {id} needs digest (sha256:…), by and on",
                           "rivisti: {id} vuole digest (sha256:…), by e on"),
    "index_duplicate": ("{id} {version} is already listed by {other}", "{id} {version} è già elencato da {other}"),
    "index_section_reused": ("{id}: [{section}] {version} has another content in {other} — a version is never reused",
                             "{id}: [{section}] {version} ha un altro contenuto in {other} — una versione non si riusa"),
    "index_vocab_conflict": ("{scheme} {version}: another content in {other} — a vocabulary version is never reused",
                             "{scheme} {version}: un altro contenuto in {other} — una versione di vocabolario non si riusa"),
    "index_vocab_owner": ("{scheme}: owned by {owner}, which this repository publishes — require it, do not copy it",
                          "{scheme}: il padrone è {owner}, che questo repository pubblica — richiedilo, non copiarlo"),
    "index_vocab_not_owner": ("{scheme}: owned by {owner} — when {owner} is published, require it instead of copying it",
                              "{scheme}: il padrone è {owner} — quando {owner} è pubblicato, richiedilo invece di copiarlo"),
    "index_vocab_central": ("{scheme}: a shared vocabulary of ExtendedMatrix/vocabularies — require it, do not copy it",
                            "{scheme}: un vocabolario condiviso di ExtendedMatrix/vocabularies — richiedilo, non copiarlo"),
    "index_requires_elsewhere": ("[requires] {id}: not in this repository (another one must have it)",
                                 "[requires] {id}: non è in questo repository (deve averlo un altro)"),
    "index_requires_cycle": ("[requires] in a cycle: {cycle}", "[requires] in un ciclo: {cycle}"),
    "index_shape": ("not an index: {why}", "non è un indice: {why}"),
    "index_version": ("index version {value!r}: this library reads {want!r}",
                      "versione dell'indice {value!r}: questa libreria legge {want!r}"),
    "index_entry_fields": ("missing: {keys}", "mancano: {keys}"),
    "index_entry_hash": ("archive_hash {value!r} is not sha256:<64 hex>", "archive_hash {value!r} non è sha256:<64 hex>"),
    "index_size_mismatch": ("{id}: the download has {got} bytes, the index says {want}",
                            "{id}: lo scaricato ha {got} byte, l'indice dice {want}"),
    "index_hash_mismatch": ("{id}: the download is not the archive the index names ({got}, not {want})",
                            "{id}: lo scaricato non è l'archivio che l'indice nomina ({got}, non {want})"),
    "index_differs": ("{path} is not the index of these archives: run server-generate again",
                      "{path} non è l'indice di questi archivi: rilancia server-generate"),
    # the repositories of this machine (X2)
    "repo_url_bad": ("{url}: not the address of a repository (https://…/index.json, file://…, or a folder)",
                     "{url}: non è l'indirizzo di un repository (https://…/index.json, file://… o una cartella)"),
    "repo_name_bad": ("{name}: a repository's name is lower-case letters, digits, - and _ (and not a reserved word)",
                      "{name}: il nome di un repository è fatto di minuscole, cifre, - e _ (e non è una parola riservata)"),
    "repo_name_used": ("a repository called {name} is already here", "c'è già un repository di nome {name}"),
    "repo_url_used": ("{url} is already here, as {name}", "{url} c'è già, come {name}"),
    "repo_unknown": ("no repository called {name}", "nessun repository di nome {name}"),
    "repo_offline": ("{url}: online access is off («Allow online access»)",
                     "{url}: l'accesso in rete è spento («Consenti l'accesso in rete»)"),
    "repo_unreachable": ("{url}: cannot be read ({why})", "{url}: non si riesce a leggere ({why})"),
    "repo_denied": ("{url}: access refused ({status}) — check the access token",
                    "{url}: accesso negato ({status}) — controlla il token di accesso"),
    "repo_http": ("{url}: the server answered {status}", "{url}: il server ha risposto {status}"),
    "repo_too_big": ("{url}: more than {limit} bytes, not read", "{url}: più di {limit} byte, non letto"),
    "repo_index_bad": ("{name}: the index is not a repository's index ({why}); the previous copy is kept",
                       "{name}: l'indice non è l'indice di un repository ({why}); resta la copia di prima"),
    "repo_not_synced": ("{name}: the index has not been read yet — «Refresh» first",
                        "{name}: l'indice non è ancora stato letto — prima «Aggiorna l'elenco»"),
    "repo_no_entry": ("{repo} does not offer {id} {version}", "{repo} non offre {id} {version}"),
    "repo_blocked": ("{id} was withdrawn by {repo}: {reason}", "{id} è stato ritirato da {repo}: {reason}"),
    "repo_blocked_installed": ("{id} is installed here, and {repo} has withdrawn it: {reason}",
                               "{id} è installato qui, e {repo} lo ha ritirato: {reason}"),
    "repo_requires_unresolved": ("{for} requires {id} {range}, which no repository offers: it installs incomplete",
                                 "{for} richiede {id} {range}, che nessun repository offre: si installa incompleto"),
    "repo_tier_c_no_url": ("{id}: tier C without a source to fetch from", "{id}: fascia C senza una fonte da cui scaricarlo"),
    "repo_tier_c_offline": ("{id}: tier C, not fetched — online access is off; «Download locally» from {url} later",
                            "{id}: fascia C, non scaricato — l'accesso in rete è spento; «Scarica in locale» da {url} più tardi"),
    "repo_tier_c_failed": ("{id}: tier C, not fetched ({why})", "{id}: fascia C, non scaricato ({why})"),
    # build (W19)
    "build_folder": ("build reads a folder, not {what}: unzip it first", "build legge una cartella, non {what}: prima scompattala"),
    "build_written": ("type = {value!r} written", "scritto type = {value!r}"),
    "build_moved": ("{scheme}: {path} moved from qualia_vocabularies to [[data.vocabularies]] (fascia {tier}, {license})",
                    "{scheme}: {path} spostato da qualia_vocabularies a [[data.vocabularies]] (fascia {tier}, {license})"),
    "build_vocab_license": ("{scheme}: {path} has no licence and the profile has not one licence — write license in qualia_vocabularies",
                            "{scheme}: {path} non ha licenza e il profilo non ne ha una sola — scrivi license in qualia_vocabularies"),
    "build_digest": ("{what}: digest {old} → {new}", "{what}: digest {old} → {new}"),
    "build_requires_profile": ("[requires] copied into profile.json requires (for a 0.2 reader without the envelope)",
                               "[requires] ricopiato in profile.json requires (per un lettore 0.2 senza busta)"),
    "build_requires_iri": ("[requires] {id} ({part}): no IRI known for it — not copied into profile.json",
                           "[requires] {id} ({part}): non se ne conosce l'IRI — non ricopiato in profile.json"),
    "build_requires_translated": ("[requires].profiles {iri} → extensions {id} (part = data)",
                                  "[requires].profiles {iri} → extensions {id} (part = data)"),
    "build_code_optional": ("[requires] {id}: a dependency on code is always optional — optional = true written",
                            "[requires] {id}: una dipendenza da codice è sempre facoltativa — scritto optional = true"),
    "build_requires_core": ("[requires].core taken from profile.json requires", "[requires].core preso da profile.json requires"),
    "build_envelope_made": ("em-extension.toml made from profile.json (a bare profile becomes an archive)",
                            "em-extension.toml ricavato da profile.json (un profilo nudo diventa un archivio)"),
    "build_refused": ("the archive was not written: {count} errors", "l'archivio non è stato scritto: {count} errori"),
    "build_toml": ("em-extension.toml: {why}", "em-extension.toml: {why}"),
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
    # W14 (MICRO-PL17) · the commands of a plugin, their slots, the descriptor
    "code_commands_shape": ("[[code.commands]]: a list of tables", "[[code.commands]]: un elenco di tabelle"),
    "code_command_id": ("[[code.commands]] {id}: the id is a letter, then letters, digits, «.», «_», «-»",
                        "[[code.commands]] {id}: l'id è una lettera, poi lettere, cifre, «.», «_», «-»"),
    "code_command_twice": ("[[code.commands]] {id}: declared twice", "[[code.commands]] {id}: dichiarato due volte"),
    "code_command_label": ("[[code.commands]] {id}: a label is required (a text, or {{it, en}})",
                           "[[code.commands]] {id}: serve un'etichetta (un testo, o {{it, en}})"),
    "code_command_writes": ("[[code.commands]] {id}: writes is true or false", "[[code.commands]] {id}: writes è true o false"),
    "code_command_slots": ("[[code.commands]] {id}: slots is a list of {{name, kind}} — kinds {kinds}",
                           "[[code.commands]] {id}: slots è un elenco di {{name, kind}} — i tipi {kinds}"),
    "code_command_in": ("[[code.commands]] {id}: in — {value!r} is not a slot (name@version)",
                        "[[code.commands]] {id}: in — {value!r} non è uno slot (nome@versione)"),
    "code_command_when": ("[[code.commands]] {id}: when {value!r} does not read (document, selection:none|any|one|many|TYPE|TYPE, joined by «and»)",
                          "[[code.commands]] {id}: when {value!r} non si legge (document, selection:none|any|one|many|TIPO|TIPO, uniti da «and»)"),
    "code_reader_accept": ("[[code.commands]] {id}: a reader (door.reader@1) declares accept = [\".ext\", …]",
                           "[[code.commands]] {id}: un lettore (door.reader@1) dichiara accept = [\".ext\", …]"),
    "code_check_writes": ("[[code.commands]] {id}: a check (check@1) only reads: writes = false",
                          "[[code.commands]] {id}: un controllo (check@1) legge soltanto: writes = false"),
    "code_slot_unknown": ("[[code.commands]] {id}: the slot {slot} is not known here: the command is not drawn there",
                          "[[code.commands]] {id}: lo slot {slot} qui non esiste: il comando lì non compare"),
    "code_slot_phase2": ("[[code.commands]] {id}: the slot {slot} comes with phase 2: not drawn yet",
                         "[[code.commands]] {id}: lo slot {slot} arriva con la fase 2: per ora non compare"),
    "code_slot_newer": ("[[code.commands]] {id}: the slot {slot} is newer than this host's: that entry is turned off",
                        "[[code.commands]] {id}: lo slot {slot} è più nuovo di quello di questo programma: quella voce è spenta"),
    "code_slot_not_command": ("[[code.commands]] {id}: {slot} is a call of the API, not a place for a command",
                              "[[code.commands]] {id}: {slot} è una chiamata dell'API, non un posto per un comando"),
    "code_descriptor": ("[code.descriptor]: a table with capabilities = [ … ]", "[code.descriptor]: una tabella con capabilities = [ … ]"),
    "code_capability_unknown": ("[code.descriptor]: unknown capability {value!r} — {known}",
                                "[code.descriptor]: capability sconosciuta {value!r} — {known}"),
    "code_writes_no_capability": ("[[code.commands]] {id}: writes, and the descriptor declares no writing capability: every write will be refused",
                                  "[[code.commands]] {id}: scrive, e il descrittore non dichiara una capability di scrittura: ogni scrittura sarà rifiutata"),
    "code_updated": ("code updated {old} → {new}", "codice aggiornato {old} → {new}"),
    "data_beside": ("data {new} installed beside {old}: each file keeps the version it declares",
                    "dati {new} installati accanto a {old}: ogni file tiene la versione che dichiara"),
    "module_collision": ("the module {module} is already loaded by {other} {version}: disable it first",
                         "il modulo {module} è già caricato da {other} {version}: disattivalo prima"),
    "trust_changed": ("the code asks again: {changes} changed since the last trust",
                      "il codice chiede di nuovo: dall'ultima fiducia sono cambiati {changes}"),
    # W15a (MICRO-PL18) · the trust from disk: the development folder
    "dev_dir_missing": ("the development folder {path} is not a folder of this machine",
                        "la cartella di sviluppo {path} non è una cartella di questa macchina"),
    "dev_no_code": ("{folder}: no [code] section, nothing to load", "{folder}: nessuna sezione [code], niente da caricare"),
    "dev_not_a_package": ("{folder}: not an extension ({why})", "{folder}: non è un'estensione ({why})"),
    "dev_same_id": ("{id} from the development folder ({folder}) and {id} from {other}: the first is loaded",
                    "{id} dalla cartella di sviluppo ({folder}) e {id} da {other}: si carica il primo"),
    "dev_hides_installed": ("the development copy of {id} hides the installed {version} while it is in the development folder",
                            "la copia di sviluppo di {id} nasconde la {version} installata finché sta nella cartella di sviluppo"),
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

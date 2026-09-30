# MICRO — dtcstamp: la risorsa di più file, il digest del contenuto e il profilo del 3tz

**Repo:** `~/Documents/GitHub/dtcstamp`, dopo `153bb88`. Un commit per parte. Git in sola lettura più commit: niente stash, checkout o reset.
**Solo lettura:** `s3Dgraphy` (dopo il MICRO-REVISIONE, `0bbf68a`: la costante `CANONICAL_3TZ_PROFILE` in `resources/tiles3tz.py` e le fixture `tests/fixtures/tiles3tz/`), `3D-survey-collection` (`cesium_exporter/archive_3tz.py`, commit `1430128`), `EMStudio`.
**Materiali:** la base di prova `~/Library/CloudStorage/OneDrive-CNR/Extended Matrix/EM_CaseStudies/01_EM_Tempio Grande/_base_EMStudio/` (leggi il `README.md`). **Non scrivere dentro la base.**

Regola d'oro: misura, non dedurre. Il referto va in `dtcstamp/.claude/wip/reports/2026-10-21-piu-file/` se `.claude/` è ignorato da git in dtcstamp; altrimenti in `s3Dgraphy/.claude/wip/reports/`, e dillo.

Decisioni di E.D. del 30 set (brain: `decisioni/la-risorsa-e-i-suoi-file.md`):
- il `ResourceNode` è l'insieme, il `ResourceFileNode` è ogni file. In s3Dgraphy (`8652737`…`e0a571a`) ci sono già `file_set` e `datablock`, e l'arco `has_file` con ruolo e percorso;
- **il digest di una risorsa di più file è il digest della lista ordinata ruolo / percorso / checksum**, in una forma canonica fissata qui;
- **un tileset ha due identità**: lo sha256 del `.3tz` identifica quel file; il digest della lista (percorso, sha256) identifica il contenuto, uguale per la cartella e per il `.3tz`. Lo calcola chi produce;
- **un solo profilo `.3tz`, quello di 3DSC**, con un caso di conformità comune.

Sostituisce il MICRO-TIMBRO-CARTELLA sospeso (13 ott), che resta sospeso per la parte «cartella grande timbrata a posteriori».

## Parte 1 — il formato (`stamp-format.md`)

- **`self.packaging`** prende un vocabolario enumerato: `file`, `file_set`, `directory`, `archive`, `datablock` (misura i valori già usati nel corpus e in s3Dgraphy e allineali).
- **`digest_covers: members`**: il digest copre la lista dei membri. La **forma canonica**, fissata byte per byte:
  - una riga per membro: `ruolo`, `percorso`, `sha256:<hex>`, separati da un carattere che non può stare in un percorso;
  - percorsi normalizzati (barre in avanti, niente barra iniziale, UTF-8 NFC);
  - righe in ordine di percorso;
  - fine riga fissa.
  
  Il digest è lo sha256 di quel testo. La lista sta **dentro il timbro** (`self.members`), perché le risorse `file_set` hanno pochi file.
- **`content_digest`** per un albero (cartella o `.3tz`): la stessa forma, con tutti i file dell'albero e ruolo `member`, tranne `tileset.json` che è `entry_point`. **Non** si elenca nel timbro quando i file sono migliaia: il timbro porta il digest, il numero di file e chi l'ha calcolato (`computed_by`: il produttore all'export, o il timbratore dopo). Una cartella e il suo `.3tz` hanno lo stesso `content_digest`.
- **Il legame tra le forme**: il timbro del `.3tz` porta il suo sha256 come digest del file e `content_digest` come identità del contenuto. Misura come EMtools lega `_link` e `_archive`, e usa la stessa parola per dire «stessa cosa, altra forma».
- **Il profilo `.3tz` canonico**, in una sezione o in un file `profiles/3tz.md`:
  - voci in ordine di percorso;
  - data 1980-01-01, `create_system` 3, attributi 0o100644;
  - STORED;
  - `.DS_Store` e `Thumbs.db` esclusi;
  - indice `@3dtilesIndex1@` ultimo e STORED, ordinato per MD5 come due uint64 LE.
  
  Il profilo è preso da `3D-survey-collection/cesium_exporter/archive_3tz.py` (`1430128`), lo stesso della costante `CANONICAL_3TZ_PROFILE` di s3Dgraphy: se i due non coincidono, fermati e dillo. Rimando alla specifica 3tz v1.3. Il 3tz di `3d-tiles-tools` 0.5.4 non è canonico per due ragioni misurate: l'ora di scrittura in ogni voce e il bit «archivio» del DOS negli attributi (`0x81a40020`).
- Se l'aggiunta cambia la versione del formato, dillo; se resta compatibile, scrivi perché.

## Parte 2 — il codice (`dtcstamp.py`)

- **`members_digest(members)`**: la forma canonica e il suo sha256.
- **`content_digest(path)`**, per una cartella o un `.3tz`:
  - legge i file a blocchi;
  - per il `.3tz` legge le voci dall'indice senza estrarre, e ignora l'indice stesso;
  - una cartella e il suo `.3tz` danno lo stesso valore.
- **`is_canonical_3tz(path)`**: dice se l'archivio segue il profilo e, se no, perché.
- **Timbrare una risorsa `file_set`**: dall'entry point si seguono `mtllib` e `map_*` (obj) oppure `buffers` e `images` (glTF), anche in sottocartelle. Un riferimento assoluto o che esce dalla cartella con `../` dà un avviso; i file che nessuno chiama restano fuori e si elencano.
- **Il sidecar** è uno, accanto alla porta (`OB_PODIO_LOD1.obj.stamp.json`, o come misuri sia già la regola per un file). **Un tetto** di membri per `file_set` (misura e proponi, per esempio 64): oltre, si rimanda al `content_digest` di un albero.
- **La verifica**: un membro mancante, cambiato o in più. Un membro in due risorse (una texture condivisa) è permesso: misura come si comporta la verifica.
- **Test sul vero**: su una copia di una tile per livello, `LOD1/OB_PODIO_LOD1.obj` dà 3 membri e `LOD0/OB_PODIO_LOD0.obj` 6; un byte cambiato in una texture rompe la verifica; togliere il mtl lo dice. Scrivi quanto costa timbrare le 33 tile (1,7 GB).
- **Il datablock**: `packaging: datablock` con il locator `blend://` (misura la forma in `s3dgraphy/resources/resolver.py`); nessun digest dei byte, e lo si dice.

## Parte 3 — la conformità

Nuovi casi in `conformance/`:
- **una risorsa `file_set`** (un obj con mtl e due texture, piccolo e generato), con il `members_digest` atteso;
- **un tileset piccolo in cartella e lo stesso in `.3tz`** scritto con il profilo, con lo sha256 atteso del `.3tz` e il `content_digest` atteso, che deve essere lo stesso per le due forme. Questo è il caso che ogni scrittore (3DSC, EMStudio) deve riprodurre: scrivi nel README di conformità come si usa;
- **un `.3tz` non canonico** (riusa la fixture di `3d-tiles-tools` in `s3Dgraphy/tests/fixtures/tiles3tz/`): `is_canonical_3tz` dice no, e il `content_digest` resta uguale a quello canonico;
- **un datablock**.

E una misura sul vero: il `.3tz` di TempluMare nella base (sha256 `232dfcbc…`) è canonico. Scrivi il suo `content_digest` e controlla che coincida con quello della cartella `RM/TempluMare_cesium/` (7302 file, tempo misurato).

## Verifica

`pytest test_dtcstamp.py` e il corpus di conformità: tutti verdi. Scrivi i numeri di prima e di dopo.

## Fine

Blocco `END OF MICRO-DTCSTAMP-PIU-FILE` compilato e stampato in chat:
- i commit;
- il vocabolario di `packaging` e `digest_covers: members`;
- la forma canonica della lista, e il `content_digest` di un albero;
- il profilo `.3tz` e dove sta;
- i casi di conformità nuovi e i loro valori attesi;
- TempluMare: canonico sì o no, `content_digest` di cartella e `.3tz`, tempi;
- cosa devono fare 3DSC (calcolare il `content_digest` all'export), EMStudio ed EMtools.

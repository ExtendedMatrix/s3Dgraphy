#!/usr/bin/env bash
# verifica-provenance · la wheel appena pubblicata porta la sua attestazione
#
#   ./scripts/verifica-provenance.sh 1.6.0.dev22
#   ATTESA_TOTALE=600 ./scripts/verifica-provenance.sh 1.6.0.dev26   # aspetta fino a 10 min
#
# ── LA DOMANDA ───────────────────────────────────────────────────────────────
#
# Un publish riuscito senza provenance è un publish che ha fatto metà del
# lavoro e lo dichiara riuscito. Non è un'ipotesi: è lo stato in cui questa
# libreria si trovava fino a dev20. Misurato il 22 settembre 2026 —
#
#   s3dgraphy 1.6.0.dev18 → /integrity/…/provenance
#   → 404  {"message":"No provenance available"}
#
# — e nessuno se n'era accorto perché nessuno l'aveva chiesto all'indice. Tre
# servizi installano questa wheel e finisce dentro le immagini che consegniamo
# a un partner: chi le specchia può risalire al Dockerfile, al commit, al tag,
# e poi arriva alla wheel e la catena si interrompe.
#
# ── PERCHÉ ORA C'È UN RITENTATIVO: 404 È UNA RISPOSTA, 503 NO ────────────────
#
# Il 28 settembre 2026 questo script ha dichiarato ROSSO un publish che era
# perfettamente riuscito, e ha aggiunto una diagnosi sbagliata: «PyPI non
# conosce ancora questo Trusted Publisher, o il publish è passato da un token».
# Nessuna delle due. Le misure di quella mattina, nello stesso quarto d'ora:
#
#   dev22  → 503, 503        e venti minuti dopo → 200, 200 (ExtendedMatrix/s3Dgraphy)
#   dev21  → 200, 200        (pubblicata il giorno prima, mai in dubbio)
#   dev18  → 503             e venti minuti dopo → 404   ← la stessa assenza,
#                                                          due codici diversi
#   packaging 25.0 → 404 sulla wheel e 503 sul sorgente, nella STESSA chiamata
#
# Cioè: l'indice, sotto carico, risponde 5xx a tutto — a ciò che ha e a ciò che
# non ha. Uno script che conta ogni risposta non-200 come «assente» trasforma
# un disservizio momentaneo di PyPI in un'accusa alla nostra configurazione, e
# manda a rimettere mano a un Trusted Publisher che funziona. È lo stesso
# difetto che questo file esiste per combattere, al contrario: là si leggeva
# verde senza aver chiesto, qui si leggeva rosso senza aver ascoltato.
#
# ── E IL 1 OTTOBRE: ANCHE IL 404, APPENA PUBBLICATO, NON È UNA RISPOSTA ──────
#
# Fino a quel giorno la regola era «404 è una risposta, non si ritenta». Il run
# della dev25 l'ha smentita, e con le misure in mano:
#
#   05:19:53  l'upload su PyPI è finito (il passo prima di questo, verde)
#   05:19:57  questo script parte, quattro secondi dopo
#             /pypi/s3dgraphy/1.6.0.dev25/json → 404, 404, 404, 404 in ~7 s
#             («non risulta su PyPI»: job ROSSO, pubblicazione RIUSCITA)
#   ~06:20    lo stesso script, a mano → «2 file su 2 con provenance»
#
# L'indice JSON di PyPI sta dietro una CDN, e una versione appena caricata ci
# arriva dopo qualche decina di secondi, a volte minuti. In quella finestra il
# 404 non dice «non c'è»: dice «non ancora». È lo stesso errore del 28
# settembre, col codice diverso — scambiare la lentezza dell'indice per un
# verdetto sulla nostra configurazione.
#
# Quindi si ASPETTA, e la ragione per cui non è più la scorciatoia che il vecchio
# commento temeva («coprire con l'attesa il caso che il cancello deve vedere»):
# l'attesa ha un TETTO, e allo scadere il verdetto è ancora rosso. Il 404 che
# resta 404 per cinque minuti su una versione che l'indice ormai mostra è
# un'assenza vera; costa cinque minuti invece di sette secondi, e smette di
# accusare chi non ha colpa.
#
# ── LA REGOLA, ORA ───────────────────────────────────────────────────────────
#
# Un'attesa sola, condivisa da tutte le domande: ATTESA_TOTALE secondi (300 di
# default), tentativi a intervalli che crescono — ATTESA_INIZIALE, il doppio, il
# doppio… (5, 10, 20, 40, 60, 60…) — ciascuno al più ATTESA_TETTO (60). A ogni
# tentativo una riga, «tentativo 3/8, prossimo fra 20 s», così nel log del
# workflow si vede che sta aspettando e non che si è piantato.
#
#   1. /pypi/<pacchetto>/<versione>/json — la versione si vede?
#        200 → sì, e dice quali file ha;   altro → si riprova.
#   2. per ogni file, /integrity/…/provenance — c'è l'attestazione?
#        200 → sì;   altro → si riprova (anche 404: la provenance può arrivare
#        all'indice dopo il file).
#   3. l'attestazione nomina QUESTO repository?
#
# ── COSA CONTROLLA, E COSA NO ────────────────────────────────────────────────
#
# Controlla che PyPI SERVA un'attestazione per ciascun file di quella versione,
# e che quell'attestazione nomini QUESTO repository. Non verifica la firma
# crittograficamente: quello lo fa PyPI quando la accetta, e rifarlo qui
# vorrebbe dire portarsi dietro sigstore per ridire una cosa già detta.
#
# USCITE — tre rossi diversi, perché meritano tre consigli diversi:
#    0  verde: ogni file ha la provenance, e nomina questo repository;
#   75  «pubblicata? non ancora visibile»: allo scadere dell'attesa l'indice non
#       mostra la versione, o non ha risposto (5xx/rete) per un suo file. Non
#       dice niente sul publish né sul Trusted Publisher: si rilancia più tardi;
#    1  errore vero: la versione si vede, e un suo file è senza provenance
#       (404 fino alla fine);
#    3  errore vero: la provenance c'è, ma nomina un ALTRO repository;
#    2  uso sbagliato (manca la versione).
#
# Per i test (tests/test_verifica_provenance.py) l'indice si sposta con
# PYPI_URL, e l'attesa si accorcia con le tre variabili qui sopra.
set -euo pipefail

VERSIONE="${1:-}"
PACCHETTO="${PACCHETTO:-s3dgraphy}"
PYPI_URL="${PYPI_URL:-https://pypi.org}"
ATTESA_TOTALE="${ATTESA_TOTALE:-300}"
ATTESA_INIZIALE="${ATTESA_INIZIALE:-5}"
ATTESA_TETTO="${ATTESA_TETTO:-60}"
#: dentro Actions è il contesto; fuori è il remote. Nessun letterale: è la
#: lezione di `check-owner.mjs` in EMStudio, e vale qui per lo stesso motivo.
ATTESO="${GITHUB_REPOSITORY:-}"
if [ -z "$ATTESO" ]; then
  remote="$(git remote get-url origin 2>/dev/null || true)"
  ATTESO="$(printf '%s' "$remote" | sed -n 's#.*github\.com[/:]\([^/]*\)/\([^/]*\)#\1/\2#p' | sed 's/\.git$//')"
fi

if [ -z "$VERSIONE" ]; then
  echo "uso: $0 <versione>   (es. 1.6.0.dev22)" >&2
  exit 2
fi

echo "▶ provenance di $PACCHETTO $VERSIONE"
[ -n "$ATTESO" ] && echo "  repository atteso nell'attestazione: $ATTESO"
echo "  attesa massima ${ATTESA_TOTALE} s (intervalli da ${ATTESA_INIZIALE} s, al più ${ATTESA_TETTO} s)"

#: la scadenza è UNA, per tutte le domande: «circa cinque minuti in tutto».
SCADENZA=$((SECONDS + ATTESA_TOTALE))

#: quanti tentativi stanno nel tempo che resta, con gli intervalli che crescono:
#: serve a scrivere «3/8» e non «3/?». Ultimo intervallo accorciato al resto.
quanti_tentativi() {
  local resto=$((SCADENZA - SECONDS)) passo="$ATTESA_INIZIALE" n=1
  while [ "$resto" -gt 0 ]; do
    n=$((n + 1))
    resto=$((resto - passo))
    passo=$((passo * 2)); [ "$passo" -gt "$ATTESA_TETTO" ] && passo="$ATTESA_TETTO"
  done
  echo "$n"
}

#: una risposta, o la confessione di non averla. NON stampa la risposta: lascia
#: il corpo in $JSON e lo stato in $STATO. Il motivo è una trappola vera, in cui
#: questo file è cascato appena scritto — `json="$(interroga …)"` esegue la
#: funzione in una SUBSHELL, e le variabili che assegna muoiono lì. Stampa
#: invece, su stderr, una riga per ogni tentativo che non è andato.
STATO=""
FATTI=0
JSON=""
interroga() {
  local url="$1" cosa="$2" passo="$ATTESA_INIZIALE" totale i=0 corpo resto
  totale="$(quanti_tentativi)"
  while :; do
    i=$((i + 1)); FATTI="$i"
    corpo="$(curl -sS -m 30 -w '\n%{http_code}' "$url" 2>/dev/null || printf '\n000')"
    STATO="$(printf '%s' "$corpo" | tail -1)"
    [ "$STATO" = "200" ] && break
    resto=$((SCADENZA - SECONDS))
    if [ "$resto" -le 0 ]; then
      echo "    $cosa: tentativo $i/$totale, HTTP $STATO — attesa finita" >&2
      break
    fi
    [ "$passo" -gt "$resto" ] && passo="$resto"
    [ "$i" -ge "$totale" ] && totale=$((i + 1))
    echo "    $cosa: tentativo $i/$totale, HTTP $STATO — prossimo fra $passo s" >&2
    sleep "$passo"
    passo=$((passo * 2)); [ "$passo" -gt "$ATTESA_TETTO" ] && passo="$ATTESA_TETTO"
  done
  JSON="$(printf '%s' "$corpo" | sed '$d')"
}

non_visibile() {
  echo
  echo "── pubblicata? non ancora visibile ──"
  echo "Dopo ${ATTESA_TOTALE} s l'indice di PyPI $1. Questo NON dice che il"
  echo "publish è fallito né che il Trusted Publisher è sbagliato: l'indice"
  echo "sta dietro una CDN e una versione appena caricata ci arriva in ritardo"
  echo "(il 1 ottobre: ~7 s non bastavano, un'ora dopo era tutto verde)."
  echo "Rilancia più tardi, anche con un'attesa più lunga:"
  echo
  echo "    ATTESA_TOTALE=600 ./scripts/verifica-provenance.sh $VERSIONE"
  echo
  echo "Il job resta rosso perché «non verificato» non è «verificato»."
  exit 75
}

interroga "$PYPI_URL/pypi/$PACCHETTO/$VERSIONE/json" "indice $PACCHETTO $VERSIONE"
if [ "$STATO" != "200" ]; then
  non_visibile "non mostra $PACCHETTO $VERSIONE (ultimo HTTP $STATO)"
fi
files="$(printf '%s' "$JSON" \
         | python3 -c 'import sys,json; d=json.load(sys.stdin); print("\n".join(u["filename"] for u in d["urls"]))' \
         2>/dev/null || true)"
if [ -z "$files" ]; then
  non_visibile "mostra $PACCHETTO $VERSIONE senza alcun file"
fi
echo "  ✓ l'indice mostra $VERSIONE$([ "$FATTI" -gt 1 ] && echo " [dopo $FATTI tentativi]")"

assenti=0
altrove=0
ignoti=0
n=0
for f in $files; do
  n=$((n + 1))
  interroga "$PYPI_URL/integrity/$PACCHETTO/$VERSIONE/$f/provenance" "$f"
  json="$JSON"
  ripetuto=""
  [ "$FATTI" -gt 1 ] && ripetuto=" [dopo $FATTI tentativi]"

  if [ "$STATO" = "404" ]; then
    echo "  ✗ $f — nessuna provenance (404 fino allo scadere dell'attesa)$ripetuto"
    assenti=$((assenti + 1))
    continue
  fi
  if [ "$STATO" != "200" ]; then
    echo "  ? $f — l'indice non ha risposto (HTTP $STATO) fino allo scadere dell'attesa"
    ignoti=$((ignoti + 1))
    continue
  fi

  #: e non basta che risponda: l'attestazione deve nominare QUESTO repository.
  #: Una provenance che dice «nata altrove» è peggio di nessuna provenance,
  #: perché sembra una garanzia.
  dove="$(printf '%s' "$json" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); raise SystemExit
visti = set()
def cerca(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("repository", "sourceRepositoryURI", "source_repository_uri") \
               and isinstance(v, str):
                visti.add(v.rstrip("/").split("github.com/")[-1])
            cerca(v)
    elif isinstance(o, list):
        for v in o:
            cerca(v)
cerca(d)
print(" ".join(sorted(visti)))
' 2>/dev/null || true)"

  if [ -n "$ATTESO" ] && [ -n "$dove" ] && ! printf '%s' " $dove " | grep -q " $ATTESO "; then
    echo "  ✗ $f — l'attestazione nomina «${dove}», non «${ATTESO}»"
    altrove=$((altrove + 1))
    continue
  fi
  echo "  ✓ $f — provenance presente${dove:+ ($dove)}$ripetuto"
done

rosse=$((assenti + altrove + ignoti))
echo
if [ "$rosse" -eq 0 ]; then
  echo "── $n file su $n con provenance ──"
  exit 0
fi

echo "── $((n - rosse)) su $n con provenance · $assenti assenti · $altrove altrove · $ignoti indeterminati ──"
echo
#: tre guasti diversi meritano tre consigli diversi. Una frase sola per tutti
#: manderebbe a riconfigurare PyPI chi ha invece un indice che non risponde —
#: ed è successo, il 28 settembre.
if [ "$altrove" -gt 0 ]; then
  echo "L'attestazione c'è ma nomina un ALTRO repository ($altrove file), e"
  echo "questo è più grave della sua assenza: una provenance che dice «nata"
  echo "altrove» sembra una garanzia. O il Trusted Publisher su PyPI punta al"
  echo "repository sbagliato, o questa versione l'ha pubblicata qualcun altro."
  echo
  exit 3
fi
if [ "$assenti" -gt 0 ]; then
  echo "MANCA l'attestazione ($assenti file): la versione si vede, e l'indice ha"
  echo "risposto 404 per tutti i ${ATTESA_TOTALE} s. O PyPI non conosce questo"
  echo "Trusted Publisher, o il publish è passato da un token: con un token"
  echo "l'indice accetta la wheel e non firma niente. I campi da mettere su"
  echo "PyPI sono nel README, «Pubblicare su PyPI»."
  echo
  exit 1
fi
non_visibile "non ha risposto (5xx/rete) per $ignoti file di $VERSIONE"

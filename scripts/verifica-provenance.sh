#!/usr/bin/env bash
# verifica-provenance · la wheel appena pubblicata porta la sua attestazione
#
#   ./scripts/verifica-provenance.sh 1.6.0.dev22
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
# Quindi la regola, e la ragione per cui NON si ritenta sul 404:
#
#   200  → c'è.            Risposta.
#   404  → non c'è.        Risposta. Rossa, e con il consiglio giusto.
#   5xx/429/rete → non lo so. NON è una risposta: si richiede, con attesa
#                  crescente. Se dopo tutti i tentativi non lo sappiamo ancora,
#                  lo si dice così — INDETERMINATO — e il job resta rosso,
#                  perché «non verificato» non è «verificato»; ma il consiglio
#                  è «rilancia», non «riconfigura».
#
# Ritentare anche sul 404 sarebbe comodo e sarebbe un errore: coprirebbe con
# l'attesa proprio il caso che questo cancello deve vedere.
#
# ── COSA CONTROLLA, E COSA NO ────────────────────────────────────────────────
#
# Controlla che PyPI SERVA un'attestazione per ciascun file di quella versione,
# e che quell'attestazione nomini QUESTO repository. Non verifica la firma
# crittograficamente: quello lo fa PyPI quando la accetta, e rifarlo qui
# vorrebbe dire portarsi dietro sigstore per ridire una cosa già detta.
#
# USCITE: 0 verde · 1 rosso accertato (assente, o nata altrove) · 75 rosso
# indeterminato (l'indice non ha risposto).
set -euo pipefail

VERSIONE="${1:-}"
PACCHETTO="${PACCHETTO:-s3dgraphy}"
TENTATIVI="${TENTATIVI:-5}"
ATTESA="${ATTESA:-3}"
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

#: una risposta, o la confessione di non averla. NON stampa niente: lascia il
#: corpo in $JSON e lo stato in $STATO. Il motivo è una trappola vera, in cui
#: questo file è cascato appena scritto — `json="$(interroga …)"` esegue la
#: funzione in una SUBSHELL, e le variabili che assegna muoiono lì: fuori
#: restavano il valore iniziale, cioè stato vuoto e zero tentativi, e ogni file
#: risultava indeterminato. Una funzione che deve riportare DUE cose non le può
#: riportare una per stdout e una per variabile.
STATO=""
FATTI=0
JSON=""
interroga() {
  local url="$1" attesa="$ATTESA" i corpo
  for i in $(seq 1 "$TENTATIVI"); do
    FATTI="$i"
    corpo="$(curl -sS -m 30 -w '\n%{http_code}' "$url" 2>/dev/null || true)"
    STATO="$(printf '%s' "$corpo" | tail -1)"
    case "$STATO" in
      200|404) break ;;
      *) if [ "$i" -lt "$TENTATIVI" ]; then sleep "$attesa"; attesa=$((attesa * 2)); fi ;;
    esac
  done
  JSON="$(printf '%s' "$corpo" | sed '$d')"
}

files="$(curl -fsS --retry 3 --retry-all-errors -m 30 "https://pypi.org/pypi/$PACCHETTO/$VERSIONE/json" \
         | python3 -c 'import sys,json; d=json.load(sys.stdin); print("\n".join(u["filename"] for u in d["urls"]))' \
         2>/dev/null || true)"

if [ -z "$files" ]; then
  echo "  ✗ $PACCHETTO $VERSIONE non risulta su PyPI (o l'indice non risponde)."
  exit 1
fi

assenti=0
altrove=0
ignoti=0
n=0
for f in $files; do
  n=$((n + 1))
  interroga "https://pypi.org/integrity/$PACCHETTO/$VERSIONE/$f/provenance"
  json="$JSON"
  ripetuto=""
  [ "$FATTI" -gt 1 ] && ripetuto=" [dopo $FATTI tentativi]"

  if [ "$STATO" = "404" ]; then
    echo "  ✗ $f — nessuna provenance (404: l'indice dice che non c'è)$ripetuto"
    assenti=$((assenti + 1))
    continue
  fi
  if [ "$STATO" != "200" ]; then
    echo "  ? $f — l'indice non ha risposto (HTTP $STATO) dopo $FATTI tentativi"
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
    echo "  ✗ $f — l'attestazione nomina «$dove», non «$ATTESO»"
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
fi
if [ "$assenti" -gt 0 ]; then
  echo "MANCA l'attestazione ($assenti file), e l'indice lo dice esplicitamente"
  echo "con un 404. Se il publish è appena riuscito, o PyPI non conosce questo"
  echo "Trusted Publisher, o il publish è passato da un token: con un token"
  echo "l'indice accetta la wheel e non firma niente. I campi da mettere su"
  echo "PyPI sono nel README, «Pubblicare su PyPI»."
  echo
fi
if [ "$ignoti" -gt 0 ]; then
  echo "NON LO SAPPIAMO ($ignoti file): PyPI ha risposto 5xx/429 a tutti i"
  echo "$TENTATIVI tentativi. Questo non dice NIENTE sulla configurazione né"
  echo "sul publish — l'indice risponde così anche per i file che l'attestazione"
  echo "ce l'hanno. Rilancia fra qualche minuto:"
  echo
  echo "    ./scripts/verifica-provenance.sh $VERSIONE"
  echo
  echo "Il job resta rosso perché «non verificato» non è «verificato». Non"
  echo "toccare il Trusted Publisher prima di aver visto un 404."
fi

if [ $((assenti + altrove)) -gt 0 ]; then exit 1; fi
exit 75

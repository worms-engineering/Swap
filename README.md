# TicketSwap booking bot

Bot che monitora un evento su [TicketSwap](https://www.ticketswap.com) e **riserva**
il primo biglietto compatibile con i tuoi criteri. Il bot **non paga mai**: quando i
biglietti sono nel carrello (TicketSwap li blocca per qualche minuto) ti avvisa e
lascia il browser aperto, così completi tu il pagamento.

## Come funziona

1. Apre ogni evento in una scheda di Chromium con il tuo profilo salvato (resti loggato).
2. Ogni `--interval` secondi (con un po' di variazione casuale) ricarica le pagine e legge gli annunci.
3. Scarta gli annunci venduti, già provati, sopra `--max-price` o con meno biglietti di `--quantity`.
4. Apre l'annuncio più economico e preme "Acquista / Buy". Se TicketSwap conferma la prenotazione
   (URL del carrello/checkout o testo "reserved"/"riservato") ti avvisa.
5. Se TicketSwap mostra una pagina di verifica anti-bot (captcha, "Verifying", errore 403/429) il bot
   **si ferma** e ti avvisa: non prova ad aggirare la protezione.

## Installazione

Serve Python 3.11 o superiore.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Uso

```bash
# 1. Login (una volta sola): si apre Google Chrome, accedi a TicketSwap e poi chiudi Chrome
python -m ticketswap_bot login

# 2. Monitora un evento
python -m ticketswap_bot watch "https://www.ticketswap.com/event/nome-evento/..." \
    --max-price 80 --quantity 2 --interval 20
```

### Più eventi e trigger price

Il **trigger price** è il prezzo massimo per biglietto: il bot riserva solo annunci a quel
prezzo o meno. Puoi monitorare più eventi contemporaneamente: ognuno ha la sua scheda nel
browser e, quando uno viene riservato, quella scheda resta sul carrello per il pagamento
mentre le altre continuano a controllare.

Stesso prezzo per tutti gli eventi:

```bash
python -m ticketswap_bot watch URL_EVENTO_1 URL_EVENTO_2 --trigger-price 60
```

Prezzo e quantità diversi per ogni evento, con un file TOML (vedi `events.example.toml`):

```toml
interval = 20

[[event]]
url = "https://www.ticketswap.com/event/nome-evento-1/..."
max_price = 80
quantity = 2

[[event]]
url = "https://www.ticketswap.com/event/nome-evento-2/..."
max_price = 45
```

```bash
python -m ticketswap_bot watch --config events.toml
```

Gli URL passati da riga di comando si possono aggiungere a quelli del file: `--trigger-price`
e `--quantity` valgono solo per questi URL, gli eventi del file mantengono i propri valori.
Con `--stop-after-first` il bot si ferma alla prima prenotazione.

L'intervallo vale per ogni giro di controlli su tutti gli eventi: con molti eventi le richieste
a TicketSwap aumentano, quindi non scendere troppo con `--interval`.

| Opzione | Descrizione |
| --- | --- |
| `--max-price` / `--trigger-price` | Prezzo massimo **per biglietto** (stessa valuta mostrata sul sito) |
| `-c`, `--config` | File TOML con più eventi e prezzi diversi |
| `--stop-after-first` | Fermati dopo la prima prenotazione |
| `--quantity` | Numero di biglietti (default 1) |
| `--interval` | Secondi tra un controllo e l'altro (default 20, minimo 5) |
| `--max-runtime` | Ferma il bot dopo N minuti |
| `--headless` | Browser invisibile (sconsigliato: non potresti pagare dalla stessa finestra) |
| `--profile` | Cartella del profilo browser (default `~/.ticketswap-bot/profile`) |
| `-v` | Log dettagliati |

Se l'evento ha più tipi di biglietto (es. "Sabato", "Weekend"), usa l'URL della pagina del
tipo di biglietto specifico, quella che mostra direttamente l'elenco degli annunci.

### Notifiche

Oltre al messaggio nel terminale (con segnale acustico) il bot usa `notify-send` (Linux) o
le notifiche di macOS se disponibili. Per riceverle anche su Telegram:

```bash
export TELEGRAM_BOT_TOKEN=...   # token del bot creato con @BotFather
export TELEGRAM_CHAT_ID=...     # il tuo chat id
```

### Login con Google

Google blocca l'accesso dai browser controllati da programmi. Per questo il comando `login`
apre il tuo **Google Chrome** normale (senza automazione) con un profilo separato dedicato al bot:
accedi a TicketSwap anche con "Continua con Google", poi chiudi Chrome. Il bot userà poi lo stesso
Chrome e lo stesso profilo, quindi resti loggato. Serve avere Google Chrome installato; se non viene
trovato il bot usa il browser integrato e il login con Google potrebbe non funzionare (in quel caso
accedi con email).

### Browser personalizzato

Per usare un altro Chrome/Chromium (sia per il login sia per il bot):

```bash
export TICKETSWAP_BOT_BROWSER=/percorso/di/chrome
```

## Adattare il bot se TicketSwap cambia interfaccia

TicketSwap non ha un'API pubblica per l'acquisto, quindi il bot lavora sulla pagina web.
I punti da aggiornare se il sito cambia sono tutti in cima a `ticketswap_bot/bot.py`:

- `LISTING_LINK_SELECTOR` – come riconoscere i link agli annunci nella pagina evento;
- `BUY_BUTTON_RE` – testo del pulsante di acquisto (multilingua);
- `RESERVED_RE` / `CHECKOUT_URL_RE` – come riconoscere che la prenotazione è avvenuta.

## Test

```bash
pip install -r requirements-dev.txt
pytest
```

I test end-to-end usano pagine finte servite in locale (`tests/fixtures`), non il sito reale.

## Avvertenze

- L'uso di strumenti automatici potrebbe violare i termini di servizio di TicketSwap e portare
  alla sospensione dell'account. Usalo per acquisti personali e con intervalli ragionevoli.
- Il bot non conserva credenziali né dati di pagamento: il login avviene a mano nel browser e la
  sessione resta solo nella cartella del profilo locale.

# TicketSwap booking bot

Bot che monitora un evento su [TicketSwap](https://www.ticketswap.com) e **riserva**
il primo biglietto compatibile con i tuoi criteri. Il bot **non paga mai**: quando i
biglietti sono nel carrello (TicketSwap li blocca per qualche minuto) ti avvisa e
lascia il browser aperto, così completi tu il pagamento.

## Come funziona

1. Apre la pagina dell'evento in un browser Chromium con il tuo profilo salvato (resti loggato).
2. Ogni `--interval` secondi (con un po' di variazione casuale) ricarica la pagina e legge gli annunci.
3. Scarta gli annunci venduti, già provati, sopra `--max-price` o con meno biglietti di `--quantity`.
4. Apre l'annuncio più economico e preme "Acquista / Buy". Se TicketSwap conferma la prenotazione
   (URL del carrello/checkout o testo "reserved"/"riservato") ti avvisa.
5. Se compare un captcha o un errore 403/429 **non prova ad aggirarlo**: ti avvisa e rallenta
   (backoff esponenziale fino a 10 minuti). Risolvi tu la verifica nella finestra del browser.

## Installazione

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Uso

```bash
# 1. Login (una volta sola): si apre il browser, accedi a TicketSwap e premi INVIO nel terminale
python -m ticketswap_bot login

# 2. Monitora un evento
python -m ticketswap_bot watch "https://www.ticketswap.com/event/nome-evento/..." \
    --max-price 80 --quantity 2 --interval 20
```

| Opzione | Descrizione |
| --- | --- |
| `--max-price` | Prezzo massimo **per biglietto** (stessa valuta mostrata sul sito) |
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

### Browser personalizzato

Per usare un Chrome/Chromium già installato invece di quello di Playwright:

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

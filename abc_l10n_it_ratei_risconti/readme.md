# ABC - Ratei e risconti (Odoo 19)

Ratei e risconti attivi e passivi di fine esercizio con il metodo italiano classico:
scrittura di assestamento alla data di chiusura **D** e storno al giorno **D + 1**.
Sostituisce i differimenti nativi di Odoo Enterprise.

## Cosa fa

- Calcola le quote **a giorni effettivi** (giorno iniziale e finale inclusi) sull'imponibile.
- Legge le righe contabili registrate con **Data inizio / Data fine** (campi nativi della riga):
  - registrate entro D con competenza oltre D → **risconti**;
  - registrate dopo D con competenza iniziata entro D → **ratei** (es. bolletta arrivata a febbraio).
- **Schede manuali** per ratei senza documento, stime e leasing; **schede pregresso** per ratei e
  risconti rilevati nel vecchio gestionale (con storno di apertura).
- **Elaborazione** con anteprima (escludi, correggi con nota, cambia conto), conferma, storno automatico,
  annullamento ed **elaborazioni integrative** (solo righe nuove, cambiate o annullate).
- **Risconti pluriennali**: quota entro 12 mesi, oltre 12 mesi (conto dedicato facoltativo) e oltre 5 anni.
- **Leasing**: periodo fiscale facoltativo sulla riga o sulla scheda, confronto civilistico/fiscale nel report.
- La **distribuzione analitica** della riga d'origine viene riportata sulla scrittura di assestamento.
- **Avviso** (mai blocco) alla data di blocco se restano righe non elaborate.

## Installazione

Dipende da `account_accountant`, `account_reports`, `l10n_it`. All'installazione:

1. la generazione nativa di spese e ricavi differiti viene impostata su *manuale* per tutte le società
   (e non si può più riportare su "alla conferma");
2. i menu nativi *Spese differite* e *Ricavi differiti* vengono nascosti (tornano visibili disinstallando il modulo).

## Configurazione

*Contabilità › Configurazione › Impostazioni › Ratei e risconti*: registro, conti predefiniti per le 4
tipologie, conti oltre 12 mesi, raggruppamento della scrittura, prefissi ammessi (default attivo `1901,1902`,
passivo `270,280,281`, cioè le voci D ed E del bilancio civilistico).
Eccezioni per conto: *Contabilità › Configurazione › Contabilità › Eccezioni conti ratei e risconti*.

## Uso

*Contabilità › Contabilità › Ratei e risconti*:

- **Elabora**: sceglie la data di chiusura (proposta dalla fine esercizio) e crea l'elaborazione in bozza.
- **Elaborazioni**: anteprima, conferma, stampa del prospetto PDF, annullamento.
- **Schede**: schede manuali e pregresso.
- **Prospetto**: tutte le righe elaborate, raggruppabili. Pulsanti **PDF** e **XLSX** in alto nella lista: aprono una finestra per filtrare intervallo di date di chiusura (dal/al), tipologia e conti rateo/risconto (con righe selezionate lavorano solo su quelle). Output A4 orizzontale, raggruppato per data, tipologia e conto con subtotali.
- **Pluriennali, leasing e quadratura**: piano dei riversamenti futuri, leasing civilistico/fiscale,
  quadratura tra saldo contabile e totale elaborazioni.

## Test

`tests/test_rr_compute.py` (casi di collaudo della specifica, solo calcolo) e `tests/test_rr_flow.py`
(flusso completo). Tag: `abc_rr`.

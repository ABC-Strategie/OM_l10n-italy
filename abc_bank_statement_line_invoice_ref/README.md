# A.B.C. - Riferimento transazione da fattura

In **Contabilita' > Corrispondenza bancaria** (Transazioni), quando una transazione
viene riconciliata con una o piu' fatture, il campo **Riferimento** della transazione
viene compilato con il riferimento e la data di ciascuna fattura pagata.

Esempio, un bonifico che paga due fatture:

> FT/001 del 12/03/2026, FT/002 del 15/03/2026

La colonna *Riferimento* e' opzionale nella lista delle transazioni: si attiva dal
menu delle colonne in fondo a destra.

## Regole

- **Fatture e note di credito cliente**: il numero della fattura. Il campo
  *Riferimento* della fattura cliente non si usa, perche' contiene il numero
  dell'ordine di vendita.
- **Fatture e note di credito fornitore**: il campo *Riferimento*, cioe' il numero sul
  documento del fornitore. Se e' vuoto, il numero della fattura.
- **Fatture in bozza** (abbinabili dal widget, ancora senza numero): vale il
  riferimento, se presente; altrimenti la fattura non compare nel testo.
- **Data**: la data fattura, in formato gg/mm/aaaa. Se manca, la data contabile.
- **Piu' fatture**: ordinate per data fattura, separate da virgola. Sono comprese le
  note di credito.
- **Riferimento gia' presente** (per esempio dall'import dell'estratto conto): viene
  sovrascritto.
- **Annullamento della riconciliazione**: il riferimento viene ricalcolato con le
  fatture rimaste, e svuotato se non ne resta nessuna.
- **Pagamento intermedio**: se la transazione e' abbinata a un pagamento, a sua volta
  riconciliato con la fattura, vale la fattura pagata dal pagamento.

Il riferimento si aggiorna qualunque sia il modo della riconciliazione: widget di
corrispondenza bancaria, riconciliazione automatica, abbinamento dal lato della
fattura.

## Transazioni pregresse

All'**installazione** il modulo compila il riferimento su tutte le transazioni gia'
riconciliate, anche solo in parte. Le transazioni senza fatture pagate non vengono
toccate. L'elaborazione non scrive messaggi nel chatter e nel log riporta quante
transazioni ha aggiornato; una transazione in errore viene segnalata nel log e non
blocca l'installazione.

Per rilanciare il calcolo in un secondo momento: selezionare le transazioni nella lista
e usare **Azioni > Aggiorna riferimento da fatture**.

## Note tecniche

- Il riferimento della transazione e' `account.move.ref` del suo movimento
  (`account.bank.statement.line` eredita `account.move` via `_inherits`).
- L'aggancio e' su `account.partial.reconcile` (`create` e `unlink`): tutte le
  riconciliazioni, da qualunque flusso, passano di li'. Sono ricalcolate solo le
  transazioni coinvolte, quindi le riconciliazioni che non toccano la banca non hanno
  costi aggiuntivi.
- Il contesto `abc_skip_invoice_ref` disattiva l'aggiornamento automatico.

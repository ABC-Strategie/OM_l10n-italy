# A.B.C. - Controllo data fattura

Avvisa l'utente quando la **data fattura** e' anteriore a quella dell'ultima fattura
confermata della stessa serie.

Il numero viene assegnato alla conferma in base alla data, quindi una fattura retrodatata
produce una numerazione **non cronologica**. Odoo non lo impedisce da se': il vincolo
`sequence.mixin._constrains_date_sequence` blocca solo il disallineamento fra numero e
periodo (anno), non una retrodatazione all'interno dello stesso periodo.

## Quando appare l'avviso

L'avviso e' un **banner giallo** in cima alla fattura (il banner di avviso nativo di
Odoo) e compare sulle fatture **in bozza**, cioe' alla creazione e alla reimpostazione
a bozza. Alla conferma sparisce.

Non e' bloccante: l'utente puo' confermare comunque, dopo una conferma esplicita (vedi
sotto).

Esempio del messaggio:

> La data fattura (05/03/2026) e' anteriore a quella dell'ultima fattura confermata del
> registro: F/2026/00042 del 12/03/2026.
> Per mantenere la numerazione cronologica, impostare una data dal 12/03/2026 in poi.

## Conferma con popup

Se l'avviso e' presente e si preme **Conferma** (anche con la scorciatoia Alt+Q), prima di
confermare compare un popup "Data fattura non cronologica" con il messaggio dell'avviso e
la domanda "Confermare comunque la fattura?", e due pulsanti:

- **Conferma**: la fattura viene salvata e confermata come di consueto;
- **Annulla** (anche la X o Esc): non succede nulla, la fattura resta in bozza e le
  modifiche non salvate restano nel form, cosi' si puo' correggere la data.

Senza avviso il pulsante Conferma funziona come sempre. Il popup compare solo dal form
della fattura, dove e' visibile il banner: la conferma multipla dalla lista
(Azioni > Conferma) non lo mostra.

## Ambito

Il controllo si applica solo a:

- registri con la casella **Controllo data fattura** attiva (scheda del registro, accanto a
  *Sequenza dedicata note di credito*, visibile ai responsabili della contabilita');
- fatture e note di credito cliente (comprese le ricevute), in stato bozza.

All'installazione la casella si accende su tutti i registri vendita, e si accende da
sola anche sui registri vendita creati dopo. Si puo' spegnere registro per registro.
Le fatture fornitore sono escluse anche con la casella accesa, perche' la loro data
fattura e' quella del fornitore e non segue la nostra numerazione.

## Serie di riferimento

Il riferimento e' l'ultima fattura confermata della **stessa serie della numerazione
nativa di Odoo**, cioe' quella con cui Odoo calcola il progressivo:

- stesso registro;
- stesso **periodo di numerazione**: l'anno per i numeri come `F/2026/00042`, il mese per
  quelli come `AC/2026/10/0001`. La periodicita' si deduce dal formato dei numeri, come
  fa Odoo;
- se il registro ha la *Sequenza dedicata note di credito*, fatture e note di credito
  hanno riferimenti separati (`F/2026/…` e `RF/2026/…`).

Una fattura datata 30/12/2025 e registrata a gennaio 2026 prende un numero del 2025, quindi
viene confrontata solo con le fatture del 2025: le fatture di gennaio 2026 non fanno
scattare l'avviso.

Sulle fatture cliente appena create la data fattura e' spesso vuota: in quel caso vale
la data contabile, che e' obbligatoria.

## Comportamento alla reimpostazione a bozza

- Riaprendo l'**ultima** fattura confermata non compare nulla: il riferimento diventa la
  precedente, e la data della fattura riaperta e' successiva.
- Riaprendo una fattura **piu' vecchia** l'avviso compare, perche' modificarne la data
  romperebbe la cronologia rispetto alle fatture confermate dopo di essa.

## Note tecniche

Il modulo usa il meccanismo di avviso nativo di Odoo 19 su `account.move`:
`_get_alerts()` viene esteso per aggiungere la voce `abc_invoice_date_before_last_posted`
al campo `alerts`, reso nel form dal widget `actionable_errors`. Le viste del modulo
aggiungono la casella alla scheda del registro e il campo invisibile
`abc_invoice_date_warning` al form della fattura, letto dal popup.

Il popup (`static/src/account_move_form_controller.js`) estende
`AccountMoveFormController.beforeExecuteActionButton`, come fa `account_peppol`, e apre un
`ConfirmationDialog` prima del salvataggio e della chiamata ad `action_post`. Il controllo
e' lato client di proposito: un override server di `action_post` verrebbe eseguito dopo
quelli dei moduli installati sopra di lui (per esempio `abc_verifica_anagrafica`, che puo'
scrivere nel chatter), anche quando l'utente poi annulla.

`_compute_alerts` del core non dipende da `invoice_date`, quindi il banner non si
aggiornerebbe alla modifica della data. Il modulo lo estende dichiarando la sola
dipendenza aggiuntiva: non e' necessario ricopiare le dipendenze del core perche'
`Field.get_depends` usa `resolve_mro`, che raccoglie tutte le implementazioni del compute
lungo la MRO e ne **somma** le `@api.depends`.

Il periodo di numerazione si ricava con gli helper nativi di `sequence.mixin`
(`_deduce_sequence_number_reset` e `_get_sequence_date_range`), con la stessa logica di
`account.move._get_last_sequence_domain`. Se un numero non e' interpretabile, il controllo
considera tutto il registro anziche' andare in errore.

La casella `abc_invoice_date_check` e' un campo calcolato memorizzato e modificabile
(vale `True` sui registri di tipo vendita): cosi' all'installazione Odoo la valorizza sui
registri esistenti senza bisogno di un hook.

Il modulo e' l'adattamento a BBS, che usa la numerazione nativa, del modulo omonimo di ABC
basato sulla numerazione personalizzata NNNN/AAAA/SS.

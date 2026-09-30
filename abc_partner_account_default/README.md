# A.B.C. - Conti di costo/ricavo per contatto

Permette di impostare sul contatto il conto di ricavo e il conto di costo da usare nelle righe delle
sue fatture, al posto del conto che arriverebbe dal prodotto o dalla categoria prodotto.

## Configurazione

Sul contatto, tab **Contabilità**, sezione *Generale*, subito sotto "Conto di debito":

| Campo | Usato su |
|---|---|
| **Conto di ricavo** | Fatture e note di credito cliente (`out_invoice`, `out_refund`) |
| **Conto di costo** | Fatture e note di credito fornitore (`in_invoice`, `in_refund`) |

Entrambi i campi sono visibili solo agli utenti del gruppo *Contabile*
(`account.group_account_user`), come i due conti standard che li precedono.

## Comportamento

- Se il conto è valorizzato sul contatto, **prevale** su quello del prodotto o della sua categoria,
  su tutte le righe prodotto della fattura.
- Se il campo è vuoto, il comportamento è quello standard di Odoo: nessun impatto.
- Se sulla fattura è impostata una **posizione fiscale**, al conto del contatto viene applicata la
  stessa mappatura (`map_account`) che Odoo applica al conto del prodotto.
- Cambiando il cliente su una fattura in bozza, il conto delle righe segue il nuovo contatto.
- Le impostazioni si leggono dal **commercial partner**: su un contatto figlio valgono i conti
  dell'azienda madre, coerentemente con come Odoo gestisce le altre impostazioni contabili.
- Il conto resta comunque modificabile a mano sulla singola riga; verrà però ricalcolato se cambia
  la fattura o il contatto.

## Note tecniche

- I due campi sono `company_dependent=True`, come `property_account_receivable_id` /
  `property_account_payable_id` su `res.partner` e come i conti su `product.template`: il valore è
  quindi per azienda.
- Il dominio sui conti è lo stesso di `product.template.property_account_income_id` in 19.0
  (esclude crediti, debiti, liquidità, carte di credito e conti d'ordine).
- L'aggancio è un override di `account.move.line._compute_account_id` che chiama `super()` e
  sovrascrive solo dopo: non viene replicata la logica standard di Odoo, così eventuali modifiche
  del core restano valide.
- Il `@api.depends` dell'override aggiunge `partner_id` a `move_id` (il core dipende dal solo
  `move_id`), altrimenti cambiare cliente non farebbe ricalcolare il conto delle righe.

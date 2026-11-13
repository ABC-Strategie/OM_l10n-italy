# abc_account_loans_due_date

Le scritture generate dai **Prestiti** (modulo enterprise `account_loans`)
prendono la data di **scadenza della rata** del piano di ammortamento.

## Date delle scritture

| Scrittura                               | Standard Odoo             | Con il modulo     |
|-----------------------------------------|---------------------------|-------------------|
| Capitale e interessi                    | fine mese della rata      | scadenza rata     |
| Riclassificazione LT - ST               | fine mese della rata      | scadenza rata     |
| Riclassificazione di storno LT - ST     | primo del mese successivo | scadenza rata     |

Riferimenti, importi e conti restano quelli dello standard. Alla conferma del
prestito vengono confermate subito le scritture con scadenza fino a oggi; le
altre restano in bozza e vengono confermate automaticamente alla scadenza.

## Prestiti gia' confermati

Pulsante **Riallinea date a scadenza rata** nel form del prestito (stato In
corso / Chiuso) oppure azione omonima dalla lista prestiti, solo per
*Contabilita' / Amministratore*:

* **bozze**: viene cambiata solo la data;
* **confermate**: rimesse in bozza, ridatate e riconfermate. Se il mese della
  nuova data e' diverso dal precedente (tipicamente lo storno, che passa dal
  primo del mese successivo al mese della rata) la scrittura riceve un nuovo
  numero e nel mese di partenza resta un buco di numerazione, sistemabile con
  *Riordina sequenza* dal menu Azioni (modalita' sviluppatore);
* **non toccate**: scritture in periodo bloccato (o che finirebbero in un
  periodo bloccato) e scritture protette da hash, elencate nella notifica
  finale.

Lo storno resta collegato alla sua riclassificazione (`reversed_entry_id`) e,
come nello standard, le due scritture non vengono riconciliate.

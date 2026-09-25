# Modelli di scrittura contabile (`abc_modelli_scritture`)

Modulo **autonomo** per Odoo 19. Non modifica, non eredita e non altera alcun
modulo esistente: aggiunge soltanto modelli, viste e menu nuovi. Dipende solo
dal modulo standard `account`.

## A cosa serve

Creare modelli riutilizzabili di scritture contabili (es. la scrittura degli
stipendi) e, a partire da un modello, generare la registrazione in un registro
di tipo **Varie**, inserendo ogni mese solo gli importi effettivi.

## Installazione su Odoo.sh

1. Copiare la cartella `abc_modelli_scritture/` dentro il repository collegato
   a Odoo.sh (nella cartella dei moduli custom, es. la radice del repo o
   `addons/` a seconda di come è configurato il branch).
2. Commit + push sul branch (di norma prima su un branch di **stage** per la
   prova, poi su production).
3. In Odoo: menu **App** → *Aggiorna elenco applicazioni* → cercare
   "Modelli di scrittura contabile" → **Installa**.

Non serve alcuna configurazione: la voce compare **dentro l'app Contabilità**,
nel menu **Contabilità → Modelli di scrittura** (non è una app separata).

## Come si usa

### 1. Creare il modello
App **Contabilità → Contabilità → Modelli di scrittura → Nuovo**

- **Nome modello**: es. "Scrittura stipendi".
- **Descrizione della scrittura**: la descrizione generale della registrazione.
- **Registro (Varie)**: il registro di tipo Varie predefinito (modificabile in
  fase di generazione).
- **Righe** (stessa struttura di una scrittura Odoo): Conto, Partner,
  Etichetta, **Dare**, **Avere**.
  - In fondo alla lista sono mostrati i **totali di colonna Dare/Avere** e,
    sotto, **Totale Dare / Totale Avere / Sbilancio**: così si vede subito se
    la scrittura quadra e dove intervenire.
  - Colonna **Distribuzione analitica** (`analytic_distribution`): permette di
    attribuire la riga a uno o più **centri di costo** (conti analitici), anche
    ripartendo in percentuale. La distribuzione impostata sul modello viene
    riportata sulla scrittura generata.
  - Colonna **Lato naturale** (opzionale) che indica il lato atteso del conto
    (costi/attività in Dare; ricavi/passività/patrimonio netto in Avere).
  - Se si mette un importo nel lato insolito (es. un costo in Avere) compare un
    **avviso** e la riga viene evidenziata; resta comunque salvabile.
  - Le righe si **riordinano trascinandole** con la maniglia a sinistra.

### 2. Confermare (blocco)
Premere **Conferma modello**: il modello passa in stato *Confermato* e i campi
diventano non modificabili. Per modificarlo di nuovo premere **Modifica
modello**: comparirà un **avviso di conferma** prima di riaprirlo.

### 3. Generare la scrittura del mese
Dal modello premere **Genera scrittura**. Nella finestra:

- indicare **Data** e, se serve, cambiare il **Registro**;
- inserire gli **importi in Dare/Avere** del mese; le righe lasciate a **zero
  non** vengono riportate;
- i totali Dare/Avere e lo **Sbilancio** sono mostrati in alto (la scrittura
  deve quadrare);
- premere **Crea scrittura**: viene creata la registrazione **in bozza** nel
  registro Varie e aperta a video per la verifica e la registrazione (Conferma).

La scrittura è creata in bozza apposta, così può essere controllata prima di
essere registrata.

## Note tecniche

- Modelli aggiunti: `abc.modelli.scritture.template`,
  `abc.modelli.scritture.template.line`, e i transitori
  `abc.modelli.scritture.genera` / `...genera.line`.
- Permessi concessi al gruppo *Contabilità / Utente*
  (`account.group_account_user`).
- Lato naturale dei conti calcolato dal campo standard `account_type`.

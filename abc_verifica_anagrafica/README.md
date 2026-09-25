# Verifica anagrafica tributaria (`abc_verifica_anagrafica`)

Modulo Odoo 19 Enterprise per la verifica dell'esistenza e validità dei
**codici fiscali delle persone fisiche** presenti nelle anagrafiche contatti,
tramite il servizio "API anagrafiche libero accesso" dell'Agenzia delle
Entrate (Piattaforma API Management, Catalogo dei servizi di
interoperabilità).

Sviluppato da ABC Strategie. Licenza LGPL-3.

Moduli inclusi:

| Modulo | Ruolo |
|---|---|
| `abc_verifica_anagrafica` | Modulo principale (contatti, coda, provider, impostazioni, fatture) |
| `abc_verifica_anagrafica_sale` | Ponte per Vendite: innesco e policy alla conferma degli ordini. Si installa automaticamente se è presente l'app Vendite |

---

## 1. Principi di funzionamento e limiti d'uso

Le Condizioni generali di utilizzo del servizio AdE vincolano il design del
modulo. In particolare:

- **Art. 8 c.1**: sono vietati gli accessi massivi alle API e la costruzione
  di basi dati derivate, salvo quanto necessario per l'ordinario utilizzo dei
  dati. Il modulo **non offre alcuna verifica massiva**: nessun pulsante
  "verifica tutti", nessuna azione su selezione multipla, nessun wizard di
  bonifica dello storico. Ogni verifica è puntuale e nasce da un evento sul
  singolo contatto.
- **Art. 5 c.1 lett. c**: le informazioni acquisite vanno conservate solo per
  il tempo strettamente necessario. Il modulo conserva unicamente l'esito
  normalizzato (mai il payload grezzo) e lo elimina definitivamente allo
  scadere della retention configurata.
- **Art. 8 c.1**: gli identificativi assegnati (client id e client secret)
  non vanno condivisi con terzi. Il secret è visibile solo agli amministratori
  del modulo e non compare mai in log, messaggi di errore, chatter o export.
- **Art. 10**: in caso di violazione l'Agenzia può disabilitare il servizio.
  Il modulo applica un limite hard di chiamate al minuto e al giorno,
  allineato alla specifica del servizio (10/minuto, 100/giorno per client).

### Quando parte una verifica

Solo in questi casi, sempre sul singolo contatto:

1. creazione di un contatto con codice fiscale;
2. modifica del codice fiscale di un contatto esistente (l'esito precedente
   viene azzerato);
3. pulsante **"Verifica ora"** sulla scheda del contatto;
4. **uso effettivo del contatto** mai verificato: salvataggio di un
   preventivo o di una fattura in bozza verso di lui, e in ogni caso
   conferma di fatture, note di credito e ordini (con il modulo ponte).
   Questo innesco, configurabile, consente di verificare progressivamente
   l'anagrafica storica nell'ambito dell'ordinario utilizzo dei dati, senza
   scansioni. Il documento non attende mai l'esito: la sua scheda si
   ricarica da sola all'arrivo dell'esito e mostra i banner di avviso già
   sul preventivo, prima dell'ordine.

Nessuna chiamata avviene durante il salvataggio: l'evento accoda una
richiesta, sveglia subito il processo pianificato e questo la elabora entro
pochi secondi nel rispetto dei limiti. L'utente non subisce la latenza del
servizio.

Il solo pulsante **"Verifica ora"** è sincrono: l'operatore ha chiesto
esplicitamente l'esito e lo riceve nella notifica, attendendo la sola
latenza del servizio (di norma pochi secondi). Anche in questo caso il
limite di chiamate è rispettato: pulsante e processo pianificato
condividono un lock per società. Se il limite è raggiunto o il servizio non
risponde, la richiesta resta in coda e viene completata automaticamente.

### Ambito

Codice fiscale: solo persone fisiche (contatti non "azienda", non collegati
a un contatto padre) con codice fiscale alfanumerico di 16 caratteri.
Aziende, enti, codici numerici a 11 cifre e indirizzi/contatti figli
risultano "Non applicabile".

Partita IVA: qualunque contatto principale con partita IVA italiana di 11
cifre (aziende, enti, ditte individuali, professionisti). Le partite IVA
estere non sono verificate.

### Partita IVA

Lo stesso servizio AdE verifica anche le partite IVA e restituisce, oltre
all'esito, la **denominazione** del titolare e le date di inizio,
**cessazione** e **sospensione** dell'attività. Gli inneschi sono gli stessi
del codice fiscale (creazione o modifica della partita IVA o del paese,
"Verifica P.IVA" sulla scheda, uso effettivo alla conferma di fatture e
ordini) e le chiamate rientrano negli stessi limiti.

Stati: Non verificata, In attesa, Valida, **Cessata/sospesa**, Non valida,
Errore, Non applicabile. Sulla scheda compaiono denominazione AdE, esito del
confronto con il nome del contatto e date di cessazione o sospensione.

Impostazioni dedicate (Impostazioni > Contabilità > Verifica anagrafica
tributaria > Verifica delle partite IVA):

- *Comportamento su partita IVA cessata o sospesa*: blocca la conferma dei
  documenti (default), solo avviso, nessuna azione;
- *Confronto con la denominazione AdE*: il nome del contatto viene
  confrontato con la denominazione restituita ignorando forma giuridica,
  punteggiatura, accenti e ordine delle parole, e accettando inclusioni
  (es. "Rossi Costruzioni" / "ROSSI COSTRUZIONI EDILI SRL"). In caso di
  differenza sostanziale il contatto è segnalato con un banner ben visibile
  su preventivi, ordini e fatture (*Solo avviso*, default) oppure, con
  *Blocca*, i documenti non possono essere confermati finché il nome non
  viene allineato: il pulsante **"Allinea nome alla denominazione AdE"**
  sulla scheda lo fa con un click.

Una partita IVA non valida segue la policy "Comportamento su codice fiscale
non valido". Anche per la partita IVA lo stato Errore non blocca mai.

### Coerenza tra codice fiscale e nome

Controllo locale, senza chiamate al servizio: le prime sei lettere del
codice fiscale vengono ricalcolate da cognome e nome del contatto con le
regole ufficiali (consonanti poi vocali, X di riempimento; per il nome, con
quattro o più consonanti si prendono la prima, la terza e la quarta).
Poiché Odoo ha un solo campo nome, vengono provate tutte le suddivisioni
in cognome e nome, in entrambi gli ordini, con tolleranza per un titolo
("Dott.", "Avv."). Nomi di una sola parola non vengono controllati.

Impostazione "Coerenza tra codice fiscale e nome":

- *Blocca il salvataggio* (default): il contatto non si salva; il messaggio
  mostra le sei lettere trovate e quelle attese;
- *Segnala come non valido*: il contatto si salva ma risulta "Non valido"
  con motivo esplicito, senza consumare chiamate;
- *Disattivo*.

Il controllo scatta quando cambiano codice fiscale, nome o tipo di
contatto; i contatti esistenti non vengono toccati finché non vengono
modificati. Le scritture con context `abc_va_skip_trigger=True` (import)
non sono bloccate: eventuali incoerenze emergono alla prima verifica.

### Anti-abuso

Se sullo stesso codice fiscale esiste già un esito reale entro le ore
configurate (default 24), "Verifica ora" riutilizza l'esito senza chiamare il
servizio. Solo un amministratore del modulo può forzare una nuova chiamata.

### Import massivi

L'importazione di molti contatti con codice fiscale accoda altrettante
verifiche, smaltite ai limiti configurati (100 al giorno). Per importare
anagrafiche **senza** accodare verifiche, eseguire l'import con il context
`abc_va_skip_trigger=True` (import programmatico) oppure disattivare
temporaneamente la verifica in Impostazioni durante l'import. I contatti
importati verranno verificati al primo uso effettivo (fattura, ordine).

---

## 2. Prerequisiti lato cliente

Da svolgere dal legale rappresentante o da un incaricato autorizzato,
nell'area riservata del sito dell'Agenzia delle Entrate (credenziali
Entratel/Fisconline, SPID, CIE o CNS).

1. **Attivare il servizio** "API anagrafiche libero accesso" dal
   *Catalogo dei servizi di interoperabilità*, sezione "Servizi
   disponibili", pulsante "Attiva", accettando le condizioni di utilizzo.
   Il servizio è riservato ai soggetti con partita IVA attiva. Con
   credenziali Fisconline/Entratel viene richiesto anche il PIN.
2. **Scaricare il file delle credenziali** proposto subito dopo la
   conferma. Il file contiene `CLIENT_ID`, `CLIENT_SECRET` e
   `DATA_SCADENZA`. **Il client secret è recuperabile solo da questo file**:
   conservarlo in un gestore di password aziendale, non in email o file di
   testo condivisi.
3. **Annotare la data di scadenza** del client secret (tipicamente 12 mesi):
   va inserita in Odoo per ricevere gli alert.
4. Facoltativo: dalla sezione "Servizi attivati", pulsante "Scarica
   documentazione", scaricare la specifica tecnica, utile in caso di
   aggiornamenti del servizio.
5. Se il servizio viene usato per conto di un incaricante, gli operatori
   devono essere autorizzati tramite "Funzioni relative agli incaricati".

Ogni società Odoo che aderisce al servizio ha le proprie credenziali: la
configurazione è per società.

---

## 3. Configurazione in Odoo

Menu **Impostazioni > Contabilità > Verifica anagrafica tributaria**
(sezione visibile agli amministratori di Contabilità; le credenziali sono
visibili solo al gruppo "Verifica anagrafica tributaria / Amministratore").

### Gruppi

| Gruppo | Permessi |
|---|---|
| Verifica anagrafica tributaria / Utente | Vede stato ed esiti sui contatti, usa "Verifica ora" |
| Verifica anagrafica tributaria / Amministratore | Configura credenziali, forza ri-verifiche, accede a coda e log |

L'amministratore di sistema riceve il gruppo Amministratore
all'installazione. Assegnare gli altri utenti da Impostazioni > Utenti.

### Passi

1. Selezionare la società (in alto a destra) se l'istanza è multi-società.
2. Attivare **"Verifica dei codici fiscali"**.
3. Provider: *Agenzia delle Entrate*. Ambiente: *Produzione* (vedi nota
   sull'ambiente di test).
4. Inserire **Client ID**, **Client Secret** e **Scadenza client secret**
   dal file credenziali.
5. Indicare il **Responsabile alert scadenza**: riceverà un'attività a 60,
   30 e 7 giorni dalla scadenza e alla scadenza.
6. Verificare i **limiti**: 10 chiamate al minuto e 100 al giorno sono i
   limiti nominali del servizio; non aumentarli. Possono essere ridotti.
7. Impostare **ore di validità esito** (anti-abuso, default 24) e
   **retention log** in mesi (default 24).
8. Scegliere il **comportamento su codice fiscale non valido**:
   - *Solo avviso* (default): banner sul documento e nota nel chatter;
   - *Blocca la conferma dei documenti*: impedisce la conferma di fatture,
     note di credito e ordini di vendita verso il soggetto; un errore
     tecnico del servizio non blocca mai;
   - *Nessuna azione*.
9. Scegliere gli **inneschi all'uso effettivo** (fatture, ordini di vendita).
10. **Salvare**, poi premere **"Test connessione"**: verifica la
    raggiungibilità del servizio per l'ambiente configurato e riporta lo
    stato delle credenziali (non configurate, in scadenza, scadute). Non
    consuma quota e non salva nulla sui contatti. La validità delle
    credenziali viene accertata alla prima verifica reale: in caso di
    credenziali errate il contatto risulta in stato "Errore" con messaggio
    esplicito e la richiesta compare in errore nella coda.

### Ambiente di test

La documentazione tecnica attualmente pubblicata dall'Agenzia riporta il
solo endpoint di produzione. L'ambiente *Test* richiede l'inserimento
dell'URL base fornito dall'Agenzia; in sua assenza il collaudo va eseguito in
produzione su pochi codici fiscali reali.

### Processi pianificati

| Azione pianificata | Frequenza | Funzione |
|---|---|---|
| Verifica anagrafica: elaborazione coda | 5 minuti, e su richiesta a ogni accodamento | Elabora la coda nel rispetto dei limiti |
| Verifica anagrafica: alert scadenza credenziali | giornaliera | Attività a 60/30/7 giorni e alla scadenza |
| Verifica anagrafica: purge log oltre retention | mensile | Eliminazione definitiva dei log oltre la retention |

Le frequenze sono modificabili da Impostazioni > Tecnico > Azioni pianificate.

---

## 4. Uso quotidiano

Sulla scheda del contatto, sotto il codice fiscale, compare il badge di
stato:

| Stato | Significato |
|---|---|
| Non verificato | Mai verificato (contatti precedenti all'installazione) |
| In attesa di verifica | Richiesta in coda |
| Valido | Riscontrato dal servizio |
| Non valido | Formalmente errato o incoerente con il nome (controllo locale, nessuna chiamata) **oppure** non riscontrato in Anagrafe Tributaria: il messaggio distingue i casi |
| Errore | Problema tecnico (credenziali, servizio non disponibile, limite raggiunto dopo i tentativi). Non blocca mai i documenti |
| Non applicabile | Azienda, ente, contatto figlio o senza codice fiscale |

Per la partita IVA il badge analogo compare sotto il campo Partita IVA, con
in più "Cessata/sospesa" e l'esito del confronto della denominazione.

Pulsanti: **Verifica ora** / **Verifica P.IVA** (Utente) e **Forza ri-verifica** (Amministratore,
ignora l'esito in cache). Entrambi mostrano l'esito nella notifica al
termine della chiamata e la scheda si aggiorna da sola. Per le verifiche
automatiche (creazione o modifica del codice fiscale) l'esito compare in
tempo reale nel chatter del contatto; il badge si aggiorna alla successiva
apertura della scheda.

Nella lista contatti è disponibile la colonna "Verifica CF" (opzionale) e i
filtri per stato.

Menu **Contabilità > Configurazione > Verifica anagrafica** (Amministratore):

- **Coda verifiche**: richieste in attesa, elaborate, in errore, annullate.
  Su una richiesta in errore è disponibile "Riprova".
- **Log verifiche**: registro immutabile di ogni evento (chiamata al
  servizio, controllo locale, esito da cache, blocco per limite raggiunto),
  con esito, codice, utente e società.

Gestione dei tentativi: errori di rete, indisponibilità del servizio (5xx) e
limite lato servizio (429, con rispetto di `Retry-After`) vengono ritentati
con attesa crescente fino a 3 volte; errori di credenziali o di richiesta
(altri 4xx) non vengono ritentati.

---

## 5. Rigenerazione del client secret alla scadenza

Alla scadenza il servizio smette di funzionare (risposte 401): i contatti
vanno in "Errore" e le richieste restano in errore nella coda. Il modulo
sospende le chiamate quando la data di scadenza configurata è superata.

1. Area riservata AdE > Catalogo dei servizi di interoperabilità > "Servizi
   attivati" > funzione di **rigenerazione del client secret** > confermare
   (PIN se credenziali Fisconline/Entratel).
2. **Scaricare il nuovo file** delle credenziali (nuovo secret e nuova data
   di scadenza).
3. In Odoo, Impostazioni > Contabilità > Verifica anagrafica tributaria:
   inserire il nuovo **Client Secret** e la nuova **Scadenza**, salvare,
   premere "Test connessione". Il cambio della data azzera gli alert.
4. Nella coda, selezionare le richieste in errore e usare "Riprova".

Consiglio: pianificare la rigenerazione all'alert dei 30 giorni.

---

## 6. Integrazioni

- **Innesco da altri moduli**: per accodare la verifica di un contatto mai
  verificato in occasione di un'operazione di business (es. apertura di una
  pratica), chiamare `partner._abc_va_on_use(company=...)`. Non effettua
  chiamate sincrone e non fa nulla se il contatto è già verificato.
- **Disattivare gli inneschi in scritture programmatiche**: context
  `abc_va_skip_trigger=True`.
- **Nuovo provider**: creare `services/<nome>_provider.py` con una
  sottoclasse di `BaseProvider` (metodi `verify_cf`, `verify_piva`,
  `health_check`, esito normalizzato `VerifyResult`), registrarla con
  `@registry.register` e aggiungere il codice alla selection
  `abc_va_provider` su `res.company`. La logica di business non cambia.
- **Adeguamento alla specifica AdE**: URL, path, header, campi e timeout sono
  costanti in cima a `services/ade_provider.py`.

---

## 7. Test

Nessun test effettua chiamate di rete: il provider e le risposte HTTP sono
simulati.

```bash
odoo-bin -d <db> -i abc_verifica_anagrafica,abc_verifica_anagrafica_sale --test-tags abc_va --stop-after-init
```

Copertura: algoritmo del check digit con omocodia, sanitizzazione del
secret, inneschi, coda, throttle, retry e backoff, cache anti-abuso,
degradazione in assenza del campo codice fiscale, immutabilità e purge del
log, driver AdE (tutti i codici HTTP, timeout, rete), blocco documenti,
innesco su uso effettivo, alert scadenza.

---

## 8. Dati trattati e privacy

Il modulo invia al servizio AdE il solo codice fiscale. Conserva: esito
normalizzato, codice esito, messaggio breve, data, utente che ha innescato,
società, valore verificato. Non conserva mai il payload grezzo. I log e le
richieste concluse vengono eliminati definitivamente dal processo di purge
(retention configurabile, default 24 mesi per i log e 30 giorni per le
richieste concluse). I log applicativi del server non contengono codici
fiscali né credenziali.

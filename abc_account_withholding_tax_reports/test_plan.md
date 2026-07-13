# Piano di Collaudo Funzionale - Report Ritenuta d'Acconto (Storico OCA)

## Ambiente e Pre-requisiti
- **Ambiente**: Odoo 19 locale o di staging.
- **Moduli Richiesti**: `account`, `l10n_it_withholding_tax` (modulo stub legacy) e il nuovo modulo `abc_account_withholding_tax_reports`.
- **Dati**: Devono esserci dei record di test (anche vecchi storici) nelle tabelle `withholding_tax_statement` e `withholding_tax_move` sul database.

## Casi di Test Operativi

### Test 1: Visibilità e Accesso ai Menu
1. Collegarsi a Odoo con un utente avente ruolo `account.group_account_manager` (Responsabile Contabilità).
2. Andare nel modulo principale **Contabilità**.
3. Aprire il menu **Rendicontazione** (o cercare nel menu top/navigazione).
4. Localizzare la voce **Ritenuta d'acconto (Storico)** e verificare che abbia due sottomenu: **Dichiarazione ritenuta d'acconto** e **Movimento ritenuta di acconto**.

### Test 2: Consultazione Dichiarazioni
1. Cliccare su **Dichiarazione ritenuta d'acconto**.
2. Verificare che venga caricata la vista ad albero (Lista) senza errori di sistema.
3. Verificare che le colonne "Importo RdA applicato" e "Importo RdA versato" contengano valori calcolati e non siano tutte a zero (a meno che non ci siano movimenti collegati).
4. Selezionare un record e aprirlo (Form view).
5. Verificare che siano visibili le informazioni del fornitore, le date e i totali.
6. Verificare che *non* sia possibile modificare (tasto "Salva" disabilitato o non presente) o eliminare il record.

### Test 3: Consultazione Movimenti e Sincronizzazione JIT
1. Andare in una fattura fornitore standard (Odoo 19) che possiede una "Dichiarazione ritenuta d'acconto" associata.
2. Registrare il pagamento (parziale o totale) di questa fattura.
3. Tornare nel menu "Contabilità -> Rendicontazione -> Ritenuta d'acconto (Storico)".
4. Cliccare su **Movimento ritenuta di acconto**. In questo preciso istante, il sistema calcolerà in background i pagamenti.
5. Verificare l'apertura della lista e constatare che il movimento appena pagato è comparso magicamente a video con i relativi importi proporzionali.
6. Aprire un singolo record.
7. Verificare che i campi collegati (come le registrazioni contabili originali) siano cliccabili se esistono ancora nel database.

## Risultati Attesi
- Nessun *RPC_ERROR* o traccia di stack trace a video durante l'apertura delle viste.
- Le informazioni archiviate vengono esposte correttamente.
- Rispetto ferreo della policy di "Sola Lettura", l'interfaccia deve bloccare eventuali tentativi di creazione manuale di nuovi record storici.

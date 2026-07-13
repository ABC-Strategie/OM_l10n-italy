# ABC - Report Ritenuta d'Acconto

## Scopo
Questo modulo ripristina la visibilità dei dati storici delle ritenute d'acconto (Dichiarazioni e Movimenti) presenti nel database Odoo, secondo la struttura del modulo OCA per Odoo 16.
A partire da Odoo 19, le ritenute vengono gestite nativamente dalla localizzazione italiana, ma questo modulo permette di consultare i record preesistenti o quelli mantenuti dallo "stub" del modulo OCA senza dover accedere al database grezzo, esponendo le viste di sola lettura sotto il menu Contabilità.

## Installazione / Dipendenze
- Richiede l'installazione del modulo base `account`.
- Richiede la presenza del modulo "stub" `l10n_it_withholding_tax` (situato solitamente in `oca-only-field-for-missing-module`), il quale conserva i modelli Python `withholding.tax.statement` e `withholding.tax.move` a livello di database.

## Funzionamento
Una volta installato:
1. Andare in **Contabilità -> Rendicontazione** (oppure sotto i menu di reportistica contabile).
2. Sarà presente la voce **Ritenuta d'acconto (Storico)**.
3. Al suo interno troverete:
   - **Dichiarazione ritenuta d'acconto**: mostra i riepiloghi delle ritenute raggruppate. I campi "Importo RdA applicato" e "Importo RdA versato" vengono ricalcolati dinamicamente leggendo le righe di movimento.
   - **Movimento ritenuta di acconto**: mostra il dettaglio dei singoli movimenti (applicata, dovuta, pagata).
4. Tutte le viste sono in modalità di sola lettura (read-only) per proteggere i dati storici e impedire la creazione di record secondo logiche obsolete per Odoo 19.

## Logiche Python Integrate
Per via della neutralizzazione di alcuni calcoli nel modulo OCA di "stub", questo modulo estende `withholding.tax.statement` iniettando i metodi computazionali mancanti al fine di mantenere aggiornati i totali "RdA applicato" e "RdA versato" nelle viste list/form.

**Sincronizzazione Just-In-Time (JIT)**: Al click sui menu "Dichiarazione ritenuta d'acconto" o "Movimento ritenuta di acconto", Odoo lancerà in automatico e in background una *Server Action* (`action_sync_wt_moves`). Questa azione analizza le fatture collegate, calcola le proporzioni pagate e genera i record mancanti nella tabella storica dei movimenti (`withholding.tax.move`). Il risultato a video sarà quindi sempre in tempo reale.

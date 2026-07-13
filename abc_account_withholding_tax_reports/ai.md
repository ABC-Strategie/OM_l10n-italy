# Architettura e Food for AI - abc_account_withholding_tax_reports

## Contesto Architetturale
- **Problema originario**: Durante la migrazione da Odoo 16 a Odoo 19, la localizzazione italiana ha introdotto una gestione nativa per le ritenute d'acconto, rendendo obsoleto il modulo OCA `l10n_it_withholding_tax`.
- **Il workaround**: Il team ha mantenuto i modelli Python OCA tramite un modulo "stub" (situato in `oca-only-field-for-missing-module/l10n_it_withholding_tax`), rimuovendo però completamente le interfacce utente (commentando `views/withholding_tax.xml` in quel modulo) per evitare conflitti o inserimenti errati da UI, salvaguardando lo schema e i dati sul DB.
- **La soluzione di questo modulo**: Poiché il cliente necessitava ancora di visualizzare i due report storici (Dichiarazione e Movimenti RDA), questo modulo si limita a definire puramente gli XML (Views, Actions, Menu) appoggiandosi ai vecchi modelli `withholding.tax.statement` e `withholding.tax.move`.

## Insight e Food for AI
- **Sola Lettura**: Tutte le viste introdotte da questo modulo hanno forzatamente `create="false"`, `edit="false"`, e `delete="false"` nei nodi `<tree>` e `<form>`. Non bisogna mai permettere l'inserimento di nuovi record in queste tabelle perché bypasserebbe la logica nativa di Odoo 19 e corromperebbe la contabilità.
- **Dipendenze**: Il modulo dipende esplicitamente da `l10n_it_withholding_tax` (il nome tecnico del modulo stub in `oca-only-field-for-missing-module`) per garantire che i field e i model siano caricati nel Registry di Odoo prima che le viste XML vengano parsate.
- **Design Pattern UI**: I menu sono iniettati sotto `account.menu_finance_reports` in modo da non disturbare i flussi standard di registrazione contabile di Odoo 19.

## Side Effects e Architettura JIT (Just-in-Time)
- È stato introdotto un override Python sul modello `withholding.tax.statement` per ripristinare il calcolo dei campi `amount` (RdA applicato) e `amount_paid` (RdA versato), le cui logiche originali (`_compute_total`) erano state disattivate nel modulo "stub". Il ricalcolo è effettuato tramite il metodo custom `_compute_abc_total` per evitare collisioni con l'eventuale metodo originale commentato.
- Per sopperire alla mancata generazione automatica dei movimenti storici OCA a fronte di pagamenti su Odoo 19, è stato introdotto il metodo `action_sync_wt_moves`.
- I due menu `menu_abc_withholding_tax_statement` e `menu_abc_withholding_tax_move` non lanciano più direttamente una *Window Action*, ma passano per una **Server Action**. Al momento del click, Odoo invoca lo script di sincronizzazione `action_sync_wt_moves` per generare eventuali `withholding.tax.move` mancanti e solo dopo restituisce la Window Action per disegnare la vista a schermo. Questo garantisce l'allineamento dati JIT senza inquinare le API di read/search e senza intaccare i flussi standard di pagamento in Odoo 19.
- In caso di uninstallation del modulo base "stub", questo modulo crasherà perché non troverà più i modelli nel DB.

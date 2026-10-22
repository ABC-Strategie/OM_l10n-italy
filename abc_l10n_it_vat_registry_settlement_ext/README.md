# ABC - Codice ATECO su Registri IVA e Liquidazione IVA senza righe non movimentate

Estensioni ai registri IVA (`l10n_it_vat_registries`) e alla liquidazione IVA
(`l10n_it_account_vat_period_end_settlement`) per BBS Pratiche e Servizi.

## Codice ATECO sul registro IVA

Campo testo **Codice ATECO** sul registro contabile (`account.journal`),
stampato nel PDF del registro IVA accanto al nome del giornale.

## Righe della liquidazione IVA

Nella liquidazione IVA le righe imposta a debito e a credito vengono generate
solo per le imposte **movimentate** nei periodi della liquidazione, cioè con
imposta o imponibile diversi da zero. Vale per il tab **Conti** e per la
stampa, che ricava le aliquote da quelle righe.

Le aliquote **0%** con imponibile nel periodo restano visibili con importo
zero, anche quando non hanno un conto IVA sulle righe di ripartizione
imposta (il modulo base le escluderebbe). Le imposte di vendita vanno tra le
righe a debito, quelle di acquisto tra le righe a credito.

Note:
- Le righe 0% senza conto non entrano nella scrittura contabile della
  liquidazione (importo zero) né nella sezione "Total Settlement" della
  stampa, quindi i totali non cambiano.
- Le aliquote 0% senza conto vengono aggiunte in coda alle altre righe.
- Con il **filtro conti** della liquidazione attivo, le aliquote 0% senza
  conto non vengono aggiunte, perché non si possono attribuire a un conto.
- Dopo l'aggiornamento del modulo, sulle liquidazioni in bozza serve
  **Ricalcola importi** per vedere le nuove righe.

## Wizard "Rimuovi periodo"

La tendina dei periodi del wizard restava vuota perché basata su una
Selection dinamica non più valorizzata da `get_views` in Odoo 19. Il wizard
usa ora un campo Many2one sui periodi della liquidazione.

## Versioni

- **19.0.1.1.0**: aliquote 0% movimentate visibili nella liquidazione IVA
  (tab Conti e stampa), anche senza conto IVA.
- **19.0.1.0.0**: prima versione.

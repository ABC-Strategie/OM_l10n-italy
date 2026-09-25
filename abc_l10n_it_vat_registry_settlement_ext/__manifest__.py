{
    'name': 'ABC - Codice ATECO su Registri IVA e Liquidazione IVA senza righe a zero',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Codice ATECO stampato sul registro IVA vendite e righe di liquidazione IVA filtrate sulle sole aliquote movimentate',
    'description': """
Estensioni ai registri IVA e alla liquidazione IVA per BBS Pratiche e Servizi:

- Campo testo "Codice ATECO" sul registro contabile (account.journal),
  stampato nel PDF del registro IVA accanto al nome del giornale.
- Nella liquidazione IVA, le righe imposta a debito/credito che non hanno
  avuto movimentazione nel periodo (importo zero) non vengono più generate,
  sia in vista che in stampa.
- Corretto il wizard "Rimuovi periodo" della liquidazione IVA: la tendina
  dei periodi restava vuota perché basata su una Selection dinamica non più
  valorizzata da get_views in Odoo 19.

Sviluppato da ABC Strategie S.r.l. per BBS Pratiche e Servizi.
    """,
    'author': 'ABC Strategie S.r.l.',
    'website': 'https://www.abcstrategie.it',
    'license': 'AGPL-3',
    'depends': [
        'l10n_it_vat_registries',
        'l10n_it_account_vat_period_end_settlement',
    ],
    'data': [
        'views/account_journal_view.xml',
        'report/report_registro_iva.xml',
        'wizard/remove_period.xml',
    ],
    'installable': True,
    'application': False,
}

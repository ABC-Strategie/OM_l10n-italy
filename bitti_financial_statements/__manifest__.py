{
    'name': 'Bitti - Situazione contabile a sezioni contrapposte',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Stato patrimoniale e Conto economico a sezioni contrapposte in un unico PDF',
    'description': """
Aggiunge al wizard OCA "Stato patrimoniale e conto economico" (l10n_it_financial_statements_report)
il tipo di report "Situazione contabile a sezioni contrapposte", che stampa in un unico documento:

* SITUAZIONE PATRIMONIALE: Attività a sinistra, Passività a destra
* CONTO ECONOMICO: Componenti negative di reddito a sinistra, positive a destra

Ogni sezione chiude con TOTALE, Utile (o Perdita) e TOTALE A PAREGGIO, sul modello della
"Situazione contabile a sezioni contrapposte" del precedente gestionale di Bitti srl.
Intestazione con dati azienda e periodo, formato A4 verticale, importi a 2 decimali,
gerarchia per gruppi conti (codice civile). La classificazione dei conti usa il campo
"Sezione" del modulo OCA (derivato dal tipo conto, modificabile conto per conto).
    """,
    'author': 'ABC Strategie',
    'website': 'https://www.abcstrategie.it',
    'depends': ['l10n_it_financial_statements_report', 'l10n_it_edi'],
    'data': [
        'report/report_paperformat.xml',
        'report/report_templates.xml',
        'report/report_actions.xml',
        'wizard/wizard_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}

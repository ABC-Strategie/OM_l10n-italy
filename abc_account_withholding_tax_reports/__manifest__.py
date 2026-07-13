# -*- coding: utf-8 -*-
{
    'name': "ABC - Report Ritenuta d'Acconto",
    'summary': "Ripristina le voci di menu e le viste OCA per Dichiarazioni e Movimenti Ritenuta d'Acconto in Odoo 19",
    'description': """
        Aggiunge i menu e le relative viste sotto Contabilità per i modelli:
        - Dichiarazione ritenuta d'acconto (withholding.tax.statement)
        - Movimento ritenuta di acconto (withholding.tax.move)
        
        Si basa sui modelli originari di OCA mantenuti in modalità sola lettura (stub) durante la migrazione.
    """,
    'author': "A.B.C. S.r.l.",
    'website': "https://www.abcstrategie.it",
    'category': 'Accounting',
    'version': '19.0.1.0.1',
    'depends': ['account', 'l10n_it_withholding_tax'],
    'data': [
        'security/ir.model.access.csv',
        'views/withholding_tax_reports_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

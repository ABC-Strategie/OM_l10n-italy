# -*- coding: utf-8 -*-
{
    'name': "ABC - Ratei e risconti",
    'summary': "Ratei e risconti attivi e passivi di fine esercizio con il metodo italiano "
               "(assestamento a D e storno a D + 1)",
    'description': """
        Calcolo a giorni effettivi di ratei e risconti dalle righe contabili con date di
        competenza e da schede manuali/pregresso; elaborazione con anteprima, conferma,
        storno automatico ed elaborazioni integrative; risconti pluriennali, leasing con
        periodo fiscale, prospetti e quadratura. Sostituisce i differimenti nativi di Odoo.
    """,
    'author': "A.B.C. S.r.l.",
    'website': "https://www.abcstrategie.it",
    'category': 'Accounting',
    'version': '19.0.1.7.0',
    'depends': ['account_accountant', 'account_reports', 'l10n_it'],
    'data': [
        'security/ir.model.access.csv',
        'security/rr_security.xml',
        'data/rr_data.xml',
        'views/rr_run_views.xml',
        'views/rr_card_views.xml',
        'views/rr_account_map_views.xml',
        'views/rr_report_views.xml',
        'views/res_config_settings_views.xml',
        'views/account_move_views.xml',
        'wizard/rr_run_wizard_views.xml',
        'wizard/rr_report_wizard_views.xml',
        'wizard/rr_prospetto_wizard_views.xml',
        'report/rr_run_report.xml',
        'report/rr_prospetto_report.xml',
        'views/rr_menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'OPL-1',
}

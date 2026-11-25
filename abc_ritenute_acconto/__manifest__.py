{
    "name": "ABC - Ritenute d'acconto attive e passive",
    "version": "19.0.1.0.1",
    "category": "Accounting/Localizations",
    "summary": "Registro, scadenzario e versamento F24 delle ritenute d'acconto, "
               "credito da ritenute subite, CU e 770",
    "description": """
Registro delle ritenute d'acconto per Odoo 19 (localizzazione italiana).

Ciclo passivo (ritenute operate sui fornitori):
- in fattura la ritenuta resta sul conto del fornitore (debito al lordo, nessun conto d'appoggio);
- al pagamento scrittura nel registro varie: Dare fornitore / Avere Erario c/ritenute da versare;
- scadenza al 16 del mese successivo al pagamento, con festivi e proroga di agosto;
- versamento F24 con sanzioni e interessi, versato in automatico alla riconciliazione bancaria;
- avvisi 5, 3, 1 giorno prima della scadenza e il giorno stesso.

Ciclo attivo (ritenute subite dai clienti):
- credito nato all'incasso, anno fiscale secondo il regime dell'azienda;
- controllo delle CU ricevute, solleciti, scomputo, utilizzo delle eccedenze.

Adempimenti annuali: CU per percipiente e quadro ST del 770, export Excel e stampa PDF.
Specifica funzionale: documento "Specifica modulo Ritenute d'acconto attive e passive".
""",
    "author": "A.B.C. S.r.l.",
    "license": "LGPL-3",
    "depends": ["account", "l10n_it_edi", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "data/tributo_map.xml",
        "report/report_actions.xml",
        "data/mail_template.xml",
        "data/cron.xml",
        "views/res_company_views.xml",
        "views/account_tax_views.xml",
        "views/res_partner_views.xml",
        "views/withholding_views.xml",
        "views/withholding_line_views.xml",
        "views/withholding_payment_views.xml",
        "views/withholding_deadline_views.xml",
        "views/withholding_cu_received_views.xml",
        "views/withholding_credit_views.xml",
        "views/withholding_declaration_views.xml",
        "views/withholding_dashboard_views.xml",
        "views/account_move_views.xml",
        "views/l10n_it_edi_templates.xml",
        "wizard/payment_wizard_views.xml",
        "wizard/rebuild_wizard_views.xml",
        "wizard/deduct_wizard_views.xml",
        "wizard/tax_config_wizard_views.xml",
        "report/report_payment.xml",
        "report/report_cu.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
}

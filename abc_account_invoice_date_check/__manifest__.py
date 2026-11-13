# -*- coding: utf-8 -*-
{
    "name": "A.B.C. - Controllo data fattura",
    "summary": "Avvisa se la data fattura e' anteriore a quella dell'ultima fattura confermata",
    "description": """
        Sui registri vendita con la casella "Controllo data fattura" attiva, mostra un
        avviso sulla fattura in bozza quando la data fattura e' anteriore a quella
        dell'ultima fattura confermata della stessa serie della numerazione nativa di
        Odoo (stesso registro, stesso anno o mese di numerazione, fatture e note di
        credito separate se il registro ha la sequenza dedicata).

        Serve a mantenere la numerazione cronologica: il numero viene assegnato alla
        conferma in base alla data, e Odoo non impedisce da se' una retrodatazione
        all'interno dello stesso periodo.

        L'avviso compare alla creazione e alla reimpostazione a bozza e usa il banner di
        avviso nativo di Odoo. Premendo Conferma con l'avviso presente, un popup chiede
        di confermare comunque o di annullare.
    """,
    "author": "A.B.C. Srl",
    "website": "https://www.abcstrategie.it/",
    "category": "Accounting/Accounting",
    "version": "19.0.1.1.0",
    "depends": ["account"],
    "data": [
        "views/account_journal_views.xml",
        "views/account_move_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "abc_account_invoice_date_check/static/src/**/*",
        ],
    },
    "license": "OPL-1",
    "installable": True,
    "application": False,
    "auto_install": False,
}

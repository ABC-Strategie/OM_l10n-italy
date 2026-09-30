# -*- coding: utf-8 -*-
{
    "name": "A.B.C. - Conti di costo/ricavo per contatto",
    "summary": "Conto di ricavo e conto di costo impostabili sul contatto e applicati alle righe fattura",
    "description": """
        Aggiunge nel tab Contabilita' del contatto due conti:

        - Conto di ricavo: usato sulle righe delle fatture e note di credito cliente;
        - Conto di costo: usato sulle righe delle fatture e note di credito fornitore.

        Quando il conto e' valorizzato sul contatto prevale su quello che arriverebbe dal
        prodotto o dalla sua categoria. Se sulla fattura e' impostata una posizione fiscale,
        al conto del contatto viene applicata la stessa mappatura che Odoo applica al conto
        del prodotto. Lasciando i campi vuoti il comportamento standard resta invariato.
    """,
    "author": "A.B.C. Srl",
    "website": "https://www.abcstrategie.it/",
    "category": "Accounting/Accounting",
    "version": "19.0.1.1.0",
    # account_accountant: per estendere la previsione del conto da storico (_predict_specific_account).
    "depends": ["account", "account_accountant"],
    "data": [
        "views/res_partner_views.xml",
    ],
    "license": "OPL-1",
    "installable": True,
    "application": False,
    "auto_install": False,
}

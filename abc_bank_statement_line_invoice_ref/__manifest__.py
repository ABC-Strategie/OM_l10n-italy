# -*- coding: utf-8 -*-
{
    "name": "A.B.C. - Riferimento transazione da fattura",
    "summary": "Compila il riferimento della transazione bancaria con riferimento e data delle fatture riconciliate",
    "description": """
        In Contabilita' > Corrispondenza bancaria, quando una transazione viene
        riconciliata con una o piu' fatture, il campo Riferimento della transazione
        viene compilato con il riferimento e la data di ciascuna fattura pagata, per
        esempio "FT/001 del 12/03/2026, FT/002 del 15/03/2026".

        Per le fatture cliente si usa il numero della fattura, per le fatture
        fornitore il Riferimento (numero del fornitore) o, se vuoto, il numero.
        Sono gestiti anche i pagamenti intermedi (transazione abbinata a un
        pagamento a sua volta riconciliato con la fattura).

        Annullando la riconciliazione il riferimento viene ricalcolato, e svuotato se
        non resta nessuna fattura.

        All'installazione il riferimento viene compilato anche sulle transazioni gia'
        riconciliate. L'azione "Aggiorna riferimento da fatture" sulla lista delle
        transazioni permette di rilanciare il calcolo sulle righe selezionate.
    """,
    "author": "A.B.C. Srl",
    "website": "https://www.abcstrategie.it/",
    "category": "Accounting/Accounting",
    "version": "19.0.1.0.0",
    "depends": ["account_accountant"],
    "data": [
        "data/ir_actions_server.xml",
    ],
    "post_init_hook": "post_init_hook",
    "license": "OPL-1",
    "installable": True,
    "application": False,
    "auto_install": False,
}

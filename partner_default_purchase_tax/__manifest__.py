{
    "name": "Imposta acquisti predefinita per fornitore",
    "summary": "Imposta di acquisto predefinita per singolo fornitore, "
               "proposta sulle righe delle fatture fornitore anche senza prodotto.",
    "description": """
Imposta acquisti predefinita per fornitore
==========================================

Aggiunge sull'anagrafica del contatto (res.partner) un campo
"Imposta acquisti predefinita".

Quando si registra una FATTURA FORNITORE (in_invoice / in_refund) e si inserisce
una riga MANUALE senza prodotto, l'imposta indicata sul fornitore viene proposta
automaticamente sulla riga contabile, dopo essere stata rimappata attraverso la
Posizione fiscale del fornitore (se presente).

Vantaggio rispetto all'imposta di default sul CONTO:
il default resta legato al FORNITORE e agisce solo in fattura, quindi NON inquina
le scritture di prima nota manuali (partita doppia) che usano gli stessi conti.
    """,
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "ABC Strategie",
    "website": "https://www.abcstrategie.it",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "views/res_partner_views.xml",
    ],
    "installable": True,
    "application": False,
}

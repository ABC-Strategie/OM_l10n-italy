# -*- coding: utf-8 -*-
{
    "name": "Modelli di scrittura contabile",
    "summary": "Crea modelli riutilizzabili di scritture contabili e genera "
               "registrazioni nei registri di tipo Varie",
    "description": """
Modelli di scrittura contabile
==============================

Modulo autonomo (non modifica né eredita alcun modulo esistente).

Permette di:

* creare un *modello* di scrittura contabile con una descrizione generale
  e un elenco di conti (righe con etichetta, lato Dare/Avere, importo);
* riordinare le righe con il trascinamento;
* ricevere un avviso quando un conto viene messo nel lato "insolito"
  rispetto alla sua natura (es. un conto di costo in Avere);
* bloccare il modello dopo la conferma: si può modificare solo dopo
  un avviso di conferma;
* generare, a partire dal modello, una registrazione contabile in un
  registro di tipo Varie, indicando ogni mese solo gli importi effettivi
  (le righe lasciate a zero non vengono riportate).
""",
    "author": "ABC Srl",
    "website": "https://www.abcstrategie.it",
    "category": "Accounting/Accounting",
    "version": "19.0.1.2.0",
    "license": "LGPL-3",
    "depends": ["account", "analytic"],
    "data": [
        "security/ir.model.access.csv",
        "views/scrittura_template_views.xml",
        "wizard/genera_scrittura_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
}

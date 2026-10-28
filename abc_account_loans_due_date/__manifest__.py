# -*- coding: utf-8 -*-
{
    'name': 'ABC - Prestiti: scritture alla scadenza della rata',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': "Le scritture generate dai prestiti prendono la data di scadenza della rata",
    'description': """
Prestiti: scritture alla scadenza della rata
============================================
Il modulo standard Prestiti (account_loans) data le scritture generate alla
conferma del prestito a fine mese (Capitale e interessi, Riclassificazione
LT - ST) e al primo giorno del mese successivo (Riclassificazione di storno
LT - ST).

Con questo modulo tutte e tre le scritture prendono la data di scadenza della
rata del piano di ammortamento.

Per i prestiti gia' confermati, il pulsante "Riallinea date a scadenza rata"
(e l'omonima azione in lista) ridata le scritture gia' generate:

* bozze: viene cambiata solo la data;
* confermate: rimesse in bozza, ridatate e riconfermate. Se la nuova data
  cade in un altro mese la scrittura riceve un nuovo numero;
* scritture in periodo bloccato o con hash: non vengono toccate e sono
  segnalate a fine elaborazione.
""",
    'author': 'ABC srl',
    'website': 'https://www.abcstrategie.it',
    'license': 'LGPL-3',
    'depends': [
        'account_loans',
    ],
    'data': [
        'views/account_loan_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

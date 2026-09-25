{
    'name': 'Verifica anagrafica tributaria - Vendite',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Innesco della verifica del codice fiscale e policy su esito '
               'non valido alla conferma degli ordini di vendita',
    'description': """
Modulo ponte, installato automaticamente quando sono presenti sia
"Verifica anagrafica tributaria" sia Vendite.

- alla conferma di un ordine di vendita, un contatto mai verificato viene
  accodato per la verifica (innesco su uso effettivo, configurabile);
- con policy "Blocca la conferma dei documenti", un ordine verso un soggetto
  con codice fiscale non valido non può essere confermato;
- banner di avviso sull'ordine.

Sviluppato da ABC Strategie.
    """,
    'author': 'ABC Strategie',
    'website': 'https://www.abcstrategie.it',
    'license': 'LGPL-3',
    'depends': [
        'abc_verifica_anagrafica',
        'sale',
    ],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': True,
}

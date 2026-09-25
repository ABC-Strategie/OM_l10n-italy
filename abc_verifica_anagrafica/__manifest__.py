{
    'name': 'Verifica anagrafica tributaria',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Verifica puntuale dei codici fiscali delle persone fisiche '
               'tramite le API dell\'Agenzia delle Entrate',
    'description': """
Verifica anagrafica tributaria
==============================

Verifica l'esistenza e la validità dei codici fiscali di persone fisiche
presenti nelle anagrafiche contatti, interrogando le API "anagrafiche"
dell'Agenzia delle Entrate (Piattaforma API Management, Catalogo dei
servizi di interoperabilità).

Caratteristiche:

- verifica esclusivamente puntuale: alla creazione o modifica del codice
  fiscale di un contatto, oppure su richiesta esplicita dell'utente sul
  singolo record. Nessuna verifica massiva, in conformità alle Condizioni
  generali di utilizzo del servizio AdE (art. 8);
- pre-controllo formale locale (check digit, omocodia) prima di ogni chiamata;
- coda interna elaborata da cron, con throttle configurabile per minuto e
  per giorno e retry con backoff;
- livello driver astratto: il provider (Agenzia delle Entrate) è isolato e
  sostituibile senza toccare la logica di business;
- credenziali per società, secret protetto e mai esposto in log o messaggi;
- alert di scadenza del client secret;
- retention configurabile dei log con purge automatico;
- blocco opzionale della conferma dei documenti contabili verso soggetti
  con codice fiscale non valido.

Sviluppato da ABC Strategie.
    """,
    'author': 'ABC Strategie',
    'website': 'https://www.abcstrategie.it',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'contacts',
        'account',
        'l10n_it_edi',
    ],
    'data': [
        # Security: privilege e gruppi PRIMA delle ACL e delle regole
        'security/security.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        # Dati
        'data/ir_cron.xml',
        # Viste
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/abc_va_queue_views.xml',
        'views/abc_va_log_views.xml',
        'views/account_move_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'abc_verifica_anagrafica/static/src/js/partner_form_refresh.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

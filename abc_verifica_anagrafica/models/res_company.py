# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from ..services import registry
from ..services.base_provider import ESITO_VALIDO

# Default allineati alla specifica del servizio AdE "API anagrafiche libero
# accesso" (README.txt della documentazione tecnica): 10 richieste/minuto,
# 100 richieste/giorno per client, controllo best effort lato AdE.
DEFAULT_RATE_MINUTE = 10
DEFAULT_RATE_DAY = 100
DEFAULT_RETENTION_MONTHS = 24
DEFAULT_RECHECK_HOURS = 24

PROVIDER_SELECTION = [
    ('ade', 'Agenzia delle Entrate'),
    # ('openapi', 'Openapi'),  # predisposto, driver non ancora implementato
]

ENVIRONMENT_SELECTION = [
    ('test', 'Test'),
    ('prod', 'Produzione'),
]

# Soglie (giorni alla scadenza) per gli alert sul client secret; 0 = scaduto
ALERT_THRESHOLDS = (60, 30, 7, 0)

NAME_CHECK_SELECTION = [
    ('block', 'Blocca il salvataggio'),
    ('flag', 'Segnala come non valido'),
    ('off', 'Disattivo'),
]

PIVA_NAME_CHECK_SELECTION = [
    ('block', 'Blocca la conferma dei documenti'),
    ('warn', 'Solo avviso'),
    ('off', 'Disattivo'),
]

ON_INVALID_SELECTION = [
    ('none', 'Nessuna azione'),
    ('warn', 'Solo avviso'),
    ('block_document', 'Blocca la conferma dei documenti'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    # ------------------------------------------------------------------
    # Interruttore e provider
    # ------------------------------------------------------------------
    abc_va_enabled = fields.Boolean(
        string='Verifica anagrafica attiva',
        default=False,
        help="Interruttore generale. Se disattivo, nessun evento accoda "
             "verifiche e il cron non elabora la coda per questa società.",
    )
    abc_va_provider = fields.Selection(
        selection=PROVIDER_SELECTION,
        string='Provider di verifica',
        default='ade',
        required=True,
    )
    abc_va_environment = fields.Selection(
        selection=ENVIRONMENT_SELECTION,
        string='Ambiente',
        default='prod',
        required=True,
        help="Ambiente del provider. La documentazione AdE attualmente "
             "pubblica solo l'endpoint di produzione: per usare 'Test' "
             "occorre indicare l'URL base dell'ambiente di test.",
    )
    abc_va_test_base_url = fields.Char(
        string='URL base ambiente di test',
        help="URL base dell'ambiente di test del provider, se fornito dalla "
             "relativa documentazione. Usato solo con ambiente = Test.",
    )

    # ------------------------------------------------------------------
    # Credenziali (per società: ogni società aderisce in proprio al servizio)
    # ------------------------------------------------------------------
    abc_va_client_id = fields.Char(
        string='Client ID',
        copy=False,
        groups='abc_verifica_anagrafica.group_abc_va_manager',
    )
    abc_va_client_secret = fields.Char(
        string='Client Secret',
        copy=False,
        groups='abc_verifica_anagrafica.group_abc_va_manager',
        help="Rilasciato dal Catalogo dei servizi di interoperabilità AdE "
             "al momento dell'attivazione. Non viene mai mostrato in "
             "chiaro né riportato in log o messaggi.",
    )
    abc_va_secret_expiry = fields.Date(
        string='Scadenza client secret',
        copy=False,
        help="Data di scadenza riportata nel file credenziali scaricato "
             "dal Catalogo AdE. Alla scadenza il servizio smette di "
             "funzionare: il secret va rigenerato manualmente in area "
             "riservata.",
    )
    abc_va_secret_days_left = fields.Integer(
        string='Giorni alla scadenza',
        compute='_compute_abc_va_secret_days_left',
        help="Giorni mancanti alla scadenza del client secret. Negativo se "
             "già scaduto.",
    )
    abc_va_alert_user_id = fields.Many2one(
        'res.users',
        string='Responsabile alert scadenza',
        help="Utente a cui vengono assegnate le attività di avviso a 60, 30 "
             "e 7 giorni dalla scadenza del client secret.",
    )
    abc_va_alerted_thresholds = fields.Char(
        string='Soglie di alert già notificate',
        copy=False,
        help="Tecnico: soglie (giorni) per cui è già stata creata "
             "un'attività per la data di scadenza corrente. Si azzera al "
             "cambio della data.",
    )

    abc_va_name_check = fields.Selection(
        selection=NAME_CHECK_SELECTION,
        string='Coerenza tra codice fiscale e nome',
        default='block',
        required=True,
        help="Controllo locale, senza chiamate: le prime sei lettere del "
             "codice fiscale devono corrispondere a cognome e nome del "
             "contatto secondo le regole ufficiali. 'Blocca' impedisce il "
             "salvataggio; 'Segnala' lascia salvare ma marca il contatto "
             "come non valido. Nomi di una sola parola non vengono "
             "controllati.",
    )

    # ------------------------------------------------------------------
    # Partita IVA
    # ------------------------------------------------------------------
    abc_va_piva_enabled = fields.Boolean(
        string='Verifica delle partite IVA',
        default=True,
        help="Verifica puntuale delle partite IVA italiane dei contatti "
             "(aziende e ditte individuali) con lo stesso servizio: esito, "
             "denominazione, cessazione o sospensione dell'attività. Le "
             "chiamate rientrano negli stessi limiti del codice fiscale.",
    )
    abc_va_on_ceased = fields.Selection(
        selection=ON_INVALID_SELECTION,
        string='Comportamento su partita IVA cessata o sospesa',
        default='block_document',
        required=True,
        help="Partita IVA esistente ma con attività cessata o sospesa "
             "secondo l'Anagrafe Tributaria.",
    )
    abc_va_piva_name_check = fields.Selection(
        selection=PIVA_NAME_CHECK_SELECTION,
        string='Confronto con la denominazione AdE',
        default='warn',
        required=True,
        help="Confronto tra il nome del contatto e la denominazione "
             "restituita dall'Anagrafe Tributaria, ignorando forma giuridica, "
             "punteggiatura e ordine delle parole. In caso di differenza "
             "sostanziale il contatto viene segnalato e, con 'Blocca', i "
             "documenti non possono essere confermati finché la "
             "denominazione non viene allineata.",
    )

    # ------------------------------------------------------------------
    # Innesco su uso effettivo del contatto
    # ------------------------------------------------------------------
    abc_va_trigger_on_invoice = fields.Boolean(
        string='Verifica alla conferma di fatture',
        default=True,
        help="Se il contatto non è mai stato verificato, la conferma di una "
             "fattura o nota di credito verso di lui accoda la verifica. "
             "Consente di verificare progressivamente l'anagrafica storica "
             "nell'ambito dell'ordinario utilizzo dei dati.",
    )
    abc_va_trigger_on_sale = fields.Boolean(
        string='Verifica alla conferma di ordini di vendita',
        default=True,
        help="Come per le fatture, alla conferma di un ordine di vendita. "
             "Richiede l'app Vendite.",
    )

    # ------------------------------------------------------------------
    # Throttle, cache, retention, policy
    # ------------------------------------------------------------------
    abc_va_rate_minute = fields.Integer(
        string='Max chiamate al minuto',
        default=DEFAULT_RATE_MINUTE,
        help="Limite hard di chiamate al provider per minuto. Al "
             "superamento le verifiche restano in coda e l'evento viene "
             "registrato nel log.",
    )
    abc_va_rate_day = fields.Integer(
        string='Max chiamate al giorno',
        default=DEFAULT_RATE_DAY,
        help="Limite hard di chiamate al provider per giorno solare.",
    )
    abc_va_recheck_hours = fields.Integer(
        string='Ore di validità esito (anti-abuso)',
        default=DEFAULT_RECHECK_HOURS,
        help="Se esiste già una verifica sullo stesso valore entro queste "
             "ore, 'Verifica ora' mostra l'esito in cache senza chiamare il "
             "provider, salvo forzatura da parte di un amministratore.",
    )
    abc_va_retention_months = fields.Integer(
        string='Retention log (mesi)',
        default=DEFAULT_RETENTION_MONTHS,
        help="I log di verifica più vecchi di questo numero di mesi vengono "
             "eliminati definitivamente dal cron di purge.",
    )
    abc_va_on_invalid = fields.Selection(
        selection=ON_INVALID_SELECTION,
        string='Comportamento su codice fiscale non valido',
        default='warn',
        required=True,
        help="'Blocca la conferma dei documenti' impedisce la conferma di "
             "fatture e documenti contabili verso soggetti con esito non "
             "valido. Un errore tecnico del provider non blocca mai.",
    )

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    def write(self, vals):
        if 'abc_va_secret_expiry' in vals and 'abc_va_alerted_thresholds' not in vals:
            # nuova data di scadenza: gli alert ripartono da zero
            vals = dict(vals, abc_va_alerted_thresholds=False)
        return super().write(vals)

    # ------------------------------------------------------------------
    # Compute / constraints
    # ------------------------------------------------------------------
    @api.depends('abc_va_secret_expiry')
    def _compute_abc_va_secret_days_left(self):
        today = fields.Date.context_today(self)
        for company in self:
            if company.abc_va_secret_expiry:
                company.abc_va_secret_days_left = (
                    company.abc_va_secret_expiry - today
                ).days
            else:
                company.abc_va_secret_days_left = 0

    @api.constrains('abc_va_rate_minute', 'abc_va_rate_day',
                    'abc_va_retention_months', 'abc_va_recheck_hours')
    def _check_abc_va_limits(self):
        for company in self:
            if company.abc_va_rate_minute < 1 or company.abc_va_rate_day < 1:
                raise ValidationError(_(
                    "I limiti di chiamate al minuto e al giorno devono "
                    "essere almeno 1."
                ))
            if company.abc_va_rate_minute > company.abc_va_rate_day:
                raise ValidationError(_(
                    "Il limite al minuto non può superare il limite "
                    "giornaliero."
                ))
            if company.abc_va_retention_months < 1:
                raise ValidationError(_(
                    "La retention dei log deve essere di almeno 1 mese."
                ))
            if company.abc_va_recheck_hours < 0:
                raise ValidationError(_(
                    "Le ore di validità dell'esito non possono essere "
                    "negative."
                ))

    @api.constrains('abc_va_enabled', 'abc_va_environment',
                    'abc_va_test_base_url')
    def _check_abc_va_environment(self):
        for company in self:
            if (company.abc_va_enabled
                    and company.abc_va_environment == 'test'
                    and not company.abc_va_test_base_url):
                raise ValidationError(_(
                    "Per attivare la verifica in ambiente Test è necessario "
                    "indicare l'URL base dell'ambiente di test."
                ))

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    def _abc_va_secret_is_expired(self):
        self.ensure_one()
        return bool(
            self.abc_va_secret_expiry
            and self.abc_va_secret_expiry < fields.Date.context_today(self)
        )

    def _abc_va_is_operational(self):
        """True se la società può effettuare chiamate al provider.

        Legge le credenziali con sudo perché il chiamante (cron, utente
        base) potrebbe non avere il gruppo amministratore.
        """
        self.ensure_one()
        company = self.sudo()
        return bool(
            company.abc_va_enabled
            and company.abc_va_client_id
            and company.abc_va_client_secret
            and not company._abc_va_secret_is_expired()
        )

    # ------------------------------------------------------------------
    # Test connessione
    # ------------------------------------------------------------------
    def _abc_va_health_check(self):
        """Health check del provider configurato. Non salva nulla.

        :return: tupla ``(ok, message)`` con messaggio leggibile e già
            sanitizzato, comprensivo dello stato delle credenziali.
        """
        self.ensure_one()
        company = self.sudo()
        try:
            provider = registry.get_provider(company)
        except registry.ProviderNotAvailable:
            return False, _("Provider '%s' non disponibile.", company.abc_va_provider)
        result = provider.health_check()
        ok = result['esito'] == ESITO_VALIDO
        notes = []
        if not company.abc_va_client_id or not company.abc_va_client_secret:
            notes.append(_("credenziali non configurate"))
        elif company._abc_va_secret_is_expired():
            notes.append(_("client secret scaduto il %s", company.abc_va_secret_expiry))
        elif company.abc_va_secret_days_left <= 30:
            notes.append(_("client secret in scadenza tra %s giorni", company.abc_va_secret_days_left))
        if not company.abc_va_enabled:
            notes.append(_("verifica non attiva"))
        message = result['messaggio'] or ''
        if notes:
            message = f"{message} ({'; '.join(notes)})"
        return ok, message

    # ------------------------------------------------------------------
    # Alert scadenza client secret
    # ------------------------------------------------------------------
    @api.model
    def _cron_abc_va_secret_expiry_alerts(self):
        """Cron giornaliero: un'attività per soglia (60, 30, 7 giorni e
        scaduto), mai ripetuta per la stessa data di scadenza."""
        today = fields.Date.context_today(self)
        companies = self.sudo().search([('abc_va_secret_expiry', '!=', False)])
        for company in companies:
            days_left = (company.abc_va_secret_expiry - today).days
            alerted = {t for t in (company.abc_va_alerted_thresholds or '').split(',') if t}
            due = [t for t in ALERT_THRESHOLDS if days_left <= t and str(t) not in alerted]
            if not due:
                continue
            # Una sola attività per esecuzione, per la soglia più urgente;
            # le soglie meno urgenti già superate vengono marcate insieme.
            company._abc_va_schedule_expiry_activity(min(due), days_left)
            company.abc_va_alerted_thresholds = ','.join(
                str(t) for t in ALERT_THRESHOLDS if str(t) in alerted or t in due)
        return True

    def _abc_va_alert_user(self):
        self.ensure_one()
        user = self.abc_va_alert_user_id
        if not user or not user.active:
            user = self.env.ref('base.user_admin', raise_if_not_found=False)
        return user

    def _abc_va_schedule_expiry_activity(self, threshold, days_left):
        """Crea l'attività sul partner della società (che ha il chatter),
        assegnata al responsabile configurato."""
        self.ensure_one()
        user = self._abc_va_alert_user()
        if not user:
            return self.env['mail.activity']
        if days_left < 0:
            summary = _("Client secret AdE SCADUTO: rigenerare le credenziali")
            detail = _("Il client secret del servizio di verifica anagrafica è scaduto il %s. "
                       "Le verifiche sono sospese.", self.abc_va_secret_expiry)
        else:
            summary = _("Client secret AdE in scadenza tra %s giorni", days_left)
            detail = _("Il client secret del servizio di verifica anagrafica scade il %s.",
                       self.abc_va_secret_expiry)
        note = (
            f"<p>{detail}</p>"
            "<p>" + _("Procedura: area riservata Agenzia delle Entrate, Catalogo dei servizi "
                      "di interoperabilità, sezione 'Servizi attivati', rigenerare il client "
                      "secret e scaricare il nuovo file credenziali. Inserire il nuovo secret e "
                      "la nuova data di scadenza in Impostazioni > Contabilità > Verifica "
                      "anagrafica tributaria.") + "</p>"
        )
        return self.partner_id.sudo().activity_schedule(
            act_type_xmlid='mail.mail_activity_data_todo',
            summary=summary,
            note=note,
            user_id=user.id,
            date_deadline=max(self.abc_va_secret_expiry, fields.Date.context_today(self)),
        )

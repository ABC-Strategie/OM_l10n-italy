# -*- coding: utf-8 -*-
import logging
import threading
import time
from datetime import timedelta

from odoo import api, fields, models, _

from ..services import registry
from ..services.base_provider import (
    ESITO_VALIDO, ESITO_NON_VALIDO, ESITO_ERRORE,
    CODE_UNEXPECTED, CODE_CONFIG,
)
from ..tools import codice_fiscale as cf_tools
from ..tools.sanitize import sanitize_text, sanitize_exception

import json

_logger = logging.getLogger(__name__)

KIND_SELECTION = [
    ('cf', 'Codice fiscale'),
    ('piva', 'Partita IVA'),
]

STATE_SELECTION = [
    ('pending', 'In attesa'),
    ('done', 'Elaborata'),
    ('error', 'Errore'),
    ('cancelled', 'Annullata'),
]

MAX_ATTEMPTS = 3
# Backoff esponenziale: 2, 4, 8 minuti (in assenza di Retry-After)
BASE_BACKOFF_SECONDS = 120
# Numero massimo di richieste caricate per esecuzione del cron. Le
# richieste che richiedono il provider si fermano comunque al throttle.
BATCH_SIZE = 50
# Finestre del throttle (sliding window, più prudente del giorno solare)
MINUTE_WINDOW_SECONDS = 60
DAY_WINDOW_SECONDS = 24 * 3600

# XML ID del cron di elaborazione, svegliato a ogni accodamento
CRON_XMLID = 'abc_verifica_anagrafica.cron_abc_va_process_queue'
# Prefisso della chiave del lock PostgreSQL che serializza, per società, le
# chiamate al provider tra cron e verifiche manuali sincrone
LOCK_KEY_PREFIX = 'abc_va_provider_lock:'

# Tipo di notifica bus inviata all'utente che ha innescato la verifica
# quando l'esito è disponibile (il client ricarica la scheda del contatto)
BUS_NOTIFICATION_TYPE = 'abc_va/partner_updated'

# Codici esito locali (non provengono dal provider)
CODE_FORMAL_INVALID = 'FORMAL_INVALID'
CODE_NAME_MISMATCH = 'NAME_MISMATCH'
CODE_CACHED = 'CACHED'
CODE_THROTTLED = 'THROTTLED'
CODE_SUPERSEDED = 'SUPERSEDED'
CODE_NOT_APPLICABLE = 'NOT_APPLICABLE'
CODE_PROVIDER_MISSING = 'PROVIDER_MISSING'
CODE_MAX_ATTEMPTS = 'MAX_ATTEMPTS'


class AbcVaQueue(models.Model):
    """Coda interna delle verifiche.

    Ogni evento (creazione, modifica del CF, richiesta manuale) accoda un
    record; il cron di elaborazione li processa uno alla volta nel rispetto
    del throttle. Nessuna chiamata HTTP avviene mai in create/write/onchange:
    il cron è l'unico consumatore del provider, quindi il conteggio del
    throttle non è soggetto a race condition.
    """
    _name = 'abc.va.queue'
    _description = 'Verifica anagrafica: coda'
    _order = 'create_date asc, id asc'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company',
        string='Società',
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Contatto',
        required=True,
        ondelete='cascade',
        index=True,
        check_company=True,
    )
    kind = fields.Selection(
        selection=KIND_SELECTION,
        string='Tipo',
        required=True,
        default='cf',
    )
    value = fields.Char(
        string='Valore da verificare',
        required=True,
        help="Valore del codice fiscale al momento dell'accodamento. Se al "
             "momento dell'elaborazione il contatto ha un valore diverso, la "
             "richiesta viene annullata (ne esiste una più recente).",
    )
    state = fields.Selection(
        selection=STATE_SELECTION,
        string='Stato',
        required=True,
        default='pending',
        index=True,
    )
    attempts = fields.Integer(
        string='Tentativi',
        default=0,
    )
    max_attempts = fields.Integer(
        string='Tentativi massimi',
        default=MAX_ATTEMPTS,
    )
    next_try = fields.Datetime(
        string='Prossimo tentativo',
        help="Non elaborare prima di questa data/ora (backoff dopo un "
             "errore transitorio o Retry-After del provider).",
    )
    last_error = fields.Char(
        string='Ultimo errore',
        help="Messaggio leggibile e sanitizzato dell'ultimo errore.",
    )
    force = fields.Boolean(
        string='Forza ri-verifica',
        default=False,
        help="Ignora l'esito in cache e chiama comunque il provider. "
             "Impostabile solo da un amministratore del modulo.",
    )
    user_id = fields.Many2one(
        'res.users',
        string='Innescata da',
        default=lambda self: self.env.user,
    )
    log_id = fields.Many2one(
        'abc.va.log',
        string='Log esito',
        readonly=True,
        ondelete='set null',
    )

    @api.depends('partner_id', 'value', 'state')
    def _compute_display_name(self):
        for job in self:
            job.display_name = f'{job.partner_id.display_name or ""} - {job.value} ({job.state})'

    # ==================================================================
    # Azioni manuali (amministratore)
    # ==================================================================
    def action_retry(self):
        for job in self.filtered(lambda j: j.state == 'error'):
            job.write({'state': 'pending', 'attempts': 0, 'next_try': False, 'last_error': False})
            if job.partner_id._abc_va_state(job.kind) == 'error':
                job.partner_id._abc_va_reset('pending', kind=job.kind)
        self._abc_va_wake_cron()
        return True

    def action_cancel(self):
        self.filtered(lambda j: j.state == 'pending').write({
            'state': 'cancelled', 'last_error': _("Annullata manualmente.")})
        return True

    # ==================================================================
    # Accodamento
    # ==================================================================
    @api.model
    def _abc_va_enqueue(self, partner, value, company, kind='cf', force=False, user=None):
        """Accoda una verifica di tipo ``kind`` per ``partner`` sul valore ``value``.

        - annulla le richieste pendenti dello stesso partner con valore
          diverso (superate);
        - non duplica una richiesta pendente identica (ne aggiorna al più il
          flag ``force``);
        - ritorna il record in coda (esistente o nuovo).
        Sempre eseguito con sudo: l'utente che modifica un contatto non ha
        necessariamente diritti sulla coda.
        """
        Queue = self.sudo()
        pending = Queue.search([
            ('partner_id', '=', partner.id),
            ('kind', '=', kind),
            ('state', '=', 'pending'),
        ])
        superseded = pending.filtered(lambda j: j.value != value)
        if superseded:
            superseded.write({
                'state': 'cancelled',
                'last_error': _("Richiesta superata: il valore da verificare è cambiato."),
            })
        existing = pending - superseded
        if existing:
            if force and not existing[0].force:
                existing[0].force = True
            return existing[0]
        job = Queue.create([{
            'partner_id': partner.id,
            'company_id': company.id,
            'kind': kind,
            'value': value,
            'force': bool(force),
            'user_id': (user or self.env.user).id,
        }])
        self._abc_va_wake_cron()
        return job

    @api.model
    def _abc_va_wake_cron(self, at=None):
        """Sveglia il cron di elaborazione (subito o all'istante ``at``) così
        che le richieste accodate vengano elaborate in pochi secondi invece
        di attendere l'intervallo del cron."""
        cron = self.env.ref(CRON_XMLID, raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger(at=at)

    @api.model
    def _abc_va_lock(self, company):
        """Lock consultivo PostgreSQL per società, rilasciato a fine
        transazione. Cron e verifiche manuali sincrone lo acquisiscono prima
        di controllare il throttle e chiamare il provider: il conteggio delle
        chiamate resta corretto anche con richieste concorrenti."""
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            (f'{LOCK_KEY_PREFIX}{company.id}',),
        )

    # ==================================================================
    # Cache anti-abuso
    # ==================================================================
    @api.model
    def _abc_va_find_cached(self, company, value, kind='cf'):
        """Ultimo esito reale (chiamata al provider) sullo stesso valore
        entro ``abc_va_recheck_hours``. Ritorna un record ``abc.va.log`` o
        un recordset vuoto."""
        hours = company.abc_va_recheck_hours
        if hours <= 0:
            return self.env['abc.va.log'].sudo()
        since = fields.Datetime.now() - timedelta(hours=hours)
        return self.env['abc.va.log'].sudo().search([
            ('company_id', '=', company.id),
            ('kind', '=', kind),
            ('value', '=', value),
            ('event', '=', 'api'),
            ('result', 'in', (ESITO_VALIDO, ESITO_NON_VALIDO)),
            ('timestamp', '>=', since),
        ], order='timestamp desc, id desc', limit=1)

    @api.model
    def _abc_va_apply_cached(self, partner, cached, value, kind, company, user=None):
        """Applica al partner un esito in cache e registra l'evento."""
        message = _("Esito del %s riutilizzato: %s",
                    fields.Datetime.to_string(cached.timestamp), cached.message or '')
        log = self._abc_va_log('cache', cached.result, CODE_CACHED, message=message,
                               partner=partner, value=value, company=company, kind=kind,
                               user=user, details=cached.details)
        if kind == 'piva':
            partner.sudo()._abc_va_apply_piva_outcome(
                cached.result, cached.message or '', value, self._abc_va_details_load(cached.details))
        else:
            state = 'valid' if cached.result == ESITO_VALIDO else 'invalid'
            partner.sudo()._abc_va_apply_result(state, message, value, kind=kind)
        return log

    @staticmethod
    def _abc_va_details_dump(dati):
        if not dati:
            return False
        try:
            return json.dumps(dati, ensure_ascii=False, default=str)[:1000]
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _abc_va_details_load(text):
        if not text:
            return {}
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    # ==================================================================
    # Throttle
    # ==================================================================
    @api.model
    def _abc_va_api_calls_since(self, company, seconds):
        since = fields.Datetime.now() - timedelta(seconds=seconds)
        return self.env['abc.va.log'].sudo().search_count([
            ('company_id', '=', company.id),
            ('event', '=', 'api'),
            ('timestamp', '>=', since),
        ])

    @api.model
    def _abc_va_throttle_check(self, company):
        """Ritorna ``(allowed, limit_type)``. ``limit_type`` è ``'minute'``
        o ``'day'`` quando il limite corrispondente è raggiunto."""
        company = company.sudo()
        if self._abc_va_api_calls_since(company, DAY_WINDOW_SECONDS) >= company.abc_va_rate_day:
            return False, 'day'
        if self._abc_va_api_calls_since(company, MINUTE_WINDOW_SECONDS) >= company.abc_va_rate_minute:
            return False, 'minute'
        return True, None

    # ==================================================================
    # Log
    # ==================================================================
    def _abc_va_log(self, event, result, result_code, message='',
                    http_status=0, partner=None, value=None, company=None,
                    kind=None, user=None, duration_ms=0, details=None):
        """Crea una riga di log sanitizzata. Utilizzabile sia su un job
        (``self`` singolo) sia a livello di modello passando i parametri."""
        job = self if len(self) == 1 else self.browse()
        company = (company or job.company_id).sudo()
        secrets = [company.abc_va_client_secret, company.abc_va_client_id]
        vals = {
            'company_id': company.id,
            'partner_id': (partner or job.partner_id).id or False,
            'kind': kind or job.kind or 'cf',
            'value': value if value is not None else (job.value or ''),
            'event': event,
            'result': result,
            'result_code': sanitize_text(result_code, secrets)[:64],
            'message': sanitize_text(message, secrets)[:500],
            'http_status': http_status or 0,
            'duration_ms': duration_ms or 0,
            'details': sanitize_text(details, secrets)[:1000] if details else False,
            'provider': company.abc_va_provider,
            'environment': company.abc_va_environment,
            'timestamp': fields.Datetime.now(),
            'user_id': (user or job.user_id or self.env.user).id,
        }
        return self.env['abc.va.log'].sudo().create([vals])

    # ==================================================================
    # Cron
    # ==================================================================
    @api.model
    def _cron_process_queue(self):
        """Elabora la coda per ogni società attiva, nel rispetto del throttle.

        Il commit dopo ogni job rende persistente il log della chiamata
        appena effettuata anche se un job successivo fallisce: il conteggio
        del throttle non deve mai perdere una chiamata realmente eseguita.
        """
        companies = self.env['res.company'].sudo().search([('abc_va_enabled', '=', True)])
        for company in companies:
            if not company._abc_va_is_operational():
                _logger.info(
                    "Verifica anagrafica: società %s attiva ma non operativa "
                    "(credenziali mancanti o secret scaduto), coda in attesa.",
                    company.id,
                )
                continue
            self._abc_va_process_company(company)
        return True

    @api.model
    def _abc_va_process_company(self, company):
        self._abc_va_lock(company)
        now = fields.Datetime.now()
        Queue = self.sudo().with_company(company)
        jobs = Queue.search([
            ('company_id', '=', company.id),
            ('state', '=', 'pending'),
            '|', ('next_try', '=', False), ('next_try', '<=', now),
        ], order='create_date asc, id asc', limit=BATCH_SIZE)
        throttled_logged = False
        for job in jobs:
            # I passi che non chiamano il provider (annullamento, controllo
            # formale, cache) non consumano quota e possono sempre procedere.
            if job._abc_va_process_local():
                job._abc_va_push_update()
                self._abc_va_commit()
                continue
            allowed, limit_type = self._abc_va_throttle_check(company)
            if not allowed:
                if not throttled_logged:
                    self._abc_va_log(
                        'throttle', ESITO_ERRORE, CODE_THROTTLED,
                        message=_("Limite di chiamate %s raggiunto: elaborazione rinviata.",
                                  _('giornaliero') if limit_type == 'day' else _('al minuto')),
                        partner=job.partner_id, value=job.value, company=company,
                        user=job.user_id,
                    )
                    _logger.warning(
                        "Verifica anagrafica: throttle %s raggiunto per la società %s, "
                        "%s richieste restano in coda.", limit_type, company.id, len(jobs),
                    )
                    throttled_logged = True
                break
            job._abc_va_process_remote()
            job._abc_va_push_update()
            self._abc_va_commit()
        return True

    def _abc_va_push_update(self):
        """Notifica sul bus l'utente che ha innescato la verifica: il client
        ricarica la scheda del contatto se è quella aperta."""
        for job in self.sudo():
            partner_channel = job.user_id.partner_id
            if not partner_channel or not job.partner_id:
                continue
            self.env['bus.bus']._sendone(partner_channel, BUS_NOTIFICATION_TYPE, {
                'partner_id': job.partner_id.id,
                'kind': job.kind,
                'state': job.partner_id._abc_va_state(job.kind),
            })

    def _abc_va_commit(self):
        """Commit intermedio del cron (vedi ``_cron_process_queue``).

        Nei test il cursore non può essere committato: Odoo sostituisce
        ``commit`` con un'asserzione. Si usa lo stesso flag di thread che
        Odoo core adotta per i propri cron (es. coda email).
        """
        if getattr(threading.current_thread(), 'testing', False):
            return
        self.env.cr.commit()

    # ==================================================================
    # Elaborazione sincrona (pulsante "Verifica ora")
    # ==================================================================
    def _abc_va_process_now(self):
        """Elabora subito questo job nella transazione corrente.

        Ritorna una stringa: ``'done'`` (esito applicato al partner),
        ``'throttled'`` (limite raggiunto: resta in coda), ``'retry'`` (errore
        transitorio: resta in coda con backoff) o ``'error'``.
        """
        self.ensure_one()
        job = self.sudo()
        company = job.company_id
        self._abc_va_lock(company)
        if job._abc_va_process_local():
            job._abc_va_push_update()
            return 'done'
        allowed, limit_type = self._abc_va_throttle_check(company)
        if not allowed:
            job._abc_va_log(
                'throttle', ESITO_ERRORE, CODE_THROTTLED,
                message=_("Limite di chiamate %s raggiunto: verifica rinviata al processo automatico.",
                          _('giornaliero') if limit_type == 'day' else _('al minuto')),
            )
            job._abc_va_wake_cron(at=fields.Datetime.now() + timedelta(
                seconds=DAY_WINDOW_SECONDS if limit_type == 'day' else MINUTE_WINDOW_SECONDS))
            return 'throttled'
        job._abc_va_process_remote()
        job._abc_va_push_update()
        if job.state == 'done':
            return 'done'
        if job.state == 'pending':
            return 'retry'
        return 'error'

    # ==================================================================
    # Elaborazione di un singolo job
    # ==================================================================
    def _abc_va_process_local(self):
        """Passi che non richiedono il provider. Ritorna True se il job è
        stato chiuso (annullato, esito locale, esito da cache), False se
        serve la chiamata remota."""
        self.ensure_one()
        partner = self.partner_id.sudo()
        company = self.company_id.sudo()
        kind = self.kind

        # 1. Contatto cambiato nel frattempo: richiesta superata
        if not partner.exists() or partner._abc_va_get_value(kind) != self.value:
            self.write({'state': 'cancelled',
                        'last_error': _("Richiesta superata: il valore da verificare è cambiato.")})
            return True

        # 2. Ambito
        if not partner._abc_va_is_applicable(kind):
            partner._abc_va_apply_result('not_applicable',
                                         _("Soggetto non rientrante nell'ambito di verifica."),
                                         self.value, kind=kind)
            self.write({'state': 'cancelled', 'last_error': _("Soggetto non applicabile.")})
            return True

        # 3. Controllo formale locale: nessuna chiamata se errato
        if kind == 'piva':
            ok, reason, reason_message = cf_tools.validate_piva(self.value)
            label = _("Partita IVA formalmente errata: %s.", reason_message)
        else:
            ok, reason, reason_message = cf_tools.validate(self.value)
            label = _("Codice fiscale formalmente errato: %s.", reason_message)
        if not ok:
            log = self._abc_va_log('local', ESITO_NON_VALIDO, CODE_FORMAL_INVALID, message=label)
            partner._abc_va_apply_result('invalid', label, self.value, kind=kind)
            self.write({'state': 'done', 'log_id': log.id})
            return True

        # 3b. Coerenza con il nome (solo codice fiscale): nessuna chiamata se incoerente
        if kind == 'cf' and company.abc_va_name_check != 'off':
            ok, expected = partner._abc_va_name_check_result()
            if not ok:
                message = partner._abc_va_name_mismatch_message(expected)
                log = self._abc_va_log('local', ESITO_NON_VALIDO, CODE_NAME_MISMATCH, message=message)
                partner._abc_va_apply_result('invalid', message, self.value, kind=kind)
                self.write({'state': 'done', 'log_id': log.id})
                return True

        # 4. Cache anti-abuso
        if not self.force:
            cached = self._abc_va_find_cached(company, self.value, kind=kind)
            if cached:
                log = self._abc_va_apply_cached(partner, cached, self.value, kind, company, self.user_id)
                self.write({'state': 'done', 'log_id': log.id})
                return True
        return False

    def _abc_va_process_remote(self):
        """Chiama il provider e applica l'esito, con retry e backoff."""
        self.ensure_one()
        company = self.company_id.sudo()
        partner = self.partner_id.sudo()
        secrets = [company.abc_va_client_secret, company.abc_va_client_id]

        try:
            provider = registry.get_provider(company)
        except registry.ProviderNotAvailable as exc:
            message = sanitize_exception(exc, secrets)
            self._abc_va_fail(partner, CODE_PROVIDER_MISSING, message, retryable=False)
            return

        if self.kind == 'piva' and not getattr(provider, 'supports_piva', False):
            self._abc_va_fail(partner, CODE_PROVIDER_MISSING,
                              _("Il provider configurato non supporta la verifica della partita IVA."),
                              retryable=False)
            return

        self.attempts += 1
        started = time.monotonic()
        try:
            with self.env.cr.savepoint():
                if self.kind == 'piva':
                    result = provider.verify_piva(self.value)
                else:
                    result = provider.verify_cf(self.value)
        except Exception as exc:  # noqa: BLE001 - il driver non deve mai far cadere il cron
            message = sanitize_exception(exc, secrets)
            _logger.error("Verifica anagrafica: eccezione dal provider per il job %s: %s",
                          self.id, message)
            self._abc_va_fail(partner, CODE_UNEXPECTED, message, retryable=True,
                              duration_ms=int((time.monotonic() - started) * 1000))
            return
        duration_ms = int((time.monotonic() - started) * 1000)

        esito = result.get('esito')
        code = result.get('codice_esito') or ''
        message = sanitize_text(result.get('messaggio') or '', secrets)
        status = result.get('raw_status_code') or 0
        dati = result.get('dati') or {}

        if esito in (ESITO_VALIDO, ESITO_NON_VALIDO):
            log = self._abc_va_log('api', esito, code, message=message, http_status=status,
                                   duration_ms=duration_ms, details=self._abc_va_details_dump(dati))
            if self.kind == 'piva':
                partner._abc_va_apply_piva_outcome(esito, message, self.value, dati)
            elif esito == ESITO_VALIDO:
                partner._abc_va_apply_result('valid', message or _("Codice fiscale valido."), self.value)
            else:
                partner._abc_va_apply_result(
                    'invalid',
                    _("Codice fiscale non riscontrato in Anagrafe Tributaria: %s", message or code),
                    self.value,
                )
            self.write({'state': 'done', 'log_id': log.id, 'last_error': False})
        else:
            self._abc_va_fail(
                partner, code, message,
                retryable=bool(result.get('retryable')),
                http_status=status,
                retry_after=result.get('retry_after'),
                rate_limit_type=result.get('rate_limit_type'),
                duration_ms=duration_ms,
            )

    def _abc_va_fail(self, partner, code, message, retryable, http_status=0,
                     retry_after=None, rate_limit_type=None, duration_ms=0):
        """Gestisce un esito di errore: log, retry con backoff oppure stato
        finale ``error`` sul job e sul partner."""
        self.ensure_one()
        # Conta ai fini del throttle solo se una chiamata è stata
        # effettuata o tentata; provider assente o configurazione
        # incompleta non generano traffico.
        event = 'local' if code in (CODE_PROVIDER_MISSING, CODE_CONFIG) else 'api'
        log = self._abc_va_log(event, ESITO_ERRORE, code, message=message, http_status=http_status,
                               duration_ms=duration_ms)
        self.log_id = log.id

        if retryable and self.attempts < self.max_attempts:
            if retry_after:
                delay = int(retry_after)
            elif rate_limit_type == 'day':
                delay = DAY_WINDOW_SECONDS
            else:
                delay = BASE_BACKOFF_SECONDS * (2 ** (self.attempts - 1))
            next_try = fields.Datetime.now() + timedelta(seconds=delay)
            self.write({
                'next_try': next_try,
                'last_error': message or code,
            })
            self._abc_va_wake_cron(at=next_try)
            # Il partner resta 'pending': la verifica non è conclusa.
            return

        final_message = message or code
        if retryable:
            final_message = _("Verifica non riuscita dopo %s tentativi: %s",
                              self.attempts, final_message)
            code = CODE_MAX_ATTEMPTS
        self.write({'state': 'error', 'last_error': final_message})
        partner._abc_va_apply_result('error', final_message, self.value, kind=self.kind)

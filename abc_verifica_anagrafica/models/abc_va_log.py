# -*- coding: utf-8 -*-
import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..services.base_provider import ESITO_VALIDO, ESITO_NON_VALIDO, ESITO_ERRORE

KIND_SELECTION = [
    ('cf', 'Codice fiscale'),
    ('piva', 'Partita IVA'),
]

EVENT_SELECTION = [
    ('api', 'Chiamata al provider'),
    ('local', 'Controllo formale locale'),
    ('cache', 'Esito da cache'),
    ('throttle', 'Bloccata dal throttle'),
]

_logger = logging.getLogger(__name__)

# Le richieste concluse (elaborate, in errore, annullate) restano in coda
# per consultazione per questo numero di giorni, poi vengono eliminate.
QUEUE_RETENTION_DAYS = 30

RESULT_SELECTION = [
    (ESITO_VALIDO, 'Valido'),
    (ESITO_NON_VALIDO, 'Non valido'),
    (ESITO_ERRORE, 'Errore'),
]


class AbcVaLog(models.Model):
    """Registro delle verifiche effettuate.

    Sola lettura da interfaccia: i record vengono creati esclusivamente dal
    codice del modulo (con sudo) e cancellati solo dal cron di purge in base
    alla retention configurata. Non contiene mai payload grezzi: solo esito
    normalizzato, codice esito e messaggio leggibile sanitizzato.
    """
    _name = 'abc.va.log'
    _description = 'Verifica anagrafica: log'
    _order = 'timestamp desc, id desc'
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
        ondelete='set null',
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
        string='Valore verificato',
        required=True,
    )
    event = fields.Selection(
        selection=EVENT_SELECTION,
        string='Evento',
        required=True,
        default='api',
        index=True,
        help="'Chiamata al provider' conta ai fini del throttle. Gli altri "
             "eventi non generano traffico verso il provider.",
    )
    result = fields.Selection(
        selection=RESULT_SELECTION,
        string='Esito',
        required=True,
    )
    result_code = fields.Char(
        string='Codice esito',
    )
    message = fields.Char(
        string='Messaggio',
    )
    details = fields.Char(
        string='Dettagli',
        help="Dati strutturati dell'esito in formato JSON (per la partita "
             "IVA: denominazione, date di inizio, cessazione e sospensione). "
             "Riutilizzati dalla cache anti-abuso; eliminati con il purge.",
    )
    duration_ms = fields.Integer(
        string='Durata (ms)',
        help="Durata della chiamata al provider in millisecondi; 0 per gli "
             "eventi senza chiamata.",
    )
    http_status = fields.Integer(
        string='HTTP status',
        help="Status code della risposta del provider; 0 se la chiamata non "
             "è avvenuta.",
    )
    provider = fields.Char(
        string='Provider',
        required=True,
    )
    environment = fields.Char(
        string='Ambiente',
        required=True,
    )
    timestamp = fields.Datetime(
        string='Data e ora',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Innescata da',
        default=lambda self: self.env.user,
    )

    # ------------------------------------------------------------------
    # Immutabilità
    # ------------------------------------------------------------------
    def write(self, vals):
        raise UserError(_(
            "I log di verifica non sono modificabili."
        ))

    def unlink(self):
        if not self.env.context.get('abc_va_purge'):
            raise UserError(_(
                "I log di verifica possono essere eliminati solo dal "
                "processo automatico di purge in base alla retention "
                "configurata."
            ))
        return super().unlink()

    @api.depends('value', 'result', 'timestamp')
    def _compute_display_name(self):
        for log in self:
            log.display_name = f'{log.value} [{log.result}] {log.timestamp or ""}'

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------
    @api.model
    def _cron_purge(self):
        """Cron mensile: elimina definitivamente (unlink) i log più vecchi
        della retention configurata su ciascuna società e le richieste
        concluse più vecchie di QUEUE_RETENTION_DAYS."""
        now = fields.Datetime.now()
        Queue = self.env['abc.va.queue'].sudo()
        for company in self.env['res.company'].sudo().search([]):
            months = company.abc_va_retention_months or 1
            cutoff = now - relativedelta(months=months)
            logs = self.sudo().search([
                ('company_id', '=', company.id),
                ('timestamp', '<', cutoff),
            ])
            if logs:
                count = len(logs)
                logs.with_context(abc_va_purge=True).unlink()
                _logger.info("Verifica anagrafica: purge di %s log per la società %s "
                             "(retention %s mesi).", count, company.id, months)
            jobs = Queue.search([
                ('company_id', '=', company.id),
                ('state', 'in', ('done', 'error', 'cancelled')),
                ('write_date', '<', now - relativedelta(days=QUEUE_RETENTION_DAYS)),
            ])
            if jobs:
                jobs.unlink()
        return True

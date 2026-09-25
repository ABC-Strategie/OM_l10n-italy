# -*- coding: utf-8 -*-
from odoo import fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    abc_va_enabled = fields.Boolean(
        related='company_id.abc_va_enabled', readonly=False)
    abc_va_provider = fields.Selection(
        related='company_id.abc_va_provider', readonly=False)
    abc_va_environment = fields.Selection(
        related='company_id.abc_va_environment', readonly=False)
    abc_va_test_base_url = fields.Char(
        related='company_id.abc_va_test_base_url', readonly=False)

    # Le credenziali restano visibili e scrivibili solo al gruppo
    # amministratore del modulo, anche sul transient delle impostazioni.
    abc_va_client_id = fields.Char(
        related='company_id.abc_va_client_id', readonly=False,
        groups='abc_verifica_anagrafica.group_abc_va_manager')
    abc_va_client_secret = fields.Char(
        related='company_id.abc_va_client_secret', readonly=False,
        groups='abc_verifica_anagrafica.group_abc_va_manager')

    abc_va_secret_expiry = fields.Date(
        related='company_id.abc_va_secret_expiry', readonly=False)
    abc_va_secret_days_left = fields.Integer(
        related='company_id.abc_va_secret_days_left')
    abc_va_alert_user_id = fields.Many2one(
        related='company_id.abc_va_alert_user_id', readonly=False)

    abc_va_rate_minute = fields.Integer(
        related='company_id.abc_va_rate_minute', readonly=False)
    abc_va_rate_day = fields.Integer(
        related='company_id.abc_va_rate_day', readonly=False)
    abc_va_recheck_hours = fields.Integer(
        related='company_id.abc_va_recheck_hours', readonly=False)
    abc_va_retention_months = fields.Integer(
        related='company_id.abc_va_retention_months', readonly=False)
    abc_va_on_invalid = fields.Selection(
        related='company_id.abc_va_on_invalid', readonly=False)
    abc_va_name_check = fields.Selection(
        related='company_id.abc_va_name_check', readonly=False)
    abc_va_piva_enabled = fields.Boolean(
        related='company_id.abc_va_piva_enabled', readonly=False)
    abc_va_on_ceased = fields.Selection(
        related='company_id.abc_va_on_ceased', readonly=False)
    abc_va_piva_name_check = fields.Selection(
        related='company_id.abc_va_piva_name_check', readonly=False)
    abc_va_trigger_on_invoice = fields.Boolean(
        related='company_id.abc_va_trigger_on_invoice', readonly=False)
    abc_va_trigger_on_sale = fields.Boolean(
        related='company_id.abc_va_trigger_on_sale', readonly=False)

    def action_abc_va_test_connection(self):
        """Pulsante "Test connessione": health check sul provider con le
        impostazioni salvate della società. Non salva nulla sui contatti."""
        self.ensure_one()
        ok, message = self.company_id._abc_va_health_check()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Test connessione riuscito") if ok else _("Test connessione fallito"),
                'message': message,
                'type': 'success' if ok else 'danger',
                'sticky': not ok,
            },
        }

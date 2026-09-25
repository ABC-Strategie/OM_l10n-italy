# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    abc_va_partner_state = fields.Selection(
        related='partner_id.abc_va_state',
        string='Verifica CF cliente/fornitore',
    )
    abc_va_partner_piva_state = fields.Selection(
        related='partner_id.abc_va_piva_state',
        string='Verifica P.IVA cliente/fornitore',
    )
    abc_va_partner_piva_name_match = fields.Selection(
        related='partner_id.abc_va_piva_name_match',
    )
    abc_va_partner_piva_denominazione = fields.Char(
        related='partner_id.abc_va_piva_denominazione',
    )
    abc_va_on_invalid = fields.Selection(
        related='company_id.abc_va_on_invalid',
    )
    abc_va_on_ceased = fields.Selection(
        related='company_id.abc_va_on_ceased',
    )
    abc_va_piva_name_check = fields.Selection(
        related='company_id.abc_va_piva_name_check',
    )

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._abc_va_on_save()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if 'partner_id' in vals:
            self._abc_va_on_save()
        return res

    def _abc_va_on_save(self):
        """Al salvataggio di una fattura in bozza con un contatto mai
        verificato, la verifica viene accodata subito (nessuna chiamata
        sincrona): il banner compare sul documento prima della conferma."""
        if self.env.context.get('abc_va_skip_trigger'):
            return
        for move in self:
            if move.state != 'draft' or not move.partner_id or not move.is_invoice(include_receipts=True):
                continue
            if move.company_id.sudo().abc_va_trigger_on_invoice:
                move._abc_va_partners()._abc_va_on_use(company=move.company_id)

    def action_post(self):
        self._abc_va_before_confirm()
        return super().action_post()

    def _abc_va_partners(self):
        """Contatti rilevanti per il documento: il partner e, se diverso,
        il partner commerciale."""
        self.ensure_one()
        return self.partner_id | self.commercial_partner_id

    def _abc_va_before_confirm(self):
        """Innesco su uso effettivo e policy sugli esiti.

        - trigger: un contatto mai verificato viene accodato (nessuna
          chiamata sincrona, il documento non attende);
        - problemi di livello ``block`` impediscono la conferma con un
          messaggio che spiega come procedere;
        - problemi di livello ``warn`` vengono tracciati nel chatter;
        - lo stato ``error`` (problema tecnico del provider) non blocca mai.
        """
        for move in self:
            if not move.is_invoice(include_receipts=True):
                continue
            company = move.company_id.sudo()
            partners = move._abc_va_partners()
            if company.abc_va_trigger_on_invoice:
                partners._abc_va_on_use(company=move.company_id)
            issues = partners._abc_va_confirm_issues(move.company_id)
            blocking = [message for level, message in issues if level == 'block']
            if blocking:
                raise UserError(_(
                    "Impossibile confermare il documento: %(problems)s.\n\n"
                    "Come procedere: correggere il dato sulla scheda del contatto "
                    "(la verifica riparte automaticamente), allineare la "
                    "denominazione con l'apposito pulsante, oppure richiedere una "
                    "nuova verifica con 'Verifica ora'. Un amministratore può "
                    "modificare le policy in Impostazioni > Contabilità > "
                    "Verifica anagrafica tributaria.",
                    problems='; '.join(blocking),
                ))
            warnings = [message for level, message in issues if level == 'warn']
            if warnings:
                move.message_post(body=_(
                    "Attenzione, secondo l'ultima verifica anagrafica: %s. "
                    "Il documento è stato confermato comunque (policy 'solo avviso').",
                    '; '.join(warnings),
                ))

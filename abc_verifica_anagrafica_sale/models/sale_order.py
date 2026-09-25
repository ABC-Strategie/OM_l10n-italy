# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    abc_va_partner_state = fields.Selection(
        related='partner_id.abc_va_state',
        string='Verifica CF cliente',
    )
    abc_va_partner_piva_state = fields.Selection(
        related='partner_id.abc_va_piva_state',
        string='Verifica P.IVA cliente',
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
        orders = super().create(vals_list)
        orders._abc_va_on_save()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if 'partner_id' in vals:
            self._abc_va_on_save()
        return res

    def _abc_va_on_save(self):
        """Al salvataggio di un preventivo con un cliente mai verificato, la
        verifica viene accodata subito (nessuna chiamata sincrona): il banner
        compare sul preventivo prima della conferma dell'ordine."""
        if self.env.context.get('abc_va_skip_trigger'):
            return
        for order in self:
            if order.state not in ('draft', 'sent') or not order.partner_id:
                continue
            if order.company_id.sudo().abc_va_trigger_on_sale:
                partners = order.partner_id | order.partner_id.commercial_partner_id
                partners._abc_va_on_use(company=order.company_id)

    def action_confirm(self):
        self._abc_va_before_confirm()
        return super().action_confirm()

    def _abc_va_before_confirm(self):
        """Stessa logica di account.move: innesco su uso effettivo e policy
        sugli esiti. Lo stato 'error' non blocca mai."""
        for order in self:
            company = order.company_id.sudo()
            partners = order.partner_id | order.partner_id.commercial_partner_id
            if company.abc_va_trigger_on_sale:
                partners._abc_va_on_use(company=order.company_id)
            issues = partners._abc_va_confirm_issues(order.company_id)
            blocking = [message for level, message in issues if level == 'block']
            if blocking:
                raise UserError(_(
                    "Impossibile confermare l'ordine: %(problems)s.\n\n"
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
                order.message_post(body=_(
                    "Attenzione, secondo l'ultima verifica anagrafica: %s. "
                    "L'ordine è stato confermato comunque (policy 'solo avviso').",
                    '; '.join(warnings),
                ))

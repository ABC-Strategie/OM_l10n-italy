from odoo import models, api, _

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_l10n_it_edi_send(self):
        # We only want to pop up the wizard if it's a single record, 
        # it's a self-invoice (integrazione), and we are not bypassing the wizard.
        if len(self) == 1 and self.l10n_it_edi_is_self_invoice and not self.env.context.get('bypass_tax_integration_wizard'):
            return {
                'name': _('Anteprima XML Integrazione Fiscale'),
                'type': 'ir.actions.act_window',
                'res_model': 'abc.tax.integration.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_move_id': self.id,
                },
            }
        
        # In all other cases (multiple records, not self-invoice, or wizard bypassed),
        # proceed with the standard send action.
        return super().action_l10n_it_edi_send()

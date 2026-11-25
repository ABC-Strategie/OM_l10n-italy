from odoo import api, models
from odoo.exceptions import UserError


class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    @api.model_create_multi
    def create(self, vals_list):
        partials = super().create(vals_list)
        if not self.env.context.get("abc_wh_skip"):
            withholding = self.env["abc.withholding"]
            lines = self.env["abc.withholding.line"]
            for partial in partials:
                # Pagamento o incasso di una fattura con ritenuta
                withholding._abc_process_partial(partial)
                # F24 riconciliato in banca con il debito verso l'Erario
                lines._abc_process_bank_partial(partial)
        return partials

    def unlink(self):
        if self and not self.env.context.get("abc_wh_skip"):
            lines = self.env["abc.withholding.line"]
            lines._abc_remove_for_partials(self)
            lines._abc_unprocess_bank_partials(self)
        return super().unlink()

    def _abc_check_settlement_partials(self):
        """La scrittura della ritenuta non si sgancia a mano dalla fattura.

        Si annulla il pagamento: il modulo storna la scrittura e riapre la ritenuta.
        """
        Line = self.env["abc.withholding.line"].sudo()
        for partial in self:
            sides = partial.debit_move_id | partial.credit_move_id
            if not any(line._abc_is_partner_withholding_line() for line in sides):
                continue
            if Line.search_count([("transfer_move_id", "in", sides.move_id.ids)]):
                raise UserError(self.env._(
                    "Questa riconciliazione chiude la ritenuta della fattura con la scrittura del modulo. "
                    "Per annullarla togliere la riconciliazione del pagamento: il modulo storna la "
                    "scrittura della ritenuta e la riapre."))

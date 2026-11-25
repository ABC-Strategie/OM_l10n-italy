from odoo import api, models
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    @api.model
    def default_get(self, fields):
        """Registra pagamento propone il netto: la ritenuta la chiude il modulo al pagamento."""
        res = super().default_get(fields)
        line_commands = res.get("line_ids")
        if line_commands and line_commands[0][0] == 6:
            lines = self.env["account.move.line"].browse(line_commands[0][2])
            keep = lines.filtered(lambda line: not line._abc_is_partner_withholding_line())
            if not keep:
                raise UserError(self.env._(
                    "Resta aperta solo la ritenuta: non va pagata al fornitore/cliente ma all'Erario. "
                    "Controllare che la scrittura della ritenuta sia stata creata (registro varie "
                    "delle ritenute configurato nell'azienda)."))
            if keep != lines:
                res["line_ids"] = [(6, 0, keep.ids)]
        return res

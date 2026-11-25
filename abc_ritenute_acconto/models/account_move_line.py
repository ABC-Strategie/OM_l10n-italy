from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _abc_is_partner_withholding_line(self):
        """Riga ritenuta registrata sul conto del fornitore/cliente (schema OCA, D2)."""
        self.ensure_one()
        tax = self.tax_line_id
        return bool(
            self.display_type == "tax"
            and tax
            and tax.abc_wh_on_partner
            and tax._abc_wh_is_withholding()
            and self.account_id.account_type in ("asset_receivable", "liability_payable")
        )

    @api.constrains("account_id", "display_type")
    def _check_payable_receivable(self):
        # Odoo vuole che sul conto fornitore/cliente ci siano solo righe di scadenza:
        # le righe ritenuta del modulo sono l'unica eccezione ammessa.
        others = self.filtered(lambda line: not line._abc_is_partner_withholding_line())
        return super(AccountMoveLine, others)._check_payable_receivable()

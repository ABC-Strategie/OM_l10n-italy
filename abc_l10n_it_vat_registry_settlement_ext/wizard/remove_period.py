# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models
from odoo.exceptions import UserError


class RemovePeriod(models.TransientModel):
    _inherit = "remove.period.from.vat.statement"

    def _default_statement_id(self):
        if self.env.context.get("active_model") == "account.vat.period.end.statement":
            return self.env.context.get("active_id")
        return False

    statement_id = fields.Many2one(
        "account.vat.period.end.statement",
        string="VAT Settlement",
        default=_default_statement_id,
    )
    date_range_id = fields.Many2one(
        "date.range",
        string="Period",
        domain="[('vat_statement_id', '=', statement_id)]",
    )

    # La Selection dinamica originale si appoggia a active_id valutato in
    # fields_get: in Odoo 19 get_views non la valorizza e la tendina resta
    # vuota. La sostituiamo con date_range_id, come gia' fa il wizard di
    # aggiunta periodo, quindi non puo' piu' essere obbligatoria.
    period_id = fields.Selection(required=False)

    def remove_period(self):
        self.ensure_one()
        if not self.date_range_id:
            return super().remove_period()
        statement = self.statement_id
        if not statement:
            raise UserError(self.env._("Current settlement not found"))
        self.date_range_id.vat_statement_id = False
        statement.set_fiscal_year()
        statement.compute_amounts()
        return {
            "type": "ir.actions.act_window_close",
        }

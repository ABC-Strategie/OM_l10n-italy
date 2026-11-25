from odoo import api, fields, models
from odoo.exceptions import UserError

from .withholding_line import LOCKED_STATES


class AccountMove(models.Model):
    _inherit = "account.move"

    abc_withholding_ids = fields.One2many("abc.withholding", "move_id", string="Ritenute")
    abc_withholding_count = fields.Integer(compute="_compute_abc_withholding_count")
    abc_wh_amount = fields.Monetary(
        string="Ritenute e contributi", compute="_compute_abc_wh_totals", currency_field="currency_id")
    abc_wh_gross_total = fields.Monetary(
        string="Totale documento (lordo)", compute="_compute_abc_wh_totals", currency_field="currency_id")
    abc_wh_net_to_pay = fields.Monetary(
        string="Netto a pagare", compute="_compute_abc_wh_totals", currency_field="currency_id")

    @api.depends("abc_withholding_ids")
    def _compute_abc_withholding_count(self):
        for move in self:
            move.abc_withholding_count = len(move.abc_withholding_ids)

    @api.depends("line_ids.amount_currency", "line_ids.tax_line_id", "amount_total")
    def _compute_abc_wh_totals(self):
        for move in self:
            wh_lines = move.line_ids.filtered(
                lambda l: l.display_type == "tax" and l.tax_line_id and l.tax_line_id._abc_wh_is_withholding())
            amount = abs(sum(wh_lines.mapped("amount_currency")))
            move.abc_wh_amount = amount
            move.abc_wh_net_to_pay = move.amount_total
            move.abc_wh_gross_total = move.amount_total + amount

    def _post(self, soft=True):
        posted = super()._post(soft)
        withholding = self.env["abc.withholding"]
        created = withholding._abc_create_from_moves(posted)
        # Riconciliazioni gia' esistenti: nota di credito riconciliata dentro super()._post()
        # e fatture rimesse in bozza (in Odoo 19 button_draft non toglie le riconciliazioni).
        terms = created.move_id.line_ids.filtered(lambda l: l.display_type == "payment_term")
        for partial in (terms.matched_debit_ids | terms.matched_credit_ids).sorted("id"):
            withholding._abc_process_partial(partial)
        # La riga ritenuta sul conto fornitore/cliente scade con la fattura (scadenzari, solleciti)
        for move in posted:
            wh_lines = move.line_ids.filtered(lambda l: l._abc_is_partner_withholding_line())
            if wh_lines and move.invoice_date_due:
                wh_lines.write({"date_maturity": move.invoice_date_due})
        return posted

    def js_remove_outstanding_partial(self, partial_id):
        """Dal widget pagamenti non si sgancia a mano la scrittura della ritenuta."""
        self.env["account.partial.reconcile"].browse(partial_id)._abc_check_settlement_partials()
        return super().js_remove_outstanding_partial(partial_id)

    def js_assign_outstanding_line(self, line_id):
        """Pulsante "Aggiungi" del widget pagamenti: si abbina il netto, non la riga ritenuta."""
        self.ensure_one()
        lines = self.env["account.move.line"].browse(line_id)
        lines += self.line_ids.filtered(
            lambda line: line.account_id == lines[0].account_id
            and not line.reconciled
            and not line._abc_is_partner_withholding_line())
        return lines.reconcile()

    def _abc_wh_check_unlock(self):
        lines = self.sudo().abc_withholding_ids.line_ids
        locked = lines.filtered(lambda l: l.state in LOCKED_STATES or l.payment_id.state == "confirmed")
        if locked:
            raise UserError(self.env._(
                "Il documento %s ha ritenute gia' versate, certificate o scomputate: "
                "non si puo' rimettere in bozza o annullare.", locked[0].move_id.name))

    # Le scritture della ritenuta si stornano prima: cosi' la riga ritenuta della fattura e'
    # gia' libera quando Odoo rimette in bozza o annulla.
    def button_draft(self):
        self._abc_wh_check_unlock()
        self.sudo().abc_withholding_ids._abc_remove()
        return super().button_draft()

    def button_cancel(self):
        self._abc_wh_check_unlock()
        self.sudo().abc_withholding_ids._abc_remove()
        return super().button_cancel()

    def action_view_abc_withholding(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Ritenute"),
            "res_model": "abc.withholding",
            "view_mode": "list,form",
            "domain": [("move_id", "=", self.id)],
            "context": {"create": False},
        }

from odoo import api, fields, models
from odoo.exceptions import UserError


class AbcWithholdingDeductWizard(models.TransientModel):
    _name = "abc.withholding.deduct.wizard"
    _description = "Scomputo delle ritenute subite in dichiarazione"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    fiscal_year = fields.Integer(string="Anno d'imposta", required=True,
                                 default=lambda self: fields.Date.context_today(self).year - 1)
    include_uncertified = fields.Boolean(string="Includi le ritenute subite senza CU confermata")
    amount = fields.Monetary(string="Importo da scomputare", compute="_compute_lines")
    line_count = fields.Integer(string="Quote", compute="_compute_lines")

    def _abc_lines(self):
        states = ("certified", "suffered") if self.include_uncertified else ("certified",)
        return self.env["abc.withholding.line"].search([
            ("company_id", "=", self.company_id.id),
            ("cycle", "=", "active"),
            ("kind", "=", "payment"),
            ("fiscal_year", "=", self.fiscal_year),
            ("state", "in", states),
        ])

    @api.depends("company_id", "fiscal_year", "include_uncertified")
    def _compute_lines(self):
        for wiz in self:
            lines = wiz._abc_lines()
            wiz.amount = sum(lines.mapped("amount"))
            wiz.line_count = len(lines)

    def action_deduct(self):
        """Segna le quote come scomputate; la scrittura si fa in sede di dichiarazione (D46)."""
        self.ensure_one()
        lines = self._abc_lines()
        if not lines:
            raise UserError(self.env._("Nessuna ritenuta da scomputare per l'anno %s.", self.fiscal_year))
        lines.write({"state": "deducted", "deduction_year": self.fiscal_year})
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Ritenute scomputate %s", self.fiscal_year),
            "res_model": "abc.withholding.line",
            "view_mode": "list,form",
            "domain": [("id", "in", lines.ids)],
        }

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from ..models.date_utils import period_of


class AbcWithholdingPaymentWizard(models.TransientModel):
    _name = "abc.withholding.payment.wizard"
    _description = "Prepara versamento F24 ritenute"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    period_date = fields.Date(
        string="Mese dei pagamenti", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1) - relativedelta(months=1),
        help="Un giorno qualsiasi del mese in cui sono stati pagati i fornitori.")
    period = fields.Char(string="Mese di competenza", compute="_compute_period")
    payment_date = fields.Date(string="Data versamento", required=True, default=fields.Date.context_today)
    apply_threshold = fields.Boolean(
        string="Proponi il rinvio sotto soglia", default=True,
        help="Se il mese e' sotto la soglia configurata, le quote non vengono preselezionate. "
             "Si possono sempre aggiungere (D22).")
    include_contributions = fields.Boolean(string="Includi contributi previdenziali (RT03-RT06)")
    line_ids = fields.Many2many("abc.withholding.line", string="Quote da versare")
    previous_line_ids = fields.Many2many(
        "abc.withholding.line", "abc_wh_payment_wizard_previous_rel", string="Quote di mesi precedenti non versate",
        compute="_compute_candidates")
    period_total = fields.Monetary(string="Totale del mese", compute="_compute_candidates")
    selected_total = fields.Monetary(string="Totale selezionato", compute="_compute_selected_total")
    threshold_message = fields.Char(compute="_compute_candidates")

    @api.depends("period_date")
    def _compute_period(self):
        for wiz in self:
            wiz.period = period_of(wiz.period_date) if wiz.period_date else False

    def _abc_base_domain(self):
        domain = [
            ("company_id", "=", self.company_id.id),
            ("cycle", "=", "passive"),
            ("kind", "=", "payment"),
            ("state", "=", "due"),
            "|", ("payment_id", "=", False), ("payment_id.state", "=", "cancelled"),
        ]
        if not self.include_contributions:
            domain.append(("is_contribution", "=", False))
        return domain

    @api.depends("period", "company_id", "include_contributions", "apply_threshold")
    def _compute_candidates(self):
        Line = self.env["abc.withholding.line"]
        for wiz in self:
            if not wiz.period:
                wiz.previous_line_ids = False
                wiz.period_total = 0.0
                wiz.threshold_message = False
                continue
            base = wiz._abc_base_domain()
            month_lines = Line.search(base + [("period", "=", wiz.period)])
            wiz.previous_line_ids = Line.search(base + [("period", "<", wiz.period)])
            wiz.period_total = sum(month_lines.mapped("amount"))
            wiz.threshold_message = wiz._abc_threshold_message(month_lines)

    def _abc_threshold_message(self, month_lines):
        threshold = self.company_id.abc_wh_threshold
        month = self.period_date.month
        if not (self.apply_threshold and threshold and month_lines) or month >= 11:
            return False
        if sum(month_lines.mapped("amount")) < threshold:
            return self.env._(
                "Il totale del mese e' sotto la soglia di %.2f: si propone il rinvio. "
                "Per versare comunque, aggiungere le quote all'elenco.", threshold)
        return False

    @api.depends("line_ids.amount")
    def _compute_selected_total(self):
        for wiz in self:
            wiz.selected_total = sum(wiz.line_ids.mapped("amount"))

    @api.onchange("period_date", "company_id", "include_contributions", "apply_threshold")
    def _onchange_period(self):
        if not self.period_date:
            return
        period = period_of(self.period_date)
        month_lines = self.env["abc.withholding.line"].search(self._abc_base_domain() + [("period", "=", period)])
        if self._abc_threshold_message(month_lines):
            self.line_ids = [Command.clear()]
        else:
            self.line_ids = [Command.set(month_lines.ids)]

    def action_add_previous(self):
        self.ensure_one()
        self.line_ids = [Command.link(l.id) for l in self.previous_line_ids]
        return self._abc_reopen()

    def _abc_reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_create(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(self.env._("Selezionare almeno una quota da versare."))
        payment = self.env["abc.withholding.payment"].create({
            "company_id": self.company_id.id,
            "date": self.payment_date,
            "period": self.period,
        })
        self.line_ids.write({"payment_id": payment.id})
        payment.action_compute_tributes()
        return {
            "type": "ir.actions.act_window",
            "res_model": "abc.withholding.payment",
            "res_id": payment.id,
            "view_mode": "form",
            "target": "current",
        }

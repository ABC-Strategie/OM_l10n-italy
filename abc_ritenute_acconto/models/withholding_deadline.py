from datetime import date, timedelta

from odoo import api, fields, models


class AbcWithholdingDeadline(models.Model):
    _name = "abc.withholding.deadline"
    _description = "Scadenza di versamento ritenute"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_due"
    _check_company_auto = True

    name = fields.Char(string="Scadenza", compute="_compute_name", store=True)
    company_id = fields.Many2one("res.company", string="Azienda", required=True, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_due = fields.Date(string="Data di scadenza", required=True, index=True)
    amount_due = fields.Monetary(string="Da versare", compute="_compute_amounts")
    line_count = fields.Integer(string="Quote", compute="_compute_amounts")
    reminded_days = fields.Char(string="Promemoria inviati (giorni)", default="")

    @api.depends("date_due")
    def _compute_name(self):
        for rec in self:
            rec.name = self.env._("Versamento ritenute del %s", rec.date_due.strftime("%d/%m/%Y")) if rec.date_due else ""

    def _abc_due_lines(self):
        self.ensure_one()
        return self.env["abc.withholding.line"].search([
            ("company_id", "=", self.company_id.id),
            ("cycle", "=", "passive"),
            ("state", "=", "due"),
            ("is_contribution", "=", False),
            ("date_due", "=", self.date_due),
        ])

    def _compute_amounts(self):
        for rec in self:
            lines = rec._abc_due_lines()
            rec.amount_due = sum(lines.mapped("amount"))
            rec.line_count = len(lines)

    def action_open_lines(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "abc.withholding.line",
            "view_mode": "list,form",
            "domain": [("id", "in", self._abc_due_lines().ids)],
        }

    @api.model
    def _cron_reminders(self):
        """Promemoria 5, 3, 1 giorno prima della scadenza e il giorno stesso (D29)."""
        today = fields.Date.context_today(self)
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        Line = self.env["abc.withholding.line"]
        for company in self.env["res.company"].search([]):
            days = []
            for token in (company.abc_wh_reminder_days or "").split(","):
                token = token.strip()
                if token.isdigit():
                    days.append(int(token))
            if not days:
                continue
            horizon = today + timedelta(days=max(days))
            lines = Line.search([
                ("company_id", "=", company.id), ("cycle", "=", "passive"),
                ("state", "=", "due"), ("is_contribution", "=", False),
                ("date_due", ">=", today), ("date_due", "<=", horizon),
            ])
            for due in set(lines.mapped("date_due")):
                deadline = self.search([("company_id", "=", company.id), ("date_due", "=", due)], limit=1) \
                    or self.create({"company_id": company.id, "date_due": due})
                delta = (due - today).days
                sent = [d for d in (deadline.reminded_days or "").split(",") if d]
                if delta not in days or str(delta) in sent:
                    continue
                total = sum(l.amount for l in lines if l.date_due == due)
                summary = self.env._("Ritenute da versare entro il %(date)s: %(amount)s",
                                     date=due.strftime("%d/%m/%Y"), amount="%.2f" % total)
                for user in company.abc_wh_responsible_ids:
                    deadline.activity_schedule(
                        activity_type_id=activity_type.id if activity_type else False,
                        summary=summary,
                        date_deadline=due,
                        user_id=user.id,
                    )
                deadline.reminded_days = ",".join(sent + [str(delta)])

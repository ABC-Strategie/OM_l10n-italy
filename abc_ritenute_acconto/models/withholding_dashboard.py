from odoo import api, fields, models


class AbcWithholdingDashboard(models.TransientModel):
    _name = "abc.withholding.dashboard"
    _description = "Cruscotto ritenute"

    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    cycle = fields.Selection([("passive", "Ritenute passive"), ("active", "Ritenute attive")], string="Ciclo",
                             required=True)
    # Ciclo passivo
    matured_amount = fields.Monetary(string="Maturate (fatture non pagate)", compute="_compute_totals")
    due_amount = fields.Monetary(string="Dovute in scadenza", compute="_compute_totals")
    overdue_amount = fields.Monetary(string="Scadute non versate", compute="_compute_totals")
    next_due_date = fields.Date(string="Prossima scadenza", compute="_compute_totals")
    # Ciclo attivo
    active_matured_amount = fields.Monetary(string="Maturate (fatture non incassate)", compute="_compute_totals")
    suffered_amount = fields.Monetary(string="Subite non certificate", compute="_compute_totals")
    certified_amount = fields.Monetary(string="Certificate da scomputare", compute="_compute_totals")
    cu_missing_count = fields.Integer(string="CU mancanti o con differenze", compute="_compute_totals")

    @api.depends("company_id", "cycle")
    def _compute_totals(self):
        Wh = self.env["abc.withholding"]
        Line = self.env["abc.withholding.line"]
        today = fields.Date.context_today(self)
        for rec in self:
            company = [("company_id", "=", rec.company_id.id)]
            passive = company + [("cycle", "=", "passive")]
            active = company + [("cycle", "=", "active")]
            rec.matured_amount = sum(Wh.search(passive + [("state", "in", ("matured", "due"))]).mapped("residual_amount"))
            due = Line.search(passive + [("state", "=", "due"), ("is_contribution", "=", False)])
            rec.due_amount = sum(due.filtered(lambda l: l.date_due >= today).mapped("amount"))
            rec.overdue_amount = sum(due.filtered(lambda l: l.date_due < today).mapped("amount"))
            upcoming = due.filtered(lambda l: l.date_due >= today).mapped("date_due")
            rec.next_due_date = min(upcoming) if upcoming else False
            rec.active_matured_amount = sum(Wh.search(active + [("state", "in", ("matured", "suffered"))]).mapped("residual_amount"))
            rec.suffered_amount = sum(Line.search(active + [("state", "=", "suffered")]).mapped("amount"))
            rec.certified_amount = sum(Line.search(active + [("state", "=", "certified")]).mapped("amount"))
            rec.cu_missing_count = self.env["abc.withholding.cu.received"].search_count(
                company + [("state", "in", ("missing", "difference"))])

    @api.model
    def action_open(self, cycle):
        record = self.create({"cycle": cycle})
        view = "abc_ritenute_acconto.view_abc_wh_dashboard_%s" % cycle
        return {
            "type": "ir.actions.act_window",
            "name": dict(self._fields["cycle"].selection)[cycle],
            "res_model": self._name,
            "res_id": record.id,
            "view_mode": "form",
            "views": [(self.env.ref(view).id, "form")],
            "target": "current",
        }

    def _abc_open_lines(self, name, domain):
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "abc.withholding.line",
            "view_mode": "list,pivot,form",
            "domain": [("company_id", "=", self.company_id.id)] + domain,
        }

    def action_open_matured(self):
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Ritenute maturate"),
            "res_model": "abc.withholding",
            "view_mode": "list,form",
            "domain": [("company_id", "=", self.company_id.id), ("cycle", "=", self.cycle),
                       ("state", "in", ("matured", "due", "suffered"))],
        }

    def action_open_due(self):
        return self._abc_open_lines(self.env._("Dovute in scadenza"),
                                    [("cycle", "=", "passive"), ("state", "=", "due"), ("is_overdue", "=", False)])

    def action_open_overdue(self):
        return self._abc_open_lines(self.env._("Scadute non versate"),
                                    [("cycle", "=", "passive"), ("is_overdue", "=", True)])

    def action_open_suffered(self):
        return self._abc_open_lines(self.env._("Subite non certificate"),
                                    [("cycle", "=", "active"), ("state", "=", "suffered")])

    def action_open_certified(self):
        return self._abc_open_lines(self.env._("Certificate da scomputare"),
                                    [("cycle", "=", "active"), ("state", "=", "certified")])

    def action_open_cu(self):
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Controllo CU"),
            "res_model": "abc.withholding.cu.received",
            "view_mode": "list,form",
            "domain": [("company_id", "=", self.company_id.id), ("state", "in", ("missing", "difference"))],
        }

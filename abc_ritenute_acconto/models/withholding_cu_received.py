from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError


class AbcWithholdingCuReceived(models.Model):
    _name = "abc.withholding.cu.received"
    _description = "CU ricevuta dal cliente (controllo ritenute subite)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "year desc, partner_id"
    _check_company_auto = True

    name = fields.Char(string="Riferimento", compute="_compute_name", store=True)
    company_id = fields.Many2one("res.company", string="Azienda", required=True,
                                 default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    partner_id = fields.Many2one("res.partner", string="Cliente", required=True, index=True, tracking=True)
    year = fields.Integer(string="Anno dei pagamenti", required=True, index=True, tracking=True)
    line_ids = fields.One2many("abc.withholding.line", "cu_received_id", string="Ritenute registrate")
    registered_amount = fields.Monetary(string="Ritenute registrate", compute="_compute_amounts", store=True)
    certified_compensi = fields.Monetary(string="Compensi certificati", tracking=True)
    certified_amount = fields.Monetary(string="Ritenute certificate", tracking=True)
    difference = fields.Monetary(string="Differenza", compute="_compute_amounts", store=True)
    received_date = fields.Date(string="Data di ricezione", tracking=True)
    source = fields.Selection(
        [("post", "Posta"), ("ade", "Sito Agenzia delle Entrate"), ("email", "Email / PEC"), ("other", "Altro")],
        string="Provenienza", tracking=True)
    attachment = fields.Binary(string="PDF della CU", attachment=True)
    attachment_name = fields.Char(string="Nome file")
    state = fields.Selection(
        [("missing", "Mancante"), ("difference", "Differenza"), ("matched", "Quadrata"), ("confirmed", "Confermata")],
        string="Esito", compute="_compute_state", store=True, index=True, tracking=True)
    confirmed = fields.Boolean(string="Confermata", copy=False, tracking=True)
    reminder_count = fields.Integer(string="Solleciti inviati", default=0)
    activity_done_year = fields.Boolean(string="Avviso gia' creato", copy=False)

    @api.depends("partner_id.name", "year")
    def _compute_name(self):
        for rec in self:
            rec.name = "CU %s - %s" % (rec.year or "", rec.partner_id.name or "")

    @api.depends("line_ids.amount", "line_ids.state", "certified_amount")
    def _compute_amounts(self):
        for rec in self:
            lines = rec.line_ids.filtered(lambda l: l.state != "not_operated")
            rec.registered_amount = sum(lines.mapped("amount"))
            rec.difference = rec.certified_amount - rec.registered_amount

    @api.depends("received_date", "difference", "confirmed")
    def _compute_state(self):
        for rec in self:
            if rec.confirmed:
                rec.state = "confirmed"
            elif not rec.received_date:
                rec.state = "missing"
            elif rec.currency_id.is_zero(rec.difference):
                rec.state = "matched"
            else:
                rec.state = "difference"

    def action_confirm(self):
        for rec in self:
            if rec.state == "missing":
                raise UserError(self.env._("Registrare prima la CU ricevuta (data e importi)."))
            if rec.state == "difference" and not self.env.context.get("abc_force"):
                raise UserError(self.env._(
                    "La CU di %s non quadra (differenza %.2f). Sollecitare il cliente o usare "
                    "\"Conferma comunque\".", rec.partner_id.name, rec.difference))
            rec.line_ids.filtered(lambda l: l.state == "suffered").write({"state": "certified"})
            rec.confirmed = True
        return True

    def action_confirm_force(self):
        return self.with_context(abc_force=True).action_confirm()

    def action_reset(self):
        for rec in self:
            if rec.line_ids.filtered(lambda l: l.state == "deducted"):
                raise UserError(self.env._("Ritenute gia' scomputate: impossibile riaprire la CU."))
            rec.line_ids.filtered(lambda l: l.state == "certified").write({"state": "suffered"})
            rec.confirmed = False
        return True

    def action_send_reminder(self):
        """Sollecito al cliente per CU mancante o errata (D45)."""
        self.ensure_one()
        template = self.env.ref("abc_ritenute_acconto.mail_template_cu_reminder", raise_if_not_found=False)
        return {
            "type": "ir.actions.act_window",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": self._name,
                "default_res_ids": self.ids,
                "default_template_id": template.id if template else False,
                "default_composition_mode": "comment",
                "abc_wh_cu_reminder": True,
            },
        }

    def message_post(self, **kwargs):
        if self.env.context.get("abc_wh_cu_reminder"):
            for rec in self:
                rec.reminder_count += 1
        return super().message_post(**kwargs)

    # ------------------------------------------------------------------
    @api.model
    def _abc_generate(self, year, companies=None):
        """Crea un controllo CU per ogni cliente con ritenute subite pagate nell'anno."""
        companies = companies or self.env["res.company"].search([])
        Line = self.env["abc.withholding.line"]
        created = self.browse()
        for company in companies:
            lines = Line.search([
                ("company_id", "=", company.id), ("cycle", "=", "active"), ("kind", "=", "payment"),
                ("payment_year", "=", year), ("cu_received_id", "=", False),
                ("state", "in", ("suffered", "certified")),
            ])
            for partner in lines.partner_id:
                record = self.search([("company_id", "=", company.id), ("partner_id", "=", partner.id),
                                      ("year", "=", year)], limit=1)
                if not record:
                    record = self.create({"company_id": company.id, "partner_id": partner.id, "year": year})
                    created |= record
                lines.filtered(lambda l: l.partner_id == partner).write({"cu_received_id": record.id})
        return created

    def action_generate_current(self):
        year = fields.Date.context_today(self).year - 1
        self._abc_generate(year, self.env.company)
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Controllo CU %s", year),
            "res_model": self._name,
            "view_mode": "list,form",
            "domain": [("year", "=", year), ("company_id", "=", self.env.company.id)],
        }

    @api.model
    def _cron_cu_check(self):
        """Dal 17 marzo: avviso per ogni cliente senza CU o con differenza."""
        today = fields.Date.context_today(self)
        if today < date(today.year, 3, 17):
            return
        year = today.year - 1
        self._abc_generate(year)
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        records = self.search([("year", "=", year), ("state", "in", ("missing", "difference")),
                               ("activity_done_year", "=", False)])
        for rec in records:
            for user in rec.company_id.abc_wh_responsible_ids:
                rec.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary=self.env._("CU %(year)s di %(partner)s: %(state)s",
                                       year=year, partner=rec.partner_id.name,
                                       state=dict(self._fields["state"].selection).get(rec.state)),
                    user_id=user.id,
                )
            rec.activity_done_year = True

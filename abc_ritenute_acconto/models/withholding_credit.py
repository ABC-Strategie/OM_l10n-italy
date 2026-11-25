from odoo import api, fields, models


class AbcWithholdingCredit(models.Model):
    _name = "abc.withholding.credit"
    _description = "Eccedenza di ritenute subite e suo utilizzo (D47)"
    _inherit = ["mail.thread"]
    _order = "year desc"
    _check_company_auto = True

    name = fields.Char(string="Riferimento", compute="_compute_name", store=True)
    company_id = fields.Many2one("res.company", string="Azienda", required=True,
                                 default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    year = fields.Integer(string="Anno d'imposta", required=True, tracking=True)
    tax_kind = fields.Selection([("ires", "IRES"), ("irpef", "IRPEF"), ("other", "Altro")],
                                string="Imposta", default="ires", required=True)
    amount = fields.Monetary(string="Eccedenza da dichiarazione", tracking=True)
    usage_ids = fields.One2many("abc.withholding.credit.usage", "credit_id", string="Utilizzi in F24")
    used_amount = fields.Monetary(string="Utilizzato", compute="_compute_used", store=True)
    residual_amount = fields.Monetary(string="Residuo", compute="_compute_used", store=True)
    note = fields.Text(string="Note")

    @api.depends("year", "tax_kind")
    def _compute_name(self):
        labels = dict(self._fields["tax_kind"].selection)
        for rec in self:
            rec.name = "Credito %s %s" % (labels.get(rec.tax_kind, ""), rec.year or "")

    @api.depends("amount", "usage_ids.amount")
    def _compute_used(self):
        for rec in self:
            rec.used_amount = sum(rec.usage_ids.mapped("amount"))
            rec.residual_amount = rec.amount - rec.used_amount


class AbcWithholdingCreditUsage(models.Model):
    _name = "abc.withholding.credit.usage"
    _description = "Utilizzo in F24 del credito da ritenute"
    _order = "date"

    credit_id = fields.Many2one("abc.withholding.credit", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="credit_id.currency_id")
    date = fields.Date(string="Data F24", required=True)
    tributo_code = fields.Char(string="Codice tributo")
    amount = fields.Monetary(string="Importo compensato", required=True)
    note = fields.Char(string="Note")

from odoo import api, fields, models


class AbcWithholdingTributoMap(models.Model):
    _name = "abc.withholding.tributo.map"
    _description = "Corrispondenza causale ritenuta - codice tributo"
    _order = "reason"
    _rec_name = "reason"

    reason = fields.Char(string="Causale (XML/CU)", required=True)
    withholding_type = fields.Selection(
        [("RT01", "RT01 - Persone fisiche"), ("RT02", "RT02 - Persone giuridiche"),
         ("RT03", "RT03 - Contributo INPS"), ("RT04", "RT04 - Contributo ENASARCO"),
         ("RT05", "RT05 - Contributo ENPAM"), ("RT06", "RT06 - Altro contributo")],
        string="Tipo ritenuta",
        help="Vuoto = vale per tutti i tipi.",
    )
    tributo_code = fields.Char(string="Codice tributo F24", required=True)
    note = fields.Char(string="Nota")
    company_id = fields.Many2one(
        "res.company", string="Azienda",
        help="Vuoto = vale per tutte le aziende.",
    )

    @api.model
    def _abc_get_code(self, reason, withholding_type, company):
        candidates = self.search([
            ("reason", "=", reason or ""),
            "|", ("company_id", "=", False), ("company_id", "=", company.id),
        ])
        best = candidates.filtered(lambda m: m.company_id and m.withholding_type == withholding_type) \
            or candidates.filtered(lambda m: not m.company_id and m.withholding_type == withholding_type) \
            or candidates.filtered(lambda m: m.company_id and not m.withholding_type) \
            or candidates.filtered(lambda m: not m.company_id and not m.withholding_type)
        return best[:1].tributo_code or False

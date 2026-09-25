from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    property_purchase_tax_id = fields.Many2one(
        comodel_name="account.tax",
        string="Imposta acquisti predefinita",
        company_dependent=True,
        domain="[('type_tax_use', '=', 'purchase')]",
        help="Imposta proposta automaticamente sulle righe delle fatture "
             "fornitore quando la riga non ha un prodotto selezionato. "
             "Se il fornitore ha una Posizione fiscale, l'imposta viene "
             "comunque rimappata da quest'ultima.",
    )

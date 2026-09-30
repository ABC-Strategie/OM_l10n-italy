# -*- coding: utf-8 -*-

from odoo import fields, models

# Stesso dominio usato da product.template.property_account_income_id in 19.0.
# Nota: in Odoo 19 account.account.deprecated non esiste piu', non va incluso.
ABC_ACCOUNT_DOMAIN = [
    ("account_type", "not in", (
        "asset_receivable", "liability_payable", "asset_cash",
        "liability_credit_card", "off_balance",
    )),
]


class ResPartner(models.Model):
    _inherit = "res.partner"

    abc_property_account_income_id = fields.Many2one(
        comodel_name="account.account",
        company_dependent=True,
        string="Conto di ricavo",
        domain=ABC_ACCOUNT_DOMAIN,
        ondelete="restrict",
        help="Conto usato sulle righe delle fatture e note di credito cliente di questo contatto. "
             "Se valorizzato prevale sul conto del prodotto o della sua categoria. "
             "Lasciare vuoto per il comportamento standard.",
    )

    abc_property_account_expense_id = fields.Many2one(
        comodel_name="account.account",
        company_dependent=True,
        string="Conto di costo",
        domain=ABC_ACCOUNT_DOMAIN,
        ondelete="restrict",
        help="Conto usato sulle righe delle fatture e note di credito fornitore di questo contatto. "
             "Se valorizzato prevale sul conto del prodotto o della sua categoria. "
             "Lasciare vuoto per il comportamento standard.",
    )

    def _abc_get_invoice_account(self, company, sale):
        """Conto impostato sul contatto per un documento di vendita (sale=True) o di acquisto.

        I campi sono company_dependent e le impostazioni contabili dei contatti figli sono
        gestite sull'azienda madre: si legge dal commercial_partner_id.
        """
        partner = self.commercial_partner_id.with_company(company)
        if sale:
            return partner.abc_property_account_income_id
        return partner.abc_property_account_expense_id

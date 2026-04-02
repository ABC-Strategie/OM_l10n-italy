from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_it_edi_doi_bill_tax_id = fields.Many2one(
        comodel_name="account.tax",
        string="Declaration of Intent Bills Tax",
    )
    # l10n_it_edi_doi_fiscal_position_id: defined in l10n_it_edi_doi (Odoo 19 core).
    # If that field is not present in the installed version, we add it here as a
    # safe fallback so that _compute_fiscal_position_id does not crash on attribute
    # access. The field is declared with check_company=False so it works in all
    # multi-company setups.
    l10n_it_edi_doi_fiscal_position_id = fields.Many2one(
        comodel_name="account.fiscal.position",
        string="Declaration of Intent Fiscal Position",
        check_company=False,
        help="Fiscal position applied automatically when a Declaration of Intent "
        "is selected on a purchase order.",
    )

from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    # stessi campi e stessa logica di visibilità di sale.order (l10n_it_edi_sale)
    l10n_it_cig = fields.Char(
        string="CIG",
        copy=False,
        help="Codice Identificativo Gara",
    )
    l10n_it_cup = fields.Char(
        string="CUP",
        copy=False,
        help="Codice Unico di Progetto",
    )
    # campo tecnico per mostrare o meno CIG e CUP
    l10n_it_partner_pa = fields.Boolean(compute="_compute_l10n_it_partner_pa")

    @api.depends("partner_id.commercial_partner_id.l10n_it_pa_index", "company_id")
    def _compute_l10n_it_partner_pa(self):
        for order in self:
            partner = order.partner_id.commercial_partner_id
            order.l10n_it_partner_pa = bool(partner) and (
                partner._l10n_it_edi_is_public_administration()
                or len(partner.l10n_it_pa_index or "") == 7
            )

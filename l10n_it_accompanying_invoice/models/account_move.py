# Copyright 2017 Lorenzo Battistini - Agile Business Group
# Copyright 2020 Simone Vanin - Agile Business Group
# Copyright 2023 Simone Rubino - Aion Tech
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from odoo import api, models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = [
        "account.move",
        "l10n_it_delivery_note.delivery_mixin",
    ]

    @api.onchange(
        "partner_id",
    )
    def _onchange_partner_shipping_data(self):
        # NOTE: In Odoo 17+ @api.onchange on account.move is deprecated in favour
        # of @api.depends/_compute. This onchange is kept for UI reactivity but
        # the real default propagation happens in _prepare_invoice (sale_order.py).
        # If l10n_it_delivery_note provides its own compute for these fields,
        # this onchange can be safely removed.
        for invoice in self:
            partner = invoice.partner_id
            if partner:
                invoice.delivery_transport_reason_id = (
                    partner.default_transport_reason_id
                )
                invoice.delivery_transport_condition_id = (
                    partner.default_transport_condition_id
                )
                invoice.delivery_transport_method_id = (
                    partner.default_transport_method_id
                )
                invoice.delivery_goods_appearance_id = (
                    partner.default_goods_appearance_id
                )

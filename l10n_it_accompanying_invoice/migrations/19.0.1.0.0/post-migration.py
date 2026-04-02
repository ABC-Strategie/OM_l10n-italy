# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

# Migration 18.0 → 19.0
# No DB schema changes required.
#
# Notes:
#   - This module depends entirely on l10n_it_delivery_note (19.0).
#     It cannot be installed without that module being available and installed first.
#   - _onchange_partner_shipping_data: kept for UI reactivity. In Odoo 17+ onchanges
#     on account.move are deprecated for server-side logic; the actual default
#     propagation is handled by sale_order._prepare_invoice().
#   - The QWeb templates (report_invoice.xml) reference
#     l10n_it_delivery_note.delivery_data and l10n_it_delivery_note.parcels_data.
#     Verify these template IDs exist in l10n_it_delivery_note 19.0.

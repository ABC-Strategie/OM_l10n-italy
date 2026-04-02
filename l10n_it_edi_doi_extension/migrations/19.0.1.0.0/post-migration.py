# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

# Migration 18.0 → 19.0
# Breaking changes fixed (no DB schema changes required):
#   - purchase.order.line.price_unit_discounted removed in Odoo 17+.
#     Replaced with: price_unit * (1 - discount / 100).
#   - l10n_it_edi_doi_fiscal_position_id: added as fallback field on res.company
#     in case the base l10n_it_edi_doi module does not define it in Odoo 19.
#     If l10n_it_edi_doi already defines it, Odoo's ORM will merge the declarations
#     without error (same comodel, no constraint conflict).

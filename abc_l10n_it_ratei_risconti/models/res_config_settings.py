# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    abc_rr_journal_id = fields.Many2one(
        related='company_id.abc_rr_journal_id', readonly=False)
    abc_rr_accrued_income_account_id = fields.Many2one(
        related='company_id.abc_rr_accrued_income_account_id', readonly=False)
    abc_rr_accrued_expense_account_id = fields.Many2one(
        related='company_id.abc_rr_accrued_expense_account_id', readonly=False)
    abc_rr_prepaid_expense_account_id = fields.Many2one(
        related='company_id.abc_rr_prepaid_expense_account_id', readonly=False)
    abc_rr_deferred_income_account_id = fields.Many2one(
        related='company_id.abc_rr_deferred_income_account_id', readonly=False)
    abc_rr_prepaid_expense_long_account_id = fields.Many2one(
        related='company_id.abc_rr_prepaid_expense_long_account_id', readonly=False)
    abc_rr_deferred_income_long_account_id = fields.Many2one(
        related='company_id.abc_rr_deferred_income_long_account_id', readonly=False)
    abc_rr_grouping = fields.Selection(
        related='company_id.abc_rr_grouping', readonly=False)
    abc_rr_asset_prefixes = fields.Char(
        related='company_id.abc_rr_asset_prefixes', readonly=False)
    abc_rr_liability_prefixes = fields.Char(
        related='company_id.abc_rr_liability_prefixes', readonly=False)

# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .rr_compute import ASSET_RR_TYPES, RR_TYPES


class AbcRrAccountMap(models.Model):
    _name = 'abc.rr.account.map'
    _description = 'Eccezione conto ratei e risconti'
    _order = 'company_id, rr_type, source_account_id'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company', string='Societa', required=True, index=True,
        default=lambda self: self.env.company)
    rr_type = fields.Selection(RR_TYPES, string='Tipologia', required=True)
    source_account_id = fields.Many2one(
        'account.account', string='Conto di costo/ricavo', required=True,
        check_company=True)
    rr_account_id = fields.Many2one(
        'account.account', string='Conto rateo/risconto', required=True,
        check_company=True)
    rr_long_account_id = fields.Many2one(
        'account.account', string='Conto oltre 12 mesi', check_company=True,
        help='Solo per i risconti. Se vuoto vale quello delle impostazioni.')

    @api.constrains('company_id', 'rr_type', 'source_account_id')
    def _check_unique(self):
        for rec in self:
            dup = self.search_count([
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
                ('rr_type', '=', rec.rr_type),
                ('source_account_id', '=', rec.source_account_id.id),
            ])
            if dup:
                raise ValidationError(self.env._(
                    "Esiste gia' un'eccezione per il conto %s e questa tipologia.",
                    rec.source_account_id.display_name))

    @api.constrains('rr_type', 'rr_account_id', 'rr_long_account_id')
    def _check_prefix(self):
        for rec in self:
            asset = rec.rr_type in ASSET_RR_TYPES
            rec.company_id._abc_rr_check_account_prefix(rec.rr_account_id, asset)
            rec.company_id._abc_rr_check_account_prefix(rec.rr_long_account_id, asset)

    @api.model
    def _get_accounts(self, company, rr_type, source_account):
        """(conto rateo/risconto, conto oltre 12 mesi) per la coppia data."""
        rec = self.search([
            ('company_id', '=', company.id),
            ('rr_type', '=', rr_type),
            ('source_account_id', '=', source_account.id),
        ], limit=1)
        account = rec.rr_account_id or company._abc_rr_default_account(rr_type)
        long_account = rec.rr_long_account_id or company._abc_rr_default_account(rr_type, long_term=True)
        return account, long_account

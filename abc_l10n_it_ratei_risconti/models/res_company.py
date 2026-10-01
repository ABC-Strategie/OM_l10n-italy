# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

NATIVE_METHOD_FIELDS = (
    'generate_deferred_expense_entries_method',
    'generate_deferred_revenue_entries_method',
)


class ResCompany(models.Model):
    _inherit = 'res.company'

    abc_rr_journal_id = fields.Many2one(
        'account.journal', string='Registro ratei e risconti',
        domain="[('type', '=', 'general'), ('company_id', '=', id)]")
    abc_rr_accrued_income_account_id = fields.Many2one(
        'account.account', string='Conto ratei attivi')
    abc_rr_accrued_expense_account_id = fields.Many2one(
        'account.account', string='Conto ratei passivi')
    abc_rr_prepaid_expense_account_id = fields.Many2one(
        'account.account', string='Conto risconti attivi')
    abc_rr_deferred_income_account_id = fields.Many2one(
        'account.account', string='Conto risconti passivi')
    abc_rr_prepaid_expense_long_account_id = fields.Many2one(
        'account.account', string='Conto risconti attivi oltre 12 mesi')
    abc_rr_deferred_income_long_account_id = fields.Many2one(
        'account.account', string='Conto risconti passivi oltre 12 mesi')
    abc_rr_grouping = fields.Selection(
        [('origin', 'Una riga per origine'), ('account', 'Una riga per conto')],
        string='Raggruppamento scrittura', default='origin', required=True)
    abc_rr_asset_prefixes = fields.Char(
        string='Prefissi conti voce D attivo', default='1901,1902',
        help='Prefissi (separati da virgola) ammessi per ratei e risconti attivi. '
             'Vuoto = nessun controllo.')
    abc_rr_liability_prefixes = fields.Char(
        string='Prefissi conti voce E passivo', default='270,280,281',
        help='Prefissi (separati da virgola) ammessi per ratei e risconti passivi. '
             'Vuoto = nessun controllo.')

    # ------------------------------------------------------------------
    # Conti
    # ------------------------------------------------------------------
    def _abc_rr_default_account(self, rr_type, long_term=False):
        self.ensure_one()
        if long_term:
            if rr_type == 'risconto_attivo':
                return self.abc_rr_prepaid_expense_long_account_id
            if rr_type == 'risconto_passivo':
                return self.abc_rr_deferred_income_long_account_id
            return self.env['account.account']
        return {
            'rateo_attivo': self.abc_rr_accrued_income_account_id,
            'rateo_passivo': self.abc_rr_accrued_expense_account_id,
            'risconto_attivo': self.abc_rr_prepaid_expense_account_id,
            'risconto_passivo': self.abc_rr_deferred_income_account_id,
        }[rr_type]

    def _abc_rr_check_account_prefix(self, account, asset_side):
        """Solleva un errore se il conto non rientra nella voce di bilancio attesa."""
        self.ensure_one()
        if not account:
            return
        raw = self.abc_rr_asset_prefixes if asset_side else self.abc_rr_liability_prefixes
        prefixes = [p.strip() for p in (raw or '').split(',') if p.strip()]
        code = account.with_company(self).code or ''
        if prefixes and not any(code.startswith(p) for p in prefixes):
            raise ValidationError(self.env._(
                "Il conto %(account)s non appartiene alla voce di bilancio dei ratei e "
                "risconti (%(side)s, prefissi ammessi: %(prefixes)s).",
                account=account.display_name,
                side=self.env._('attivo') if asset_side else self.env._('passivo'),
                prefixes=', '.join(prefixes),
            ))

    @api.constrains(
        'abc_rr_accrued_income_account_id', 'abc_rr_accrued_expense_account_id',
        'abc_rr_prepaid_expense_account_id', 'abc_rr_deferred_income_account_id',
        'abc_rr_prepaid_expense_long_account_id', 'abc_rr_deferred_income_long_account_id',
        'abc_rr_asset_prefixes', 'abc_rr_liability_prefixes')
    def _check_abc_rr_accounts(self):
        for company in self:
            company._abc_rr_check_account_prefix(company.abc_rr_accrued_income_account_id, True)
            company._abc_rr_check_account_prefix(company.abc_rr_prepaid_expense_account_id, True)
            company._abc_rr_check_account_prefix(company.abc_rr_prepaid_expense_long_account_id, True)
            company._abc_rr_check_account_prefix(company.abc_rr_accrued_expense_account_id, False)
            company._abc_rr_check_account_prefix(company.abc_rr_deferred_income_account_id, False)
            company._abc_rr_check_account_prefix(company.abc_rr_deferred_income_long_account_id, False)

    # ------------------------------------------------------------------
    # Differimenti nativi: sempre manuali, il calcolo lo fa questo modulo
    # ------------------------------------------------------------------
    @api.model
    def _abc_rr_force_manual(self, vals):
        for fname in NATIVE_METHOD_FIELDS:
            if fname in self._fields and vals.get(fname) == 'on_validation':
                vals[fname] = 'manual'
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create([self._abc_rr_force_manual(dict(v)) for v in vals_list])
        companies._abc_rr_disable_native()
        return companies

    def write(self, vals):
        return super().write(self._abc_rr_force_manual(dict(vals)))

    def _abc_rr_disable_native(self):
        vals = {f: 'manual' for f in NATIVE_METHOD_FIELDS if f in self._fields}
        if vals:
            to_fix = self.filtered(lambda c: any(c[f] != 'manual' for f in vals))
            if to_fix:
                super(ResCompany, to_fix).write(vals)

    # ------------------------------------------------------------------
    # Esercizio
    # ------------------------------------------------------------------
    def _abc_rr_closing_date(self, ref_date):
        """Data di chiusura dell'esercizio che contiene ``ref_date``,
        letta dalle impostazioni della societa'."""
        self.ensure_one()
        return fields.Date.to_date(self.compute_fiscalyear_dates(ref_date)['date_to'])

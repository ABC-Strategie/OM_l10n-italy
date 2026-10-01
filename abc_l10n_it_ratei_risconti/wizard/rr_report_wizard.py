# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import fields, models

from ..models.rr_compute import RR_TYPES, days_between, entry_sign, rr_kind, total_days


class AbcRrReportWizard(models.TransientModel):
    _name = 'abc.rr.report.wizard'
    _description = 'Report ratei e risconti'

    mode = fields.Selection(
        [('multi', 'Piano dei risconti pluriennali'),
         ('leasing', 'Leasing: civilistico e fiscale'),
         ('check', 'Quadratura con la contabilita')],
        string='Report', required=True, default='multi')
    company_id = fields.Many2one('res.company', string='Societa', required=True,
                                 default=lambda self: self.env.company)
    closing_date = fields.Date(string='Data di chiusura (D)', required=True,
                               default=lambda self: self.env['abc.rr.run.wizard']._default_closing_date())
    include_draft = fields.Boolean(string='Includi elaborazioni in bozza')

    def _run_lines(self):
        states = ['confirmed', 'draft'] if self.include_draft else ['confirmed']
        return self.env['abc.rr.run.line'].search([
            ('company_id', '=', self.company_id.id),
            ('closing_date', '=', self.closing_date),
            ('run_state', 'in', states),
            ('excluded', '=', False),
        ])

    def _fiscal_years(self, date_from, date_to):
        """Elenco (inizio, fine) degli esercizi che coprono [date_from, date_to]."""
        company = self.company_id
        years = []
        cursor = date_from
        while cursor <= date_to and len(years) < 60:
            dates = company.compute_fiscalyear_dates(cursor)
            start = fields.Date.to_date(dates['date_from'])
            end = fields.Date.to_date(dates['date_to'])
            years.append((start, end))
            cursor = end + relativedelta(days=1)
        return years

    def action_open(self):
        self.ensure_one()
        closing = self.company_id._abc_rr_closing_date(self.closing_date)
        if closing != self.closing_date:
            self.closing_date = closing
        Out = self.env['abc.rr.report.line']
        Out.search([('create_uid', '=', self.env.uid), ('mode', '=', self.mode)]).unlink()
        currency = self.company_id.currency_id
        vals_list = []
        lines = self._run_lines()
        if self.mode == 'multi':
            for line in lines.filtered(lambda l: rr_kind(l.rr_type) == 'risconto' and not l.adjustment
                                       and l.base_amount and l.date_start and l.date_end):
                tot = total_days(line.date_start, line.date_end)
                for fy_start, fy_end in self._fiscal_years(self.closing_date + relativedelta(days=1), line.date_end):
                    days = days_between(line.date_start, line.date_end, fy_start, fy_end)
                    if not days:
                        continue
                    vals_list.append({
                        'mode': 'multi', 'wizard_closing_date': self.closing_date,
                        'company_id': self.company_id.id, 'run_line_id': line.id,
                        'name': line.name, 'rr_type': line.rr_type, 'account_id': line.account_id.id,
                        'partner_id': line.partner_id.id, 'fy_end': fy_end,
                        'civil_amount': currency.round(abs(line.base_amount) * days / tot),
                    })
        elif self.mode == 'leasing':
            for line in lines.filtered(lambda l: l.tax_date_start and l.tax_date_end and not l.adjustment
                                       and l.base_amount and l.date_start and l.date_end):
                tot_c = total_days(line.date_start, line.date_end)
                tot_f = total_days(line.tax_date_start, line.tax_date_end)
                first = min(line.date_start, line.tax_date_start)
                last = max(line.date_end, line.tax_date_end)
                cumulative = 0.0
                base = abs(line.base_amount)
                for fy_start, fy_end in self._fiscal_years(first, last):
                    civil = currency.round(base * days_between(line.date_start, line.date_end, fy_start, fy_end) / tot_c)
                    tax = currency.round(base * days_between(line.tax_date_start, line.tax_date_end, fy_start, fy_end) / tot_f)
                    diff = currency.round(tax - civil)
                    cumulative = currency.round(cumulative + diff)
                    vals_list.append({
                        'mode': 'leasing', 'wizard_closing_date': self.closing_date,
                        'company_id': self.company_id.id, 'run_line_id': line.id,
                        'name': line.name, 'rr_type': line.rr_type, 'account_id': line.account_id.id,
                        'partner_id': line.partner_id.id, 'fy_end': fy_end,
                        'civil_amount': civil, 'tax_amount': tax,
                        'difference': diff, 'cumulative': cumulative,
                    })
        else:
            expected = {}
            for line in lines.filtered(lambda l: l.run_state == 'confirmed'):
                sign = entry_sign(line.rr_type)
                if line.rr_long_account_id and line.final_beyond:
                    expected[line.rr_long_account_id] = expected.get(line.rr_long_account_id, 0.0) - sign * line.final_beyond
                    expected[line.rr_account_id] = expected.get(line.rr_account_id, 0.0) - sign * line.final_within
                elif line.rr_account_id:
                    expected[line.rr_account_id] = expected.get(line.rr_account_id, 0.0) - sign * line.amount
            company = self.company_id
            accounts = set(expected)
            for acc in (company.abc_rr_accrued_income_account_id, company.abc_rr_accrued_expense_account_id,
                        company.abc_rr_prepaid_expense_account_id, company.abc_rr_deferred_income_account_id,
                        company.abc_rr_prepaid_expense_long_account_id,
                        company.abc_rr_deferred_income_long_account_id):
                if acc:
                    accounts.add(acc)
            accounts |= set(self.env['abc.rr.account.map'].search(
                [('company_id', '=', company.id)]).mapped('rr_account_id'))
            for acc in accounts:
                [(book,)] = self.env['account.move.line']._read_group([
                    ('company_id', '=', company.id), ('account_id', '=', acc.id),
                    ('parent_state', '=', 'posted'), ('date', '<=', self.closing_date),
                ], aggregates=['balance:sum'])
                book = book or 0.0
                exp = currency.round(expected.get(acc, 0.0))
                vals_list.append({
                    'mode': 'check', 'wizard_closing_date': self.closing_date,
                    'company_id': company.id, 'name': acc.display_name, 'account_id': acc.id,
                    'book_balance': currency.round(book), 'run_balance': exp,
                    'difference': currency.round(book - exp),
                })
        Out.create(vals_list)
        title = dict(self._fields['mode'].selection)[self.mode]
        return {
            'type': 'ir.actions.act_window',
            'name': '%s - %s' % (title, self.closing_date.strftime('%d/%m/%Y')),
            'res_model': 'abc.rr.report.line',
            'view_mode': 'list,pivot',
            'views': [(self.env.ref('abc_l10n_it_ratei_risconti.view_rr_report_line_list_%s' % self.mode).id, 'list'),
                      (False, 'pivot')],
            'domain': [('create_uid', '=', self.env.uid), ('mode', '=', self.mode)],
            'context': {'search_default_group_fy': 1} if self.mode != 'check' else {},
        }


class AbcRrReportLine(models.TransientModel):
    _name = 'abc.rr.report.line'
    _description = 'Riga report ratei e risconti'
    _order = 'name, fy_end'
    _transient_max_hours = 12.0

    mode = fields.Selection(
        [('multi', 'Pluriennali'), ('leasing', 'Leasing'), ('check', 'Quadratura')], required=True)
    company_id = fields.Many2one('res.company', string='Societa')
    currency_id = fields.Many2one(related='company_id.currency_id')
    wizard_closing_date = fields.Date(string='Data D')
    run_line_id = fields.Many2one('abc.rr.run.line', string='Riga elaborazione', ondelete='cascade')
    name = fields.Char(string='Descrizione')
    rr_type = fields.Selection(RR_TYPES, string='Tipologia')
    account_id = fields.Many2one('account.account', string='Conto')
    partner_id = fields.Many2one('res.partner', string='Partner')
    fy_end = fields.Date(string='Esercizio al')
    civil_amount = fields.Monetary(string='Quota civilistica')
    tax_amount = fields.Monetary(string='Quota fiscale')
    difference = fields.Monetary(string='Differenza')
    cumulative = fields.Monetary(string='Differenza cumulata')
    book_balance = fields.Monetary(string='Saldo contabile a D')
    run_balance = fields.Monetary(string='Totale elaborazioni a D')

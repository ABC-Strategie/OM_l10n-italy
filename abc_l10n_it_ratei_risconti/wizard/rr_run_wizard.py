# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class AbcRrRunWizard(models.TransientModel):
    _name = 'abc.rr.run.wizard'
    _description = 'Nuova elaborazione ratei e risconti'

    company_id = fields.Many2one(
        'res.company', string='Societa', required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [('id', 'in', self.env.companies.ids)])
    closing_date = fields.Date(
        string='Data di chiusura (D)', required=True,
        default=lambda self: self._default_closing_date(),
        help="Fine esercizio dalle impostazioni della societa'. Si puo' scegliere un'altra "
             "data dell'esercizio: viene riportata alla sua chiusura.")
    pending_count = fields.Integer(string='Fonti da elaborare', compute='_compute_info')
    existing_info = fields.Char(compute='_compute_info')

    @api.model
    def _default_closing_date(self):
        company = self.env.company
        today = fields.Date.context_today(self)
        date_from = fields.Date.to_date(company.compute_fiscalyear_dates(today)['date_from'])
        return date_from - relativedelta(days=1)

    @api.onchange('closing_date', 'company_id')
    def _onchange_closing_date(self):
        if self.closing_date and self.company_id:
            closing = self.company_id._abc_rr_closing_date(self.closing_date)
            if closing != self.closing_date:
                self.closing_date = closing

    @api.depends('closing_date', 'company_id')
    def _compute_info(self):
        Run = self.env['abc.rr.run']
        for wiz in self:
            if not (wiz.closing_date and wiz.company_id):
                wiz.pending_count = 0
                wiz.existing_info = False
                continue
            wiz.pending_count = Run._pending_sources_count(wiz.company_id, wiz.closing_date)
            runs = Run.search([('company_id', '=', wiz.company_id.id),
                               ('closing_date', '=', wiz.closing_date),
                               ('state', '!=', 'cancelled')])
            wiz.existing_info = ', '.join(
                '%s (%s)' % (r.name, dict(r._fields['state'].selection)[r.state]) for r in runs) or False

    def action_create(self):
        self.ensure_one()
        company = self.company_id
        closing = company._abc_rr_closing_date(self.closing_date)
        Run = self.env['abc.rr.run'].with_company(company)
        draft = Run.search([('company_id', '=', company.id), ('closing_date', '=', closing),
                            ('state', '=', 'draft')], limit=1)
        if draft:
            draft.action_compute()
            run = draft
        else:
            confirmed = Run.search_count([('company_id', '=', company.id), ('closing_date', '=', closing),
                                          ('state', '=', 'confirmed')])
            run = Run.create({
                'company_id': company.id,
                'closing_date': closing,
                'run_type': 'supplement' if confirmed else 'main',
            })
            run.action_compute()
        if not run.line_ids:
            run.message_post(body=self.env._("Nessun rateo o risconto da elaborare alla data."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'abc.rr.run',
            'res_id': run.id,
            'view_mode': 'form',
            'target': 'current',
        }

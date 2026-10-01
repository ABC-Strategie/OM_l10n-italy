# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.rr_compute import RR_TYPES


class AbcRrProspettoWizard(models.TransientModel):
    _name = 'abc.rr.prospetto.wizard'
    _description = 'Stampa ed estrazione prospetto ratei e risconti'

    output = fields.Selection([('pdf', 'PDF'), ('xlsx', 'Excel')], string='Formato', required=True, default='pdf')
    line_ids = fields.Many2many(
        'abc.rr.run.line', 'abc_rr_prospetto_wizard_line_rel', 'wizard_id', 'line_id',
        string='Righe selezionate', default=lambda self: self._default_line_ids())
    selected_count = fields.Integer(string='Righe selezionate', compute='_compute_selected_count')
    company_id = fields.Many2one('res.company', string='Società', required=True,
                                 default=lambda self: self.env.company)
    date_from = fields.Date(
        string='Data di chiusura dal',
        default=lambda self: False if self._default_line_ids()
        else self.env['abc.rr.run.wizard']._default_closing_date(),
        help='Prima data di chiusura (D) da includere. Vuoto = nessun limite.')
    date_to = fields.Date(
        string='al',
        default=lambda self: False if self._default_line_ids()
        else self.env['abc.rr.run.wizard']._default_closing_date(),
        help='Ultima data di chiusura (D) da includere. Vuoto = nessun limite.')
    rr_type = fields.Selection(RR_TYPES, string='Tipologia', help='Vuoto = tutte le tipologie.')
    available_account_ids = fields.Many2many(
        'account.account', compute='_compute_available_account_ids')
    rr_account_ids = fields.Many2many(
        'account.account', 'abc_rr_prospetto_wizard_account_rel', 'wizard_id', 'account_id',
        string='Conti rateo/risconto',
        domain="[('id', 'in', available_account_ids)]",
        help='Vuoto = tutti i conti.')
    only_confirmed = fields.Boolean(string='Solo elaborazioni confermate', default=True)
    include_excluded = fields.Boolean(string='Includi righe escluse')

    @api.model
    def _default_line_ids(self):
        ctx = self.env.context
        if ctx.get('active_model') == 'abc.rr.run.line' and ctx.get('active_ids'):
            return [(6, 0, ctx['active_ids'])]
        return False

    @api.depends('line_ids')
    def _compute_selected_count(self):
        for wiz in self:
            wiz.selected_count = len(wiz.line_ids)

    def _base_domain(self, with_accounts=True):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id), ('run_state', '!=', 'cancelled')]
        if self.line_ids:
            domain.append(('id', 'in', self.line_ids.ids))
        if self.date_from:
            domain.append(('closing_date', '>=', self.date_from))
        if self.date_to:
            domain.append(('closing_date', '<=', self.date_to))
        if self.rr_type:
            domain.append(('rr_type', '=', self.rr_type))
        if self.only_confirmed:
            domain.append(('run_state', '=', 'confirmed'))
        if not self.include_excluded:
            domain.append(('excluded', '=', False))
        if with_accounts and self.rr_account_ids:
            # il conto oltre 12 mesi conta solo se la riga ha davvero una quota oltre 12 mesi
            domain += ['|', ('rr_account_id', 'in', self.rr_account_ids.ids),
                       '&', ('rr_long_account_id', 'in', self.rr_account_ids.ids), ('final_beyond', '!=', 0)]
        return domain

    @api.depends('company_id', 'date_from', 'date_to', 'rr_type', 'only_confirmed', 'include_excluded', 'line_ids')
    def _compute_available_account_ids(self):
        for wiz in self:
            if not wiz.company_id:
                wiz.available_account_ids = False
                continue
            lines = self.env['abc.rr.run.line'].search(wiz._base_domain(with_accounts=False))
            wiz.available_account_ids = lines.rr_account_id | lines.filtered('final_beyond').rr_long_account_id

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wiz in self:
            if wiz.date_from and wiz.date_to and wiz.date_to < wiz.date_from:
                raise UserError(self.env._("La data finale precede la data iniziale."))

    def _lines(self):
        lines = self.env['abc.rr.run.line'].search(self._base_domain())
        if not lines:
            raise UserError(self.env._("Nessuna riga corrisponde ai filtri scelti."))
        return lines

    def action_print(self):
        self.ensure_one()
        lines = self._lines()
        if self.output == 'xlsx':
            return lines._prospetto_xlsx_action()
        return self.env.ref('abc_l10n_it_ratei_risconti.action_report_rr_prospetto').report_action(lines)

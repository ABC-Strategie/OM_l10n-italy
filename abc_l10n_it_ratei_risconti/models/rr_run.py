# -*- coding: utf-8 -*-
import hashlib
import json
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

from .rr_compute import (
    COST_TYPES, INCOME_TYPES, RR_TYPES, classify, compute_quota, days_between, entry_sign, rr_kind,
    split_final,
)


class AbcRrRun(models.Model):
    _name = 'abc.rr.run'
    _description = 'Elaborazione ratei e risconti'
    _inherit = ['mail.thread']
    _order = 'closing_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Numero', required=True, copy=False, readonly=True, default='/')
    company_id = fields.Many2one(
        'res.company', string='Societa', required=True, index=True, readonly=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    closing_date = fields.Date(string='Data di chiusura (D)', required=True, readonly=True, index=True)
    run_type = fields.Selection(
        [('main', 'Principale'), ('supplement', 'Integrativa')],
        string='Tipo', required=True, readonly=True, default='main')
    state = fields.Selection(
        [('draft', 'Bozza'), ('confirmed', 'Confermata'), ('cancelled', 'Annullata')],
        string='Stato', default='draft', required=True, readonly=True, tracking=True, copy=False)
    line_ids = fields.One2many('abc.rr.run.line', 'run_id', string='Righe')
    move_id = fields.Many2one('account.move', string='Scrittura di assestamento', readonly=True, copy=False)
    reverse_move_id = fields.Many2one('account.move', string='Scrittura di storno', readonly=True, copy=False)
    confirm_uid = fields.Many2one('res.users', string='Confermata da', readonly=True, copy=False)
    confirm_date = fields.Datetime(string='Confermata il', readonly=True, copy=False)
    note = fields.Text(string='Note')

    line_count = fields.Integer(compute='_compute_totals')
    changed_count = fields.Integer(string='Fonti modificate', compute='_compute_changed')
    full_count = fields.Integer(string='Ratei al 100%', compute='_compute_totals')
    total_rateo_attivo = fields.Monetary(compute='_compute_totals', string='Ratei attivi')
    total_rateo_passivo = fields.Monetary(compute='_compute_totals', string='Ratei passivi')
    total_risconto_attivo = fields.Monetary(compute='_compute_totals', string='Risconti attivi')
    total_risconto_passivo = fields.Monetary(compute='_compute_totals', string='Risconti passivi')

    @api.depends('line_ids.amount', 'line_ids.excluded', 'line_ids.rr_type', 'line_ids.full_period')
    def _compute_totals(self):
        for run in self:
            lines = run.line_ids.filtered(lambda l: not l.excluded)
            run.line_count = len(run.line_ids)
            run.full_count = len(lines.filtered(lambda l: l.full_period and rr_kind(l.rr_type) == 'rateo'))
            for rr_type, _label in RR_TYPES:
                # importi esposti positivi, come nel prospetto di bilancio
                run['total_%s' % rr_type] = sum(
                    l.amount * l._natural_sign() for l in lines if l.rr_type == rr_type)

    def _compute_changed(self):
        for run in self:
            run.changed_count = len(run.line_ids.filtered('source_changed')) if run.state == 'confirmed' else 0

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('abc.rr.run') or '/'
        return super().create(vals_list)

    def unlink(self):
        if any(run.state == 'confirmed' for run in self):
            raise UserError(self.env._("Annullare l'elaborazione prima di eliminarla."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Candidati
    # ------------------------------------------------------------------
    def _source_domain(self):
        self.ensure_one()
        return [
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('deferred_start_date', '!=', False),
            ('deferred_end_date', '!=', False),
            ('display_type', 'not in', ('line_section', 'line_note')),
            ('account_id.account_type', 'in', list(COST_TYPES + INCOME_TYPES)),
            '|',
            # risconti: registrati entro D, competenza oltre D
            '&', ('date', '<=', self.closing_date), ('deferred_end_date', '>', self.closing_date),
            # ratei: registrati dopo D, competenza iniziata entro D
            '&', ('date', '>', self.closing_date), ('deferred_start_date', '<=', self.closing_date),
        ]

    def _candidate_from_aml(self, aml):
        nature = 'cost' if aml.account_id.account_type in COST_TYPES else 'income'
        rr_type = classify(aml.date, self.closing_date, nature)
        return {
            'aml': aml,
            'card': self.env['abc.rr.card'],
            'rr_type': rr_type,
            'account': aml.account_id,
            'forced_rr_account': self.env['account.account'],
            'partner': aml.partner_id,
            'analytic': aml.analytic_distribution or False,
            'balance': aml.balance,
            'start': aml.deferred_start_date,
            'end': aml.deferred_end_date,
            'tax_start': aml.abc_rr_tax_date_start,
            'tax_end': aml.abc_rr_tax_date_end,
            'label': aml.name or aml.move_id.name,
            'fingerprint': self.env['abc.rr.run.line']._fingerprint_aml(aml),
        }

    def _candidate_from_card(self, card):
        return {
            'aml': self.env['account.move.line'],
            'card': card,
            'rr_type': card.rr_type,
            'account': card.account_id,
            'forced_rr_account': card.rr_account_id,
            'partner': card.partner_id,
            'analytic': card.analytic_distribution or False,
            'balance': card._signed_base(),
            'start': card.date_start,
            'end': card.date_end,
            'tax_start': card.tax_date_start,
            'tax_end': card.tax_date_end,
            'label': card.name,
            'fingerprint': self.env['abc.rr.run.line']._fingerprint_card(card),
        }

    def _card_domain(self):
        self.ensure_one()
        d = self.closing_date
        fy_start = fields.Date.to_date(self.company_id.compute_fiscalyear_dates(d)['date_from'])
        return [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'active'),
            '|',
            '&', ('rr_type', 'in', ('risconto_attivo', 'risconto_passivo')), ('date_end', '>', d),
            # ratei: iniziati entro D e non terminati prima dell'esercizio
            '&', ('rr_type', 'in', ('rateo_attivo', 'rateo_passivo')),
            '&', ('date_start', '<=', d), ('date_end', '>=', fy_start),
        ]

    def _card_already_realized(self, card):
        """Scheda rateo con periodo terminato entro D e gia' registrata a una chiusura
        precedente: il documento vero e' arrivato (o doveva arrivare) nell'esercizio,
        quindi non si ripropone."""
        self.ensure_one()
        if rr_kind(card.rr_type) != 'rateo' or card.date_end > self.closing_date:
            return False
        return bool(self.env['abc.rr.run.line'].search_count([
            ('card_id', '=', card.id),
            ('run_id.state', '=', 'confirmed'),
            ('run_id.closing_date', '<', self.closing_date),
        ]))

    def _booked_by_source(self):
        """Quote gia' elaborate (calcolate) per fonte, nelle elaborazioni
        confermate della stessa societa' e data D, esclusa questa."""
        self.ensure_one()
        lines = self.env['abc.rr.run.line'].search([
            ('run_id', '!=', self.id),
            ('run_id.company_id', '=', self.company_id.id),
            ('run_id.closing_date', '=', self.closing_date),
            ('run_id.state', '=', 'confirmed'),
        ])
        empty = self.env['abc.rr.run.line']
        booked = defaultdict(lambda: {
            'amount': 0.0, 'within': 0.0, 'beyond': 0.0, 'beyond_5y': 0.0,
            'posted': 0.0, 'posted_within': 0.0, 'posted_beyond': 0.0, 'lines': empty})
        for line in lines:
            item = booked[line._source_key()]
            # quote calcolate (anche delle righe escluse): servono a capire se la fonte e' cambiata
            item['amount'] += line.calc_amount
            item['within'] += line.calc_within
            item['beyond'] += line.calc_beyond
            item['beyond_5y'] += line.amount_beyond_5y
            # quote registrate davvero: servono per stornarle se la fonte non vale piu'
            if not line.excluded:
                item['posted'] += line.amount
                item['posted_within'] += line.final_within
                item['posted_beyond'] += line.final_beyond
            item['lines'] |= line
        return booked

    # ------------------------------------------------------------------
    # Azioni
    # ------------------------------------------------------------------
    def action_compute(self):
        Line = self.env['abc.rr.run.line']
        for run in self:
            if run.state != 'draft':
                raise UserError(self.env._("Si possono ricalcolare solo le elaborazioni in bozza."))
            currency = run.company_id.currency_id
            run.line_ids.unlink()
            booked = run._booked_by_source()
            seen = set()
            vals_list = []
            candidates = [run._candidate_from_aml(aml)
                          for aml in self.env['account.move.line'].search(run._source_domain())]
            candidates += [run._candidate_from_card(card)
                           for card in self.env['abc.rr.card'].search(run._card_domain())
                           if not run._card_already_realized(card)]
            for cand in candidates:
                key = ('aml', cand['aml'].id) if cand['aml'] else ('card', cand['card'].id)
                seen.add(key)
                res = compute_quota(cand['balance'], cand['start'], cand['end'], run.closing_date,
                                    cand['rr_type'], round_fn=currency.round)
                if not res:
                    continue
                prev = booked.get(key)
                amount = res['amount'] - (prev['amount'] if prev else 0.0)
                within = res['amount_within'] - (prev['within'] if prev else 0.0)
                beyond = res['amount_beyond'] - (prev['beyond'] if prev else 0.0)
                if float_is_zero(amount, precision_rounding=currency.rounding) and \
                        float_is_zero(beyond, precision_rounding=currency.rounding):
                    continue
                vals = Line._prepare_vals(run, cand, res, amount, within, beyond)
                if prev:
                    vals['adjustment'] = True
                    vals['amount_beyond_5y'] = res['amount_beyond_5y'] - prev['beyond_5y']
                vals_list.append(vals)
            # fonti gia' elaborate che non sono piu' candidate: quota uguale e contraria
            for key, prev in booked.items():
                if key in seen or float_is_zero(prev['posted'], precision_rounding=currency.rounding):
                    continue
                last = prev['lines'][-1]
                vals_list.append(last._prepare_reversal_vals(run, prev))
            Line.create(vals_list)
        return True

    def _check_config(self):
        self.ensure_one()
        company = self.company_id
        if not company.abc_rr_journal_id:
            raise UserError(self.env._("Configurare il registro ratei e risconti nelle impostazioni della societa' %s.", company.name))
        missing = self.line_ids.filtered(lambda l: not l.excluded and not l.rr_account_id)
        if missing:
            raise UserError(self.env._(
                "Manca il conto rateo/risconto su %s righe: configurarlo nelle impostazioni o sulle righe.",
                len(missing)))

    def _prepare_move_lines(self):
        self.ensure_one()
        currency = self.company_id.currency_id
        grouping = self.company_id.abc_rr_grouping
        raw = []  # (account, partner, analytic_json, name, balance)
        for line in self.line_ids.filtered(lambda l: not l.excluded):
            if float_is_zero(line.amount, precision_rounding=currency.rounding) and \
                    float_is_zero(line.final_beyond, precision_rounding=currency.rounding):
                continue
            sign = entry_sign(line.rr_type)
            within, beyond = line.final_within, line.final_beyond
            label = line.name
            raw.append((line.account_id, line.partner_id, line.analytic_distribution, label, sign * line.amount))
            if line.rr_long_account_id and not float_is_zero(beyond, precision_rounding=currency.rounding):
                raw.append((line.rr_account_id, line.partner_id, False, label, -sign * within))
                raw.append((line.rr_long_account_id, line.partner_id, False, label, -sign * beyond))
            else:
                raw.append((line.rr_account_id, line.partner_id, False, label, -sign * line.amount))
        if grouping == 'account':
            grouped = defaultdict(float)
            for account, _partner, analytic, _label, bal in raw:
                grouped[(account.id, json.dumps(analytic, sort_keys=True) if analytic else '')] += bal
            raw = []
            for (account_id, analytic_json), bal in grouped.items():
                account = self.env['account.account'].browse(account_id)
                raw.append((account, self.env['res.partner'], json.loads(analytic_json) if analytic_json else False,
                            self.env._("Ratei e risconti al %s", fields.Date.to_string(self.closing_date)), bal))
        commands = []
        for account, partner, analytic, label, bal in raw:
            bal = currency.round(bal)
            if float_is_zero(bal, precision_rounding=currency.rounding):
                continue
            commands.append(Command.create({
                'name': label,
                'account_id': account.id,
                'partner_id': partner.id or False,
                'debit': bal if bal > 0 else 0.0,
                'credit': -bal if bal < 0 else 0.0,
                'analytic_distribution': analytic or False,
            }))
        return commands

    def action_confirm(self):
        for run in self:
            if run.state != 'draft':
                raise UserError(self.env._("L'elaborazione %s non e' in bozza.", run.name))
            run._check_config()
            commands = run._prepare_move_lines()
            if not commands:
                raise UserError(self.env._("Nessuna quota da registrare nell'elaborazione %s.", run.name))
            ref = self.env._("Ratei e risconti al %(date)s (%(run)s)",
                             date=run.closing_date.strftime('%d/%m/%Y'), run=run.name)
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': run.company_id.abc_rr_journal_id.id,
                'company_id': run.company_id.id,
                'date': run.closing_date,
                'ref': ref,
                'abc_rr_run_id': run.id,
                'line_ids': commands,
            })
            move.action_post()
            storno_date = run.closing_date + relativedelta(days=1)
            reverse = move._reverse_moves([{
                'date': storno_date,
                'ref': self.env._("Storno %s", ref),
                'abc_rr_run_id': run.id,
            }])
            reverse.action_post()
            run.write({
                'state': 'confirmed',
                'move_id': move.id,
                'reverse_move_id': reverse.id,
                'confirm_uid': self.env.uid,
                'confirm_date': fields.Datetime.now(),
            })
            run.line_ids._store_fingerprint()
        return True

    def action_cancel(self):
        for run in self:
            if run.state != 'confirmed':
                raise UserError(self.env._("Si possono annullare solo le elaborazioni confermate."))
            later = self.search([
                ('company_id', '=', run.company_id.id),
                ('closing_date', '=', run.closing_date),
                ('state', '=', 'confirmed'),
                ('id', '>', run.id),
            ])
            if later:
                raise UserError(self.env._(
                    "Annullare prima le elaborazioni successive per la stessa data: %s.",
                    ', '.join(later.mapped('name'))))
            moves = (run.move_id | run.reverse_move_id).with_context(abc_rr_allow=True)
            posted = moves.filtered(lambda m: m.state == 'posted')
            posted.button_draft()
            moves.button_cancel()
            run.write({'state': 'draft', 'move_id': False, 'reverse_move_id': False,
                       'confirm_uid': False, 'confirm_date': False})
            run.message_post(body=self.env._(
                "Elaborazione annullata: le scritture %s sono state annullate.",
                ', '.join(m.name or str(m.id) for m in moves)))
        return True

    def action_discard(self):
        self.filtered(lambda r: r.state == 'draft').write({'state': 'cancelled'})
        return True

    def action_view_moves(self):
        self.ensure_one()
        moves = self.move_id | self.reverse_move_id
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Scritture'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }

    def action_view_changed(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Fonti modificate'),
            'res_model': 'abc.rr.run.line',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.line_ids.filtered('source_changed').ids)],
        }

    def get_report_groups(self):
        """Dati del prospetto PDF: una sezione per tipologia, importi positivi."""
        self.ensure_one()
        groups = []
        for rr_type, label in RR_TYPES:
            lines = self.line_ids.filtered(lambda l: l.rr_type == rr_type and not l.excluded).sorted(
                lambda l: (l.rr_account_id.code or '', l.date_start or self.closing_date, l.id))
            if not lines:
                continue
            rows = []
            totals = {'amount': 0.0, 'within': 0.0, 'beyond': 0.0, 'beyond_5y': 0.0}
            for line in lines:
                sg = line._natural_sign()
                row = {
                    'line': line,
                    'base': line.base_amount * sg,
                    'competence': line.competence_amount * sg,
                    'amount': line.amount * sg,
                    'within': line.final_within * sg,
                    'beyond': line.final_beyond * sg,
                    'beyond_5y': line.amount_beyond_5y * sg,
                }
                for key in totals:
                    totals[key] += row[key]
                rows.append(row)
            groups.append({'label': label, 'rows': rows, 'totals': totals})
        return groups

    def action_print(self):
        return self.env.ref('abc_l10n_it_ratei_risconti.action_report_rr_run').report_action(self)

    @api.model
    def _pending_sources_count(self, company, closing_date):
        """Numero di righe/schede a cavallo di D non ancora elaborate (per gli avvisi)."""
        run = self.new({'company_id': company.id, 'closing_date': closing_date})
        booked_keys = set()
        for line in self.env['abc.rr.run.line'].search([
                ('run_id.company_id', '=', company.id),
                ('run_id.closing_date', '=', closing_date),
                ('run_id.state', '=', 'confirmed')]):
            booked_keys.add(line._source_key())
        amls = self.env['account.move.line'].search(run._source_domain())
        cards = self.env['abc.rr.card'].search(run._card_domain()).filtered(
            lambda c: not run._card_already_realized(c))
        pending = [a for a in amls if ('aml', a.id) not in booked_keys]
        pending += [c for c in cards if ('card', c.id) not in booked_keys]
        return len(pending)


class AbcRrRunLine(models.Model):
    _name = 'abc.rr.run.line'
    _description = 'Riga elaborazione ratei e risconti'
    _inherit = ['analytic.mixin']
    _order = 'rr_type, rr_account_id, date_start, id'

    run_id = fields.Many2one('abc.rr.run', string='Elaborazione', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='run_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='run_id.currency_id')
    closing_date = fields.Date(related='run_id.closing_date', store=True)
    run_state = fields.Selection(related='run_id.state', store=True, string='Stato elaborazione')
    name = fields.Char(string='Descrizione', required=True)
    aml_id = fields.Many2one('account.move.line', string='Riga contabile', index=True, ondelete='set null')
    move_id = fields.Many2one(related='aml_id.move_id', string='Documento', store=True)
    move_date = fields.Date(related='aml_id.date', string='Data documento', store=True)
    card_id = fields.Many2one('abc.rr.card', string='Scheda', index=True, ondelete='restrict')
    source_ref = fields.Char(string='Rif. fonte', required=True, index=True,
                             help='Chiave tecnica della fonte: aml,<id> oppure card,<id>.')
    rr_type = fields.Selection(RR_TYPES, string='Tipologia', required=True)
    account_id = fields.Many2one('account.account', string='Conto di costo/ricavo', required=True)
    rr_account_id = fields.Many2one('account.account', string='Conto rateo/risconto')
    rr_long_account_id = fields.Many2one('account.account', string='Conto oltre 12 mesi')
    partner_id = fields.Many2one('res.partner', string='Partner')
    base_amount = fields.Monetary(string='Imponibile')
    date_start = fields.Date(string='Data inizio')
    date_end = fields.Date(string='Data fine')
    days_total = fields.Integer(string='Giorni totali')
    days_rr = fields.Integer(string='Giorni rateo/risconto')
    days_competence = fields.Integer(string='Gg competenza esercizio', compute='_compute_days_competence', store=True)
    calc_amount = fields.Monetary(string='Rateo/Risconto calcolato', readonly=True)
    calc_within = fields.Monetary(string='Calcolata entro 12 mesi', readonly=True)
    calc_beyond = fields.Monetary(string='Calcolata oltre 12 mesi', readonly=True)
    amount = fields.Monetary(string='Rateo/Risconto alla data')
    final_within = fields.Monetary(string='Entro 12 mesi', compute='_compute_final_split', store=True)
    final_beyond = fields.Monetary(string='Oltre 12 mesi', compute='_compute_final_split', store=True)
    amount_beyond_5y = fields.Monetary(string='Di cui oltre 5 anni', readonly=True)
    competence_amount = fields.Monetary(string='Competenza esercizio', compute='_compute_days_competence', store=True)
    long_account_needed = fields.Boolean(compute='_compute_final_split', store=True)
    full_period = fields.Boolean(string='100% del periodo', readonly=True)
    adjustment = fields.Boolean(string='Rettifica', readonly=True,
                                help='Riga di rettifica di una quota gia elaborata in una precedente elaborazione.')
    excluded = fields.Boolean(string='Escludi')
    edit_note = fields.Char(string='Nota di modifica')
    fingerprint = fields.Char(readonly=True, copy=False)
    source_changed = fields.Boolean(string='Fonte modificata', compute='_compute_source_changed')
    tax_date_start = fields.Date(string='Inizio periodo fiscale')
    tax_date_end = fields.Date(string='Fine periodo fiscale')

    @api.constrains('rr_type', 'rr_account_id', 'rr_long_account_id')
    def _check_prefix(self):
        for line in self:
            asset = line.rr_type in ('rateo_attivo', 'risconto_attivo')
            line.company_id._abc_rr_check_account_prefix(line.rr_account_id, asset)
            line.company_id._abc_rr_check_account_prefix(line.rr_long_account_id, asset)

    @api.depends('date_start', 'date_end', 'days_total', 'base_amount', 'adjustment',
                 'run_id.closing_date', 'run_id.company_id')
    def _compute_days_competence(self):
        """Giorni e quota di competenza del solo esercizio che si chiude a D
        (non cumulati dall'inizio del periodo)."""
        for line in self:
            closing = line.run_id.closing_date
            if line.adjustment or not (closing and line.date_start and line.date_end and line.days_total):
                line.days_competence = 0
                line.competence_amount = 0.0
                continue
            company = line.run_id.company_id
            fy_start = fields.Date.to_date(company.compute_fiscalyear_dates(closing)['date_from'])
            days = days_between(line.date_start, line.date_end, fy_start, closing)
            currency = line.currency_id or company.currency_id
            line.days_competence = days
            line.competence_amount = currency.round(line.base_amount * days / line.days_total)

    @api.depends('amount', 'calc_amount', 'calc_beyond', 'calc_within')
    def _compute_final_split(self):
        for line in self:
            currency = line.currency_id or self.env.company.currency_id
            if line.amount == line.calc_amount:
                within, beyond = line.calc_within, line.calc_beyond
            else:
                within, beyond = split_final(line.amount, line.calc_amount, line.calc_beyond,
                                             round_fn=currency.round)
            line.final_within = within
            line.final_beyond = beyond
            line.long_account_needed = not float_is_zero(beyond, precision_rounding=currency.rounding)

    def _compute_source_changed(self):
        for line in self:
            if line.run_state != 'confirmed' or not line.fingerprint:
                line.source_changed = False
            elif line.card_id:
                line.source_changed = line.fingerprint != self._fingerprint_card(line.card_id)
            elif line.source_ref.startswith('aml,'):
                aml = line.aml_id
                line.source_changed = (not aml) or line.fingerprint != self._fingerprint_aml(aml)
            else:
                line.source_changed = False

    def _natural_sign(self):
        """Segno del saldo 'normale' della fonte: costi positivi, ricavi negativi."""
        self.ensure_one()
        return 1 if self.rr_type in ('rateo_passivo', 'risconto_attivo') else -1

    def _source_key(self):
        self.ensure_one()
        kind, rid = self.source_ref.split(',')
        return (kind, int(rid))

    @api.model
    def _fingerprint_aml(self, aml):
        raw = '|'.join(str(x) for x in (
            aml.account_id.id, aml.balance, aml.deferred_start_date, aml.deferred_end_date,
            aml.parent_state, aml.date))
        return hashlib.sha1(raw.encode()).hexdigest()

    @api.model
    def _fingerprint_card(self, card):
        raw = '|'.join(str(x) for x in (
            card.account_id.id, card.amount, card.date_start, card.date_end, card.state, card.rr_type))
        return hashlib.sha1(raw.encode()).hexdigest()

    def _store_fingerprint(self):
        for line in self:
            if line.card_id:
                line.fingerprint = self._fingerprint_card(line.card_id)
            elif line.aml_id:
                line.fingerprint = self._fingerprint_aml(line.aml_id)

    @api.model
    def _prepare_vals(self, run, cand, res, amount, within, beyond):
        rr_account, long_account = self.env['abc.rr.account.map']._get_accounts(
            run.company_id, cand['rr_type'], cand['account'])
        if cand['forced_rr_account']:
            rr_account = cand['forced_rr_account']
        if rr_kind(cand['rr_type']) == 'rateo':
            long_account = self.env['account.account']
        source_ref = 'aml,%s' % cand['aml'].id if cand['aml'] else 'card,%s' % cand['card'].id
        return {
            'run_id': run.id,
            'name': cand['label'],
            'aml_id': cand['aml'].id or False,
            'card_id': cand['card'].id or False,
            'source_ref': source_ref,
            'rr_type': cand['rr_type'],
            'account_id': cand['account'].id,
            'rr_account_id': rr_account.id or False,
            'rr_long_account_id': long_account.id or False,
            'partner_id': cand['partner'].id or False,
            'analytic_distribution': cand['analytic'],
            'base_amount': cand['balance'],
            'date_start': cand['start'],
            'date_end': cand['end'],
            'days_total': res['days_total'],
            'days_rr': res['days_rr'],
            'calc_amount': amount,
            'calc_within': within,
            'calc_beyond': beyond,
            'amount': amount,
            'amount_beyond_5y': res['amount_beyond_5y'],
            'full_period': res['full'],
            'fingerprint': cand['fingerprint'],
            'tax_date_start': cand['tax_start'],
            'tax_date_end': cand['tax_end'],
        }

    def _prepare_reversal_vals(self, run, prev):
        """Fonte non piu' valida (annullata, rimessa in bozza, date tolte): quota contraria."""
        self.ensure_one()
        return {
            'run_id': run.id,
            'name': self.env._("Rettifica: %s", self.name),
            'aml_id': self.aml_id.id or False,
            'card_id': self.card_id.id or False,
            'source_ref': self.source_ref,
            'rr_type': self.rr_type,
            'account_id': self.account_id.id,
            'rr_account_id': self.rr_account_id.id or False,
            'rr_long_account_id': self.rr_long_account_id.id or False,
            'partner_id': self.partner_id.id or False,
            'analytic_distribution': self.analytic_distribution,
            'base_amount': 0.0,
            'date_start': self.date_start,
            'date_end': self.date_end,
            'days_total': self.days_total,
            'days_rr': 0,
            'calc_amount': -prev['posted'],
            'calc_within': -prev['posted_within'],
            'calc_beyond': -prev['posted_beyond'],
            'amount': -prev['posted'],
            'amount_beyond_5y': -prev['beyond_5y'],
            'adjustment': True,
        }

    def write(self, vals):
        if any(line.run_id.state != 'draft' for line in self) and \
                set(vals) & {'amount', 'excluded', 'rr_account_id', 'rr_long_account_id', 'analytic_distribution'}:
            raise UserError(self.env._("Le righe di un'elaborazione confermata non si modificano."))
        if 'amount' in vals and not vals.get('edit_note'):
            for line in self:
                if line.currency_id.compare_amounts(vals['amount'], line.calc_amount) != 0 and not line.edit_note:
                    raise UserError(self.env._(
                        "Indicare una nota di modifica per la riga %s prima di cambiare la quota.", line.name))
        return super().write(vals)

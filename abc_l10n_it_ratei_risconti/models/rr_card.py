# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .rr_compute import COST_RR_TYPES, RR_TYPES, entry_sign


class AbcRrCard(models.Model):
    _name = 'abc.rr.card'
    _description = 'Scheda rateo/risconto'
    _inherit = ['mail.thread', 'analytic.mixin']
    _order = 'date_start desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Descrizione', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Societa', required=True, index=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    card_type = fields.Selection(
        [('manual', 'Manuale'), ('legacy', 'Pregresso')],
        string='Tipo scheda', required=True, default='manual', tracking=True)
    rr_type = fields.Selection(RR_TYPES, string='Tipologia', required=True, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Partner', check_company=True)
    account_id = fields.Many2one(
        'account.account', string='Conto di costo/ricavo', required=True,
        check_company=True, tracking=True)
    rr_account_id = fields.Many2one(
        'account.account', string='Conto rateo/risconto', check_company=True,
        help='Se vuoto: eccezione per conto o conto delle impostazioni.')
    amount = fields.Monetary(
        string='Imponibile del periodo', required=True, tracking=True,
        help="Importo totale del periodo, positivo. Il segno contabile dipende dalla tipologia.")
    date_start = fields.Date(string='Data inizio', required=True, tracking=True)
    date_end = fields.Date(string='Data fine', required=True, tracking=True)
    tax_date_start = fields.Date(string='Inizio periodo fiscale')
    tax_date_end = fields.Date(string='Fine periodo fiscale')
    state = fields.Selection(
        [('draft', 'Bozza'), ('active', 'Attiva'), ('closed', 'Chiusa')],
        string='Stato', default='draft', required=True, tracking=True)
    note = fields.Text(string='Note')

    # Pregresso
    legacy_closing_date = fields.Date(
        string='Chiusura esercizio vecchio gestionale',
        help="Data dell'ultima chiusura in cui il rateo/risconto e' stato rilevato fuori da Odoo.")
    legacy_amount = fields.Monetary(
        string='Importo rilevato alla chiusura',
        help='Importo positivo del rateo/risconto rilevato nel vecchio gestionale.')
    legacy_storno_done = fields.Boolean(
        string='Storno gia registrato',
        help="Selezionare se lo storno e' gia' entrato con l'import dei saldi di apertura.")
    legacy_storno_move_id = fields.Many2one(
        'account.move', string='Scrittura di storno pregresso', readonly=True, copy=False)

    run_line_ids = fields.One2many('abc.rr.run.line', 'card_id', string='Righe elaborate')

    @api.constrains('date_start', 'date_end', 'tax_date_start', 'tax_date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_end < rec.date_start:
                raise ValidationError(self.env._("La data fine precede la data inizio."))
            if bool(rec.tax_date_start) != bool(rec.tax_date_end):
                raise ValidationError(self.env._("Indicare entrambe le date del periodo fiscale."))
            if rec.tax_date_start and rec.tax_date_end < rec.tax_date_start:
                raise ValidationError(self.env._("Il periodo fiscale termina prima di iniziare."))

    @api.constrains('amount', 'legacy_amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0 or rec.legacy_amount < 0:
                raise ValidationError(self.env._("Gli importi della scheda vanno indicati positivi."))

    @api.constrains('rr_type', 'rr_account_id')
    def _check_prefix(self):
        for rec in self:
            rec.company_id._abc_rr_check_account_prefix(
                rec.rr_account_id, rec.rr_type in ('rateo_attivo', 'risconto_attivo'))

    def _signed_base(self):
        """Saldo contabile equivalente: costo positivo, ricavo negativo."""
        self.ensure_one()
        return self.amount if self.rr_type in COST_RR_TYPES else -self.amount

    def action_activate(self):
        self.write({'state': 'active'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_generate_legacy_storno(self):
        """Storno alla data di apertura del rateo/risconto rilevato nel vecchio gestionale."""
        for card in self:
            if card.card_type != 'legacy' or card.legacy_storno_done or card.legacy_storno_move_id:
                raise UserError(self.env._("Storno non necessario per la scheda %s.", card.name))
            if not card.legacy_closing_date or not card.legacy_amount:
                raise UserError(self.env._(
                    "Indicare data di chiusura e importo del vecchio gestionale (scheda %s).", card.name))
            company = card.company_id
            journal = company.abc_rr_journal_id
            if not journal:
                raise UserError(self.env._("Configurare il registro ratei e risconti nelle impostazioni."))
            rr_account = card.rr_account_id or self.env['abc.rr.account.map']._get_accounts(
                company, card.rr_type, card.account_id)[0]
            if not rr_account:
                raise UserError(self.env._("Nessun conto configurato per la tipologia della scheda %s.", card.name))
            sign = entry_sign(card.rr_type)
            base = card.legacy_amount if card.rr_type in COST_RR_TYPES else -card.legacy_amount
            # storno = inverso dell'assestamento: conto d'origine -sign*q, conto rr +sign*q
            origin_bal = -sign * base
            rr_bal = sign * base
            label = self.env._("Storno pregresso: %s", card.name)
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': journal.id,
                'company_id': company.id,
                'date': card.legacy_closing_date + relativedelta(days=1),
                'ref': label,
                'line_ids': [
                    Command.create({
                        'name': label,
                        'account_id': card.account_id.id,
                        'partner_id': card.partner_id.id,
                        'debit': max(origin_bal, 0.0),
                        'credit': max(-origin_bal, 0.0),
                        'analytic_distribution': card.analytic_distribution,
                    }),
                    Command.create({
                        'name': label,
                        'account_id': rr_account.id,
                        'partner_id': card.partner_id.id,
                        'debit': max(rr_bal, 0.0),
                        'credit': max(-rr_bal, 0.0),
                    }),
                ],
            })
            move.action_post()
            card.write({'legacy_storno_move_id': move.id, 'legacy_storno_done': True})
        return True

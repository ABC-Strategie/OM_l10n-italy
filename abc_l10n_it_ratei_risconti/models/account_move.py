# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    abc_rr_run_id = fields.Many2one(
        'abc.rr.run', string='Elaborazione ratei e risconti', readonly=True, copy=False, index=True)

    def write(self, vals):
        protected = {'line_ids', 'date', 'journal_id'}
        if not self.env.context.get('abc_rr_allow') and protected & set(vals):
            locked = self.filtered(lambda m: m.abc_rr_run_id and m.abc_rr_run_id.state == 'confirmed'
                                   and m.state == 'posted')
            if locked:
                raise UserError(self.env._(
                    "Le scritture generate dal modulo Ratei e risconti non si modificano a mano: "
                    "annullare l'elaborazione %s.", ', '.join(locked.mapped('abc_rr_run_id.name'))))
        return super().write(vals)

    def _abc_rr_check_generated(self):
        if self.env.context.get('abc_rr_allow'):
            return
        locked = self.filtered(lambda m: m.abc_rr_run_id and m.abc_rr_run_id.state == 'confirmed')
        if locked:
            raise UserError(self.env._(
                "Le scritture generate dal modulo Ratei e risconti si annullano solo annullando "
                "l'elaborazione %s.", ', '.join(locked.mapped('abc_rr_run_id.name'))))

    def button_draft(self):
        self._abc_rr_check_generated()
        return super().button_draft()

    def button_cancel(self):
        self._abc_rr_check_generated()
        return super().button_cancel()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    abc_rr_tax_date_start = fields.Date(
        string='Inizio periodo fiscale', copy=True,
        help='Solo leasing: periodo di deduzione fiscale, se diverso dalla competenza civilistica.')
    abc_rr_tax_date_end = fields.Date(string='Fine periodo fiscale', copy=True)
    abc_rr_line_ids = fields.One2many('abc.rr.run.line', 'aml_id', string='Ratei e risconti elaborati')
    abc_rr_processed_date = fields.Date(
        string='Elaborato al', compute='_compute_abc_rr_processed_date',
        help="Ultima data di chiusura in cui la riga e' entrata in un'elaborazione confermata.")

    @api.depends('abc_rr_line_ids.run_state', 'abc_rr_line_ids.closing_date')
    def _compute_abc_rr_processed_date(self):
        for line in self:
            dates = line.abc_rr_line_ids.filtered(lambda l: l.run_state == 'confirmed').mapped('closing_date')
            line.abc_rr_processed_date = max(dates) if dates else False

    @api.constrains('deferred_start_date', 'deferred_end_date', 'abc_rr_tax_date_start', 'abc_rr_tax_date_end')
    def _check_abc_rr_dates(self):
        for line in self:
            if line.deferred_start_date and line.deferred_end_date \
                    and line.deferred_end_date < line.deferred_start_date:
                raise ValidationError(self.env._(
                    "Riga '%s': la data fine competenza precede la data inizio.", line.name or ''))
            if bool(line.abc_rr_tax_date_start) != bool(line.abc_rr_tax_date_end):
                raise ValidationError(self.env._(
                    "Riga '%s': indicare entrambe le date del periodo fiscale.", line.name or ''))
            if line.abc_rr_tax_date_start and line.abc_rr_tax_date_end < line.abc_rr_tax_date_start:
                raise ValidationError(self.env._(
                    "Riga '%s': il periodo fiscale termina prima di iniziare.", line.name or ''))

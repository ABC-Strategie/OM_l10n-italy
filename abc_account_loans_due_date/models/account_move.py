# -*- coding: utf-8 -*-
from odoo import api, models

# Impostata da account.loan.action_confirm: solo in quella chiamata le
# scritture con generating_loan_line_id vengono datate alla scadenza rata.
DUE_DATE_CTX = 'abc_loan_move_due_date'


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get(DUE_DATE_CTX):
            line_ids = {vals['generating_loan_line_id'] for vals in vals_list if vals.get('generating_loan_line_id')}
            due_dates = {line.id: line.date for line in self.env['account.loan.line'].browse(line_ids)}
            # account_loans calcola la data a fine mese (o al primo del mese
            # successivo per lo storno): la sostituiamo con la scadenza rata.
            vals_list = [
                dict(vals, date=due_dates[vals['generating_loan_line_id']])
                if vals.get('generating_loan_line_id') in due_dates else vals
                for vals in vals_list
            ]
        return super().create(vals_list)

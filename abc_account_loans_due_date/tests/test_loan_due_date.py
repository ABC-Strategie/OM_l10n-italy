# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account_loans.models.account_loan import AccountLoan as AccountLoanBase


@tagged('post_install', '-at_install')
class TestLoanDueDate(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loan_journal = cls.env['account.journal'].search([
            ('company_id', '=', cls.company.id),
            ('type', '=', 'general'),
            ('id', '!=', cls.company.currency_exchange_journal_id.id),
        ], limit=1)
        cls.long_term_account = cls.env['account.account'].search([
            ('company_ids', '=', cls.company.id),
            ('account_type', '=', 'liability_non_current'),
        ], limit=1)
        cls.short_term_account = cls.env['account.account'].search([
            ('company_ids', '=', cls.company.id),
            ('account_type', '=', 'liability_current'),
        ], limit=1)
        cls.expense_account = cls.env['account.account'].search([
            ('company_ids', '=', cls.company.id),
            ('account_type', '=', 'expense'),
            ('id', '!=', cls.company.account_journal_early_pay_discount_loss_account_id.id),
        ], limit=1)

    def _create_loan(self, first_due_date='2024-01-15', duration=12):
        return self.env['account.loan'].create({
            'name': 'Finanziamento test',
            'date': '2024-01-01',
            'duration': duration,
            'amount_borrowed': 12_000,
            'interest': 1_200,
            'journal_id': self.loan_journal.id,
            'long_term_account_id': self.long_term_account.id,
            'short_term_account_id': self.short_term_account.id,
            'expense_account_id': self.expense_account.id,
            'line_ids': [
                Command.create({
                    'date': fields.Date.to_date(first_due_date) + relativedelta(months=month),
                    'principal': 12_000 / duration,
                    'interest': 1_200 / duration,
                }) for month in range(duration)
            ],
        })

    def _assert_moves_on_due_date(self, moves):
        for move in moves:
            self.assertEqual(move.date, move.generating_loan_line_id.date, move.ref)

    @freeze_time('2024-07-31')
    def test_confirm_dates_moves_on_due_date(self):
        loan = self._create_loan()
        loan.action_confirm()

        moves = loan.line_ids.generated_move_ids
        payment_moves = moves.filtered('is_loan_payment_move')
        reversal_moves = moves.filtered('reversed_entry_id')
        self.assertEqual(len(payment_moves), 12)
        self.assertEqual(len(reversal_moves), 11)
        self.assertEqual(len(moves - payment_moves - reversal_moves), 11)
        self._assert_moves_on_due_date(moves)

        # Confermate solo le scritture con scadenza fino a oggi (15/01 -> 15/07)
        today = fields.Date.to_date('2024-07-31')
        self.assertTrue(all(m.state == 'posted' for m in moves if m.date <= today))
        self.assertTrue(all(m.state == 'draft' for m in moves if m.date > today))
        self.assertEqual(len(payment_moves.filtered(lambda m: m.state == 'posted')), 7)

    @freeze_time('2024-07-31')
    def test_realign_existing_loan(self):
        loan = self._create_loan()
        # Prestito confermato con le date standard (fine mese / primo del mese successivo)
        AccountLoanBase.action_confirm(loan)
        moves = loan.line_ids.generated_move_ids
        self.assertFalse(any(m.date == m.generating_loan_line_id.date for m in moves))
        # Scrittura con data futura confermata in anticipo: auto_post resta 'at_date'
        future_move = moves.filtered(lambda m: m.state == 'draft' and m.is_loan_payment_move)[:1]
        future_move.auto_post = 'no'
        future_move.action_post()
        future_move.auto_post = 'at_date'
        states = {move: move.state for move in moves}
        reversed_entries = {move: move.reversed_entry_id for move in moves if move.reversed_entry_id}

        loan.action_abc_realign_move_dates()

        self._assert_moves_on_due_date(moves)
        self.assertEqual({move: move.state for move in moves}, states)
        self.assertEqual({move: move.reversed_entry_id for move in moves if move.reversed_entry_id}, reversed_entries)
        for move in moves.filtered(lambda m: m.state == 'posted'):
            self.assertTrue(move._sequence_matches_date(), move.name)
        self.assertFalse(moves.line_ids.filtered('reconciled'))
        self.assertRecordValues(future_move, [{'state': 'posted', 'auto_post': 'at_date'}])

    @freeze_time('2024-07-31')
    def test_realign_skips_locked_period(self):
        loan = self._create_loan()
        AccountLoanBase.action_confirm(loan)
        lock_date = fields.Date.to_date('2024-03-31')
        self.company.fiscalyear_lock_date = lock_date
        moves = loan.line_ids.generated_move_ids
        # Bloccate anche quelle (es. storno di marzo, oggi al 01/04) che finirebbero nel periodo chiuso
        locked = moves.filtered(lambda m: m.generating_loan_line_id.date <= lock_date)
        locked_dates = {move: move.date for move in locked}

        action = loan.action_abc_realign_move_dates()

        self.assertEqual({move: move.date for move in locked}, locked_dates)
        self._assert_moves_on_due_date(moves - locked)
        self.assertEqual(action['params']['type'], 'warning')

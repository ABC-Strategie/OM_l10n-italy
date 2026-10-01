# -*- coding: utf-8 -*-
from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install', 'abc_rr')
class TestRrFlow(AccountTestInvoicingCommon):
    """Elaborazione completa: calcolo, conferma, storno, integrativa, annullamento."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'fiscalyear_last_day': 31, 'fiscalyear_last_month': '12'})
        Account = cls.env['account.account']
        cls.acc_cost = Account.create({'code': 'X42010', 'name': 'Assicurazioni', 'account_type': 'expense'})
        cls.acc_leasing = Account.create({'code': 'X42020', 'name': 'Canoni leasing', 'account_type': 'expense'})
        cls.acc_other = Account.create({'code': 'X25010', 'name': 'Debiti diversi', 'account_type': 'liability_current'})
        cls.acc_ra = Account.create({'code': '19019901', 'name': 'Ratei attivi test', 'account_type': 'asset_current'})
        cls.acc_ri_a = Account.create({'code': '19029901', 'name': 'Risconti attivi test', 'account_type': 'asset_current'})
        cls.acc_ri_a_long = Account.create({'code': '19029902', 'name': 'Risconti attivi pluriennali test', 'account_type': 'asset_current'})
        cls.acc_rp = Account.create({'code': '27019901', 'name': 'Ratei passivi test', 'account_type': 'liability_current'})
        cls.acc_ri_p = Account.create({'code': '27029901', 'name': 'Risconti passivi test', 'account_type': 'liability_current'})
        cls.journal = cls.env['account.journal'].create({'name': 'Ratei e risconti test', 'code': 'RRTST', 'type': 'general'})
        cls.company.write({
            'abc_rr_journal_id': cls.journal.id,
            'abc_rr_accrued_income_account_id': cls.acc_ra.id,
            'abc_rr_accrued_expense_account_id': cls.acc_rp.id,
            'abc_rr_prepaid_expense_account_id': cls.acc_ri_a.id,
            'abc_rr_deferred_income_account_id': cls.acc_ri_p.id,
            'abc_rr_prepaid_expense_long_account_id': cls.acc_ri_a_long.id,
        })
        cls.misc = cls.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', cls.company.id), ('id', '!=', cls.journal.id)], limit=1)

    def _entry(self, move_date, account, amount, start, end, name='Test'):
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.misc.id,
            'date': move_date,
            'line_ids': [
                Command.create({'name': name, 'account_id': account.id, 'debit': amount, 'credit': 0.0,
                                'deferred_start_date': start, 'deferred_end_date': end}),
                Command.create({'name': name, 'account_id': self.acc_other.id, 'debit': 0.0, 'credit': amount}),
            ],
        })
        move.action_post()
        return move

    def _run(self, closing):
        run = self.env['abc.rr.run'].create({'company_id': self.company.id, 'closing_date': closing})
        run.action_compute()
        return run

    def test_native_disabled(self):
        self.assertEqual(self.company.generate_deferred_expense_entries_method, 'manual')
        self.company.generate_deferred_expense_entries_method = 'on_validation'
        self.assertEqual(self.company.generate_deferred_expense_entries_method, 'manual')

    def test_risconto_confirm_and_storno(self):
        self._entry(date(2025, 10, 1), self.acc_cost, 1200.0, date(2025, 10, 1), date(2026, 9, 30), 'Assicurazione')
        run = self._run(date(2025, 12, 31))
        self.assertEqual(len(run.line_ids), 1)
        line = run.line_ids
        self.assertEqual(line.rr_type, 'risconto_attivo')
        self.assertAlmostEqual(line.amount, 897.53)
        run.action_confirm()
        self.assertEqual(run.state, 'confirmed')
        self.assertEqual(run.move_id.date, date(2025, 12, 31))
        self.assertEqual(run.reverse_move_id.date, date(2026, 1, 1))
        rr = run.move_id.line_ids.filtered(lambda l: l.account_id == self.acc_ri_a)
        self.assertAlmostEqual(rr.debit, 897.53)
        cost = run.move_id.line_ids.filtered(lambda l: l.account_id == self.acc_cost)
        self.assertAlmostEqual(cost.credit, 897.53)
        rev = run.reverse_move_id.line_ids.filtered(lambda l: l.account_id == self.acc_ri_a)
        self.assertAlmostEqual(rev.credit, 897.53)
        # nessuna nuova proposta in un'elaborazione integrativa
        run2 = self._run(date(2025, 12, 31))
        self.assertFalse(run2.line_ids)
        # annullamento: scritture annullate, elaborazione in bozza
        run2.unlink()
        run.action_cancel()
        self.assertEqual(run.state, 'draft')

    def test_rateo_next_year_and_supplement(self):
        self._entry(date(2026, 2, 15), self.acc_cost, 300.0, date(2025, 11, 1), date(2026, 1, 31), 'Bolletta')
        run = self._run(date(2025, 12, 31))
        self.assertEqual(run.line_ids.rr_type, 'rateo_passivo')
        self.assertAlmostEqual(run.line_ids.amount, 198.91)
        run.action_confirm()
        rr = run.move_id.line_ids.filtered(lambda l: l.account_id == self.acc_rp)
        self.assertAlmostEqual(rr.credit, 198.91)
        # arriva una nuova fattura dopo la conferma: l'integrativa propone solo quella
        self._entry(date(2026, 3, 10), self.acc_cost, 620.0, date(2025, 12, 1), date(2026, 1, 31), 'Manutenzione')
        run2 = self._run(date(2025, 12, 31))
        self.assertEqual(len(run2.line_ids), 1)
        self.assertAlmostEqual(run2.line_ids.amount, 310.0)

    def test_leasing_split_long_account(self):
        self._entry(date(2025, 7, 1), self.acc_leasing, 12000.0, date(2025, 7, 1), date(2030, 6, 30), 'Maxicanone')
        run = self._run(date(2025, 12, 31))
        line = run.line_ids
        self.assertAlmostEqual(line.amount, 10790.80)
        self.assertAlmostEqual(line.final_within, 2398.69)
        self.assertAlmostEqual(line.final_beyond, 8392.11)
        run.action_confirm()
        short = run.move_id.line_ids.filtered(lambda l: l.account_id == self.acc_ri_a)
        long_ = run.move_id.line_ids.filtered(lambda l: l.account_id == self.acc_ri_a_long)
        self.assertAlmostEqual(short.debit, 2398.69)
        self.assertAlmostEqual(long_.debit, 8392.11)
        # competenza del solo esercizio: 184 giorni nel 2025, 365 nel 2026 (non cumulati)
        self.assertEqual(line.days_competence, 184)
        self.assertAlmostEqual(line.competence_amount, 1209.20)
        run26 = self._run(date(2026, 12, 31))
        line26 = run26.line_ids.filtered(lambda l: l.aml_id == line.aml_id)
        self.assertEqual(line26.days_competence, 365)
        self.assertAlmostEqual(line26.competence_amount, 2398.69)

    def test_rateo_card_not_repeated(self):
        card = self.env['abc.rr.card'].create({
            'name': 'Interessi mutuo', 'card_type': 'manual', 'rr_type': 'rateo_passivo',
            'account_id': self.acc_cost.id, 'amount': 1810.0,
            'date_start': date(2025, 12, 1), 'date_end': date(2026, 5, 31),
        })
        card.action_activate()
        run = self._run(date(2025, 12, 31))
        self.assertAlmostEqual(run.line_ids.amount, 308.30)
        run.action_confirm()
        # alla chiusura successiva il periodo e' finito ed e' gia' stato registrato: nessuna proposta
        run26 = self._run(date(2026, 12, 31))
        self.assertFalse(run26.line_ids.filtered(lambda l: l.card_id == card))
        # le scritture generate non si rimettono in bozza a mano
        with self.assertRaises(UserError):
            run.move_id.button_draft()

    def test_legacy_card(self):
        card = self.env['abc.rr.card'].create({
            'name': 'Canone software', 'card_type': 'legacy', 'rr_type': 'risconto_attivo',
            'account_id': self.acc_cost.id, 'amount': 6000.0,
            'date_start': date(2024, 7, 1), 'date_end': date(2026, 6, 30),
            'legacy_closing_date': date(2024, 12, 31), 'legacy_amount': 4487.67,
        })
        card.action_activate()
        card.action_generate_legacy_storno()
        storno = card.legacy_storno_move_id
        self.assertEqual(storno.date, date(2025, 1, 1))
        self.assertAlmostEqual(storno.line_ids.filtered(lambda l: l.account_id == self.acc_cost).debit, 4487.67)
        run = self._run(date(2025, 12, 31))
        self.assertAlmostEqual(run.line_ids.amount, 1487.67)

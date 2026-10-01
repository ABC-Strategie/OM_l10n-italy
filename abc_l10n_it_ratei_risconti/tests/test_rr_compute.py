# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests import TransactionCase, tagged

from ..models.rr_compute import classify, compute_quota, split_final

D2025 = date(2025, 12, 31)


@tagged('post_install', '-at_install', 'abc_rr')
class TestRrCompute(TransactionCase):
    """Casi della sezione 9 della specifica (solo calcolo)."""

    def q(self, balance, start, end, closing, rr_type):
        return compute_quota(balance, start, end, closing, rr_type)

    def test_01_risconto_attivo(self):
        res = self.q(1200.0, date(2025, 10, 1), date(2026, 9, 30), D2025, 'risconto_attivo')
        self.assertEqual(res['days_total'], 365)
        self.assertEqual(res['days_rr'], 273)
        self.assertAlmostEqual(res['amount'], 897.53)
        self.assertAlmostEqual(res['amount_beyond'], 0.0)

    def test_02_rateo_passivo(self):
        self.assertEqual(classify(date(2026, 2, 15), D2025, 'cost'), 'rateo_passivo')
        res = self.q(300.0, date(2025, 11, 1), date(2026, 1, 31), D2025, 'rateo_passivo')
        self.assertEqual((res['days_total'], res['days_rr']), (92, 61))
        self.assertAlmostEqual(res['amount'], 198.91)

    def test_03_rateo_scheda(self):
        res = self.q(1810.0, date(2025, 12, 1), date(2026, 5, 31), D2025, 'rateo_passivo')
        self.assertEqual((res['days_total'], res['days_rr']), (182, 31))
        self.assertAlmostEqual(res['amount'], 308.30)

    def test_04_risconto_passivo(self):
        self.assertEqual(classify(date(2025, 12, 1), D2025, 'income'), 'risconto_passivo')
        res = self.q(-2400.0, date(2025, 12, 1), date(2026, 11, 30), D2025, 'risconto_passivo')
        self.assertEqual(res['days_rr'], 334)
        self.assertAlmostEqual(res['amount'], -2196.16)

    def test_05_rateo_attivo(self):
        res = self.q(-450.0, date(2025, 10, 1), date(2026, 3, 31), D2025, 'rateo_attivo')
        self.assertEqual((res['days_total'], res['days_rr']), (182, 92))
        self.assertAlmostEqual(res['amount'], -227.47)

    def test_06_leasing_pluriennale(self):
        res = self.q(12000.0, date(2025, 7, 1), date(2030, 6, 30), D2025, 'risconto_attivo')
        self.assertEqual((res['days_total'], res['days_rr']), (1826, 1642))
        self.assertAlmostEqual(res['amount'], 10790.80)
        self.assertAlmostEqual(res['amount_within'], 2398.69)
        self.assertAlmostEqual(res['amount_beyond'], 8392.11)
        self.assertAlmostEqual(res['amount_beyond_5y'], 0.0)
        res26 = self.q(12000.0, date(2025, 7, 1), date(2030, 6, 30), date(2026, 12, 31), 'risconto_attivo')
        self.assertAlmostEqual(res26['amount'], 8392.11)

    def test_06bis_quota_fiscale(self):
        # quota fiscale 2025 su periodo 01/07/2025-31/12/2027 (914 giorni, 184 nel 2025)
        self.assertAlmostEqual(round(12000.0 * 184 / 914, 2), 2415.75)
        civil_2025 = round(12000.0 - 10790.80, 2)
        self.assertAlmostEqual(civil_2025, 1209.20)
        self.assertAlmostEqual(round(2415.75 - civil_2025, 2), 1206.55)

    def test_07_nota_credito(self):
        res = self.q(-200.0, date(2025, 10, 1), date(2026, 9, 30), D2025, 'risconto_attivo')
        self.assertAlmostEqual(res['amount'], -149.59)
        self.assertAlmostEqual(round(897.53 + res['amount'], 2), 747.94)

    def test_08_esercizio_non_solare(self):
        res = self.q(3650.0, date(2026, 4, 1), date(2027, 3, 31), date(2026, 6, 30), 'risconto_attivo')
        self.assertEqual(res['days_rr'], 274)
        self.assertAlmostEqual(res['amount'], 2740.00)

    def test_09_pregresso(self):
        res24 = self.q(6000.0, date(2024, 7, 1), date(2026, 6, 30), date(2024, 12, 31), 'risconto_attivo')
        self.assertEqual(res24['days_total'], 730)
        self.assertAlmostEqual(res24['amount'], 4487.67)
        res25 = self.q(6000.0, date(2024, 7, 1), date(2026, 6, 30), D2025, 'risconto_attivo')
        self.assertAlmostEqual(res25['amount'], 1487.67)

    def test_11_integrativa_quota(self):
        res = self.q(620.0, date(2025, 12, 1), date(2026, 1, 31), D2025, 'rateo_passivo')
        self.assertEqual((res['days_total'], res['days_rr']), (62, 31))
        self.assertAlmostEqual(res['amount'], 310.00)

    def test_casi_limite(self):
        # periodo tutto nell'esercizio: nessuna quota
        res = self.q(100.0, date(2025, 3, 1), date(2025, 6, 30), D2025, 'risconto_attivo')
        self.assertAlmostEqual(res['amount'], 0.0)
        # periodo tutto dopo D: risconto del 100%
        res = self.q(100.0, date(2026, 1, 1), date(2026, 3, 31), D2025, 'risconto_attivo')
        self.assertTrue(res['full'])
        self.assertAlmostEqual(res['amount'], 100.0)
        # date invertite: nessun calcolo
        self.assertIsNone(self.q(100.0, date(2026, 3, 1), date(2026, 1, 1), D2025, 'risconto_attivo'))
        # ripartizione di una quota corretta a mano
        self.assertEqual(split_final(5000.0, 10790.80, 8392.11), (1111.45, 3888.55))

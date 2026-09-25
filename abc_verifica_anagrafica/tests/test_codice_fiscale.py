# -*- coding: utf-8 -*-
"""Test dell'algoritmo interno di controllo formale (nessuna dipendenza
dall'ORM). I vettori sono stati verificati contro python-stdnum 2.2."""
from odoo.tests import BaseCase, tagged

from ..tools import codice_fiscale as cf


@tagged('post_install', '-at_install', 'abc_va')
class TestCodiceFiscale(BaseCase):

    VALID = [
        'TLEMRA83A01H501T',   # esempio della specifica AdE
        'RSSMRA85T10A562S',
        'MRTMTT91D08F205J',   # esempio del constraint l10n_it_edi
    ]

    # Varianti omocodiche di RSSMRA85T10A562S, sostituzione progressiva da destra
    OMOCODICI = [
        'RSSMRA85T10A56NH',
        'RSSMRA85T10A5SNT',
        'RSSMRA85T10ARSNO',
        'RSSMRA85T1LARSNR',
        'RSSMRA85TMLARSNC',
        'RSSMRA8RTMLARSNO',
        'RSSMRAURTMLARSNL',
    ]

    def test_valid_codes(self):
        for code in self.VALID:
            ok, reason, _msg = cf.validate(code)
            self.assertTrue(ok, code)
            self.assertIsNone(reason)
            self.assertFalse(cf.is_omocodico(code))

    def test_omocodia(self):
        for code in self.OMOCODICI:
            ok, reason, _msg = cf.validate(code)
            self.assertTrue(ok, f'{code}: {reason}')
            self.assertTrue(cf.is_omocodico(code))
            self.assertEqual(cf.base_code(code), 'RSSMRA85T10A562S')

    def test_normalization(self):
        self.assertTrue(cf.is_valid(' rssmra85t10a562s '))
        self.assertTrue(cf.is_valid('RSSMRA 85T10 A562S'))
        self.assertEqual(cf.normalize(None), '')

    def test_check_digit(self):
        self.assertEqual(cf.compute_check_char('RSSMRA85T10A562'), 'S')
        ok, reason, _msg = cf.validate('RSSMRA85T10A562X')
        self.assertFalse(ok)
        self.assertEqual(reason, cf.REASON_CHECK_DIGIT)

    def test_reasons(self):
        cases = {
            '': cf.REASON_EMPTY,
            None: cf.REASON_EMPTY,
            'RSSMRA85T10A562': cf.REASON_LENGTH,
            'RSSMRA85T10A562SX': cf.REASON_LENGTH,
            'RSSMRA85T10A56-S': cf.REASON_ALPHABET,
            'RSSMR185T10A562S': cf.REASON_STRUCTURE,   # cifra in posizione alfabetica
            'RSSMRA8AT10A562S': cf.REASON_STRUCTURE,   # lettera non omocodica in posizione numerica
            'RSSMRA85Z10A562S': cf.REASON_MONTH,
            'RSSMRA85T00A562S': cf.REASON_DAY,
            'RSSMRA85T35A562S': cf.REASON_DAY,
            'RSSMRA85T99A562S': cf.REASON_DAY,
        }
        for code, expected in cases.items():
            ok, reason, _msg = cf.validate(code)
            self.assertFalse(ok, repr(code))
            self.assertEqual(reason, expected, repr(code))

    def test_female_day(self):
        # giorno 41-71: donne
        first15 = 'BNCGNN70A41F205'
        code = first15 + cf.compute_check_char(first15)
        self.assertTrue(cf.is_valid(code))

    def test_partita_iva(self):
        self.assertTrue(cf.is_valid_piva('12345670546'))
        self.assertTrue(cf.is_valid_piva('IT01114601006'))
        self.assertFalse(cf.is_valid_piva('12345678901'))
        self.assertFalse(cf.is_valid_piva('00000000000'))
        self.assertFalse(cf.is_valid_piva('0111460100'))
        self.assertFalse(cf.is_valid_piva(''))

    # ------------------------------------------------------------------
    # Coerenza con cognome e nome
    # ------------------------------------------------------------------
    def test_surname_and_name_codes(self):
        self.assertEqual(cf.surname_code('Rossi'), 'RSS')
        self.assertEqual(cf.surname_code('Bianchi'), 'BNC')
        self.assertEqual(cf.surname_code('De Luca'), 'DLC')
        self.assertEqual(cf.surname_code("D'Angelo"), 'DNG')
        self.assertEqual(cf.surname_code('Fo'), 'FOX')
        self.assertEqual(cf.surname_code('Ai'), 'AIX')
        self.assertEqual(cf.name_code('Mario'), 'MRA')
        self.assertEqual(cf.name_code('Giovanna'), 'GNN')      # 4+ consonanti: 1a, 3a, 4a
        self.assertEqual(cf.name_code('Gianfranco'), 'GFR')
        self.assertEqual(cf.name_code('Anna'), 'NNA')
        self.assertEqual(cf.name_code('Al'), 'LAX')
        self.assertEqual(cf.name_code('Maria Luisa'), 'MLS')   # nomi doppi concatenati
        self.assertEqual(cf.name_code('Niccolò'), 'NCL')       # accenti rimossi

    def test_name_matches(self):
        self.assertTrue(cf.name_matches('RSSMRA85T10A562S', 'Mario Rossi')[0])
        self.assertTrue(cf.name_matches('RSSMRA85T10A562S', 'Rossi Mario')[0])
        self.assertTrue(cf.name_matches('RSSMRA85T10A562S', 'ROSSI MARIO')[0])
        self.assertTrue(cf.name_matches('MRTMTT91D08F205J', 'Matteo Marti')[0])
        self.assertTrue(cf.name_matches('BNCGNN70A41F205X', 'Giovanna Bianchi')[0])
        # cognome composto e nome doppio
        self.assertTrue(cf.name_matches('DLCMLS80A41H501X', 'Maria Luisa De Luca')[0])
        # titolo spurio tollerato
        self.assertTrue(cf.name_matches('RSSMRA85T10A562S', 'Dott. Mario Rossi')[0])
        # incoerente
        ok, expected = cf.name_matches('RSSMRA85T10A562S', 'Luigi Bianchi')
        self.assertFalse(ok)
        self.assertIn('BNCLGU', expected)
        # non controllabile: nome di una sola parola, o CF non a 16 caratteri
        self.assertEqual(cf.name_matches('RSSMRA85T10A562S', 'Rossi'), (True, []))
        self.assertEqual(cf.name_matches('12345670546', 'Mario Rossi'), (True, []))
        self.assertEqual(cf.name_matches('', 'Mario Rossi'), (True, []))

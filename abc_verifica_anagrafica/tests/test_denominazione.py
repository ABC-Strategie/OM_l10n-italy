# -*- coding: utf-8 -*-
from odoo.tests import BaseCase, tagged

from ..tools import denominazione as den


@tagged('post_install', '-at_install', 'abc_va')
class TestDenominazione(BaseCase):

    def test_normalize_and_tokens(self):
        self.assertEqual(den.normalize("Rossi & Figli S.r.l."), 'ROSSI E FIGLI S R L')
        self.assertEqual(den.core_tokens("Rossi & Figli S.r.l."), ['ROSSI', 'FIGLI'])
        self.assertEqual(den.core_tokens("Alfa S.p.A."), ['ALFA'])
        self.assertEqual(den.core_tokens('ROSSI SRL'), ['ROSSI'])
        self.assertEqual(den.core_tokens('Società Cooperativa Sociale Aurora ONLUS'), ['SOCIALE', 'AURORA'])
        self.assertEqual(den.core_tokens('Caffè Nòvo'), ['CAFFE', 'NOVO'])

    def test_matches(self):
        cases = [
            ('Rossi S.r.l.', 'ROSSI SRL'),
            ('Mario Rossi', 'ROSSI MARIO'),
            ('Bianchi & Figli S.n.c.', 'BIANCHI E FIGLI SNC'),
            ('Studio Legale Rossi', 'ROSSI STUDIO LEGALE'),
            ('Rossi Costruzioni', 'ROSSI COSTRUZIONI EDILI SRL'),
            ('BBS Pratiche & Servizi', 'BBSPRATICHE&SERVIZI SRL'),
            ('Alfa Beta Gamma S.p.A.', 'ALFA BETA GAMMA SOCIETA PER AZIONI'),
            ('Autotrasporti Verdi di Verdi Luca', 'VERDI LUCA'),
        ]
        for odoo_name, ade_name in cases:
            self.assertTrue(den.names_match(odoo_name, ade_name), (odoo_name, ade_name))

    def test_mismatches(self):
        cases = [
            ('Rossi S.r.l.', 'BIANCHI SRL'),
            ('Rossi', 'ROSSINI SRL'),
            ('Mario Rossi', 'ROSSI LUIGI'),
            ('S.r.l.', 'ROSSI SRL'),          # nessun token significativo
            ('', 'ROSSI SRL'),
        ]
        for odoo_name, ade_name in cases:
            self.assertFalse(den.names_match(odoo_name, ade_name), (odoo_name, ade_name))

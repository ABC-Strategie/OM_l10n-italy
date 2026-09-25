# -*- coding: utf-8 -*-
"""Test del controllo di coerenza tra codice fiscale e nome sul contatto."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from ..services import registry
from .test_queue import FakeProvider, SECRET, CLIENT_ID

CF_ROSSI = 'RSSMRA85T10A562S'   # Mario Rossi


@tagged('post_install', '-at_install', 'abc_va')
class TestNameCheck(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'abc_va_enabled': True,
            'abc_va_client_id': CLIENT_ID,
            'abc_va_client_secret': SECRET,
            'abc_va_secret_expiry': fields.Date.today() + timedelta(days=365),
            'abc_va_name_check': 'block',
        })
        cls.Partner = cls.env['res.partner']
        cls.Queue = cls.env['abc.va.queue']

    def setUp(self):
        super().setUp()
        FakeProvider.responses = []
        FakeProvider.calls = []
        patcher = patch.object(registry, 'get_provider', lambda company: FakeProvider(company))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _create(self, name, cf=CF_ROSSI, **vals):
        return self.Partner.create([dict(vals, name=name, l10n_it_codice_fiscale=cf)])

    def test_default_is_block(self):
        self.assertEqual(self.env['res.company'].default_get(['abc_va_name_check'])['abc_va_name_check'], 'block')

    def test_block_on_create(self):
        with self.assertRaises(ValidationError) as cm, self.env.cr.savepoint():
            self._create('Luigi Bianchi')
        self.assertIn('RSSMRA', str(cm.exception))
        self.assertIn('BNCLGU', str(cm.exception))

    def test_block_on_name_change(self):
        partner = self._create('Mario Rossi')
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            partner.name = 'Mario Bianchi'
        partner.name = 'Rossi Mario'   # stesso soggetto, ordine diverso: ok

    def test_block_on_cf_change(self):
        partner = self._create('Mario Rossi')
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            partner.l10n_it_codice_fiscale = 'BNCGNN70A41F205X'

    def test_coherent_names_pass(self):
        for name in ('Mario Rossi', 'Rossi Mario', 'Dott. Mario Rossi', 'ROSSI MARIO'):
            partner = self._create(name)
            self.assertEqual(partner.abc_va_state, 'pending')

    def test_single_word_and_company_not_checked(self):
        self._create('Rossi')
        self._create('Bianchi Srl', cf='12345670546', is_company=True)

    def test_skip_trigger_context_bypasses(self):
        partner = self.Partner.with_context(abc_va_skip_trigger=True).create([{
            'name': 'Luigi Bianchi', 'l10n_it_codice_fiscale': CF_ROSSI,
        }])
        self.assertTrue(partner.exists())

    def test_flag_mode_marks_invalid_without_call(self):
        self.company.abc_va_name_check = 'flag'
        partner = self._create('Luigi Bianchi')
        self.assertEqual(partner.abc_va_state, 'pending')
        self.Queue._cron_process_queue()
        self.assertEqual(partner.abc_va_state, 'invalid')
        self.assertIn('non sono coerenti', partner.abc_va_message)
        self.assertFalse(FakeProvider.calls, 'nessuna chiamata al provider')
        log = self.env['abc.va.log'].search([('partner_id', '=', partner.id)])
        self.assertEqual(log.event, 'local')
        self.assertEqual(log.result_code, 'NAME_MISMATCH')

    def test_block_mode_also_in_queue(self):
        # dati arrivati senza constraint (import con skip trigger)
        partner = self.Partner.with_context(abc_va_skip_trigger=True).create([{
            'name': 'Luigi Bianchi', 'l10n_it_codice_fiscale': CF_ROSSI,
        }])
        self.Queue._abc_va_enqueue(partner, CF_ROSSI, self.company)
        self.Queue._cron_process_queue()
        self.assertEqual(partner.abc_va_state, 'invalid')
        self.assertFalse(FakeProvider.calls)

    def test_off_mode(self):
        self.company.abc_va_name_check = 'off'
        partner = self._create('Luigi Bianchi')
        self.Queue._cron_process_queue()
        self.assertEqual(partner.abc_va_state, 'valid')
        self.assertEqual(FakeProvider.calls, [CF_ROSSI])

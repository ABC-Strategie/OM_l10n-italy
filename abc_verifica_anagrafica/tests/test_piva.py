# -*- coding: utf-8 -*-
"""Test della verifica delle partite IVA: ambito, inneschi, esiti (valida,
cessata, non valida), confronto denominazione, cache con dettagli, blocco
documenti e allineamento del nome."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from ..services import registry
from ..services.base_provider import (
    BaseProvider, VerifyResult, ESITO_VALIDO, ESITO_NON_VALIDO, CODE_OK, CODE_NOT_FOUND,
)
from .test_queue import SECRET, CLIENT_ID

PIVA = '12345670546'


class FakePivaProvider(BaseProvider):
    code = 'fake'
    label = 'Fake'
    supports_piva = True
    responses = []
    calls = []

    def verify_cf(self, codice_fiscale, anagrafica=None):
        FakePivaProvider.calls.append(('cf', codice_fiscale))
        return VerifyResult(ESITO_VALIDO, CODE_OK, 'Codice fiscale valido', 200)

    def verify_piva(self, partita_iva):
        FakePivaProvider.calls.append(('piva', partita_iva))
        if FakePivaProvider.responses:
            response = FakePivaProvider.responses.pop(0)
        else:
            response = valid_response('ROSSI SRL')
        if isinstance(response, Exception):
            raise response
        return response


def valid_response(denominazione, end=None, suspended=None):
    return VerifyResult(ESITO_VALIDO, CODE_OK, denominazione or 'Partita IVA valida', 200, dati={
        'denominazione': denominazione,
        'data_inizio': '2010-01-01',
        'data_cessazione': end,
        'data_sospensione': suspended,
        'gruppo_iva': False,
        'piva_gruppo': None,
    })


@tagged('post_install', '-at_install', 'abc_va')
class TestPiva(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'abc_va_enabled': True,
            'abc_va_piva_enabled': True,
            'abc_va_client_id': CLIENT_ID,
            'abc_va_client_secret': SECRET,
            'abc_va_secret_expiry': fields.Date.today() + timedelta(days=365),
            'abc_va_on_invalid': 'block_document',
            'abc_va_on_ceased': 'block_document',
            'abc_va_piva_name_check': 'block',
            'abc_va_name_check': 'off',
            'abc_va_recheck_hours': 24,
        })
        cls.italy = cls.env.ref('base.it')
        cls.Partner = cls.env['res.partner']
        cls.Queue = cls.env['abc.va.queue']
        cls.Log = cls.env['abc.va.log']

    def setUp(self):
        super().setUp()
        FakePivaProvider.responses = []
        FakePivaProvider.calls = []
        patcher = patch.object(registry, 'get_provider', lambda company: FakePivaProvider(company))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _company_partner(self, name='Rossi S.r.l.', vat='IT' + PIVA, **vals):
        vals.update({'name': name, 'is_company': True, 'vat': vat, 'country_id': self.italy.id})
        return self.Partner.create([vals])

    def _pending(self, partner):
        return self.Queue.search([('partner_id', '=', partner.id), ('kind', '=', 'piva'),
                                  ('state', '=', 'pending')])

    def _run(self):
        self.Queue._cron_process_queue()

    # ------------------------------------------------------------------
    # Ambito e inneschi
    # ------------------------------------------------------------------
    def test_default_policies(self):
        defaults = self.env['res.company'].default_get(['abc_va_piva_name_check', 'abc_va_on_ceased'])
        self.assertEqual(defaults['abc_va_piva_name_check'], 'warn')
        self.assertEqual(defaults['abc_va_on_ceased'], 'block_document')

    def test_create_enqueues_piva(self):
        partner = self._company_partner()
        self.assertEqual(partner.abc_va_piva_state, 'pending')
        self.assertEqual(partner.abc_va_state, 'not_applicable', "azienda: CF non applicabile")
        job = self._pending(partner)
        self.assertEqual(job.value, PIVA)
        self.assertFalse(FakePivaProvider.calls)

    def test_person_with_piva_is_applicable(self):
        partner = self.Partner.create([{'name': 'Mario Rossi', 'vat': 'IT' + PIVA, 'country_id': self.italy.id}])
        self.assertEqual(partner.abc_va_piva_state, 'pending')

    def test_foreign_vat_not_applicable(self):
        partner = self.Partner.create([{'name': 'Foreign', 'is_company': True, 'vat': 'BE0477472701',
                                        'country_id': self.env.ref('base.be').id}])
        self.assertEqual(partner.abc_va_piva_state, 'not_applicable')
        self.assertFalse(self._pending(partner))

    def test_vat_without_prefix_and_country(self):
        partner = self.Partner.create([{'name': 'Senza paese', 'is_company': True, 'vat': PIVA}])
        self.assertEqual(partner._abc_va_get_piva(), PIVA)
        self.assertEqual(partner.abc_va_piva_state, 'pending')

    def test_disabled_piva(self):
        self.company.abc_va_piva_enabled = False
        partner = self._company_partner()
        self.assertEqual(partner.abc_va_piva_state, 'not_verified')
        self.assertFalse(self._pending(partner))

    def test_vat_change_supersedes(self):
        partner = self._company_partner()
        self._run()
        self.assertEqual(partner.abc_va_piva_state, 'valid')
        partner.vat = 'IT01114601006'
        self.assertEqual(partner.abc_va_piva_state, 'pending')
        self.assertFalse(partner.abc_va_piva_denominazione)
        self.assertEqual(self._pending(partner).value, '01114601006')

    # ------------------------------------------------------------------
    # Esiti
    # ------------------------------------------------------------------
    def test_valid_with_matching_name(self):
        partner = self._company_partner('Rossi S.r.l.')
        self._run()
        self.assertEqual(partner.abc_va_piva_state, 'valid')
        self.assertEqual(partner.abc_va_piva_denominazione, 'ROSSI SRL')
        self.assertEqual(partner.abc_va_piva_name_match, 'match')
        self.assertEqual(partner.abc_va_piva_start_date, fields.Date.to_date('2010-01-01'))
        self.assertEqual(FakePivaProvider.calls, [('piva', PIVA)])
        log = self.Log.search([('partner_id', '=', partner.id), ('kind', '=', 'piva')])
        self.assertEqual(log.event, 'api')
        self.assertIn('ROSSI SRL', log.details)

    def test_valid_with_name_mismatch(self):
        FakePivaProvider.responses = [valid_response('BIANCHI SPA')]
        partner = self._company_partner('Rossi S.r.l.')
        self._run()
        self.assertEqual(partner.abc_va_piva_state, 'valid')
        self.assertEqual(partner.abc_va_piva_name_match, 'mismatch')
        self.assertIn('denominazione diversa', partner.abc_va_piva_message)

    def test_ceased(self):
        FakePivaProvider.responses = [valid_response('ROSSI SRL', end='2020-06-30')]
        partner = self._company_partner()
        self._run()
        self.assertEqual(partner.abc_va_piva_state, 'ceased')
        self.assertEqual(partner.abc_va_piva_end_date, fields.Date.to_date('2020-06-30'))
        self.assertIn('cessata', partner.abc_va_piva_message)

    def test_suspended(self):
        FakePivaProvider.responses = [valid_response('ROSSI SRL', suspended='2024-01-15')]
        partner = self._company_partner()
        self._run()
        self.assertEqual(partner.abc_va_piva_state, 'ceased')
        self.assertIn('sospesa', partner.abc_va_piva_message)

    def test_not_valid(self):
        FakePivaProvider.responses = [VerifyResult(ESITO_NON_VALIDO, CODE_NOT_FOUND, '', 200, dati={'denominazione': None})]
        partner = self._company_partner()
        self._run()
        self.assertEqual(partner.abc_va_piva_state, 'invalid')
        self.assertIn('non riscontrata', partner.abc_va_piva_message)
        self.assertFalse(partner.abc_va_piva_name_match)

    def test_formal_invalid_no_call(self):
        partner = self._company_partner(vat='IT12345678901')   # cifra di controllo errata
        self._run()
        self.assertEqual(partner.abc_va_piva_state, 'invalid')
        self.assertIn('formalmente errata', partner.abc_va_piva_message)
        self.assertFalse(FakePivaProvider.calls)

    def test_cache_reuses_details(self):
        first = self._company_partner('Rossi S.r.l.')
        self._run()
        second = self._company_partner('Rossi Srl duplicato')
        self._run()
        self.assertEqual(len(FakePivaProvider.calls), 1)
        self.assertEqual(second.abc_va_piva_state, 'valid')
        self.assertEqual(second.abc_va_piva_denominazione, 'ROSSI SRL')
        self.assertEqual(second.abc_va_piva_name_match, 'match')
        self.assertEqual(first.abc_va_piva_state, 'valid')

    def test_verify_now_piva_synchronous(self):
        self.company.abc_va_recheck_hours = 0
        partner = self._company_partner()
        action = partner.with_context(abc_va_kind='piva').action_abc_va_verify_now()
        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual(partner.abc_va_piva_state, 'valid')
        self.assertEqual(len(FakePivaProvider.calls), 1)

    def test_verify_now_piva_ceased_notification(self):
        FakePivaProvider.responses = [valid_response('ROSSI SRL', end='2020-06-30')]
        partner = self._company_partner()
        action = partner.with_context(abc_va_kind='piva').action_abc_va_verify_now()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertIn('cessata', action['params']['title'])

    # ------------------------------------------------------------------
    # Allineamento denominazione
    # ------------------------------------------------------------------
    def test_align_name(self):
        FakePivaProvider.responses = [valid_response('BIANCHI SPA')]
        partner = self._company_partner('Rossi S.r.l.')
        self._run()
        self.assertEqual(partner.abc_va_piva_name_match, 'mismatch')
        partner.action_abc_va_align_name()
        self.assertEqual(partner.name, 'BIANCHI SPA')
        self.assertEqual(partner.abc_va_piva_name_match, 'match')
        self.assertEqual(partner.abc_va_piva_state, 'valid', "il cambio nome non azzera l'esito")

    # ------------------------------------------------------------------
    # Documenti
    # ------------------------------------------------------------------
    def _invoice(self, partner):
        return self.init_invoice('out_invoice', partner=partner, amounts=[100.0])

    def test_block_ceased(self):
        FakePivaProvider.responses = [valid_response('ROSSI SRL', end='2020-06-30')]
        partner = self._company_partner()
        self._run()
        with self.assertRaises(UserError) as cm:
            self._invoice(partner).action_post()
        self.assertIn('cessata', str(cm.exception))

    def test_ceased_warn(self):
        self.company.abc_va_on_ceased = 'warn'
        FakePivaProvider.responses = [valid_response('ROSSI SRL', end='2020-06-30')]
        partner = self._company_partner()
        self._run()
        invoice = self._invoice(partner)
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')
        self.assertIn('cessata', ' '.join(invoice.message_ids.mapped(lambda m: str(m.body))))

    def test_block_name_mismatch_then_align(self):
        FakePivaProvider.responses = [valid_response('BIANCHI SPA')]
        partner = self._company_partner('Rossi S.r.l.')
        self._run()
        invoice = self._invoice(partner)
        with self.assertRaises(UserError) as cm:
            invoice.action_post()
        self.assertIn('denominazione', str(cm.exception))
        partner.action_abc_va_align_name()
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')

    def test_name_mismatch_off(self):
        self.company.abc_va_piva_name_check = 'off'
        FakePivaProvider.responses = [valid_response('BIANCHI SPA')]
        partner = self._company_partner('Rossi S.r.l.')
        self._run()
        self._invoice(partner).action_post()

    def test_block_invalid_piva(self):
        FakePivaProvider.responses = [VerifyResult(ESITO_NON_VALIDO, CODE_NOT_FOUND, '', 200)]
        partner = self._company_partner()
        self._run()
        with self.assertRaises(UserError):
            self._invoice(partner).action_post()

    def test_valid_does_not_block_and_error_never_blocks(self):
        partner = self._company_partner()
        self._run()
        self._invoice(partner).action_post()
        partner._abc_va_apply_result('error', 'gateway', PIVA, kind='piva')
        self._invoice(partner).action_post()

    def test_on_use_trigger_piva(self):
        partner = self.Partner.with_context(abc_va_skip_trigger=True).create([{
            'name': 'Vecchia Srl', 'is_company': True, 'vat': 'IT' + PIVA, 'country_id': self.italy.id,
        }])
        self.assertEqual(partner.abc_va_piva_state, 'not_verified')
        self._invoice(partner).action_post()
        self.assertEqual(partner.abc_va_piva_state, 'pending')
        self.assertEqual(len(self._pending(partner)), 1)

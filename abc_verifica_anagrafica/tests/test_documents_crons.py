# -*- coding: utf-8 -*-
"""Test di blocco documenti, innesco su uso effettivo, alert scadenza e purge."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from ..services import registry
from ..services.base_provider import ESITO_VALIDO, CODE_OK
from ..models.abc_va_log import QUEUE_RETENTION_DAYS
from .test_queue import FakeProvider, CF_VALID_1, CF_VALID_2, SECRET, CLIENT_ID


@tagged('post_install', '-at_install', 'abc_va')
class TestDocumentsAndCrons(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'abc_va_enabled': True,
            'abc_va_provider': 'ade',
            'abc_va_environment': 'prod',
            'abc_va_client_id': CLIENT_ID,
            'abc_va_client_secret': SECRET,
            'abc_va_secret_expiry': fields.Date.today() + timedelta(days=365),
            'abc_va_on_invalid': 'block_document',
            'abc_va_trigger_on_invoice': True,
            'abc_va_retention_months': 24,
            'abc_va_name_check': 'off',
        })
        cls.Queue = cls.env['abc.va.queue']
        cls.Log = cls.env['abc.va.log']

    def setUp(self):
        super().setUp()
        FakeProvider.responses = []
        FakeProvider.calls = []
        patcher = patch.object(registry, 'get_provider', lambda company: FakeProvider(company))
        patcher.start()
        self.addCleanup(patcher.stop)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    def _person(self, cf, state=None, message='esito di test'):
        partner = self.env['res.partner'].with_context(abc_va_skip_trigger=True).create([{
            'name': f'Persona {cf}',
            'l10n_it_codice_fiscale': cf,
        }])
        if state:
            partner._abc_va_apply_result(state, message, cf)
        return partner

    def _invoice(self, partner):
        return self.init_invoice('out_invoice', partner=partner, amounts=[100.0])

    def _pending(self, partner):
        return self.Queue.search([('partner_id', '=', partner.id), ('state', '=', 'pending')])

    # ------------------------------------------------------------------
    # Blocco documenti
    # ------------------------------------------------------------------
    def test_block_invalid(self):
        partner = self._person(CF_VALID_1, 'invalid', 'Codice fiscale non riscontrato')
        invoice = self._invoice(partner)
        with self.assertRaises(UserError) as cm:
            invoice.action_post()
        self.assertIn('Come procedere', str(cm.exception))
        self.assertIn('non riscontrato', str(cm.exception))
        self.assertEqual(invoice.state, 'draft')

    def test_error_never_blocks(self):
        partner = self._person(CF_VALID_1, 'error', 'gateway down')
        invoice = self._invoice(partner)
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')

    def test_pending_and_valid_do_not_block(self):
        for state in ('pending', 'valid', 'not_applicable'):
            partner = self._person(CF_VALID_1, state)
            invoice = self._invoice(partner)
            invoice.action_post()
            self.assertEqual(invoice.state, 'posted')

    def test_warn_policy(self):
        self.company.abc_va_on_invalid = 'warn'
        partner = self._person(CF_VALID_1, 'invalid')
        invoice = self._invoice(partner)
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')
        bodies = ' '.join(invoice.message_ids.mapped(lambda m: str(m.body)))
        self.assertIn('non valido', bodies)

    def test_none_policy(self):
        self.company.abc_va_on_invalid = 'none'
        partner = self._person(CF_VALID_1, 'invalid')
        invoice = self._invoice(partner)
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')
        bodies = ' '.join(invoice.message_ids.mapped(lambda m: str(m.body)))
        self.assertNotIn('non valido', bodies)

    def test_related_fields_on_move(self):
        partner = self._person(CF_VALID_1, 'invalid')
        invoice = self._invoice(partner)
        self.assertEqual(invoice.abc_va_partner_state, 'invalid')
        self.assertEqual(invoice.abc_va_on_invalid, 'block_document')

    def test_block_disabled_when_setting_none_but_partner_invalid(self):
        # 'none' non blocca nemmeno con contatto non valido
        self.company.abc_va_on_invalid = 'none'
        partner = self._person(CF_VALID_1, 'invalid')
        self._invoice(partner).action_post()

    # ------------------------------------------------------------------
    # Innesco su uso effettivo
    # ------------------------------------------------------------------
    def test_on_use_trigger(self):
        partner = self._person(CF_VALID_1)
        self.assertEqual(partner.abc_va_state, 'not_verified')
        invoice = self._invoice(partner)
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted', "il documento non attende la verifica")
        self.assertEqual(partner.abc_va_state, 'pending')
        self.assertEqual(len(self._pending(partner)), 1)
        self.assertFalse(FakeProvider.calls, "nessuna chiamata sincrona")
        # una seconda fattura non duplica la richiesta
        self._invoice(partner).action_post()
        self.assertEqual(len(self._pending(partner)), 1)
        # dopo la verifica, gli usi successivi non fanno nulla
        self.Queue._cron_process_queue()
        self.assertEqual(partner.abc_va_state, 'valid')
        self._invoice(partner).action_post()
        self.assertEqual(partner.abc_va_state, 'valid')
        self.assertFalse(self._pending(partner))

    def test_draft_invoice_save_triggers_verification(self):
        partner = self._person(CF_VALID_1)
        invoice = self._invoice(partner)
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(partner.abc_va_state, 'pending', "verifica accodata al salvataggio della bozza")
        self.assertEqual(len(self._pending(partner)), 1)

    def test_on_use_trigger_disabled(self):
        self.company.abc_va_trigger_on_invoice = False
        partner = self._person(CF_VALID_1)
        self._invoice(partner).action_post()
        self.assertEqual(partner.abc_va_state, 'not_verified')
        self.assertFalse(self._pending(partner))

    def test_on_use_module_disabled(self):
        self.company.abc_va_enabled = False
        partner = self._person(CF_VALID_1)
        self._invoice(partner).action_post()
        self.assertEqual(partner.abc_va_state, 'not_verified')
        self.assertFalse(self._pending(partner))

    def test_on_use_company_partner_not_applicable(self):
        company_partner = self.env['res.partner'].with_context(abc_va_skip_trigger=True).create([{
            'name': 'Azienda', 'is_company': True, 'l10n_it_codice_fiscale': '12345670546',
        }])
        self._invoice(company_partner).action_post()
        self.assertEqual(company_partner.abc_va_state, 'not_verified')
        self.assertFalse(self._pending(company_partner))

    def test_on_use_uses_document_company(self):
        partner = self._person(CF_VALID_1)
        invoice = self._invoice(partner)
        invoice.action_post()
        self.assertEqual(self._pending(partner).company_id, invoice.company_id)

    def test_on_use_outdated_result(self):
        # esito riferito a un CF diverso da quello attuale: va rifatto
        partner = self._person(CF_VALID_1, 'valid')
        partner.with_context(abc_va_skip_trigger=True).l10n_it_codice_fiscale = CF_VALID_2
        self.assertTrue(partner._abc_va_is_outdated())
        self._invoice(partner).action_post()
        self.assertEqual(partner.abc_va_state, 'pending')
        self.assertEqual(self._pending(partner).value, CF_VALID_2)

    # ------------------------------------------------------------------
    # Alert scadenza client secret
    # ------------------------------------------------------------------
    def _alerts(self):
        return self.env['mail.activity'].search([
            ('res_model', '=', 'res.partner'),
            ('res_id', '=', self.company.partner_id.id),
            ('summary', 'ilike', 'Client secret'),
        ], order='id')

    def _run_alerts(self):
        self.env['res.company']._cron_abc_va_secret_expiry_alerts()

    def test_expiry_alerts(self):
        today = fields.Date.today()
        alert_user = self.env.ref('base.user_admin')
        self.company.write({'abc_va_alert_user_id': alert_user.id,
                            'abc_va_secret_expiry': today + timedelta(days=100)})
        self._run_alerts()
        self.assertFalse(self._alerts(), "oltre 60 giorni: nessun alert")

        self.company.abc_va_secret_expiry = today + timedelta(days=50)
        self._run_alerts()
        alerts = self._alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts.user_id, alert_user)
        self.assertIn('50 giorni', alerts.summary)
        self.assertEqual(self.company.abc_va_alerted_thresholds, '60')
        # giorni successivi: nessuna ripetizione
        self._run_alerts()
        self._run_alerts()
        self.assertEqual(len(self._alerts()), 1)

        # soglia 30
        self.company.abc_va_secret_expiry = today + timedelta(days=20)
        self.assertFalse(self.company.abc_va_alerted_thresholds, "nuova data: alert azzerati")
        self._run_alerts()
        self.assertEqual(len(self._alerts()), 2)
        self.assertEqual(self.company.abc_va_alerted_thresholds, '60,30')
        self._run_alerts()
        self.assertEqual(len(self._alerts()), 2)

        # soglia 7 sulla stessa data: simula il passare del tempo
        with patch.object(fields.Date, 'context_today', lambda *a, **k: today + timedelta(days=15)):
            self._run_alerts()
        self.assertEqual(len(self._alerts()), 3)
        self.assertEqual(self.company.abc_va_alerted_thresholds, '60,30,7')

        # scaduto
        with patch.object(fields.Date, 'context_today', lambda *a, **k: today + timedelta(days=21)):
            self._run_alerts()
        alerts = self._alerts()
        self.assertEqual(len(alerts), 4)
        self.assertIn('SCADUTO', alerts[-1].summary)
        self.assertEqual(self.company.abc_va_alerted_thresholds, '60,30,7,0')

    def test_expiry_alert_fallback_admin(self):
        self.company.write({'abc_va_alert_user_id': False,
                            'abc_va_secret_expiry': fields.Date.today() + timedelta(days=3)})
        self._run_alerts()
        alerts = self._alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts.user_id, self.env.ref('base.user_admin'))
        self.assertEqual(self.company.abc_va_alerted_thresholds, '60,30,7')

    # ------------------------------------------------------------------
    # Retention e purge
    # ------------------------------------------------------------------
    def _age(self, table, column, record, **delta):
        self.env.cr.execute(
            f"UPDATE {table} SET {column} = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(**delta), record.id),
        )
        record.invalidate_recordset()

    def test_purge(self):
        partner = self._person(CF_VALID_1)
        old = self.Queue._abc_va_log('api', ESITO_VALIDO, CODE_OK, message='old',
                                     partner=partner, value=CF_VALID_1, company=self.company)
        recent = self.Queue._abc_va_log('api', ESITO_VALIDO, CODE_OK, message='recent',
                                        partner=partner, value=CF_VALID_1, company=self.company)
        self._age('abc_va_log', 'timestamp', old, days=25 * 31)
        self._age('abc_va_log', 'timestamp', recent, days=23 * 30)

        job_old = self.Queue.sudo().create([{'partner_id': partner.id, 'company_id': self.company.id,
                                             'value': CF_VALID_1, 'state': 'done'}])
        job_recent = self.Queue.sudo().create([{'partner_id': partner.id, 'company_id': self.company.id,
                                                'value': CF_VALID_1, 'state': 'pending'}])
        self._age('abc_va_queue', 'write_date', job_old, days=QUEUE_RETENTION_DAYS + 5)
        self._age('abc_va_queue', 'write_date', job_recent, days=QUEUE_RETENTION_DAYS + 5)

        self.Log._cron_purge()
        self.assertFalse(old.exists(), "log oltre retention eliminato")
        self.assertTrue(recent.exists(), "log entro retention conservato")
        self.assertFalse(job_old.exists(), "richiesta conclusa e vecchia eliminata")
        self.assertTrue(job_recent.exists(), "richiesta pendente mai eliminata")

    def test_purge_respects_company_retention(self):
        self.company.abc_va_retention_months = 1
        partner = self._person(CF_VALID_1)
        log = self.Queue._abc_va_log('api', ESITO_VALIDO, CODE_OK, partner=partner,
                                     value=CF_VALID_1, company=self.company)
        self._age('abc_va_log', 'timestamp', log, days=40)
        self.Log._cron_purge()
        self.assertFalse(log.exists())

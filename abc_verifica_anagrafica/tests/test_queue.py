# -*- coding: utf-8 -*-
"""Test di coda, inneschi, throttle, retry, cache e sanitizzazione.

Nessuna chiamata di rete: il provider viene sostituito da un driver finto
registrato al posto di quello configurato.
"""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..services import registry
from ..services.base_provider import (
    BaseProvider, VerifyResult,
    ESITO_VALIDO, ESITO_NON_VALIDO, ESITO_ERRORE,
    CODE_OK, CODE_NOT_FOUND, CODE_AUTH, CODE_RATE_LIMIT, CODE_UNAVAILABLE,
)

CF_VALID_1 = 'RSSMRA85T10A562S'
CF_VALID_2 = 'TLEMRA83A01H501T'
CF_VALID_3 = 'MRTMTT91D08F205J'
CF_BAD_CHECK = 'RSSMRA85T10A562X'
SECRET = 'SECRET-abcdef123456'
CLIENT_ID = 'clientid-0123456789'


class FakeProvider(BaseProvider):
    code = 'fake'
    label = 'Fake'
    responses = []
    calls = []

    def verify_cf(self, codice_fiscale, anagrafica=None):
        FakeProvider.calls.append(codice_fiscale)
        if FakeProvider.responses:
            response = FakeProvider.responses.pop(0)
        else:
            response = VerifyResult(ESITO_VALIDO, CODE_OK, 'Codice fiscale valido', 200)
        if isinstance(response, Exception):
            raise response
        return response

    def health_check(self):
        return VerifyResult(ESITO_VALIDO, CODE_OK, 'ok', 200)


@tagged('post_install', '-at_install', 'abc_va')
class TestQueue(TransactionCase):

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
            'abc_va_rate_minute': 10,
            'abc_va_rate_day': 100,
            'abc_va_recheck_hours': 24,
            'abc_va_name_check': 'off',
        })
        cls.Partner = cls.env['res.partner']
        cls.Queue = cls.env['abc.va.queue']
        cls.Log = cls.env['abc.va.log']
        group_user = cls.env.ref('abc_verifica_anagrafica.group_abc_va_user')
        group_manager = cls.env.ref('abc_verifica_anagrafica.group_abc_va_manager')
        cls.user = cls.env['res.users'].create([{
            'name': 'VA User', 'login': 'va_user_test',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id, group_user.id])],
        }])
        cls.manager = cls.env['res.users'].create([{
            'name': 'VA Manager', 'login': 'va_manager_test',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id, group_manager.id])],
        }])

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
    def _partner(self, cf, **vals):
        vals.setdefault('name', f'Test {cf}')
        vals['l10n_it_codice_fiscale'] = cf
        return self.Partner.create([vals])

    def _pending(self, partner):
        return self.Queue.search([('partner_id', '=', partner.id), ('state', '=', 'pending')])

    def _run_cron(self):
        self.Queue._cron_process_queue()

    def _logs(self, partner=None, event=None):
        domain = []
        if partner is not None:
            domain.append(('partner_id', '=', partner.id))
        if event:
            domain.append(('event', '=', event))
        return self.Log.search(domain)

    # ------------------------------------------------------------------
    # Inneschi
    # ------------------------------------------------------------------
    def test_create_with_cf_enqueues(self):
        partner = self._partner(CF_VALID_1)
        self.assertEqual(partner.abc_va_state, 'pending')
        jobs = self._pending(partner)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs.value, CF_VALID_1)
        self.assertEqual(jobs.company_id, self.company)
        self.assertFalse(FakeProvider.calls, "nessuna chiamata sincrona nel create")

    def test_create_company_not_applicable(self):
        partner = self._partner('12345670546', is_company=True)
        self.assertEqual(partner.abc_va_state, 'not_applicable')
        self.assertFalse(self._pending(partner))

    def test_create_child_contact_not_applicable(self):
        parent = self._partner('12345670546', is_company=True)
        child = self._partner(CF_VALID_1, parent_id=parent.id)
        self.assertEqual(child.abc_va_state, 'not_applicable')
        self.assertFalse(self._pending(child))

    def test_create_without_cf(self):
        partner = self.Partner.create([{'name': 'Senza CF'}])
        self.assertEqual(partner.abc_va_state, 'not_verified')
        self.assertFalse(self._pending(partner))

    def test_create_disabled_company(self):
        self.company.abc_va_enabled = False
        partner = self._partner(CF_VALID_1)
        self.assertEqual(partner.abc_va_state, 'not_verified')
        self.assertFalse(self._pending(partner))

    def test_write_cf_change_resets_and_supersedes(self):
        partner = self._partner(CF_VALID_1)
        self._run_cron()
        self.assertEqual(partner.abc_va_state, 'valid')
        self.assertEqual(partner.abc_va_checked_value, CF_VALID_1)

        partner.l10n_it_codice_fiscale = CF_VALID_2
        self.assertEqual(partner.abc_va_state, 'pending')
        self.assertFalse(partner.abc_va_checked_value)
        self.assertFalse(partner.abc_va_message)
        jobs = self._pending(partner)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs.value, CF_VALID_2)

    def test_pending_superseded_on_second_change(self):
        partner = self._partner(CF_VALID_1)
        first = self._pending(partner)
        partner.l10n_it_codice_fiscale = CF_VALID_2
        self.assertEqual(first.state, 'cancelled')
        self.assertEqual(self._pending(partner).value, CF_VALID_2)

    def test_write_unrelated_field_no_trigger(self):
        partner = self._partner(CF_VALID_1)
        self._run_cron()
        partner.write({'phone': '123'})
        self.assertEqual(partner.abc_va_state, 'valid')
        self.assertFalse(self._pending(partner))

    def test_clear_cf_sets_not_applicable(self):
        partner = self._partner(CF_VALID_1)
        self._run_cron()
        partner.l10n_it_codice_fiscale = False
        self.assertEqual(partner.abc_va_state, 'not_applicable')

    def test_skip_trigger_context(self):
        partner = self.Partner.with_context(abc_va_skip_trigger=True).create([{
            'name': 'Import', 'l10n_it_codice_fiscale': CF_VALID_1,
        }])
        self.assertEqual(partner.abc_va_state, 'not_verified')
        self.assertFalse(self._pending(partner))

    # ------------------------------------------------------------------
    # Elaborazione
    # ------------------------------------------------------------------
    def test_process_valid(self):
        partner = self._partner(CF_VALID_1)
        self._run_cron()
        self.assertEqual(partner.abc_va_state, 'valid')
        self.assertEqual(partner.abc_va_checked_value, CF_VALID_1)
        self.assertTrue(partner.abc_va_last_check)
        self.assertEqual(FakeProvider.calls, [CF_VALID_1])
        job = self.Queue.search([('partner_id', '=', partner.id)])
        self.assertEqual(job.state, 'done')
        self.assertEqual(job.attempts, 1)
        log = self._logs(partner, 'api')
        self.assertEqual(len(log), 1)
        self.assertEqual(log.result, ESITO_VALIDO)
        self.assertEqual(log.result_code, CODE_OK)
        self.assertEqual(log.http_status, 200)
        self.assertGreaterEqual(log.duration_ms, 0)
        self.assertEqual(log.provider, 'ade')
        self.assertEqual(log.environment, 'prod')
        self.assertEqual(job.log_id, log)

    def test_process_not_valid(self):
        FakeProvider.responses = [VerifyResult(ESITO_NON_VALIDO, CODE_NOT_FOUND, 'Codice fiscale non valido', 200)]
        partner = self._partner(CF_VALID_1)
        self._run_cron()
        self.assertEqual(partner.abc_va_state, 'invalid')
        self.assertIn('Anagrafe Tributaria', partner.abc_va_message)
        self.assertEqual(self._logs(partner, 'api').result, ESITO_NON_VALIDO)

    def test_formal_invalid_no_call(self):
        partner = self._partner(CF_VALID_1)
        # simula un CF formalmente errato arrivato senza passare dal
        # constraint standard (import, scritture programmatiche)
        with patch.object(self.env.registry['res.partner'], '_abc_va_get_cf', lambda self: CF_BAD_CHECK):
            self._pending(partner).value = CF_BAD_CHECK
            self._run_cron()
        self.assertEqual(partner.abc_va_state, 'invalid')
        self.assertIn('formalmente errato', partner.abc_va_message)
        self.assertIn('carattere di controllo', partner.abc_va_message)
        self.assertFalse(FakeProvider.calls)
        log = self._logs(partner)
        self.assertEqual(log.event, 'local')
        self.assertEqual(log.result_code, 'FORMAL_INVALID')

    def test_superseded_job_cancelled_at_processing(self):
        partner = self._partner(CF_VALID_1)
        job = self._pending(partner)
        partner.with_context(abc_va_skip_trigger=True).l10n_it_codice_fiscale = CF_VALID_2
        self._run_cron()
        self.assertEqual(job.state, 'cancelled')
        self.assertFalse(FakeProvider.calls)

    def test_provider_missing(self):
        partner = self._partner(CF_VALID_1)
        with patch.object(registry, 'get_provider', side_effect=registry.ProviderNotAvailable('x')):
            self._run_cron()
        self.assertEqual(partner.abc_va_state, 'error')
        job = self.Queue.search([('partner_id', '=', partner.id)])
        self.assertEqual(job.state, 'error')
        self.assertFalse(self._logs(partner, 'api'), "nessuna chiamata conteggiata")

    # ------------------------------------------------------------------
    # Throttle
    # ------------------------------------------------------------------
    def test_throttle_minute(self):
        self.company.abc_va_rate_minute = 2
        partners = [self._partner(cf) for cf in (CF_VALID_1, CF_VALID_2, CF_VALID_3)]
        self._run_cron()
        self.assertEqual(len(FakeProvider.calls), 2)
        self.assertEqual(partners[0].abc_va_state, 'valid')
        self.assertEqual(partners[1].abc_va_state, 'valid')
        self.assertEqual(partners[2].abc_va_state, 'pending')
        self.assertTrue(self._pending(partners[2]))
        throttle_logs = self._logs(event='throttle')
        self.assertEqual(len(throttle_logs), 1)
        self.assertEqual(throttle_logs.result_code, 'THROTTLED')
        self.assertIn('al minuto', throttle_logs.message)
        # una seconda esecuzione nella stessa finestra non chiama e non
        # duplica il log del blocco oltre uno per esecuzione
        self._run_cron()
        self.assertEqual(len(FakeProvider.calls), 2)

    def test_throttle_day(self):
        self.company.write({'abc_va_rate_minute': 1, 'abc_va_rate_day': 1})
        partners = [self._partner(cf) for cf in (CF_VALID_1, CF_VALID_2)]
        self._run_cron()
        self.assertEqual(len(FakeProvider.calls), 1)
        # sposta la chiamata fuori dalla finestra del minuto ma dentro il giorno
        log = self._logs(partners[0], 'api')
        self.env.cr.execute(
            "UPDATE abc_va_log SET timestamp = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(minutes=5), log.id),
        )
        log.invalidate_recordset()
        self._run_cron()
        self.assertEqual(len(FakeProvider.calls), 1)
        self.assertIn('giornaliero', self._logs(event='throttle')[0].message)
        self.assertEqual(partners[1].abc_va_state, 'pending')

    def test_throttle_counts_errors_and_429(self):
        self.company.abc_va_rate_minute = 1
        FakeProvider.responses = [VerifyResult(ESITO_ERRORE, CODE_UNAVAILABLE, 'down', 503, retryable=True)]
        partners = [self._partner(cf) for cf in (CF_VALID_1, CF_VALID_2)]
        self._run_cron()
        self.assertEqual(len(FakeProvider.calls), 1, "anche una chiamata fallita consuma quota")
        self.assertEqual(partners[1].abc_va_state, 'pending')

    # ------------------------------------------------------------------
    # Retry e backoff
    # ------------------------------------------------------------------
    def _force_next_try_past(self, job):
        job.next_try = fields.Datetime.now() - timedelta(seconds=1)

    def test_retry_backoff_then_success(self):
        FakeProvider.responses = [VerifyResult(ESITO_ERRORE, CODE_UNAVAILABLE, 'Servizio non disponibile', 503, retryable=True)]
        partner = self._partner(CF_VALID_1)
        job = self._pending(partner)
        self._run_cron()
        self.assertEqual(job.state, 'pending')
        self.assertEqual(job.attempts, 1)
        self.assertTrue(job.next_try > fields.Datetime.now())
        self.assertEqual(partner.abc_va_state, 'pending')
        # non rielaborato prima di next_try
        self._run_cron()
        self.assertEqual(len(FakeProvider.calls), 1)
        self._force_next_try_past(job)
        self._run_cron()
        self.assertEqual(job.state, 'done')
        self.assertEqual(job.attempts, 2)
        self.assertEqual(partner.abc_va_state, 'valid')

    def test_backoff_is_exponential(self):
        FakeProvider.responses = [
            VerifyResult(ESITO_ERRORE, CODE_UNAVAILABLE, 'x', 503, retryable=True),
            VerifyResult(ESITO_ERRORE, CODE_UNAVAILABLE, 'x', 503, retryable=True),
        ]
        partner = self._partner(CF_VALID_1)
        job = self._pending(partner)
        self._run_cron()
        delay1 = (job.next_try - fields.Datetime.now()).total_seconds()
        self._force_next_try_past(job)
        self._run_cron()
        delay2 = (job.next_try - fields.Datetime.now()).total_seconds()
        self.assertGreater(delay1, 100)
        self.assertGreater(delay2, delay1 * 1.5)

    def test_max_attempts_then_error(self):
        FakeProvider.responses = [
            VerifyResult(ESITO_ERRORE, CODE_UNAVAILABLE, 'down', 503, retryable=True)
            for _ in range(3)
        ]
        partner = self._partner(CF_VALID_1)
        job = self._pending(partner)
        for _ in range(3):
            self._force_next_try_past(job)
            self._run_cron()
        self.assertEqual(job.state, 'error')
        self.assertEqual(job.attempts, 3)
        self.assertEqual(partner.abc_va_state, 'error')
        self.assertIn('3 tentativi', partner.abc_va_message)
        self.assertEqual(len(self._logs(partner, 'api')), 3)

    def test_non_retryable_auth_error(self):
        FakeProvider.responses = [VerifyResult(ESITO_ERRORE, CODE_AUTH, 'Invalid credentials', 401, retryable=False)]
        partner = self._partner(CF_VALID_1)
        job = self._pending(partner)
        self._run_cron()
        self.assertEqual(job.state, 'error')
        self.assertEqual(job.attempts, 1)
        self.assertEqual(partner.abc_va_state, 'error')
        self.assertIn('Invalid credentials', partner.abc_va_message)

    def test_retry_after_honoured(self):
        FakeProvider.responses = [VerifyResult(
            ESITO_ERRORE, CODE_RATE_LIMIT, 'Quota per minuto superata', 429,
            retryable=True, retry_after=45, rate_limit_type='minute',
        )]
        partner = self._partner(CF_VALID_1)
        job = self._pending(partner)
        self._run_cron()
        delay = (job.next_try - fields.Datetime.now()).total_seconds()
        self.assertTrue(40 <= delay <= 46, delay)
        self.assertEqual(job.state, 'pending')

    def test_provider_exception_is_retryable_and_sanitized(self):
        FakeProvider.responses = [RuntimeError(f'boom with {SECRET} and {CLIENT_ID}')]
        partner = self._partner(CF_VALID_1)
        job = self._pending(partner)
        self._run_cron()
        self.assertEqual(job.state, 'pending')
        self.assertEqual(job.attempts, 1)
        self.assertNotIn(SECRET, job.last_error)
        self.assertNotIn(CLIENT_ID, job.last_error)
        self.assertIn('***', job.last_error)
        log = self._logs(partner, 'api')
        self.assertNotIn(SECRET, log.message)

    def test_secret_never_in_partner_message_or_log(self):
        FakeProvider.responses = [VerifyResult(
            ESITO_ERRORE, CODE_AUTH, f'invalid secret {SECRET}', 401, retryable=False)]
        partner = self._partner(CF_VALID_1)
        self._run_cron()
        self.assertNotIn(SECRET, partner.abc_va_message)
        self.assertIn('***', partner.abc_va_message)
        for log in self._logs(partner):
            self.assertNotIn(SECRET, log.message or '')
            self.assertNotIn(SECRET, log.result_code or '')

    # ------------------------------------------------------------------
    # Cache anti-abuso e verifica manuale
    # ------------------------------------------------------------------
    def test_cache_reused_in_queue(self):
        p1 = self._partner(CF_VALID_1)
        self._run_cron()
        # secondo contatto con lo stesso CF (omonimo/duplicato): esito da cache
        p2 = self._partner(CF_VALID_1)
        self._run_cron()
        self.assertEqual(p2.abc_va_state, 'valid')
        self.assertEqual(len(FakeProvider.calls), 1)
        self.assertEqual(self._logs(p2).event, 'cache')
        self.assertEqual(self._logs(p1, 'api').result, ESITO_VALIDO)

    def test_cache_expired(self):
        p1 = self._partner(CF_VALID_1)
        self._run_cron()
        log = self._logs(p1, 'api')
        self.env.cr.execute(
            "UPDATE abc_va_log SET timestamp = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(hours=25), log.id),
        )
        log.invalidate_recordset()
        p2 = self._partner(CF_VALID_1)
        self._run_cron()
        self.assertEqual(len(FakeProvider.calls), 2)
        self.assertEqual(p2.abc_va_state, 'valid')

    def test_verify_now_uses_cache(self):
        partner = self._partner(CF_VALID_1)
        self._run_cron()
        action = partner.with_user(self.user).action_abc_va_verify_now()
        self.assertEqual(action['params']['type'], 'info')
        self.assertFalse(self._pending(partner))
        self.assertEqual(partner.abc_va_state, 'valid')
        self.assertEqual(self._logs(partner, 'cache').result_code, 'CACHED')

    def test_verify_now_synchronous(self):
        self.company.abc_va_recheck_hours = 0
        partner = self._partner(CF_VALID_1)
        action = partner.with_user(self.user).action_abc_va_verify_now()
        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual(action['params']['next']['type'], 'ir.actions.act_window_close')
        self.assertEqual(partner.abc_va_state, 'valid')
        self.assertEqual(FakeProvider.calls, [CF_VALID_1], "chiamata sincrona, senza cron")
        # tracking nel chatter: solo l'esito finale, non il passaggio a pending
        # (i messaggi di tracking vengono creati al precommit)
        self.env.flush_all()
        self.env.cr.precommit.run()
        tracked = partner.message_ids.filtered(lambda m: m.tracking_value_ids)
        self.assertEqual(len(tracked), 1)
        values = tracked.tracking_value_ids.filtered(lambda t: t.field_id.name == 'abc_va_state')
        self.assertEqual(values.new_value_char, 'Valido')
        self.assertFalse(self._pending(partner))
        job = self.Queue.search([('partner_id', '=', partner.id)])
        self.assertEqual(job.state, 'done')
        self.assertEqual(job.user_id, self.user)

    def test_verify_now_invalid_result(self):
        FakeProvider.responses = [VerifyResult(ESITO_NON_VALIDO, CODE_NOT_FOUND, 'Codice fiscale non valido', 200)]
        partner = self._partner(CF_VALID_1)
        action = partner.with_user(self.user).action_abc_va_verify_now()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertTrue(action['params']['sticky'])
        self.assertEqual(partner.abc_va_state, 'invalid')

    def test_verify_now_throttled_falls_back_to_queue(self):
        self.company.write({'abc_va_rate_minute': 1, 'abc_va_recheck_hours': 0})
        first = self._partner(CF_VALID_1)
        self._run_cron()
        self.assertEqual(len(FakeProvider.calls), 1)
        partner = self._partner(CF_VALID_2)
        action = partner.with_user(self.user).action_abc_va_verify_now()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('Limite', action['params']['title'])
        self.assertEqual(partner.abc_va_state, 'pending')
        self.assertEqual(len(self._pending(partner)), 1)
        self.assertEqual(len(FakeProvider.calls), 1, "nessuna chiamata oltre il limite")
        self.assertTrue(self._logs(partner, 'throttle'))
        self.assertEqual(first.abc_va_state, 'valid')

    def test_verify_now_provider_down_stays_pending(self):
        FakeProvider.responses = [VerifyResult(ESITO_ERRORE, CODE_UNAVAILABLE, 'Servizio non disponibile', 503, retryable=True)]
        partner = self._partner(CF_VALID_1)
        action = partner.with_user(self.user).action_abc_va_verify_now()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('non disponibile', action['params']['message'])
        self.assertEqual(partner.abc_va_state, 'pending')
        job = self._pending(partner)
        self.assertEqual(job.attempts, 1)
        self.assertTrue(job.next_try)
        # un secondo click prima di next_try non richiama il provider
        action = partner.with_user(self.user).action_abc_va_verify_now()
        self.assertEqual(action['params']['title'], 'Verifica già in coda')
        self.assertEqual(len(FakeProvider.calls), 1)

    def test_verify_now_auth_error(self):
        FakeProvider.responses = [VerifyResult(ESITO_ERRORE, CODE_AUTH, 'Invalid credentials', 401, retryable=False)]
        partner = self._partner(CF_VALID_1)
        action = partner.with_user(self.user).action_abc_va_verify_now()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertEqual(partner.abc_va_state, 'error')
        self.assertIn('Invalid credentials', action['params']['message'])

    def test_verify_now_force_by_manager(self):
        partner = self._partner(CF_VALID_1)
        self._run_cron()
        # l'utente base non può forzare: usa la cache
        partner.with_user(self.user).with_context(abc_va_force=True).action_abc_va_verify_now()
        self.assertEqual(len(FakeProvider.calls), 1)
        # il manager sì: nuova chiamata sincrona
        action = partner.with_user(self.manager).with_context(abc_va_force=True).action_abc_va_verify_now()
        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual(len(FakeProvider.calls), 2)
        self.assertFalse(self._pending(partner))
        job = self.Queue.search([('partner_id', '=', partner.id), ('force', '=', True)])
        self.assertEqual(job.state, 'done')

    def test_bus_notification_on_result(self):
        partner = self._partner(CF_VALID_1)
        job = self._pending(partner)
        self._run_cron()
        self.env.flush_all()
        self.env.cr.precommit.run()
        notifications = self.env['bus.bus'].sudo().search([
            ('message', 'ilike', 'abc_va/partner_updated'),
        ], order='id desc', limit=1)
        self.assertTrue(notifications, "notifica bus inviata all'utente che ha innescato")
        self.assertIn(str(partner.id), notifications.message)
        self.assertIn(str(job.user_id.partner_id.id), notifications.channel)

    def test_enqueue_wakes_cron(self):
        cron = self.env.ref('abc_verifica_anagrafica.cron_abc_va_process_queue')
        before = self.env['ir.cron.trigger'].search_count([('cron_id', '=', cron.id)])
        self._partner(CF_VALID_1)
        after = self.env['ir.cron.trigger'].search_count([('cron_id', '=', cron.id)])
        self.assertEqual(after, before + 1)

    def test_verify_now_not_applicable(self):
        partner = self._partner('12345670546', is_company=True)
        with self.assertRaises(UserError):
            partner.with_user(self.user).action_abc_va_verify_now()

    def test_verify_now_not_operational(self):
        partner = self._partner(CF_VALID_1)
        self.company.abc_va_client_secret = False
        with self.assertRaises(UserError):
            partner.with_user(self.user).action_abc_va_verify_now()

    def test_verify_now_secret_expired(self):
        partner = self._partner(CF_VALID_1)
        self.company.abc_va_secret_expiry = fields.Date.today() - timedelta(days=1)
        with self.assertRaises(UserError):
            partner.with_user(self.user).action_abc_va_verify_now()
        # e il cron non elabora
        self._run_cron()
        self.assertFalse(FakeProvider.calls)
        self.assertEqual(partner.abc_va_state, 'pending')

    # ------------------------------------------------------------------
    # Degradazione senza campo codice fiscale
    # ------------------------------------------------------------------
    def test_degradation_without_cf_field(self):
        with patch.object(self.env.registry['res.partner'], '_abc_va_cf_field_name', lambda self: None):
            partner = self._partner(CF_VALID_1)
            self.assertEqual(partner.abc_va_state, 'not_verified')
            self.assertFalse(self._pending(partner))
            with self.assertRaises(UserError):
                partner.with_user(self.user).action_abc_va_verify_now()
            partner.l10n_it_codice_fiscale = CF_VALID_2
            self.assertFalse(self._pending(partner))

    # ------------------------------------------------------------------
    # Immutabilità del log e company
    # ------------------------------------------------------------------
    def test_log_immutable(self):
        partner = self._partner(CF_VALID_1)
        self._run_cron()
        log = self._logs(partner, 'api')
        with self.assertRaises(UserError):
            log.write({'message': 'x'})
        with self.assertRaises(UserError):
            log.unlink()
        self.assertTrue(log.exists())
        log.with_context(abc_va_purge=True).unlink()
        self.assertFalse(log.exists())

    def test_company_limits_constraint(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.company.abc_va_rate_minute = 0
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.company.write({'abc_va_rate_minute': 500, 'abc_va_rate_day': 100})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.company.write({'abc_va_environment': 'test', 'abc_va_test_base_url': False})

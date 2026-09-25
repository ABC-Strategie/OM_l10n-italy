# -*- coding: utf-8 -*-
"""Test del driver AdE con HTTP interamente mockato (nessuna rete)."""
from datetime import timedelta
from unittest.mock import patch

import requests

from odoo import fields
from odoo.tests import TransactionCase, tagged

from ..services import ade_provider, registry
from ..services.ade_provider import AdeProvider
from ..services.base_provider import (
    ESITO_VALIDO, ESITO_NON_VALIDO, ESITO_ERRORE,
    CODE_OK, CODE_NOT_FOUND, CODE_AUTH, CODE_RATE_LIMIT, CODE_UNAVAILABLE,
    CODE_BAD_REQUEST, CODE_UNEXPECTED,
)

SECRET = 'SECRET-abcdef123456'
CLIENT_ID = 'clientid-0123456789'
CF = 'TLEMRA83A01H501T'


class FakeResponse:
    def __init__(self, status_code, json_data=None, headers=None, text=''):
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError('no json')
        return self._json


@tagged('post_install', '-at_install', 'abc_va')
class TestAdeProvider(TransactionCase):

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
            'abc_va_name_check': 'off',
        })
        cls.provider = AdeProvider(cls.company)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    def _post(self, response=None, side_effect=None):
        """Patcha requests.post nel modulo del driver e ritorna il mock."""
        patcher = patch.object(ade_provider.requests, 'post',
                               return_value=response, side_effect=side_effect)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def _get(self, response=None, side_effect=None):
        patcher = patch.object(ade_provider.requests, 'get',
                               return_value=response, side_effect=side_effect)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    # ------------------------------------------------------------------
    # Registrazione e configurazione
    # ------------------------------------------------------------------
    def test_registered(self):
        self.assertIn('ade', registry.available_codes())
        self.assertIsInstance(registry.get_provider(self.company), AdeProvider)
        self.assertNotIn(SECRET, repr(self.provider))

    def test_request_shape(self):
        mock = self._post(FakeResponse(200, {'valido': True, 'messaggio': 'Codice fiscale valido'}))
        self.provider.verify_cf(CF)
        mock.assert_called_once()
        args, kwargs = mock.call_args
        self.assertEqual(args[0], ade_provider.PROD_BASE_URL + ade_provider.CF_VERIFY_PATH)
        self.assertEqual(kwargs['json'], {'codiceFiscale': CF})
        self.assertEqual(kwargs['headers']['X-Client-Id'], CLIENT_ID)
        self.assertEqual(kwargs['headers']['X-Client-Secret'], SECRET)
        self.assertEqual(kwargs['headers']['Accept'], 'application/json')
        self.assertEqual(kwargs['timeout'], (ade_provider.CONNECT_TIMEOUT, ade_provider.READ_TIMEOUT))

    def test_test_environment_requires_url(self):
        self.company.write({'abc_va_enabled': False, 'abc_va_environment': 'test',
                            'abc_va_test_base_url': False})
        mock = self._post()
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['esito'], ESITO_ERRORE)
        self.assertEqual(result['codice_esito'], ade_provider.CODE_CONFIG)
        self.assertFalse(result['retryable'])
        mock.assert_not_called()

    def test_test_environment_url_used(self):
        self.company.write({'abc_va_environment': 'test',
                            'abc_va_test_base_url': 'https://test.example.org/api/'})
        mock = self._post(FakeResponse(200, {'valido': True, 'messaggio': 'ok'}))
        self.provider.verify_cf(CF)
        self.assertEqual(mock.call_args[0][0],
                         'https://test.example.org/api' + ade_provider.CF_VERIFY_PATH)

    def test_missing_credentials_no_call(self):
        self.company.abc_va_client_secret = False
        mock = self._post()
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['codice_esito'], ade_provider.CODE_CONFIG)
        mock.assert_not_called()

    # ------------------------------------------------------------------
    # Risposte 200
    # ------------------------------------------------------------------
    def test_valid(self):
        self._post(FakeResponse(200, {'valido': True, 'messaggio': 'Codice fiscale valido'}))
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['esito'], ESITO_VALIDO)
        self.assertEqual(result['codice_esito'], CODE_OK)
        self.assertEqual(result['messaggio'], 'Codice fiscale valido')
        self.assertEqual(result['raw_status_code'], 200)
        self.assertFalse(result['retryable'])

    def test_not_valid(self):
        self._post(FakeResponse(200, {'valido': False, 'messaggio': 'Codice fiscale non valido'}))
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['esito'], ESITO_NON_VALIDO)
        self.assertEqual(result['codice_esito'], CODE_NOT_FOUND)
        self.assertEqual(result['messaggio'], 'Codice fiscale non valido')

    def test_malformed_200(self):
        self._post(FakeResponse(200, None, text='<html>maintenance</html>'))
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['esito'], ESITO_ERRORE)
        self.assertEqual(result['codice_esito'], CODE_UNEXPECTED)
        self.assertTrue(result['retryable'])
        self.assertNotIn('maintenance', result['messaggio'], "il body grezzo non viene restituito")

    def test_message_truncated(self):
        self._post(FakeResponse(200, {'valido': True, 'messaggio': 'x' * 1000}))
        result = self.provider.verify_cf(CF)
        self.assertLessEqual(len(result['messaggio']), ade_provider.MAX_MESSAGE_LENGTH)

    # ------------------------------------------------------------------
    # Errori HTTP
    # ------------------------------------------------------------------
    def test_401(self):
        self._post(FakeResponse(401, {'error': 'invalid_credentials', 'message': 'Invalid credentials'}))
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['esito'], ESITO_ERRORE)
        self.assertEqual(result['codice_esito'], CODE_AUTH)
        self.assertFalse(result['retryable'])
        self.assertEqual(result['raw_status_code'], 401)
        self.assertIn('Invalid credentials', result['messaggio'])

    def test_403(self):
        self._post(FakeResponse(403, {'error': 'missing_credentials', 'message': 'Missing header'}))
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['codice_esito'], CODE_AUTH)
        self.assertFalse(result['retryable'])

    def test_429_minute(self):
        self._post(FakeResponse(
            429, {'error': 'too_many_requests_minute', 'message': 'Quota per minuto superata'},
            headers={'Retry-After': '30', 'X-RateLimit-Type': 'minute'},
        ))
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['codice_esito'], CODE_RATE_LIMIT)
        self.assertTrue(result['retryable'])
        self.assertEqual(result['retry_after'], 30)
        self.assertEqual(result['rate_limit_type'], 'minute')

    def test_429_day_from_body_when_header_missing(self):
        self._post(FakeResponse(429, {'error': 'too_many_requests_day', 'message': 'Quota giornaliera superata'}))
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['rate_limit_type'], 'day')
        self.assertIsNone(result['retry_after'])

    def test_429_bad_retry_after(self):
        self._post(FakeResponse(429, {'error': 'x', 'message': 'y'}, headers={'Retry-After': 'soon'}))
        result = self.provider.verify_cf(CF)
        self.assertIsNone(result['retry_after'])
        self.assertTrue(result['retryable'])

    def test_503(self):
        self._post(FakeResponse(503, {'error': 'Gateway_Timeout', 'message': 'riprovare'}))
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['codice_esito'], CODE_UNAVAILABLE)
        self.assertTrue(result['retryable'])
        self.assertEqual(result['raw_status_code'], 503)

    def test_500_without_json(self):
        self._post(FakeResponse(500, None, text='Internal error'))
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['codice_esito'], CODE_UNAVAILABLE)
        self.assertTrue(result['retryable'])

    def test_other_4xx_not_retryable(self):
        self._post(FakeResponse(400, {'error': 'bad_request', 'message': 'campo mancante'}))
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['codice_esito'], CODE_BAD_REQUEST)
        self.assertFalse(result['retryable'])
        self.assertIn('campo mancante', result['messaggio'])

    # ------------------------------------------------------------------
    # Errori di rete
    # ------------------------------------------------------------------
    def test_timeout(self):
        self._post(side_effect=requests.exceptions.ReadTimeout('read timed out'))
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['esito'], ESITO_ERRORE)
        self.assertEqual(result['codice_esito'], CODE_UNAVAILABLE)
        self.assertTrue(result['retryable'])
        self.assertIsNone(result['raw_status_code'])

    def test_connection_error_sanitized(self):
        self._post(side_effect=requests.exceptions.ConnectionError(
            f'refused for {CLIENT_ID}:{SECRET}@host'))
        result = self.provider.verify_cf(CF)
        self.assertEqual(result['codice_esito'], CODE_UNAVAILABLE)
        self.assertNotIn(SECRET, result['messaggio'])
        self.assertNotIn(CLIENT_ID, result['messaggio'])

    def test_secret_in_body_sanitized(self):
        self._post(FakeResponse(401, {'error': f'bad {SECRET}', 'message': f'secret {SECRET} rejected'}))
        result = self.provider.verify_cf(CF)
        self.assertNotIn(SECRET, result['messaggio'])
        self.assertNotIn(SECRET, result['codice_esito'])

    # ------------------------------------------------------------------
    # Partita IVA (predisposizione)
    # ------------------------------------------------------------------
    def test_piva(self):
        mock = self._post(FakeResponse(200, {
            'valida': True, 'partitaIva': '12345670546', 'denominazione': 'Rossi S.r.l.',
            'dataCessazioneAttivita': None,
        }))
        result = self.provider.verify_piva('IT 12345670546')
        self.assertEqual(mock.call_args[0][0], ade_provider.PROD_BASE_URL + ade_provider.PIVA_VERIFY_PATH)
        self.assertEqual(mock.call_args[1]['json'], {'partitaIva': '12345670546'})
        self.assertEqual(result['esito'], ESITO_VALIDO)
        self.assertIn('Rossi', result['messaggio'])
        self.assertEqual(result['dati']['denominazione'], 'Rossi S.r.l.')
        self.assertIsNone(result['dati']['data_cessazione'])
        self.assertFalse(result['dati']['gruppo_iva'])

    def test_piva_dati_sanitized(self):
        self._post(FakeResponse(200, {'valida': True, 'denominazione': f'X {SECRET} Y',
                                      'dataInizioSospensione': '2024-01-15', 'isGruppoIva': True}))
        result = self.provider.verify_piva('12345670546')
        self.assertNotIn(SECRET, result['dati']['denominazione'])
        self.assertEqual(result['dati']['data_sospensione'], '2024-01-15')
        self.assertTrue(result['dati']['gruppo_iva'])
        self.assertIn('sospesa', result['messaggio'])

    def test_cf_has_empty_dati(self):
        self._post(FakeResponse(200, {'valido': True, 'messaggio': 'ok'}))
        self.assertEqual(self.provider.verify_cf(CF)['dati'], {})

    def test_piva_ceased(self):
        self._post(FakeResponse(200, {'valida': True, 'denominazione': 'X', 'dataCessazioneAttivita': '2020-01-01'}))
        result = self.provider.verify_piva('12345670546')
        self.assertIn('cessata', result['messaggio'])

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    def test_health_ok_without_credentials(self):
        mock = self._get(FakeResponse(200))
        result = self.provider.health_check()
        self.assertEqual(result['esito'], ESITO_VALIDO)
        self.assertEqual(mock.call_args[0][0], ade_provider.PROD_BASE_URL + ade_provider.CF_STATUS_PATH)
        self.assertNotIn('X-Client-Secret', mock.call_args[1]['headers'])
        self.assertEqual(mock.call_args[1]['timeout'], (ade_provider.CONNECT_TIMEOUT, ade_provider.READ_TIMEOUT))

    def test_health_down(self):
        self._get(FakeResponse(503))
        result = self.provider.health_check()
        self.assertEqual(result['esito'], ESITO_ERRORE)
        self.assertEqual(result['raw_status_code'], 503)

    def test_health_network_error(self):
        self._get(side_effect=requests.exceptions.ConnectionError('dns'))
        result = self.provider.health_check()
        self.assertEqual(result['esito'], ESITO_ERRORE)
        self.assertEqual(result['codice_esito'], CODE_UNAVAILABLE)

    def test_company_health_check_and_settings_action(self):
        self._get(FakeResponse(200))
        ok, message = self.company._abc_va_health_check()
        self.assertTrue(ok)
        self.assertIn('raggiungibile', message)
        self.assertNotIn(SECRET, message)

        self.company.abc_va_secret_expiry = fields.Date.today() + timedelta(days=10)
        ok, message = self.company._abc_va_health_check()
        self.assertTrue(ok)
        self.assertIn('in scadenza', message)

        settings = self.env['res.config.settings'].create([{}])
        action = settings.action_abc_va_test_connection()
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['type'], 'success')

        self._get(FakeResponse(503))
        action = settings.action_abc_va_test_connection()
        self.assertEqual(action['params']['type'], 'danger')

# -*- coding: utf-8 -*-
"""Driver Agenzia delle Entrate: servizio "API anagrafiche libero accesso".

Fonte: documentazione tecnica scaricata dal Catalogo dei servizi di
interoperabilità (OpenAPI ``verifica-cf-openaccess_1.0.0.yaml`` e
``verifica-piva-openaccess_1.0.0.yaml``, README.txt). Tutto ciò che dipende
dalla specifica è raccolto nelle costanti in cima al file: un adeguamento a
una nuova versione della specifica è una modifica localizzata qui.

Regole del driver:

- ogni chiamata ha timeout espliciti di connessione e lettura;
- nessun testo proveniente da URL, header, body o eccezioni viene loggato o
  restituito senza passare da ``sanitize_text``;
- il body grezzo della risposta non viene mai restituito: solo esito
  normalizzato, codice e un messaggio breve.
"""
import logging

import requests

from .base_provider import (
    BaseProvider, VerifyResult,
    ESITO_VALIDO, ESITO_NON_VALIDO, ESITO_ERRORE,
    CODE_OK, CODE_NOT_FOUND, CODE_AUTH, CODE_RATE_LIMIT, CODE_UNAVAILABLE,
    CODE_BAD_REQUEST, CODE_UNEXPECTED, CODE_CONFIG,
)
from .registry import register
from ..tools.sanitize import sanitize_text, sanitize_exception

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Costanti dalla specifica AdE (OpenAPI 1.0.0, "libero accesso")
# ---------------------------------------------------------------------------
PROD_BASE_URL = 'https://api.agenziaentrate.gov.it/entrate/api'

CF_STATUS_PATH = '/codice-fiscale-liberoaccesso/status'        # GET, nessuna autenticazione
CF_VERIFY_PATH = '/codice-fiscale-liberoaccesso/verifica'      # POST {"codiceFiscale": ...}
PIVA_STATUS_PATH = '/partita-iva-liberoaccesso/status'          # GET
PIVA_VERIFY_PATH = '/partita-iva-liberoaccesso/verifica'        # POST {"partitaIva": ...}

HEADER_CLIENT_ID = 'X-Client-Id'
HEADER_CLIENT_SECRET = 'X-Client-Secret'
HEADER_RETRY_AFTER = 'Retry-After'
HEADER_RATE_LIMIT_TYPE = 'X-RateLimit-Type'   # 'minute' | 'day'

# Campi del body
REQ_CF_FIELD = 'codiceFiscale'
REQ_PIVA_FIELD = 'partitaIva'
RESP_CF_VALID_FIELD = 'valido'
RESP_PIVA_VALID_FIELD = 'valida'
RESP_MESSAGE_FIELD = 'messaggio'
RESP_ERROR_CODE_FIELD = 'error'
RESP_ERROR_MESSAGE_FIELD = 'message'
RESP_PIVA_NAME_FIELD = 'denominazione'
RESP_PIVA_START_FIELD = 'dataInizioAttivita'
RESP_PIVA_END_FIELD = 'dataCessazioneAttivita'
RESP_PIVA_SUSPENDED_FIELD = 'dataInizioSospensione'
RESP_PIVA_GROUP_FLAG_FIELD = 'isGruppoIva'
RESP_PIVA_GROUP_MEMBER_FIELD = 'isPartecipanteGruppoIva'
RESP_PIVA_GROUP_FIELD = 'partitaIvaGruppo'

# Timeout (secondi): connessione e lettura separati, mai una chiamata senza
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 20

# Lunghezza massima del messaggio del provider riportato nell'esito
MAX_MESSAGE_LENGTH = 200

USER_AGENT = 'Odoo/abc_verifica_anagrafica'


@register
class AdeProvider(BaseProvider):
    code = 'ade'
    label = 'Agenzia delle Entrate'
    supports_piva = True

    # ------------------------------------------------------------------
    # Configurazione
    # ------------------------------------------------------------------
    def _base_url(self):
        """URL base per l'ambiente configurato, o None se non configurabile."""
        company = self.company.sudo()
        if company.abc_va_environment == 'test':
            url = (company.abc_va_test_base_url or '').strip()
            return url.rstrip('/') or None
        return PROD_BASE_URL

    def _auth_headers(self):
        company = self.company.sudo()
        return {
            HEADER_CLIENT_ID: company.abc_va_client_id or '',
            HEADER_CLIENT_SECRET: company.abc_va_client_secret or '',
        }

    def _common_headers(self):
        return {
            'Accept': 'application/json',
            'User-Agent': USER_AGENT,
        }

    def _config_error(self, message):
        return VerifyResult(ESITO_ERRORE, CODE_CONFIG, message, None, retryable=False)

    # ------------------------------------------------------------------
    # Interfaccia pubblica
    # ------------------------------------------------------------------
    def verify_cf(self, codice_fiscale, anagrafica=None):
        # ``anagrafica`` non è usata: il servizio "libero accesso" verifica
        # il solo codice.
        return self._verify(CF_VERIFY_PATH, {REQ_CF_FIELD: codice_fiscale},
                            RESP_CF_VALID_FIELD, self._cf_message)

    def verify_piva(self, partita_iva):
        piva = ''.join(str(partita_iva or '').split()).upper()
        if piva.startswith('IT'):
            piva = piva[2:]
        return self._verify(PIVA_VERIFY_PATH, {REQ_PIVA_FIELD: piva},
                            RESP_PIVA_VALID_FIELD, self._piva_message, self._piva_data)

    def health_check(self):
        """GET sullo status del servizio codice fiscale.

        L'endpoint di stato non richiede autenticazione: il test verifica la
        raggiungibilità del servizio per l'ambiente configurato, non la
        validità delle credenziali (che non vengono inviate).
        """
        base_url = self._base_url()
        if not base_url:
            return self._config_error(
                "URL base dell'ambiente di test non configurato.")
        url = base_url + CF_STATUS_PATH
        secrets = self._secrets()
        try:
            response = requests.get(
                url, headers=self._common_headers(),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.exceptions.RequestException as exc:
            message = sanitize_exception(exc, secrets)
            _logger.warning("AdE health check: errore di rete: %s", message)
            return VerifyResult(ESITO_ERRORE, CODE_UNAVAILABLE,
                                f"Servizio non raggiungibile: {message}", None, retryable=True)
        if response.status_code == 200:
            return VerifyResult(ESITO_VALIDO, CODE_OK,
                                "Servizio raggiungibile.", 200)
        return VerifyResult(
            ESITO_ERRORE, self._code_for_status(response.status_code),
            f"Servizio non disponibile (HTTP {response.status_code}).",
            response.status_code, retryable=response.status_code >= 500,
        )

    # ------------------------------------------------------------------
    # Chiamata e interpretazione
    # ------------------------------------------------------------------
    def _verify(self, path, payload, valid_field, message_builder, data_builder=None):
        base_url = self._base_url()
        if not base_url:
            return self._config_error(
                "URL base dell'ambiente di test non configurato.")
        company = self.company.sudo()
        if not company.abc_va_client_id or not company.abc_va_client_secret:
            return self._config_error("Credenziali del servizio non configurate.")

        url = base_url + path
        secrets = self._secrets()
        headers = {**self._common_headers(), **self._auth_headers()}
        try:
            response = requests.post(
                url, json=payload, headers=headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.exceptions.Timeout as exc:
            message = sanitize_exception(exc, secrets)
            _logger.warning("AdE %s: timeout: %s", path, message)
            return VerifyResult(ESITO_ERRORE, CODE_UNAVAILABLE,
                                "Timeout nella comunicazione con il servizio.", None, retryable=True)
        except requests.exceptions.RequestException as exc:
            message = sanitize_exception(exc, secrets)
            _logger.warning("AdE %s: errore di rete: %s", path, message)
            return VerifyResult(ESITO_ERRORE, CODE_UNAVAILABLE,
                                f"Errore di rete: {message}", None, retryable=True)

        return self._interpret(response, valid_field, message_builder, secrets, data_builder)

    def _interpret(self, response, valid_field, message_builder, secrets, data_builder=None):
        status = response.status_code
        data = self._json(response)
        _logger.info("AdE risposta HTTP %s", status)

        if status == 200:
            if not isinstance(data, dict) or valid_field not in data:
                return VerifyResult(ESITO_ERRORE, CODE_UNEXPECTED,
                                    "Risposta del servizio non interpretabile.", status, retryable=True)
            message = sanitize_text(message_builder(data), secrets)[:MAX_MESSAGE_LENGTH]
            dati = data_builder(data, secrets) if data_builder else {}
            if data.get(valid_field) is True:
                return VerifyResult(ESITO_VALIDO, CODE_OK, message, status, dati=dati)
            return VerifyResult(ESITO_NON_VALIDO, CODE_NOT_FOUND, message, status, dati=dati)

        error_code, error_message = self._error_fields(data, secrets)
        code = self._code_for_status(status)

        if status == 429:
            retry_after = self._int_header(response, HEADER_RETRY_AFTER)
            limit_type = (response.headers.get(HEADER_RATE_LIMIT_TYPE) or '').strip().lower() or None
            if limit_type not in ('minute', 'day'):
                limit_type = 'day' if 'day' in error_code else 'minute' if 'minute' in error_code else None
            return VerifyResult(
                ESITO_ERRORE, CODE_RATE_LIMIT,
                error_message or "Limite di richieste del servizio superato.",
                status, retryable=True, retry_after=retry_after, rate_limit_type=limit_type,
            )
        if status in (401, 403):
            default = ("Credenziali del servizio non valide." if status == 401
                       else "Credenziali del servizio mancanti o non accettate.")
            return VerifyResult(ESITO_ERRORE, CODE_AUTH, error_message or default, status, retryable=False)
        if status >= 500:
            return VerifyResult(ESITO_ERRORE, CODE_UNAVAILABLE,
                                error_message or "Servizio momentaneamente non disponibile.",
                                status, retryable=True)
        # Altri 4xx: nessun retry
        return VerifyResult(ESITO_ERRORE, code,
                            error_message or f"Richiesta rifiutata dal servizio (HTTP {status}).",
                            status, retryable=False)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    @staticmethod
    def _code_for_status(status):
        if status == 429:
            return CODE_RATE_LIMIT
        if status in (401, 403):
            return CODE_AUTH
        if status >= 500:
            return CODE_UNAVAILABLE
        if status >= 400:
            return CODE_BAD_REQUEST
        return CODE_UNEXPECTED

    @staticmethod
    def _json(response):
        try:
            return response.json()
        except ValueError:
            return None

    @staticmethod
    def _int_header(response, name):
        value = response.headers.get(name)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _error_fields(data, secrets):
        """Codice e messaggio di errore dal body ``ErrorResponse``, sanitizzati."""
        if not isinstance(data, dict):
            return '', ''
        code = sanitize_text(data.get(RESP_ERROR_CODE_FIELD) or '', secrets)[:64].lower()
        message = sanitize_text(data.get(RESP_ERROR_MESSAGE_FIELD) or '', secrets)[:MAX_MESSAGE_LENGTH]
        return code, message

    @staticmethod
    def _cf_message(data):
        return str(data.get(RESP_MESSAGE_FIELD) or '')

    @staticmethod
    def _piva_message(data):
        parts = []
        name = data.get(RESP_PIVA_NAME_FIELD)
        if name:
            parts.append(str(name))
        if data.get(RESP_PIVA_END_FIELD):
            parts.append(f"cessata il {data.get(RESP_PIVA_END_FIELD)}")
        elif data.get(RESP_PIVA_SUSPENDED_FIELD):
            parts.append(f"sospesa dal {data.get(RESP_PIVA_SUSPENDED_FIELD)}")
        return ', '.join(parts)

    @staticmethod
    def _piva_data(data, secrets):
        """Dati strutturati della partita IVA, normalizzati e sanitizzati."""
        def text(key, limit=200):
            value = data.get(key)
            return sanitize_text(value, secrets)[:limit] if value else None
        return {
            'denominazione': text(RESP_PIVA_NAME_FIELD),
            'data_inizio': text(RESP_PIVA_START_FIELD, 10),
            'data_cessazione': text(RESP_PIVA_END_FIELD, 10),
            'data_sospensione': text(RESP_PIVA_SUSPENDED_FIELD, 10),
            'gruppo_iva': bool(data.get(RESP_PIVA_GROUP_FLAG_FIELD) or data.get(RESP_PIVA_GROUP_MEMBER_FIELD)),
            'piva_gruppo': text(RESP_PIVA_GROUP_FIELD, 11),
        }

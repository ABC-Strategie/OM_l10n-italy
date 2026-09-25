# -*- coding: utf-8 -*-
"""Interfaccia astratta del provider di verifica.

La logica di business (coda, partner, UI) dialoga esclusivamente con questa
interfaccia e con la struttura normalizzata ``VerifyResult``. Nessun modulo
al di fuori di ``services`` deve conoscere il provider concreto.

Per aggiungere un provider:

1. creare ``services/<nome>_provider.py`` con una sottoclasse di
   ``BaseProvider`` che valorizza ``code`` e ``label``;
2. registrarla con ``@registry.register``;
3. aggiungere il codice alla selection ``abc_va_provider`` su ``res.company``.
"""

# Esiti normalizzati. Sono gli unici valori che la logica di business conosce.
ESITO_VALIDO = 'valido'
ESITO_NON_VALIDO = 'non_valido'
ESITO_ERRORE = 'errore'
ESITI = (ESITO_VALIDO, ESITO_NON_VALIDO, ESITO_ERRORE)

# Codici esito normalizzati, indipendenti dal provider. Il provider concreto
# mappa le proprie risposte su questi valori; il codice grezzo del provider
# viene comunque conservato in ``codice_esito`` quando disponibile.
CODE_OK = 'OK'                        # soggetto valido / esistente
CODE_NOT_FOUND = 'NOT_FOUND'          # soggetto non valido / non esistente
CODE_AUTH = 'AUTH_ERROR'              # credenziali mancanti o non valide (4xx)
CODE_RATE_LIMIT = 'RATE_LIMIT'        # 429 lato provider
CODE_UNAVAILABLE = 'UNAVAILABLE'      # 5xx / timeout / errore di rete
CODE_BAD_REQUEST = 'BAD_REQUEST'      # 4xx diverso da 401/403/429
CODE_UNEXPECTED = 'UNEXPECTED'        # risposta non interpretabile
CODE_CONFIG = 'CONFIG_ERROR'          # configurazione incompleta, nessuna chiamata effettuata


class VerifyResult(dict):
    """Struttura normalizzata restituita da ogni metodo di verifica.

    Chiavi:

    - ``esito``: uno tra ``valido``, ``non_valido``, ``errore``;
    - ``codice_esito``: codice normalizzato (vedi costanti ``CODE_*``);
    - ``messaggio``: testo leggibile, GIÀ SANITIZZATO, mai il payload grezzo;
    - ``raw_status_code``: HTTP status della risposta, ``None`` se la chiamata
      non è avvenuta (errore di rete, timeout);
    - ``retryable``: ``True`` se ha senso ritentare (rete, 5xx, 429);
    - ``retry_after``: secondi suggeriti dal provider prima di ritentare,
      ``None`` se non indicati;
    - ``rate_limit_type``: ``'minute'`` / ``'day'`` quando il provider segnala
      quale limite è stato superato, altrimenti ``None``;
    - ``dati``: dict di dati strutturati e sanitizzati restituiti dal provider
      (per la partita IVA: denominazione, date di inizio, cessazione e
      sospensione, gruppo IVA), ``{}`` se non disponibili.

    È un ``dict`` per restare serializzabile e semplice da mockare nei test.
    """

    def __init__(self, esito, codice_esito, messaggio='', raw_status_code=None,
                 retryable=False, retry_after=None, rate_limit_type=None, dati=None):
        if esito not in ESITI:
            raise ValueError(f'Esito non valido: {esito!r}')
        super().__init__(
            esito=esito,
            codice_esito=codice_esito,
            messaggio=messaggio or '',
            raw_status_code=raw_status_code,
            retryable=bool(retryable),
            retry_after=retry_after,
            rate_limit_type=rate_limit_type,
            dati=dict(dati or {}),
        )

    @property
    def esito(self):
        return self['esito']

    @property
    def is_error(self):
        return self['esito'] == ESITO_ERRORE


class BaseProvider:
    """Contratto che ogni driver deve rispettare.

    Il provider riceve la ``res.company`` di riferimento e da essa legge
    credenziali, ambiente e ogni altra impostazione. Non deve mai
    memorizzare il secret in attributi che possano finire in un ``repr``
    o in un log.
    """

    #: codice tecnico usato nella selection ``abc_va_provider``
    code = None
    #: etichetta leggibile
    label = None
    #: True se il driver supporta la verifica della partita IVA
    supports_piva = False

    def __init__(self, company):
        self.company = company
        self.env = company.env

    # ------------------------------------------------------------------
    # Interfaccia pubblica
    # ------------------------------------------------------------------
    def verify_cf(self, codice_fiscale, anagrafica=None):
        """Verifica un codice fiscale di persona fisica.

        :param codice_fiscale: stringa già normalizzata (maiuscola, senza
            spazi) e già validata formalmente dal chiamante.
        :param anagrafica: dict opzionale con dati anagrafici (nome, cognome,
            data e luogo di nascita) per i provider che li richiedono o li
            usano per un riscontro. Il provider AdE "libero accesso" non li
            usa.
        :return: ``VerifyResult``
        """
        raise NotImplementedError

    def verify_piva(self, partita_iva):
        """Verifica una partita IVA.

        :param partita_iva: 11 cifre, già normalizzate dal chiamante.
        :return: ``VerifyResult``; in ``dati`` le chiavi normalizzate
            ``denominazione``, ``data_inizio``, ``data_cessazione``,
            ``data_sospensione`` (stringhe ISO o ``None``), ``gruppo_iva``
            (bool), ``piva_gruppo``.
        """
        raise NotImplementedError

    def health_check(self):
        """Verifica la raggiungibilità del provider senza consumare quota
        ove possibile e senza salvare nulla.

        :return: ``VerifyResult`` con ``esito`` ``valido`` se il servizio è
            raggiungibile, ``errore`` altrimenti.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Helper comuni
    # ------------------------------------------------------------------
    def _secrets(self):
        """Valori da mascherare in qualunque testo prodotto dal driver."""
        company = self.company.sudo()
        return [company.abc_va_client_secret, company.abc_va_client_id]

    def __repr__(self):
        # Mai includere credenziali nel repr.
        return f'<{type(self).__name__} company={self.company.id}>'

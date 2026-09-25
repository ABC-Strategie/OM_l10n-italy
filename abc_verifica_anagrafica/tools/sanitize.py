# -*- coding: utf-8 -*-
"""Sanitizzazione delle credenziali.

Le Condizioni generali del servizio AdE (art. 8 c.1) vietano di condividere
con terzi gli identificativi assegnati. Questo modulo garantisce che client
id e client secret non compaiano mai in log, traceback, messaggi di errore,
chatter, record di verifica o export.

Regola d'uso: OGNI stringa che possa contenere dati provenienti da una
richiesta o risposta HTTP (URL, header, body, messaggio di eccezione) deve
passare da ``sanitize_text`` prima di essere loggata o salvata.
"""

MASK = '***'

# Lunghezza minima di un segreto per essere mascherato. Evita che valori
# banali (es. stringa vuota o 1-2 caratteri) producano sostituzioni assurde.
MIN_SECRET_LENGTH = 4


def sanitize_text(text, secrets):
    """Ritorna ``text`` con ogni occorrenza di ``secrets`` sostituita da MASK.

    :param text: qualunque valore; viene convertito in stringa.
    :param secrets: iterabile di stringhe da mascherare. I valori falsy o
        più corti di MIN_SECRET_LENGTH vengono ignorati.
    :return: stringa sanitizzata.
    """
    if text is None:
        return ''
    result = str(text)
    for secret in sorted({s for s in (secrets or []) if s}, key=len, reverse=True):
        secret = str(secret)
        if len(secret) < MIN_SECRET_LENGTH:
            continue
        if secret in result:
            result = result.replace(secret, MASK)
    return result


def sanitize_exception(exc, secrets):
    """Messaggio leggibile di un'eccezione, con segreti mascherati.

    Non include mai il traceback: il messaggio è destinato a log applicativi,
    campi ``last_error`` e notifiche utente.
    """
    if exc is None:
        return ''
    message = f'{type(exc).__name__}: {exc}'
    return sanitize_text(message, secrets)


def sanitize_mapping(mapping, secrets):
    """Copia superficiale di un dict con tutti i valori stringa sanitizzati.

    Utile per loggare header o payload in modalità debug senza rischiare la
    fuga del secret.
    """
    if not mapping:
        return {}
    return {
        str(key): sanitize_text(value, secrets) if isinstance(value, str) else value
        for key, value in mapping.items()
    }

# -*- coding: utf-8 -*-
"""Registro dei provider disponibili.

I driver concreti si registrano con il decoratore ``register``. La logica di
business ottiene un'istanza tramite ``get_provider(company)`` e non importa
mai direttamente un driver.
"""

_PROVIDERS = {}


class ProviderNotAvailable(Exception):
    """Il provider configurato non è registrato o non è implementato."""


def register(provider_class):
    """Decoratore di classe: registra un driver per il suo ``code``."""
    code = getattr(provider_class, 'code', None)
    if not code:
        raise ValueError('Il provider deve definire un attributo "code"')
    _PROVIDERS[code] = provider_class
    return provider_class


def available_codes():
    """Codici dei provider effettivamente implementati."""
    return sorted(_PROVIDERS)


def get_provider_class(code):
    try:
        return _PROVIDERS[code]
    except KeyError:
        raise ProviderNotAvailable(
            f'Provider "{code}" non disponibile. Disponibili: {available_codes()}'
        ) from None


def get_provider(company):
    """Istanzia il driver configurato sulla company."""
    code = company.abc_va_provider
    return get_provider_class(code)(company)

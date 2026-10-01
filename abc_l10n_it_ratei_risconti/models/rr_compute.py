# -*- coding: utf-8 -*-
"""Calcolo puro di ratei e risconti (nessun accesso al database).

Convenzioni:
- ``balance`` e' il saldo contabile della riga d'origine (dare positivo, avere
  negativo) in valuta societa': un costo ha saldo positivo, un ricavo negativo.
- ``closing`` e' la data di chiusura D dell'esercizio.
- I giorni sono effettivi, con giorno iniziale e finale inclusi.
"""
from dateutil.relativedelta import relativedelta

COST_TYPES = ('expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost')
INCOME_TYPES = ('income', 'income_other')

RR_TYPES = [
    ('rateo_attivo', 'Rateo attivo'),
    ('rateo_passivo', 'Rateo passivo'),
    ('risconto_attivo', 'Risconto attivo'),
    ('risconto_passivo', 'Risconto passivo'),
]

# rateo/risconto x costo/ricavo -> tipologia
TYPE_MATRIX = {
    ('risconto', 'cost'): 'risconto_attivo',
    ('risconto', 'income'): 'risconto_passivo',
    ('rateo', 'cost'): 'rateo_passivo',
    ('rateo', 'income'): 'rateo_attivo',
}

COST_RR_TYPES = ('rateo_passivo', 'risconto_attivo')
ASSET_RR_TYPES = ('rateo_attivo', 'risconto_attivo')


def rr_kind(rr_type):
    """'rateo' oppure 'risconto'."""
    return 'rateo' if rr_type.startswith('rateo') else 'risconto'


def entry_sign(rr_type):
    """Segno della riga sul conto d'origine nella scrittura di assestamento.

    Risconto: si toglie la quota dal costo/ricavo (segno -1 sul saldo).
    Rateo: si aggiunge la quota al costo/ricavo (segno +1 sul saldo).
    """
    return -1 if rr_kind(rr_type) == 'risconto' else 1


def total_days(start, end):
    return (end - start).days + 1


def days_between(start, end, win_from, win_to):
    """Giorni di [start, end] che cadono in [win_from, win_to], estremi inclusi."""
    first = max(start, win_from)
    last = min(end, win_to)
    if last < first:
        return 0
    return (last - first).days + 1


def classify(line_date, closing, nature):
    """Tipologia di una riga registrata (nature = 'cost' | 'income')."""
    kind = 'risconto' if line_date <= closing else 'rateo'
    return TYPE_MATRIX[(kind, nature)]


def compute_quota(balance, start, end, closing, rr_type, round_fn=None):
    """Restituisce un dizionario con giorni e quote.

    Chiavi: days_total, days_rr (giorni del rateo o risconto), amount (quota
    firmata come ``balance``), amount_within (entro 12 mesi da D), amount_beyond
    (oltre 12 mesi), amount_beyond_5y (di cui oltre 5 anni), full (True se la
    quota e' il 100% dell'importo).
    Per i ratei entro/oltre non si applicano: amount_within = amount.
    """
    if round_fn is None:
        def round_fn(x):
            return round(x, 2)
    if not start or not end or end < start:
        return None
    tot = total_days(start, end)
    if rr_kind(rr_type) == 'risconto':
        days = days_between(start, end, closing + relativedelta(days=1), end)
        one_year = closing + relativedelta(years=1)
        five_years = closing + relativedelta(years=5)
        days_within = days_between(start, end, closing + relativedelta(days=1), one_year)
        days_5y = days_between(start, end, five_years + relativedelta(days=1), end)
        amount = round_fn(balance * days / tot)
        within = round_fn(balance * days_within / tot)
        beyond = round_fn(amount - within)
        beyond_5y = round_fn(balance * days_5y / tot)
    else:
        days = days_between(start, end, start, closing)
        amount = round_fn(balance * days / tot)
        within = amount
        beyond = 0.0
        beyond_5y = 0.0
    return {
        'days_total': tot,
        'days_rr': days,
        'amount': amount,
        'amount_within': within,
        'amount_beyond': beyond,
        'amount_beyond_5y': beyond_5y,
        'full': days == tot,
    }


def split_final(amount, calc_amount, calc_beyond, round_fn=None):
    """Ripartisce una quota corretta a mano tra entro e oltre 12 mesi,
    in proporzione al calcolo originale."""
    if round_fn is None:
        def round_fn(x):
            return round(x, 2)
    if not calc_amount or not calc_beyond:
        return amount, 0.0
    beyond = round_fn(amount * calc_beyond / calc_amount)
    return round_fn(amount - beyond), beyond

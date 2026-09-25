# -*- coding: utf-8 -*-
"""Confronto tra la denominazione presente in Odoo e quella restituita
dall'Anagrafe Tributaria per una partita IVA.

Le due scritture differiscono quasi sempre per forma giuridica, punteggiatura,
maiuscole, accenti e ordine delle parole ("Rossi S.r.l." / "ROSSI SRL",
"Mario Rossi" / "ROSSI MARIO"). Il confronto lavora quindi sui soli token
significativi, senza forma giuridica e congiunzioni, e accetta anche
inclusioni (denominazione più completa da una parte) e piccole differenze
ortografiche.
"""
import re
import unicodedata
from difflib import SequenceMatcher

# Forme giuridiche, congiunzioni e parole di servizio ignorate nel confronto
LEGAL_FORM_TOKENS = {
    'SRL', 'SRLS', 'SPA', 'SAPA', 'SNC', 'SAS', 'SS', 'SC', 'SCARL', 'SCRL',
    'SCPA', 'SCARLPA', 'SRLU', 'COOP', 'COOPERATIVA', 'SOCIETA', 'SOC',
    'RL', 'RESPONSABILITA', 'LIMITATA', 'SEMPLIFICATA', 'PER', 'AZIONI',
    'IN', 'ACCOMANDITA', 'SEMPLICE', 'NOME', 'COLLETTIVO', 'UNIPERSONALE',
    'SOCIO', 'UNICO', 'CON', 'DI', 'DEI', 'DEL', 'DELLA', 'DELLE', 'DEGLI',
    'E', 'ED', 'A', 'AL', 'ALLA', 'IMPRESA', 'INDIVIDUALE', 'DITTA',
    'ONLUS', 'ETS', 'APS', 'ODV', 'SB', 'BENEFIT',
}

# Soglia di somiglianza (0-1) oltre la quale due denominazioni con token
# diversi vengono comunque considerate corrispondenti
SIMILARITY_THRESHOLD = 0.85


def normalize(text):
    """Maiuscolo, senza accenti, '&' come 'E', solo lettere e cifre."""
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', str(text)).replace('&', ' E ')
    text = ''.join(c for c in text if not unicodedata.combining(c)).upper()
    return re.sub(r'[^A-Z0-9]+', ' ', text).strip()


def core_tokens(text):
    """Token significativi della denominazione: senza forme giuridiche e
    senza token di una sola lettera (residui di sigle puntate come
    "S.r.l." o "S.p.A.")."""
    return [t for t in normalize(text).split()
            if len(t) > 1 and t not in LEGAL_FORM_TOKENS]


def names_match(name_a, name_b):
    """True se le due denominazioni identificano plausibilmente lo stesso
    soggetto.

    Regole, in ordine: stessi token (a prescindere dall'ordine); i token di
    una sono inclusi in quelli dell'altra; somiglianza ortografica dei token
    ordinati oltre SIMILARITY_THRESHOLD. Se una delle due non ha token
    significativi (es. solo forma giuridica) il confronto è negativo.
    """
    tokens_a, tokens_b = core_tokens(name_a), core_tokens(name_b)
    if not tokens_a or not tokens_b:
        return False
    set_a, set_b = set(tokens_a), set(tokens_b)
    if set_a == set_b or set_a <= set_b or set_b <= set_a:
        return True
    joined_a = ' '.join(sorted(set_a))
    joined_b = ' '.join(sorted(set_b))
    return SequenceMatcher(None, joined_a, joined_b).ratio() >= SIMILARITY_THRESHOLD

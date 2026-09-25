# -*- coding: utf-8 -*-
"""Controllo formale locale del codice fiscale (persone fisiche) e della
partita IVA, secondo gli algoritmi ufficiali (D.M. 23/12/1976 per il codice
fiscale; algoritmo di controllo della partita IVA).

Implementazione interna senza dipendenze esterne. Gestisce l'omocodia:
nei casi di omocodia l'Anagrafe Tributaria sostituisce, partendo da destra,
le cifre delle posizioni numeriche con lettere secondo la tabella
``OMOCODIA``. Il carattere di controllo viene calcolato sui 15 caratteri
così come risultano dopo la sostituzione, quindi va verificato sulla stringa
effettiva e non sul codice "de-omocodizzato".
"""
import re
import unicodedata

# Sostituzione cifra -> lettera nei casi di omocodia
OMOCODIA = {
    '0': 'L', '1': 'M', '2': 'N', '3': 'P', '4': 'Q',
    '5': 'R', '6': 'S', '7': 'T', '8': 'U', '9': 'V',
}
OMOCODIA_INVERSE = {letter: digit for digit, letter in OMOCODIA.items()}

# Posizioni (0-based) che nel codice fiscale sono numeriche e possono
# essere soggette a omocodia: anno (6,7), giorno (9,10), codice catastale (12,13,14)
NUMERIC_POSITIONS = (6, 7, 9, 10, 12, 13, 14)

# Lettere ammesse per il mese di nascita
MONTH_LETTERS = 'ABCDEHLMPRST'

# Tabelle per il carattere di controllo (posizioni 1-based dispari e pari)
_ODD_VALUES = {
    '0': 1, '1': 0, '2': 5, '3': 7, '4': 9, '5': 13, '6': 15, '7': 17, '8': 19, '9': 21,
    'A': 1, 'B': 0, 'C': 5, 'D': 7, 'E': 9, 'F': 13, 'G': 15, 'H': 17, 'I': 19,
    'J': 21, 'K': 2, 'L': 4, 'M': 18, 'N': 20, 'O': 11, 'P': 3, 'Q': 6, 'R': 8,
    'S': 12, 'T': 14, 'U': 16, 'V': 10, 'W': 22, 'X': 25, 'Y': 24, 'Z': 23,
}
_EVEN_VALUES = {
    **{str(d): d for d in range(10)},
    **{chr(ord('A') + i): i for i in range(26)},
}

_CF_RE = re.compile(r'^[A-Z0-9]{16}$')
_PIVA_RE = re.compile(r'^[0-9]{11}$')

# Codici motivo di non validità formale (stabili, usabili nei messaggi)
REASON_EMPTY = 'empty'
REASON_LENGTH = 'length'
REASON_ALPHABET = 'alphabet'
REASON_STRUCTURE = 'structure'
REASON_MONTH = 'month'
REASON_DAY = 'day'
REASON_CHECK_DIGIT = 'check_digit'

REASON_MESSAGES = {
    REASON_EMPTY: 'codice fiscale non valorizzato',
    REASON_LENGTH: 'lunghezza diversa da 16 caratteri',
    REASON_ALPHABET: 'caratteri non ammessi',
    REASON_STRUCTURE: 'struttura non conforme (lettere e cifre in posizione errata)',
    REASON_MONTH: 'lettera del mese di nascita non valida',
    REASON_DAY: 'giorno di nascita non valido',
    REASON_CHECK_DIGIT: 'carattere di controllo errato',
}


def normalize(value):
    """Maiuscolo, senza spazi interni o esterni. ``None`` -> ''."""
    if not value:
        return ''
    return ''.join(str(value).split()).upper()


def compute_check_char(first15):
    """Carattere di controllo per i primi 15 caratteri del codice fiscale.

    ``first15`` deve essere già normalizzato e composto da soli A-Z0-9.
    """
    total = 0
    for index, char in enumerate(first15[:15]):
        # index 0-based -> posizione 1-based dispari quando index è pari
        if index % 2 == 0:
            total += _ODD_VALUES[char]
        else:
            total += _EVEN_VALUES[char]
    return chr(ord('A') + total % 26)


def _decode_digit(char):
    """Cifra corrispondente a un carattere numerico eventualmente omocodico,
    o None se il carattere non è né cifra né lettera di omocodia."""
    if char.isdigit():
        return char
    return OMOCODIA_INVERSE.get(char)


def validate(value):
    """Valida formalmente un codice fiscale di persona fisica.

    :return: tupla ``(ok, reason, message)``. ``reason`` è ``None`` se valido,
        altrimenti uno dei ``REASON_*``; ``message`` è il testo leggibile.
    """
    cf = normalize(value)
    if not cf:
        return False, REASON_EMPTY, REASON_MESSAGES[REASON_EMPTY]
    if len(cf) != 16:
        return False, REASON_LENGTH, REASON_MESSAGES[REASON_LENGTH]
    if not _CF_RE.match(cf):
        return False, REASON_ALPHABET, REASON_MESSAGES[REASON_ALPHABET]

    # Struttura: lettere nelle posizioni alfabetiche, cifre o lettere di
    # omocodia nelle posizioni numeriche, lettera di controllo finale.
    for index in range(15):
        char = cf[index]
        if index in NUMERIC_POSITIONS:
            if _decode_digit(char) is None:
                return False, REASON_STRUCTURE, REASON_MESSAGES[REASON_STRUCTURE]
        elif not char.isalpha():
            return False, REASON_STRUCTURE, REASON_MESSAGES[REASON_STRUCTURE]
    if not cf[15].isalpha():
        return False, REASON_STRUCTURE, REASON_MESSAGES[REASON_STRUCTURE]

    if cf[8] not in MONTH_LETTERS:
        return False, REASON_MONTH, REASON_MESSAGES[REASON_MONTH]

    day = int(_decode_digit(cf[9]) + _decode_digit(cf[10]))
    # 1-31 uomini, 41-71 donne
    if not (1 <= day <= 31 or 41 <= day <= 71):
        return False, REASON_DAY, REASON_MESSAGES[REASON_DAY]

    if compute_check_char(cf[:15]) != cf[15]:
        return False, REASON_CHECK_DIGIT, REASON_MESSAGES[REASON_CHECK_DIGIT]

    return True, None, 'codice fiscale formalmente valido'


def is_valid(value):
    return validate(value)[0]


def is_omocodico(value):
    """True se il codice contiene lettere di omocodia nelle posizioni numeriche."""
    cf = normalize(value)
    if len(cf) != 16:
        return False
    return any(cf[i].isalpha() for i in NUMERIC_POSITIONS)


def base_code(value):
    """Codice fiscale con le lettere di omocodia riconvertite in cifre e il
    carattere di controllo ricalcolato. Utile per confronti: due codici
    omocodici dello stesso soggetto hanno lo stesso ``base_code``."""
    cf = normalize(value)
    if len(cf) != 16:
        return cf
    chars = list(cf[:15])
    for i in NUMERIC_POSITIONS:
        digit = _decode_digit(chars[i])
        if digit is not None:
            chars[i] = digit
    first15 = ''.join(chars)
    return first15 + compute_check_char(first15)


def validate_piva(value):
    """Valida formalmente una partita IVA italiana (11 cifre, cifra di controllo).

    Predisposizione per la fase di verifica delle partite IVA.
    :return: tupla ``(ok, reason, message)``
    """
    piva = normalize(value)
    if piva.startswith('IT'):
        piva = piva[2:]
    if not piva:
        return False, REASON_EMPTY, 'partita IVA non valorizzata'
    if not _PIVA_RE.match(piva):
        return False, REASON_STRUCTURE, 'la partita IVA deve essere composta da 11 cifre'
    if piva == '0' * 11:
        return False, REASON_STRUCTURE, 'partita IVA non ammessa'
    total = 0
    for index, char in enumerate(piva[:10]):
        digit = int(char)
        if index % 2 == 0:
            total += digit
        else:
            doubled = digit * 2
            total += doubled - 9 if doubled > 9 else doubled
    check = (10 - total % 10) % 10
    if check != int(piva[10]):
        return False, REASON_CHECK_DIGIT, 'cifra di controllo della partita IVA errata'
    return True, None, 'partita IVA formalmente valida'


def is_valid_piva(value):
    return validate_piva(value)[0]


# ---------------------------------------------------------------------------
# Coerenza delle prime sei lettere con cognome e nome (D.M. 23/12/1976)
# ---------------------------------------------------------------------------
VOWELS = 'AEIOU'


def letters_only(text):
    """Solo lettere A-Z maiuscole: accenti rimossi, apostrofi, spazi e
    caratteri non alfabetici eliminati, come fa l'Anagrafe Tributaria."""
    if not text:
        return ''
    normalized = unicodedata.normalize('NFKD', str(text))
    return ''.join(c for c in normalized.upper() if 'A' <= c <= 'Z')


def surname_code(surname):
    """Tre lettere del cognome: consonanti in ordine, poi vocali, X di
    riempimento."""
    text = letters_only(surname)
    consonants = [c for c in text if c not in VOWELS]
    vowels = [c for c in text if c in VOWELS]
    return ''.join((consonants + vowels)[:3]).ljust(3, 'X')


def name_code(name):
    """Tre lettere del nome: con almeno quattro consonanti si prendono la
    prima, la terza e la quarta; altrimenti come per il cognome."""
    text = letters_only(name)
    consonants = [c for c in text if c not in VOWELS]
    vowels = [c for c in text if c in VOWELS]
    if len(consonants) >= 4:
        return consonants[0] + consonants[2] + consonants[3]
    return ''.join((consonants + vowels)[:3]).ljust(3, 'X')


def _split_candidates(tokens):
    """Tutte le suddivisioni contigue di ``tokens`` in (cognome, nome), in
    entrambi gli ordini."""
    for i in range(1, len(tokens)):
        first, second = ' '.join(tokens[:i]), ' '.join(tokens[i:])
        yield first, second   # cognome, nome
        yield second, first   # nome, cognome


def expected_name_codes(full_name):
    """Codici a sei lettere compatibili con ``full_name`` (senza duplicati,
    in ordine di plausibilità). Lista vuota se il nome ha una sola parola:
    senza distinzione tra cognome e nome il controllo non è possibile."""
    tokens = [t for t in str(full_name or '').split() if letters_only(t)]
    if len(tokens) < 2:
        return []
    codes = []
    for surname, name in _split_candidates(tokens):
        code = surname_code(surname) + name_code(name)
        if code not in codes:
            codes.append(code)
    # tolleranza per titoli o parole spurie: riprova ignorando una parola
    if len(tokens) >= 3:
        for skip in range(len(tokens)):
            reduced = tokens[:skip] + tokens[skip + 1:]
            for surname, name in _split_candidates(reduced):
                code = surname_code(surname) + name_code(name)
                if code not in codes:
                    codes.append(code)
    return codes


def name_matches(value, full_name):
    """Verifica che le prime sei lettere del codice fiscale siano coerenti
    con ``full_name``.

    :return: tupla ``(ok, expected)``: ``ok`` è ``True`` se coerente o se il
        controllo non è possibile (nome di una sola parola o codice non a
        16 caratteri); ``expected`` è la lista dei codici attesi, utile nei
        messaggi (i primi due sono le suddivisioni più naturali).
    """
    cf = normalize(value)
    if len(cf) != 16:
        return True, []
    expected = expected_name_codes(full_name)
    if not expected:
        return True, []
    return cf[:6] in expected, expected

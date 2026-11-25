"""Calcolo delle scadenze di versamento delle ritenute (giorni festivi italiani)."""
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

# Festivita' nazionali a data fissa (mese, giorno)
FIXED_HOLIDAYS = {
    (1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15),
    (11, 1), (12, 8), (12, 25), (12, 26),
}


def easter_sunday(year):
    """Domenica di Pasqua (algoritmo di Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def is_working_day(day):
    if day.weekday() >= 5:
        return False
    if (day.month, day.day) in FIXED_HOLIDAYS:
        return False
    if day == easter_sunday(day.year) + timedelta(days=1):
        return False
    return True


def next_working_day(day):
    while not is_working_day(day):
        day += timedelta(days=1)
    return day


def withholding_due_date(payment_date):
    """Il 16 del mese successivo al pagamento.

    Le scadenze dal 1 al 20 agosto slittano al 20 agosto; se il giorno
    risultante e' festivo o cade nel fine settimana, si passa al primo
    giorno lavorativo successivo.
    """
    due = (payment_date + relativedelta(months=1)).replace(day=16)
    if due.month == 8 and due.day <= 20:
        due = due.replace(day=20)
    return next_working_day(due)


def period_of(day):
    """Mese di competenza del versamento nel formato AAAA-MM."""
    return "%04d-%02d" % (day.year, day.month)

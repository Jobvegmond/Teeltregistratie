"""
De week van de app: zondag t/m zaterdag (weekdefinitie B, UI-standaard).
Het weeknummer is dat van de ISO-week die op de maandag erna begint, dus de
zondag telt al mee met de nieuwe week. Teeltcodes en plantweken blijven de
ISO-week van de plantdatum; dit gaat alleen over kalenderweken (kop, perioden,
watergift). Tests in tests/test_weken.py.
"""
from datetime import date, timedelta


def week_begin(dag):
    """De zondag waarmee de week van `dag` begint."""
    return dag - timedelta(days=(dag.weekday() + 1) % 7)


def week_sleutel(dag):
    """(jaar, week) van `dag`; het jaar is dat van de week, niet van de dag (zo 27-12-2026 = (2026, 53))."""
    jaar, week, _ = (dag + timedelta(days=1)).isocalendar()
    return jaar, week


def weeknummer(dag):
    return week_sleutel(dag)[1]


def laatste_week(jaar):
    """Het hoogste weeknummer van een jaar (52 of 53)."""
    return date(jaar, 12, 28).isocalendar()[1]


def week_zondag(jaar, week):
    """De zondag waarmee week `week` van `jaar` begint; een week 53 die niet bestaat wordt de laatste week."""
    week = min(week, laatste_week(jaar))
    return date.fromisocalendar(jaar, week, 1) - timedelta(days=1)


def week_dagen(jaar, week):
    """(zondag, zaterdag) van de week."""
    zondag = week_zondag(jaar, week)
    return zondag, zondag + timedelta(days=6)

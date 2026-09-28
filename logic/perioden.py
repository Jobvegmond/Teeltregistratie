"""
Perioden (week, maand, kwartaal, jaar) als sleutels, met hun grenzen, bladeren
(◀ ▶) en de vergelijkingsperiode (vorige periode of dezelfde periode vorig
jaar). Alleen rekenwerk; tests in tests/test_perioden.py.
"""
from datetime import date, timedelta

PERIODEN = ("Week", "Maand", "Kwartaal", "Jaar")
MAANDNAMEN_KORT = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


def periode_sleutel(d, periode_naam):
    """
    (sorteersleutel, label) voor een datum, op de gekozen periode-granulariteit
    ("Week"/"Maand"/"Kwartaal"/"Jaar"). De sleutel sorteert chronologisch; het
    label is wat er in de grafieken en tabellen komt te staan.
    """
    if periode_naam == "Week":
        jaar, week, _ = d.isocalendar()
        return (jaar, week), f"Wk {week} - {jaar}"
    if periode_naam == "Maand":
        return (d.year, d.month), f"{MAANDNAMEN_KORT[d.month - 1]} {d.year}"
    if periode_naam == "Kwartaal":
        kwartaal = (d.month - 1) // 3 + 1
        return (d.year, kwartaal), f"{d.year} K{kwartaal}"
    return (d.year,), str(d.year)


def periode_grenzen(sleutel, periode_naam):
    """Eerste en laatste dag (beide inclusief) van een periode uit periode_sleutel."""
    if periode_naam == "Week":
        jaar, week = sleutel
        # Week 53 bestaat niet elk jaar; dan de laatste week van dat jaar.
        week = min(week, date(jaar, 12, 28).isocalendar()[1])
        van = date.fromisocalendar(jaar, week, 1)
        return van, van + timedelta(days=6)
    if periode_naam == "Maand":
        jaar, maand = sleutel
        volgende = date(jaar + 1, 1, 1) if maand == 12 else date(jaar, maand + 1, 1)
        return date(jaar, maand, 1), volgende - timedelta(days=1)
    if periode_naam == "Kwartaal":
        jaar, kwartaal = sleutel
        van = date(jaar, 3 * kwartaal - 2, 1)
        volgende = date(jaar + 1, 1, 1) if kwartaal == 4 else date(jaar, 3 * kwartaal + 1, 1)
        return van, volgende - timedelta(days=1)
    return date(sleutel[0], 1, 1), date(sleutel[0], 12, 31)


def periode_label(sleutel, periode_naam):
    return periode_sleutel(periode_grenzen(sleutel, periode_naam)[0], periode_naam)[1]


def verschuif(sleutel, periode_naam, stappen):
    """De periode `stappen` verder (positief) of terug (negatief)."""
    for _ in range(abs(stappen)):
        van, eind = periode_grenzen(sleutel, periode_naam)
        dag = eind + timedelta(days=1) if stappen > 0 else van - timedelta(days=1)
        sleutel = periode_sleutel(dag, periode_naam)[0]
    return sleutel


def laatste_volledige(periode_naam, vandaag):
    """De laatste periode die helemaal voorbij is (vandaag telt nog niet mee)."""
    sleutel = periode_sleutel(vandaag, periode_naam)[0]
    return verschuif(sleutel, periode_naam, -1)


def venster(sleutel, periode_naam, vandaag):
    """
    (van, tot, loopt_nog): de dagen van de periode met data. Loopt de periode
    nog, dan tot en met gisteren (de dag van vandaag is nog niet compleet).
    """
    van, eind = periode_grenzen(sleutel, periode_naam)
    gisteren = vandaag - timedelta(days=1)
    return van, min(eind, gisteren), eind > gisteren


def vergelijk_venster(sleutel, periode_naam, soort, vandaag):
    """
    (van, tot, label) van de vergelijkingsperiode: soort "vorige" = de periode
    ervoor, "vorig_jaar" = dezelfde periode een jaar eerder. Loopt de gekozen
    periode nog, dan de vergelijking tot even ver na het begin, anders
    vergelijk je een halve week met een hele.
    """
    van, tot, _ = venster(sleutel, periode_naam, vandaag)
    ander = vergelijk_sleutel(sleutel, periode_naam, soort)
    v_van, v_eind = periode_grenzen(ander, periode_naam)
    return v_van, min(v_eind, v_van + (tot - van)), periode_label(ander, periode_naam)


def vergelijk_sleutel(sleutel, periode_naam, soort):
    """De vergelijkingsperiode: "vorige" = de periode ervoor, "vorig_jaar" = dezelfde een jaar eerder."""
    return verschuif(sleutel, periode_naam, -1) if soort == "vorige" else (sleutel[0] - 1,) + tuple(sleutel[1:])


def kort_label(sleutel, periode_naam, soort):
    """
    Kort label van de vergelijkingsperiode voor de kleine regel: bij vorig jaar
    het jaartal ("2025"), anders de periode zelf ("wk 38", "aug", "K2", "2025").
    """
    ander = vergelijk_sleutel(sleutel, periode_naam, soort)
    if soort != "vorige" or periode_naam == "Jaar":
        return str(ander[0])
    if periode_naam == "Week":
        return f"wk {ander[1]}"
    if periode_naam == "Maand":
        return MAANDNAMEN_KORT[ander[1] - 1]
    return f"K{ander[1]}"

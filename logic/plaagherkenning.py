"""
Plaagherkenning op een foto: Claude (Anthropic API) bekijkt een foto van het gewas of een vangplaat en zegt of
er trips, luis, wittevlieg of iets anders op zit.

- `voorbereiden()` maakt van een upload een JPEG die de API aanneemt (rechtop, hooguit 2576 px, < 5 MB).
- `analyseer()` stuurt de foto naar Claude en geeft een dict met de uitslag (vaste velden, zie SCHEMA).
- `opmerking_tekst()` maakt van een uitslag de tekst voor een opmerking bij een vak.

De API-sleutel komt uit de omgevingsvariabele ANTHROPIC_API_KEY (op de NAS in .env). Zonder sleutel geeft
`beschikbaar()` False en toont de app alleen uitleg.
"""
import base64
import hashlib
import io
import json
import os

MODEL = "claude-opus-5-5"
# Herkennen van kleine insecten is precisiewerk: niet op de laagste stand. Hoger kost vooral wachttijd.
INSPANNING = "high"
MAX_PIXELS = 2576               # lange zijde; groter rekent Claude toch niet mee
MAX_BYTES = 4_500_000           # de API neemt tot 5 MB per afbeelding aan (na base64 iets meer: ruim blijven)

SOORTEN = ("plaag", "ziekte", "nuttig", "schade", "anders")
ZEKERHEDEN = ("zeker", "waarschijnlijk", "mogelijk")
SOORT_LABEL = {"plaag": "Plaag", "ziekte": "Ziekte", "nuttig": "Nuttig (bestrijder)", "schade": "Schade",
               "anders": "Anders"}

SYSTEEM = """Je bent een ervaren gewasbeschermingsadviseur in de Nederlandse glastuinbouw. Je bekijkt foto's van \
een kwekerij van matricaria (Tanacetum parthenium, snijbloem, grondteelt onder glas, LED-belichting, biologische \
bestrijding met roofmijten en sluipwespen naast chemie). De foto is van het gewas (blad, kop, stengel, bloem) of \
van een gele of blauwe vangplaat.

Zoek vooral naar:
- trips (Frankliniella occidentalis e.a.): slanke langwerpige insectjes van 1-2 mm, geel tot bruin; zilverige \
zuigvlekjes met zwarte puntjes (uitwerpselen) op het blad;
- bladluis: peervormige luizen in groen, zwart, roze of geel, vaak in kolonies op de kop of onder het blad; witte \
vervellingshuidjes, honingdauw, roetdauw; luismummies (bol, bruin/goudkleurig) zijn juist een teken van sluipwespen;
- wittevlieg (kas- of tabakswittevlieg): witte vliegjes van 1-2 mm onder het blad, ovale platte larven/poppen;
- mineervlieg: kronkelende vraatgangen in het blad, witte prikstippen van de vrouwtjes, kleine zwart-gele vliegjes;
- spint: fijne gele stippen op het blad, spinsel, mijtjes van < 0,5 mm;
- rupsen en vraatschade; trips- of luisschade aan de kop;
- ziekten: meeldauw (wit poederig), roest (bruine/oranje sporenhoopjes), botrytis (grijs schimmelpluis), \
bladvlekken, verwelking.

Belangrijk:
- Herken ook nuttige insecten en noem ze apart als "nuttig": roofmijten (Amblyseius, Transeius montdorensis), \
sluipwespen en luismummies, gaasvlieglarven, lieveheersbeestjes, roofwantsen (Orius), galmuglarven. Noem een \
bestrijder nooit een plaag.
- Wees eerlijk over wat je kunt zien. Is iets te klein, te wazig of niet goed te onderscheiden, zet dan \
zekerheid "mogelijk" en zeg wat de teler moet doen om het zeker te weten (loep, close-up, onderkant blad).
- Verzin niets: staat er niets op, geef dan geen bevindingen en zeg dat in de samenvatting.
- Bij een vangplaat: schat per soort het aantal op het zichtbare deel.
- Advies kort en praktisch (wat nu te doen of te controleren), geen middelen en doseringen voorschrijven.

Schrijf alles in het Nederlands, kort en zakelijk."""

VRAAG = "Wat zie je op deze foto? Zit er trips, luis, wittevlieg of iets anders op?"

_BEVINDING = {
    "type": "object",
    "properties": {
        "naam": {"type": "string", "description": "Nederlandse naam, bijv. 'trips', 'groene perzikluis'"},
        "soort": {"type": "string", "enum": list(SOORTEN)},
        "zekerheid": {"type": "string", "enum": list(ZEKERHEDEN)},
        "aantal": {"type": "string", "description": "bijv. '± 5', 'tientallen', 'alleen schade'"},
        "stadium": {"type": "string", "description": "bijv. 'volwassen', 'larven', 'eitjes'; leeg als onbekend"},
        "kenmerken": {"type": "string", "description": "waaraan je het herkent en waar op de foto"},
    },
    "required": ["naam", "soort", "zekerheid", "aantal", "stadium", "kenmerken"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "fototype": {"type": "string", "enum": ["gewas", "vangplaat", "anders"]},
        "fotokwaliteit": {"type": "string", "enum": ["goed", "matig", "slecht"]},
        "kwaliteit_tip": {"type": "string", "description": "hoe een betere foto te maken; leeg als goed"},
        "bevindingen": {"type": "array", "items": _BEVINDING},
        "samenvatting": {"type": "string", "description": "één of twee zinnen"},
        "advies": {"type": "string", "description": "wat de teler nu het beste kan doen of controleren"},
    },
    "required": ["fototype", "fotokwaliteit", "kwaliteit_tip", "bevindingen", "samenvatting", "advies"],
    "additionalProperties": False,
}


class AnalyseFout(Exception):
    """Iets ging mis bij de analyse; de tekst is voor de teler bedoeld."""


def beschikbaar():
    """True als er een API-sleutel is."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def sleutel(data):
    """Vaste sleutel per foto, om een uitslag niet twee keer te betalen."""
    return hashlib.sha1(data).hexdigest()


def voorbereiden(data):
    """
    Upload (bytes) → JPEG-bytes: rechtop gezet volgens de EXIF, RGB, lange zijde hooguit MAX_PIXELS en kleiner dan
    MAX_BYTES. Geeft AnalyseFout als het geen leesbare afbeelding is.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        beeld = Image.open(io.BytesIO(data))
        beeld = ImageOps.exif_transpose(beeld)
    except (UnidentifiedImageError, OSError) as fout:
        raise AnalyseFout("Dit bestand is geen foto die de app kan lezen (gebruik JPG of PNG).") from fout
    beeld = beeld.convert("RGB")
    beeld.thumbnail((MAX_PIXELS, MAX_PIXELS))
    for kwaliteit in (90, 80, 70, 60):
        uit = io.BytesIO()
        beeld.save(uit, format="JPEG", quality=kwaliteit)
        if uit.tell() <= MAX_BYTES:
            return uit.getvalue()
    beeld.thumbnail((MAX_PIXELS // 2, MAX_PIXELS // 2))
    uit = io.BytesIO()
    beeld.save(uit, format="JPEG", quality=80)
    return uit.getvalue()


def _client():
    import anthropic
    return anthropic.Anthropic()


def _bericht(jpeg, toelichting=""):
    tekst = VRAAG + (f"\n\nToelichting van de teler: {toelichting.strip()}" if toelichting.strip() else "")
    return [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                     "data": base64.standard_b64encode(jpeg).decode("ascii")}},
        {"type": "text", "text": tekst},
    ]}]


def lees_antwoord(antwoord):
    """Het API-antwoord → dict volgens SCHEMA (AnalyseFout bij een weigering of een afgebroken antwoord)."""
    if antwoord.stop_reason == "refusal":
        raise AnalyseFout("Claude wilde deze foto niet beoordelen. Probeer een andere foto.")
    if antwoord.stop_reason == "max_tokens":
        raise AnalyseFout("Het antwoord van Claude was te lang en is afgebroken. Probeer het nog eens.")
    teksten = [b.text for b in antwoord.content if getattr(b, "type", None) == "text"]
    if not teksten:
        raise AnalyseFout("Claude gaf geen antwoord. Probeer het nog eens.")
    try:
        uitslag = json.loads(teksten[-1])
    except json.JSONDecodeError as fout:
        raise AnalyseFout("Het antwoord van Claude was onleesbaar. Probeer het nog eens.") from fout
    uitslag.setdefault("bevindingen", [])
    return uitslag


def analyseer(jpeg, toelichting="", client=None):
    """
    Stuur een voorbereide foto (JPEG-bytes) naar Claude en geef de uitslag (dict volgens SCHEMA).
    Weigert het model, dan probeert de API het zelf opnieuw op een ander model (server-side fallback).
    """
    import anthropic

    client = client or _client()
    try:
        antwoord = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEEM,
            messages=_bericht(jpeg, toelichting),
            output_config={"effort": INSPANNING, "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as fout:
        raise AnalyseFout("De API-sleutel (ANTHROPIC_API_KEY) klopt niet.") from fout
    except anthropic.PermissionDeniedError as fout:
        raise AnalyseFout("De API-sleutel mag dit model niet gebruiken (of het tegoed is op).") from fout
    except anthropic.RateLimitError as fout:
        raise AnalyseFout("Even te veel aanvragen tegelijk. Probeer het over een minuut opnieuw.") from fout
    except anthropic.BadRequestError as fout:
        raise AnalyseFout(f"Claude kon deze foto niet aannemen: {fout.message}") from fout
    except anthropic.APIStatusError as fout:
        raise AnalyseFout(f"Claude is even niet bereikbaar (fout {fout.status_code}). Probeer het later.") from fout
    except anthropic.APIConnectionError as fout:
        raise AnalyseFout("Geen verbinding met Claude. Is er internet?") from fout
    return lees_antwoord(antwoord)


def kort(uitslag):
    """Eén regel: wat er gevonden is, bijv. 'trips (waarschijnlijk), roofmijt (nuttig)'."""
    delen = []
    for b in uitslag.get("bevindingen", []):
        extra = "nuttig" if b.get("soort") == "nuttig" else b.get("zekerheid", "")
        delen.append(f"{b.get('naam', '?')} ({extra})" if extra else b.get("naam", "?"))
    return ", ".join(delen) if delen else "niets gevonden"


def opmerking_tekst(uitslagen):
    """
    Tekst voor een opmerking bij een vak, uit één of meer uitslagen (lijst van (bestandsnaam, uitslag)).
    """
    regels = []
    for naam, uitslag in uitslagen:
        kop = f"Foto {naam}: {kort(uitslag)}." if len(uitslagen) > 1 else f"Fotoherkenning: {kort(uitslag)}."
        regels.append(kop)
        for b in uitslag.get("bevindingen", []):
            details = "; ".join(x for x in (b.get("aantal"), b.get("stadium")) if x)
            regels.append(f"- {b.get('naam')}: {b.get('zekerheid')}{' · ' + details if details else ''}")
        if uitslag.get("advies"):
            regels.append(f"Advies: {uitslag['advies']}")
    return "\n".join(regels)

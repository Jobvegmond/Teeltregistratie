"""
Plaagherkenning op een foto, zonder Anthropic-API: de teler stuurt in de app (Registreren → Foto) een foto in, die
komt in de wachtrij (tabel foto_beoordeling). De geplande Claude-taak "Foto's beoordelen" op de werklaptop bekijkt
de foto's en schrijft per foto een uitslag; de uurtaak op de NAS zet die terug in de app (fotobeoordeling.py).

Hier staat wat beide kanten delen:
- `voorbereiden()` maakt van een upload een kleine JPEG voor de database (rechtop, hooguit MAX_PIXELS).
- `INSTRUCTIES` en `SCHEMA`: wat Claude moet doen en de vorm van de uitslag (`opdracht()` zet ze samen).
- `controleer()` keurt een uitslag van Claude voordat die naar de NAS gaat.
- `kort()` en `opmerking_tekst()` maken er tekst van voor de app en de opmerking bij het vak.
"""
import hashlib
import io
import json

MAX_PIXELS = 2000               # lange zijde in de database; scherp genoeg voor trips en luis, ± 0,3–0,6 MB
KWALITEIT = 85

SOORTEN = ("plaag", "ziekte", "nuttig", "schade", "anders")
ZEKERHEDEN = ("zeker", "waarschijnlijk", "mogelijk")
FOTOTYPES = ("gewas", "vangplaat", "anders")
FOTOKWALITEIT = ("goed", "matig", "slecht")
SOORT_LABEL = {"plaag": "Plaag", "ziekte": "Ziekte", "nuttig": "Nuttig (bestrijder)", "schade": "Schade",
               "anders": "Anders"}

INSTRUCTIES = """Je bent een ervaren gewasbeschermingsadviseur in de Nederlandse glastuinbouw. Je bekijkt foto's van \
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
        "fototype": {"type": "string", "enum": list(FOTOTYPES)},
        "fotokwaliteit": {"type": "string", "enum": list(FOTOKWALITEIT)},
        "kwaliteit_tip": {"type": "string", "description": "hoe een betere foto te maken; leeg als goed"},
        "bevindingen": {"type": "array", "items": _BEVINDING},
        "samenvatting": {"type": "string", "description": "één of twee zinnen"},
        "advies": {"type": "string", "description": "wat de teler nu het beste kan doen of controleren"},
    },
    "required": ["fototype", "fotokwaliteit", "kwaliteit_tip", "bevindingen", "samenvatting", "advies"],
    "additionalProperties": False,
}


class FotoFout(Exception):
    """Iets ging mis met de foto; de tekst is voor de teler bedoeld."""


def sleutel(data):
    """Vaste sleutel per foto (om dezelfde foto niet twee keer in te sturen)."""
    return hashlib.sha1(data).hexdigest()


def voorbereiden(data):
    """
    Upload (bytes) → JPEG-bytes: rechtop gezet volgens de EXIF, RGB, lange zijde hooguit MAX_PIXELS.
    Geeft FotoFout als het geen leesbare afbeelding is.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        beeld = Image.open(io.BytesIO(data))
        beeld = ImageOps.exif_transpose(beeld)
    except (UnidentifiedImageError, OSError) as fout:
        raise FotoFout("Dit bestand is geen foto die de app kan lezen (gebruik JPG of PNG).") from fout
    beeld = beeld.convert("RGB")
    beeld.thumbnail((MAX_PIXELS, MAX_PIXELS))
    uit = io.BytesIO()
    beeld.save(uit, format="JPEG", quality=KWALITEIT)
    return uit.getvalue()


def opdracht():
    """De opdracht voor de geplande taak: instructies en de vorm van de uitslag (Markdown)."""
    return (f"# Foto's beoordelen\n\n{INSTRUCTIES}\n\n"
            "## Vorm van de uitslag\n\nSchrijf per foto `<id>.json` (UTF-8) met precies dit JSON-schema:\n\n"
            f"```json\n{json.dumps(SCHEMA, ensure_ascii=False, indent=2)}\n```\n")


def controleer(uitslag):
    """Lijst met fouten in een uitslag (leeg = goed); volgt SCHEMA zonder extra bibliotheek."""
    if not isinstance(uitslag, dict):
        return ["de uitslag is geen JSON-object"]
    fouten = []
    velden = SCHEMA["properties"]
    for veld in SCHEMA["required"]:
        if veld not in uitslag:
            fouten.append(f"veld '{veld}' ontbreekt")
    for veld in uitslag:
        if veld not in velden:
            fouten.append(f"onbekend veld '{veld}'")
    for veld, opties in (("fototype", FOTOTYPES), ("fotokwaliteit", FOTOKWALITEIT)):
        if veld in uitslag and uitslag[veld] not in opties:
            fouten.append(f"'{veld}' moet een van {', '.join(opties)} zijn")
    for veld in ("kwaliteit_tip", "samenvatting", "advies"):
        if veld in uitslag and not isinstance(uitslag[veld], str):
            fouten.append(f"'{veld}' moet tekst zijn")
    bevindingen = uitslag.get("bevindingen", [])
    if not isinstance(bevindingen, list):
        return fouten + ["'bevindingen' moet een lijst zijn"]
    for nr, b in enumerate(bevindingen, 1):
        if not isinstance(b, dict):
            fouten.append(f"bevinding {nr} is geen object")
            continue
        for veld in _BEVINDING["required"]:
            if not isinstance(b.get(veld), str):
                fouten.append(f"bevinding {nr}: '{veld}' ontbreekt of is geen tekst")
        if b.get("soort") not in SOORTEN:
            fouten.append(f"bevinding {nr}: 'soort' moet een van {', '.join(SOORTEN)} zijn")
        if b.get("zekerheid") not in ZEKERHEDEN:
            fouten.append(f"bevinding {nr}: 'zekerheid' moet een van {', '.join(ZEKERHEDEN)} zijn")
        for veld in b:
            if veld not in _BEVINDING["properties"]:
                fouten.append(f"bevinding {nr}: onbekend veld '{veld}'")
    return fouten


def kort(uitslag):
    """Eén regel: wat er gevonden is, bijv. 'trips (waarschijnlijk), roofmijt (nuttig)'."""
    delen = []
    for b in uitslag.get("bevindingen", []):
        extra = "nuttig" if b.get("soort") == "nuttig" else b.get("zekerheid", "")
        delen.append(f"{b.get('naam', '?')} ({extra})" if extra else b.get("naam", "?"))
    return ", ".join(delen) if delen else "niets gevonden"


def opmerking_tekst(uitslag):
    """Tekst voor de opmerking (Ziekte/plagen) bij de vakken van een beoordeelde foto."""
    regels = [f"Fotoherkenning: {kort(uitslag)}."]
    for b in uitslag.get("bevindingen", []):
        details = "; ".join(x for x in (b.get("aantal"), b.get("stadium")) if x)
        regels.append(f"- {b.get('naam')}: {b.get('zekerheid')}{' · ' + details if details else ''}")
    if uitslag.get("advies"):
        regels.append(f"Advies: {uitslag['advies']}")
    return "\n".join(regels)

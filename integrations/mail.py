"""
Mail versturen vanaf de NAS: één verzendweg voor alle rapporten (Teelt afgerond, later het dagrapport).

Instellingen in de omgeving (.env.taak); de eerste die compleet is wordt gebruikt:
- Microsoft Graph (standaard sinds 2.25.0): app-registratie "VEM teeltregistratie" met de toepassingsmachtiging
  Mail.Send. GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_GEHEIM en RAPPORT_VAN (de mailbox waarvandaan het verstuurd
  wordt, klimaat@tanacetum.nl). GRAPH_GEHEIM_VERLOOPT (jjjj-mm-dd): vanaf een maand ervoor een waarschuwing.
  Een kopie staat in Verzonden items van die mailbox.
- Direct Send van Microsoft 365 (zonder inloggen, alleen naar adressen binnen het eigen domein):
  SMTP_SERVER=tanacetum-nl.mail.protection.outlook.com, SMTP_POORT=25, RAPPORT_VAN=…@tanacetum.nl. Komt in de
  spam zolang het openbare IP-adres van de NAS niet in het SPF-record van tanacetum.nl staat.
- Of SMTP met inloggen (bijv. Gmail met een app-wachtwoord): SMTP_SERVER, SMTP_POORT (587 = STARTTLS,
  465 = SSL), SMTP_GEBRUIKER, SMTP_WACHTWOORD, RAPPORT_VAN (standaard SMTP_GEBRUIKER). Bij Microsoft 365 staat
  dit in de tenant uit.

Bijlagen met een cid staan in de tekst (<img src="cid:…">), de rest als gewone bijlage. Bij Graph moet het
geheel onder de 3 MB blijven.
"""
import base64
import os
import re
import smtplib
from collections import namedtuple
from datetime import date, timedelta
from email.message import EmailMessage

TIMEOUT = 60
GRAPH = ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_GEHEIM", "RAPPORT_VAN")
SMTP = ("SMTP_SERVER", "SMTP_GEBRUIKER", "SMTP_WACHTWOORD")
DIRECT_SEND = ("SMTP_SERVER", "RAPPORT_VAN")       # poort 25, zonder inloggen
WAARSCHUW_DAGEN = 30                                # zoveel dagen voor het verlopen van het Graph-geheim

# inhoud: bytes; mime: bijv. "image/png"; cid: alleen voor een afbeelding in de tekst.
Bijlage = namedtuple("Bijlage", "naam inhoud mime cid", defaults=(None,))


class MailFout(RuntimeError):
    pass


def instelling(naam, standaard=None):
    """Een instelling uit de omgeving, zonder spaties of een Windows-regeleinde (\r) eromheen."""
    waarde = os.environ.get(naam)
    return waarde.strip() if waarde and waarde.strip() else standaard


def verzendweg():
    """"graph", "direct send", "smtp" of None: welke instellingen compleet zijn (in die volgorde)."""
    if all(instelling(k) for k in GRAPH):
        return "graph"
    if instelling("SMTP_POORT") == "25" and all(instelling(k) for k in DIRECT_SEND):
        return "direct send"
    if all(instelling(k) for k in SMTP):
        return "smtp"
    return None


def afzender():
    return instelling("RAPPORT_VAN") or instelling("SMTP_GEBRUIKER")


def ontvangers(tekst):
    """"a@x.nl, b@x.nl" → ["a@x.nl", "b@x.nl"]."""
    return [a.strip() for a in (tekst or "").split(",") if a.strip()]


def geheim_verloopt():
    """De vervaldatum van het Graph-geheim (GRAPH_GEHEIM_VERLOOPT), of None als die niet (goed) is ingevuld."""
    try:
        return date.fromisoformat(instelling("GRAPH_GEHEIM_VERLOOPT", ""))
    except ValueError:
        return None


def waarschuwing(vandaag=None):
    """Een regel voor het logboek als het Graph-geheim binnen WAARSCHUW_DAGEN verloopt of verlopen is, anders None."""
    verloopt = geheim_verloopt() if verzendweg() == "graph" else None
    if verloopt is None:
        return None
    vandaag = vandaag or date.today()
    if verloopt < vandaag:
        return f"LET OP: het Graph-geheim is verlopen op {verloopt:%d-%m-%Y}; vraag een nieuw geheim aan."
    if verloopt - vandaag <= timedelta(days=WAARSCHUW_DAGEN):
        return (f"LET OP: het Graph-geheim verloopt op {verloopt:%d-%m-%Y} (over {(verloopt - vandaag).days} "
                "dagen); vraag een nieuw geheim aan.")
    return None


def platte_tekst(html_tekst):
    """Een eenvoudige tekstversie van HTML, voor mailprogramma's zonder HTML."""
    tekst = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|h\d|li)>", "\n", html_tekst)
    tekst = re.sub(r"<[^>]+>", "", tekst)
    return re.sub(r"\n\s*\n+", "\n\n", tekst).strip()


def graph_bericht(onderwerp, html_tekst, aan, bijlagen=()):
    """De JSON voor Graph /users/{RAPPORT_VAN}/sendMail."""
    bericht = {"subject": onderwerp, "body": {"contentType": "HTML", "content": html_tekst},
               "toRecipients": [{"emailAddress": {"address": a}} for a in aan]}
    if bijlagen:
        bericht["attachments"] = [
            {"@odata.type": "#microsoft.graph.fileAttachment", "name": b.naam, "contentType": b.mime,
             "contentBytes": base64.b64encode(b.inhoud).decode("ascii"), "isInline": b.cid is not None,
             **({"contentId": b.cid} if b.cid else {})}
            for b in bijlagen]
    return {"message": bericht, "saveToSentItems": True}


def smtp_bericht(onderwerp, tekst, html_tekst, aan, bijlagen=()):
    """Het bericht voor SMTP: tekst + HTML, afbeeldingen met een cid in de HTML, de rest als bijlage."""
    bericht = EmailMessage()
    bericht["Subject"] = onderwerp
    bericht["From"] = afzender()
    bericht["To"] = ", ".join(aan)
    bericht.set_content(tekst)
    bericht.add_alternative(html_tekst, subtype="html")
    html_deel = bericht.get_payload()[1]
    for b in bijlagen:
        if b.cid:
            html_deel.add_related(b.inhoud, *b.mime.split("/"), cid=f"<{b.cid}>", filename=b.naam)
    for b in bijlagen:
        if not b.cid:
            bericht.add_attachment(b.inhoud, *b.mime.split("/"), filename=b.naam)
    return bericht


def _graph(onderwerp, html_tekst, aan, bijlagen):
    """Versturen via Microsoft Graph (client credentials, Mail.Send) namens de mailbox RAPPORT_VAN."""
    import requests
    token = requests.post(
        f"https://login.microsoftonline.com/{instelling('GRAPH_TENANT_ID')}/oauth2/v2.0/token", timeout=TIMEOUT,
        data={"client_id": instelling("GRAPH_CLIENT_ID"), "client_secret": instelling("GRAPH_GEHEIM"),
              "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"})
    if not token.ok:
        raise MailFout(f"aanmelden bij Microsoft mislukt ({token.status_code}): {token.text[:300]}")
    r = requests.post(
        f"https://graph.microsoft.com/v1.0/users/{instelling('RAPPORT_VAN')}/sendMail", timeout=TIMEOUT,
        headers={"Authorization": f"Bearer {token.json()['access_token']}"},
        json=graph_bericht(onderwerp, html_tekst, aan, bijlagen))
    if r.status_code != 202:
        raise MailFout(f"versturen mislukt ({r.status_code}): {r.text[:300]}")


def _smtp(onderwerp, tekst, html_tekst, aan, bijlagen):
    bericht = smtp_bericht(onderwerp, tekst, html_tekst, aan, bijlagen)
    poort = int(instelling("SMTP_POORT", "587"))
    verbinding = smtplib.SMTP_SSL if poort == 465 else smtplib.SMTP
    with verbinding(instelling("SMTP_SERVER"), poort, timeout=TIMEOUT) as smtp:
        if poort != 465:
            smtp.starttls()
        if poort != 25:                 # Direct Send (poort 25) levert af zonder in te loggen
            smtp.login(instelling("SMTP_GEBRUIKER"), instelling("SMTP_WACHTWOORD"))
        smtp.send_message(bericht)


def verstuur(onderwerp, html_tekst, aan, tekst=None, bijlagen=()):
    """Verstuurt de mail over de ingestelde verzendweg en geeft die terug; MailFout als het niet lukt."""
    weg = verzendweg()
    if not weg:
        raise MailFout("het versturen is niet ingesteld (GRAPH_… of SMTP_… in .env.taak)")
    if not aan:
        raise MailFout("geen ontvangers")
    try:
        if weg == "graph":
            _graph(onderwerp, html_tekst, aan, bijlagen)
        else:
            _smtp(onderwerp, tekst or platte_tekst(html_tekst), html_tekst, aan, bijlagen)
    except MailFout:
        raise
    except Exception as e:
        raise MailFout(f"{type(e).__name__}: {e}") from e
    return weg


def verstuur_en_log(soort, sleutel, onderwerp, html_tekst, aan, tekst=None, bijlagen=(), log=None):
    """
    Zoals verstuur(), en elke poging (gelukt of niet) in de mail-log via log(soort, sleutel, onderwerp, aan, weg,
    status, melding), bijv. database.log_mail. Lukt het loggen niet, dan gaat het versturen gewoon door.
    """
    weg, status, melding = verzendweg(), "ok", None
    try:
        weg = verstuur(onderwerp, html_tekst, aan, tekst, bijlagen)
        return weg
    except MailFout as e:
        status, melding = "fout", str(e)
        raise
    finally:
        if log:
            try:
                log(soort, sleutel, onderwerp, ", ".join(aan), weg, status, melding)
            except Exception as e:
                print(f"Mail-log bijwerken mislukt: {e}")

"""Tests voor integrations/mail.py: welke verzendweg, de waarschuwing voor het Graph-geheim en de berichten."""
import base64
import unittest
from datetime import date
from unittest import mock

from integrations import mail

GRAPH = {"GRAPH_TENANT_ID": "t", "GRAPH_CLIENT_ID": "c", "GRAPH_GEHEIM": "g", "RAPPORT_VAN": "klimaat@tanacetum.nl"}
DIRECT = {"SMTP_SERVER": "tanacetum-nl.mail.protection.outlook.com", "SMTP_POORT": "25",
          "RAPPORT_VAN": "klimaat@tanacetum.nl"}
GMAIL = {"SMTP_SERVER": "smtp.gmail.com", "SMTP_POORT": "587", "SMTP_GEBRUIKER": "vem@gmail.com",
         "SMTP_WACHTWOORD": "x"}
PNG = mail.Bijlage("grafiek.png", b"\x89PNG", "image/png", cid="grafiek")
XLSX = mail.Bijlage("data.xlsx", b"PK", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def omgeving(*delen, **extra):
    waarden = {}
    for d in delen:
        waarden.update(d)
    waarden.update(extra)
    return mock.patch.dict("os.environ", waarden, clear=True)


class TestVerzendweg(unittest.TestCase):
    def test_graph_gaat_voor(self):
        with omgeving(DIRECT, GRAPH):
            self.assertEqual(mail.verzendweg(), "graph")

    def test_direct_send_op_poort_25(self):
        with omgeving(DIRECT):
            self.assertEqual(mail.verzendweg(), "direct send")

    def test_smtp_met_inloggen(self):
        with omgeving(GMAIL):
            self.assertEqual(mail.verzendweg(), "smtp")
            self.assertEqual(mail.afzender(), "vem@gmail.com")

    def test_niets_ingesteld_of_alleen_spaties(self):
        with omgeving(GRAPH, GRAPH_GEHEIM="  \r"):
            self.assertIsNone(mail.verzendweg())

    def test_verstuur_zonder_verzendweg_geeft_mailfout(self):
        with omgeving(), self.assertRaises(mail.MailFout):
            mail.verstuur("o", "<p>x</p>", ["a@b.nl"])

    def test_ontvangers(self):
        self.assertEqual(mail.ontvangers(" a@x.nl, ,b@x.nl "), ["a@x.nl", "b@x.nl"])
        self.assertEqual(mail.ontvangers(None), [])


class TestWaarschuwing(unittest.TestCase):
    def test_geen_waarschuwing_ruim_voor_het_verlopen(self):
        with omgeving(GRAPH, GRAPH_GEHEIM_VERLOOPT="2028-11-02"):
            self.assertIsNone(mail.waarschuwing(date(2028, 9, 1)))

    def test_waarschuwing_binnen_een_maand(self):
        with omgeving(GRAPH, GRAPH_GEHEIM_VERLOOPT="2028-11-02"):
            self.assertIn("over 10 dagen", mail.waarschuwing(date(2028, 10, 23)))

    def test_verlopen(self):
        with omgeving(GRAPH, GRAPH_GEHEIM_VERLOOPT="2028-11-02"):
            self.assertIn("verlopen op 02-11-2028", mail.waarschuwing(date(2028, 11, 3)))

    def test_alleen_bij_graph_en_een_geldige_datum(self):
        with omgeving(DIRECT, GRAPH_GEHEIM_VERLOOPT="2028-11-02"):
            self.assertIsNone(mail.waarschuwing(date(2028, 11, 3)))
        with omgeving(GRAPH, GRAPH_GEHEIM_VERLOOPT="nov 2028"):
            self.assertIsNone(mail.waarschuwing(date(2028, 11, 3)))


class TestBerichten(unittest.TestCase):
    def test_graph_bericht_met_bijlagen(self):
        b = mail.graph_bericht("Onderwerp", "<p>x</p>", ["a@x.nl", "b@x.nl"], [PNG, XLSX])
        self.assertTrue(b["saveToSentItems"])
        self.assertEqual([r["emailAddress"]["address"] for r in b["message"]["toRecipients"]], ["a@x.nl", "b@x.nl"])
        inline, los = b["message"]["attachments"]
        self.assertEqual((inline["isInline"], inline["contentId"]), (True, "grafiek"))
        self.assertEqual(base64.b64decode(inline["contentBytes"]), b"\x89PNG")
        self.assertFalse(los["isInline"])
        self.assertNotIn("contentId", los)

    def test_graph_bericht_zonder_bijlagen(self):
        self.assertNotIn("attachments", mail.graph_bericht("O", "<p>x</p>", ["a@x.nl"])["message"])

    def test_smtp_bericht_met_afbeelding_in_de_tekst_en_bijlage(self):
        with omgeving(DIRECT):
            b = mail.smtp_bericht("O", "tekst", '<img src="cid:grafiek">', ["a@x.nl"], [PNG, XLSX])
        self.assertEqual(b["From"], "klimaat@tanacetum.nl")
        self.assertEqual(b.get_content_type(), "multipart/mixed")
        delen = {d.get_content_type(): d for d in b.walk()}
        self.assertEqual(delen["image/png"]["Content-ID"], "<grafiek>")
        self.assertIn("multipart/related", delen)
        self.assertEqual([a.get_filename() for a in b.iter_attachments()], ["data.xlsx"])

    def test_mime_gebruikt_base64_en_blijft_heel(self):
        """Lange HTML met ▲ en °C mag niet als quoted-printable verstuurd worden (kwam via Graph verminkt aan)."""
        html = '<div class="grijs" style="font-size:12px;color:#6B7280;padding-top:2px">▲ +0,3 °C t.o.v. vorige dag</div>' * 20
        with omgeving(DIRECT):
            b = mail.smtp_bericht("O", "tekst ▲ °C", html, ["a@x.nl"])
            ruw = mail.graph_mime("O", "tekst ▲ °C", html, ["a@x.nl"])
        self.assertEqual(b.get_content_type(), "multipart/alternative")
        for deel in b.iter_parts():
            self.assertEqual(deel["Content-Transfer-Encoding"], "base64")
        self.assertEqual(b.get_body(("html",)).get_content().strip(), html)
        self.assertNotIn(b"quoted-printable", base64.b64decode(ruw).lower())

    def test_platte_tekst(self):
        self.assertEqual(mail.platte_tekst("<p>Kas</p><table><tr><td>1</td></tr></table>"), "Kas\n1")


class TestVerstuurEnLog(unittest.TestCase):
    def setUp(self):
        self.log = []

    def schrijf(self, *regel):
        self.log.append(regel)

    def test_gelukt_wordt_gelogd(self):
        with omgeving(GRAPH), mock.patch.object(mail, "_graph") as graph:
            weg = mail.verstuur_en_log("teelt_rapport", "2026-35", "O", "<p>x</p>", ["a@x.nl"], log=self.schrijf)
        graph.assert_called_once()
        self.assertEqual(weg, "graph")
        self.assertEqual(self.log, [("teelt_rapport", "2026-35", "O", "a@x.nl", "graph", "ok", None)])

    def test_mislukt_wordt_gelogd_en_doorgegeven(self):
        with omgeving(DIRECT), mock.patch("smtplib.SMTP", side_effect=OSError("geen verbinding")):
            with self.assertRaises(mail.MailFout):
                mail.verstuur_en_log("teelt_rapport", "2026-35", "O", "<p>x</p>", ["a@x.nl"], log=self.schrijf)
        soort, sleutel, _, _, weg, status, melding = self.log[0]
        self.assertEqual((weg, status), ("direct send", "fout"))
        self.assertIn("geen verbinding", melding)

    def test_mislukt_loggen_stopt_het_versturen_niet(self):
        def kapot(*_):
            raise RuntimeError("database weg")
        with omgeving(GRAPH), mock.patch.object(mail, "_graph"), mock.patch("builtins.print"):
            self.assertEqual(mail.verstuur_en_log("t", None, "O", "<p>x</p>", ["a@x.nl"], log=kapot), "graph")


if __name__ == "__main__":
    unittest.main()

"""
Beheer van inloggebruikers voor de Teeltregistratie-app.

Gebruikersnamen en (bcrypt-)gehashte wachtwoorden worden opgeslagen in de tabel
`gebruikers` in de Supabase-database. De connectiestring komt uit DATABASE_URL
(zie .env), net als in database.py. Er wordt nooit een wachtwoord in platte
tekst opgeslagen.

Gebruik:
    python beheer_gebruikers.py toevoegen <gebruikersnaam> "<Volledige naam>" [email]
    python beheer_gebruikers.py lijst
    python beheer_gebruikers.py verwijderen <gebruikersnaam>

Bij 'toevoegen' wordt het wachtwoord interactief gevraagd (niet als argument,
zodat het niet in je shell-geschiedenis belandt). Een bestaande gebruikersnaam
wordt bijgewerkt.
"""

import contextlib
import getpass
import io
import logging
import sys

# streamlit_authenticator trekt streamlit mee; buiten een Streamlit-run logt dat
# "missing ScriptRunContext"- en cache-ruis naar stderr tijdens de import.
# Die import gebeurt eenmalig hier met stderr gedempt en streamlit-logging op ERROR.
logging.getLogger("streamlit").setLevel(logging.ERROR)
with contextlib.redirect_stderr(io.StringIO()):
    import streamlit_authenticator as stauth  # noqa: E402

import database  # noqa: E402


def _cli_gebruiker():
    """Identificeert wie dit CLI-commando draait, voor het wijzigingenlog."""
    return f"cli:{getpass.getuser()}"


def _toevoegen(args):
    if len(args) < 2:
        print('Gebruik: python beheer_gebruikers.py toevoegen <gebruikersnaam> "<Volledige naam>" [email]')
        return
    username, naam = args[0], args[1]
    email = args[2] if len(args) > 2 else None

    wachtwoord = getpass.getpass("Wachtwoord: ")
    if not wachtwoord:
        print("Geen wachtwoord opgegeven - geannuleerd.")
        return
    if wachtwoord != getpass.getpass("Wachtwoord (herhaal): "):
        print("Wachtwoorden komen niet overeen - geannuleerd.")
        return

    database.init_db()
    wachtwoord_hash = stauth.Hasher.hash(wachtwoord)
    database.voeg_gebruiker_toe(username, naam, wachtwoord_hash, email, gebruiker=_cli_gebruiker())
    print(f"Gebruiker '{username.strip().lower()}' opgeslagen.")


def _lijst(_args):
    database.init_db()
    gebruikers = database.get_alle_gebruikers()
    if not gebruikers:
        print("Nog geen gebruikers.")
        return
    for username, naam, email in gebruikers:
        print(f"  {username}  -  {naam}" + (f"  <{email}>" if email else ""))


def _verwijderen(args):
    if not args:
        print("Gebruik: python beheer_gebruikers.py verwijderen <gebruikersnaam>")
        return
    database.init_db()
    database.verwijder_gebruiker(args[0], gebruiker=_cli_gebruiker())
    print(f"Gebruiker '{args[0].strip().lower()}' verwijderd (indien aanwezig).")


COMMANDOS = {
    "toevoegen": _toevoegen,
    "lijst": _lijst,
    "verwijderen": _verwijderen,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDOS:
        print("Commando's: toevoegen, lijst, verwijderen")
        print('Voorbeeld: python beheer_gebruikers.py toevoegen jan "Jan Jansen"')
        return
    COMMANDOS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()

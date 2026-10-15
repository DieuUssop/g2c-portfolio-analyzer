"""
mettre_a_jour_titres.py — Ajoute à la base locale les LISTES OFFICIELLES des titres cotés.

À lancer avec Internet, sur votre ordinateur (double-clic sur mettre_a_jour_titres.bat, ou dans le
terminal : python mettre_a_jour_titres.py). Durée : une à quelques minutes.

Sources (gratuites, sans compte) :
    1. Euronext : listes des ETF et des actions de Paris, Amsterdam, Bruxelles, Lisbonne, Milan,
       Dublin et Oslo ;
    2. Deutsche Börse Xetra : fichier « All tradable instruments » (ETF, ETC, actions).

Résultat : des milliers de fiches dans data/base/titres.csv (ticker Yahoo Finance, nom officiel,
ISIN, devise ; pour un ETF, l'indice suivi, la région et l'éligibilité au PEA). L'application s'en sert
hors connexion pour reconnaître un ISIN, un symbole ou un libellé d'avis d'opéré. Les fiches
existantes sont complétées, jamais effacées. Une source qui ne répond pas est simplement ignorée
(le site a pu changer d'adresse) : le message le dit, et les autres sources sont quand même lues.
Un compte rendu est écrit dans data/base/mise_a_jour_titres.txt.
"""

import datetime
import re
import sys
import time
import urllib.parse
import urllib.request

from src import base_officielle as bo
from src import base_titres

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Portfolio Tracker (projet etudiant IAE Caen)"
DELAI = 60
MICS_EURONEXT = "XPAR,ALXP,XMLI,XAMS,XBRU,ALXB,XLIS,ALXL,XMSM,XESM,MTAA,ETLX,XOSL,MERK"

# Euronext : formulaire de téléchargement (POST) des listes du site live.euronext.com.
# Plusieurs noms de liste sont essayés (le site les change parfois).
LISTES_EURONEXT = [
    ("ETF", ["track", "etfs", "etf", "trackers"]),
    ("Action", ["stocks"]),
]
URL_EURONEXT = ("https://live.euronext.com/pd/data/{liste}/download?mics={mics}"
                "&display_datapoints=dp_{liste}&display_filters=df_{liste}")
FORMULAIRE_EURONEXT = {"iDisplayLength": "100000", "iDisplayStart": "0", "args[fe_type]": "csv",
                       "args[fe_layout]": "ver", "args[fe_decimal_separator]": ".",
                       "args[fe_date_format]": "d/m/y"}

# Xetra : adresse connue du fichier, sinon recherchée dans les pages de téléchargement
URL_XETRA = ("https://www.xetra.com/resource/blob/1528/fd276b284c2590e4645b8be8e1e5e601/data/"
             "t7-xetr-allTradableInstruments.csv")
PAGES_XETRA = ["https://www.cashmarket.deutsche-boerse.com/cash-en/trading/Tradable-Instruments-Xetra/Downloads",
               "https://www.xetra.com/xetra-en/instruments/instruments/allTradableInstruments"]


def _lire(url, donnees=None):
    corps = urllib.parse.urlencode(donnees).encode() if donnees else None
    requete = urllib.request.Request(url, data=corps, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(requete, timeout=DELAI) as reponse:
        brut = reponse.read()
    for codage in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return brut.decode(codage)
        except UnicodeDecodeError:
            continue
    return brut.decode("utf-8", errors="replace")


def euronext(journal):
    titres = []
    for nature, listes in LISTES_EURONEXT:
        for liste in listes:
            try:
                texte = _lire(URL_EURONEXT.format(liste=liste, mics=urllib.parse.quote(MICS_EURONEXT)),
                              FORMULAIRE_EURONEXT)
                lus = bo.lire_euronext(texte, nature)
            except Exception as erreur:
                journal.append(f"Euronext {liste} : {type(erreur).__name__} {erreur}")
                continue
            if lus:
                journal.append(f"Euronext ({liste}) : {len(lus)} {nature}(s)")
                titres += lus
                break
            journal.append(f"Euronext {liste} : réponse sans titres (début gardé dans euronext_{liste}_brut.txt)")
            try:                 # pour adapter la lecture si Euronext a changé de format
                (base_titres._dossier() / f"euronext_{liste}_brut.txt").write_text(texte[:20000], encoding="utf-8")
            except OSError:
                pass
        time.sleep(1)
    return titres


def xetra(journal):
    adresses = [URL_XETRA]
    for page in PAGES_XETRA:
        try:
            html = _lire(page)
            for lien in re.findall(r'href="([^"]*allTradableInstruments[^"]*\.csv)"', html, re.IGNORECASE):
                adresses.append(urllib.parse.urljoin(page, lien))
        except Exception as erreur:
            journal.append(f"Xetra (page {page}) : {type(erreur).__name__}")
    for adresse in dict.fromkeys(adresses):
        try:
            lus = bo.lire_xetra(_lire(adresse))
        except Exception as erreur:
            journal.append(f"Xetra : {type(erreur).__name__} {erreur} ({adresse})")
            continue
        if lus:
            journal.append(f"Xetra : {sum(t['nature'] == 'ETF' for t in lus)} ETF/ETC, "
                           f"{sum(t['nature'] == 'Action' for t in lus)} actions")
            return lus
    return []


def main():
    journal = [f"Mise à jour du {datetime.datetime.now():%d/%m/%Y %H:%M}"]
    print("Téléchargement des listes officielles (Euronext, Xetra)…")
    titres = euronext(journal) + xetra(journal)
    for ligne in journal[1:]:
        print("  " + ligne)
    if not titres:
        print("Aucune liste n'a pu être téléchargée (pas d'Internet, ou les sites ont changé d'adresse).")
        print("Envoyez data/base/mise_a_jour_titres.txt au créateur du logiciel.")
    fiches = bo.en_fiches(titres)
    avant = len(base_titres.lire_titres())
    base_titres.ajouter_titres(fiches)
    apres = len(base_titres.lire_titres())
    from src import composition_etf
    etf = [f for f in fiches if "ETF" in f["indices"]]
    reconnus = sum(1 for f in etf if composition_etf.indice_suivi(f["ticker"], f["nom"]))
    resume = (f"{len(fiches)} fiches lues ({len(etf)} ETF/ETC, dont {reconnus} rattachés à un indice connu ; "
              f"les autres : thématiques, matières premières, cryptos… classés « Monde (ETF) ») ; "
              f"base locale : {avant} -> {apres} titres.")
    journal.append(resume)
    print(resume)
    try:
        (base_titres._dossier() / "mise_a_jour_titres.txt").write_text("\n".join(journal), encoding="utf-8")
    except OSError:
        pass
    return 0 if titres else 1


if __name__ == "__main__":
    code = main()
    if sys.stdin and sys.stdin.isatty() and "--sans-pause" not in sys.argv:
        input("\nAppuyez sur Entrée pour fermer cette fenêtre…")      # lancé depuis le menu Démarrer
    sys.exit(code)

"""
base_officielle.py — Listes OFFICIELLES des titres cotés (ETF et actions), pour la base locale.

Sources gratuites, sans compte ni clé, téléchargées par mettre_a_jour_titres.py (avec Internet,
sur l'ordinateur de l'utilisateur) :

    - Euronext (Paris, Amsterdam, Bruxelles, Lisbonne, Milan, Dublin, Oslo) : listes des ETF
      (« trackers ») et des actions, au format CSV (Nom ; ISIN ; Symbole ; Marché ; Devise…) ;
    - Deutsche Börse Xetra : fichier « All tradable instruments » (≈ 4 000 ETF et des milliers
      d'actions de toute l'Europe et des États-Unis), CSV séparé par des « ; ».

Chaque titre devient une fiche de la base locale (data/base/titres.csv) : ticker Yahoo Finance
(symbole + suffixe de la place), nom officiel complet, ISIN, devise, et pour un ETF son classement
(indice suivi, région, classe d'actifs : src/classement.py) ; pour une action, son pays d'après
l'ISIN. Les fiches existantes sont complétées, jamais effacées.

Les fonctions de lecture ne dépendent pas d'Internet (testées sur des extraits) ; le
téléchargement est dans mettre_a_jour_titres.py.
"""

import csv
import io
import re

# Pays d'un ISIN (2 premières lettres) -> pays du projet (composition_etf.PAYS)
PAYS_ISIN = {
    "FR": "France", "DE": "Allemagne", "NL": "Pays-Bas", "BE": "Belgique", "ES": "Espagne", "IT": "Italie",
    "PT": "Portugal", "IE": "Irlande", "AT": "Autriche", "FI": "Finlande", "LU": "Luxembourg", "GR": "Grèce",
    "SE": "Suède", "DK": "Danemark", "NO": "Norvège", "PL": "Pologne", "GB": "Royaume-Uni", "CH": "Suisse",
    "US": "États-Unis", "CA": "Canada", "JP": "Japon", "AU": "Australie", "HK": "Hong Kong", "SG": "Singapour",
    "CN": "Chine", "TW": "Taïwan", "KR": "Corée du Sud", "IN": "Inde", "BR": "Brésil", "MX": "Mexique",
    "IL": "Israël", "ZA": "Afrique du Sud", "CZ": "Tchéquie", "HU": "Hongrie", "SK": "Slovaquie",
    "SI": "Slovénie", "NZ": "Nouvelle-Zélande",
}
# Marché Euronext (colonne « Market ») -> suffixe Yahoo Finance
SUFFIXE_EURONEXT = {
    "euronext paris": ".PA", "euronext growth paris": ".PA", "euronext access paris": ".PA",
    "euronext amsterdam": ".AS", "euronext growth amsterdam": ".AS", "euronext brussels": ".BR",
    "euronext growth brussels": ".BR", "euronext lisbon": ".LS", "euronext growth lisbon": ".LS",
    "euronext milan": ".MI", "euronext growth milan": ".MI", "euronext dublin": ".IR",
    "euronext growth dublin": ".IR", "oslo børs": ".OL", "oslo bors": ".OL", "euronext growth oslo": ".OL",
    "euronext expand oslo": ".OL", "trading after hours": ".PA",
}
# MIC (Xetra et autres places du fichier Deutsche Börse) -> suffixe Yahoo Finance
SUFFIXE_MIC = {"XETR": ".DE", "XFRA": ".F", "XPAR": ".PA", "XAMS": ".AS", "XBRU": ".BR", "XMIL": ".MI",
               "XLON": ".L", "XSWX": ".SW", "XVTX": ".SW", "XNYS": "", "XNAS": "", "XWBO": ".VI"}
MOTIF_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")


def _lignes(texte, separateur=";"):
    """Lignes CSV à partir de la ligne d'en-tête (celle qui contient « ISIN »)."""
    lignes = list(csv.reader(io.StringIO((texte or "").lstrip("﻿")), delimiter=separateur))
    for i, ligne in enumerate(lignes):
        if any(c.strip().upper() == "ISIN" for c in ligne):
            entete = [c.strip() for c in ligne]
            return [dict(zip(entete, [c.strip() for c in l])) for l in lignes[i + 1:] if len(l) >= 3]
    return []


def _colonne(ligne, *noms):
    for nom in noms:
        for cle, valeur in ligne.items():
            if cle.lower().replace(".", " ").strip() == nom:
                return valeur
    return ""


def lire_euronext(texte, nature="ETF"):
    """Liste Euronext (CSV « ; ») -> [{"symbole", "suffixe", "isin", "nom", "devise", "nature"}]."""
    titres = []
    for ligne in _lignes(texte):
        isin = _colonne(ligne, "isin").upper()
        symbole = _colonne(ligne, "symbol", "symbole", "mnemo", "mnémo")
        marche = _colonne(ligne, "market", "marché", "marche").lower()
        suffixe = next((s for m, s in SUFFIXE_EURONEXT.items() if marche.startswith(m)), None)
        if not MOTIF_ISIN.match(isin) or not symbole or suffixe is None:
            continue
        titres.append({"symbole": symbole.upper(), "suffixe": suffixe, "isin": isin,
                       "nom": _colonne(ligne, "name", "nom"),
                       "devise": _colonne(ligne, "trading currency", "currency", "devise"), "nature": nature})
    return titres


def lire_xetra(texte):
    """Fichier « All tradable instruments » de Deutsche Börse -> même format que lire_euronext.
    Garde les ETF, ETC / ETN et actions cotés sur Xetra (MIC XETR)."""
    titres = []
    for ligne in _lignes(texte):
        isin = _colonne(ligne, "isin").upper()
        symbole = _colonne(ligne, "mnemonic")
        mic = (_colonne(ligne, "mic code") or "XETR").upper()
        genre = _colonne(ligne, "instrument type", "product type").upper()
        if not MOTIF_ISIN.match(isin) or not symbole or mic not in SUFFIXE_MIC:
            continue
        if genre in ("ETF", "ETFS", "ETP", "ETC", "ETN") or "ETF" in genre:
            nature = "ETF"
        elif genre in ("CS", "COMMON STOCK", "EQUITY", "STOCK", "ADR", "GDR", "PS", "SHARE"):
            nature = "Action"
        else:
            continue
        titres.append({"symbole": symbole.upper(), "suffixe": SUFFIXE_MIC[mic], "isin": isin,
                       "nom": _colonne(ligne, "instrument", "instrument name", "name"),
                       "devise": _colonne(ligne, "settlement currency", "currency"), "nature": nature})
    return titres


def en_fiches(titres):
    """Titres lus -> fiches de la base locale (colonnes de base_titres.COLONNES_TITRES)."""
    from . import classement, composition_etf
    fiches = {}
    for t in titres:
        ticker = t["symbole"] + t["suffixe"]
        if t["nature"] == "ETF":
            k = classement.classer_etf(ticker, t["nom"])
            pays = ""
            region, secteur, classe = k["region"], k["secteur"], k["classe"]
            etiquettes = "ETF;Officiel" + (";PEA" if classement.eligible_pea_synthetique(ticker, t["nom"]) else "")
        else:
            pays = PAYS_ISIN.get(t["isin"][:2], "")
            region = composition_etf.region_du_pays(pays) or ""
            secteur, classe, etiquettes = "", "Actions", "Officiel"
        fiches[ticker] = {"ticker": ticker, "nom": t["nom"], "isin": t["isin"], "pays": pays, "region": region,
                          "secteur": secteur, "classe": classe, "devise": t["devise"], "indices": etiquettes}
    return list(fiches.values())

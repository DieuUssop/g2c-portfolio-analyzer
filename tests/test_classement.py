"""Classement des titres (src/classement.py) : actions françaises, ETF selon l'indice suivi,
ETF éligibles au PEA par swap, obligations, or, monétaire ; éligibilité au PEA."""
import pandas as pd

from src import classement as c
from src import fiscalite


def test_actions_francaises_classees():
    assert c.classer("ORP.PA", "ORPEA")["secteur"] == "Santé"
    assert c.classer("ALHYG.PA", "HYBRIGENICS")["secteur"] == "Santé"
    assert c.classer("STLAP.PA", "STELLANTIS")["secteur"] == "Consommation discrétionnaire"
    engie = c.classer("ENGI.PA", "ENGIE")
    assert (engie["secteur"], engie["pays"], engie["region"]) == ("Services publics", "France", "Europe")
    inconnue = c.classer("XYZ.PA", "Société inconnue")
    assert inconnue["secteur"] == c.NON_CLASSE and inconnue["region"] == "Europe"   # pays d'après la place


def test_secteurs_normalises():
    assert c.normaliser_secteur("Financial Services") == "Finance"
    assert c.normaliser_secteur("Consumer Cyclical") == "Consommation discrétionnaire"
    assert c.normaliser_secteur("Banques") == "Finance"
    assert c.normaliser_secteur("Pétrole et gaz") == "Énergie"
    assert c.normaliser_secteur("") == ""


def test_etf_classes_selon_l_indice_suivi():
    sp = c.classer("PSP5.PA", "Amundi PEA S&P 500 UCITS ETF")
    assert (sp["classe"], sp["region"], sp["secteur"], sp["pea_synthetique"]) == \
        ("Actions", "États-Unis", "ETF diversifié", True)
    em = c.classer("PAEEM.PA", "Amundi PEA MSCI Emerging Markets")
    assert em["region"] == "Émergents" and em["pea_synthetique"]
    assert c.classer("MEUD.PA", "Amundi Stoxx Europe 600")["region"] == "Europe"
    assert c.classer("IEF", "iShares 7-10 Year Treasury Bond")["classe"] == "Obligations"
    assert c.classer("EUN5.DE", "iShares Core € Corp Bond")["secteur"] == "Obligations d'entreprises"
    assert c.classer("4GLD.DE", "Xetra-Gold")["classe"] == "Or"
    assert c.classer("XEON.DE", "Xtrackers II EUR Overnight Rate Swap")["classe"] == "Monétaire"
    assert c.classer("INRG.L", "iShares Global Clean Energy UCITS ETF")["secteur"] == "Services publics"


def test_fiche_du_referentiel_prioritaire():
    fiche = {"nom": "Apple", "pays": "États-Unis", "region": "États-Unis", "secteur": "Technologie",
             "classe": "Actions"}
    assert c.classer("AAPL", "Apple", fiche)["secteur"] == "Technologie"
    # secteur de la base de titres en anglais : ramené au nom du projet
    assert c.classer("XOM", "Exxon", {"secteur": "Energy"})["secteur"] == "Énergie"
    # Yahoo Finance (gardé en mémoire) pour un titre inconnu
    assert c.classer("FOO", "Foo Inc", yahoo={"secteur": "Healthcare", "pays": "United States"})["secteur"] == "Santé"


def test_eligibilite_pea_avec_etf_synthetiques():
    positions = pd.DataFrame({
        "valeur": [100.0, 100.0, 100.0, 100.0],
        "pays": ["France", "France", "France", "États-Unis"],
        "classe": ["Actions"] * 4,
        "region": ["Europe", "États-Unis", "États-Unis", "États-Unis"],
        "secteur": ["Santé", "ETF diversifié", "ETF diversifié", "Technologie"],
        "pea_synthetique": [False, True, False, False],
    }, index=["ORP.PA", "PSP5.PA", "ETFUS.PA", "AAPL"])
    part, exclus = fiscalite.eligibilite_pea(positions)
    assert part == 0.5 and set(exclus) == {"ETFUS.PA", "AAPL"}

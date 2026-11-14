"""
Exports CSV de courtiers français et européens (fichiers FICTIFS de tests/donnees/courtiers/) :
chacun doit être lu sans l'assistant, avec les bons types, quantités, prix et frais.
"""

from pathlib import Path

import pytest

from src import import_fichier as imp

DOSSIER = Path(__file__).parent / "donnees" / "courtiers"
TITRES = {"LVMH": ("MC.PA", "LVMH Moët Hennessy Louis Vuitton", "EQUITY"),
          "FR0000121014": ("MC.PA", "LVMH Moët Hennessy Louis Vuitton", "EQUITY"),
          "AMUNDI MSCI WORLD": ("CW8.PA", "Amundi MSCI World UCITS ETF", "ETF"),
          "LU1681043599": ("CW8.PA", "Amundi MSCI World UCITS ETF", "ETF")}


def _chercher(requete):
    for cle, (symbole, nom, nature) in TITRES.items():
        if cle in str(requete).upper():
            return [{"symbol": symbole, "longname": nom, "quoteType": nature}]
    return []


@pytest.mark.parametrize("courtier", ["degiro", "fortuneo", "boursedirect", "boursorama", "traderepublic"])
def test_export_de_courtier_lu_automatiquement(courtier):
    brut = (DOSSIER / f"{courtier}_fictif.csv").read_bytes()
    r = imp.importer_automatiquement(brut, chercher=_chercher, marche=lambda t: ({}, None))
    assert r["sur"], r["raison"]
    t = r["transactions"]
    titres = t[t["ticker"] != "ESPECES"].sort_values("date").reset_index(drop=True)
    assert list(titres["type"]) == ["ACHAT", "ACHAT", "VENTE"]
    assert list(titres["ticker"]) == ["MC.PA", "CW8.PA", "MC.PA"]
    assert list(titres["quantite"]) == [1, 2, 1]                 # vente DEGIRO écrite « -1 » : quantité positive
    assert list(titres["prix"]) == pytest.approx([812.4, 495.1, 690.0])
    assert (titres["frais"] > 0).all()


def test_depot_trade_republic_devient_un_versement():
    brut = (DOSSIER / "traderepublic_fictif.csv").read_bytes()
    t = imp.importer_automatiquement(brut, chercher=_chercher, marche=lambda t: ({}, None))["transactions"]
    versement = t[t["type"] == "VERSEMENT"]
    assert len(versement) == 1 and versement["prix"].iloc[0] == pytest.approx(500.0)


def test_ligne_de_donnees_jamais_prise_pour_les_titres_de_colonnes():
    grille = [["Date", "Produit", "Code ISIN", "Quantité", "", "Cours"],
              ["03-06-2024", "AMUNDI MSCI WORLD UCITS ETF EUR (C)", "LU1681043599", "2", "EUR", "495,10"]]
    assert imp.detecter_ligne_entete(grille) == 0

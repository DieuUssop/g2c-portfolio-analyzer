"""Exports de courtiers à plusieurs tableaux : relevé d'activité CSV d'Interactive Brokers.
Fichier d'exemple fictif (tests/donnees/courtiers), au format réel d'IBKR."""
import os

import pandas as pd
import pytest

from src import import_fichier as imp
from src import releves_courtiers as rc

DOSSIER = os.path.join(os.path.dirname(__file__), "donnees", "courtiers")


def _brut(nom):
    with open(os.path.join(DOSSIER, nom), "rb") as f:
        return f.read()


def test_releve_ibkr_reconnu_et_lu():
    brut = _brut("ibkr_activity_statement.csv")
    assert rc.est_releve_ibkr(imp._texte(brut))
    grille, nature = imp._grille(brut)
    assert nature == "ibkr_csv" and grille[0] == rc.ENTETE
    lignes = [dict(zip(grille[0], l)) for l in grille[1:]]
    operations = [(l["Date"], l["Sens"], l["ISIN"], l["Quantité"], l["Cours"], l["Frais"]) for l in lignes
                  if l["Sens"] != "DIVIDENDE"]
    assert operations == [("2026-07-13", "ACHAT", "FR0011550185", "7", "33.454", "1.17"),     # ESEd -> son ISIN
                          ("2026-03-02", "ACHAT", "US0378331005", "5", "241.2", "1"),
                          ("2026-05-04", "VENTE", "US0378331005", "2", "250.5", "1")]
    # ordre annulé (code Ca), change EUR.USD, sous-totaux : ignorés
    assert rc.IGNOREES == {"annulée": 1, "change (Forex)": 1, "correction de dividende (déduite)": 1}
    dividendes = sorted((l["Date"], l["Montant"], l["Frais"]) for l in lignes if l["Sens"] == "DIVIDENDE")
    # mai : 1,30 $ brut, 0,20 $ de retenue ; août : versement, annulation, nouveau versement = 0,78 $ une fois
    assert dividendes == [("2026-05-15", "1.3", "0.2"), ("2026-08-14", "0.78", "0")]


def test_releve_ibkr_jusqu_aux_transactions():
    tableau, _ = imp.lire_tableau_brut(_brut("ibkr_activity_statement.csv"))
    correspondance = imp.proposer_correspondance(tableau)
    assert not imp.correspondance_complete(correspondance)
    transactions, rapport = imp.appliquer_correspondance(
        tableau, correspondance, identifiants={"FR0011550185": "ESE.PA", "US0378331005": "AAPL"})
    assert not rapport["erreurs"]
    assert list(transactions["type"].value_counts().sort_index().items()) == [("ACHAT", 2), ("DIVIDENDE", 2),
                                                                             ("VENTE", 1)]
    ese = transactions[transactions["ticker"] == "ESE.PA"].iloc[0]
    assert ese["quantite"] == 7 and ese["prix"] == pytest.approx(33.454)


def test_symbole_et_place_sans_isin():
    texte = ("Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,Comm/Fee,Code\n"
             'Trades,Data,Order,Stocks,EUR,ESEd,"2026-07-13, 07:05:17",7,33.454,-1.17,O\n'
             "Financial Instrument Information,Header,Asset Category,Symbol,Description,Conid,Listing Exch\n"
             "Financial Instrument Information,Data,Stocks,ESEd,BNP PARIBAS EASY S&P 500,1,SBF\n")
    grille, _ = rc.grille_ibkr(texte)
    assert grille[1][2] == "ESE.PA" and grille[1][3] == "BNP PARIBAS EASY S&P 500"


def test_csv_utf16_d_excel():
    texte = "date;type;ticker;nom;quantite;prix;frais\n2024-01-15;ACHAT;CW8.PA;Amundi MSCI World;10;420;2,5\n"
    grille, sep = imp._grille(texte.encode("utf-16"))
    assert sep == ";" and grille[1][2] == "CW8.PA"


def test_dates_excel_en_nombre():
    dates = imp.convertir_dates(pd.Series(["45291", "45292.0", "2024-01-02"]))
    assert [d.strftime("%Y-%m-%d") for d in dates] == ["2023-12-31", "2024-01-01", "2024-01-02"]


def test_ticker_et_colonne_place():
    """Ticker « nu » + colonne Place (MC + Euronext Paris -> MC.PA), place inconnue laissée telle quelle.
    (Plantait avec pandas 3 + pyarrow : texte « Arrow » + colonne mixte.)"""
    csv = ("Date;Sens;Ticker;Nom;Place;Quantité;Cours;Frais\n"
           "02/01/2024;Achat;MC;LVMH;Euronext Paris;2;700;1\n"
           "03/01/2024;Achat;SAP;SAP;XETRA;3;150;1\n"
           "04/01/2024;Achat;ABC;Inconnue;Place lointaine;1;10;0\n").encode()
    tableau, _ = imp.lire_tableau_brut(csv)
    correspondance = imp.proposer_correspondance(tableau)
    assert correspondance.get("place")
    transactions, _ = imp.appliquer_correspondance(tableau, correspondance)
    assert list(transactions.sort_values("date")["ticker"]) == ["MC.PA", "SAP.DE", "ABC"]

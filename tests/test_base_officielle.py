"""Listes officielles (Euronext, Xetra) -> fiches de la base locale. Extraits au format des vrais
fichiers (aucun accès à Internet pendant les tests)."""
from src import base_officielle as bo
from src import base_titres, classement

EURONEXT = """﻿Name;ISIN;Symbol;Market;Trading Currency;Open;High;Low;Last;Last Date/Time;Time Zone;Volume;Turnover
European Equities;;;;;;;;;;;;
"15 Oct 2026";;;;;;;;;;;;
"All datapoints provided as of end of last active trading day.";;;;;;;;;;;;
AM PEA MSCI AC ASIA PAC EX JAP;FR0011869312;PAASI;Euronext Paris;EUR;24.1;24.3;24.0;24.2;15/10/2026 17:35;CET;1200;29000
BNPP E S&P 500 EUR C;FR0011550185;ESE;Euronext Paris;EUR;28.1;28.3;28.0;28.2;15/10/2026 17:35;CET;50000;1400000
ISHARES CORE MSCI WORLD;IE00B4L5Y983;IWDA;Euronext Amsterdam;EUR;100;101;99;100.5;15/10/2026 17:35;CET;9000;900000
"""
XETRA = """Market:;XETR
Date Last Update:;15.10.2026
Product Status;Instrument Status;Instrument;ISIN;Product ID;Instrument ID;WKN;Mnemonic;MIC Code;CCP eligible Code;Trading Model Type;Product Assignment Group;Product Assignment Group Description;Designated Sponsor Member ID;Designated Sponsor;Price Range Value;Price Range Percentage;Minimum Quote Size;Instrument Type;Tick Size 1;Settlement Currency
Active;Active;ISHARES CORE MSCI JAPAN IMI UCITS ETF;IE00B4L5YX21;1;2;A0RPWJ;SXR5;XETR;Y;CT;ETF1;ETFs;;;;;;ETF;0.001;EUR
Active;Active;SAP SE O.N.;DE0007164600;3;4;716460;SAP;XETR;Y;CT;DAX;DAX;;;;;;CS;0.01;EUR
Active;Active;SOME WARRANT;DE000XYZ1234;5;6;XYZ123;XYZ;XETR;N;CT;WAR;Warrants;;;;;;WAR;0.01;EUR
"""


def test_liste_euronext():
    titres = bo.lire_euronext(EURONEXT, "ETF")
    assert [(t["symbole"] + t["suffixe"], t["isin"]) for t in titres] == [
        ("PAASI.PA", "FR0011869312"), ("ESE.PA", "FR0011550185"), ("IWDA.AS", "IE00B4L5Y983")]


def test_liste_xetra():
    titres = bo.lire_xetra(XETRA)
    assert [(t["symbole"] + t["suffixe"], t["nature"]) for t in titres] == [("SXR5.DE", "ETF"), ("SAP.DE", "Action")]


def test_fiches_classees_et_base_completee():
    fiches = {f["ticker"]: f for f in bo.en_fiches(bo.lire_euronext(EURONEXT, "ETF") + bo.lire_xetra(XETRA))}
    assert fiches["PAASI.PA"]["region"] == "Asie-Pacifique" and "PEA" in fiches["PAASI.PA"]["indices"]
    assert fiches["SXR5.DE"]["region"] == "Japon"
    assert fiches["IWDA.AS"]["region"] == "Monde (ETF)"
    assert (fiches["SAP.DE"]["pays"], fiches["SAP.DE"]["region"]) == ("Allemagne", "Europe")
    base_titres.ajouter_titres(list(fiches.values()))
    # l'ISIN d'un avis d'opéré est retrouvé hors connexion, avec son ticker Yahoo
    trouve = base_titres.chercher_localement("FR0011869312")
    assert trouve and trouve[0]["symbol"] == "PAASI.PA"
    # un avis au libellé illisible : le nom officiel de la base permet de classer l'ETF
    fiche = base_titres.lire_titres().loc["PAASI.PA"].to_dict()
    k = classement.classer("PAASI.PA", "ETF XYZ", fiche)
    assert k["region"] == "Asie-Pacifique"


def test_noms_compacts_du_fichier_xetra():
    """Vrais noms du fichier Xetra (abrégés, mots collés, code de la part à la fin)."""
    from src import composition_etf as ce
    attendus = {
        "AIS-AM.S+P500 SW.UETFEOCD": "S&P 500", "X(IE)-MSCIACWLDSC 1C": "MSCI World Small Cap",          # ACWI petites capitalisations
        "ISHSIII-CORE MSCI WLD DLA": "MSCI World", "UBS FDSO-U.MS.AC AXJ DLA": "MSCI AC Asia Pacific ex Japan",
        "XT.-S+P500EW 2CHEOA": "S&P 500 Equal Weight", "X.IEX.NDQ100SW 1DDLD": "Nasdaq-100",
        "ISHSIII-C.EO GOV. B.EODIS": "Emprunts d'État zone euro", "INVESCOM2-EUR COR B ESG A": "Obligations d'entreprises euro",
        "VANG.UK GILT LS ACC": "Emprunts d'État britanniques", "UBS BBG JP.GOV1-3 UE HEOA": "Emprunts d'État japonais",
        "VANG.FTSE D.E.XUK ETF EOA": "MSCI Europe ex UK", "MUL AMUN ASIA-E-J ETF ACC": "MSCI AC Asia ex Japan",
        "ISHSIII-C.MSCI JP.IMI DLA": "MSCI Japan", "VANG.USD EM G.BD UETF DLD": "Obligations émergentes en dollars",
        "JPM-GEM REI SPA UE DLD": "MSCI Emerging Markets",                # JPM = J.P. Morgan, pas le Japon
    }
    for nom, indice in attendus.items():
        assert ce.indice_suivi("X.DE", nom) == indice, nom
    # ETC, cryptos, produits à effet de levier : pas un indice d'actions
    for nom in ("LEVERAGE SHARES 3NVDA ETP", "BITWISE EURO CORE BITCOIN", "HANETF ETC O.END ZT EUAS"):
        assert ce.indice_suivi("X.DE", nom) is None, nom

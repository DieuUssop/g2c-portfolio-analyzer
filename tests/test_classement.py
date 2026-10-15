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


# ----------------------------------------------------------------------
# ETF : beaucoup plus d'indices reconnus, libellés abrégés des avis, catégories Yahoo, swap PEA
# ----------------------------------------------------------------------
NOMS_ET_INDICES = {
    "AM P AP M AC AP EX JAP ETF-C": "MSCI AC Asia Pacific ex Japan",      # avis d'opéré de Kévin
    "Amundi PEA MSCI AC Asia Pacific ex Japan ESG": "MSCI AC Asia Pacific ex Japan",
    "BNP P.EASY S&P500 UCITS ETF": "S&P 500", "LYX PEA SP500": "S&P 500", "AM.C.C.40 UC.ETF C": "CAC 40",
    "AM PEA MSCI EMERG ESG": "MSCI Emerging Markets", "AM P EM ASIA": "MSCI EM Asia",
    "Vanguard FTSE All-World UCITS ETF": "MSCI ACWI", "SPDR MSCI ACWI IMI": "MSCI ACWI",
    "iShares MSCI World Small Cap": "MSCI World Small Cap", "iShares Core MSCI Japan IMI": "MSCI Japan",
    "Amundi Japan Topix": "MSCI Japan", "iShares Core MSCI Pacific ex-Japan": "MSCI Pacific ex Japan",
    "Xtrackers MSCI Emerging Markets Asia": "MSCI EM Asia", "AM MSCI LATIN AMERICA": "MSCI EM Latin America",
    "iShares MSCI China A": "MSCI China", "Amundi MSCI India": "MSCI India", "iShares MSCI Korea": "MSCI Korea",
    "Amundi PEA Nasdaq-100": "Nasdaq-100", "Invesco S&P 500 Equal Weight": "S&P 500 Equal Weight",
    "Vanguard Total Stock Market": "US Total Market", "Xtrackers Russell 2000": "Russell 2000",
    "Amundi Stoxx Europe 600": "MSCI Europe", "Amundi MSCI EMU": "MSCI EMU", "Xtrackers Euro Stoxx 50": "Euro Stoxx 50",
    "Amundi MSCI Europe Small Cap": "MSCI Europe Small Cap", "AMUNDI PEA PME": "France petites et moyennes valeurs",
    "iShares Core FTSE 100": "FTSE 100", "iShares Core DAX": "DAX",
    "iShares Core € Corp Bond": "Obligations d'entreprises euro", "iShares € Govt Bond 1-3yr": "Emprunts d'État zone euro",
    "iShares € Inflation Linked Govt Bond": "Obligations indexées sur l'inflation euro",
    "iShares Euro High Yield Corp Bond": "Haut rendement euro",
    "iShares Core Global Aggregate Bond": "Obligations agrégées mondiales",
    "iShares J.P. Morgan $ EM Bond": "Obligations émergentes en dollars",
    "Xtrackers USD Corporate Bond": "Obligations d'entreprises américaines",
    "iShares 7-10 Year Treasury Bond": "Emprunts d'État américains",
}


def test_beaucoup_d_etf_reconnus_par_leur_nom():
    from src import composition_etf as ce
    for nom, indice in NOMS_ET_INDICES.items():
        assert ce.indice_suivi("INCONNU.PA", nom) == indice, nom
    assert len(ce.PAYS_PAR_INDICE) >= 50 and len(ce.ETF_INDICE) >= 100
    for indice in ce.PAYS_PAR_INDICE:                      # chaque indice a une région
        assert ce.region_de_l_indice(indice), indice


def test_etf_asie_pacifique_de_kevin():
    """« AM P AP M AC AP EX JAP ETF-C » (Amundi PEA MSCI AC Asia Pacific ex Japan) : Asie, éligible au
    PEA par swap, et JAMAIS compté comme une action française parce qu'il est coté à Paris."""
    from src import expositions as ex
    etf = c.classer("XYZ.PA", "AM P AP M AC AP EX JAP ETF-C")
    assert (etf["region"], etf["pea_synthetique"], etf["indice"]) == ("Asie-Pacifique", True,
                                                                       "MSCI AC Asia Pacific ex Japan")
    assert etf["pays"] == ""
    positions = pd.DataFrame({"nom": ["AM P AP M AC AP EX JAP ETF-C"], "valeur": [1000.0], "classe": ["Actions"],
                              "pays": [""], "region": [etf["region"]], "secteur": [etf["secteur"]],
                              "devise": ["EUR"], "indice": [etf["indice"]], "duration": [None]},
                             index=["XYZ.PA"])
    tr = ex.transparence(positions)
    pays = tr.groupby("pays")["poids"].sum()
    assert "France" not in pays.index
    for p in ("Chine", "Taïwan", "Inde", "Australie", "Corée du Sud"):
        assert pays[p] > 0.05, p


def test_categorie_yahoo_quand_le_nom_ne_dit_rien():
    inconnu = c.classer("XYZ.PA", "AMUNDI ETF XYZ")
    assert inconnu["region"] == "Monde (ETF)" and not inconnu["indice"]
    avec_yahoo = c.classer("XYZ.PA", "AMUNDI ETF XYZ",
                           yahoo={"type": "ETF", "nom": "Amundi Index Fund", "categorie": "Japan Large-Cap Equity"})
    assert (avec_yahoo["region"], avec_yahoo["indice"]) == ("Japon", "MSCI Japan")


def test_pea_100_pour_cent_swap_expose_hors_europe_sans_alerte_d_eligibilite():
    """PEA d'ETF par swap (S&P 500, Nasdaq, Asie) : exposition surtout hors Europe — c'est normal —
    et 100 % éligible au PEA."""
    from src import expositions as ex
    noms = {"ESE.PA": "BNP P.EASY S&P500 UCITS ETF", "PUST.PA": "Amundi PEA Nasdaq-100",
            "XYZ.PA": "AM P AP M AC AP EX JAP ETF-C"}
    lignes = []
    for t, n in noms.items():
        k = c.classer(t, n)
        lignes.append({"ticker": t, "nom": n, "valeur": 1000.0, "classe": k["classe"], "pays": k["pays"],
                       "region": k["region"], "secteur": k["secteur"], "devise": "EUR", "indice": k["indice"],
                       "pea_synthetique": k["pea_synthetique"], "duration": None})
    positions = pd.DataFrame(lignes).set_index("ticker")
    part, exclus = fiscalite.eligibilite_pea(positions)
    assert part == 1.0 and exclus == []
    pays = ex.transparence(positions).groupby("pays")["poids"].sum()
    assert pays["États-Unis"] > 0.6 and pays.get("France", 0) < 0.01


def test_symboles_des_courtiers():
    from src import import_fichier as imp
    assert imp.normaliser_symbole_courtier("ESEd") == "ESE"              # Interactive Brokers
    assert imp.normaliser_symbole_courtier("BRK B") == "BRK-B"
    assert imp.normaliser_symbole_courtier("ESE SBF") == "ESE.PA"        # code de place IBKR
    assert imp.normaliser_symbole_courtier("SAP@IBIS") == "SAP.DE"
    assert imp.normaliser_symbole_courtier("VUSA LSEETF") == "VUSA.L"
    assert imp.convertir_code_global("ESE:xpar") == "ESE.PA"            # Saxo
    for inchange in ("FR0011550185", "Apple Inc", "MC.PA", "AAPL"):
        assert imp.normaliser_symbole_courtier(inchange) == inchange
    tableau = imp.resoudre_identifiants(["ESE SBF"], memoire=False, chercher=lambda q: [])
    assert tableau.iloc[0]["ticker"] == "ESE.PA" and tableau.iloc[0]["identifiant"] == "ESE SBF"

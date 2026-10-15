"""Effet change / effet marché, dividendes (brut, retenues, net), divisions d'actions non
appliquées, titres reçus sans prix d'achat (scission), date des cours hors connexion."""
import pandas as pd
import pytest

from src import devises, mouvements
from src import import_fichier as imp
from src import interface as ui
from src.analyse import _date_du_cache
from src.portfolio import Portfolio


def _transactions(lignes):
    return pd.DataFrame(lignes, columns=["date", "type", "ticker", "nom", "quantite", "prix", "frais"]).assign(
        date=lambda d: pd.to_datetime(d["date"]))


# ----------------------------------------------------------------------
# Effet change et effet marché
# ----------------------------------------------------------------------
def test_effet_change_et_effet_marche_un_achat():
    """10 actions à 100 $ quand 1 € = 1,25 $ (coût 800 €). Aujourd'hui 120 $ et 1 € = 1,50 $ :
    valeur 800 €, plus-value 0 — le titre a gagné 160 € (effet marché), le dollar en a fait perdre 160."""
    brutes = _transactions([("2024-01-02", "ACHAT", "AAPL", "Apple", 10, 100.0, 0.0)])
    taux = pd.DataFrame({"USD": [1.25]}, index=pd.to_datetime(["2024-01-02"]))
    converties = devises.convertir_transactions(brutes, {"AAPL": ("USD", 1.0)}, taux)
    assert converties["prix"].iloc[0] == pytest.approx(80.0) and converties["taux_change"].iloc[0] == 1.25
    positions = Portfolio(converties).valoriser({"AAPL": 120 / 1.5})
    tableau = devises.decomposer_change(positions, converties, {"AAPL": 120.0}, {"AAPL": ("USD", 1.0)}, {"USD": 1.5})
    ligne = tableau.loc["AAPL"]
    assert ligne["taux_achat"] == pytest.approx(1.25) and ligne["taux_actuel"] == 1.5
    assert ligne["effet_change"] == pytest.approx(-160.0)
    assert ligne["effet_marche"] == pytest.approx(160.0)
    assert ligne["effet_marche"] + ligne["effet_change"] == pytest.approx(positions.loc["AAPL", "pv_latente"])


def test_effet_change_taux_moyen_apres_vente_et_frais():
    """Deux achats à des taux différents puis une vente : le taux d'achat est la moyenne pondérée
    des achats (coût en $ / coût en €), une vente ne la change pas ; effet marché + effet change =
    plus-value latente, frais d'achat compris (dans l'effet marché)."""
    brutes = _transactions([("2024-01-02", "ACHAT", "AAPL", "Apple", 10, 100.0, 2.0),
                            ("2024-03-01", "ACHAT", "AAPL", "Apple", 10, 110.0, 2.0),
                            ("2024-06-03", "VENTE", "AAPL", "Apple", 5, 130.0, 2.0)])
    taux = pd.DataFrame({"USD": [1.25, 1.10, 1.08]}, index=pd.to_datetime(["2024-01-02", "2024-03-01", "2024-06-03"]))
    converties = devises.convertir_transactions(brutes, {"AAPL": ("USD", 1.0)}, taux)
    positions = Portfolio(converties).valoriser({"AAPL": 140 / 1.2})
    ligne = devises.decomposer_change(positions, converties, {"AAPL": 140.0}, {"AAPL": ("USD", 1.0)},
                                      {"USD": 1.2}).loc["AAPL"]
    cout_dollars, cout_euros = 10 * 100 + 10 * 110, 10 * 100 / 1.25 + 10 * 110 / 1.10
    assert ligne["taux_achat"] == pytest.approx(cout_dollars / cout_euros)
    assert ligne["effet_change"] == pytest.approx(15 * 140 * (1 / 1.2 - cout_euros / cout_dollars))
    assert ligne["effet_marche"] + ligne["effet_change"] == pytest.approx(positions.loc["AAPL", "pv_latente"])


def test_pas_d_effet_change_en_euros():
    brutes = _transactions([("2024-01-02", "ACHAT", "MC.PA", "LVMH", 2, 700.0, 1.0)])
    positions = Portfolio(brutes).valoriser({"MC.PA": 750.0})
    assert devises.decomposer_change(positions, brutes, {"MC.PA": 750.0}, {"MC.PA": ("EUR", 1.0)}, {}).empty


# ----------------------------------------------------------------------
# Dividendes : brut, retenues, net
# ----------------------------------------------------------------------
def test_dividende_brut_retenues_net():
    """Ligne DIVIDENDE : prix = montant brut, frais = retenues. Le net (brut − retenues) compte dans
    les dividendes ; les retenues ne sont pas des frais de courtage."""
    p = Portfolio(_transactions([("2024-01-02", "ACHAT", "AAPL", "Apple", 50, 100.0, 2.0),
                                 ("2024-05-15", "DIVIDENDE", "AAPL", "Apple", 0, 12.0, 3.6)]))
    r = p.resume()
    assert r["dividendes"] == pytest.approx(8.4) and r["dividendes_bruts"] == pytest.approx(12.0)
    assert r["retenues"] == pytest.approx(3.6) and r["frais_totaux"] == pytest.approx(2.0)


def test_avis_de_dividende_retenues_lues_ou_deduites():
    texte = ("Montant brut : 12,00 USD\nRetenue à la source (15 %) : 1,80 USD\nPrélèvements sociaux : 1,50 USD\n"
             "Net crédité : 8,70 USD")
    assert imp._dividende_brut_et_retenues(texte, "", 0) == ("12.00", 3.3)
    # retenue non détaillée : brut − net
    assert imp._dividende_brut_et_retenues("Montant brut : 100,00\nNet crédité : 87,20", "", 0) == ("100.00", 12.8)
    # pas de montant brut écrit : rien n'est inventé
    assert imp._dividende_brut_et_retenues("Dividende 0,79 x 40", "31,60", 0) == ("31,60", 0)


# ----------------------------------------------------------------------
# Titres reçus sans prix d'achat (scission / spin-off)
# ----------------------------------------------------------------------
def test_vente_sans_achat_signalee_sans_planter():
    p = Portfolio(_transactions([("2024-01-02", "ACHAT", "MC.PA", "LVMH", 2, 700.0, 1.0),
                                 ("2024-06-03", "VENTE", "SOLB.BR", "Syensqo", 4, 90.0, 1.0)]))
    assert [a["type"] for a in p.alertes] == ["vente_sans_achat"]
    assert p.positions.loc["SOLB.BR", "pv_realisee"] == pytest.approx(359.0)
    prix = pd.DataFrame({"MC.PA": [700.0, 720.0, 740.0]}, index=pd.to_datetime(["2024-01-02", "2024-06-03", "2024-06-04"]))
    histo = p.historique(prix)
    assert (histo["valeur"] >= 0).all()                       # pas de quantité négative
    assert histo["gain"].iloc[-1] == pytest.approx(p.resume_valorise({"MC.PA": 740.0})["gain_total"])


def test_titre_detenu_sans_prix_signale():
    p = Portfolio(_transactions([("2024-01-02", "ACHAT", "AI.PA", "Air Liquide", 5, 0.0, 0.0)]))
    assert p.alertes == [{"type": "pru_nul", "ticker": "AI.PA", "nom": "Air Liquide", "quantite": 5.0}]


# ----------------------------------------------------------------------
# Divisions d'actions non appliquées
# ----------------------------------------------------------------------
def _cours_ajustes():
    jours = pd.bdate_range("2024-01-01", "2024-12-31")
    cours = pd.Series(100.0, index=jours)                       # 1 000 avant la division 10 pour 1, ajusté : 100
    return pd.DataFrame({"NVDA": cours})


def test_division_non_appliquee_detectee_puis_ajustee():
    divisions = {"NVDA": [(pd.Timestamp("2024-06-10"), 10.0)]}
    fichier = _transactions([("2024-02-01", "ACHAT", "NVDA", "Nvidia", 3, 1000.0, 1.0),
                             ("2024-07-01", "ACHAT", "NVDA", "Nvidia", 10, 100.0, 1.0)])
    trouvees = mouvements.divisions_non_appliquees(fichier, divisions, _cours_ajustes())
    assert [(d["ticker"], d["facteur"], d["operations"]) for d in trouvees] == [("NVDA", 10.0, 1)]
    ajuste, n = mouvements.appliquer_division(fichier, "NVDA", trouvees[0]["date"], 10.0)
    assert n == 1 and ajuste.loc[0, "quantite"] == 30 and ajuste.loc[0, "prix"] == pytest.approx(100.0)
    assert mouvements.divisions_non_appliquees(ajuste, divisions, _cours_ajustes()) == []


def test_division_deja_appliquee_rien_a_faire():
    fichier = _transactions([("2024-02-01", "ACHAT", "NVDA", "Nvidia", 30, 100.0, 1.0)])
    assert mouvements.divisions_non_appliquees(fichier, {"NVDA": [(pd.Timestamp("2024-06-10"), 10.0)]},
                                               _cours_ajustes()) == []


# ----------------------------------------------------------------------
# Hors connexion : date des cours
# ----------------------------------------------------------------------
def test_date_des_cours_hors_connexion():
    assert _date_du_cache("cache local du 2026-10-08 (Yahoo Finance injoignable)") == pd.Timestamp("2026-10-08")
    assert _date_du_cache("Yahoo Finance (en direct)") is None
    bandeau = ui.entete("T", "S", "s", "cache local du 2026-10-08 (Yahoo Finance injoignable)", "08/10/2026",
                        date_cours=pd.Timestamp("2026-10-08"))
    assert "Hors ligne · cours du 08/10/2026" in bandeau


def test_regroupement_deduit_des_cours_orpea():
    """Avis Crédit Agricole : 2 000 ORPEA à 0,0145 € (décembre 2023). ORPEA a ensuite regroupé
    ses actions (1 nouvelle pour 1 000 anciennes) ; Yahoo ajuste ses cours : 14,50 € ce jour-là.
    Sans correction, 2 000 × ~12 € = 24 000 € au lieu de 2 actions. Le regroupement est déduit des
    cours (sans connexion, ou si Yahoo ne le donne pas) et proposé."""
    jours = pd.bdate_range("2023-11-01", "2026-09-30")
    cours = pd.DataFrame({"ORP.PA": pd.Series(14.5, index=jours), "HYG.PA": pd.Series(30.0, index=jours),
                          "MC.PA": pd.Series(700.0, index=jours)})
    fichier = _transactions([("2023-12-12", "ACHAT", "ORP.PA", "ORPEA", 2000, 0.0145, 1.02),
                             ("2023-12-08", "ACHAT", "HYG.PA", "HYBRIGENICS", 1000, 0.03, 1.02),
                             ("2024-01-10", "ACHAT", "MC.PA", "LVMH", 2, 700.0, 1.0)])
    trouvees = {d["ticker"]: d for d in mouvements.divisions_non_appliquees(fichier, {}, cours)}
    assert set(trouvees) == {"ORP.PA", "HYG.PA"}                 # LVMH colle au cours : rien
    orpea = trouvees["ORP.PA"]
    assert orpea["deduite"] and orpea["facteur"] == pytest.approx(0.001) and orpea["operations"] == 1
    ajuste, n = mouvements.appliquer_division(fichier, "ORP.PA", orpea["date"], orpea["facteur"])
    ligne = ajuste[ajuste["ticker"] == "ORP.PA"].iloc[0]
    assert ligne["quantite"] == pytest.approx(2) and ligne["prix"] == pytest.approx(14.5)
    assert ligne["quantite"] * ligne["prix"] == pytest.approx(29.0)          # montant investi inchangé
    # un prix simplement un peu éloigné du cours (± 30 %) n'est pas pris pour une division
    assert mouvements.division_deduite(_transactions([("2024-01-10", "ACHAT", "MC.PA", "LVMH", 2, 910.0, 1.0)]),
                                       "MC.PA", cours) is None


def test_regroupement_non_ajuste_par_yahoo():
    """Yahoo n'a pas ajusté le regroupement : 0,0145 € puis 14,50 € du jour au lendemain. Les cours
    d'avant sont ramenés dans les nouvelles unités ; ensuite, l'achat de 2 000 actions à 0,0145 €
    est reconnu comme un regroupement de 1 000 en 1 à appliquer."""
    jours = pd.bdate_range("2023-12-01", "2024-12-31")
    serie = pd.Series(14.5, index=jours)
    serie[serie.index < "2024-08-20"] = 0.0145
    cours = pd.DataFrame({"ORP.PA": serie, "MC.PA": pd.Series(700.0, index=jours)})
    corriges, notes = mouvements.corriger_sauts_de_cours(cours, ["ORP.PA", "MC.PA"])
    assert [(n["ticker"], n["facteur"]) for n in notes] == [("ORP.PA", 1000.0)]
    assert corriges["ORP.PA"].iloc[0] == pytest.approx(14.5) and corriges["MC.PA"].iloc[0] == 700.0
    fichier = _transactions([("2023-12-12", "ACHAT", "ORP.PA", "ORPEA", 2000, 0.0145, 1.02)])
    assert mouvements.divisions_non_appliquees(fichier, {}, corriges)[0]["facteur"] == pytest.approx(0.001)
    # une chute réelle de 90 % n'est pas « corrigée »
    chute = pd.Series(10.0, index=jours)
    chute[chute.index >= "2024-08-20"] = 1.0
    assert mouvements.corriger_sauts_de_cours(pd.DataFrame({"X.PA": chute}), ["X.PA"])[1] == []


# ----------------------------------------------------------------------
# Regroupements connus appliqués d'office (ORPEA, Casino, Atos)
# ----------------------------------------------------------------------
def _orpea(*autres):
    return _transactions([("2023-12-12", "ACHAT", "ORP.PA", "ORPEA", 2000, 0.0145, 1.02)] + list(autres))


@pytest.mark.parametrize("cas", ["ajuste_avec_dilution", "historique_depuis_le_regroupement", "sans_cours",
                                 "nouveau_ticker"])
def test_regroupement_orpea_applique_d_office(cas):
    """Avis Crédit Agricole : 2 000 ORPEA achetées avant le regroupement. Quel que soit l'historique
    de Yahoo (cours ajustés aussi pour les augmentations de capital, rapport non « rond » ; historique
    qui ne commence qu'au regroupement ; aucun cours), la ligne est ramenée à 2 actions à 14,50 €."""
    ticker = "EMEIS.PA" if cas == "nouveau_ticker" else "ORP.PA"
    fichier = _orpea().assign(ticker=ticker)
    if cas == "ajuste_avec_dilution":
        cours = pd.DataFrame({ticker: pd.Series(6.0, index=pd.bdate_range("2023-11-01", "2026-09-30"))})
    elif cas in ("historique_depuis_le_regroupement", "nouveau_ticker"):
        cours = pd.DataFrame({ticker: pd.Series(12.4, index=pd.bdate_range("2024-03-22", "2026-09-30"))})
    else:
        cours = None
    ajuste, notes = mouvements.appliquer_operations_connues(fichier, cours)
    assert [(n["ticker"], n["operations"]) for n in notes] == [(ticker, 1)]
    ligne = ajuste.iloc[0]
    assert ligne["quantite"] == pytest.approx(2) and ligne["prix"] == pytest.approx(14.5)
    positions = Portfolio(ajuste).valoriser({ticker: 12.4})
    assert positions.loc[ticker, "valeur"] == pytest.approx(24.8)          # et non 24 800 €


def test_regroupements_casino_et_atos():
    fichier = _transactions([("2023-05-02", "ACHAT", "CO.PA", "CASINO GUICHARD", 300, 0.9, 1.0),
                             ("2024-12-02", "ACHAT", "ATO.PA", "ATOS", 50000, 0.0012, 1.0)])
    ajuste, notes = mouvements.appliquer_operations_connues(fichier)
    assert {n["ticker"]: n["facteur"] for n in notes} == {"CO.PA": 0.01, "ATO.PA": 0.0001}
    assert list(ajuste["quantite"]) == pytest.approx([3, 5])
    assert list(ajuste["prix"]) == pytest.approx([90, 12])


def test_regroupement_orpea_deja_applique_ou_posterieur():
    """Rien n'est touché : achat déjà ramené dans les nouvelles unités (2 à 14,50 €), achat après le
    regroupement, droits de souscription ORPEA (un autre titre), autre société."""
    cours = pd.DataFrame({"ORP.PA": pd.Series(12.0, index=pd.bdate_range("2023-11-01", "2026-09-30"))})
    fichier = _transactions([("2023-12-12", "ACHAT", "ORP.PA", "ORPEA", 2, 14.5, 1.02),
                             ("2024-06-03", "ACHAT", "ORP.PA", "ORPEA", 10, 11.0, 1.0),
                             ("2023-12-05", "ACHAT", "FR001400MXO7", "DROITS ORPEA DS24", 16, 0.01, 0.0),
                             ("2023-12-05", "ACHAT", "MC.PA", "LVMH", 1, 700.0, 1.0)])
    ajuste, notes = mouvements.appliquer_operations_connues(fichier, cours)
    assert notes == [] and ajuste.equals(fichier)


def test_regroupement_deduit_malgre_l_ajustement_des_augmentations_de_capital():
    """Cours ajusté de Yahoo à 11 € (et non 14,50 €) : rapport 0,0013, pas tout à fait 1/1 000.
    Pour un facteur de 100 et plus, l'écart toléré est plus large ; pour un petit facteur, non."""
    cours = pd.DataFrame({"X.PA": pd.Series(11.0, index=pd.bdate_range("2023-11-01", "2024-12-31"))})
    fichier = _transactions([("2023-12-12", "ACHAT", "X.PA", "X", 2000, 0.0145, 1.0)])
    assert mouvements.division_deduite(fichier, "X.PA", cours)["facteur"] == pytest.approx(0.001)
    assert mouvements._facteur_rond(12.5, 0.15) is None                    # ni 10 ni 15 (écart > 15 %)
    assert mouvements._facteur_rond(0.0013, 0.15) == pytest.approx(0.001)


def test_valeur_incoherente_signalee():
    positions = Portfolio(_orpea(("2024-01-10", "ACHAT", "MC.PA", "LVMH", 2, 700.0, 1.0))).valoriser(
        {"ORP.PA": 12.4, "MC.PA": 650.0})
    alertes = mouvements.valeurs_incoherentes(positions)
    assert [a["ticker"] for a in alertes] == ["ORP.PA"] and alertes[0]["multiple"] > 500

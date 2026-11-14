"""
Tests des améliorations « confort de l'utilisateur » (revue du 14/11/2026) :
comptes typés et vue « Tous mes comptes », journal et annulations multiples, sauvegardes,
dividendes, allocation cible, Livret A, « Ce qu'il faut retenir », export Excel,
simulateur d'achat, avancement du calcul.
"""

import io

import numpy as np
import pandas as pd
import pytest

from src import (allocation, comptes, consolidation, dividendes, export_excel, livret_a, mouvements,
                 simulation_achat, synthese)

PEA = (b"date,type,ticker,nom,quantite,prix,frais\n"
       b"2024-01-02,VERSEMENT,ESPECES,Versement,0,5000,0\n"
       b"2024-01-15,ACHAT,CW8.PA,Amundi MSCI World,5,450,2\n")
CTO = (b"date,type,ticker,nom,quantite,prix,frais\n"
       b"2024-02-01,ACHAT,CW8.PA,Amundi MSCI World,3,460,2\n"
       b"2024-03-01,ACHAT,MC.PA,LVMH,2,800,2\n"
       b"2024-06-01,SOLDE,ESPECES,Solde saisi,0,300,0\n")


# ----------------------------------------------------------------------
# Espace personnel : versions, journal, type de compte, sauvegardes
# ----------------------------------------------------------------------
def test_plusieurs_annulations_et_journal():
    s = comptes.creer_compte("alice", "motdepasse1")
    pid = s.enregistrer("PEA", PEA)
    v2 = PEA + b"2024-02-15,ACHAT,MC.PA,LVMH,1,800,2\n"
    v3 = v2 + b"2024-03-15,ACHAT,AI.PA,Air Liquide,2,170,2\n"
    s.enregistrer("PEA", v2, identifiant=pid)
    s.enregistrer("PEA", v3, identifiant=pid)
    s.enregistrer("PEA", v3, identifiant=pid)                 # contenu identique : pas de nouvelle version
    journal = s.journal(pid)
    assert [j["action"] for j in journal] == ["ajout", "ajout", "creation"]
    assert journal[0]["n"] == 1 and journal[-1]["operations"] == 2
    s.annuler_derniere_modification(pid)
    assert s.lire(pid) == v2
    s.annuler_derniere_modification(pid)                       # deux crans en arrière
    assert s.lire(pid) == PEA and "precedente" not in s.lister()[0]
    assert s.journal(pid)[0]["action"] == "annulation"
    with pytest.raises(comptes.ErreurCompte):
        s.annuler_derniere_modification(pid)


def test_versions_limitees():
    s = comptes.creer_compte("bruno", "motdepasse1")
    pid = s.enregistrer("CTO", CTO)
    contenu = CTO
    for i in range(comptes.VERSIONS_MAX + 3):
        contenu += f"2024-07-{i + 1:02d},ACHAT,AI.PA,Air Liquide,1,170,1\n".encode()
        s.enregistrer("CTO", contenu, identifiant=pid)
    fiche = s.lister()[0]
    assert len(fiche["versions"]) == comptes.VERSIONS_MAX
    assert len(list(s.dossier.glob(f"{pid}.v*.enc"))) == comptes.VERSIONS_MAX


def test_type_de_compte():
    s = comptes.creer_compte("chloe", "motdepasse1")
    pid = s.enregistrer("Mon PEA", PEA)
    assert s.enveloppe(pid) is None
    s.definir_enveloppe(pid, "PEA")
    assert s.enveloppe(pid) == "PEA" and s.lister()[0]["enveloppe"] == "PEA"
    with pytest.raises(comptes.ErreurCompte):
        s.definir_enveloppe(pid, "Livret")
    s.definir_enveloppe(pid, None)
    assert s.enveloppe(pid) is None


def test_sauvegarde_automatique_restauration_et_mot_de_passe():
    s = comptes.creer_compte("david", "motdepasse1")
    assert s.sauvegarde_automatique("2026-11-01") is None          # rien à sauvegarder
    pid = s.enregistrer("PEA", PEA)
    premiere = s.sauvegarde_automatique("2026-11-01 10:00")
    assert premiere and s.sauvegarde_automatique("2026-11-05") is None       # moins d'une semaine
    s.enregistrer("PEA", CTO, identifiant=pid)
    assert s.sauvegarde_automatique("2026-11-09") is not None
    for jour in ("2026-11-17", "2026-11-25", "2026-12-03"):
        s.sauvegarde_automatique(jour)
    assert len(s.sauvegardes()) == comptes.SAUVEGARDES_MAX
    # le mot de passe change : les sauvegardes sont rechiffrées et restent lisibles
    s.changer_mot_de_passe("motdepasse1", "nouveaumdp2", "nouveaumdp2")
    s = comptes.connecter("david", "nouveaumdp2")
    ancienne = s.sauvegardes()[-1]["id"]                            # contient encore la version PEA ?
    s.restaurer(s.sauvegardes()[0]["id"])
    assert s.lire(pid) == CTO
    with pytest.raises(comptes.ErreurCompte):
        s.restaurer("../../etc")
    assert ancienne


# ----------------------------------------------------------------------
# Vue « Tous mes comptes »
# ----------------------------------------------------------------------
def test_reunir_les_comptes_sans_melanger_les_especes():
    reuni = mouvements.lire(consolidation.reunir([PEA, CTO]))
    assert not reuni["type"].isin(["VERSEMENT", "SOLDE"]).any()
    assert (reuni["ticker"] == "CW8.PA").sum() == 2 and len(reuni) == 3
    assert list(reuni["date"]) == sorted(reuni["date"])
    totaux = consolidation.especes_totales([{"solde_especes": 2748.0, "versements": 5000, "retraits": 0},
                                            {"solde_especes": 300.0, "versements": 0, "retraits": 0},
                                            {"solde_especes": None}])
    assert totaux["solde"] == pytest.approx(3048.0) and totaux["comptes_sans_solde"] == 1
    resume = consolidation.appliquer_especes({"valeur_actuelle": 10_000.0, "solde_especes": None}, totaux)
    assert resume["valeur_compte"] == pytest.approx(13_048.0)
    tableau = consolidation.tableau_par_compte([
        ("PEA", "PEA", {"valeur_actuelle": 3000, "montant_investi": 2500, "gain_total": 500}),
        ("CTO", "CTO", {"valeur_actuelle": 1000, "montant_investi": 900, "gain_total": 100})])
    assert list(tableau["part"]) == pytest.approx([75.0, 25.0])


# ----------------------------------------------------------------------
# Dividendes
# ----------------------------------------------------------------------
def _transactions_dividendes():
    return pd.DataFrame([
        ["2023-01-10", "ACHAT", "MC.PA", "LVMH", 10, 700, 2],
        ["2023-05-01", "DIVIDENDE", "MC.PA", "LVMH", 0, 70, 0],
        ["2024-03-01", "ACHAT", "MC.PA", "LVMH", 10, 750, 2],
        ["2024-04-25", "DIVIDENDE", "MC.PA", "LVMH", 0, 150, 30],        # 7,50 € brut par action, 6 € net
        ["2024-06-01", "ACHAT", "CW8.PA", "Amundi MSCI World", 5, 450, 1],
    ], columns=["date", "type", "ticker", "nom", "quantite", "prix", "frais"]).assign(
        date=lambda d: pd.to_datetime(d["date"]))


def test_dividendes_par_annee_et_estimation():
    tr = _transactions_dividendes()
    annuel = dividendes.par_annee(tr)
    assert annuel[2023] == pytest.approx(70) and annuel[2024] == pytest.approx(120)
    positions = pd.DataFrame({"nom": ["LVMH", "Amundi MSCI World"], "quantite": [20, 5], "valeur": [14_000, 2_500]},
                             index=["MC.PA", "CW8.PA"])
    total, tableau = dividendes.estimation_12_mois(tr, positions, date_fin="2024-12-31")
    assert total == pytest.approx(6 * 20) and list(tableau["ticker"]) == ["MC.PA"]    # l'ETF capitalise : 0
    assert tableau["rendement_pct"].iloc[0] == pytest.approx(120 / 14_000 * 100)


# ----------------------------------------------------------------------
# Allocation cible
# ----------------------------------------------------------------------
def _positions_allocation():
    return pd.DataFrame({
        "nom": ["Amundi MSCI World", "Amundi Emerging", "iShares Govt Bond", "LVMH"],
        "classe": ["Actions", "Actions", "Obligations", "Actions"],
        "region": ["Monde (ETF)", "Émergents", "Europe", "Europe"],
        "quantite": [10, 10, 10, 1], "valeur": [7_000.0, 1_000.0, 1_000.0, 1_000.0]},
        index=["CW8.PA", "AEEM.PA", "EUNH.DE", "MC.PA"])


def test_poches_et_repartition_du_versement():
    p = _positions_allocation()
    actuelle = allocation.repartition_actuelle(p)
    assert actuelle.loc["Actions Monde", "poids"] == pytest.approx(70)
    assert set(actuelle.index) == {"Actions Monde", "Actions émergentes", "Obligations", "Actions Europe"}
    cible = pd.Series({"Actions Monde": 60.0, "Actions émergentes": 20.0, "Obligations": 20.0})
    a_investir = allocation.repartir_versement(actuelle["valeur"], cible, 2_000)
    assert a_investir.sum() == pytest.approx(2_000)
    # total après versement 12 000 € : retards Monde 200, émergents 1 400, obligations 1 400 (au prorata)
    assert a_investir["Actions Europe"] == pytest.approx(0)              # hors cible : rien de plus
    assert a_investir["Actions Monde"] == pytest.approx(2_000 * 200 / 3_000)
    assert a_investir["Actions émergentes"] == pytest.approx(2_000 * 1_400 / 3_000)
    t = allocation.tableau(p, cible, 2_000)
    assert t.loc["Actions émergentes", "ligne"] == "Amundi Emerging"
    assert t["apres"].sum() == pytest.approx(100)
    # gros versement : tous les retards comblés, le reste selon la cible
    gros = allocation.repartir_versement(actuelle["valeur"], cible, 20_000)
    assert gros.sum() == pytest.approx(20_000) and (gros >= 0).all()
    defaut = allocation.cible_par_defaut(actuelle)
    assert defaut.sum() == pytest.approx(100)


# ----------------------------------------------------------------------
# Livret A
# ----------------------------------------------------------------------
def test_livret_a_meme_argent_memes_dates():
    jours = pd.bdate_range("2024-01-02", "2025-12-31")
    histo = pd.DataFrame({"flux": 0.0, "valeur": 11_000.0}, index=jours)
    histo.iloc[0, 0] = 10_000.0
    c = livret_a.comparer(histo)
    # 3 % jusqu'au 31/01/2025, 2,4 % ensuite, 1,7 % à partir d'août 2025 : environ 10 000 × (1 + 3 % + 2,2 %)
    assert 10_450 < c["livret"] < 10_560
    assert c["ecart"] == pytest.approx(11_000 - c["livret"])
    assert livret_a.taux_au(["2026-11-14"]).iloc[0] == pytest.approx(0.017)
    assert livret_a.taux_au(["2023-06-01"]).iloc[0] == pytest.approx(0.03)


# ----------------------------------------------------------------------
# « Ce qu'il faut retenir »
# ----------------------------------------------------------------------
def _res(twr=0.08, ecart=0.02, solde=100.0, jours=200):
    return {"indicateurs": {"twr_annualise": twr},
            "avances": {"twr_portefeuille_meme_periode": 0.30, "twr_indice": 0.30 - ecart},
            "resume": {"gain_total": 1_000.0, "solde_especes": solde}, "jours_de_cotation": jours}


def test_ce_qu_il_faut_retenir():
    alerte = {"dimension": "concentration", "niveau": "alerte", "titre": "Ligne trop grosse : {nom}",
              "pistes": ["Alléger {nom}"], "valeurs": {"nom": "LVMH"}}
    p = synthese.phrases(_res(), [alerte], "MSCI World")
    assert len(p) == 3
    assert "mieux que" in p[0][2] and p[0][3]["indice"] == "MSCI World"
    assert p[1][0] == "alerte" and p[1][3]["nom"] == "LVMH"
    assert p[2][1] == "Piste :" and p[2][2] == "Alléger {nom}"
    p = synthese.phrases(_res(ecart=-0.03, solde=-50), [], "MSCI World")
    assert "moins que" in p[0][2] and p[1][0] == "ok" and p[2][0] == "attention"
    assert "récent" in synthese.phrases(_res(jours=5), [])[0][2]


# ----------------------------------------------------------------------
# Export Excel
# ----------------------------------------------------------------------
def test_export_excel_toutes_les_feuilles():
    jours = pd.bdate_range("2024-01-02", "2024-04-30")
    histo = pd.DataFrame({"valeur": np.linspace(1000, 1100, len(jours)), "apports_nets": 1000.0}, index=jours)
    rendements = histo["valeur"].pct_change()
    positions = pd.DataFrame({"nom": ["LVMH"], "classe": ["Actions"], "region": ["Europe"], "quantite": [2],
                              "pru": [500.0], "cours": [550.0], "valeur": [1100.0], "pv_latente": [100.0],
                              "poids_pct": [100.0]}, index=pd.Index(["MC.PA"], name="ticker"))
    res = {"resume": {"valeur_actuelle": 1100.0, "montant_investi": 1000.0, "gain_total": 100.0,
                      "pv_latentes": 100.0, "pv_realisees": 0.0, "dividendes": 0.0, "frais_totaux": 2.0,
                      "solde_especes": None},
           "positions": positions, "historique": histo,
           "indicateurs": {"rendements": rendements, "twr_annualise": 0.3, "volatilite": 0.1, "max_drawdown": 0.0},
           "transactions": _transactions_dividendes(), "especes": None}
    constat = {"niveau": "attention", "titre": "Une seule ligne", "pistes": ["Diversifier"], "valeurs": {}}
    octets = export_excel.classeur(res, constats=[constat])
    feuilles = pd.read_excel(io.BytesIO(octets), sheet_name=None)
    assert list(feuilles) == ["Résumé", "Positions", "Performance mensuelle", "Transactions", "Dividendes",
                              "Diagnostic"]
    assert len(feuilles["Performance mensuelle"]) == 4 and feuilles["Positions"]["Ticker"].iloc[0] == "MC.PA"


# ----------------------------------------------------------------------
# Simulateur « Et si j'achetais… »
# ----------------------------------------------------------------------
def test_achat_fictif_et_risque_ex_ante():
    contenu, quantite = simulation_achat.contenu_avec_achat(PEA, "mc.pa", "LVMH", 1_000, "2024-06-03", 800)
    t = mouvements.lire(contenu)
    assert quantite == pytest.approx(1.25) and t["ticker"].iloc[-1] == "MC.PA"
    with pytest.raises(ValueError):
        simulation_achat.contenu_avec_achat(PEA, "MC.PA", "LVMH", 0, "2024-06-03", 800)
    alea = np.random.default_rng(1)
    jours = pd.bdate_range("2023-01-02", periods=300)
    prix = pd.DataFrame({"A": 100 * np.cumprod(1 + alea.normal(0, 0.01, 300)),
                         "B": 100 * np.cumprod(1 + alea.normal(0, 0.02, 300))}, index=jours)
    seul_a = simulation_achat.volatilite_ex_ante(prix, pd.DataFrame({"valeur": [1000.0]}, index=["A"]))
    melange = simulation_achat.volatilite_ex_ante(prix, pd.DataFrame({"valeur": [500.0, 500.0]}, index=["A", "B"]))
    assert seul_a == pytest.approx(0.01 * np.sqrt(252), rel=0.15)
    assert melange > seul_a
    avant = {"constats": [{"dimension": "pays", "niveau": "alerte", "titre": "X"}]}
    apres = {"constats": [{"dimension": "secteurs", "niveau": "attention", "titre": "Y"}]}
    nouveaux, disparus = simulation_achat.nouveaux_constats(avant, apres)
    assert [c["titre"] for c in nouveaux] == ["Y"] and [c["titre"] for c in disparus] == ["X"]


def test_avancement_du_calcul():
    from src import analyse
    etapes = []
    analyse.suivre_avancement(lambda part, texte: etapes.append(part))
    try:
        analyse._etape(0.5, "essai")
        analyse.suivre_avancement(lambda part, texte: 1 / 0)       # une erreur d'affichage ne bloque rien
        analyse._etape(0.6, "essai")
    finally:
        analyse.suivre_avancement(None)
    analyse._etape(0.7, "sans suivi")
    assert etapes == [0.5]

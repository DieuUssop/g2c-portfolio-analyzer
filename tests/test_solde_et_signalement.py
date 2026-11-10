"""
Retours de M. Souissi du 10/11/2026 : solde espèces saisi à la main (point de départ), contrôle du solde
insuffisant, relevés déjà importés, titres à vérifier (ISIN, région d'ETF à préciser), corrections de
l'utilisateur, message « Signaler un problème » envoyé par e-mail, compatibilité Mac.
"""
import io
from urllib.parse import parse_qs, urlparse, unquote

import pandas as pd
import pytest

from src import classement, mouvements, signalement
from src.portfolio import Portfolio

BASE = """date,type,ticker,nom,quantite,prix,frais
2024-01-02,ACHAT,ESE.PA,ESE,100,30,2
2024-06-03,VENTE,ESE.PA,ESE,40,35,2
"""


def _ajout(contenu, **operation):
    return mouvements.fusionner(contenu, pd.DataFrame([{"nom": operation.get("ticker", "ESPECES"), "quantite": 0.0,
                                                         "frais": 0.0, **operation}]))


# ----------------------------------------------------------------------
# Solde saisi à la main
# ----------------------------------------------------------------------
def test_solde_saisi_point_de_depart():
    contenu = mouvements.en_csv(mouvements.avec_solde_saisi(BASE.encode(), 500, "2024-06-30"))
    p = Portfolio(io.BytesIO(contenu))
    assert p.solde_especes() == pytest.approx(500)           # les opérations antérieures n'y changent rien
    assert p.solde_saisi() == (pd.Timestamp("2024-06-30"), 500.0)
    apres = _ajout(contenu, date="2024-07-01", type="ACHAT", ticker="ESE.PA", quantite=10, prix=30, frais=1)
    apres = _ajout(mouvements.en_csv(apres), date="2024-07-02", type="VERSEMENT", ticker="ESPECES", prix=100)
    assert Portfolio(io.BytesIO(mouvements.en_csv(apres))).solde_especes() == pytest.approx(500 - 301 + 100)


def test_un_seul_solde_saisi_et_retour_au_calcul():
    t = mouvements.avec_solde_saisi(BASE.encode(), 500, "2024-06-30")
    t = mouvements.avec_solde_saisi(t, 800, "2024-07-31")
    assert list(t.loc[t["type"] == "SOLDE", "prix"]) == [800]
    assert "SOLDE" not in set(mouvements.sans_solde_saisi(t)["type"])


def test_solde_saisi_relu_depuis_le_fichier():
    from src import import_fichier as imp
    contenu = mouvements.en_csv(mouvements.avec_solde_saisi(BASE.encode(), 0, "2024-06-30"))
    t = imp.lire_directement(contenu)
    assert list(t["type"]) == ["ACHAT", "VENTE", "SOLDE"] and t["prix"].iloc[-1] == 0


# ----------------------------------------------------------------------
# Solde insuffisant
# ----------------------------------------------------------------------
def test_achat_qui_depasse_le_solde_bloque():
    contenu = mouvements.en_csv(mouvements.avec_solde_saisi(BASE.encode(), 500, "2024-06-30"))
    trop = _ajout(contenu, date="2024-07-01", type="ACHAT", ticker="ESE.PA", quantite=20, prix=30, frais=1)
    probleme = mouvements.controler_solde(trop)
    assert probleme["type"] == "ACHAT" and probleme["solde"] == pytest.approx(-101)
    assert mouvements.solde_minimum_necessaire(probleme) == pytest.approx(601)
    # une fois le solde indiqué la veille, l'achat passe
    corrige = mouvements.avec_solde_saisi(trop, 601, probleme["veille"])
    assert mouvements.controler_solde(corrige) is None


def test_solde_exactement_zero_permis():
    contenu = mouvements.en_csv(mouvements.avec_solde_saisi(BASE.encode(), 500, "2024-06-30"))
    pile = _ajout(contenu, date="2024-07-01", type="ACHAT", ticker="ESE.PA", quantite=10, prix=49.9, frais=1)
    assert mouvements.controler_solde(pile) is None


def test_sans_solde_connu_pas_de_controle():
    plus = _ajout(BASE.encode(), date="2024-07-01", type="ACHAT", ticker="ESE.PA", quantite=1000, prix=30, frais=1)
    assert mouvements.controler_solde(plus) is None and not mouvements.solde_connu(plus)


def test_retrait_en_premier_ne_dit_rien_du_solde():
    # relevés incomplets : un retrait sans versement connu avant ne permet pas de conclure
    t = _ajout(BASE.encode(), date="2024-11-15", type="RETRAIT", ticker="ESPECES", prix=200)
    assert mouvements.controler_solde(t) is None


def test_achat_en_dollars_converti_pour_le_controle():
    contenu = mouvements.en_csv(mouvements.avec_solde_saisi(BASE.encode(), 1000, "2024-06-30"))
    t = _ajout(contenu, date="2024-07-01", type="ACHAT", ticker="AAPL", quantite=4, prix=220, frais=1)
    assert mouvements.controler_solde(t, {"AAPL": ("USD", 1.0)}, {"USD": 1.10}) is None      # 880 $ = 800 € + 1 €
    t = _ajout(contenu, date="2024-07-01", type="ACHAT", ticker="AAPL", quantite=6, prix=220, frais=1)
    assert mouvements.controler_solde(t, {"AAPL": ("USD", 1.0)}, {"USD": 1.10})["approx"]


# ----------------------------------------------------------------------
# Titres à vérifier, région des ETF, corrections
# ----------------------------------------------------------------------
def test_titres_a_verifier():
    positions = pd.DataFrame({"nom": ["FR0011550185", "Amundi CAC 40", "ETF XYZ", "LVMH"],
                              "region": ["États-Unis", "Europe", "À préciser (ETF)", "Europe"],
                              "secteur": ["ETF diversifié"] * 3 + ["Consommation discrétionnaire"]},
                             index=["FR0011550185", "CACC.PA", "XYZ.PA", "MC.PA"])
    raisons = {tk: r for tk, _, r in classement.titres_a_verifier(positions)}
    assert set(raisons) == {"FR0011550185", "XYZ.PA"}


@pytest.mark.parametrize("ticker,nom", [("CACC.PA", "Amundi CAC 40 UCITS ETF Acc"), ("CAC.PA", "Amundi CAC 40 UCITS ETF Dist"),
                                        ("XYZ.PA", "LYXOR CAC 40 (DR) UCITS ETF"), ("XYZ.PA", "AM.C.C.40 UC.ETF C"),
                                        ("XYZ.PA", "BNP PARIBAS EASY CAC 40 ESG")])
def test_etf_cac40_toujours_en_europe(ticker, nom):
    k = classement.classer(ticker, nom)
    assert k["region"] == "Europe" and k["indice"] == "CAC 40"


def test_etf_inconnu_n_est_plus_range_monde():
    k = classement.classer("XYZ.PA", "AMUNDI ETF XYZ")
    assert k["region"] == "À préciser (ETF)" and k["pays"] == ""


def test_nom_l_emporte_sur_une_categorie_yahoo_contraire():
    k = classement.classer("XYZ.PA", "AMUNDI CAC 40 UCITS ETF",
                           yahoo={"type": "ETF", "nom": "Amundi", "categorie": "Global Large-Cap Blend Equity"})
    assert k["indice"] == "CAC 40" and k["region"] == "Europe"


def test_correction_de_l_utilisateur(tmp_path, monkeypatch):
    from src import base_titres
    from src.analyse import charger_fiches
    monkeypatch.setattr(base_titres, "DOSSIER", tmp_path)
    base_titres.corriger("XYZ.PA", "Mon ETF Japon", "MSCI Japan")
    fiches = charger_fiches()
    assert fiches.loc["XYZ.PA", "nom"] == "Mon ETF Japon"
    k = classement.classer_tous(["XYZ.PA"], {"XYZ.PA": "ETF XYZ"}, fiches)
    assert k.loc["XYZ.PA", "indice"] == "MSCI Japan" and k.loc["XYZ.PA", "region"] == "Japon"


def test_place_de_paris_preferee():
    from src import import_fichier as imp
    assert imp._place_preferee("ESE.PA", "FR0011550185") and not imp._place_preferee("ESEE.DE", "FR0011550185")
    assert imp._place_preferee("SAP.DE", "DE0007164600")


# ----------------------------------------------------------------------
# Signaler un problème : message libre par e-mail
# ----------------------------------------------------------------------
def test_liens_e_mail():
    objet = signalement.objet("Question")
    corps = signalement.corps("Bonjour, mon PDF & mes « frais » ne passent pas ?", "Version : x\n" + "ligne\n" * 1000)
    assert len(corps) <= signalement.LONGUEUR_LIEN and "raccourci" in corps
    mailto = signalement.lien_mailto("prof@exemple.fr", objet, corps)
    assert mailto.startswith("mailto:prof@exemple.fr?subject=")
    assert "Bonjour, mon PDF & mes « frais »" in unquote(mailto.split("&body=")[1])
    gmail = parse_qs(urlparse(signalement.lien_gmail("prof@exemple.fr", objet, corps)).query)
    assert gmail["to"] == ["prof@exemple.fr"] and gmail["su"] == [objet] and gmail["body"] == [corps]
    assert signalement.corps("") == "(pas de message)"
    assert signalement.CONTACT == "kevin.brule@etu.unicaen.fr"


def test_compatibilite_mac_plateforme():
    import importlib.util
    from pathlib import Path
    chemin = Path(__file__).resolve().parent.parent / "installateur" / "compatibilite_mac.py"
    spec = importlib.util.spec_from_file_location("compatibilite_mac", chemin)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.argv = ["compatibilite_mac.py", "12.0"]
    spec.loader.exec_module(module)
    assert module.PLATEFORME == "macosx_12_0_arm64" and module._version("14.0") > module._version("12.0")

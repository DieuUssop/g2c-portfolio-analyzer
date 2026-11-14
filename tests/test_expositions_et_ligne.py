"""
Retours du 14/11/2026 : diagnostic des expositions selon le profil (cas réel de Kévin : ETF S&P 500, Hermès,
ETF Asie-Pacifique PEA, Euro Stoxx 50 sur deux places, NVIDIA), une seule ligne par titre, courbe par ligne.
"""
import pandas as pd
import pytest

from src import expositions as ex
from src import import_fichier as imp
from src.portfolio import suivi_ligne


def _portefeuille():
    p = pd.DataFrame([
        ("ESE.PA", "BNP EASY S&P 500 EUR", "Actions", "", "États-Unis", "ETF diversifié", "EUR", 3324, None, "S&P 500"),
        ("RMS.PA", "HERMES INTL", "Actions", "France", "Europe", "Consommation discrétionnaire", "EUR", 1342, None, ""),
        ("PAEJ.PA", "AM P AP M AC AP EX JAP ETF-C", "Actions", "", "Asie-Pacifique", "ETF diversifié", "EUR", 1170, None,
         "MSCI AC Asia Pacific ex Japan"),
        ("MSE.PA", "AMUNDI EUROSTOXX 50", "Actions", "", "Europe", "ETF diversifié", "EUR", 1241, None, "Euro Stoxx 50"),
        ("NVDA", "NVIDIA Corp", "Actions", "États-Unis", "États-Unis", "Technologie", "USD", 147, None, ""),
    ], columns=["ticker", "nom", "classe", "pays", "region", "secteur", "devise", "valeur", "duration", "indice"]) \
        .set_index("ticker")
    p["indice"] = p["indice"].replace("", None)
    p["poids_pct"] = p["valeur"] / p["valeur"].sum() * 100
    return p


def _constats(profil):
    p = _portefeuille()
    tr = ex.transparence(p)
    return ex.diagnostic(p, tr, None, profil=profil, doublons=ex.doublons_probables(p, tr))


def test_profil_dynamique_plus_tolerant_sur_les_secteurs():
    def secteur(profil):
        return {c["valeurs"]["secteur"]: c["niveau"] for c in _constats(profil)
                if c["dimension"] == "secteurs" and "secteur {secteur}" in c["titre"]}
    cible = "Consommation discrétionnaire"
    assert secteur("Prudent")[cible] == "alerte"
    assert secteur("Dynamique").get(cible) in ("attention", None)       # plus « à corriger » en dynamique


def test_france_signalee_une_seule_fois():
    france = [c for c in _constats("Dynamique") if c["dimension"] == "geographie"
              and ("France" in str(c["valeurs"].get("pays", "")) or "Biais" in c["titre"])]
    assert len(france) <= 1


def test_doublon_nvidia_trop_petit_pour_etre_signale():
    assert not [c for c in _constats("Dynamique") if "détenu(s) en direct" in c["titre"]]


def test_hermes_seule_action_concentree():
    p = _portefeuille()
    conc = ex.concentration(p, ex.transparence(p))
    assert conc["plus_grosse_action"][0] == "RMS.PA"                     # pas l'ETF S&P 500 (46 %)
    assert conc["plus_grosse_action"][1] == pytest.approx(1342 / 7224, abs=1e-3)


def test_meme_etf_sur_deux_places_regroupe():
    t = pd.DataFrame({"ticker": ["MSE.PA", "C50.XC", "ESE.PA"],
                      "nom": ["AMUNDI EUROSTOXX 50", "AMUNDI EUROSTOXX 50", "BNP EASY S&P 500 EUR"]})
    _, remplacements = imp.regrouper_cotations(t)
    assert remplacements == {"C50.XC": "MSE.PA"}
    assert imp._meilleur_resultat([{"symbol": "C50.XC", "quoteType": "ETF"},
                                   {"symbol": "C50.PA", "quoteType": "ETF"}])["symbol"] == "C50.PA"


def test_suivi_d_une_ligne():
    jours = pd.bdate_range("2024-01-02", "2024-03-29")
    prix = pd.DataFrame({"ESE.PA": [30.0] * 20 + [33.0] * (len(jours) - 20)}, index=jours)
    ops = pd.DataFrame({"date": pd.to_datetime(["2024-01-02", "2024-02-15", "2024-03-01"]),
                        "type": ["ACHAT", "ACHAT", "VENTE"], "ticker": "ESE.PA", "nom": "ESE",
                        "quantite": [10, 10, 5], "prix": [30.0, 33.0, 33.0], "frais": [1.0, 1.0, 1.0]})
    suivi, operations = suivi_ligne(ops, "ESE.PA", prix)
    assert suivi["quantite"].iloc[-1] == 15
    assert suivi["pru"].iloc[-1] == pytest.approx((301 + 331) / 20)          # PRU frais compris, inchangé par la vente
    assert suivi["valeur"].iloc[-1] == pytest.approx(15 * 33)
    assert list(operations["type"]) == ["ACHAT", "ACHAT", "VENTE"]


def test_format_euros_des_colonnes():
    from src import langues
    assert langues.eur_colonne("%.2f") == "euro"                # « 32,27 € » en français
    assert langues.eur_colonne("%+.0f") == "%+.0f €"

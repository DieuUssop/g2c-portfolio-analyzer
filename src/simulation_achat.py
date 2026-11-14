"""
simulation_achat.py — Le simulateur « Et si j'achetais… » : un achat fictif ajouté au
portefeuille, pour voir son effet AVANT de passer l'ordre. Rien n'est enregistré.

L'achat est daté du dernier jour connu, au dernier cours. Comme il n'a pas d'histoire, les
indicateurs passés (volatilité historique, TWR) ne bougent presque pas : on compare donc le
risque « ex ante », c'est-à-dire la volatilité qu'aurait eue la NOUVELLE répartition sur les
trois dernières années (poids d'aujourd'hui × covariance des titres), et les expositions
(pays, secteurs, concentration, diagnostic).
"""

import numpy as np
import pandas as pd

from . import expositions as ex
from . import mouvements

JOURS_RISQUE = 756            # environ 3 ans de bourse


def contenu_avec_achat(contenu, ticker, nom, montant, date, prix):
    """Le fichier du portefeuille avec un achat fictif de « montant » euros (prix dans la devise de
    cotation ; la quantité peut être fractionnaire). Renvoie (octets, quantité)."""
    if prix <= 0 or montant <= 0:
        raise ValueError("Montant et cours doivent être positifs.")
    quantite = round(float(montant) / float(prix), 6)
    tableau = mouvements.lire(contenu)
    ligne = pd.DataFrame([{"date": pd.Timestamp(date), "type": "ACHAT", "ticker": str(ticker).strip().upper(),
                           "nom": nom or ticker, "quantite": quantite, "prix": float(prix), "frais": 0.0}])
    tableau = mouvements._trier(pd.concat([tableau, ligne], ignore_index=True))
    return mouvements.en_csv(tableau), quantite


def prix_en_devise(res, ticker):
    """Dernier cours d'un titre déjà détenu, dans sa devise de cotation (None s'il est inconnu)."""
    p = res["positions"]
    if ticker not in p.index or "cours" not in p.columns:
        return None
    cours = float(p.at[ticker, "cours"])
    devise = p.at[ticker, "devise"] if "devise" in p.columns else "EUR"
    return cours * float(res.get("taux_actuels", {}).get(devise, 1.0)) if devise != "EUR" else cours


def volatilite_ex_ante(prix_hist, positions, jours=JOURS_RISQUE):
    """Volatilité annualisée de la répartition actuelle, sur les derniers jours de cotation."""
    poids = positions["valeur"] / positions["valeur"].sum()
    colonnes = [c for c in poids.index if c in prix_hist.columns]
    if not colonnes:
        return float("nan")
    rendements = prix_hist[colonnes].ffill().pct_change(fill_method=None).iloc[-jours:].fillna(0.0)
    w = poids.reindex(colonnes).fillna(0.0).values
    w = w / w.sum() if w.sum() else w
    return float(np.sqrt(w @ rendements.cov().values @ w * 252))


def resume_exposition(res, profil="Équilibré"):
    """Chiffres comparés avant / après pour un résultat d'analyse."""
    positions = res["positions"]
    transp = ex.transparence(positions)
    pays = ex.repartition(transp, "pays", "Actions", normaliser=True).drop(ex.NON_CLASSE, errors="ignore")
    secteurs = ex.repartition(transp, "secteur", "Actions", normaliser=True).drop(ex.NON_CLASSE, errors="ignore")
    constats = ex.diagnostic(positions, transp, None, profil=profil)
    plus_grosse = positions["valeur"].idxmax()
    return {
        "valeur": float(positions["valeur"].sum()),
        "volatilite": volatilite_ex_ante(res["prix_hist"], positions),
        "plus_grosse_ligne": (positions.at[plus_grosse, "nom"], float(positions["valeur"].max() / positions["valeur"].sum())),
        "pays": (pays.index[0], float(pays.iloc[0])) if len(pays) else ("", 0.0),
        "secteur": (secteurs.index[0], float(secteurs.iloc[0])) if len(secteurs) else ("", 0.0),
        "alertes": sum(c["niveau"] == "alerte" for c in constats),
        "attentions": sum(c["niveau"] == "attention" for c in constats),
        "constats": constats,
    }


def nouveaux_constats(avant, apres):
    """Constats (alerte ou attention) qui apparaissent avec l'achat, et ceux qui disparaissent."""
    def cles(r):
        return {(c["dimension"], c["titre"]): c for c in r["constats"] if c["niveau"] != "ok"}
    a, b = cles(avant), cles(apres)
    return [b[k] for k in b if k not in a], [a[k] for k in a if k not in b]

"""
dividendes.py — Les dividendes et coupons : historique par année et estimation des
revenus des 12 prochains mois.

Estimation (simple et prudente) : pour chaque ligne encore détenue, les dividendes reçus
pendant les 12 derniers mois, ramenés à une part (montant ÷ quantité détenue le jour du
versement), multipliés par la quantité détenue aujourd'hui. Une ligne qui n'a rien versé
depuis un an (ETF capitalisant, action sans dividende, achat récent) compte pour 0 : on ne
devine rien. Montants nets (après retenue à la source), en euros.
"""

import pandas as pd

QUANTITE_MIN = 1e-9


def _dividendes(transactions):
    d = transactions[transactions["type"] == "DIVIDENDE"].copy()
    d["date"] = pd.to_datetime(d["date"])
    d["net"] = d["prix"].astype(float) - d["frais"].astype(float)
    return d


def par_annee(transactions):
    """Dividendes nets par année civile (Series indexée par l'année, en euros)."""
    d = _dividendes(transactions)
    if d.empty:
        return pd.Series(dtype=float)
    return d.groupby(d["date"].dt.year)["net"].sum().rename("dividendes")


def _quantite_au(transactions, ticker, date):
    """Quantité détenue d'un titre à la fin d'une journée."""
    o = transactions[(transactions["ticker"] == ticker) & (pd.to_datetime(transactions["date"]) <= date)]
    signe = o["type"].map({"ACHAT": 1.0, "VENTE": -1.0}).fillna(0.0)
    return float((signe * o["quantite"].astype(float)).sum())


def estimation_12_mois(transactions, positions, date_fin=None):
    """Estimation des dividendes des 12 prochains mois.

    Renvoie (total, tableau) ; tableau : une ligne par titre détenu qui a versé un dividende
    dans l'année écoulée (nom, quantité, dividende par part sur 12 mois, estimation, rendement
    sur la valeur actuelle en %)."""
    d = _dividendes(transactions)
    fin = pd.Timestamp(date_fin) if date_fin is not None else (d["date"].max() if len(d) else pd.Timestamp.today())
    fin = max(fin, pd.to_datetime(transactions["date"]).max())
    recents = d[d["date"] > fin - pd.Timedelta(days=365)]
    lignes = []
    for ticker, groupe in recents.groupby("ticker"):
        if ticker not in positions.index or positions.at[ticker, "quantite"] <= QUANTITE_MIN:
            continue
        par_part = 0.0
        for _, v in groupe.iterrows():
            qte = _quantite_au(transactions, ticker, v["date"])
            if qte > QUANTITE_MIN:
                par_part += v["net"] / qte
        quantite = float(positions.at[ticker, "quantite"])
        estimation = par_part * quantite
        valeur = float(positions.at[ticker, "valeur"]) if "valeur" in positions.columns else 0.0
        lignes.append({"ticker": ticker, "nom": positions.at[ticker, "nom"] if "nom" in positions.columns else ticker,
                       "quantite": quantite, "par_part": par_part, "estimation": estimation,
                       "rendement_pct": estimation / valeur * 100 if valeur else 0.0})
    tableau = pd.DataFrame(lignes, columns=["ticker", "nom", "quantite", "par_part", "estimation", "rendement_pct"])
    tableau = tableau.sort_values("estimation", ascending=False).reset_index(drop=True)
    return float(tableau["estimation"].sum()), tableau

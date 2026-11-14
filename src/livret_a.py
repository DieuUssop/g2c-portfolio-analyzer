"""
livret_a.py — « Et si j'avais tout mis sur un Livret A ? »

Le même argent, versé et retiré aux mêmes dates que dans le portefeuille (flux de
Portfolio.historique), placé sur un Livret A au taux en vigueur chaque jour.

Taux officiels (Banque de France, arrêtés publiés au Journal officiel ; info.gouv.fr pour
le taux du 1er août 2026). Simplifications, signalées à l'écran :
    - intérêts calculés au jour près (la vraie règle compte par quinzaines) ;
    - intérêts ajoutés au capital le 31 décembre, comme sur un vrai Livret A ; les intérêts
      de l'année en cours sont comptés dans la valeur affichée ;
    - plafond de dépôt (22 950 €) ignoré : la comparaison porte sur la même somme.
"""

import pandas as pd

# date d'effet -> taux annuel. À compléter à chaque changement (1er février et 1er août).
TAUX_LIVRET_A = {
    "2008-08-01": 4.00, "2009-02-01": 2.50, "2009-05-01": 1.75, "2009-08-01": 1.25,
    "2010-08-01": 1.75, "2011-02-01": 2.00, "2011-08-01": 2.25, "2013-02-01": 1.75,
    "2013-08-01": 1.25, "2014-08-01": 1.00, "2015-08-01": 0.75, "2020-02-01": 0.50,
    "2022-02-01": 1.00, "2022-08-01": 2.00, "2023-02-01": 3.00, "2025-02-01": 2.40,
    "2025-08-01": 1.70, "2026-02-01": 1.50, "2026-08-01": 1.70,
}
SOURCE = "Banque de France · info.gouv.fr (taux au 1er août 2026)"


def taux_au(dates):
    """Taux du Livret A (en décimal) pour chaque date."""
    serie = pd.Series({pd.Timestamp(d): v / 100 for d, v in TAUX_LIVRET_A.items()}).sort_index()
    dates = pd.DatetimeIndex(pd.to_datetime(dates))
    return pd.Series(serie.reindex(serie.index.union(dates)).ffill().reindex(dates).fillna(serie.iloc[0]).values,
                     index=dates)


def simuler(historique):
    """Valeur jour par jour d'un Livret A alimenté par les mêmes flux que le portefeuille.

    historique : DataFrame indexé par date avec la colonne « flux » (apports + , retraits −).
    Renvoie une Series (euros)."""
    jours = pd.date_range(historique.index[0], historique.index[-1], freq="D")
    flux = historique["flux"].reindex(jours).fillna(0.0)
    taux = taux_au(jours)
    capital, interets, valeurs = 0.0, 0.0, []
    for jour, f, r in zip(jours, flux.values, taux.values):
        capital += f
        interets += max(capital, 0.0) * r / 365
        if jour.month == 12 and jour.day == 31:
            capital, interets = capital + interets, 0.0
        valeurs.append(capital + interets)
    return pd.Series(valeurs, index=jours).reindex(historique.index)


def comparer(historique):
    """Valeur finale du portefeuille et du Livret A, écart (euros) et taux actuel."""
    livret = simuler(historique)
    return {"livret": float(livret.iloc[-1]), "portefeuille": float(historique["valeur"].iloc[-1]),
            "ecart": float(historique["valeur"].iloc[-1] - livret.iloc[-1]),
            "taux_actuel": float(taux_au([historique.index[-1]]).iloc[0]), "serie": livret}

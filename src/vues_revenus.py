"""
vues_revenus.py — Encadrés « Dividendes » (onglet Positions : par année et estimation des 12
prochains mois, src/dividendes.py) et « Comparé au Livret A » (onglet Performance,
src/livret_a.py).
"""

import streamlit as st

from . import dividendes as dv
from . import graphiques_interactifs as gi
from . import interface as ui
from . import langues, livret_a
from .interface import euros, pct
from .langues import t


def html(morceau):
    st.markdown(morceau, unsafe_allow_html=True)


def dividendes(res, graphique):
    annuel = dv.par_annee(res["transactions"])
    total, tableau = dv.estimation_12_mois(res["transactions"], res["positions"], res["historique"].index[-1])
    with st.container(border=True):
        html(ui.titre_section(t("Dividendes et coupons"),
                              t("Montants nets reçus chaque année, et estimation des 12 prochains mois")))
        if annuel.empty:
            st.caption(t("Aucun dividende enregistré pour l'instant (ETF capitalisants, ou dividendes absents du "
                         "fichier)."))
            return
        valeur = res["resume"]["valeur_actuelle"]
        annee = int(annuel.index[-1])
        en_cours = annee == res["historique"].index[-1].year
        html(ui.grille([
            ui.carte(t("Reçus depuis le 1er janvier") if en_cours else t("Reçus en {annee}", annee=annee),
                     euros(annuel.iloc[-1]), detail=str(annee) if en_cours else ""),
            ui.carte(t("Total depuis l'origine"), euros(annuel.sum())),
            ui.carte(t("Estimation sur 12 mois"), euros(total),
                     detail=t("Rendement {taux} sur la valeur actuelle", taux=pct(total / valeur if valeur else 0,
                                                                                signe=False)),
                     aide=t("Dividendes reçus ces 12 derniers mois, par part, × quantité détenue aujourd'hui. Une "
                            "ligne qui n'a rien versé depuis un an compte pour 0.")),
        ]))
        graphique(gi.fig_dividendes_annuels(annuel, total, annee_en_cours=en_cours))
        if len(tableau):
            # sous le graphique, sur toute la largeur : toutes les colonnes sont visibles
            st.dataframe(tableau[["nom", "estimation", "rendement_pct", "par_part"]].assign(
                rendement_pct=tableau["rendement_pct"] / 100), hide_index=True, width="stretch",
                height=min(len(tableau), 10) * 35 + 38, column_config={
                    "nom": st.column_config.TextColumn(t("Titre"), width="large"),
                    "estimation": st.column_config.NumberColumn(t("Estimation sur 12 mois"),
                                                                format=langues.eur_colonne("%.0f")),
                    "rendement_pct": st.column_config.NumberColumn(t("Rendement"), format=langues.pct_colonne()),
                    "par_part": st.column_config.NumberColumn(t("Par part (12 mois)"),
                                                              format=langues.eur_colonne("%.2f")),
                })
        html(ui.note(t("Estimation prudente : rien n'est deviné pour une ligne qui n'a pas versé de dividende "
                       "depuis un an. Les dividendes futurs ne sont jamais garantis.")))


def meme_argent(res):
    """Le même argent placé dans l'indice de référence et sur un Livret A (src/livret_a.py)."""
    return livret_a.comparer_tout(res["historique"], res["avances"].get("indice_reference"),
                                  res["resume"]["valeur_actuelle"])


def comparaison_livret_a(res, graphique, nom_indice=""):
    """Encadré « Le même argent ailleurs » : dans l'indice de référence et sur un Livret A, aux mêmes dates.
    C'est la comparaison qui se lit en euros, à côté du gain réel du portefeuille."""
    histo = res["historique"]
    c = meme_argent(res)
    with st.container(border=True):
        html(ui.titre_section(t("Le même argent ailleurs"),
                              t("Mêmes versements et retraits, aux mêmes dates, placés dans {indice} ou sur un "
                                "Livret A", indice=nom_indice or t("l'indice"))))
        cartes = [ui.carte(t("Mon portefeuille"), euros(c["portefeuille"]), detail=t("Valeur des titres aujourd'hui"))]
        if c["indice"] is not None:
            cartes.append(ui.carte(
                t("Dans {indice}", indice=nom_indice or t("l'indice")), euros(c["indice"]),
                detail=ui.pastille((t("+{montant} pour mon portefeuille", montant=euros(c["ecart_indice"]))
                                    if c["ecart_indice"] >= 0 else
                                    t("{montant} pour mon portefeuille", montant=euros(c["ecart_indice"], signe=True))),
                                   "positive" if c["ecart_indice"] >= 0 else "negative"),
                aide=t("Chaque versement achète des parts de l'indice le même jour ; chaque retrait en revend")))
        cartes.append(ui.carte(
            t("Sur un Livret A"), euros(c["livret"]),
            detail=ui.pastille((t("+{montant} pour mon portefeuille", montant=euros(c["ecart_livret"]))
                                if c["ecart_livret"] >= 0 else
                                t("{montant} pour mon portefeuille", montant=euros(c["ecart_livret"], signe=True))),
                               "positive" if c["ecart_livret"] >= 0 else "negative"),
            aide=t("Taux actuel {taux}", taux=pct(c["taux_actuel"], signe=False))))
        html(ui.grille(cartes))
        graphique(gi.fig_livret_a(histo, c["serie_livret"], c["serie_indice"], nom_indice))
        st.caption(t("Taux officiels du Livret A depuis 2008 ({source}). Intérêts comptés au jour près et ajoutés au "
                     "capital le 31 décembre ; plafond de 22 950 € ignoré. Le Livret A est sans risque : la "
                     "différence rémunère le risque pris en bourse.", source=livret_a.SOURCE))

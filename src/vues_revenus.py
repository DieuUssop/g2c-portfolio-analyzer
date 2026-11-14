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
        html(ui.grille([
            ui.carte(t("Reçus en {annee}", annee=int(annuel.index[-1])), euros(annuel.iloc[-1])),
            ui.carte(t("Total depuis l'origine"), euros(annuel.sum())),
            ui.carte(t("Estimation sur 12 mois"), euros(total),
                     detail=t("Rendement {taux} sur la valeur actuelle", taux=pct(total / valeur if valeur else 0,
                                                                                signe=False)),
                     aide=t("Dividendes reçus ces 12 derniers mois, par part, × quantité détenue aujourd'hui. Une "
                            "ligne qui n'a rien versé depuis un an compte pour 0.")),
        ]))
        gauche, droite = st.columns([3, 2], gap="medium")
        with gauche:
            graphique(gi.fig_dividendes_annuels(annuel, total))
        with droite:
            if len(tableau):
                st.dataframe(tableau[["nom", "par_part", "estimation", "rendement_pct"]], hide_index=True,
                             width="stretch", column_config={
                                 "nom": st.column_config.TextColumn(t("Titre")),
                                 "par_part": st.column_config.NumberColumn(t("Par part (12 mois)"),
                                                                           format=langues.eur_colonne("%.2f")),
                                 "estimation": st.column_config.NumberColumn(t("Estimation"),
                                                                             format=langues.eur_colonne("%.0f")),
                                 "rendement_pct": st.column_config.NumberColumn(t("Rendement"),
                                                                                format=langues.pct_colonne("%.1f")),
                             })
        html(ui.note(t("Estimation prudente : rien n'est deviné pour une ligne qui n'a pas versé de dividende "
                       "depuis un an. Les dividendes futurs ne sont jamais garantis.")))


def comparaison_livret_a(res, graphique):
    histo = res["historique"]
    c = livret_a.comparer(histo)
    with st.container(border=True):
        html(ui.titre_section(t("Comparé au Livret A"),
                              t("Le même argent, versé et retiré aux mêmes dates, placé sur un Livret A")))
        html(ui.grille([
            ui.carte(t("Mon portefeuille"), euros(c["portefeuille"])),
            ui.carte(t("Sur un Livret A"), euros(c["livret"]),
                     detail=t("Taux actuel {taux}", taux=pct(c["taux_actuel"], signe=False))),
            ui.carte(t("Différence"), euros(c["ecart"], signe=True),
                     detail=ui.pastille(t("mieux que le Livret A") if c["ecart"] >= 0 else t("moins bien que le Livret A"),
                                        "positive" if c["ecart"] >= 0 else "negative")),
        ]))
        graphique(gi.fig_livret_a(histo, c["serie"]))
        st.caption(t("Taux officiels du Livret A depuis 2008 ({source}). Intérêts comptés au jour près et ajoutés au "
                     "capital le 31 décembre ; plafond de 22 950 € ignoré. Le Livret A est sans risque : la "
                     "différence rémunère le risque pris en bourse.", source=livret_a.SOURCE))

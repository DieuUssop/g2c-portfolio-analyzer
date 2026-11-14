"""
vues_ligne.py — Courbe d'une seule ligne du portefeuille (un ETF ou une action).

Un menu « Tout le portefeuille / une ligne » au-dessus du graphique d'évolution (Vue d'ensemble) et dans
l'onglet Positions. Pour une ligne :
    - « Valeur » : valeur de la ligne et argent investi dans la ligne (quantité × PRU) ;
    - « Cours et PRU » : cours du titre, PRU en pointillé, achats ▲ et ventes ▼ au prix payé ;
    - « Comparée à l'indice » : cours depuis le premier achat (base 100) face à l'indice de référence ;
    + plus-value latente, réalisée, dividendes et frais de la ligne.
Les lignes déjà vendues sont proposées aussi (historique jusqu'à la vente).
Calculs : portfolio.suivi_ligne ; graphiques : graphiques_interactifs.fig_ligne_*.
"""

import streamlit as st

from . import graphiques_interactifs as gi
from . import interface as ui
from .langues import t
from .portfolio import suivi_ligne

TOUT = "__tout__"


def html(morceau):
    st.markdown(morceau, unsafe_allow_html=True)


def choisir_ligne(res, cle):
    """Menu « Tout le portefeuille / ligne » ; renvoie le ticker choisi, ou None pour tout le portefeuille."""
    toutes = res.get("toutes_positions", res["positions"])
    valeurs = res["positions"]["valeur"] if "valeur" in res["positions"].columns else None
    ordre = sorted(toutes.index, key=lambda tk: (-(valeurs.get(tk, 0.0) if valeurs is not None else 0.0), str(tk)))
    noms = toutes["nom"].astype(str).to_dict()
    vendus = set(toutes.index[toutes["quantite"] <= 1e-9])

    def libelle(tk):
        if tk == TOUT:
            return t("Tout le portefeuille")
        return f"{noms.get(tk, tk)} ({tk})" + (" · " + t("vendue") if tk in vendus else "")

    choix = st.selectbox(t("Courbe"), [TOUT] + ordre, format_func=libelle, key=f"ligne_{cle}",
                         label_visibility="collapsed")
    return None if choix == TOUT else choix


def afficher_ligne(res, ticker, nom_indice, code_indice, cle, graphique):
    """Graphiques et chiffres d'une ligne. graphique : fonction d'affichage d'une figure (app.py)."""
    from .interface import euros
    suivi, operations = suivi_ligne(res["transactions"], ticker, res["prix_hist"])
    if suivi.empty:
        st.info(t("Pas de cours pour cette ligne."))
        return
    vue = st.segmented_control(t("Vue"), [t("Valeur"), t("Cours et PRU"), t("Comparée à l'indice")],
                               default=t("Valeur"), key=f"vue_ligne_{cle}", label_visibility="collapsed") or t("Valeur")
    if vue == t("Cours et PRU"):
        graphique(gi.fig_ligne_cours(suivi, operations))
    elif vue == t("Comparée à l'indice"):
        indice = res["prix_hist"][code_indice] if code_indice in res["prix_hist"].columns else suivi["cours"] * 0
        graphique(gi.fig_ligne_performance(suivi["cours"], indice.reindex(suivi.index), nom_indice))
    else:
        graphique(gi.fig_ligne_valeur(suivi))
    ligne = res.get("toutes_positions", res["positions"]).loc[ticker]
    latente = float(res["positions"].at[ticker, "pv_latente"]) if ticker in res["positions"].index else 0.0
    html(ui.decomposition_gain([
        (t("Latente"), latente, ticker in res["positions"].index),
        (t("Réalisée"), float(ligne.get("pv_realisee", 0.0)), True),
        (t("Dividendes"), float(ligne.get("dividendes", 0.0)), bool(ligne.get("dividendes", 0.0))),
        (t("Frais"), -float(ligne.get("frais_totaux", 0.0)), bool(ligne.get("frais_totaux", 0.0))),
    ], euros))

"""
vues_allocation.py — L'onglet « Allocation cible » : objectifs par poche (src/allocation.py),
répartition du prochain versement sans rien vendre, et simulateur « Et si j'achetais… »
(src/simulation_achat.py).

Les objectifs sont gardés avec le portefeuille : dans les préférences chiffrées pour un
portefeuille de l'espace personnel, pour la session sinon.
"""

import pandas as pd
import streamlit as st

from . import allocation, langues, simulation_achat
from . import graphiques_interactifs as gi
from . import interface as ui
from .interface import euros, nombre, pct
from .langues import t, td


def html(morceau):
    st.markdown(morceau, unsafe_allow_html=True)


def _cle(cible):
    return f"allocation_{(cible or {}).get('id') or (cible or {}).get('origine') or 'session'}"


def _objectifs_enregistres(cible, session_compte):
    if cible and cible.get("type") == "perso" and session_compte is not None:
        try:
            return session_compte.preference(_cle(cible), {}) or {}
        except Exception:
            return {}
    return st.session_state.get(_cle(cible), {})


def _enregistrer(cible, session_compte, objectifs):
    st.session_state[_cle(cible)] = objectifs
    if cible and cible.get("type") == "perso" and session_compte is not None:
        try:
            session_compte.definir_preference(_cle(cible), objectifs)
        except Exception:
            pass


# ----------------------------------------------------------------------
# Allocation cible
# ----------------------------------------------------------------------
def afficher(res, contenu, cible, session_compte, analyser, graphique, profil="Équilibré"):
    positions = res["positions"]
    actuelle = allocation.repartition_actuelle(positions)
    enregistres = _objectifs_enregistres(cible, session_compte)
    defaut = allocation.cible_par_defaut(actuelle)
    poches = [p for p in allocation.POCHES if p != "Autres" or p in actuelle.index]
    objectifs = pd.Series({p: float(enregistres.get(p, defaut.get(p, 0.0))) for p in poches})

    with st.container(border=True):
        html(ui.titre_section(t("Allocation cible"),
                              t("Fixez votre répartition idéale par grande poche : l'application calcule comment "
                                "investir votre prochain versement pour vous en rapprocher, sans rien vendre.")))
        if not enregistres:
            st.caption(t("Proposition de départ : votre répartition actuelle, arrondie à 5 points. Modifiez la "
                         "colonne « Cible ». Une ligne MSCI World compte dans « Actions Monde »."))
        gauche, droite = st.columns([3, 2], gap="medium")
        with gauche:
            tableau = pd.DataFrame({"poche": [td(p) for p in poches],
                                    "actuel": [float(actuelle["poids"].get(p, 0.0)) for p in poches],
                                    "cible": objectifs.values})
            edite = st.data_editor(
                tableau, hide_index=True, width="stretch", num_rows="fixed", key=f"editeur_{_cle(cible)}",
                disabled=["poche", "actuel"],
                column_config={
                    "poche": st.column_config.TextColumn(t("Poche")),
                    "actuel": st.column_config.NumberColumn(t("Actuel"), format=langues.pct_colonne("%.1f")),
                    "cible": st.column_config.NumberColumn(t("Cible"), min_value=0.0, max_value=100.0, step=5.0,
                                                           format=langues.pct_colonne("%.0f")),
                })
            nouveaux = pd.Series(pd.DataFrame(edite)["cible"].astype(float).values, index=poches)
            total = float(nouveaux.sum())
            if abs(total - 100) > 0.05:
                html(ui.note(t("Total des cibles : {total} (il faut 100 %).", total=pct(total / 100, signe=False,
                                                                                      decimales=1)), attention=True))
            elif nouveaux.round(4).to_dict() != objectifs.round(4).to_dict() or not enregistres:
                if st.button(t("Enregistrer ces objectifs"), type="primary", key="enregistrer_allocation"):
                    _enregistrer(cible, session_compte, {k: float(v) for k, v in nouveaux.items() if v > 0})
                    st.rerun()
        with droite:
            montant = st.number_input(t("Montant du prochain versement (€)"), min_value=0.0, max_value=10_000_000.0,
                                      value=500.0, step=100.0, key="versement_allocation")
            if abs(total - 100) <= 0.05:
                detail = allocation.tableau(positions, nouveaux[nouveaux > 0] if nouveaux.sum() else nouveaux, montant)
                ecart = allocation.ecart_total(detail)
                html(ui.grille([
                    ui.carte(t("Écart à la cible"), t("{n} points", n=nombre(ecart, 1)),
                             detail=ui.pastille(t("aligné") if ecart < 2 else t("à rééquilibrer"),
                                                "positive" if ecart < 2 else "attention"),
                             aide=t("Somme des écarts des poches au-dessus de leur cible")),
                    ui.carte(t("Écart après le versement"),
                             t("{n} points", n=nombre(float((detail["apres"] - detail["cible"]).clip(lower=0).sum()), 1))),
                ]))
        if abs(total - 100) <= 0.05:
            achats = detail[detail["a_investir"] > 0.5].sort_values("a_investir", ascending=False)
            if len(achats) and montant > 0:
                html(ui.titre_section(t("Où investir les {montant}", montant=euros(montant))))
                st.dataframe(pd.DataFrame({
                    t("Poche"): [td(p) for p in achats.index],
                    t("À investir"): [euros(v) for v in achats["a_investir"]],
                    t("Actuel"): [pct(v / 100, signe=False, decimales=1) for v in achats["actuel"]],
                    t("Cible"): [pct(v / 100, signe=False, decimales=0) for v in achats["cible"]],
                    t("Après"): [pct(v / 100, signe=False, decimales=1) for v in achats["apres"]],
                    t("Par exemple via"): [n or t("(aucune ligne détenue : à choisir)") for n in achats["ligne"]],
                }), hide_index=True, width="stretch")
            graphique(gi.fig_allocation(detail))
            html(ui.note(t("Rééquilibrage par les apports : on renforce les poches en retard au lieu de vendre "
                           "celles en avance (pas de frais de vente, pas d'impôt sur une plus-value). Exercice "
                           "pédagogique, pas un conseil en investissement.")))

    _simulateur(res, contenu, analyser, profil)


# ----------------------------------------------------------------------
# Simulateur « Et si j'achetais… »
# ----------------------------------------------------------------------
def _simulateur(res, contenu, analyser, profil):
    positions = res["positions"]
    with st.container(border=True):
        html(ui.titre_section(t("Et si j'achetais…"),
                              t("Testez un achat avant de passer l'ordre : effet sur le risque, les expositions et le "
                                "diagnostic. Rien n'est enregistré.")))
        autre = "__autre__"
        choix = [autre] + list(positions.sort_values("valeur", ascending=False).index)
        a, b, c = st.columns([3, 2, 1.4], vertical_alignment="bottom")
        titre = a.selectbox(t("Titre"), choix, index=1 if len(choix) > 1 else 0, key="simulation_titre",
                            format_func=lambda tk: t("Autre titre (ticker Yahoo Finance)…") if tk == autre
                            else f"{positions.at[tk, 'nom']} ({tk})")
        montant = b.number_input(t("Montant (€)"), min_value=0.0, value=1000.0, step=100.0, key="simulation_montant")
        ticker, nom = titre, None
        if titre == autre:
            ticker = st.text_input(t("Ticker Yahoo Finance"), placeholder="CW8.PA, AAPL, PAEJ.PA…",
                                   key="simulation_ticker").strip().upper()
            nom = ticker
        else:
            nom = positions.at[titre, "nom"]
        lancer = c.button(t("Simuler"), type="primary", key="simulation_lancer", width="stretch",
                          disabled=not ticker or montant <= 0)
        cle = ("simulation", ticker, montant, len(res["transactions"]))
        if lancer:
            st.session_state["simulation_demandee"] = cle
        if st.session_state.get("simulation_demandee") != cle:
            return
        prix = simulation_achat.prix_en_devise(res, ticker)
        if prix is None:
            try:
                from .market_data import obtenir_cours
                prix = (obtenir_cours([ticker]) or {}).get(ticker)
            except Exception:
                prix = None
        if not prix or prix != prix:
            st.warning(t("Cours introuvable pour {ticker} (ticker mal écrit, ou pas d'Internet).", ticker=ticker))
            return
        try:
            contenu, quantite = simulation_achat.contenu_avec_achat(
                contenu, ticker, nom, montant, res["historique"].index[-1], prix)
            with st.spinner(t("Simulation de l'achat...")):
                apres_res = analyser(contenu)
            avant, apres = simulation_achat.resume_exposition(res, profil), simulation_achat.resume_exposition(apres_res, profil)
        except Exception as erreur:
            st.error(t("Simulation impossible : {erreur}", erreur=erreur))
            return
        st.caption(t("Achat fictif de {q} × {nom} au dernier cours, le {date}.", q=nombre(quantite, 4), nom=nom,
                     date=langues.date(res["historique"].index[-1])))

        def ligne(libelle, f, cle_):
            return {t("Indicateur"): libelle, t("Avant"): f(avant[cle_]), t("Après l'achat"): f(apres[cle_])}

        def part(v):
            return f"{td(v[0])} {pct(v[1], signe=False, decimales=0)}" if v[0] else "—"

        st.dataframe(pd.DataFrame([
            ligne(t("Valeur des titres"), euros, "valeur"),
            ligne(t("Volatilité de la répartition (3 ans)"), lambda v: pct(v, signe=False) if v == v else "—",
                  "volatilite"),
            ligne(t("Plus grosse ligne"), lambda v: f"{v[0]} {pct(v[1], signe=False, decimales=0)}", "plus_grosse_ligne"),
            ligne(t("Premier pays (actions)"), part, "pays"),
            ligne(t("Premier secteur (actions)"), part, "secteur"),
            ligne(t("Alertes du diagnostic"), str, "alertes"),
            ligne(t("Points d'attention"), str, "attentions"),
        ]), hide_index=True, width="stretch")
        nouveaux, disparus = simulation_achat.nouveaux_constats(avant, apres)
        for c_ in nouveaux:
            html(ui.note(t("Nouveau : {texte}", texte=t(c_["titre"], **c_["valeurs"])), attention=True))
        for c_ in disparus:
            html(ui.note(t("Réglé par cet achat : {texte}", texte=t(c_["titre"], **c_["valeurs"]))))
        if not nouveaux and not disparus:
            html(ui.note(t("Cet achat ne change aucun constat du diagnostic.")))
        html(ui.note(t("Volatilité de la répartition : celle qu'aurait eue la nouvelle répartition sur les 3 dernières "
                       "années. L'achat n'a pas d'histoire : la volatilité passée du portefeuille ne bougerait pas.")))

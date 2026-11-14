"""
vues_bienvenue.py — La prise en main : carte « Bienvenue » du premier lancement, bandeau
« portefeuille d'exemple », encadré « Ce qu'il faut retenir » et mode Essentiel / Expert.

La carte de bienvenue s'affiche tant que l'utilisateur ne l'a pas fermée. Ce choix est gardé :
    - dans ses préférences chiffrées s'il est connecté ;
    - sinon dans un petit fichier « bienvenue_vue » à côté des comptes (aucune donnée personnelle).
"""

from pathlib import Path

import streamlit as st

from . import comptes, synthese
from . import interface as ui
from .langues import t

MODES = {"expert": "Expert", "essentiel": "Essentiel"}
# Mode Essentiel : les onglets utiles au quotidien (le reste est dans le mode Expert)
ONGLETS_ESSENTIELS = ["Vue d'ensemble", "Positions", "Expositions", "Allocation cible", "Transactions"]
ESPACES_ESSENTIELS = ["Analyse du portefeuille", "Manuel et aide"]


def html(morceau):
    st.markdown(morceau, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Mode Essentiel / Expert
# ----------------------------------------------------------------------
def _choix_mode():
    if st.session_state.get("mode_affichage") is None:          # clic sur le mode déjà choisi : on le garde
        st.session_state["mode_affichage"] = st.session_state.get("mode_actif", "expert")
    st.session_state["mode_actif"] = st.session_state["mode_affichage"]
    session = st.session_state.get("session_compte")
    if session is not None:
        try:
            session.definir_preference("mode", st.session_state["mode_affichage"])
        except Exception:
            pass


def choisir_mode(session):
    """Sélecteur « Essentiel · Expert » de la barre latérale (Expert par défaut). Renvoie le mode."""
    if "mode_affichage" not in st.session_state and session is not None:
        try:
            st.session_state["mode_affichage"] = session.preference("mode", "expert") or "expert"
        except Exception:
            pass
    st.segmented_control(t("Affichage des onglets"), list(MODES), format_func=lambda m: t(MODES[m]),
                         default="expert", key="mode_affichage", on_change=_choix_mode,
                         help=t("Essentiel : les onglets du quotidien (vue d'ensemble, positions, expositions, "
                                "allocation, transactions). Expert : tous les onglets et tous les espaces."))
    return st.session_state.get("mode_affichage") or "expert"


# ----------------------------------------------------------------------
# Carte de bienvenue
# ----------------------------------------------------------------------
def _fichier_vue():
    return Path(comptes.DOSSIER).parent / "bienvenue_vue"


def deja_vue(session):
    if st.session_state.get("bienvenue_fermee"):
        return True
    if session is not None:
        try:
            if session.preference("bienvenue_vue"):
                return True
        except Exception:
            pass
    return _fichier_vue().exists()


def _fermer(session):
    st.session_state["bienvenue_fermee"] = True
    try:
        _fichier_vue().parent.mkdir(parents=True, exist_ok=True)
        _fichier_vue().write_text("1", encoding="utf-8")
    except OSError:
        pass
    if session is not None:
        try:
            session.definir_preference("bienvenue_vue", True)
        except Exception:
            pass


def _aller_manuel():
    st.session_state["espace_actif"] = "Manuel et aide"


def afficher(session, exemple, fichiers_envoyes, modele_csv):
    """Carte « Bienvenue » (premier lancement) et bandeau « portefeuille d'exemple »."""
    if exemple and not fichiers_envoyes and not deja_vue(session):
        html(ui.bienvenue(
            t("Bienvenue dans Portfolio Tracker"),
            t("Trois étapes pour analyser votre propre portefeuille. En attendant, un portefeuille d'exemple "
              "est affiché ci-dessous."),
            [(t("Importer vos opérations"),
              t("Glissez votre relevé de courtier (PDF, CSV, Excel ou photo) dans la zone « Données » de la "
                "barre latérale, à gauche. Il est lu automatiquement.")),
             (t("Vérifier le solde espèces"),
              t("Sous la carte « Solde espèces », le crayon ✏️ permet de recopier le solde de votre relevé.")),
             (t("Lire la Vue d'ensemble"),
              t("L'encadré « Ce qu'il faut retenir » résume la performance, le principal risque et une piste. "
                "Connectez-vous pour enregistrer vos portefeuilles (chiffrés)."))]))
        html(ui.surligner_depot())
        a, b, c, _ = st.columns([1.2, 1.4, 1.4, 2])
        a.button(t("J'ai compris"), type="primary", key="fermer_bienvenue", on_click=_fermer, args=(session,))
        b.download_button(t("Modèle de fichier"), data=modele_csv.encode("utf-8-sig"),
                          file_name="modele_transactions.csv", mime="text/csv", icon=":material/description:",
                          key="modele_bienvenue")
        c.button(t("Lire le manuel"), icon=":material/menu_book:", key="manuel_bienvenue", on_click=_aller_manuel)
    elif exemple and not fichiers_envoyes:
        html(ui.bandeau_exemple(t("Vous regardez un portefeuille d'exemple. Pour analyser le vôtre : glissez votre "
                                  "relevé dans la zone « Données » de la barre latérale.")))


# ----------------------------------------------------------------------
# « Ce qu'il faut retenir »
# ----------------------------------------------------------------------
def retenir(res, constats, nom_indice):
    """Trois phrases en haut de la Vue d'ensemble (src/synthese.py)."""
    from .interface import euros, pct
    lignes = []
    for niveau, prefixe, texte, valeurs in synthese.phrases(
            res, constats, nom_indice, f_pct=lambda x: pct(x), f_eur=lambda x: euros(x, signe=True)):
        phrase = t(texte, **valeurs)
        lignes.append((niveau, (t(prefixe) + " " if prefixe else "") + phrase))
    html(ui.retenir(t("Ce qu'il faut retenir"), lignes))

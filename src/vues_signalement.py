"""
vues_signalement.py — Bouton « Signaler un problème » (voir src/signalement.py).

Le diagnostic est affiché AVANT d'être téléchargé : l'étudiant voit exactement ce qu'il enverra
(aucune donnée personnelle), et rien ne part tout seul.
"""

import streamlit as st

from . import langues, signalement
from .langues import t


def noter_erreur(etape, message):
    """À appeler à côté de chaque st.error : l'erreur figurera dans le diagnostic."""
    try:
        signalement.noter_erreur(st.session_state, etape, message)
    except Exception:
        pass


def bouton(brut=None, nom_fichier=None, cle="", dans_barre=False):
    """Repli « Signaler un problème » : explication, aperçu du diagnostic, téléchargement."""
    with st.expander(t("Signaler un problème"), icon=":material/bug_report:"):
        st.caption(t("Un fichier texte qui dit ce qui a coincé, sans données personnelles (nom, adresse, e-mail, "
                     "téléphone, numéros de compte masqués). Relisez-le, puis envoyez-le au créateur du logiciel : "
                     "rien n'est envoyé automatiquement."))
        # préparé seulement à la demande (lire le fichier prend un peu de temps)
        drapeau = f"signalement_pret_{cle}"
        if not st.session_state.get(drapeau):
            if st.button(t("Préparer le diagnostic"), key=f"preparer_signalement_{cle}", icon=":material/description:"):
                st.session_state[drapeau] = True
                st.rerun()
            return
        contexte = {"Espace": st.session_state.get("espace_actif", ""),
                    "Langue": "anglais" if langues.anglais() else "français"}
        texte = signalement.diagnostic(st.session_state, brut, nom_fichier, contexte)
        limite = 1200 if dans_barre else 3000
        st.code(texte[:limite] + ("\n… (" + t("suite dans le fichier") + ")" if len(texte) > limite else ""),
                language=None)
        st.download_button(t("Télécharger le diagnostic"), data=texte.encode("utf-8"),
                           file_name="diagnostic_portfolio_tracker.txt", mime="text/plain",
                           icon=":material/download:", key=f"signalement_{cle}", type="tertiary" if dans_barre
                           else "secondary")
        contact = signalement.consigne()
        st.caption(t("À envoyer à : {contact}", contact=contact) if contact else
                   t("À envoyer à la personne qui vous a transmis l'application."))

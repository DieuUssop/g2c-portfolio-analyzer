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
    """Repli « Signaler un problème » : l'utilisateur choisit un sujet, écrit son message, joint s'il le veut
    le diagnostic anonymisé (visible avant l'envoi), puis ouvre l'e-mail déjà rempli dans sa messagerie ou
    dans Gmail ; il n'a plus qu'à cliquer « Envoyer ». Rien ne part automatiquement."""
    contact = signalement.consigne()
    with st.expander(t("Signaler un problème"), icon=":material/bug_report:"):
        st.caption(t("Écrivez votre question ou votre problème : il arrivera par e-mail au créateur du logiciel."))
        sujet = st.selectbox(t("Sujet"), signalement.SUJETS, format_func=t, key=f"sujet_signalement_{cle}")
        message = st.text_area(t("Votre message"), key=f"message_signalement_{cle}", height=120,
                               placeholder=t("Que s'est-il passé ? Quel fichier, quel écran ? Ce que vous attendiez…"))
        erreur_recente = bool(st.session_state.get("erreurs_affichees"))
        joindre = st.checkbox(t("Joindre le diagnostic anonymisé"), value=erreur_recente or brut is not None,
                              key=f"joindre_signalement_{cle}",
                              help=t("Version du logiciel, erreurs affichées et fichier envoyé, sans données "
                                     "personnelles (nom, adresse, e-mail, téléphone, numéros de compte masqués)."))
        texte_diagnostic = None
        if joindre:
            contexte = {"Espace": st.session_state.get("espace_actif", ""),
                        "Langue": "anglais" if langues.anglais() else "français"}
            texte_diagnostic = _diagnostic(cle, brut, nom_fichier, contexte)
            with st.popover(t("Voir le diagnostic joint"), icon=":material/visibility:"):
                st.code(texte_diagnostic[:3000] + ("\n…" if len(texte_diagnostic) > 3000 else ""), language=None)
                st.download_button(t("Télécharger le diagnostic complet"), data=texte_diagnostic.encode("utf-8"),
                                   file_name="diagnostic_portfolio_tracker.txt", mime="text/plain",
                                   icon=":material/download:", key=f"signalement_{cle}")
        if not contact:
            st.caption(t("À envoyer à la personne qui vous a transmis l'application."))
            return
        objet = signalement.objet(t(sujet))
        corps = signalement.corps(message, texte_diagnostic)
        gauche, droite = (st.container(), st.container()) if dans_barre else st.columns(2)   # barre étroite : empilés
        gauche.link_button(t("Ouvrir dans ma messagerie"), signalement.lien_mailto(contact, objet, corps),
                           icon=":material/mail:", width="stretch", disabled=not message.strip())
        droite.link_button(t("Ouvrir dans Gmail"), signalement.lien_gmail(contact, objet, corps),
                           icon=":material/open_in_new:", width="stretch", disabled=not message.strip())
        if not message.strip():
            st.caption(t("Écrivez d'abord votre message."))
        st.caption(t("Rien ne s'ouvre ? Copiez le message (icône en haut à droite du cadre) et envoyez-le à {contact}.",
                     contact=contact))
        st.code(f"{objet}\n\n{corps}", language=None)


def _diagnostic(cle, brut, nom_fichier, contexte):
    """Diagnostic préparé une fois par fichier (la lecture d'un PDF prend un peu de temps)."""
    import hashlib
    empreinte = (cle, hashlib.md5(brut).hexdigest() if brut else "", len(st.session_state.get("erreurs_affichees") or []))
    memoire = st.session_state.setdefault("diagnostics_prets", {})
    if empreinte not in memoire:
        memoire[empreinte] = signalement.diagnostic(st.session_state, brut, nom_fichier, contexte)
    return memoire[empreinte]

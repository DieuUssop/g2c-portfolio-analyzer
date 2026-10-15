"""
vues_transactions.py — Onglet « Transactions » : historique des opérations, et
modification (suppression ou correction) de n'importe quelle opération.

Ce qui est modifié, c'est le FICHIER du portefeuille lui-même (format du projet :
date, type, ticker, nom, quantité, prix dans la devise de cotation, frais),
pas le tableau converti en euros affiché par ailleurs.

Selon l'origine du portefeuille :
    - espace personnel : réenregistré chiffré ; la version précédente est gardée
      (bouton « Annuler la dernière modification ») ;
    - fichier envoyé sans compte ou portefeuille d'exemple : modification valable
      pour la session, fichier corrigé proposé au téléchargement.

Appelé par app.py : vues_transactions.afficher(res, contenu, cible, session_compte).
"""

import pandas as pd
import streamlit as st

from . import langues, mouvements
from . import interface as ui
from .devises import devise_par_suffixe
from .langues import t, td


def html(morceau):
    st.markdown(morceau, unsafe_allow_html=True)


def afficher(res, contenu, cible, session_compte):
    """cible : {"type": "perso", "id", "nom"} ou {"type": "session", "origine", "nom"}."""
    transactions = res["transactions"]
    if st.session_state.get("message_transactions"):
        st.success(st.session_state.pop("message_transactions"))
    with st.container(border=True):
        tete, bouton = st.columns([4, 1], vertical_alignment="bottom")
        with tete:
            html(ui.titre_section(t("Historique des opérations")))
        edition = st.session_state.get("edition_operations", False)
        if bouton.button(t("Terminer") if edition else t("Modifier les opérations"),
                         type="secondary", width="stretch", key="bouton_edition_operations",
                         help=t("Supprimer ou corriger n'importe quelle opération du portefeuille")):
            st.session_state["edition_operations"] = not edition
            st.rerun()

        gauche, droite = st.columns(2)
        choix_types = gauche.multiselect(t("Type"), ["ACHAT", "VENTE", "DIVIDENDE"],
                                         default=["ACHAT", "VENTE", "DIVIDENDE"], format_func=td)
        choix_titres = droite.multiselect(t("Titres"), sorted(transactions["nom"].unique()),
                                          placeholder=t("Tous les titres"))
        if edition:
            _edition(contenu, cible, session_compte, transactions, choix_types, choix_titres)
        else:
            _consultation(transactions, choix_types, choix_titres)
            _bouton_annuler(cible, session_compte)


# ----------------------------------------------------------------------
# Consultation (tableau converti en euros)
# ----------------------------------------------------------------------
def _consultation(transactions, choix_types, choix_titres):
    filtre = transactions["type"].isin(choix_types)
    if choix_titres:
        filtre &= transactions["nom"].isin(choix_titres)
    selection = transactions[filtre].sort_values("date", ascending=False)
    st.caption(t("{n} opération(s) affichée(s) sur {total}", n=len(selection), total=len(transactions)))
    st.dataframe(
        selection.assign(type=selection["type"].map(td)), hide_index=True, width="stretch",
        column_config={
            "date": st.column_config.DateColumn("Date", format="DD MMM YYYY" if langues.anglais() else "DD/MM/YYYY"),
            "type": st.column_config.TextColumn(t("Type")),
            "ticker": st.column_config.TextColumn("Ticker"),
            "nom": st.column_config.TextColumn(t("Titre")),
            "quantite": st.column_config.NumberColumn(t("Quantité"), format="%d"),
            "prix": st.column_config.NumberColumn(t("Prix / montant (€)"), format=langues.eur_colonne("%.2f")),
            "frais": st.column_config.NumberColumn(t("Frais"), format=langues.eur_colonne("%.2f")),
            "devise": st.column_config.TextColumn(t("Devise")),
            "prix_devise": st.column_config.NumberColumn(t("Prix en devise"), format="%.2f",
                                                         help=t("Prix saisi, avant conversion en euros")),
            "taux_change": st.column_config.NumberColumn(t("Taux de change"), format="%.4f",
                                                         help=t("1 € en devise, le jour de l'opération (taux "
                                                                "utilisé pour la conversion en euros)")),
        },
    )
    # Le fichier téléchargé garde le format d'origine (types ACHAT / VENTE / DIVIDENDE)
    st.download_button(
        t("Télécharger la sélection (CSV)"), data=selection.to_csv(index=False).encode("utf-8"),
        file_name="transactions_selection.csv", mime="text/csv",
    )


# ----------------------------------------------------------------------
# Modification : supprimer ou corriger
# ----------------------------------------------------------------------
def _edition(contenu, cible, session_compte, transactions, choix_types, choix_titres):
    source = mouvements.lire(contenu)
    noms = dict(zip(transactions["ticker"], transactions["nom"]))         # noms complets (référentiel)
    source["nom"] = [n if str(n).strip() else noms.get(tk, tk) for n, tk in zip(source["nom"], source["ticker"])]
    filtre = source["type"].isin(choix_types)
    if choix_titres:
        filtre &= source["nom"].isin(choix_titres) | source["ticker"].map(noms).isin(choix_titres)
    vue = source[filtre].sort_values("date", ascending=False)

    if cible["type"] == "perso":
        html(ui.note(t("Les modifications seront enregistrées dans votre espace (chiffré). La version actuelle est "
                       "conservée : vous pourrez revenir en arrière.")))
    else:
        html(ui.note(t("Portefeuille hors de votre espace : les modifications valent pour cette session. Le fichier "
                       "corrigé pourra être téléchargé.")))
    st.caption(t("Cochez « Supprimer » ou modifiez directement la date, la quantité, le prix ou les frais. "
                 "Le prix est celui de la devise de cotation du titre."))

    tableau = vue.assign(supprimer=False, devise=[devise_par_suffixe(tk) for tk in vue["ticker"]],
                         type_affiche=vue["type"].map(td))
    tableau = tableau[["supprimer", "date", "type_affiche", "ticker", "nom", "quantite", "prix", "devise", "frais"]]
    edite = st.data_editor(
        tableau, key=f"editeur_operations_{cible.get('id') or cible.get('origine')}", hide_index=True,
        width="stretch", num_rows="fixed",
        disabled=["type_affiche", "ticker", "nom", "devise"],
        column_config={
            "supprimer": st.column_config.CheckboxColumn(t("Supprimer"), default=False, width="small"),
            "date": st.column_config.DateColumn("Date", format="DD MMM YYYY" if langues.anglais() else "DD/MM/YYYY"),
            "type_affiche": st.column_config.TextColumn(t("Type")),
            "ticker": st.column_config.TextColumn("Ticker"),
            "nom": st.column_config.TextColumn(t("Titre")),
            "quantite": st.column_config.NumberColumn(t("Quantité"), min_value=0.0, format="%g"),
            "prix": st.column_config.NumberColumn(t("Prix (devise de cotation)"), min_value=0.0, format="%.4g"),
            "devise": st.column_config.TextColumn(t("Devise")),
            "frais": st.column_config.NumberColumn(t("Frais"), min_value=0.0, format="%.2f"),
        },
    )
    edite = pd.DataFrame(edite).set_axis(tableau.index)
    nouveau, supprimees, corrections = mouvements.appliquer_modifications(source, edite)
    nb_corrigees = len({c["ligne"] for c in corrections})
    if supprimees.empty and not corrections:
        st.caption(t("Aucune modification pour l'instant."))
        _bouton_annuler(cible, session_compte)
        return

    # Récapitulatif
    html(ui.titre_section(t("Récapitulatif"), t("{s} suppression(s) · {c} correction(s)", s=len(supprimees),
                                                    c=nb_corrigees)))
    lignes = []
    for _, l in supprimees.iterrows():
        lignes.append([t("Supprimée"), _decrire(l)])
    libelles = {"date": t("date"), "quantite": t("quantité"), "prix": t("prix"), "frais": t("frais")}
    for c in corrections:
        l = source.loc[c["ligne"]]
        lignes.append([t("Corrigée"), _decrire(l) + " · " + t("{champ} : {avant} → {apres}", champ=libelles[c["champ"]],
                                                             avant=_valeur(c["avant"]), apres=_valeur(c["apres"]))])
    from html import escape
    from .lecture import tableau_html
    html(tableau_html([t("Action"), t("Opération")], [[escape(a), escape(b)] for a, b in lignes], droite_a_partir_de=9))

    # Contrôles : vente à découvert, date future, quantité ou prix nul
    alertes = mouvements.controler(nouveau)
    bloquantes = [a for a in alertes if a["bloquant"]]
    for a in bloquantes:
        st.error(t(a["message"], **a["valeurs"]))
    if any("Vente de" in a["message"] for a in bloquantes):
        st.caption(t("Si vous supprimez un achat, supprimez aussi la ou les ventes qui en dépendent (même titre, "
                     "date postérieure)."))
    disparus = mouvements.titres_disparus(source, nouveau)
    if disparus and not bloquantes:
        st.warning(t("Après cette modification, ces titres ne sont plus détenus : {titres}.",
                     titres=", ".join(noms.get(tk, tk) for tk in disparus)))
    if nouveau.empty:
        st.error(t("Le portefeuille ne peut pas être vide : gardez au moins une opération."))
        bloquantes = bloquantes + [{"message": "vide"}]

    a, b, _ = st.columns([2, 1, 2])
    confirme = a.checkbox(t("Je confirme ces modifications"), key="confirmer_modifications", disabled=bool(bloquantes))
    if a.button(t("Enregistrer les modifications"), type="primary", disabled=bool(bloquantes) or not confirme,
                key="enregistrer_modifications", width="stretch"):
        _enregistrer(nouveau, contenu, cible, session_compte, len(supprimees), nb_corrigees)
    if b.button(t("Tout annuler"), key="abandonner_modifications", width="stretch"):
        st.session_state.pop(f"editeur_operations_{cible.get('id') or cible.get('origine')}", None)
        st.session_state["edition_operations"] = False
        st.rerun()


def _decrire(ligne):
    date = pd.Timestamp(ligne["date"]).strftime("%d/%m/%Y")
    return f"{date} · {td(ligne['type'])} · {ligne['quantite']:g} {ligne['nom'] or ligne['ticker']}"


def _valeur(v):
    if isinstance(v, pd.Timestamp):
        return v.strftime("%d/%m/%Y")
    texte = f"{float(v):g}"
    return texte if langues.anglais() else texte.replace(".", ",")


def _enregistrer(nouveau, contenu_actuel, cible, session_compte, nb_supprimees, nb_corrigees):
    contenu = mouvements.en_csv(nouveau)
    if cible["type"] == "perso" and session_compte is not None:
        session_compte.enregistrer(cible["nom"], contenu, identifiant=cible["id"], garder_precedente=True)
        message = t("Portefeuille « {nom} » modifié : {s} suppression(s), {c} correction(s). « Annuler la dernière "
                    "modification » permet de revenir en arrière.", nom=cible["nom"], s=nb_supprimees, c=nb_corrigees)
    else:
        st.session_state["fusion_session"] = {"origine": cible["origine"], "contenu": contenu, "nom": cible["nom"],
                                              "precedent": contenu_actuel}
        message = t("Modifications appliquées pour cette session : {s} suppression(s), {c} correction(s). "
                    "Téléchargez le fichier mis à jour pour le garder.", s=nb_supprimees, c=nb_corrigees)
    st.session_state["message_compte"] = message
    st.session_state["message_transactions"] = message
    st.session_state["edition_operations"] = False
    st.rerun()


def _bouton_annuler(cible, session_compte):
    """« Annuler la dernière modification » : version précédente du portefeuille."""
    if cible["type"] == "perso" and session_compte is not None:
        fiche = next((p for p in session_compte.lister() if p["id"] == cible["id"]), None)
        if fiche and fiche.get("precedente"):
            if st.button(t("Annuler la dernière modification"), key="annuler_modif_transactions",
                         help=t("Revenir à la version du {date}", date=fiche["precedente"].get("maj", ""))):
                session_compte.annuler_derniere_modification(cible["id"])
                st.session_state["edition_operations"] = False
                st.rerun()
    else:
        fusion = st.session_state.get("fusion_session")
        if fusion and fusion.get("origine") == cible.get("origine") and fusion.get("precedent") is not None:
            if st.button(t("Annuler la dernière modification"), key="annuler_modif_session"):
                import hashlib
                if hashlib.md5(fusion["precedent"]).hexdigest()[:12] == cible.get("origine"):
                    st.session_state.pop("fusion_session")           # retour au fichier d'origine
                else:
                    fusion["contenu"], fusion["precedent"] = fusion["precedent"], None
                st.session_state["edition_operations"] = False
                st.rerun()


# ----------------------------------------------------------------------
# Effet marché et effet change (titres cotés hors zone euro)
# ----------------------------------------------------------------------
def effet_change(tableau, positions):
    """Plus-value latente des titres en devise, séparée en effet marché et effet change."""
    from .interface import euros
    lignes = tableau.join(positions[["nom"]]).reset_index()
    total_change, total_marche = lignes["effet_change"].sum(), lignes["effet_marche"].sum()
    with st.container(border=True):
        html(ui.titre_section(
            t("Effet marché et effet change"),
            t("Titres cotés hors zone euro · effet change total {change}, effet marché {marche}",
              change=euros(total_change, signe=True), marche=euros(total_marche, signe=True))))
        st.dataframe(
            lignes[["ticker", "nom", "devise", "taux_achat", "taux_actuel", "effet_marche", "effet_change",
                    "pv_latente"]],
            hide_index=True, width="stretch",
            column_config={
                "ticker": st.column_config.TextColumn("Ticker", width="small"),
                "nom": st.column_config.TextColumn(t("Titre")),
                "devise": st.column_config.TextColumn(t("Devise"), width="small"),
                "taux_achat": st.column_config.NumberColumn(
                    t("Taux à l'achat"), format="%.4f",
                    help=t("1 € en devise : taux moyen des achats encore détenus")),
                "taux_actuel": st.column_config.NumberColumn(t("Taux actuel"), format="%.4f",
                                                             help=t("1 € en devise aujourd'hui")),
                "effet_marche": st.column_config.NumberColumn(
                    t("Effet marché"), format=langues.eur_colonne("%+.0f"),
                    help=t("Gain du titre dans sa devise, compté au taux d'achat (frais d'achat déduits)")),
                "effet_change": st.column_config.NumberColumn(
                    t("Effet change"), format=langues.eur_colonne("%+.0f"),
                    help=t("Gain ou perte dû à la variation de la devise depuis l'achat")),
                "pv_latente": st.column_config.NumberColumn(t("+/- value"), format=langues.eur_colonne("%+.0f")),
            },
        )
        st.caption(t("Effet change = quantité × cours en devise × (1 / taux actuel − 1 / taux à l'achat). "
                     "Une devise qui baisse face à l'euro (taux qui monte) donne un effet change négatif."))


# ----------------------------------------------------------------------
# Opérations sur titres : divisions d'actions non appliquées, titres reçus sans prix (scission)
# ----------------------------------------------------------------------
def _sauver(nouveau, contenu_actuel, cible, session_compte, message):
    contenu = mouvements.en_csv(nouveau)
    if cible["type"] == "perso" and session_compte is not None:
        session_compte.enregistrer(cible["nom"], contenu, identifiant=cible["id"], garder_precedente=True)
    else:
        st.session_state["fusion_session"] = {"origine": cible["origine"], "contenu": contenu, "nom": cible["nom"],
                                              "precedent": contenu_actuel}
        message += " " + t("Téléchargez le fichier mis à jour pour le garder.")
    st.session_state["message_compte"] = message
    st.session_state["message_transactions"] = message
    st.rerun()


def proposer_divisions(divisions, contenu, cible, session_compte):
    """Divisions d'actions connues de Yahoo Finance que le fichier n'a pas prises en compte :
    explication et bouton pour ajuster les opérations antérieures (après confirmation)."""
    par_titre = {}
    for d in divisions:
        par_titre.setdefault(d["ticker"], []).append(d)
    for ticker, liste in par_titre.items():
        with st.container(border=True):
            html(ui.titre_section(t("Division ou regroupement d'actions détecté"), f"{liste[0]['nom']} ({ticker})"))
            for d in liste:
                parite = (t("1 ancienne → {n} nouvelles", n=f"{d['facteur']:g}") if d["facteur"] > 1
                          else t("{n} anciennes → 1 nouvelle", n=f"{1 / d['facteur']:g}"))
                if d.get("deduite"):
                    st.write(t("{nature} constaté d'après les cours (date exacte inconnue) : {parite} — {n} opération(s) "
                               "à convertir, jusqu'au {date}.",
                               nature=t("Division") if d["facteur"] > 1 else t("Regroupement"), parite=parite,
                               n=d["operations"], date=(d["date"] - pd.Timedelta(days=1)).strftime("%d/%m/%Y")))
                else:
                    st.write(t("{nature} le {date} : {parite} ({n} opération(s) antérieure(s)).",
                               nature=t("Division") if d["facteur"] > 1 else t("Regroupement"),
                               date=d["date"].strftime("%d/%m/%Y"), parite=parite, n=d["operations"]))
            st.caption(t("Vos prix d'achat d'avant cette date sont dans les anciennes unités, alors que les cours de "
                         "Yahoo Finance sont ajustés : quantités, valeur et plus-values sont faussées. Ajuster convertit "
                         "ces opérations (quantité × facteur, prix ÷ facteur) ; le montant investi ne change pas."))
            if st.button(t("Ajuster les opérations de {ticker}", ticker=ticker), type="primary",
                         key=f"division_{ticker}", icon=":material/call_split:"):
                tableau, total = contenu, 0
                for d in liste:
                    tableau, n = mouvements.appliquer_division(tableau, ticker, d["date"], d["facteur"])
                    total += n
                _sauver(tableau, contenu, cible, session_compte,
                        t("{n} opération(s) de {ticker} ajustée(s) (division d'actions).", n=total, ticker=ticker))


def alertes_titres(alertes):
    """Titres reçus sans prix d'achat (scission / spin-off, attribution gratuite) : signalés
    au lieu d'arrêter le calcul."""
    if not alertes:
        return
    lignes = []
    for a in alertes:
        if a["type"] == "pru_nul":
            lignes.append(t("{nom} ({ticker}) : {q:g} titre(s) détenu(s) sans prix d'achat (PRU de 0) — toute sa "
                            "valeur compte comme plus-value.", nom=a["nom"], ticker=a["ticker"], q=a["quantite"]))
        elif a["type"] == "vente_sans_achat":
            lignes.append(t("{nom} ({ticker}) : vente de {q:g} titre(s) le {date} sans achat enregistré — comptés "
                            "reçus à un prix de revient nul.", nom=a["nom"], ticker=a["ticker"], q=a["quantite"],
                            date=a["date"].strftime("%d/%m/%Y")))
    html(ui.note(t("Titres reçus sans prix d'achat (scission, attribution gratuite ?)") + " : " + " ".join(lignes)
                 + " " + t("Pour un calcul juste, répartissez le prix de revient de la société d'origine entre les "
                           "deux titres selon la clé publiée par l'émetteur, avec « Modifier les opérations » dans "
                           "l'onglet « Transactions »."), attention=True))


def cours_corriges(notes):
    """Historique de cours corrigé (regroupement non ajusté par Yahoo Finance) : on le dit."""
    for n in notes or []:
        html(ui.note(t("{ticker} : le cours fait un bond de ×{f} le {date} sans que Yahoo Finance l'ait ajusté "
                       "(regroupement d'actions). Les cours d'avant cette date ont été ramenés dans les nouvelles "
                       "unités pour les calculs.", ticker=n["ticker"], f=f"{n['facteur']:g}",
                       date=n["date"].strftime("%d/%m/%Y"))))


def operations_appliquees(notes):
    """Regroupements d'actions connus appliqués d'office aux calculs (ORPEA 1 000 pour 1…)."""
    for n in notes or []:
        html(ui.note(t(n["libelle"]) + ". " + t(
            "{nom} : {k} opération(s) d'avant cette date ramenée(s) dans les nouvelles unités pour les calculs "
            "(quantité × {f}, prix ÷ {f}). Votre fichier n'est pas modifié.",
            nom=n["nom"], k=n["operations"], f=f"{n['facteur']:g}")))


def valeurs_incoherentes(lignes):
    """Ligne qui vaut plus de 50 fois son prix de revient : sans doute une division ou un
    regroupement d'actions non appliqué."""
    for v in lignes or []:
        html(ui.note(t("{nom} ({ticker}) vaut {multiple:.0f} fois son prix de revient ({valeur} € pour {investi} € "
                       "investis). C'est presque toujours un regroupement ou une division d'actions non appliqué, "
                       "pas une vraie hausse : vérifiez la quantité détenue (avis d'opération sur titres de votre "
                       "courtier) et corrigez-la avec « Modifier les opérations » dans l'onglet « Transactions ».",
                       nom=v["nom"], ticker=v["ticker"], multiple=v["multiple"],
                       valeur=f"{v['valeur']:,.0f}".replace(",", " "),
                       investi=f"{v['investi']:,.0f}".replace(",", " ")), attention=True))

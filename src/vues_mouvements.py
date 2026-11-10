"""
vues_mouvements.py — Page « Ajouter des opérations » : mettre à jour un
portefeuille avec seulement les NOUVEAUX mouvements, sans renvoyer tout
l'historique.

Trois façons d'ajouter :
    1. un fichier Excel / CSV des dernières opérations (n'importe quel format) ;
    2. un ou plusieurs PDF (avis d'opéré, relevé, y compris scannés) ; si un PDF n'est pas lu
       automatiquement, un formulaire pré-rempli permet de compléter l'opération (src/vues_pdf.py) ;
    3. une saisie à la main (un ordre d'achat, par exemple).

Avant d'enregistrer : tableau de vérification modifiable, doublons décochés,
contrôles bloquants (vente de titres non détenus, date future).
Les calculs sont dans src/mouvements.py.
"""

import hashlib

import pandas as pd
import streamlit as st

from . import vues_signalement
from . import images, import_fichier, lecture_pdf, mouvements, vues_pdf
from . import interface as ui
from .langues import t, td


def html(morceau):
    st.markdown(morceau, unsafe_allow_html=True)


def ouvrir(cible):
    """Ouvre la page pour un portefeuille. cible : {"type": "perso"|"session", "id", "nom", "contenu"}."""
    st.session_state["ajout_operations"] = cible
    st.session_state.pop("ops_ajoutees", None)
    st.session_state.pop("page_compte", None)


def fermer():
    for cle in ("ajout_operations", "ops_ajoutees", "ops_fichiers"):
        st.session_state.pop(cle, None)


_resoudre_titre = vues_pdf.resoudre_titre       # ticker et nom d'un titre saisi à la main


def _avis_ost(brut):
    """Avis de division / regroupement d'actions (src/lecture_pdf.lire_ost), ou None."""
    if import_fichier.nature_fichier(brut) != "pdf":
        return None
    try:
        texte = "\n".join(p["texte"] for p in import_fichier._pages_pdf(brut))
    except Exception:
        return None
    return lecture_pdf.lire_ost(texte)


def _proposer_ost(ost, nom_fichier, empreinte, cible, session_compte):
    """Avis d'opération sur titres : propose d'ajuster les opérations antérieures du titre."""
    with st.container(border=True):
        html(ui.titre_section(t("Opération sur titres"), nom_fichier))
        try:
            ticker, nom = vues_pdf.resoudre_titre(ost["isin"])
        except Exception:
            st.warning(t("Titre introuvable : {titre}. Indiquez son ticker Yahoo Finance (ex. MC.PA).",
                         titre=ost["isin"]))
            return
        facteur = ost["facteur"]
        parite = (t("1 ancienne → {n} nouvelles", n=f"{facteur:g}") if facteur > 1
                  else t("{n} anciennes → 1 nouvelle", n=f"{1 / facteur:g}"))
        st.write(t("{nature} de {titre} ({ticker}) le {date} : {parite}.",
                   nature=t("Division") if facteur > 1 else t("Regroupement"), titre=nom or ost["libelle"],
                   ticker=ticker, date=ost["date"] or "?", parite=parite))
        ajuste, n = mouvements.appliquer_division(cible["contenu"], ticker, pd.to_datetime(ost["date"], dayfirst=True),
                                                  facteur)
        if not n:
            st.caption(t("Aucune opération de ce titre avant cette date : rien à ajuster."))
            return
        st.caption(t("Les {n} opération(s) antérieures seront converties (quantité × {f}, prix ÷ {f}), comme les "
                     "cours de Yahoo Finance, déjà ajustés.", n=n, f=f"{facteur:g}"))
        if st.button(t("Appliquer aux opérations antérieures"), type="primary", key=f"ost_{empreinte}"):
            contenu = mouvements.en_csv(ajuste)
            if cible["type"] == "perso" and session_compte is not None:
                session_compte.enregistrer(cible["nom"], contenu, identifiant=cible["id"], garder_precedente=True)
            else:
                st.session_state["fusion_session"] = {"origine": cible["origine"], "contenu": contenu,
                                                      "nom": cible["nom"]}
            st.session_state["message_compte"] = t("{n} opération(s) de {ticker} ajustée(s).", n=n, ticker=ticker)
            fermer()
            st.rerun()


def page(session_compte, importer):
    cible = st.session_state["ajout_operations"]
    ajoutees = st.session_state.setdefault("ops_ajoutees", [])
    html(ui.titre_section(t("Ajouter des opérations"), t("Portefeuille : {nom}", nom=cible["nom"])))
    if st.button(t("Retour au tableau de bord"), icon=":material/arrow_back:", key="retour_ajout"):
        fermer()
        st.rerun()
    html(ui.note(t("Envoyez seulement les nouveaux mouvements : un avis d'opéré (PDF), un export des dernières "
                   "opérations (Excel, CSV ou PDF), ou saisissez un ordre à la main. Les opérations déjà présentes "
                   "sont reconnues et ne sont pas ajoutées deux fois.")))

    fichier_tab, saisie_tab = st.tabs([t("Depuis un fichier"), t("Saisie manuelle")])
    with fichier_tab:
        fichiers = st.file_uploader(t("Fichiers (CSV, Excel, PDF ou image)"),
                                    type=["csv", "xlsx", "pdf"] + images.EXTENSIONS,
                                    accept_multiple_files=True, key="ops_fichiers")
        for f in fichiers or []:
            if vues_pdf.est_annule(f.getvalue()):
                st.caption(t("Lecture annulée : {nom}", nom=f.name))
                continue
            brut = vues_pdf.version_lisible(f.getvalue())          # PDF déchiffré si mot de passe donné
            empreinte = hashlib.md5(brut).hexdigest()[:12]
            if any(a.get("source") == empreinte for a in ajoutees):
                continue
            if import_fichier.est_protege(brut):
                vues_pdf.demander_mot_de_passe(brut, f.name, empreinte)
                continue
            ost = _avis_ost(brut)
            if ost is not None:                                     # division ou regroupement d'actions
                _proposer_ost(ost, f.name, empreinte, cible, session_compte)
                continue
            attente, valeurs = import_fichier.message_attente(brut)
            with st.spinner(f.name + " · " + t(attente, **valeurs)):
                resultat = importer(brut)
            if resultat["sur"]:
                tableau = resultat["transactions"][mouvements.COLONNES].copy()
                tableau["source"] = empreinte
                ajoutees.extend(tableau.to_dict("records"))
                st.success(t("{nom} : {n} opération(s) lue(s).", nom=f.name, n=len(tableau)))
            elif import_fichier.nature_fichier(brut) == "pdf":
                # PDF non lu automatiquement : formulaire pré-rempli avec ce qui a été trouvé
                operation = vues_pdf.formulaire(brut, f.name, empreinte, raison=resultat["raison"])
                if operation is not None:
                    ajoutees.append({**operation, "source": empreinte})
                    st.rerun()
            else:
                st.error(t("{nom} : {raison}", nom=f.name, raison=t(resultat["raison"])))
                vues_signalement.noter_erreur("ajout d'opérations", t("{nom} : {raison}", nom=f.name, raison=t(resultat["raison"])))
                st.caption(t("Pour un format inhabituel, envoyez le fichier depuis la barre latérale : "
                             "l'assistant d'import vous guidera."))
    with saisie_tab:
        with st.form("saisie_operation", clear_on_submit=True, border=False):
            a, b, c = st.columns(3)
            date = a.date_input(t("Date"), value=pd.Timestamp.today(), format="DD/MM/YYYY")
            sens = b.selectbox(t("Type"), ["ACHAT", "VENTE", "DIVIDENDE", "VERSEMENT", "RETRAIT", "FRAIS"],
                               format_func=td, help=t("Versement, retrait, frais : mouvements d'espèces du compte "
                                                      "(sans titre : le montant va dans « prix »)"))
            titre = c.text_input(t("Titre"), placeholder=t("Ticker, ISIN, nom ou code Bloomberg"))
            a, b, c = st.columns(3)
            quantite = a.number_input(t("Quantité"), min_value=0.0, value=1.0, step=1.0)
            prix = b.number_input(t("Prix unitaire (devise du titre) ou montant du dividende"), min_value=0.0,
                                  value=0.0, step=1.0)
            frais = c.number_input(t("Frais (€)"), min_value=0.0, value=0.0, step=0.5)
            if st.form_submit_button(t("Ajouter à la liste"), icon=":material/add:"):
                try:
                    if sens in ("VERSEMENT", "RETRAIT", "FRAIS"):
                        if prix <= 0:
                            raise ValueError(t("Indiquez le montant dans « prix »."))
                        ajoutees.append({"date": pd.Timestamp(date), "type": sens, "ticker": "ESPECES",
                                         "nom": titre.strip() or td(sens).capitalize(), "quantite": 0.0,
                                         "prix": prix, "frais": 0.0, "source": "saisie"})
                    else:
                        if not titre.strip():
                            raise ValueError(t("Indiquez le titre."))
                        with st.spinner(t("Recherche du titre...")):
                            ticker, nom = _resoudre_titre(titre)
                        ajoutees.append({"date": pd.Timestamp(date), "type": sens, "ticker": ticker,
                                         "nom": nom or titre.strip(), "quantite": quantite, "prix": prix,
                                         "frais": frais, "source": "saisie"})
                except Exception as erreur:
                    st.error(str(erreur))
                    vues_signalement.noter_erreur("ajout d'opérations", str(erreur))

    if not ajoutees:
        return
    # ------------------------------------------------------------------ vérification
    nouvelles = pd.DataFrame(ajoutees)[mouvements.COLONNES]
    preparees, _ = mouvements.preparer(cible["contenu"], nouvelles)
    with st.container(border=True):
        html(ui.titre_section(t("Vérification avant enregistrement"),
                              t("Décochez une ligne pour ne pas l'ajouter. Les cellules sont modifiables.")))
        affichage = preparees.assign(statut=preparees["statut"].map(t))
        modifiees = st.data_editor(
            affichage[["inclure", "statut"] + mouvements.COLONNES], hide_index=True, width="stretch",
            key="verification_ops", disabled=["statut"],
            column_config={
                "inclure": st.column_config.CheckboxColumn(t("Ajouter")),
                "statut": st.column_config.TextColumn(t("Statut")),
                "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                "type": st.column_config.SelectboxColumn(t("Type"), options=["ACHAT", "VENTE", "DIVIDENDE", "VERSEMENT",
                                                                             "RETRAIT", "FRAIS", "SOLDE"]),
                "ticker": st.column_config.TextColumn("Ticker"),
                "nom": st.column_config.TextColumn(t("Titre")),
                "quantite": st.column_config.NumberColumn(t("Quantité")),
                "prix": st.column_config.NumberColumn(t("Prix")),
                "frais": st.column_config.NumberColumn(t("Frais")),
            })
        retenues = modifiees[modifiees["inclure"].astype(bool)]
        fusion = mouvements.fusionner(cible["contenu"], modifiees)
        alertes = mouvements.controler(fusion)
        bloquantes = [a for a in alertes if a["bloquant"]]
        for a in bloquantes:
            st.error(t(a["message"], **a["valeurs"]))
            vues_signalement.noter_erreur("ajout d'opérations", t(a["message"], **a["valeurs"]))
        # Solde des espèces : jamais sous 0 € (0 € pile reste permis)
        if controle_du_solde(fusion, ajoutees, "ajout", cible["contenu"]):
            bloquantes = bloquantes + [{"message": "solde"}]
        avant = mouvements.lire(cible["contenu"])
        st.caption(t("{n} opération(s) ajoutée(s) · {total} au total ({avant} avant)", n=len(retenues),
                     total=len(fusion), avant=len(avant)))
        a, b, _ = st.columns([2, 1, 2])
        if a.button(t("Enregistrer les opérations"), type="primary", icon=":material/save:",
                    disabled=bool(bloquantes) or retenues.empty, key="enregistrer_ops", width="stretch"):
            contenu = mouvements.en_csv(fusion)
            if cible["type"] == "perso" and session_compte is not None:
                session_compte.enregistrer(cible["nom"], contenu, identifiant=cible["id"], garder_precedente=True)
                st.session_state["message_compte"] = t("{n} opération(s) ajoutée(s) à « {nom} ». Vous pouvez "
                                                       "annuler cet ajout depuis « Mon compte ».",
                                                       n=len(retenues), nom=cible["nom"])
            else:
                st.session_state["fusion_session"] = {"origine": cible["origine"], "contenu": contenu,
                                                      "nom": cible["nom"]}
                st.session_state["message_compte"] = t("{n} opération(s) ajoutée(s) pour cette session. "
                                                       "Téléchargez le fichier mis à jour pour le garder.",
                                                       n=len(retenues))
            fermer()
            st.rerun()
        if b.button(t("Tout effacer"), key="effacer_ops", width="stretch"):
            st.session_state["ops_ajoutees"] = []
            st.rerun()


# ----------------------------------------------------------------------
# Fichiers qui ne contiennent QUE des mouvements d'espèces
# ----------------------------------------------------------------------
TYPES_ESPECES = ("VERSEMENT", "RETRAIT", "FRAIS", "SOLDE")


def seulement_especes(contenu):
    """Vrai si le fichier lu ne contient que des versements, retraits ou frais (aucun achat ni vente) :
    relevés d'espèces envoyés seuls, à AJOUTER à un portefeuille plutôt qu'à analyser à sa place."""
    try:
        tableau = mouvements.lire(contenu)
    except Exception:
        return False
    return not tableau.empty and tableau["type"].isin(TYPES_ESPECES).all()


def especes_seules(contenu, fichiers, fichier_choisi, session_compte, fusion_session=None):
    """Page affichée quand les fichiers envoyés ne contiennent que des mouvements d'espèces : leur
    contenu, puis un bouton pour les ajouter au portefeuille choisi dans la liste (espace personnel :
    enregistré ; portefeuille d'exemple : pour la session). Les fichiers sont ensuite mis de côté et le
    portefeuille, complété, s'affiche."""
    from pathlib import Path
    especes = mouvements.lire(contenu)
    with st.container(border=True):
        html(ui.titre_section(t("Mouvements d'espèces"),
                              t("{n} opération(s) : versements, retraits ou frais, sans achat ni vente de titres",
                                n=len(especes))))
        signe = especes["type"].map({"VERSEMENT": 1}).fillna(-1)
        # montants au format de la langue (« −200,00 € » ; « −€200.00 » en anglais)
        st.dataframe(especes.assign(type=especes["type"].map(td),
                                    montant=[ui.euros_cents(s * p, signe=True) for s, p in zip(signe, especes["prix"])])[
            ["date", "type", "nom", "montant"]], hide_index=True, width="stretch",
            column_config={"date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                           "type": st.column_config.TextColumn(t("Type")),
                           "nom": st.column_config.TextColumn(t("Libellé")),
                           "montant": st.column_config.TextColumn(t("Montant total (€)"))})
        html(ui.note(t("Ces documents ne contiennent aucun achat ni vente : il n'y a pas de portefeuille de titres à "
                       "analyser. Ajoutez-les au portefeuille qui contient vos achats et ventes : ils compteront "
                       "dans son solde en espèces et ses frais.")))
        # le portefeuille cible : celui choisi dans la liste de la barre latérale
        if isinstance(fichier_choisi, tuple) and session_compte is not None:
            base, nom, perso = session_compte.lire(fichier_choisi[1]), fichier_choisi[2], True
        elif fichier_choisi is not None and not isinstance(fichier_choisi, tuple):
            base, nom, perso = fichier_choisi.read_bytes(), fichier_choisi.name, False
        else:
            st.info(t("Choisissez d'abord votre portefeuille dans la liste de la barre latérale (ou envoyez-le en "
                      "même temps que ces documents)."))
            _bouton_fermer(fichiers)
            return
        origine = hashlib.md5(base).hexdigest()[:12]
        if fusion_session and fusion_session.get("origine") == origine:
            base = fusion_session["contenu"]
        preparees, _ = mouvements.preparer(base, especes)
        deja = int((~preparees["inclure"]).sum())
        if deja == len(preparees):
            # tout est déjà là : rien à ajouter, et surtout un moyen de sortir de cette page
            st.success(t("Ce document est déjà dans votre portefeuille « {nom} » : rien à ajouter.",
                         nom=Path(str(nom)).stem))
            _bouton_fermer(fichiers, principal=True)
            return
        if deja:
            st.caption(t("{n} mouvement(s) déjà dans ce portefeuille : non ajouté(s) une deuxième fois.", n=deja))
        solde_choisi = st.session_state.get("solde_especes_seules")
        if solde_choisi:                         # solde disponible indiqué avant ces relevés
            preparees = pd.concat([preparees, pd.DataFrame([{
                "date": pd.Timestamp(solde_choisi[0]), "type": "SOLDE", "ticker": "ESPECES", "nom": "Solde saisi",
                "quantite": 0.0, "prix": float(solde_choisi[1]), "frais": 0.0, "inclure": True,
                "statut": "nouvelle"}])], ignore_index=True)
        fusion = mouvements.fusionner(base, preparees)
        info, taux = st.session_state.get("devises_taux", ({}, {}))
        probleme = mouvements.controler_solde(fusion, info, taux)
        if probleme is not None and mouvements.controler_solde(base, info, taux) is not None:
            probleme = None                     # déjà négatif avant ces relevés : pas de blocage
        if probleme is not None:
            from .vues_transactions import message_solde_insuffisant
            st.error(message_solde_insuffisant(probleme))
            with st.popover(t("Indiquer le solde disponible avant l'opération"), icon=":material/edit:"):
                with st.form("solde_especes_seules_form", border=False):
                    minimum = mouvements.solde_minimum_necessaire(probleme)
                    st.caption(t("Il faut au moins {montant} sur le compte le {date} pour couvrir les opérations "
                                 "suivantes.", montant=ui.euros_cents(minimum),
                                 date=probleme["veille"].strftime("%d/%m/%Y")))
                    montant = st.number_input(t("Solde disponible (€)"), min_value=0.0, value=float(minimum),
                                              step=10.0, format="%.2f")
                    date = st.date_input(t("à la date du"), value=probleme["veille"], format="DD/MM/YYYY")
                    if st.form_submit_button(t("Enregistrer le solde"), type="primary"):
                        st.session_state["solde_especes_seules"] = (pd.Timestamp(date), float(montant))
                        st.rerun()
        gauche, droite = st.columns([3, 1])
        with droite:
            _bouton_fermer(fichiers)
        if gauche.button(t("Ajouter à « {nom} »", nom=Path(str(nom)).stem), type="primary", icon=":material/add:",
                         key="ajouter_especes", disabled=probleme is not None):
            nouveau = mouvements.en_csv(fusion)
            if perso:
                session_compte.enregistrer(nom, nouveau, identifiant=fichier_choisi[1], garder_precedente=True)
            else:
                st.session_state["fusion_session"] = {"origine": origine, "contenu": nouveau, "nom": nom}
            # fichiers mis de côté (comme « Annuler ») : le portefeuille complété s'affiche
            annules = st.session_state.setdefault("imports_ajoutes", set())
            for f in fichiers:
                annules.add(hashlib.md5(f.getvalue()).hexdigest()[:12])
                annules.add(hashlib.md5(vues_pdf.version_lisible(f.getvalue())).hexdigest()[:12])
            st.session_state.pop("solde_especes_seules", None)
            st.session_state["especes_ajoutees"] = t("{n} mouvement(s) d'espèces ajouté(s) à « {nom} ».",
                                                     n=len(preparees) - deja, nom=Path(str(nom)).stem)
            st.rerun()



# ----------------------------------------------------------------------
# Solde insuffisant (le solde des espèces ne doit jamais passer sous 0 €)
# ----------------------------------------------------------------------
def controle_du_solde(fusion, ajoutees, cle, base=None):
    """Affiche le message « Solde insuffisant » si une opération fait passer les espèces sous 0 €, avec
    « Annuler cette opération » (si elle fait partie des opérations ajoutées) et « Indiquer le solde
    disponible avant l'opération » (ligne SOLDE pré-remplie avec le minimum nécessaire, la veille).
    Renvoie True si l'enregistrement doit être bloqué. Sans solde connu : simple proposition."""
    from .vues_transactions import message_solde_insuffisant
    info, taux = st.session_state.get("devises_taux", ({}, {}))
    probleme = mouvements.controler_solde(fusion, info, taux)
    if probleme is not None and base is not None and mouvements.controler_solde(base, info, taux) is not None:
        # historique DÉJÀ négatif avant cet ajout (relevés incomplets) : on prévient sans bloquer
        st.warning(t("Le solde des espèces est déjà négatif dans ce portefeuille (des versements manquent sans "
                     "doute) : indiquez le solde disponible pour que le contrôle reprenne."))
        with st.popover(t("Indiquer le solde disponible avant l'opération"), icon=":material/edit:"):
            _formulaire_solde(ajoutees, probleme, f"{cle}_historique")
        return False
    if probleme is None:
        if ajoutees and not mouvements.solde_connu(fusion):
            with st.popover(t("Indiquer le solde disponible (facultatif)"), icon=":material/edit:"):
                _formulaire_solde(ajoutees, None, f"{cle}_facultatif")
        return False
    st.error(message_solde_insuffisant(probleme) + (" " + t("(montants en devise convertis au taux du jour)")
                                                    if probleme["approx"] else ""))
    gauche, droite = st.columns(2)
    correspond = [i for i, a in enumerate(ajoutees) if pd.Timestamp(a["date"]) == probleme["date"]
                  and a["type"] == probleme["type"] and a["ticker"] == probleme["ticker"]]
    if correspond and gauche.button(t("Annuler cette opération"), icon=":material/close:", key=f"annuler_op_{cle}"):
        ajoutees.pop(correspond[0])
        st.rerun()
    with droite.popover(t("Indiquer le solde disponible avant l'opération"), icon=":material/edit:"):
        _formulaire_solde(ajoutees, probleme, cle)
    return True


def _formulaire_solde(ajoutees, probleme, cle):
    """Saisie du solde disponible : ajoutée comme une ligne SOLDE aux opérations à enregistrer."""
    minimum = mouvements.solde_minimum_necessaire(probleme) if probleme else 0.0
    with st.form(f"solde_{cle}", border=False):
        if probleme:
            st.caption(t("Il faut au moins {montant} sur le compte le {date} pour couvrir les opérations suivantes.",
                         montant=ui.euros_cents(minimum), date=probleme["veille"].strftime("%d/%m/%Y")))
        montant = st.number_input(t("Solde disponible (€)"), min_value=0.0, value=float(minimum), step=10.0,
                                  format="%.2f")
        date = st.date_input(t("à la date du"), value=probleme["veille"] if probleme else pd.Timestamp.today(),
                             format="DD/MM/YYYY")
        if st.form_submit_button(t("Enregistrer le solde"), type="primary"):
            ajoutees[:] = [a for a in ajoutees if a["type"] != "SOLDE"]
            ajoutees.append({"date": pd.Timestamp(date), "type": "SOLDE", "ticker": "ESPECES", "nom": "Solde saisi",
                             "quantite": 0.0, "prix": float(montant), "frais": 0.0, "source": "solde"})
            st.rerun()



def _bouton_fermer(fichiers, principal=False):
    """« Fermer » : met les fichiers envoyés de côté et revient au portefeuille (jamais de page sans issue)."""
    if st.button(t("Fermer"), icon=":material/close:", key="fermer_especes", type="primary" if principal else "secondary",
                 help=t("Mettre ces fichiers de côté et revenir au portefeuille")):
        mis_de_cote = st.session_state.setdefault("imports_ajoutes", set())
        for f in fichiers:
            mis_de_cote.add(hashlib.md5(f.getvalue()).hexdigest()[:12])
            mis_de_cote.add(hashlib.md5(vues_pdf.version_lisible(f.getvalue())).hexdigest()[:12])
        st.rerun()

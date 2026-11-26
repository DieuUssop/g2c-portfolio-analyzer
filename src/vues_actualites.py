"""
vues_actualites.py — L'onglet « Actualités » (revue du 26/11/2026) et le bandeau des alertes de cours.

    1. quatre cartes : articles de la semaine, forte variation du jour, prochains résultats, prochain dividende ;
    2. le fil d'actualité de la liste de surveillance (filtre par société, recherche) ;
    3. la liste de surveillance (lignes détenues + sociétés suivies, src/surveillance.py) et les alertes de cours ;
    4. la fiche de la société et l'agenda du portefeuille.

Rien n'est téléchargé à l'ouverture de la page : le dernier fil est relu sur le disque
(src/actualites.py) et le bouton « Mettre à jour les actualités » va sur Internet. Seule exception :
s'il existe des alertes de cours, leurs cours sont relus (gardés 15 minutes en mémoire).
"""

import datetime as dt
from html import escape

import streamlit as st

from . import actualites, base_titres, langues, surveillance
from . import interface as ui
from .interface import euros, nombre, pct
from .langues import t

GENRES_RDV = {"resultats": "Résultats", "dividende": "Dividende (détachement)"}


def html(morceau):
    st.markdown(morceau, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# État de la liste (préférence du portefeuille, comme l'allocation cible)
# ----------------------------------------------------------------------
def _cle(cible):
    return f"surveillance_{(cible or {}).get('id') or (cible or {}).get('origine') or 'session'}"


def lire_etat(cible, session_compte):
    if cible and cible.get("type") == "perso" and session_compte is not None:
        try:
            return surveillance.normaliser_etat(session_compte.preference(_cle(cible), {}))
        except Exception:
            pass
    return surveillance.normaliser_etat(st.session_state.get(_cle(cible), {}))


def _enregistrer(cible, session_compte, etat):
    st.session_state[_cle(cible)] = etat
    if cible and cible.get("type") == "perso" and session_compte is not None:
        try:
            session_compte.definir_preference(_cle(cible), etat)
        except Exception:
            st.warning(t("La liste n'a pas pu être enregistrée dans votre espace : elle vaut pour cette session."))


# ----------------------------------------------------------------------
# Cours (Yahoo Finance), seulement pour les alertes et la mise à jour
# ----------------------------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def cours_actuels(tickers):
    """{ticker: (dernier cours, cours de la veille)} dans la devise de cotation ; {} sans Internet."""
    if not tickers:
        return {}
    try:
        import yfinance as yf
        donnees = yf.download(list(tickers), period="5d", progress=False, auto_adjust=False, threads=True)
        cloture = donnees["Close"] if "Close" in donnees else donnees
        if hasattr(cloture, "to_frame") and not hasattr(cloture, "columns"):
            cloture = cloture.to_frame(tickers[0])
        sortie = {}
        for ticker in tickers:
            if ticker in cloture.columns:
                serie = cloture[ticker].dropna()
                if len(serie) >= 2:
                    sortie[ticker] = (float(serie.iloc[-1]), float(serie.iloc[-2]))
                elif len(serie) == 1:
                    sortie[ticker] = (float(serie.iloc[-1]), None)
        return sortie
    except Exception:
        return {}


def _telecharger(societes, langue, google):
    """Articles, fiches, rendez-vous et cours de la liste (bouton « Mettre à jour »)."""
    articles, erreurs = actualites.telecharger_articles([(s["ticker"], s["nom"]) for s in societes],
                                                        langue=langue, google=google)
    fiches, rdv = {}, []
    try:
        import yfinance as yf
        for s in societes:
            try:
                objet = yf.Ticker(s["ticker"])
                fiches[s["ticker"]] = actualites.fiche_societe(objet.info)
                rdv.append(actualites.rendez_vous(s["ticker"], objet.calendar))
            except Exception:
                erreurs.append((s["ticker"], "Yahoo Finance"))
    except ImportError:
        pass
    cours = cours_actuels(tuple(s["ticker"] for s in societes))
    donnees = {"articles": articles, "fiches": fiches, "agenda": actualites.agenda(rdv),
               "cours": {k: list(v) for k, v in cours.items()}, "societes": [s["ticker"] for s in societes],
               "langue": langue, "google": google}
    actualites.enregistrer_cache(donnees)
    return actualites.lire_cache() or donnees, erreurs


# ----------------------------------------------------------------------
# Bandeau des alertes (haut de la page, à l'ouverture)
# ----------------------------------------------------------------------
def _texte_alerte(a, noms):
    nom = noms.get(a["ticker"], a["ticker"])
    if a["genre"] in ("au_dessus", "en_dessous"):
        return t("{nom} : cours {cours} ({regle} {seuil})", nom=nom, cours=nombre(a["cours"]),
                 regle=t("au-dessus de") if a["genre"] == "au_dessus" else t("en dessous de"), seuil=nombre(a["seuil"]))
    return t("{nom} : {variation} aujourd'hui (seuil {seuil})", nom=nom, variation=pct(a["variation"] or 0.0),
             seuil=("−" if a["genre"] == "baisse" else "+") + nombre(a["seuil"], 1) + (" %" if not langues.anglais()
                                                                                         else "%"))


def bandeau_alertes(res, cible, session_compte):
    """Rappelle en haut de la page les alertes de cours atteintes (rien si aucune alerte n'est réglée)."""
    etat = lire_etat(cible, session_compte)
    if not etat["alertes"]:
        return
    cours = cours_actuels(tuple(sorted({a["ticker"] for a in etat["alertes"]})))
    atteintes = surveillance.alertes_declenchees(etat, cours)
    if atteintes:
        noms = {s["ticker"]: s["nom"] for s in surveillance.liste(res["positions"], etat)}
        html(ui.note("🔔 " + t("Alertes de cours atteintes :") + " " + " · ".join(_texte_alerte(a, noms)
                                                                              for a in atteintes)
                     + " " + t("(onglet Actualités)"), attention=True))


# ----------------------------------------------------------------------
# L'onglet
# ----------------------------------------------------------------------
def _fil_html(articles, noms, limite=40):
    if not articles:
        return ui.note(t("Aucun article pour cette sélection."))
    morceaux, jour_courant = [], None
    aujourd_hui = dt.date.today()
    for a in articles[:limite]:
        jour = a["date"].date() if a.get("date") else None
        if jour != jour_courant:
            jour_courant = jour
            libelle = (t("Aujourd'hui") if jour == aujourd_hui else t("Hier") if jour == aujourd_hui - dt.timedelta(1)
                       else langues.date(jour) if jour else t("Date inconnue"))
            morceaux.append(f'<div class="act-jour">{escape(libelle)}</div>')
        quand = a["date"].strftime("%H:%M") if a.get("date") and jour == aujourd_hui else (
            langues.date(jour) if jour else "")
        morceaux.append(
            '<div class="act-article">'
            f'<div class="act-ini">{escape(a["ticker"].split(".")[0][:5])}</div>'
            f'<div class="act-corps"><a href="{escape(a["lien"], quote=True)}" target="_blank" rel="noopener noreferrer">'
            f'{escape(a["titre"])}</a>'
            f'<div class="act-meta"><span class="act-tk">{escape(noms.get(a["ticker"], a["ticker"]))}</span>'
            f'{escape(a["source"])} · {escape(quand)}</div></div></div>')
    return '<div class="act-fil">' + "".join(morceaux) + "</div>"


@st.fragment
def afficher(res, cible, session_compte, mode="expert"):
    """L'onglet entier (fragment : un clic ne recalcule pas les autres onglets)."""
    lecture_seule = (cible or {}).get("type") == "consolide"
    etat = lire_etat(cible, session_compte)
    positions = res["positions"]
    toutes = surveillance.liste(positions, etat)
    societes = [s for s in toutes if not s["masquee"]]
    noms = {s["ticker"]: s["nom"] for s in toutes}
    cache = actualites.lire_cache() or {}

    html(ui.titre_section(t("Ce qui se passe sur vos lignes"),
                          t("Articles récents, prochains rendez-vous et fiches des sociétés que vous détenez ou suivez")))
    reglages = st.columns([2, 2, 3], vertical_alignment="bottom")
    langue = reglages[0].segmented_control(
        t("Langue des articles"), ["fr", "en"], default=cache.get("langue") or langues.langue(),
        format_func=lambda c: t({"fr": "Français", "en": "Anglais"}[c]), key="langue_actualites") or "fr"
    google = reglages[1].checkbox(t("Google Actualités"), value=cache.get("google", True), key="google_actualites",
                                  help=t("Flux public et gratuit de Google Actualités, en plus de Yahoo Finance. "
                                         "Google voit alors le nom des sociétés recherchées."))
    with reglages[2]:
        if st.button(t("Mettre à jour les actualités"), icon=":material/refresh:", key="maj_actualites",
                     type="primary" if not cache else "secondary", width="stretch",
                     help=t("Télécharge les articles, fiches et rendez-vous (Internet nécessaire)")):
            with st.spinner(t("Téléchargement des actualités...")):
                cache, erreurs = _telecharger(societes, langue, google)
            if erreurs:
                st.caption(t("Sans réponse : {liste}.", liste=", ".join(sorted({f"{noms.get(tk, tk)} ({s})"
                                                                                for tk, s in erreurs}))))
    if cache.get("telecharge_le"):
        st.caption(t("Dernière mise à jour : {quand}. Sans Internet, ce fil reste consultable.",
                     quand=cache["telecharge_le"].replace("T", " ")))
    else:
        html(ui.note(t("Cliquez sur « Mettre à jour les actualités » pour charger les articles de vos lignes "
                       "(Internet nécessaire). Rien n'est téléchargé tant que vous ne le demandez pas.")))
    manquantes = [s["nom"] for s in societes if cache and s["ticker"] not in cache.get("societes", [])]
    if manquantes:
        st.caption(t("Pas encore dans le fil : {liste} (mettez à jour).", liste=", ".join(manquantes)))

    visibles = {s["ticker"] for s in societes}
    articles = [a for a in cache.get("articles", []) if a["ticker"] in visibles]

    # 1. Cartes
    variations = _variations(res, cache, visibles)
    fortes = actualites.fortes_variations(variations)
    semaine = actualites.fil(articles, depuis_jours=7)
    agenda = [r for r in cache.get("agenda", []) if r["ticker"] in visibles and r["date"] >= dt.date.today()]
    prochains = {g: next((r for r in agenda if r["genre"] == g), None) for g in GENRES_RDV}
    cartes = [ui.carte(t("Articles · 7 derniers jours"), str(len(semaine)),
                       detail=t("sur {n} sociétés surveillées", n=len(societes)))]
    if fortes:
        tk, v = fortes[0]
        cartes.append(ui.carte(t("Forte variation · dernière séance"), f"{noms.get(tk, tk)} {pct(v, decimales=1)}",
                               detail=ui.pastille(t("au-delà de ± 5 %"), "attention")))
    else:
        cartes.append(ui.carte(t("Forte variation · dernière séance"), "—", detail=t("Aucune ligne au-delà de ± 5 %")))
    for genre, libelle in (("resultats", "Prochains résultats"), ("dividende", "Prochain dividende")):
        r = prochains[genre]
        cartes.append(ui.carte(t(libelle), noms.get(r["ticker"], r["ticker"]) if r else "—",
                               detail=t("Le {date} · dans {n} jours", date=langues.date(r["date"]),
                                        n=(r["date"] - dt.date.today()).days) if r else t("Rien de connu")))
    html(ui.grille(cartes))

    gauche, droite = st.columns([1.75, 1], gap="large")

    # 2. Fil d'actualité
    with gauche, st.container(border=True):
        html(ui.titre_section(t("Fil d'actualité"), t("Les plus récents d'abord · le lien ouvre l'article sur le site "
                                                      "de l'éditeur")))
        a, b = st.columns([2, 2])
        choix = a.selectbox(t("Société"), ["*"] + [s["ticker"] for s in societes], key="filtre_actualites",
                            format_func=lambda x: t("Toute la liste") if x == "*" else noms.get(x, x))
        recherche = b.text_input(t("Rechercher"), placeholder=t("Mot du titre…"), key="recherche_actualites")
        choisis = articles if choix == "*" else [x for x in articles if x["ticker"] == choix]
        if recherche:
            choisis = [x for x in choisis if recherche.lower() in x["titre"].lower()]
        for tk, v in fortes:
            if choix in ("*", tk):
                gain = _effet_en_euros(positions, tk, v)
                html(ui.note(t("{nom} {variation} à la dernière séance{effet}. Les articles récents peuvent l'expliquer "
                               "(ci-dessous).", nom=noms.get(tk, tk), variation=pct(v, decimales=1),
                               effet=t(" (votre ligne : {montant})", montant=euros(gain, signe=True)) if gain else ""),
                             attention=True))
        html(_fil_html(choisis, noms))
        st.caption(t("Seuls le titre, la source, la date et le lien sont affichés. Sources : Yahoo Finance et, si la "
                     "case est cochée, Google Actualités."))

    # 3. Liste de surveillance et alertes
    with droite:
        with st.container(border=True):
            _liste_de_surveillance(toutes, etat, cible, session_compte, cache, lecture_seule)
        with st.container(border=True):
            _alertes(etat, toutes, cible, session_compte, lecture_seule)
        if mode == "expert":
            with st.container(border=True):
                _fiche(res, societes, cache)
            with st.container(border=True):
                _agenda(agenda, noms, cache, positions)


def _variations(res, cache, visibles):
    """Variation du jour : lignes détenues d'après les cours de l'analyse (en euros), sociétés suivies d'après
    les cours gardés à la dernière mise à jour."""
    variations = {}
    prix = res.get("prix_hist")
    if prix is not None and len(prix) >= 2:
        for tk in visibles:
            if tk in prix.columns:
                serie = prix[tk].dropna()
                if len(serie) >= 2 and serie.iloc[-2]:
                    variations[tk] = float(serie.iloc[-1] / serie.iloc[-2] - 1)
    variations.update(actualites.variations_du_jour(
        {k: tuple(v) for k, v in cache.get("cours", {}).items() if k in visibles and k not in variations}))
    return variations


def _effet_en_euros(positions, ticker, variation):
    if ticker in positions.index and "valeur" in positions.columns and variation > -1:
        valeur = float(positions.at[ticker, "valeur"])
        return valeur - valeur / (1 + variation)
    return None


def _liste_de_surveillance(toutes, etat, cible, session_compte, cache, lecture_seule):
    html(ui.titre_section(t("Ma liste de surveillance"),
                          t("Vos lignes y sont ajoutées automatiquement ; ajoutez d'autres sociétés à suivre sans les "
                            "acheter")))
    cours = cache.get("cours", {})
    for s in [x for x in toutes if not x["masquee"]]:
        c1, c2, c3 = st.columns([5, 3, 1], vertical_alignment="center")
        badge = ui.pastille(t("Détenue"), "neutre") if s["detenue"] else ui.pastille(t("Suivie"), "attention")
        c1.markdown(f'**{escape(s["nom"])}** {badge}<br><span class="act-petit">{escape(s["ticker"])}</span>',
                    unsafe_allow_html=True)
        if s["ticker"] in cours and cours[s["ticker"]][0]:
            dernier, veille = cours[s["ticker"]]
            variation = dernier / veille - 1 if veille else None
            c2.markdown(f'{nombre(dernier)}<br><span class="act-petit {ui.tendance(variation or 0)}">'
                        f'{pct(variation, decimales=1) if variation is not None else ""}</span>',
                        unsafe_allow_html=True)
        if not lecture_seule and c3.button("✕", key=f"retirer_surveillance_{s['ticker']}", type="tertiary",
                                           help=t("Retirer du fil") if s["detenue"] else t("Retirer de la liste")):
            _enregistrer(cible, session_compte, surveillance.retirer(etat, s["ticker"], s["detenue"]))
            st.rerun(scope="fragment")
    if lecture_seule:
        st.caption(t("Vue « Tous mes comptes » : la liste se modifie depuis chaque compte."))
        return
    recherche = st.text_input(t("Ajouter une société"), placeholder=t("Nom, ticker ou ISIN…"),
                              key="ajout_surveillance")
    if recherche and len(recherche.strip()) >= 2:
        try:
            resultats = base_titres.chercher_localement(recherche.strip())[:5]
        except Exception:
            resultats = []
        for i, r in enumerate(resultats):
            nom = r.get("longname") or r.get("shortname") or r["symbol"]
            if st.button(f"+ {nom} · {r['symbol']}", key=f"ajouter_surveillance_{i}", type="tertiary"):
                _enregistrer(cible, session_compte, surveillance.ajouter(etat, r["symbol"], nom))
                st.rerun(scope="fragment")
        texte = recherche.strip().upper()
        if " " not in texte and st.button(t("+ Ajouter « {ticker} » (ticker Yahoo Finance)", ticker=texte),
                                          key="ajouter_surveillance_ticker", type="tertiary"):
            _enregistrer(cible, session_compte, surveillance.ajouter(etat, texte, texte))
            st.rerun(scope="fragment")
    masquees = [s for s in toutes if s["masquee"]]
    if masquees:
        a, b = st.columns([3, 1.3], vertical_alignment="bottom")
        choix = a.selectbox(t("Masquées (les ETF et fonds le sont au départ)"), [s["ticker"] for s in masquees], key="reafficher_choix",
                            format_func=lambda x: next(s["nom"] for s in masquees if s["ticker"] == x))
        if b.button(t("Réafficher"), key="reafficher_surveillance"):
            _enregistrer(cible, session_compte, surveillance.reafficher(etat, choix))
            st.rerun(scope="fragment")


def _alertes(etat, toutes, cible, session_compte, lecture_seule):
    html(ui.titre_section(t("Alertes de cours"),
                          t("Vérifiées à chaque ouverture du logiciel et signalées en haut de la page ; rien n'est "
                            "envoyé")))
    noms = {s["ticker"]: s["nom"] for s in toutes}
    for i, a in enumerate(etat["alertes"]):
        c1, c2 = st.columns([8, 1], vertical_alignment="center")
        seuil = nombre(a["seuil"], 1) + (" %" if a["genre"] in ("baisse", "hausse") else "")
        c1.markdown(f"{escape(noms.get(a['ticker'], a['ticker']))} · {escape(t(surveillance.GENRES_ALERTE[a['genre']]))}"
                    f" {escape(seuil)}")
        if not lecture_seule and c2.button("✕", key=f"retirer_alerte_{i}", type="tertiary", help=t("Supprimer")):
            _enregistrer(cible, session_compte, surveillance.retirer_alerte(etat, i))
            st.rerun(scope="fragment")
    if lecture_seule or not toutes:
        return
    with st.expander(t("Nouvelle alerte"), icon=":material/notifications:"):
        societe = st.selectbox(t("Société"), [s["ticker"] for s in toutes], format_func=lambda x: noms.get(x, x),
                               key="alerte_societe")
        genre = st.selectbox(t("Condition"), list(surveillance.GENRES_ALERTE), key="alerte_genre",
                             format_func=lambda g: t(surveillance.GENRES_ALERTE[g]))
        seuil = st.number_input(t("Seuil (cours dans la devise de cotation, ou %)"), min_value=0.0, value=5.0,
                                step=1.0, key="alerte_seuil")
        if st.button(t("Ajouter l'alerte"), key="ajouter_alerte", type="primary"):
            try:
                _enregistrer(cible, session_compte, surveillance.ajouter_alerte(etat, societe, genre, seuil))
                st.rerun(scope="fragment")
            except ValueError:
                st.warning(t("Indiquez un seuil supérieur à 0."))


def _fiche(res, societes, cache):
    html(ui.titre_section(t("Fiche société")))
    if not societes:
        return
    noms = {s["ticker"]: s["nom"] for s in societes}
    choix = st.selectbox(t("Société"), list(noms), format_func=lambda x: f"{noms[x]} · {x}", key="fiche_societe")
    fiche = cache.get("fiches", {}).get(choix)
    if not fiche:
        st.caption(t("Fiche non encore téléchargée : cliquez sur « Mettre à jour les actualités »."))
        return
    html(f'<div class="act-nom">{escape(fiche["nom"] or noms[choix])}</div>'
         f'<div class="act-petit">{escape(" · ".join(x for x in (fiche["secteur"], fiche["industrie"], fiche["pays"]) if x))}'
         '</div>')
    if fiche["activite"]:
        resume = fiche["activite"] if len(fiche["activite"]) < 600 else fiche["activite"][:600].rsplit(" ", 1)[0] + "…"
        st.caption(resume)
    chiffres = []
    if fiche["capitalisation"]:
        chiffres.append((t("Capitalisation"), f"{nombre(fiche['capitalisation'] / 1e9, 1)} Md {fiche['devise']}"))
    if fiche["per"]:
        chiffres.append((t("PER"), nombre(fiche["per"], 1)))
    if fiche["rendement"] is not None:
        chiffres.append((t("Rendement du dividende"), pct(fiche["rendement"], signe=False, decimales=1)))
    if fiche["variation_1an"] is not None:
        chiffres.append((t("Variation sur 1 an"), pct(fiche["variation_1an"], decimales=1)))
    p = res["positions"]
    if choix in p.index:
        chiffres.append((t("Poids dans votre portefeuille"), pct(float(p.at[choix, "poids_pct"]) / 100, signe=False,
                                                                  decimales=1)))
        if "pv_latente" in p.columns:
            chiffres.append((t("Votre plus-value latente"), euros(float(p.at[choix, "pv_latente"]), signe=True)))
    html('<div class="act-kv">' + "".join(f'<div><span>{escape(k)}</span><b>{escape(v)}</b></div>'
                                          for k, v in chiffres) + "</div>")
    if fiche["site"]:
        st.markdown(f"[{t('Site de la société')} ↗]({fiche['site']})")
    st.caption(t("Données Yahoo Finance (en anglais pour la description)."))


def _agenda(agenda, noms, cache, positions):
    html(ui.titre_section(t("Agenda du portefeuille"), t("Résultats et dividendes à venir (lignes détenues et suivies)")))
    if not agenda:
        st.caption(t("Aucun rendez-vous connu. Mettez à jour les actualités (Yahoo Finance ne connaît pas toutes "
                     "les dates)."))
        return
    lignes = []
    for r in agenda[:10]:
        detail = ""
        fiche = cache.get("fiches", {}).get(r["ticker"]) or {}
        if (r["genre"] == "dividende" and r["ticker"] in positions.index and fiche.get("devise") == "EUR"
                and fiche.get("dividende_par_action")):
            par_action = fiche["dividende_par_action"]
            quantite = float(positions.at[r["ticker"], "quantite"])
            detail = t(" · ≈ {montant} par an pour vous", montant=euros(par_action * quantite))
        lignes.append(f'<div class="act-rdv"><span class="act-date">{escape(langues.date(r["date"]))}</span>'
                      f'<span>{escape(noms.get(r["ticker"], r["ticker"]))} '
                      f'{ui.pastille(t(GENRES_RDV[r["genre"]]), "positive" if r["genre"] == "dividende" else "neutre")}'
                      f'{escape(detail)}</span></div>')
    html("".join(lignes))

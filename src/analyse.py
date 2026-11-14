"""
analyse.py — Toute l'analyse du portefeuille en UNE fonction.

Cette fonction enchaîne les étapes 1 à 5 (+ les devises de l'étape 8) :
    transactions -> devises -> cours -> conversion en euros
                 -> valorisation -> historique -> indicateurs

Elle est utilisée par le tableau de bord (app.py) et par main.py. Elle ne
contient aucun affichage : elle renvoie seulement des résultats. Avantage :
on peut la tester sans lancer l'interface.
"""

import threading
from pathlib import Path

import pandas as pd

from . import config, indices
from .devises import (convertir_cours, decomposer_change, convertir_prix_historiques, convertir_transactions,
                      detecter_devises, devises_etrangeres, ticker_change)
from .market_data import obtenir_cours, obtenir_historique
from .metrics import (calculer_indicateurs, calculer_indicateurs_avances,
                      matrice_correlation)
from .classement import classer_tous
from .portfolio import Portfolio


CHEMIN_REFERENTIEL = Path(__file__).resolve().parent.parent / "data" / "referentiel.csv"

# Avancement du calcul (barre de progression du tableau de bord) : une fonction (part de 0 à 1, texte)
# propre à chaque visiteur (threading.local : Streamlit sert chaque visiteur dans son propre fil).
_avancement = threading.local()


def suivre_avancement(fonction):
    """Indique la fonction à appeler à chaque étape (None pour arrêter)."""
    _avancement.fonction = fonction


def _etape(part, texte):
    fonction = getattr(_avancement, "fonction", None)
    if fonction is not None:
        try:
            fonction(part, texte)
        except Exception:
            pass                                 # l'affichage de l'avancement ne bloque jamais le calcul


def charger_fiches():
    """Fiche descriptive de chaque titre : le référentiel du projet, complété par la
    base locale de titres (data/base/titres.csv, plusieurs milliers de titres).
    Le référentiel l'emporte quand un titre figure dans les deux."""
    referentiel = charger_referentiel()
    try:
        from . import base_titres
        fiches = base_titres.lire_titres()
    except Exception:
        return _avec_corrections(referentiel)
    if fiches.empty:
        return _avec_corrections(referentiel)
    fiches = fiches.replace("", float("nan"))
    supplement = fiches.loc[~fiches.index.isin(referentiel.index)]
    colonnes = [c for c in referentiel.columns if c in supplement.columns]
    return _avec_corrections(pd.concat([referentiel, supplement[colonnes]]))


def _avec_corrections(fiches):
    """Corrections de l'utilisateur (nom, indice suivi : base_titres.corriger) : elles l'emportent."""
    try:
        from . import base_titres
        corrections = base_titres.lire_corrections()
    except Exception:
        return fiches
    if corrections.empty:
        return fiches
    fiches = fiches.astype(object)                  # textes et nombres mêlés (pandas 3 refuse sinon)
    if "indice_suivi" not in fiches.columns:
        fiches["indice_suivi"] = None
    for ticker, c in corrections.iterrows():
        if ticker not in fiches.index:
            fiches.loc[ticker] = float("nan")
        if c["nom"]:
            fiches.loc[ticker, "nom"] = c["nom"]
        if c["indice_suivi"]:
            fiches.loc[ticker, "indice_suivi"] = c["indice_suivi"]
            fiches.loc[ticker, ["region", "pays"]] = float("nan")       # déduits de l'indice
    return fiches


def charger_referentiel():
    """Région, secteur, pays, classe d'actifs et duration de chaque titre
    (fichier data/referentiel.csv).
    Renvoie un tableau vide si le fichier n'existe pas."""
    if not CHEMIN_REFERENTIEL.exists():
        return pd.DataFrame(columns=["region", "secteur", "pays"])
    return pd.read_csv(CHEMIN_REFERENTIEL).set_index("ticker")


def _date_du_cache(source):
    """Cours hors connexion : la date des derniers cours connus (« cache local du 2026-10-08 »),
    sinon None (cours en direct)."""
    import re
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", source or "")
    return pd.Timestamp(f"{m.group(1)}-{m.group(2)}-{m.group(3)}") if m and "direct" not in source.lower() else None


MOTIF_ISIN = __import__("re").compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")


def nom_du_titre(ticker, nom, fiches=None):
    """Nom à afficher pour un titre : le libellé saisi, sauf s'il n'est qu'un code (ISIN, ticker) ou vide ;
    dans ce cas, le nom de la fiche du titre (référentiel, base locale) ou de la table des ISIN connus."""
    nom = "" if nom is None or str(nom).strip().lower() in ("", "nan", "none") else str(nom).strip()
    code = nom.upper()
    if nom and not MOTIF_ISIN.match(code) and code != str(ticker).upper():
        return nom
    try:
        fiches = charger_fiches() if fiches is None else fiches
        if ticker in fiches.index and "nom" in fiches.columns:
            trouve = fiches.loc[ticker, "nom"]
            trouve = trouve.iloc[0] if isinstance(trouve, pd.Series) else trouve
            if isinstance(trouve, str) and trouve.strip() and not MOTIF_ISIN.match(trouve.strip().upper()):
                return trouve.strip()
    except Exception:
        pass
    try:
        from . import base_titres
        tables = {**base_titres.ISIN_ETF, **base_titres.ISIN_ACTIONS}
        for isin, (tk, libelle) in tables.items():
            if tk == ticker or isin == code:
                return libelle
    except Exception:
        pass
    return nom or str(ticker)


def _noms_lisibles(portefeuille):
    """Remplace, dans les transactions et les positions, les noms qui ne sont qu'un code ISIN ou le ticker."""
    t = portefeuille.transactions
    a_revoir = {tk for tk, n in zip(t["ticker"], t["nom"].astype(str))
                if not n.strip() or n.strip().lower() == "nan" or MOTIF_ISIN.match(n.strip().upper())
                or n.strip().upper() == str(tk).upper()}
    if not a_revoir:
        return
    fiches = charger_fiches()
    noms = {tk: nom_du_titre(tk, "", fiches) for tk in a_revoir}
    t["nom"] = [noms.get(tk, n) if tk in noms else n for tk, n in zip(t["ticker"], t["nom"])]
    if "nom" in portefeuille.positions.columns:
        portefeuille.positions["nom"] = [noms.get(tk, n) for tk, n in
                                         zip(portefeuille.positions.index, portefeuille.positions["nom"])]


def analyse_complete(source_csv,
                     indice=config.INDICE_REFERENCE,
                     taux_sans_risque=config.TAUX_SANS_RISQUE,
                     niveau_var=config.NIVEAU_CONFIANCE_VAR):
    """Lance toute l'analyse et renvoie un dictionnaire de résultats.

    source_csv : chemin du fichier de transactions, ou fichier déjà ouvert
                 (par exemple un fichier envoyé depuis le tableau de bord).
    """
    # Étape 1 : les transactions, telles que saisies (vérification du fichier)
    _etape(0.05, "Lecture des opérations")
    brut = Portfolio(source_csv)
    especes = brut.especes                       # versements, retraits, frais de compte (pas des titres)
    # Titres saisis par leur code ISIN (« FR0011550185 ») : remplacés par leur ticker Yahoo (« ESE.PA »), pour
    # que le nom, la région et l'indice suivi soient reconnus (quel que soit le chemin d'import)
    if brut.transactions["ticker"].astype(str).str.match(MOTIF_ISIN.pattern).any():
        from .import_fichier import tickers_depuis_isin
        convertis = tickers_depuis_isin(brut.transactions)
        if not convertis["ticker"].equals(brut.transactions["ticker"]):
            brut = Portfolio(convertis)
            brut.especes = especes
    titres = brut.tous_les_tickers()
    # L'indice de référence peut être un ETF, un indice ou un composite (src/indices.py) :
    # on télécharge tous ses tickers possibles, puis on construit sa série.
    candidats_indice = [c for c in indices.tickers_a_telecharger(indice) if c not in titres]
    tous = titres + candidats_indice

    # Étape 8 : devise de chaque titre et taux de change nécessaires
    info_devises = detecter_devises(tous)
    etrangeres = devises_etrangeres(info_devises)
    tickers_change = [ticker_change(d) for d in etrangeres]

    _etape(0.2, "Téléchargement des cours (Yahoo Finance)")
    # Étape 3 : historique des cours (titres + indice + taux de change, en un seul
    # téléchargement : le cache hors ligne contient ainsi tout le nécessaire)
    prix_hist_brut, source_hist = obtenir_historique(tous + tickers_change, brut.date_debut())
    # Portefeuille très récent (achats d'hier ou du jour) : aucun cours de clôture depuis le premier
    # achat (Yahoo ne l'a pas encore publié, ou seul un cache plus ancien est disponible). On ajoute le
    # cours du moment comme dernier point de l'historique, au lieu d'arrêter l'analyse.
    cours_du_moment = None
    debut = brut.date_debut()
    recents = prix_hist_brut[prix_hist_brut.index >= debut]
    if recents.reindex(columns=[t for t in titres if t in recents.columns]).dropna(how="all").empty:
        cours_du_moment = obtenir_cours(tous + tickers_change)
        jour = max(pd.Timestamp.today().normalize(), pd.Timestamp(debut).normalize())
        ligne = pd.DataFrame({c: [v] for c, v in cours_du_moment[0].items()}, index=[jour])
        prix_hist_brut = pd.concat([prix_hist_brut, ligne])
        prix_hist_brut = prix_hist_brut[~prix_hist_brut.index.duplicated(keep="last")].sort_index().ffill()
    manquants = [t for t in tickers_change if t not in prix_hist_brut.columns]
    if manquants:
        raise ValueError(f"Taux de change introuvables : {manquants}")

    # regroupements d'actions non ajustés par Yahoo (bond ×1 000 du cours) : historique corrigé
    from .mouvements import appliquer_operations_connues, corriger_sauts_de_cours, valeurs_incoherentes
    prix_hist_brut, cours_corriges = corriger_sauts_de_cours(prix_hist_brut, titres)
    # regroupements connus (ORPEA 1 000 pour 1…) : opérations ramenées dans les nouvelles unités
    transactions_ost, operations_appliquees = appliquer_operations_connues(brut.transactions, prix_hist_brut)
    if operations_appliquees:
        brut = Portfolio(transactions_ost)
    # même ETF sous deux tickers (Paris et Cboe Europe « .XC »…) : une seule ligne, si les cours concordent
    from .import_fichier import regrouper_cotations
    regroupees, remplacements = regrouper_cotations(brut.transactions)
    def _dernier(tk):
        serie = prix_hist_brut[tk].dropna() if tk in prix_hist_brut.columns else pd.Series(dtype=float)
        return float(serie.iloc[-1]) if len(serie) else None
    remplacements = {a: b for a, b in remplacements.items()
                     if _dernier(a) and _dernier(b) and abs(_dernier(a) / _dernier(b) - 1) < 0.05}
    if remplacements:
        brut = Portfolio(brut.transactions.assign(ticker=brut.transactions["ticker"].replace(remplacements)))
        brut.especes = especes
    taux_hist = prix_hist_brut[tickers_change].copy()
    taux_hist.columns = etrangeres
    # On ne garde que les jours où au moins un titre a coté (les marchés des
    # changes cotent aussi certains jours fériés boursiers).
    colonnes_titres = [c for c in tous if c in prix_hist_brut.columns]
    prix_hist = prix_hist_brut[colonnes_titres].dropna(how="all")

    _etape(0.55, "Conversion en euros")
    # Conversion en euros (si nécessaire) des transactions et des cours passés
    if etrangeres:
        portefeuille = Portfolio(convertir_transactions(brut.transactions, info_devises, taux_hist))
        prix_hist = convertir_prix_historiques(prix_hist, info_devises, taux_hist)
    else:
        portefeuille = brut
    portefeuille.especes = especes
    # Noms lisibles : un libellé resté sous la forme d'un code ISIN (« FR0011550185 ») ou du ticker est
    # remplacé par le nom du titre (référentiel, base locale, tables d'ISIN intégrées)
    _noms_lisibles(portefeuille)
    # Série de l'indice de référence (en euros), ajoutée comme une colonne de plus
    serie_indice, tickers_indice = indices.construire(prix_hist, indice)
    prix_hist = prix_hist.drop(columns=[c for c in candidats_indice if c in prix_hist.columns])
    prix_hist[indice] = serie_indice

    # Étape 2 : cours actuels (et taux de change actuels), puis valorisation
    prix, source_cours = obtenir_cours(portefeuille.tickers() + tickers_change) if cours_du_moment is None \
        else ({t: v for t, v in cours_du_moment[0].items() if t in portefeuille.tickers() + tickers_change},
              cours_du_moment[1])
    taux_actuels = {d: prix.pop(t) for d, t in zip(etrangeres, tickers_change) if t in prix}
    if len(taux_actuels) < len(etrangeres):
        raise ValueError("Taux de change actuels introuvables.")
    prix_locaux = dict(prix)                       # cours dans la devise de cotation
    prix = convertir_cours(prix, info_devises, taux_actuels)
    positions = portefeuille.valoriser(prix)
    positions["devise"] = [info_devises.get(t, ("EUR", 1.0))[0] for t in positions.index]
    _etape(0.7, "Classement des titres (pays, secteurs)")
    # Classement de chaque titre (classe d'actifs, région, pays, secteur : src/classement.py) :
    # fiche du référentiel ou de la base locale, ETF selon l'indice suivi, valeurs françaises,
    # puis Yahoo Finance (avec Internet) pour les titres restés non classés
    referentiel = charger_fiches()
    noms = dict(zip(portefeuille.transactions["ticker"], portefeuille.transactions["nom"].astype(str)))
    classement = classer_tous(list(portefeuille.positions.index), noms, referentiel,
                              en_ligne="direct" in str(source_cours).lower())
    for colonne in ["region", "secteur", "pays", "classe", "pea_synthetique", "indice"]:
        positions[colonne] = positions.index.map(classement[colonne].to_dict())
    # Duration (sensibilité aux taux) des fonds obligataires, en années
    positions["duration"] = pd.to_numeric(positions.index.map(referentiel["duration"].to_dict()), errors="coerce") \
        if "duration" in referentiel.columns else float("nan")
    resume = portefeuille.resume_valorise(prix)
    # Titres en devise : la plus-value latente séparée en effet marché et effet change
    effet_change = decomposer_change(positions, portefeuille.transactions, prix_locaux, info_devises, taux_actuels)
    positions["effet_change"] = effet_change["effet_change"].reindex(positions.index).fillna(0.0)
    positions["effet_marche"] = positions["pv_latente"] - positions["effet_change"]
    resume["effet_change"] = float(positions["effet_change"].sum())

    # Étape 3 (suite) : historique du portefeuille, en euros
    histo = portefeuille.historique(prix_hist)

    _etape(0.85, "Calcul des indicateurs de performance et de risque")
    # Étapes 4 et 5 : indicateurs
    indicateurs = calculer_indicateurs(histo)
    avances = calculer_indicateurs_avances(
        histo, indicateurs["rendements"], prix_hist[indice], taux_sans_risque, niveau_var
    )
    correlations = matrice_correlation(prix_hist, portefeuille.tickers())

    return {
        "transactions": portefeuille.transactions,
        "especes": portefeuille.especes,
        "solde_saisi": portefeuille.solde_saisi(),
        "mouvements_especes": portefeuille.mouvements_especes() if portefeuille.a_des_especes() else None,
        "positions": positions,
        "toutes_positions": portefeuille.positions,      # y compris les titres entièrement vendus
        "resume": resume,
        "historique": histo,
        "indicateurs": indicateurs,
        "avances": avances,
        "correlations": correlations,
        "prix_hist": prix_hist,
        "valeur_par_titre": portefeuille.valeur_par_titre,
        "date_ouverture": portefeuille.date_debut(),
        "devises": info_devises,
        "taux_actuels": taux_actuels,
        "source_cours": source_cours,
        "date_cours": _date_du_cache(source_cours),
        "effet_change": effet_change,
        "alertes": portefeuille.alertes,
        "classement": classement,
        "cours_corriges": cours_corriges,
        "jours_de_cotation": int(len(histo)),
        "operations_appliquees": operations_appliquees,
        "valeurs_incoherentes": valeurs_incoherentes(positions),
        "source_historique": source_hist,
    }

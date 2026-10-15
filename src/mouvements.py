"""
mouvements.py — Ajouter de nouvelles opérations à un portefeuille existant.

Au lieu de renvoyer tout l'historique modifié, l'utilisateur envoie seulement
ses nouveaux mouvements (un avis d'opéré PDF, un export Excel des dernières
opérations, ou une saisie à la main). Ce module :

    1. repère les DOUBLONS : opération déjà présente (même date, même titre, même
       type, même quantité, prix à 0,5 % près) — cas d'un relevé qui chevauche
       l'ancien ; ils sont exclus par défaut ;
    2. CONTRÔLE la cohérence : vente de plus de titres que ceux détenus à cette
       date (bloquant), date dans le futur, quantité ou prix nul ;
    3. FUSIONNE l'ancien et le nouveau, trié par date.

Ajouter deux fois le même fichier ne change donc rien (les opérations sont
reconnues comme déjà présentes).
"""

import math
import re

import pandas as pd

COLONNES = ["date", "type", "ticker", "nom", "quantite", "prix", "frais"]
TOLERANCE_PRIX = 0.005
ORDRE_TYPES = {"ACHAT": 0, "DIVIDENDE": 1, "VENTE": 2}       # le même jour : achat avant vente


def lire(contenu):
    """Fichier au format du projet (octets ou DataFrame) -> tableau standard."""
    if isinstance(contenu, pd.DataFrame):
        tableau = contenu.copy()
    else:
        import io
        tableau = pd.read_csv(io.BytesIO(contenu) if isinstance(contenu, bytes) else io.StringIO(contenu))
    for c in COLONNES:
        if c not in tableau.columns:
            tableau[c] = "" if c in ("nom",) else 0.0
    tableau = tableau[COLONNES].copy()
    tableau["date"] = pd.to_datetime(tableau["date"])
    tableau["type"] = tableau["type"].astype(str).str.upper().str.strip()
    tableau["ticker"] = tableau["ticker"].astype(str).str.strip()
    for c in ["quantite", "prix", "frais"]:
        tableau[c] = pd.to_numeric(tableau[c], errors="coerce").fillna(0.0).astype(float)
    tableau["nom"] = tableau["nom"].fillna("").astype(str)
    return tableau


def en_csv(tableau):
    sortie = tableau[COLONNES].copy()
    sortie["date"] = pd.to_datetime(sortie["date"]).dt.strftime("%Y-%m-%d")
    return sortie.to_csv(index=False, float_format="%.6g").encode("utf-8")


def _trier(tableau):
    t = tableau.assign(_ordre=tableau["type"].map(ORDRE_TYPES).fillna(1))
    return t.sort_values(["date", "_ordre"], kind="stable").drop(columns="_ordre").reset_index(drop=True)


def _meme_operation(a, b):
    if a["date"] != b["date"] or a["ticker"] != b["ticker"] or a["type"] != b["type"]:
        return False
    if abs(a["quantite"] - b["quantite"]) > 1e-6:
        return False
    reference = max(abs(a["prix"]), abs(b["prix"]), 1e-9)
    return abs(a["prix"] - b["prix"]) / reference <= TOLERANCE_PRIX


def reperer_doublons(existant, nouvelles):
    """Série booléenne (index des nouvelles) : vrai si l'opération est déjà dans l'existant
    (ou en double dans les nouvelles elles-mêmes)."""
    deja = []
    vues = []
    par_cle = {}
    for _, e in existant.iterrows():
        par_cle.setdefault((e["date"], e["ticker"], e["type"]), []).append(e)
    for i, n in nouvelles.iterrows():
        candidats = par_cle.get((n["date"], n["ticker"], n["type"]), []) + vues
        doublon = any(_meme_operation(n, c) for c in candidats)
        deja.append(doublon)
        if not doublon:
            vues.append(n)
    return pd.Series(deja, index=nouvelles.index, dtype=bool)


def controler(fusion, aujourdhui=None):
    """Contrôles de cohérence sur le portefeuille fusionné.

    Renvoie une liste d'alertes : {"bloquant", "message", "valeurs", "ticker", "date"}.
    Les messages sont en français (clés de traduction)."""
    aujourdhui = pd.Timestamp(aujourdhui or pd.Timestamp.today().normalize())
    alertes = []
    for _, ligne in fusion[fusion["date"] > aujourdhui].iterrows():
        alertes.append({"bloquant": True, "ticker": ligne["ticker"], "date": ligne["date"],
                        "message": "Opération datée dans le futur : {titre}, le {date}.",
                        "valeurs": {"titre": ligne["nom"] or ligne["ticker"],
                                    "date": ligne["date"].strftime("%d/%m/%Y")}})
    for _, ligne in fusion[(fusion["type"] != "DIVIDENDE") & ((fusion["quantite"] <= 0) | (fusion["prix"] <= 0))].iterrows():
        alertes.append({"bloquant": True, "ticker": ligne["ticker"], "date": ligne["date"],
                        "message": "Quantité ou prix nul pour {titre}, le {date}.",
                        "valeurs": {"titre": ligne["nom"] or ligne["ticker"],
                                    "date": ligne["date"].strftime("%d/%m/%Y")}})
    detenu = {}
    for _, ligne in _trier(fusion).iterrows():
        signe = {"ACHAT": 1, "VENTE": -1}.get(ligne["type"], 0)
        detenu[ligne["ticker"]] = detenu.get(ligne["ticker"], 0.0) + signe * ligne["quantite"]
        if detenu[ligne["ticker"]] < -1e-6:
            alertes.append({"bloquant": True, "ticker": ligne["ticker"], "date": ligne["date"],
                            "message": "Vente de {quantite} {titre} le {date}, mais seulement {detenu} détenu(s) "
                                       "à cette date.",
                            "valeurs": {"titre": ligne["nom"] or ligne["ticker"], "quantite": f"{ligne['quantite']:g}",
                                        "date": ligne["date"].strftime("%d/%m/%Y"),
                                        "detenu": f"{detenu[ligne['ticker']] + ligne['quantite']:g}"}})
            detenu[ligne["ticker"]] = 0.0
    return alertes


def preparer(existant, nouvelles):
    """Analyse des nouvelles opérations avant enregistrement.

    Renvoie (nouvelles avec les colonnes « inclure » et « statut », alertes)."""
    existant, nouvelles = lire(existant), lire(nouvelles)
    doublons = reperer_doublons(existant, nouvelles)
    nouvelles = nouvelles.assign(inclure=~doublons,
                                 statut=["déjà dans le portefeuille" if d else "nouvelle" for d in doublons])
    return nouvelles, controler(fusionner(existant, nouvelles))


def fusionner(existant, nouvelles):
    """Ancien + nouvelles opérations retenues (colonne « inclure » si présente), triées par date."""
    existant, retenues = lire(existant), nouvelles
    if "inclure" in retenues.columns:
        retenues = retenues[retenues["inclure"].astype(bool)]
    retenues = lire(retenues[COLONNES])
    return _trier(pd.concat([existant, retenues], ignore_index=True))


def fusionner_operations(existant, nouvelles):
    """Fonction tout-en-un : (fusion, doublons exclus, alertes)."""
    preparees, alertes = preparer(existant, nouvelles)
    return fusionner(existant, preparees), preparees[~preparees["inclure"]], alertes


# ======================================================================
# Modifier ou supprimer des opérations existantes (onglet « Transactions »)
# ======================================================================
CHAMPS_MODIFIABLES = ["date", "quantite", "prix", "frais"]


def appliquer_modifications(source, edite):
    """Applique les modifications faites dans le tableau éditable.

    source : le fichier du portefeuille (octets ou tableau), lignes numérotées dans l'ordre du fichier ;
    edite  : tableau édité, indexé par le numéro de ligne d'origine, avec les colonnes modifiables
             et une colonne booléenne « supprimer ». Les lignes absentes (filtrées) sont inchangées.

    Renvoie (nouveau tableau trié par date, supprimées, corrections) où corrections est une liste
    de dictionnaires {ligne, champ, avant, apres}."""
    source = lire(source)
    nouveau = source.copy()
    a_supprimer = []
    corrections = []
    for ligne, valeurs in edite.iterrows():
        if ligne not in nouveau.index:
            continue
        if bool(valeurs.get("supprimer", False)):
            a_supprimer.append(ligne)
            continue
        for champ in CHAMPS_MODIFIABLES:
            if champ not in valeurs.index:
                continue
            avant, apres = nouveau.at[ligne, champ], valeurs[champ]
            if champ == "date":
                apres = pd.Timestamp(apres)
                change = pd.Timestamp(avant).normalize() != apres.normalize()
            else:
                apres = float(apres) if apres == apres and apres is not None else 0.0
                change = abs(float(avant) - apres) > 1e-9
            if change:
                corrections.append({"ligne": ligne, "champ": champ, "avant": avant, "apres": apres})
                nouveau.at[ligne, champ] = apres
    supprimees = source.loc[a_supprimer]
    nouveau = nouveau.drop(index=a_supprimer)
    return _trier(nouveau), supprimees, corrections


def positions_finales(tableau):
    """Quantité détenue à la fin, par titre."""
    signe = tableau["type"].map({"ACHAT": 1, "VENTE": -1}).fillna(0)
    return (signe * tableau["quantite"]).groupby(tableau["ticker"]).sum()


def titres_disparus(avant, apres):
    """Titres détenus avant la modification et qui ne le sont plus après."""
    q_avant, q_apres = positions_finales(lire(avant)), positions_finales(lire(apres))
    return [t for t in q_avant.index if q_avant[t] > 1e-6 and q_apres.get(t, 0) <= 1e-6]


# ======================================================================
# Division ou regroupement d'actions (avis d'opération sur titres)
# ======================================================================
def appliquer_division(source, ticker, date, facteur):
    """Ramène les opérations d'un titre antérieures à une division (ou à un regroupement) dans
    les unités d'après : quantité × facteur, prix ÷ facteur (les cours de Yahoo Finance sont
    eux-mêmes ajustés de cette façon). Les dividendes (montants totaux) ne changent pas.
    Renvoie (nouveau tableau, nombre d'opérations ajustées)."""
    tableau = lire(source)
    date = pd.Timestamp(date)
    concernees = (tableau["ticker"] == ticker) & (tableau["date"] < date) & tableau["type"].isin(["ACHAT", "VENTE"])
    tableau.loc[concernees, "quantite"] = tableau.loc[concernees, "quantite"] * facteur
    tableau.loc[concernees, "prix"] = tableau.loc[concernees, "prix"] / facteur
    return tableau, int(concernees.sum())


def divisions_non_appliquees(transactions, divisions, prix_hist, tolerance=0.25):
    """Divisions d'actions (connues de Yahoo Finance) dont les opérations du fichier ne tiennent
    pas compte.

    Les cours de Yahoo sont ajustés : avant une division par 10, ils sont divisés par 10. Si le prix
    d'achat d'une opération antérieure est environ 10 fois le cours ajusté de ce jour-là, c'est que
    l'opération est restée dans les unités d'avant la division. Si le prix colle au cours ajusté,
    la division a déjà été appliquée (rien à faire).

    transactions : opérations (prix et cours dans la même devise, par exemple tout en euros) ;
    divisions : {ticker: [(date, facteur), …]} ; prix_hist : cours ajustés (colonnes = tickers).
    Renvoie [{"ticker", "nom", "date", "facteur", "operations"}] (une entrée par division à appliquer)."""
    a_appliquer = []
    for ticker, liste in divisions.items():
        if ticker not in prix_hist.columns:
            continue
        cours = prix_hist[ticker].dropna().sort_index()
        operations = transactions[(transactions["ticker"] == ticker) & transactions["type"].isin(["ACHAT", "VENTE"])
                                  & (transactions["prix"] > 0)]
        if cours.empty or operations.empty:
            continue
        non_ajustees, comptees = [], 0
        for _, op in operations.iterrows():
            # facteur cumulé des divisions postérieures à l'opération (le cours ajusté en tient compte)
            cumule = 1.0
            for date, facteur in liste:
                if date > op["date"]:
                    cumule *= facteur
            position = cours.index.searchsorted(op["date"])
            if cumule == 1.0 or position >= len(cours):
                continue
            comptees += 1
            rapport = op["prix"] / cours.iloc[position]
            # opération restée dans les unités d'avant : rapport prix / cours ajusté ≈ facteur cumulé
            if abs(rapport / cumule - 1) < tolerance and abs(rapport - 1) > tolerance:
                non_ajustees.append(op["date"])
        if non_ajustees and len(non_ajustees) * 2 > comptees:
            premiere = min(non_ajustees)
            for date, facteur in liste:
                if date > premiere:
                    n = int(((operations["date"] < date)).sum())
                    a_appliquer.append({"ticker": ticker, "nom": str(operations["nom"].iloc[0]), "date": date,
                                        "facteur": facteur, "operations": n})
    # Titres sans division connue (hors connexion, ou Yahoo ne la donne pas) : la division se
    # déduit des cours eux-mêmes (ORPEA : 2 000 actions à 0,0145 € alors que le cours ajusté du jour
    # vaut 14,50 € → regroupement de 1 000 en 1 non appliqué)
    deja = {d["ticker"] for d in a_appliquer}
    for ticker in sorted(set(transactions["ticker"]) - deja):
        deduite = division_deduite(transactions, ticker, prix_hist)
        if deduite:
            a_appliquer.append(deduite)
    return a_appliquer


FACTEURS_RONDS = sorted({f for b in (2, 3, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50, 100, 200, 250, 500, 1000, 2000,
                                       5000, 10000, 20000, 100000) for f in (float(b), 1 / b)})


def _facteur_rond(rapport, tolerance):
    """Le facteur de division « rond » (10, 1/1000…) le plus proche du rapport, ou None. Sans la
    date de Yahoo, on reste prudent : seulement un écart d'au moins 5 fois (une division par 2 ou 3
    se confondrait avec un prix mal saisi ou un titre qui a beaucoup bougé)."""
    if not rapport or rapport != rapport or 0.2 < rapport < 5:
        return None
    meilleur = min(FACTEURS_RONDS, key=lambda f: abs(rapport / f - 1))
    # gros regroupement (100 pour 1 et au-delà) : Yahoo ajuste souvent aussi ses cours pour les
    # augmentations de capital de la même période (ORPEA 2024), le rapport n'est alors plus tout à
    # fait rond ; un écart de 100 fois ou plus ne peut de toute façon pas venir d'un prix mal saisi
    if meilleur >= 100 or meilleur <= 0.01:
        tolerance = max(tolerance, 0.4)
    return meilleur if abs(rapport / meilleur - 1) < tolerance else None


def division_deduite(transactions, ticker, prix_hist, tolerance=0.15):
    """Division ou regroupement non appliqué, déduit des cours : toutes les opérations d'un titre
    jusqu'à une date ont un prix égal à un même facteur rond (10, 1/1000…) fois le cours ajusté du
    jour, et les suivantes collent au cours. Renvoie la division à appliquer (date : le lendemain de
    la dernière opération concernée, la date exacte n'étant pas connue) ou None."""
    if ticker not in prix_hist.columns:
        return None
    cours = prix_hist[ticker].dropna().sort_index()
    operations = transactions[(transactions["ticker"] == ticker) & transactions["type"].isin(["ACHAT", "VENTE"])
                              & (transactions["prix"] > 0)].sort_values("date")
    if cours.empty or operations.empty:
        return None
    facteurs = []
    for _, op in operations.iterrows():
        position = cours.index.searchsorted(op["date"])
        if position >= len(cours) or not cours.iloc[position]:
            return None
        rapport = op["prix"] / cours.iloc[position]
        facteurs.append((op["date"], _facteur_rond(rapport, tolerance), abs(rapport - 1) <= tolerance))
    # les premières opérations avec un même facteur, puis seulement des opérations au bon cours
    premier = facteurs[0][1]
    if premier is None:
        return None
    k = 0
    while k < len(facteurs) and facteurs[k][1] == premier:
        k += 1
    if not all(au_cours for _, _, au_cours in facteurs[k:]):
        return None
    derniere = facteurs[k - 1][0]
    return {"ticker": ticker, "nom": str(operations["nom"].iloc[0]),
            "date": pd.Timestamp(derniere) + pd.Timedelta(days=1), "facteur": premier, "operations": k,
            "deduite": True}


# ======================================================================
# Opérations sur titres connues (appliquées d'office, sans attendre Yahoo Finance)
# ======================================================================
# Regroupements d'actions certains, que Yahoo Finance donne mal ou pas du tout. Un titre est reconnu
# à son ticker, à son ISIN (ancien ou nouveau) ou à son nom.
# Source ORPEA : communiqué du 21/03/2024 (regroupement de 1 000 actions anciennes en 1 nouvelle,
# actions regroupées cotées à partir du 22/03/2024, ISIN FR0000184798 → FR001400NLM4).
OPERATIONS_CONNUES = [
    {"isin": ("FR0000184798", "FR001400NLM4"), "tickers": ("ORP.PA", "EMEIS.PA", "ORP", "EMEIS"),
     "nom": r"\b(ORPEA|EMEIS)\b", "date": "2024-03-22", "facteur": 0.001,
     "libelle": "ORPEA (devenu emeis) : regroupement de 1 000 actions anciennes en 1 nouvelle, le 22/03/2024"},
    # Casino : avis du 14/06/2024 (100 anciennes → 1 nouvelle, premier jour de cotation le 14/06/2024)
    {"isin": ("FR0000125585", "FR001400OKR3"), "tickers": ("CO.PA", "CO"),
     "nom": r"\bCASINO\b", "date": "2024-06-14", "facteur": 0.01,
     "libelle": "Casino Guichard-Perrachon : regroupement de 100 actions anciennes en 1 nouvelle, le 14/06/2024"},
    # Atos : communiqué de finalisation (10 000 anciennes → 1 nouvelle, premier jour de cotation le 24/04/2025)
    {"isin": ("FR0000051732", "FR001400X2S4"), "tickers": ("ATO.PA", "ATO"),
     "nom": r"\bATOS\b", "date": "2025-04-24", "facteur": 0.0001,
     "libelle": "Atos : regroupement de 10 000 actions anciennes en 1 nouvelle, le 24/04/2025"},
]
# droits préférentiels, bons de souscription… : d'autres titres, qui portent le même nom
MOTIF_DROITS = re.compile(r"\b(DROITS?|DPS|DS\d*|BSA\w*|WARRANTS?|RIGHTS?)\b")


def _concerne(operation_connue, ticker, nom):
    ticker, nom = str(ticker).upper(), str(nom).upper()
    if ticker in operation_connue["tickers"] or ticker in operation_connue["isin"]:
        return True
    return re.search(operation_connue["nom"], nom) is not None and not MOTIF_DROITS.search(nom)


def appliquer_operations_connues(transactions, prix_hist=None):
    """Applique les regroupements de OPERATIONS_CONNUES aux opérations restées dans les anciennes
    unités (achats et ventes antérieurs à la date, au prix d'avant : 2 000 ORPEA à 0,0145 € →
    2 actions à 14,50 €). Une opération déjà ramenée dans les nouvelles unités (prix proche du cours
    ajusté, ou correction déjà enregistrée par l'utilisateur) n'est pas touchée.

    Le test : le rapport prix payé / cours ajusté du jour est plus proche du facteur (1/1 000) que
    de 1, en échelle logarithmique. Sans cours, on compare au prix des opérations postérieures du
    même titre ; sans rien pour comparer, l'opération est ajustée (le regroupement est certain).
    Renvoie (transactions, [{"ticker", "nom", "date", "facteur", "operations", "libelle"}])."""
    tableau = transactions.copy()
    notes = []
    for oc in OPERATIONS_CONNUES:
        date = pd.Timestamp(oc["date"])
        log_f = math.log(oc["facteur"])
        for ticker in tableau["ticker"].unique():
            lignes = tableau[tableau["ticker"] == ticker]
            if not _concerne(oc, ticker, lignes["nom"].iloc[0] if "nom" in lignes else ""):
                continue
            avant = lignes[(lignes["date"] < date) & lignes["type"].isin(["ACHAT", "VENTE"]) & (lignes["prix"] > 0)]
            if avant.empty:
                continue
            cours = None
            if prix_hist is not None and ticker in getattr(prix_hist, "columns", []):
                cours = prix_hist[ticker].dropna().sort_index()
                cours = cours[cours > 0]
            apres = lignes[(lignes["date"] >= date) & lignes["type"].isin(["ACHAT", "VENTE"]) & (lignes["prix"] > 0)]
            a_ajuster = []
            for i, op in avant.iterrows():
                if cours is not None and len(cours):
                    reference = cours.iloc[min(cours.index.searchsorted(op["date"]), len(cours) - 1)]
                elif len(apres):
                    reference = float(apres["prix"].median())
                else:
                    reference = None
                if reference:
                    log_r = math.log(op["prix"] / reference)
                    if abs(log_r - log_f) >= abs(log_r):
                        continue                      # déjà dans les nouvelles unités
                a_ajuster.append(i)
            if a_ajuster:
                tableau.loc[a_ajuster, "quantite"] = tableau.loc[a_ajuster, "quantite"] * oc["facteur"]
                tableau.loc[a_ajuster, "prix"] = tableau.loc[a_ajuster, "prix"] / oc["facteur"]
                notes.append({"ticker": ticker, "nom": str(lignes["nom"].iloc[0]), "date": date,
                              "facteur": oc["facteur"], "operations": len(a_ajuster), "libelle": oc["libelle"]})
    return tableau, notes


def valeurs_incoherentes(positions, seuil=50.0, minimum=500.0):
    """Lignes qui valent plus de 50 fois leur prix de revient (et au moins 500 €) : presque
    toujours une division ou un regroupement d'actions non appliqué, pas une vraie hausse.
    Renvoie [{"ticker", "nom", "valeur", "investi", "multiple"}]."""
    sortie = []
    for ticker, p in positions.iterrows():
        investi, valeur = float(p.get("montant_investi", 0) or 0), float(p.get("valeur", 0) or 0)
        if investi > 0 and valeur >= minimum and valeur > seuil * investi:
            sortie.append({"ticker": ticker, "nom": str(p.get("nom", ticker)), "valeur": valeur,
                           "investi": investi, "multiple": valeur / investi})
    return sortie


def corriger_sauts_de_cours(prix_hist, colonnes):
    """Regroupement d'actions que Yahoo Finance n'a pas ajusté dans son historique : le cours fait
    un bond d'un facteur rond (×10, ×100, ×1 000…) d'un jour à l'autre et reste à ce niveau. Les
    cours d'avant sont alors ramenés dans les nouvelles unités (multipliés par ce facteur), comme
    Yahoo le fait d'habitude. Seuls les bonds vers le HAUT d'au moins ×10 sont corrigés : une
    hausse de 900 % en un jour n'arrive pas en bourse, alors qu'une chute de 90 % peut être réelle.
    Renvoie (cours corrigés, [{"ticker", "date", "facteur"}])."""
    corriges, notes = prix_hist.copy(), []
    for ticker in colonnes:
        if ticker not in corriges.columns:
            continue
        serie = corriges[ticker].dropna()
        if len(serie) < 3:
            continue
        rapports = (serie / serie.shift(1)).iloc[1:]
        for date, rapport in rapports[rapports >= 9].items():
            facteur = min((f for f in FACTEURS_RONDS if f >= 10), key=lambda f: abs(rapport / f - 1))
            if abs(rapport / facteur - 1) > 0.1:
                continue
            # le nouveau niveau tient (pas un point aberrant isolé)
            apres = serie[serie.index >= date].iloc[:5]
            if (apres < serie.loc[date] / 3).any():
                continue
            avant = corriges.index < date
            corriges.loc[avant, ticker] = corriges.loc[avant, ticker] * facteur
            notes.append({"ticker": ticker, "date": pd.Timestamp(date), "facteur": facteur})
    return corriges, notes

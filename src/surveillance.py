"""
surveillance.py — Liste de surveillance et alertes de cours (revue du 26/11/2026).

La liste = les lignes détenues (ajoutées automatiquement, qu'on peut masquer) + des sociétés « suivies »
qu'on ne possède pas. Elle sert à l'onglet « Actualités » (src/vues_actualites.py).

Les alertes portent sur une société de la liste :
    « au_dessus »  : le cours dépasse un seuil (dans la devise de cotation) ;
    « en_dessous » : le cours passe sous un seuil ;
    « baisse »     : baisse du jour d'au moins x % ;
    « hausse »     : hausse du jour d'au moins x %.
Elles sont vérifiées à l'ouverture du logiciel et signalées en haut de la page : rien n'est envoyé
(ni e-mail ni notification), tout reste sur l'ordinateur.

État enregistré (préférence du portefeuille, chiffrée dans l'espace personnel) :
    {"suivies": [{"ticker", "nom"}], "masquees": [ticker], "affichees": [ticker],
     "alertes": [{"ticker", "genre", "seuil"}]}
Les fonds (ETF, obligations, or, monétaire : peu d'actualités propres) sont masqués au départ ; « affichees »
garde ceux que l'utilisateur a réaffichés.
"""

GENRES_ALERTE = {
    "au_dessus": "Cours au-dessus de",
    "en_dessous": "Cours en dessous de",
    "baisse": "Baisse du jour d'au moins (%)",
    "hausse": "Hausse du jour d'au moins (%)",
}


def etat_vide():
    return {"suivies": [], "masquees": [], "affichees": [], "alertes": []}


def normaliser_etat(etat):
    """État lu dans les préférences (ancien ou incomplet) -> état complet."""
    etat = dict(etat or {})
    sortie = etat_vide()
    sortie["suivies"] = [{"ticker": str(s["ticker"]).upper(), "nom": s.get("nom") or s["ticker"]}
                         for s in etat.get("suivies", []) if s.get("ticker")]
    sortie["masquees"] = sorted({str(t).upper() for t in etat.get("masquees", [])})
    sortie["affichees"] = sorted({str(t).upper() for t in etat.get("affichees", [])})
    sortie["alertes"] = [a for a in etat.get("alertes", []) if a.get("ticker") and a.get("genre") in GENRES_ALERTE]
    return sortie


def liste(positions, etat):
    """Sociétés de la liste : [{"ticker", "nom", "detenue", "masquee"}], lignes détenues d'abord (par valeur),
    puis les sociétés suivies. Les espèces et les lignes soldées ne comptent pas."""
    etat = normaliser_etat(etat)
    sortie, vus = [], set()
    if positions is not None and len(positions):
        p = positions[positions["quantite"] > 1e-9] if "quantite" in positions.columns else positions
        if "valeur" in p.columns:
            p = p.sort_values("valeur", ascending=False)
        for ticker, ligne in p.iterrows():
            if ticker == "ESPECES":
                continue
            fonds = est_un_fonds(ligne)
            sortie.append({"ticker": ticker, "nom": ligne.get("nom") or ticker, "detenue": True, "fonds": fonds,
                           "masquee": ticker in etat["masquees"] or (fonds and ticker not in etat["affichees"])})
            vus.add(ticker)
    for s in etat["suivies"]:
        if s["ticker"] not in vus:
            sortie.append({"ticker": s["ticker"], "nom": s["nom"], "detenue": False, "fonds": False,
                           "masquee": s["ticker"] in etat["masquees"]})
            vus.add(s["ticker"])
    return sortie


def est_un_fonds(ligne):
    """Vrai pour un ETF ou un fonds (indice suivi connu, ou classe autre qu'« Actions »)."""
    indice = str(ligne.get("indice") or "").strip()
    return bool(indice and indice.lower() != "nan") or (ligne.get("classe") or "Actions") != "Actions"


def visibles(positions, etat):
    """Sociétés affichées dans le fil (non masquées)."""
    return [s for s in liste(positions, etat) if not s["masquee"]]


def ajouter(etat, ticker, nom):
    """Ajoute une société suivie (sans doublon) ; la réaffiche si elle était masquée."""
    etat = normaliser_etat(etat)
    ticker = str(ticker).strip().upper()
    if ticker and ticker not in {s["ticker"] for s in etat["suivies"]}:
        etat["suivies"].append({"ticker": ticker, "nom": nom or ticker})
    etat["masquees"] = [t for t in etat["masquees"] if t != ticker]
    return etat


def retirer(etat, ticker, detenue):
    """Retire une société du fil. Une ligne détenue est seulement MASQUÉE (elle reste dans le portefeuille,
    on peut la réafficher) ; une société suivie est retirée de la liste, avec ses alertes."""
    etat = normaliser_etat(etat)
    if detenue:
        etat["masquees"] = sorted(set(etat["masquees"]) | {ticker})
        etat["affichees"] = [t for t in etat["affichees"] if t != ticker]
    else:
        etat["suivies"] = [s for s in etat["suivies"] if s["ticker"] != ticker]
        etat["alertes"] = [a for a in etat["alertes"] if a["ticker"] != ticker]
    return etat


def reafficher(etat, ticker):
    etat = normaliser_etat(etat)
    etat["masquees"] = [t for t in etat["masquees"] if t != ticker]
    etat["affichees"] = sorted(set(etat["affichees"]) | {ticker})
    return etat


def ajouter_alerte(etat, ticker, genre, seuil):
    if genre not in GENRES_ALERTE or seuil is None or float(seuil) <= 0:
        raise ValueError("Alerte incomplète")
    etat = normaliser_etat(etat)
    etat["alertes"].append({"ticker": str(ticker).upper(), "genre": genre, "seuil": float(seuil)})
    return etat


def retirer_alerte(etat, index):
    etat = normaliser_etat(etat)
    if 0 <= index < len(etat["alertes"]):
        etat["alertes"].pop(index)
    return etat


def alertes_declenchees(etat, cours):
    """Alertes atteintes. cours : {ticker: (dernier cours, cours de la veille)} dans la devise de cotation.
    Renvoie [{"ticker", "genre", "seuil", "cours", "variation"}] (une alerte sans cours connu est ignorée)."""
    sortie = []
    for a in normaliser_etat(etat)["alertes"]:
        dernier, veille = cours.get(a["ticker"], (None, None))
        if dernier is None:
            continue
        variation = dernier / veille - 1 if veille else None
        s = a["seuil"]
        atteinte = ((a["genre"] == "au_dessus" and dernier >= s) or (a["genre"] == "en_dessous" and dernier <= s)
                    or (a["genre"] == "baisse" and variation is not None and variation <= -s / 100)
                    or (a["genre"] == "hausse" and variation is not None and variation >= s / 100))
        if atteinte:
            sortie.append(dict(a, cours=dernier, variation=variation))
    return sortie

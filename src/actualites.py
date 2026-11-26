"""
actualites.py — Actualités des sociétés suivies (onglet « Actualités », revue du 26/11/2026).

Sources gratuites, sans clé ni compte (règle 1 du projet) :
    - Yahoo Finance (yfinance) : titres d'articles, fiche de la société, prochains rendez-vous ;
    - Google Actualités (flux RSS public, en français ou en anglais), désactivable.
On ne garde que le TITRE, la SOURCE, la DATE et le LIEN de chaque article : le texte reste sur le site
de l'éditeur (droits d'auteur). Aucun résumé automatique (pas d'IA en ligne).

Le dernier fil téléchargé est gardé dans data/cache_actualites.json (lisible sans Internet).
Toutes les fonctions qui vont sur Internet reçoivent leur « lecteur » en paramètre : les tests
leur passent des réponses fictives.
"""

import datetime as dt
import email.utils
import json
import math
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

CHEMIN_CACHE = Path(__file__).resolve().parent.parent / "data" / "cache_actualites.json"
URL_GOOGLE = "https://news.google.com/rss/search?q={requete}&hl={hl}&gl={gl}&ceid={gl}:{langue}"
ARTICLES_PAR_SOCIETE = 8
SEUIL_FORTE_VARIATION = 0.05           # ± 5 % sur la journée


# ----------------------------------------------------------------------
# Articles
# ----------------------------------------------------------------------
def _date(valeur):
    """Date d'un article (horodatage, texte ISO ou date RSS) -> datetime UTC sans fuseau, ou None."""
    if valeur in (None, ""):
        return None
    try:
        if isinstance(valeur, (int, float)):
            return dt.datetime.fromtimestamp(float(valeur), tz=dt.timezone.utc).replace(tzinfo=None)
        texte = str(valeur)
        if texte[:4].isdigit():
            d = dt.datetime.fromisoformat(texte.replace("Z", "+00:00"))
        else:
            d = email.utils.parsedate_to_datetime(texte)
        return d.astimezone(dt.timezone.utc).replace(tzinfo=None) if d.tzinfo else d
    except (ValueError, TypeError, OverflowError):
        return None


def articles_yahoo(ticker, nouvelles):
    """Articles de Yahoo Finance pour un ticker. nouvelles : la liste renvoyée par yfinance.Ticker(t).news
    (deux formats selon la version de yfinance : ancien {title, publisher, link, providerPublishTime},
    nouveau {content: {title, pubDate, provider, canonicalUrl}})."""
    sortie = []
    for n in nouvelles or []:
        c = n.get("content") if isinstance(n.get("content"), dict) else n
        titre = c.get("title")
        lien = ((c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url")
                or c.get("link"))
        source = (c.get("provider") or {}).get("displayName") or c.get("publisher") or "Yahoo Finance"
        date = _date(c.get("pubDate") or c.get("displayTime") or c.get("providerPublishTime"))
        if titre and lien:
            sortie.append({"ticker": ticker, "titre": str(titre).strip(), "source": source, "lien": lien,
                           "date": date, "origine": "Yahoo Finance"})
    return sortie


def url_google(nom, langue="fr"):
    """Adresse du flux RSS Google Actualités pour un nom de société (guillemets : nom exact)."""
    hl, gl = ("fr", "FR") if langue == "fr" else ("en-US", "US")
    return URL_GOOGLE.format(requete=urllib.parse.quote(f'"{nom}"'), hl=hl, gl=gl, langue=langue)


def articles_google(ticker, texte_rss):
    """Articles d'un flux RSS Google Actualités. Le titre se termine par « - Source » : on le retire."""
    sortie = []
    try:
        racine = ET.fromstring(texte_rss)
    except ET.ParseError:
        return sortie
    for item in racine.iter("item"):
        titre = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        if source and titre.endswith(" - " + source):
            titre = titre[: -len(source) - 3].strip()
        lien = (item.findtext("link") or "").strip()
        if titre and lien:
            sortie.append({"ticker": ticker, "titre": titre, "source": source or "Google Actualités", "lien": lien,
                           "date": _date(item.findtext("pubDate")), "origine": "Google Actualités"})
    return sortie


def nom_de_recherche(nom):
    """Nom court pour chercher une société dans les actualités : « LVMH Moët Hennessy Louis Vuitton SE » ->
    « LVMH Moët Hennessy Louis Vuitton » (formes juridiques et mentions entre parenthèses retirées)."""
    mots = str(nom).split("(")[0].replace(",", " ").split()
    formes = {"SE", "SA", "S.A.", "AG", "NV", "N.V.", "PLC", "INC", "INC.", "CORP", "CORP.", "CORPORATION", "LTD",
              "LTD.", "CO", "CO.", "LIMITED", "HOLDING", "HOLDINGS", "GROUP", "GROUPE", "SCA", "ASA", "AB", "OYJ"}
    while mots and mots[-1].upper() in formes:
        mots.pop()
    return " ".join(mots) or str(nom)


def fil(articles, depuis_jours=None, maintenant=None):
    """Fil unique : doublons retirés (même titre), du plus récent au plus ancien ; depuis_jours : seulement
    les articles des n derniers jours (les articles sans date sont gardés à la fin)."""
    vus, sortie = set(), []
    limite = None
    if depuis_jours:
        limite = (maintenant or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)) - dt.timedelta(days=depuis_jours)
    for a in articles:
        cle = " ".join(a["titre"].lower().split())
        if cle in vus or (limite and a.get("date") and a["date"] < limite):
            continue
        vus.add(cle)
        sortie.append(a)
    return sorted(sortie, key=lambda a: a.get("date") or dt.datetime.min, reverse=True)


def telecharger_articles(societes, langue="fr", google=True, yahoo=True, lire_yahoo=None, lire_texte=None):
    """Articles des sociétés [(ticker, nom)]. lire_yahoo(ticker) -> liste yfinance ; lire_texte(url) -> RSS.
    Une source qui ne répond pas est ignorée (le reste du fil s'affiche). Renvoie (articles, erreurs)."""
    if lire_yahoo is None:
        def lire_yahoo(ticker):
            import yfinance as yf
            return yf.Ticker(ticker).news
    if lire_texte is None:
        from .sources_secours import _lire as lire_texte
    articles, erreurs = [], []
    for ticker, nom in societes:
        if yahoo:
            try:
                articles += articles_yahoo(ticker, lire_yahoo(ticker))[:ARTICLES_PAR_SOCIETE]
            except Exception:
                erreurs.append((ticker, "Yahoo Finance"))
        if google and nom:
            try:
                articles += articles_google(ticker, lire_texte(url_google(nom_de_recherche(nom), langue)))[
                    :ARTICLES_PAR_SOCIETE]
            except Exception:
                erreurs.append((ticker, "Google Actualités"))
    return fil(articles), erreurs


# ----------------------------------------------------------------------
# Fiche de la société et rendez-vous
# ----------------------------------------------------------------------
def _nombre(v):
    try:
        v = float(v)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def fiche_societe(info):
    """Fiche d'une société d'après yfinance.Ticker(t).info (dict) : seulement ce qui est affiché."""
    info = info or {}
    rendement = _nombre(info.get("dividendYield"))
    if rendement is not None and rendement > 1:          # selon la version de yfinance : 2.1 ou 0.021
        rendement /= 100
    return {
        "nom": info.get("longName") or info.get("shortName") or "",
        "activite": info.get("longBusinessSummary") or "",
        "secteur": info.get("sector") or "", "industrie": info.get("industry") or "",
        "pays": info.get("country") or "", "site": info.get("website") or "",
        "capitalisation": _nombre(info.get("marketCap")), "devise": info.get("currency") or "",
        "per": _nombre(info.get("trailingPE")), "rendement": rendement,
        "variation_1an": _nombre(info.get("52WeekChange")),
        "dividende_par_action": _nombre(info.get("dividendRate") or info.get("lastDividendValue")),
    }


def rendez_vous(ticker, calendrier, aujourd_hui=None):
    """Prochains rendez-vous d'après yfinance.Ticker(t).calendar (dict) : [(date, genre)] à venir, genre =
    « resultats » ou « dividende » (date de détachement)."""
    aujourd_hui = aujourd_hui or dt.date.today()
    sortie = []
    calendrier = calendrier or {}
    dates_resultats = calendrier.get("Earnings Date") or []
    if not isinstance(dates_resultats, (list, tuple)):
        dates_resultats = [dates_resultats]
    for genre, valeurs in (("resultats", dates_resultats[:1]), ("dividende", [calendrier.get("Ex-Dividend Date")])):
        for v in valeurs:
            if v is None:
                continue
            try:
                jour = v if isinstance(v, dt.date) and not isinstance(v, dt.datetime) else _date(str(v)).date()
            except AttributeError:
                continue
            if jour >= aujourd_hui:
                sortie.append({"ticker": ticker, "date": jour, "genre": genre})
    return sortie


def agenda(rendez_vous_par_titre):
    """Tous les rendez-vous, du plus proche au plus lointain."""
    tous = [r for liste in rendez_vous_par_titre for r in liste]
    return sorted(tous, key=lambda r: r["date"])


# ----------------------------------------------------------------------
# Variations du jour
# ----------------------------------------------------------------------
def variations_du_jour(cours):
    """cours : {ticker: (dernier cours, cours de la veille)} -> {ticker: variation (fraction)}."""
    sortie = {}
    for ticker, (dernier, veille) in cours.items():
        d, v = _nombre(dernier), _nombre(veille)
        if d is not None and v:
            sortie[ticker] = d / v - 1
    return sortie


def fortes_variations(variations, seuil=SEUIL_FORTE_VARIATION):
    """[(ticker, variation)] au-delà de ± seuil, de la plus forte à la plus faible (en valeur absolue)."""
    return sorted(((t, v) for t, v in variations.items() if abs(v) >= seuil), key=lambda x: -abs(x[1]))


# ----------------------------------------------------------------------
# Cache sur disque (dernier fil, lisible sans Internet)
# ----------------------------------------------------------------------
def _en_json(objet):
    if isinstance(objet, (dt.datetime, dt.date)):
        return objet.isoformat()
    raise TypeError(type(objet))


def enregistrer_cache(donnees, chemin=None):
    """Garde le dernier fil (articles, fiches, agenda) avec l'heure du téléchargement."""
    chemin = Path(chemin or CHEMIN_CACHE)
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        contenu = dict(donnees, telecharge_le=dt.datetime.now().isoformat(timespec="minutes"))
        chemin.write_text(json.dumps(contenu, default=_en_json, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def lire_cache(chemin=None):
    """Dernier fil enregistré (dates remises en datetime / date), ou None."""
    chemin = Path(chemin or CHEMIN_CACHE)
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for a in donnees.get("articles", []):
        a["date"] = _date(a.get("date"))
    for r in donnees.get("agenda", []):
        try:
            r["date"] = dt.date.fromisoformat(str(r["date"])[:10])
        except ValueError:
            r["date"] = None
    donnees["agenda"] = [r for r in donnees.get("agenda", []) if r.get("date")]
    return donnees

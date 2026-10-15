"""
sources_secours.py — Cours de secours quand Yahoo Finance ne répond pas (ou bloque).

Avec beaucoup d'utilisateurs, Yahoo Finance peut limiter les requêtes un moment, et la
bibliothèque yfinance casse parfois après un changement chez Yahoo. Ces sources gratuites, sans
clé ni compte, prennent alors le relais, titre par titre :

    - Banque centrale européenne (BCE) : taux de change de référence quotidiens, API officielle
      (https://data-api.ecb.europa.eu) ; même sens que Yahoo : 1 € = x unités de devise ;
    - Stooq : historiques quotidiens en CSV, pour les actions et ETF américains, allemands,
      britanniques, japonais et de Hong Kong (le symbole Yahoo est traduit : AAPL → aapl.us,
      SAP.DE → sap.de, VOD.L → vod.uk).

Si aucune source ne répond, l'application garde ses cours en mémoire (cache local et base de
titres), comme avant. Rien n'est payant ; aucune donnée personnelle n'est envoyée (seulement les
codes des titres).
"""

import io
import os
import urllib.error
import urllib.request

import pandas as pd

DELAI = 12                       # secondes avant d'abandonner une requête
AGENT = "Mozilla/5.0 (Portfolio Tracker, projet étudiant)"

URL_BCE = ("https://data-api.ecb.europa.eu/service/data/EXR/D.{devise}.EUR.SP00.A"
           "?startPeriod={debut}&format=csvdata")
URL_STOOQ = "https://stooq.com/q/d/l/?s={symbole}&i=d"

# Suffixe Yahoo -> suffixe Stooq (places couvertes par Stooq)
SUFFIXES_STOOQ = {"": ".us", ".DE": ".de", ".F": ".de", ".L": ".uk", ".T": ".jp", ".HK": ".hk"}


def _lire(url, delai=DELAI):
    """Contenu texte d'une adresse (lève une exception en cas d'échec)."""
    requete = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return reponse.read().decode("utf-8", errors="replace")


# ----------------------------------------------------------------------
# Taux de change de la BCE
# ----------------------------------------------------------------------
def devise_du_ticker_change(ticker):
    """'EURUSD=X' -> 'USD' ; autre chose -> None."""
    t = str(ticker).upper()
    if t.startswith("EUR") and t.endswith("=X") and len(t) == 8:
        return t[3:6]
    return None


def taux_bce(devise, debut, lire=_lire):
    """Série quotidienne 1 € = x devise, depuis debut (BCE). lire : fonction de téléchargement
    (remplacée dans les tests)."""
    texte = lire(URL_BCE.format(devise=devise.upper(), debut=pd.Timestamp(debut).strftime("%Y-%m-%d")))
    tableau = pd.read_csv(io.StringIO(texte))
    if not {"TIME_PERIOD", "OBS_VALUE"} <= set(tableau.columns):
        raise ValueError("Réponse de la BCE inattendue")
    serie = pd.Series(pd.to_numeric(tableau["OBS_VALUE"], errors="coerce").values,
                      index=pd.to_datetime(tableau["TIME_PERIOD"]), name=f"EUR{devise.upper()}=X").dropna()
    if serie.empty:
        raise ValueError("Aucun taux de la BCE")
    return serie.sort_index()


# ----------------------------------------------------------------------
# Cours de Stooq
# ----------------------------------------------------------------------
def symbole_stooq(ticker):
    """Ticker Yahoo -> symbole Stooq, ou None si la place n'est pas couverte."""
    t = str(ticker).upper()
    if devise_du_ticker_change(t) or t.startswith("^"):
        return None
    racine, point, suffixe = t.rpartition(".")
    if not point:
        racine, suffixe = t, ""
    else:
        suffixe = "." + suffixe
    if suffixe not in SUFFIXES_STOOQ or not racine:
        return None
    return racine.lower().replace("-", ".") + SUFFIXES_STOOQ[suffixe]


def historique_stooq(ticker, debut, lire=_lire):
    """Clôtures quotidiennes d'un titre depuis debut (Stooq)."""
    symbole = symbole_stooq(ticker)
    if symbole is None:
        raise ValueError(f"{ticker} : place non couverte par Stooq")
    texte = lire(URL_STOOQ.format(symbole=symbole))
    tableau = pd.read_csv(io.StringIO(texte))
    colonnes = {c.lower(): c for c in tableau.columns}
    if "date" not in colonnes or "close" not in colonnes:
        raise ValueError(f"{ticker} : réponse de Stooq inattendue")
    serie = pd.Series(pd.to_numeric(tableau[colonnes["close"]], errors="coerce").values,
                      index=pd.to_datetime(tableau[colonnes["date"]], errors="coerce"), name=ticker).dropna()
    serie = serie[serie.index >= pd.Timestamp(debut) - pd.Timedelta(days=10)]
    if serie.empty:
        raise ValueError(f"{ticker} : aucun cours chez Stooq")
    return serie.sort_index()


# ----------------------------------------------------------------------
# Point d'entrée : tout ce qui peut être trouvé
# ----------------------------------------------------------------------
def historiques(tickers, debut, lire=_lire):
    """Tableau des cours (colonnes = tickers trouvés) depuis debut, et la liste des sources utilisées.
    Un titre introuvable est simplement absent (jamais d'exception)."""
    series, sources = {}, set()
    if os.environ.get("PORTFOLIO_SANS_SECOURS") and lire is _lire:      # tests : jamais d'Internet
        return pd.DataFrame(), []
    injoignables = set()                     # une source injoignable (pas d'Internet) n'est pas réessayée
    for ticker in tickers:
        devise = devise_du_ticker_change(ticker)
        source = "BCE" if devise else ("Stooq" if symbole_stooq(ticker) else None)
        if source is None or source in injoignables:
            continue
        try:
            series[ticker] = taux_bce(devise, debut, lire) if devise else historique_stooq(ticker, debut, lire)
            sources.add(source)
        except (urllib.error.HTTPError, ValueError, KeyError, pd.errors.ParserError):
            continue                          # ce titre seulement
        except Exception:
            injoignables.add(source)          # réseau coupé, délai dépassé… : on n'insiste pas
    if not series:
        return pd.DataFrame(), []
    tableau = pd.DataFrame(series)
    tableau.index = pd.to_datetime(tableau.index).normalize()
    return tableau.sort_index(), sorted(sources)


def derniers_cours(tickers, lire=_lire):
    """{ticker: dernier cours} trouvés par les sources de secours, et les sources utilisées."""
    tableau, sources = historiques(tickers, pd.Timestamp.today() - pd.Timedelta(days=15), lire)
    if tableau.empty:
        return {}, []
    derniers = tableau.ffill().iloc[-1]
    return {t: float(v) for t, v in derniers.items() if pd.notna(v)}, sources

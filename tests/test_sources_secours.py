"""Sources de secours quand Yahoo Finance ne répond pas : BCE (taux de change) et Stooq (cours).
Les réponses des sites sont simulées (aucun accès à Internet pendant les tests)."""
import urllib.error

import pandas as pd
import pytest

from src import market_data, sources_secours

BCE = ("KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\n"
       "EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-10-12,1.0912\n"
       "EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-10-13,1.0950\n")
STOOQ = "Date,Open,High,Low,Close,Volume\n2026-10-12,250,252,249,251.5,1000\n2026-10-13,251,255,250,254.0,1200\n"


def _faux_internet(url):
    if "ecb.europa.eu" in url:
        return BCE
    if "stooq" in url and "aapl.us" in url:
        return STOOQ
    raise urllib.error.HTTPError(url, 404, "absent", None, None)


def test_symboles_stooq():
    assert sources_secours.symbole_stooq("AAPL") == "aapl.us"
    assert sources_secours.symbole_stooq("SAP.DE") == "sap.de"
    assert sources_secours.symbole_stooq("VOD.L") == "vod.uk"
    assert sources_secours.symbole_stooq("BRK-B") == "brk.b.us"
    assert sources_secours.symbole_stooq("MC.PA") is None                 # place non couverte
    assert sources_secours.symbole_stooq("EURUSD=X") is None
    assert sources_secours.devise_du_ticker_change("EURUSD=X") == "USD"


def test_bce_et_stooq():
    taux = sources_secours.taux_bce("USD", "2026-10-01", _faux_internet)
    assert taux.iloc[-1] == pytest.approx(1.095) and taux.name == "EURUSD=X"
    tableau, sources = sources_secours.historiques(["AAPL", "EURUSD=X", "MC.PA", "MSFT"], "2026-10-01",
                                                   _faux_internet)
    assert set(tableau.columns) == {"AAPL", "EURUSD=X"} and sources == ["BCE", "Stooq"]
    derniers, _ = sources_secours.derniers_cours(["AAPL"], _faux_internet)
    assert derniers == {"AAPL": pytest.approx(254.0)}


def test_pas_d_internet_on_n_insiste_pas():
    appels = []

    def coupe(url):
        appels.append(url)
        raise urllib.error.URLError("pas de réseau")
    tableau, sources = sources_secours.historiques(["AAPL", "MSFT", "SAP.DE", "EURUSD=X", "EURGBP=X"], "2026-10-01",
                                                   coupe)
    assert tableau.empty and sources == []
    assert len(appels) == 2                                    # une tentative par source, pas une par titre


def test_yahoo_en_panne_les_secours_prennent_le_relais():
    def yahoo_en_panne(*a, **k):
        raise ConnectionError("Too Many Requests")

    def secours(tickers, lire=None):
        return ({t: v for t, v in {"AAPL": 254.0, "EURUSD=X": 1.095}.items() if t in tickers}, ["BCE", "Stooq"])
    remplacements = [(market_data, "telecharger_derniers_cours", yahoo_en_panne),
                     (market_data, "_avec_nouvel_essai", lambda f, *a, **k: f(*a)),
                     (sources_secours, "derniers_cours", secours),
                     (market_data, "_sauver_cache", lambda prix: None)]
    anciens = [(m, n, getattr(m, n)) for m, n, _ in remplacements]
    try:
        for m, n, f in remplacements:
            setattr(m, n, f)
        prix, source = market_data.obtenir_cours(["AAPL", "EURUSD=X"])
    finally:
        for m, n, f in anciens:
            setattr(m, n, f)
    assert prix == {"AAPL": 254.0, "EURUSD=X": 1.095}
    assert "secours" in source and "direct" in source and "BCE" in source

"""Onglet « Actualités » : articles, liste de surveillance, alertes de cours, événements sur la courbe
(revue du 26/11/2026). Réponses de Yahoo et de Google FICTIVES : aucun accès à Internet."""

import datetime as dt

import pandas as pd

from src import actualites, surveillance
from src import graphiques_interactifs as gi

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Exemple : la société relève ses prévisions - Journal fictif</title><link>https://exemple.invalid/a</link>
<pubDate>Wed, 25 Nov 2026 08:30:00 GMT</pubDate><source url="https://exemple.invalid">Journal fictif</source></item>
<item><title>Exemple : article plus ancien - Autre source</title><link>https://exemple.invalid/b</link>
<pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate><source url="https://exemple.invalid">Autre source</source></item>
</channel></rss>"""

YAHOO_NOUVEAU = [{"id": "1", "content": {"title": "Example headline", "pubDate": "2026-11-26T07:00:00Z",
                                         "provider": {"displayName": "Fictive Wire"},
                                         "canonicalUrl": {"url": "https://exemple.invalid/y"}}}]
YAHOO_ANCIEN = [{"title": "Old format headline", "publisher": "Fictive", "link": "https://exemple.invalid/z",
                 "providerPublishTime": 1795000000}]


def test_articles_des_deux_sources_et_fil_sans_doublon():
    g = actualites.articles_google("MC.PA", RSS)
    assert g[0]["titre"] == "Exemple : la société relève ses prévisions" and g[0]["source"] == "Journal fictif"
    y = actualites.articles_yahoo("MC.PA", YAHOO_NOUVEAU) + actualites.articles_yahoo("MC.PA", YAHOO_ANCIEN)
    assert [a["source"] for a in y] == ["Fictive Wire", "Fictive"]
    tout = actualites.fil(g + y + g)                       # le même article deux fois : gardé une fois
    assert len(tout) == 4 and tout[0]["titre"] == "Example headline"
    recents = actualites.fil(tout, depuis_jours=7, maintenant=dt.datetime(2026, 11, 26, 12))
    assert "Exemple : article plus ancien" not in [a["titre"] for a in recents]


def test_telechargement_tolere_une_source_muette():
    def yahoo_en_panne(ticker):
        raise OSError("pas de réseau")
    articles, erreurs = actualites.telecharger_articles([("MC.PA", "LVMH Moët Hennessy Louis Vuitton SE")],
                                                        lire_yahoo=yahoo_en_panne, lire_texte=lambda url: RSS)
    assert len(articles) == 2 and erreurs == [("MC.PA", "Yahoo Finance")]
    assert actualites.nom_de_recherche("LVMH Moët Hennessy Louis Vuitton SE") == "LVMH Moët Hennessy Louis Vuitton"
    assert "%22Samsung%20Electronics%22" in actualites.url_google("Samsung Electronics")


def test_fiche_rendez_vous_et_cache(tmp_path):
    fiche = actualites.fiche_societe({"longName": "Société fictive", "marketCap": 3e11, "trailingPE": 24.1,
                                      "dividendYield": 2.1, "52WeekChange": -0.084, "currency": "EUR"})
    assert fiche["rendement"] == 0.021 and fiche["per"] == 24.1
    rdv = actualites.rendez_vous("MC.PA", {"Earnings Date": [dt.date(2027, 1, 29)],
                                           "Ex-Dividend Date": dt.date(2026, 12, 1)}, aujourd_hui=dt.date(2026, 11, 26))
    assert [r["genre"] for r in actualites.agenda([rdv])] == ["dividende", "resultats"]
    chemin = tmp_path / "cache.json"
    actualites.enregistrer_cache({"articles": actualites.articles_google("MC.PA", RSS), "agenda": rdv}, chemin)
    relu = actualites.lire_cache(chemin)
    assert isinstance(relu["articles"][0]["date"], dt.datetime) and dt.date(2026, 12, 1) in [r["date"] for r in relu["agenda"]]
    assert actualites.fortes_variations({"A": 0.062, "B": -0.01, "C": -0.08}) == [("C", -0.08), ("A", 0.062)]


def _positions():
    return pd.DataFrame({"nom": ["LVMH", "Samsung Electronics", "Vendue", "ETF Monde"], "quantite": [2, 10, 0, 5],
                         "valeur": [1200.0, 600.0, 0.0, 300.0], "classe": ["Actions"] * 4,
                         "indice": ["", "", "", "MSCI World"]},
                        index=pd.Index(["MC.PA", "005930.KS", "OLD.PA", "CW8.PA"], name="ticker"))


def test_liste_de_surveillance():
    etat = surveillance.ajouter(surveillance.etat_vide(), "asml.as", "ASML Holding")
    liste = surveillance.liste(_positions(), etat)
    assert [s["ticker"] for s in liste] == ["MC.PA", "005930.KS", "CW8.PA", "ASML.AS"]  # détenues, puis suivies
    assert [s["detenue"] for s in liste] == [True, True, True, False]
    assert [s["masquee"] for s in liste] == [False, False, True, False]           # ETF masqué au départ
    assert "CW8.PA" in [s["ticker"] for s in surveillance.visibles(_positions(), surveillance.reafficher(etat, "CW8.PA"))]
    etat = surveillance.retirer(etat, "MC.PA", detenue=True)                       # masquée, pas vendue
    assert [s["ticker"] for s in surveillance.visibles(_positions(), etat)] == ["005930.KS", "ASML.AS"]
    etat = surveillance.reafficher(etat, "MC.PA")
    etat = surveillance.ajouter_alerte(etat, "ASML.AS", "au_dessus", 700)
    etat = surveillance.retirer(etat, "ASML.AS", detenue=False)                   # retirée avec son alerte
    assert etat["suivies"] == [] and etat["alertes"] == [] and etat["masquees"] == []
    assert etat["affichees"] == ["MC.PA"]


def test_alertes_de_cours():
    etat = surveillance.etat_vide()
    etat = surveillance.ajouter_alerte(etat, "005930.KS", "au_dessus", 70000)
    etat = surveillance.ajouter_alerte(etat, "MC.PA", "baisse", 3)
    etat = surveillance.ajouter_alerte(etat, "MC.PA", "en_dessous", 500)
    cours = {"005930.KS": (71400.0, 67200.0), "MC.PA": (590.0, 612.0)}
    atteintes = surveillance.alertes_declenchees(etat, cours)
    assert [(a["ticker"], a["genre"]) for a in atteintes] == [("005930.KS", "au_dessus"), ("MC.PA", "baisse")]
    assert surveillance.alertes_declenchees(etat, {}) == []                       # sans Internet : rien
    try:
        surveillance.ajouter_alerte(etat, "MC.PA", "au_dessus", 0)
        assert False
    except ValueError:
        pass


def test_evenements_sur_la_courbe():
    tr = pd.DataFrame({"date": pd.to_datetime(["2026-01-05", "2026-01-05", "2026-03-02", "2026-04-20"]),
                       "type": ["ACHAT", "ACHAT", "VENTE", "DIVIDENDE"], "ticker": ["MC.PA", "AI.PA", "MC.PA", "AI.PA"],
                       "nom": ["LVMH", "Air Liquide", "LVMH", "Air Liquide"], "quantite": [2, 5, 1, 0],
                       "prix": [600.0, 170.0, 650.0, 16.5], "frais": [2.0, 1.0, 1.5, 0.0]})
    especes = pd.DataFrame({"date": pd.to_datetime(["2026-01-02"]), "type": ["VERSEMENT"], "ticker": ["ESPECES"],
                            "nom": ["Versement"], "quantite": [0], "prix": [3000.0], "frais": [0.0]})
    ev = gi.evenements_portefeuille(tr, especes)
    achats = ev[ev["categorie"] == "achat"]
    assert len(achats) == 1 and achats.iloc[0]["montant"] == 2 * 600 + 2 + 5 * 170 + 1   # même jour : regroupés
    assert ev[ev["categorie"] == "vente"].iloc[0]["montant"] == 650 - 1.5
    assert set(ev["categorie"]) == {"achat", "vente", "dividende", "versement"}
    histo = pd.DataFrame({"valeur": [3000.0, 3100.0, 3050.0], "apports_nets": [3000.0] * 3},
                         index=pd.to_datetime(["2026-01-02", "2026-02-02", "2026-05-01"]))
    fig = gi.fig_valeur_et_apports(histo, ev)
    if type(fig).__module__.startswith("plotly"):                                 # (Plotly installé)
        assert len(fig.data) == 2 + 4                                            # 2 courbes + 4 types d'événements

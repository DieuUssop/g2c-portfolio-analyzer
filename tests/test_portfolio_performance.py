"""Banc d'essai : avis d'opéré réels de courtiers européens, tirés des tests du logiciel libre
Portfolio Performance (licence EPL-1.0, voir tests/donnees/portfolio_performance/README.md).

Chaque fichier .txt est le texte d'un vrai avis (anonymisé par les auteurs de Portfolio
Performance) ; attendus.json donne, pour chacun, les opérations que leur propre lecteur en tire.
On fait lire chaque texte par la lecture universelle de l'application (sans aucun modèle propre
au courtier) et on compare : date, sens et quantité doivent être justes, et quantité × cours doit
retomber sur le montant brut attendu.

Les seuils ci-dessous sont les résultats obtenus au moment où le banc a été ajouté : ils servent
de garde-fou (une modification qui ferait reculer la lecture fait échouer le test).
"""
import json
import os
from collections import Counter

import pandas as pd

from src import import_fichier as imp

DOSSIER = os.path.join(os.path.dirname(__file__), "donnees", "portfolio_performance")


def _texte(courtier, fichier):
    """Le texte du fichier, sans l'en-tête technique ajouté par Portfolio Performance
    (« PDFBox Version… », « Portfolio Performance Version… », « ----- »)."""
    with open(os.path.join(DOSSIER, courtier, fichier), encoding="utf-8", errors="replace") as f:
        lignes = f.read().split("\n")
    i = next((k for k, l in enumerate(lignes[:8]) if l.startswith("-----")), None)
    if i is not None and any(l.startswith("PDFBox") for l in lignes[:i]):
        lignes = lignes[i + 1:]
    return "\n".join(lignes)


def _evaluer(cas):
    """« exact » (tout juste), « lu » (date, sens, quantité justes mais cours dans une autre
    devise), « partiel » (une partie des opérations), « faux » (lu mais faux), « echec » (rien lu :
    le formulaire « Compléter l'opération » prend le relais)."""
    try:
        grille, _ = imp.grille_depuis_textes([_texte(cas["courtier"], cas["fichier"])])
    except Exception:
        return "echec", 0
    lignes = []
    for ligne in grille[1:]:
        d = dict(zip(grille[0], ligne))
        q, c = imp.convertir_nombres(pd.Series([d["Quantité"], d["Cours"]]))
        lignes.append({"date": d["Date"].replace(".", "/").replace("-", "/"), "sens": imp.classer_type(d["Sens"]),
                       "q": abs(q), "c": c})
    bons = prix = 0
    for o in cas["operations"]:
        a, m, j = o["date"].split("-")
        trouvee = next((l for l in lignes if l["date"] == f"{j}/{m}/{a}" and l["sens"] == o["sens"]
                        and abs(l["q"] - abs(o["quantite"])) < 1e-6 * max(1, abs(o["quantite"])) + 1e-9), None)
        if not trouvee:
            continue
        bons += 1
        brut = o["brut"][1] if o["brut"] else None
        if brut is not None and trouvee["c"] == trouvee["c"] and \
                abs(trouvee["q"] * trouvee["c"] - brut) <= max(0.02, 0.005 * brut):
            prix += 1
    n = len(cas["operations"])
    statut = "exact" if bons == n and prix == n else ("lu" if bons == n else ("partiel" if bons else "faux"))
    return statut, bons


_RESULTATS = {}


def _resultats():
    if not _RESULTATS:
        with open(os.path.join(DOSSIER, "attendus.json"), encoding="utf-8") as f:
            for cas in json.load(f):
                _RESULTATS[(cas["courtier"], cas["fichier"])] = (cas,) + _evaluer(cas)
    return _RESULTATS


def test_banc_portfolio_performance_global():
    r = _resultats()
    statuts = Counter(s for _, s, _ in r.values())
    operations = sum(len(c["operations"]) for c, _, _ in r.values())
    lues = sum(b for _, _, b in r.values())
    assert len(r) >= 150
    assert statuts["exact"] >= 106, statuts
    assert statuts["exact"] + statuts["lu"] >= 119, statuts
    # une lecture fausse est pire qu'un échec (le formulaire prend alors le relais)
    assert statuts["faux"] <= 3, [k for k, v in r.items() if v[1] == "faux"]
    assert lues >= 0.85 * operations, (lues, operations)


def test_banc_courtiers_francais():
    """Bourse Direct, BoursoBank, Fortuneo (Arkéa Direct Bank), Keytrade et les avis en français
    de Trade Republic et DEGIRO : aucun n'est lu faux."""
    r = _resultats()
    francais = [k for k in r if k[0] in ("boursedirect", "boursobank", "arkeadirectbank", "keytradebank")
                or (k[0] == "traderepublic" and k[1].startswith(("Achat", "Vente")))
                or (k[0] == "degiro" and "french" in k[1])]
    assert len(francais) >= 35
    faux = [k for k in francais if r[k][1] == "faux"]
    assert not faux, faux
    lus = [k for k in francais if r[k][1] in ("exact", "lu")]
    assert len(lus) >= 0.75 * len(francais), (len(lus), len(francais))
    for k in r:
        if k[0] in ("boursedirect", "boursobank"):
            assert r[k][1] in ("exact", "lu"), k

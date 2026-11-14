"""
allocation.py — Allocation cible personnelle et répartition du prochain versement.

L'utilisateur fixe ses objectifs par grande poche (classe d'actifs et zone), par exemple
« Actions Monde 70 % · Actions émergentes 20 % · Obligations 10 % ». On compare avec la
répartition actuelle et on calcule comment répartir le PROCHAIN VERSEMENT pour se rapprocher
de la cible sans rien vendre (rééquilibrage par les apports : pas de frais de vente, pas
d'impôt sur une plus-value).

Les poches sont celles de la ligne telle qu'elle est détenue (un ETF MSCI World est dans
« Actions Monde »), pas la transparence de l'onglet Expositions : c'est ainsi qu'on raisonne
quand on choisit ce qu'on achète.
"""

import pandas as pd

POCHES = ["Actions Monde", "Actions Amérique du Nord", "Actions Europe", "Actions Asie-Pacifique",
          "Actions émergentes", "Actions autres", "Obligations", "Monétaire", "Or et matières premières", "Autres"]
REGIONS_POCHE = {
    "Monde (ETF)": "Actions Monde", "Monde": "Actions Monde",
    "États-Unis": "Actions Amérique du Nord", "Canada": "Actions Amérique du Nord",
    "Amérique du Nord": "Actions Amérique du Nord",
    "Europe": "Actions Europe", "Zone euro": "Actions Europe", "France": "Actions Europe",
    "Royaume-Uni": "Actions Europe", "Suisse": "Actions Europe",
    "Japon": "Actions Asie-Pacifique", "Asie-Pacifique": "Actions Asie-Pacifique",
    "Émergents": "Actions émergentes",
}
CLASSES_POCHE = {"Obligations": "Obligations", "Monétaire": "Monétaire", "Or": "Or et matières premières",
                 "Matières premières": "Or et matières premières"}


def poche(classe, region):
    """Poche d'allocation d'une ligne."""
    if classe == "Actions":
        return REGIONS_POCHE.get(region, "Actions autres")
    return CLASSES_POCHE.get(classe, "Autres")


def repartition_actuelle(positions):
    """Valeur (euros) et poids (%) de chaque poche présente. DataFrame indexé par poche."""
    p = positions[positions["quantite"] > 1e-9]
    poches = [poche(c, r) for c, r in zip(p["classe"], p["region"])]
    valeurs = p["valeur"].groupby(poches).sum()
    valeurs = valeurs.reindex([x for x in POCHES if x in valeurs.index])
    total = valeurs.sum()
    return pd.DataFrame({"valeur": valeurs, "poids": valeurs / total * 100 if total else 0.0})


def cible_par_defaut(actuelle):
    """Cible proposée au départ : la répartition actuelle arrondie à 5 points, ramenée à 100 %."""
    arrondi = (actuelle["poids"] / 5).round() * 5
    if arrondi.sum() <= 0:
        return actuelle["poids"].round(1)
    ecart = 100 - arrondi.sum()
    arrondi.iloc[int(actuelle["poids"].values.argmax())] += ecart          # le reste sur la plus grosse poche
    return arrondi.clip(lower=0)


def repartir_versement(valeurs, cible_pct, montant):
    """Répartit un versement entre les poches pour se rapprocher de la cible, sans vente.

    valeurs : euros actuels par poche ; cible_pct : objectif en % (somme 100) ; montant : versement.
    Les poches sous leur cible reçoivent l'argent au prorata de leur retard ; si le versement couvre
    tous les retards, le reste est réparti selon la cible. Renvoie une Series (euros par poche)."""
    poches = list(dict.fromkeys(list(cible_pct.index) + list(valeurs.index)))
    v = valeurs.reindex(poches).fillna(0.0).astype(float)
    c = cible_pct.reindex(poches).fillna(0.0).astype(float) / 100
    montant = max(float(montant), 0.0)
    total = v.sum() + montant
    retards = (c * total - v).clip(lower=0)
    if retards.sum() <= 0 or montant == 0:
        return (c * montant).rename("a_investir")
    if retards.sum() >= montant:
        return (retards / retards.sum() * montant).rename("a_investir")
    return (retards + c * (montant - retards.sum())).rename("a_investir")


def tableau(positions, cible_pct, montant):
    """Tableau complet : poids actuel, cible, écart (points), à investir, poids après le versement,
    et ligne conseillée pour investir dans chaque poche (la plus grosse ligne déjà détenue)."""
    actuelle = repartition_actuelle(positions)
    a_investir = repartir_versement(actuelle["valeur"], cible_pct, montant)
    poches = a_investir.index
    t = pd.DataFrame(index=poches)
    t["actuel"] = actuelle["poids"].reindex(poches).fillna(0.0)
    t["cible"] = cible_pct.reindex(poches).fillna(0.0)
    t["ecart"] = t["actuel"] - t["cible"]
    t["a_investir"] = a_investir
    apres = actuelle["valeur"].reindex(poches).fillna(0.0) + a_investir
    t["apres"] = apres / apres.sum() * 100 if apres.sum() else 0.0
    p = positions[positions["quantite"] > 1e-9]
    p = p.assign(_poche=[poche(c, r) for c, r in zip(p["classe"], p["region"])])
    meilleures = p.sort_values("valeur", ascending=False).groupby("_poche")["nom"].first()
    t["ligne"] = meilleures.reindex(poches).fillna("")
    return t


def ecart_total(t):
    """Écart total à la cible (somme des écarts positifs, en points) : 0 = parfaitement aligné."""
    return float(t["ecart"].clip(lower=0).sum())

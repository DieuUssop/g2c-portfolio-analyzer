"""
consolidation.py — La vue « Tous mes comptes » : plusieurs portefeuilles de l'espace personnel
(un PEA, un compte-titres, une assurance-vie…) analysés comme un seul.

Chaque portefeuille enregistré est un compte ; son type (PEA, CTO, Assurance-vie, Autre) est gardé
dans l'espace personnel (comptes.Session.definir_enveloppe).

Règles :
    - les opérations sur titres et les dividendes de tous les comptes sont réunies : un même ETF
      détenu dans deux comptes devient une seule ligne (quantités et PRU combinés) ;
    - les frais de compte (FRAIS) sont gardés : ils diminuent le gain ;
    - les espèces ne s'additionnent PAS opération par opération : un solde saisi (SOLDE) dans un
      compte remettrait à zéro le solde des autres, et un compte sans versements ferait baisser le
      total à chaque achat. Les versements, retraits et soldes saisis sont donc retirés du fichier
      réuni, et le solde total est la somme des soldes calculés compte par compte (especes_totales).
"""

import pandas as pd

from . import mouvements

TYPES_ESPECES_RETIRES = ("VERSEMENT", "RETRAIT", "SOLDE")


def reunir(contenus):
    """contenus : liste de fichiers au format du projet (octets). Renvoie le fichier réuni (octets)."""
    tableaux = [mouvements.lire(c) for c in contenus if c]
    if not tableaux:
        raise ValueError("Aucun portefeuille à réunir.")
    tout = pd.concat(tableaux, ignore_index=True)
    tout = tout[~tout["type"].isin(TYPES_ESPECES_RETIRES)]
    return mouvements.en_csv(mouvements._trier(tout.reset_index(drop=True)))


def especes_totales(resumes):
    """Somme des espèces des comptes. resumes : liste des « resume » de chaque compte (analyse_complete).
    Renvoie {solde, versements, retraits, comptes_sans_solde} ; solde None si aucun compte ne le connaît."""
    connus = [r for r in resumes if r.get("solde_especes") is not None]
    return {
        "solde": sum(r["solde_especes"] for r in connus) if connus else None,
        "versements": sum(r.get("versements", 0.0) for r in connus),
        "retraits": sum(r.get("retraits", 0.0) for r in connus),
        "comptes_sans_solde": len(resumes) - len(connus),
    }


def appliquer_especes(resume, totaux):
    """Remplace, dans le résumé de l'analyse réunie, les espèces par la somme des comptes."""
    resume = dict(resume)
    resume["solde_especes"] = totaux["solde"]
    resume["versements"], resume["retraits"] = totaux["versements"], totaux["retraits"]
    resume["valeur_compte"] = resume["valeur_actuelle"] + (totaux["solde"] or 0.0)
    return resume


def tableau_par_compte(comptes):
    """comptes : liste de (nom, enveloppe, resume). Une ligne par compte, avec la part de chacun."""
    lignes = [{"compte": nom, "enveloppe": enveloppe or "", "valeur": r["valeur_actuelle"],
               "investi": r["montant_investi"], "gain": r["gain_total"],
               "especes": r.get("solde_especes")} for nom, enveloppe, r in comptes]
    tableau = pd.DataFrame(lignes)
    total = tableau["valeur"].sum() if len(tableau) else 0.0
    tableau["part"] = tableau["valeur"] / total * 100 if total else 0.0
    return tableau

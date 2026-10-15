"""
releves_courtiers.py — Exports de courtiers qui ne sont pas « un tableau simple ».

Interactive Brokers : relevé d'activité au format CSV (« Activity Statement »)
    Un seul fichier contient PLUSIEURS tableaux, chacun annoncé par une ligne « Header » :
        Statement,Header,Field Name,Field Value
        Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,…
        Trades,Data,Order,Stocks,EUR,ESEd,"2026-07-13, 07:05:17",7,33.454,…
        Dividends,Header,Currency,Date,Description,Amount
        Withholding Tax,Header,Currency,Date,Description,Amount,Code
        Financial Instrument Information,Header,Asset Category,Symbol,Description,Conid,Security ID,…
    Ce module en tire un tableau simple (une ligne par opération, mêmes colonnes que la lecture des
    PDF : Date, Sens, ISIN, Libellé, Quantité, Cours, Devise, Frais, Montant) :
        - achats et ventes d'actions et d'ETF (« Stocks », « ETFs ») ; l'ISIN vient du tableau
          « Financial Instrument Information » ; à défaut, symbole + place (« ESE SBF » -> ESE.PA) ;
        - dividendes bruts, avec la retenue à la source du même jour et du même titre en frais ;
        - sont IGNORÉS (et comptés) : opérations de change (Forex), options, futures, CFD,
          lignes annulées (code « Ca »), sous-totaux et totaux.
"""

import csv
import re

ENTETE = ["Date", "Sens", "ISIN", "Libellé", "Quantité", "Cours", "Devise", "Frais", "Montant"]
CATEGORIES_TITRES = {"stocks", "etfs", "etf", "funds", "mutual funds", "actions"}
MOTIF_ISIN_PARENTHESES = re.compile(r"^\s*([^(]+?)\s*\(([A-Z]{2}[A-Z0-9]{9}\d)\)")


def est_releve_ibkr(texte):
    """Vrai pour un relevé d'activité CSV d'Interactive Brokers (plusieurs tableaux « Header »)."""
    debut = "\n".join((texte or "").splitlines()[:400])
    return bool(re.search(r"^﻿?Trades,Header,", debut, re.MULTILINE)) or \
        (bool(re.search(r"^﻿?Statement,Header,", debut, re.MULTILINE))
         and bool(re.search(r"Interactive Brokers|Activity Statement", debut, re.IGNORECASE)))


def _nombre(texte):
    """« 1,000 » -> 1000.0 ; « -234.18 » -> -234.18 (IBKR : point décimal, virgule des milliers)."""
    t = str(texte or "").strip().replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _texte_nombre(x):
    return "" if x is None else f"{x:.10g}"


def sections(texte):
    """{nom de section: [dict(colonne -> valeur), …]} (une section peut avoir plusieurs en-têtes)."""
    resultat = {}
    entetes = {}
    for ligne in csv.reader((texte or "").lstrip("﻿").splitlines()):
        if len(ligne) < 2:
            continue
        nom, nature = ligne[0].strip(), ligne[1].strip()
        if nature == "Header":
            entetes[nom] = [c.strip() for c in ligne[2:]]
        elif nature == "Data" and nom in entetes:
            resultat.setdefault(nom, []).append(dict(zip(entetes[nom], [c.strip() for c in ligne[2:]])))
    return resultat


def _instruments(tables):
    """Symbole -> (ISIN, description, place de cotation), d'après « Financial Instrument Information »."""
    infos = {}
    for ligne in tables.get("Financial Instrument Information", []):
        symbole = ligne.get("Symbol", "")
        isin = ligne.get("Security ID", "") or ligne.get("ISIN", "")
        for s in [x.strip() for x in symbole.split(",") if x.strip()]:   # « ESE, ESEd » : plusieurs symboles
            infos[s] = (isin if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", isin or "") else "",
                        ligne.get("Description", ""), ligne.get("Listing Exch", ""))
    return infos


def _identifiant(symbole, instruments):
    from .import_fichier import PLACES, normaliser_symbole_courtier
    isin, description, place = instruments.get(symbole, ("", "", ""))
    if isin:
        return isin, description or symbole
    racine = normaliser_symbole_courtier(symbole)
    if place and place.upper() in PLACES and "." not in racine:
        return racine + PLACES[place.upper()], description or symbole
    return racine, description or symbole


def grille_ibkr(texte):
    """(grille, "ibkr_csv") : tableau simple tiré du relevé d'activité ; grille[0] = ENTETE.
    Les lignes ignorées sont comptées dans IGNOREES (dernier relevé lu)."""
    tables = sections(texte)
    instruments = _instruments(tables)
    lignes = [list(ENTETE)]
    ignorees = {}

    def ignorer(raison):
        ignorees[raison] = ignorees.get(raison, 0) + 1

    for t in tables.get("Trades", []):
        if t.get("DataDiscriminator", "Order") not in ("Order", "Trade", ""):
            continue                                         # sous-totaux, lots fermés
        categorie = t.get("Asset Category", "").strip().lower()
        if categorie not in CATEGORIES_TITRES:
            ignorer("change (Forex)" if categorie == "forex" else (categorie or "inconnu"))
            continue
        codes = {c.strip() for c in re.split(r"[;,]", t.get("Code", "")) if c.strip()}
        if "Ca" in codes:
            ignorer("annulée")
            continue
        quantite, cours = _nombre(t.get("Quantity")), _nombre(t.get("T. Price") or t.get("TradePrice"))
        if not quantite or cours is None:
            continue
        frais = abs(_nombre(t.get("Comm/Fee") or t.get("Comm in EUR") or t.get("IBCommission")) or 0.0)
        date = (t.get("Date/Time") or t.get("TradeDate") or "").split(",")[0].split(";")[0].strip()
        identifiant, libelle = _identifiant(t.get("Symbol", ""), instruments)
        lignes.append([date, "VENTE" if quantite < 0 else "ACHAT", identifiant, libelle,
                       _texte_nombre(abs(quantite)), _texte_nombre(cours), t.get("Currency", ""),
                       _texte_nombre(round(frais, 2)), _texte_nombre(round(abs(quantite) * cours, 2))])

    # Dividendes, avec la retenue à la source du même titre et du même jour
    retenues = {}
    for r in tables.get("Withholding Tax", []):
        m = MOTIF_ISIN_PARENTHESES.match(r.get("Description", ""))
        montant = _nombre(r.get("Amount"))
        if m and montant is not None:
            cle = (r.get("Date", ""), m.group(2))
            retenues[cle] = retenues.get(cle, 0.0) + montant
    # un dividende corrigé par IBKR apparaît en plusieurs lignes (versement, annulation négative,
    # nouveau versement) : on additionne par titre et par jour
    dividendes = {}
    for d in tables.get("Dividends", []):
        m = MOTIF_ISIN_PARENTHESES.match(d.get("Description", ""))
        montant = _nombre(d.get("Amount"))
        if not m or montant is None or d.get("Currency", "").lower().startswith("total"):
            continue
        cle = (d.get("Date", ""), m.group(2))
        if montant < 0:
            ignorer("correction de dividende (déduite)")
        symbole, devise, total = dividendes.get(cle, (m.group(1).strip(), d.get("Currency", ""), 0.0))
        dividendes[cle] = (symbole, devise, total + montant)
    for (date, isin), (symbole, devise, montant) in dividendes.items():
        if montant <= 0.004:
            continue
        retenue = abs(retenues.get((date, isin), 0.0))
        lignes.append([date, "DIVIDENDE", isin, instruments.get(symbole, ("", symbole, ""))[1] or symbole,
                       "", "", devise, _texte_nombre(round(retenue, 2)), _texte_nombre(round(montant, 2))])
    IGNOREES.clear()
    IGNOREES.update(ignorees)
    return lignes, "ibkr_csv"


IGNOREES = {}

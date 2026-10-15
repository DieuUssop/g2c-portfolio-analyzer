"""
composition_etf.py — Ce que contient VRAIMENT un ETF (analyse « en transparence »).

Un ETF MSCI World est enregistré comme un seul titre, coté à Paris en euros.
Mais il contient environ 1 400 actions de 23 pays, dont près de 73 % aux
États-Unis : son risque géographique, sectoriel et de change est celui de ces
actions, pas celui d'un titre français. Ce module donne, pour chaque grand
indice, sa répartition approximative par pays et par secteur, et reconnaît
l'indice suivi par chaque ETF.

SOURCES ET DATES (approximations, à mettre à jour une fois par an) :
    - MSCI World, ACWI, Emerging Markets, Europe : fiches MSCI au 30/09/2026
      (5 premiers pays et secteurs) ; pays suivants : ordres de grandeur
      habituels de l'indice, ramenés au total « autres pays » de la fiche ;
    - S&P 500, Nasdaq-100, Euro Stoxx 50, CAC 40, DAX, Russell 2000, emprunts
      d'État et obligations d'entreprises de la zone euro : ordres de grandeur
      2025-2026 (fiches des émetteurs d'ETF).
Les poids des indices bougent peu d'une année sur l'autre : l'approximation
suffit pour une analyse d'exposition (quelques points d'écart au plus).
"""

import re

import pandas as pd

DATE_SOURCE = "30/09/2026"

# ----------------------------------------------------------------------
# 1. Pays : code ISO-3 (carte du monde), devise, région du référentiel
# ----------------------------------------------------------------------
PAYS = {   # nom -> (ISO-3, devise, région)
    "États-Unis": ("USA", "USD", "États-Unis"), "Canada": ("CAN", "CAD", "Canada"),
    "Japon": ("JPN", "JPY", "Japon"), "Royaume-Uni": ("GBR", "GBP", "Royaume-Uni"),
    "Suisse": ("CHE", "CHF", "Suisse"), "France": ("FRA", "EUR", "Europe"),
    "Allemagne": ("DEU", "EUR", "Europe"), "Pays-Bas": ("NLD", "EUR", "Europe"),
    "Espagne": ("ESP", "EUR", "Europe"), "Italie": ("ITA", "EUR", "Europe"),
    "Belgique": ("BEL", "EUR", "Europe"), "Finlande": ("FIN", "EUR", "Europe"),
    "Irlande": ("IRL", "EUR", "Europe"), "Autriche": ("AUT", "EUR", "Europe"),
    "Portugal": ("PRT", "EUR", "Europe"), "Grèce": ("GRC", "EUR", "Émergents"),
    "Slovaquie": ("SVK", "EUR", "Europe"), "Slovénie": ("SVN", "EUR", "Europe"),
    "Luxembourg": ("LUX", "EUR", "Europe"),
    "Suède": ("SWE", "SEK", "Europe"), "Danemark": ("DNK", "DKK", "Europe"),
    "Norvège": ("NOR", "NOK", "Europe"), "Pologne": ("POL", "PLN", "Émergents"),
    "Hongrie": ("HUN", "HUF", "Émergents"), "Tchéquie": ("CZE", "CZK", "Émergents"),
    "Israël": ("ISR", "ILS", "Asie-Pacifique"),
    "Australie": ("AUS", "AUD", "Asie-Pacifique"), "Nouvelle-Zélande": ("NZL", "NZD", "Asie-Pacifique"),
    "Hong Kong": ("HKG", "HKD", "Asie-Pacifique"), "Singapour": ("SGP", "SGD", "Asie-Pacifique"),
    "Chine": ("CHN", "CNY", "Émergents"), "Taïwan": ("TWN", "TWD", "Émergents"),
    "Corée du Sud": ("KOR", "KRW", "Émergents"), "Inde": ("IND", "INR", "Émergents"),
    "Brésil": ("BRA", "BRL", "Émergents"), "Mexique": ("MEX", "MXN", "Émergents"),
    "Afrique du Sud": ("ZAF", "ZAR", "Émergents"), "Arabie saoudite": ("SAU", "SAR", "Émergents"),
    "Émirats arabes unis": ("ARE", "AED", "Émergents"), "Qatar": ("QAT", "QAR", "Émergents"),
    "Koweït": ("KWT", "KWD", "Émergents"), "Indonésie": ("IDN", "IDR", "Émergents"),
    "Malaisie": ("MYS", "MYR", "Émergents"), "Thaïlande": ("THA", "THB", "Émergents"),
    "Philippines": ("PHL", "PHP", "Émergents"), "Turquie": ("TUR", "TRY", "Émergents"),
    "Chili": ("CHL", "CLP", "Émergents"), "Pérou": ("PER", "PEN", "Émergents"),
    "Colombie": ("COL", "COP", "Émergents"), "Égypte": ("EGY", "EGP", "Émergents"),
}
AUTRES = "Autres pays"

# ----------------------------------------------------------------------
# 2. Répartition des indices par pays (en %, total = 100)
# ----------------------------------------------------------------------
def _completer(principaux, suivants, total_autres):
    """Pays principaux (fiche officielle) + pays suivants ramenés au total « autres »."""
    somme = sum(suivants.values())
    resultat = dict(principaux)
    for pays, poids in suivants.items():
        resultat[pays] = poids * total_autres / somme
    return resultat


# Pays « suivants » des indices développés (ordres de grandeur relatifs)
_SUIVANTS_DEVELOPPES = {
    "Suisse": 2.4, "Allemagne": 2.3, "Australie": 1.6, "Pays-Bas": 1.1, "Suède": 0.8, "Espagne": 0.8,
    "Italie": 0.7, "Danemark": 0.55, "Hong Kong": 0.5, "Singapour": 0.4, "Finlande": 0.25, "Belgique": 0.25,
    "Israël": 0.2, "Norvège": 0.15, "Irlande": 0.15, "Nouvelle-Zélande": 0.05, "Autriche": 0.05,
    "Portugal": 0.04,
}
_SUIVANTS_EMERGENTS = {
    "Afrique du Sud": 3.3, "Arabie saoudite": 2.8, "Mexique": 1.8, "Émirats arabes unis": 1.3,
    "Malaisie": 1.2, "Indonésie": 1.1, "Thaïlande": 1.0, "Pologne": 0.9, "Qatar": 0.7, "Koweït": 0.7,
    "Grèce": 0.5, "Turquie": 0.4, "Chili": 0.4, "Philippines": 0.4, "Pérou": 0.3, "Hongrie": 0.25,
    "Tchéquie": 0.15, "Colombie": 0.1, "Égypte": 0.05,
}
_SUIVANTS_EUROPE = {
    "Suède": 5.5, "Danemark": 3.8, "Espagne": 4.8, "Italie": 4.5, "Finlande": 1.6, "Belgique": 1.6,
    "Norvège": 1.0, "Irlande": 0.8, "Autriche": 0.3, "Portugal": 0.3, "Pologne": 0.2,
}

_MONDE = _completer({"États-Unis": 72.94, "Japon": 5.91, "Royaume-Uni": 3.41, "Canada": 3.29, "France": 2.24},
                    _SUIVANTS_DEVELOPPES, 12.21)
_EMERGENTS = _completer({"Taïwan": 28.94, "Corée du Sud": 21.4, "Chine": 19.8, "Inde": 10.65, "Brésil": 4.09},
                        _SUIVANTS_EMERGENTS, 15.12)
# ACWI ≈ 89,5 % pays développés + 10,5 % émergents (fiche MSCI : États-Unis 64,21 %, Japon 5,2 %,
# Taïwan 3,46 %, Royaume-Uni 3 %, Canada 2,9 %) : on combine les deux répartitions.
_PART_EMERGENTS_ACWI = 0.12
_ACWI = {p: _MONDE.get(p, 0) * (1 - _PART_EMERGENTS_ACWI) + _EMERGENTS.get(p, 0) * _PART_EMERGENTS_ACWI
         for p in set(_MONDE) | set(_EMERGENTS)}
_EUROPE = _completer({"Royaume-Uni": 22.55, "France": 14.79, "Suisse": 14.16, "Allemagne": 13.62,
                      "Pays-Bas": 9.45}, _SUIVANTS_EUROPE, 25.44)
# Pays développés hors États-Unis et Canada (MSCI EAFE, FTSE Developed ex-North America)
_EAFE = {p: v for p, v in _MONDE.items() if p not in ("États-Unis", "Canada")}


def _parmi(repartition, pays):
    """Part d'une répartition limitée à certains pays (ramenée à 100 par pays_de)."""
    return {p: v for p, v in repartition.items() if p in pays}


_ASIE_EMERGENTE = ("Chine", "Taïwan", "Corée du Sud", "Inde", "Indonésie", "Malaisie", "Thaïlande", "Philippines")
_AMERIQUE_LATINE = ("Brésil", "Mexique", "Chili", "Pérou", "Colombie")
_ZONE_EURO = ("France", "Allemagne", "Pays-Bas", "Espagne", "Italie", "Belgique", "Finlande", "Irlande", "Autriche",
              "Portugal", "Luxembourg", "Grèce", "Slovaquie", "Slovénie")
# Ordres de grandeur 2025-2026 (fiches des indices et des émetteurs d'ETF) : à revoir une fois par an
_ASIE_PACIFIQUE_HORS_JAPON = {"Chine": 24, "Taïwan": 20, "Inde": 17, "Australie": 15, "Corée du Sud": 11,
                              "Hong Kong": 4.5, "Singapour": 3.5, "Indonésie": 1.3, "Malaisie": 1.3,
                              "Thaïlande": 1.1, "Philippines": 0.4, "Nouvelle-Zélande": 0.4}
_ASIE_HORS_JAPON = {p: v for p, v in _ASIE_PACIFIQUE_HORS_JAPON.items() if p not in ("Australie", "Nouvelle-Zélande")}
_PACIFIQUE_HORS_JAPON = {"Australie": 63, "Hong Kong": 18, "Singapour": 15, "Nouvelle-Zélande": 2.5}
_PACIFIQUE = {"Japon": 65, "Australie": 22, "Hong Kong": 6.5, "Singapour": 5, "Nouvelle-Zélande": 1}
_EMU = {"France": 31, "Allemagne": 28, "Pays-Bas": 15, "Espagne": 9.5, "Italie": 9, "Finlande": 2.5,
        "Belgique": 2.5, "Irlande": 1.3, "Autriche": 0.5, "Portugal": 0.5}
_EUROPE_HORS_RU = {p: v for p, v in _EUROPE.items() if p != "Royaume-Uni"}
_MONDE_PETITES = {"États-Unis": 60, "Japon": 10.5, "Royaume-Uni": 5, "Canada": 3.5, "Australie": 3,
                  "Suisse": 2.5, "Suède": 2, "Allemagne": 2, "France": 1.5, "Italie": 1.3, "Israël": 1,
                  "Espagne": 1, "Pays-Bas": 1, "Danemark": 0.8, "Norvège": 0.8, "Singapour": 0.6, "Belgique": 0.6,
                  "Hong Kong": 0.5, "Finlande": 0.5, "Autriche": 0.4, "Nouvelle-Zélande": 0.3, "Portugal": 0.2,
                  "Irlande": 0.2}
_EUROPE_PETITES = {"Royaume-Uni": 30, "Suède": 11, "Suisse": 8, "Allemagne": 7, "Italie": 7, "France": 6,
                   "Norvège": 4, "Espagne": 4, "Danemark": 4, "Pays-Bas": 4, "Belgique": 3, "Finlande": 3,
                   "Autriche": 2, "Irlande": 1, "Portugal": 0.7}
# Obligations
_AGREGAT_MONDIAL = {"États-Unis": 40, "Japon": 9, "Chine": 9, "France": 5, "Allemagne": 5, "Royaume-Uni": 4.5,
                    "Italie": 4, "Canada": 3, "Espagne": 2.5, "Australie": 1.5, "Corée du Sud": 1.5,
                    "Pays-Bas": 1.2, "Belgique": 1, "Autriche": 0.6, "Suède": 0.4, "Danemark": 0.4,
                    "Finlande": 0.3, "Irlande": 0.3, "Mexique": 0.4, "Indonésie": 0.4, "Pologne": 0.3}
_ETATS_MONDE = {"États-Unis": 40, "Japon": 12, "Chine": 10, "France": 6, "Italie": 6, "Allemagne": 5,
                "Royaume-Uni": 5, "Espagne": 3.5, "Canada": 2, "Belgique": 1.5, "Australie": 1.5,
                "Pays-Bas": 1.3, "Autriche": 0.8, "Corée du Sud": 1.5, "Finlande": 0.4, "Irlande": 0.4,
                "Danemark": 0.3, "Suède": 0.3, "Singapour": 0.4, "Mexique": 0.4, "Pologne": 0.4}
_EURO_INFLATION = {"France": 40, "Italie": 25, "Allemagne": 15, "Espagne": 15, "Belgique": 2, "Autriche": 1,
                   "Pays-Bas": 1, "Finlande": 1}
_EMERGENTS_LOCAL = {"Chine": 10, "Indonésie": 10, "Mexique": 9, "Brésil": 9, "Malaisie": 9, "Afrique du Sud": 8,
                    "Thaïlande": 8, "Pologne": 7, "Colombie": 6, "Tchéquie": 5, "Pérou": 4, "Chili": 3,
                    "Hongrie": 3, "Turquie": 2, "Philippines": 2, "Inde": 5}

PAYS_PAR_INDICE = {
    "MSCI World": _MONDE,
    "MSCI ACWI": _ACWI,
    "MSCI Emerging Markets": _EMERGENTS,
    "MSCI Europe": _EUROPE,
    "MSCI EAFE": _EAFE,
    "S&P 500": {"États-Unis": 100},
    "Russell 2000": {"États-Unis": 100},
    "US Total Market": {"États-Unis": 100},
    "Nasdaq-100": {"États-Unis": 96.0, "Pays-Bas": 1.4, "Royaume-Uni": 1.3, "Canada": 0.8, "Chine": 0.5},
    "Euro Stoxx 50": {"France": 35, "Allemagne": 31, "Pays-Bas": 15, "Espagne": 9, "Italie": 7, "Belgique": 2,
                      "Finlande": 1},
    "CAC 40": {"France": 100},
    "DAX": {"Allemagne": 100},
    # Actions : autres indices (ordres de grandeur 2025-2026)
    "MSCI World Small Cap": _MONDE_PETITES,
    "MSCI USA": {"États-Unis": 100},
    "S&P 500 Equal Weight": {"États-Unis": 100},
    "MSCI EMU": _EMU,
    "MSCI Europe ex UK": _EUROPE_HORS_RU,
    "MSCI Europe Small Cap": _EUROPE_PETITES,
    "MSCI Japan": {"Japon": 100},
    "MSCI Pacific": _PACIFIQUE,
    "MSCI Pacific ex Japan": _PACIFIQUE_HORS_JAPON,
    "MSCI AC Asia Pacific ex Japan": _ASIE_PACIFIQUE_HORS_JAPON,
    "MSCI AC Asia ex Japan": _ASIE_HORS_JAPON,
    "MSCI EM Asia": _parmi(_EMERGENTS, _ASIE_EMERGENTE),
    "MSCI EM Latin America": _parmi(_EMERGENTS, _AMERIQUE_LATINE),
    "MSCI EM ex China": {p: v for p, v in _EMERGENTS.items() if p != "Chine"},
    "MSCI China": {"Chine": 100},
    "MSCI India": {"Inde": 100},
    "MSCI Korea": {"Corée du Sud": 100},
    "MSCI Taiwan": {"Taïwan": 100},
    "MSCI Brazil": {"Brésil": 100},
    "FTSE 100": {"Royaume-Uni": 100},
    "MSCI Switzerland": {"Suisse": 100},
    "MSCI Canada": {"Canada": 100},
    "MSCI Australia": {"Australie": 100},
    "MSCI Italy": {"Italie": 100},
    "MSCI Spain": {"Espagne": 100},
    "MSCI Netherlands": {"Pays-Bas": 100},
    "France petites et moyennes valeurs": {"France": 100},
    "MDAX": {"Allemagne": 100},
    # Obligations
    "Emprunts d'État zone euro": {"France": 23.5, "Italie": 21.5, "Allemagne": 18, "Espagne": 14,
                                  "Belgique": 4.5, "Pays-Bas": 4, "Autriche": 3, "Portugal": 2, "Finlande": 1.5,
                                  "Irlande": 1.5, "Slovaquie": 0.6, "Slovénie": 0.4, "Luxembourg": 0.2},
    "Obligations d'entreprises euro": {"France": 27, "Allemagne": 14, "États-Unis": 13, "Pays-Bas": 7,
                                       "Italie": 6, "Espagne": 6, "Royaume-Uni": 6, "Suède": 2, "Belgique": 2,
                                       "Irlande": 2, "Japon": 2, "Suisse": 2},
    "Haut rendement euro": {"France": 20, "Italie": 15, "Allemagne": 12, "États-Unis": 9, "Espagne": 7,
                            "Royaume-Uni": 7, "Pays-Bas": 6, "Suède": 3, "Luxembourg": 3},
    "Emprunts d'État américains": {"États-Unis": 100},
    "Emprunts d'État japonais": {"Japon": 100},
    "Emprunts d'État britanniques": {"Royaume-Uni": 100},
    "MSCI Singapore": {"Singapour": 100},
    "MSCI North America": {"États-Unis": 95, "Canada": 5},
    "Obligations indexées sur l'inflation euro": _EURO_INFLATION,
    "Obligations agrégées euro": {"France": 22, "Italie": 16, "Allemagne": 18, "Espagne": 10, "Pays-Bas": 5,
                                  "Belgique": 4, "Autriche": 2.5, "États-Unis": 6, "Royaume-Uni": 3, "Finlande": 1.5,
                                  "Irlande": 1.5, "Portugal": 1.5, "Suède": 1, "Japon": 1, "Suisse": 1},
    "Obligations agrégées mondiales": _AGREGAT_MONDIAL,
    "Emprunts d'État mondiaux": _ETATS_MONDE,
    "Obligations émergentes en devises locales": _EMERGENTS_LOCAL,
    "Obligations d'entreprises mondiales": {"États-Unis": 60, "France": 6, "Royaume-Uni": 6, "Allemagne": 5,
                                            "Japon": 4, "Canada": 4, "Pays-Bas": 3, "Suisse": 2, "Espagne": 2,
                                            "Italie": 2, "Australie": 2, "Suède": 1, "Irlande": 1, "Belgique": 1,
                                            "Danemark": 1},
    "Obligations d'entreprises américaines": {"États-Unis": 85, "Royaume-Uni": 4, "Canada": 3, "Japon": 3,
                                              "France": 2, "Allemagne": 2},
    "Obligations émergentes en dollars": {"Mexique": 7, "Arabie saoudite": 7, "Indonésie": 6, "Turquie": 5,
                                          "Chili": 4, "Brésil": 4, "Émirats arabes unis": 4, "Qatar": 4,
                                          "Colombie": 4, "Philippines": 4, "Afrique du Sud": 3, "Pérou": 3,
                                          "Égypte": 3, "Pologne": 2, "Chine": 3, "Inde": 2},
}

# ----------------------------------------------------------------------
# 3. Répartition des indices actions par secteur (en %)
# ----------------------------------------------------------------------
SECTEURS_PAR_INDICE = {
    "MSCI World": {"Technologie": 31.78, "Finance": 15.74, "Industrie": 10.8, "Santé": 9.2,
                   "Consommation discrétionnaire": 8.36, "Communication": 8.31, "Consommation de base": 4.77,
                   "Énergie": 4.03, "Matériaux": 3.21, "Services publics": 2.3, "Immobilier": 1.52},
    "MSCI ACWI": {"Technologie": 33.21, "Finance": 16.17, "Industrie": 10.27, "Santé": 8.42,
                  "Consommation discrétionnaire": 8.24, "Communication": 8.01, "Consommation de base": 4.51,
                  "Énergie": 3.96, "Matériaux": 3.51, "Services publics": 2.25, "Immobilier": 1.45},
    "MSCI Emerging Markets": {"Technologie": 43.78, "Finance": 19.35, "Consommation discrétionnaire": 7.39,
                              "Industrie": 6.34, "Communication": 5.86, "Matériaux": 5.77, "Énergie": 3.4,
                              "Santé": 2.72, "Consommation de base": 2.58, "Services publics": 1.86,
                              "Immobilier": 0.95},
    "MSCI Europe": {"Finance": 25.5, "Industrie": 18.61, "Santé": 12.72, "Technologie": 9.75,
                    "Consommation de base": 8.25, "Consommation discrétionnaire": 6.0, "Matériaux": 5.43,
                    "Énergie": 5.36, "Services publics": 4.78, "Communication": 3.08, "Immobilier": 0.53},
    "MSCI EAFE": {"Finance": 23, "Industrie": 18, "Santé": 10.5, "Consommation discrétionnaire": 10,
                  "Technologie": 9, "Consommation de base": 7.5, "Matériaux": 6, "Communication": 5,
                  "Énergie": 4, "Services publics": 3.5, "Immobilier": 2},
    "S&P 500": {"Technologie": 34, "Finance": 13, "Consommation discrétionnaire": 10.5, "Communication": 10,
                "Santé": 9, "Industrie": 8.5, "Consommation de base": 5, "Énergie": 3, "Services publics": 2.4,
                "Immobilier": 2, "Matériaux": 1.8},
    "US Total Market": {"Technologie": 33, "Finance": 13.5, "Consommation discrétionnaire": 10.5,
                        "Communication": 9.5, "Santé": 9.5, "Industrie": 9.5, "Consommation de base": 4.5,
                        "Énergie": 3, "Immobilier": 2.5, "Services publics": 2.5, "Matériaux": 2},
    "Nasdaq-100": {"Technologie": 51, "Communication": 16, "Consommation discrétionnaire": 13, "Santé": 5,
                   "Consommation de base": 5, "Industrie": 4.5, "Services publics": 1.5, "Matériaux": 1.5,
                   "Finance": 1, "Énergie": 0.5, "Immobilier": 1},
    "Russell 2000": {"Finance": 18, "Industrie": 17, "Santé": 16, "Technologie": 14,
                     "Consommation discrétionnaire": 10, "Immobilier": 6, "Énergie": 5, "Matériaux": 4.5,
                     "Services publics": 3, "Consommation de base": 3, "Communication": 2.5},
    "Euro Stoxx 50": {"Finance": 20, "Technologie": 16, "Industrie": 16, "Consommation discrétionnaire": 15,
                      "Consommation de base": 7, "Santé": 6, "Services publics": 6, "Énergie": 5,
                      "Communication": 5, "Matériaux": 4},
    "CAC 40": {"Consommation discrétionnaire": 22, "Industrie": 20, "Santé": 10, "Consommation de base": 10,
               "Finance": 10, "Matériaux": 8, "Énergie": 7, "Technologie": 6, "Communication": 3,
               "Services publics": 3, "Immobilier": 1},
    "DAX": {"Industrie": 25, "Finance": 20, "Technologie": 15, "Consommation discrétionnaire": 12, "Santé": 7,
            "Communication": 7, "Matériaux": 6, "Services publics": 5, "Immobilier": 1, "Consommation de base": 1,
            "Énergie": 1},
    # Autres indices actions (ordres de grandeur 2025-2026)
    "MSCI World Small Cap": {"Industrie": 20, "Finance": 15, "Technologie": 11, "Consommation discrétionnaire": 11,
                             "Santé": 9, "Immobilier": 8, "Matériaux": 7, "Consommation de base": 5, "Énergie": 4,
                             "Services publics": 3, "Communication": 3},
    "S&P 500 Equal Weight": {"Industrie": 15, "Finance": 14, "Technologie": 13, "Santé": 12,
                             "Consommation discrétionnaire": 10, "Consommation de base": 7, "Immobilier": 6,
                             "Services publics": 6, "Matériaux": 5, "Énergie": 4.5, "Communication": 4},
    "MSCI EMU": {"Finance": 22, "Industrie": 19, "Technologie": 14, "Consommation discrétionnaire": 11, "Santé": 7,
                 "Consommation de base": 7, "Services publics": 6, "Matériaux": 5.5, "Énergie": 4,
                 "Communication": 4, "Immobilier": 1},
    "MSCI Europe Small Cap": {"Industrie": 25, "Finance": 15, "Consommation discrétionnaire": 10, "Immobilier": 9,
                              "Technologie": 9, "Matériaux": 7, "Santé": 7, "Communication": 5,
                              "Consommation de base": 5, "Énergie": 4, "Services publics": 4},
    "MSCI Japan": {"Industrie": 23, "Consommation discrétionnaire": 17, "Finance": 15, "Technologie": 13,
                   "Communication": 8, "Santé": 6, "Consommation de base": 5, "Matériaux": 5, "Immobilier": 2,
                   "Services publics": 1, "Énergie": 1},
    "MSCI Pacific ex Japan": {"Finance": 40, "Matériaux": 14, "Industrie": 9, "Immobilier": 8, "Santé": 7,
                              "Consommation discrétionnaire": 7, "Services publics": 3, "Consommation de base": 3,
                              "Énergie": 3, "Communication": 3, "Technologie": 2},
    "MSCI AC Asia Pacific ex Japan": {"Technologie": 28, "Finance": 23, "Consommation discrétionnaire": 10,
                                      "Communication": 8, "Industrie": 7, "Matériaux": 6, "Santé": 4,
                                      "Consommation de base": 4, "Énergie": 3.5, "Immobilier": 3,
                                      "Services publics": 2.5},
    "MSCI AC Asia ex Japan": {"Technologie": 32, "Finance": 20, "Consommation discrétionnaire": 12,
                              "Communication": 9, "Industrie": 7, "Matériaux": 5, "Santé": 4,
                              "Consommation de base": 4, "Énergie": 3, "Immobilier": 2, "Services publics": 2},
    "MSCI China": {"Consommation discrétionnaire": 30, "Communication": 21, "Finance": 16, "Technologie": 9,
                   "Industrie": 6, "Consommation de base": 4, "Santé": 4, "Énergie": 3, "Matériaux": 3,
                   "Immobilier": 2, "Services publics": 2},
    "MSCI India": {"Finance": 30, "Consommation discrétionnaire": 12, "Technologie": 11, "Énergie": 9,
                   "Industrie": 9, "Matériaux": 8, "Consommation de base": 6, "Santé": 6, "Communication": 4,
                   "Services publics": 4, "Immobilier": 1},
    "MSCI Korea": {"Technologie": 40, "Industrie": 15, "Finance": 12, "Consommation discrétionnaire": 9,
                   "Santé": 7, "Communication": 6, "Matériaux": 5, "Consommation de base": 3, "Énergie": 2,
                   "Services publics": 1},
    "MSCI Taiwan": {"Technologie": 70, "Finance": 15, "Industrie": 4, "Matériaux": 4, "Communication": 3,
                    "Consommation discrétionnaire": 2, "Consommation de base": 1, "Santé": 1},
    "MSCI Brazil": {"Finance": 35, "Énergie": 15, "Matériaux": 14, "Services publics": 10, "Industrie": 9,
                    "Consommation de base": 6, "Consommation discrétionnaire": 4, "Santé": 3, "Communication": 3,
                    "Technologie": 1},
    "FTSE 100": {"Finance": 22, "Consommation de base": 14, "Industrie": 14, "Santé": 12, "Énergie": 11,
                 "Matériaux": 9, "Consommation discrétionnaire": 7, "Services publics": 4, "Communication": 4,
                 "Immobilier": 1.5, "Technologie": 1.5},
    "MSCI Switzerland": {"Santé": 33, "Consommation de base": 19, "Finance": 19, "Industrie": 10, "Matériaux": 7,
                         "Consommation discrétionnaire": 6, "Technologie": 2, "Communication": 1.5,
                         "Immobilier": 1.5},
    "MSCI Canada": {"Finance": 35, "Énergie": 17, "Industrie": 12, "Matériaux": 12, "Technologie": 9,
                    "Consommation discrétionnaire": 4, "Consommation de base": 4, "Services publics": 3,
                    "Communication": 2.5, "Immobilier": 1.5},
    "MSCI Australia": {"Finance": 35, "Matériaux": 20, "Santé": 8, "Consommation discrétionnaire": 7,
                       "Industrie": 7, "Immobilier": 7, "Énergie": 4, "Consommation de base": 4, "Communication": 3,
                       "Technologie": 3, "Services publics": 2},
}
# Indices dont la répartition sectorielle est celle d'un autre (même univers, ou presque)
for _indice, _modele in {"MSCI USA": "S&P 500", "MSCI North America": "S&P 500", "MSCI Singapore": "MSCI Pacific ex Japan", "MSCI Europe ex UK": "MSCI Europe", "MSCI Pacific": "MSCI Japan",
                         "MSCI EM Asia": "MSCI AC Asia ex Japan", "MSCI EM ex China": "MSCI Emerging Markets",
                         "MSCI EM Latin America": "MSCI Brazil", "MSCI Italy": "MSCI EMU", "MSCI Spain": "MSCI EMU",
                         "MSCI Netherlands": "MSCI EMU", "France petites et moyennes valeurs": "MSCI Europe Small Cap",
                         "MDAX": "MSCI Europe Small Cap"}.items():
    SECTEURS_PAR_INDICE[_indice] = SECTEURS_PAR_INDICE[_modele]

# ----------------------------------------------------------------------
# 4. Quel indice suit chaque ETF ?
# ----------------------------------------------------------------------
ETF_INDICE = {
    "CW8.PA": "MSCI World", "EWLD.PA": "MSCI World", "WPEA.PA": "MSCI World", "IWDA.AS": "MSCI World",
    "EUNL.DE": "MSCI World", "SWDA.L": "MSCI World", "URTH": "MSCI World",
    "VWCE.DE": "MSCI ACWI", "VWRL.AS": "MSCI ACWI", "IUSQ.DE": "MSCI ACWI", "SPYI.DE": "MSCI ACWI",
    "VT": "MSCI ACWI", "ACWI": "MSCI ACWI",
    "ESE.PA": "S&P 500", "PE500.PA": "S&P 500", "VUSA.AS": "S&P 500", "SXR8.DE": "S&P 500", "CSPX.L": "S&P 500",
    "SPY": "S&P 500", "VOO": "S&P 500", "IVV": "S&P 500", "DIA": "S&P 500",
    "PUST.PA": "Nasdaq-100", "EQQQ.DE": "Nasdaq-100", "QQQ": "Nasdaq-100",
    "PAEEM.PA": "MSCI Emerging Markets", "AEEM.PA": "MSCI Emerging Markets", "EIMI.L": "MSCI Emerging Markets",
    "IS3N.DE": "MSCI Emerging Markets", "VWO": "MSCI Emerging Markets", "EEM": "MSCI Emerging Markets",
    "CAC.PA": "CAC 40", "CACC.PA": "CAC 40", "C40.PA": "CAC 40", "MSE.PA": "Euro Stoxx 50", "C50.PA": "Euro Stoxx 50", "EXS1.DE": "DAX",
    "EUNK.DE": "MSCI Europe", "MEUD.PA": "MSCI Europe",
    "VEA": "MSCI EAFE", "EFA": "MSCI EAFE", "VTI": "US Total Market", "IWM": "Russell 2000",
    "IBCA.DE": "Emprunts d'État zone euro", "EUNH.DE": "Emprunts d'État zone euro", "DBXN.DE": "Emprunts d'État zone euro",
    "IBCI.DE": "Emprunts d'État zone euro", "EUN5.DE": "Obligations d'entreprises euro",
    "EUNW.DE": "Haut rendement euro", "TLT": "Emprunts d'État américains", "IEF": "Emprunts d'État américains",
    "SHY": "Emprunts d'État américains", "TIP": "Emprunts d'État américains", "AGG": "Emprunts d'État américains",
    "BND": "Emprunts d'État américains", "LQD": "Obligations d'entreprises américaines",
    "HYG": "Obligations d'entreprises américaines", "EMB": "Obligations émergentes en dollars",
    # Autres ETF très détenus (le nom suffit aussi : cette table sert quand le libellé est illisible)
    "MWRD.PA": "MSCI World", "XDWD.DE": "MSCI World", "SPPW.DE": "MSCI World", "VEVE.AS": "MSCI World",
    "VWRA.L": "MSCI ACWI", "SSAC.L": "MSCI ACWI", "ISAC.L": "MSCI ACWI",
    "VFEM.AS": "MSCI Emerging Markets", "XMME.DE": "MSCI Emerging Markets", "IEMG": "MSCI Emerging Markets",
    "500.PA": "S&P 500", "PSP5.PA": "S&P 500", "VUAA.DE": "S&P 500", "CNDX.L": "Nasdaq-100", "SXRV.DE": "Nasdaq-100",
    "PANX.PA": "Nasdaq-100", "QQQM": "Nasdaq-100",
    "CEU.PA": "MSCI Europe", "PCEU.PA": "MSCI Europe", "EXSA.DE": "MSCI Europe", "VEUR.AS": "MSCI Europe",
    "EXW1.DE": "Euro Stoxx 50", "FEZ": "Euro Stoxx 50", "DBXD.DE": "DAX",
    "EWJ": "MSCI Japan", "PTPXE.PA": "MSCI Japan", "RS2K.PA": "Russell 2000", "IUSN.DE": "MSCI World Small Cap",
    "WSML.L": "MSCI World Small Cap", "MCHI": "MSCI China", "FXI": "MSCI China", "INDA": "MSCI India",
    "EWZ": "MSCI Brazil", "EWY": "MSCI Korea", "EWT": "MSCI Taiwan", "EWU": "FTSE 100", "EWL": "MSCI Switzerland",
    "EWC": "MSCI Canada", "EWA": "MSCI Australia", "AAXJ": "MSCI AC Asia ex Japan", "RSP": "S&P 500 Equal Weight",
    "IJR": "Russell 2000", "VB": "Russell 2000", "VGK": "MSCI Europe", "EZU": "MSCI EMU",
    "BNDX": "Obligations agrégées mondiales", "VCIT": "Obligations d'entreprises américaines",
    "IUSB": "Emprunts d'État américains", "GOVT": "Emprunts d'État américains",
}
# Reconnaissance par le nom, pour les ETF absents de la liste ci-dessus (ORDRE IMPORTANT : du plus
# précis au plus général ; « Asia Pacific ex Japan » avant « Japan », « World Small Cap » avant « World »).
# Le nom est d'abord complété par ses abréviations développées (libellés tronqués des avis d'opéré :
# « AM P AP M AC AP EX JAP ETF-C » = Amundi PEA MSCI AC Asia Pacific ex Japan, voir developper()).
_OBLIG = r"(bond|oblig|govt|government|gov\b|treasur|aggregate|\bagg\b|corp|high yield|inflation|linker|\btips\b|" \
         r"souverain|sovereign|gilt|credit|\bbtp\b|\boat\b)"
MOTIFS_NOM = [
    # --- obligations (le nom contient un mot obligataire) ---
    (rf"(?=.*{_OBLIG})(?=.*(emerging|emergent|\bem\b)).*(local)", "Obligations émergentes en devises locales"),
    (rf"(?=.*{_OBLIG}).*(emerging|emergent|\bem\b|jp ?morgan embi)", "Obligations émergentes en dollars"),
    (rf"(?=.*(inflation|linker|indexed|\binfl\b|indexées|indexe)).*(euro|€|\beur\b|eurozone|\bemu\b|oat)",
     "Obligations indexées sur l'inflation euro"),
    (r"\btips\b|(us|u\.s\.|usd|\$|treasury).*inflation|inflation.*(us|u\.s\.|usd|\$|treasury)",
     "Emprunts d'État américains"),
    (r"(global|world|monde|mondial).*(aggregate|\bagg\b)|(aggregate|\bagg\b).*(global|world)",
     "Obligations agrégées mondiales"),
    (r"(global|world|monde|mondial).*(govt|government|sovereign|souverain|état|etat)", "Emprunts d'État mondiaux"),
    (rf"(?=.*{_OBLIG})(global|world|monde|mondial).*corp", "Obligations d'entreprises mondiales"),
    (r"(€|eur|euro|eurozone|\bemu\b).*(aggregate|\bagg\b)", "Obligations agrégées euro"),
    (r"(€|eur|euro).*(high yield|haut rendement|\bhy\b)", "Haut rendement euro"),
    (r"(€|eur|euro).*(corp|entreprise|credit)", "Obligations d'entreprises euro"),
    (r"(€|eur|euro|eurozone|\bemu\b).*(govt|gov\b|government|state|souverain|sovereign|état|etat|\bbtp\b|\boat\b)",
     "Emprunts d'État zone euro"),
    (r"(us|u\.s\.|usd|\$|dollar).*(high yield|\bhy\b)|(high yield|\bhy\b).*(us|usd|\$)",
     "Obligations d'entreprises américaines"),
    (r"(us|u\.s\.|usd|\$|dollar).*(corp|investment grade|credit)|\blqd\b", "Obligations d'entreprises américaines"),
    (r"treasury|us aggregate|u\.s\. aggregate|total bond|us govt|us government", "Emprunts d'État américains"),
    (rf"(?=.*{_OBLIG})(japan|japon|\bjgb\b)", "Emprunts d'État japonais"),
    (rf"(?=.*{_OBLIG})(\buk\b|gilt|united kingdom|sterling|\bgbp\b)", "Emprunts d'État britanniques"),
    # obligations sans précision : selon la zone ou la devise écrite dans le nom
    (rf"(?=.*{_OBLIG})(global|world|monde|mondial)", "Obligations agrégées mondiales"),
    (rf"(?=.*{_OBLIG})(€|\beur\b|\beuro\b|eurozone|\bemu\b)", "Obligations agrégées euro"),
    (rf"(?=.*{_OBLIG})(\busd\b|\$|dollar|\busa?\b|u\.s\.)", "Emprunts d'État américains"),
    # --- actions : Asie et Pacifique (avant « Japan », « Asia », « emerging ») ---
    (r"(asia|asie)[ -]?(pac|pacific|pacifique)[a-z]*.*ex[ -]?(jap|japan|japon)|"
     r"apac.*ex[ -]?(jap|japan)|(all country|\bac\b).*(asia|asie).*(pac|pacific).*ex", "MSCI AC Asia Pacific ex Japan"),
    (r"(pacific|pacifique).*ex[ -]?(jap|japan|japon)", "MSCI Pacific ex Japan"),
    (r"(asia|asie).*ex[ -]?(jap|japan|japon)|far east ex|asia 50|asie hors japon", "MSCI AC Asia ex Japan"),
    (r"(emerging|emergent|émergent|\bem\b).*(asia|asie)|(asia|asie).*(emerging|émergente?|emergente?)",
     "MSCI EM Asia"),
    (r"latin america|latam|amérique latine|amerique latine", "MSCI EM Latin America"),
    (r"(emerging|\bem\b).*ex[ -]?china|ex[ -]?china.*(emerging|\bem\b)", "MSCI EM ex China"),
    (r"china|chine|csi ?300|hang seng|\bhscei\b|a50", "MSCI China"),
    (r"\bindia\b|\binde\b|nifty|sensex", "MSCI India"),
    (r"korea|corée|coree", "MSCI Korea"),
    (r"taiwan|taïwan", "MSCI Taiwan"),
    (r"brazil|brésil|bresil|bovespa|ibovespa", "MSCI Brazil"),
    (r"japan|japon|\bjpn\b|topix|nikkei|jpx", "MSCI Japan"),
    (r"pacific|pacifique", "MSCI Pacific"),
    (r"\basia\b|\basie\b", "MSCI AC Asia ex Japan"),
    # --- actions : petites capitalisations (avant les indices larges) ---
    (r"(world|global|monde|mondial|acwi).*(small|petites)|small ?cap.*(world|global)", "MSCI World Small Cap"),
    (r"(europe|euro|emu).*(small|petites|mid)|(small|petites).*europe", "MSCI Europe Small Cap"),
    (r"russell 2000|s&p ?600|small ?cap 600|(us|usa|u\.s\.).*small|small.*(us|usa)\b", "Russell 2000"),
    (r"cac (mid|small)|mid ?60|enternext|pea[ -]?pme|sbf ?120|cac all|france (small|mid)", 
     "France petites et moyennes valeurs"),
    (r"\bmdax\b|\bsdax\b", "MDAX"),
    # --- actions : monde ---
    (r"all[- ]?world|acwi|all country world|(\bac\b|all country) world|total world|world all cap|"
     r"ftse global all", "MSCI ACWI"),
    (r"emerging|émergent|emergent|\bem\b|\bem imi\b|\bemu?ergent", "MSCI Emerging Markets"),
    (r"eafe|developed markets ex|ex[- ]?(us|usa)\b|world ex[- ]?(us|usa)|international developed",
     "MSCI EAFE"),
    (r"msci world|developed world|\bworld\b|monde|mondial|\bglobal\b|\bwld\b", "MSCI World"),
    # --- actions : États-Unis ---
    (r"nasdaq|\bndx\b", "Nasdaq-100"),
    (r"(s&p ?500|sp ?500).*(equal|\bew\b)|equal weight.*(500|us)", "S&P 500 Equal Weight"),
    (r"s&p ?500|sp ?500|\bspx\b", "S&P 500"),
    (r"total (stock|us|u\.s\.) market|crsp us total|russell 3000", "US Total Market"),
    (r"north america|amérique du nord|amerique du nord", "MSCI North America"),
    (r"msci usa|\busa\b|united states|états[- ]unis|etats[- ]unis|\bus equity|russell 1000|dow jones industrial|"
     r"\bdjia\b|\bus\b(?!d)", "MSCI USA"),
    # --- actions : Europe ---
    (r"euro ?stoxx ?50|\bstoxx ?50\b|\bestx ?50\b|eurostoxx50", "Euro Stoxx 50"),
    (r"europe ex[- ]?(uk|united kingdom)", "MSCI Europe ex UK"),
    (r"\bemu\b|eurozone|euro ?zone|zone euro|euro ?stoxx|msci euro\b|\beuro\b(?! ?stoxx)(?=.*(equity|actions|"
     r"msci|stoxx|etf))", "MSCI EMU"),
    (r"stoxx (europe )?600|europe 600|msci europe|developed europe|\beurope\b|\beurop\b", "MSCI Europe"),
    (r"cac ?40|\bc\.c\.40\b|\bcac\b", "CAC 40"),
    (r"\bdax\b|germany|allemagne", "DAX"),
    (r"ftse ?100|ftse ?250|\buk\b|united kingdom|royaume[- ]uni|britain", "FTSE 100"),
    (r"switzerland|\bswiss\b|suisse|\bsmi\b", "MSCI Switzerland"),
    (r"canada|\btsx\b", "MSCI Canada"),
    (r"singapore|singapour", "MSCI Singapore"),
    (r"australia|australie|\basx\b", "MSCI Australia"),
    (r"\bitaly\b|italie|ftse ?mib", "MSCI Italy"),
    (r"\bspain\b|espagne|\bibex\b", "MSCI Spain"),
    (r"netherlands|pays[- ]bas|\baex\b", "MSCI Netherlands"),
    (r"\bfrance\b", "CAC 40"),
]
_MOTIFS_NOM = [(re.compile(m, re.IGNORECASE), i) for m, i in MOTIFS_NOM]

# Abréviations des libellés d'avis d'opéré (souvent limités à 30 caractères) : mot abrégé -> mot entier.
# « AM P AP M AC AP EX JAP ETF-C » -> « amundi pea asia pacific msci all country asia pacific ex japan etf-c »
ABREVIATIONS = {
    "AM": "amundi", "AMUN": "amundi", "LYX": "lyxor", "ISH": "ishares", "ISHS": "ishares", "ISHR": "ishares",
    "XTR": "xtrackers", "XTRA": "xtrackers", "DBX": "xtrackers", "BNPP": "bnp paribas", "VANG": "vanguard",
    "INV": "invesco", "HSBC": "hsbc", "UBS": "ubs", "WT": "wisdomtree", "SPDR": "spdr",
    "P": "pea", "M": "msci", "AC": "all country", "AP": "asia pacific", "APAC": "asia pacific",
    "PAC": "pacific", "JAP": "japan", "JPN": "japan", "JP": "japan", "EXJAP": "ex japan", "XJ": "ex japan",
    "EMER": "emerging", "EMERG": "emerging", "EMRG": "emerging", "EMG": "emerging", "EME": "emerging",
    "EMKT": "emerging markets", "WLD": "world", "WRLD": "world", "WORL": "world", "MOND": "monde",
    "STX": "stoxx", "ESTX": "euro stoxx", "SP": "s&p", "NASD": "nasdaq", "NSDQ": "nasdaq", "NDX": "nasdaq",
    "SC": "small cap", "SMC": "small cap", "SMCAP": "small cap", "EW": "equal weight", "GOV": "government",
    "GVT": "government", "GOVT": "government", "CRP": "corporate", "CORP": "corporate", "HY": "high yield",
    "INFL": "inflation", "LAT": "latin america", "LATAM": "latin america", "CHN": "china", "EUR": "europe",
    "EURP": "europe", "EUROP": "europe", "EUROPE": "europe", "US": "usa", "USA": "usa", "TOT": "total",
    "AGG": "aggregate", "IMI": "imi", "CW": "world",
}


# Noms compacts du fichier Xetra (« AIS-AM.S+P500 SW.UETFEOCD », « X(IE)-MSCIACWLDSC 1C »,
# « ISHS3-A.XJPEQ.EN.ACT.DLA », « STXE600 ») : mots collés, abréviations et code de la part
# (devise EO = euro, DL = dollar ; A = capitalisation, D = distribution ; H = couverte) à la fin.
_COMPACTS = [
    (r"S\+P|S&P", " S&P "), (r"\bSP5\b|SP500", " S&P 500 "), (r"SEU ?600|S\.EU\.600|ST\.EO ?600|S\.E\.600|\bST ?600", " STOXX EUROPE 600 "),
    (r"DLHY|USD ?HY", " USD HIGH YIELD BOND "),
    (r"\bCOR\.? ?B\b|CORPB|CORPHYB|\bCOR\b|\bCB\b", " CORPORATE BOND "), (r"EMBD|EM\.?BD|\bEMB\b", " EMERGING BOND "),
    (r"500 ?EW\b|500EW|EQLW|EQW\b", " 500 EQUAL WEIGHT "), (r"\bGEM\b", " GLOBAL EMERGING MARKETS "), (r"USTB|US ?T\.?B\b", " US TREASURY BOND "), (r"\bG\.C\.BD", " GLOBAL CORPORATE BOND "),
    (r"\bEOZ\b|EOZ\.", " EUROZONE "), (r"\bGBD\b|\.GBD", " GOVERNMENT BOND "), (r"\bSLI\b", " SWISS "),
    (r"\bN\.A\b", " NORTH AMERICA "), (r"\bST50|D\.E\.ST50", " EURO STOXX 50 "),
    (r"AP\.? ?EX ?JN|AP ?EX ?JAP", " ASIA PACIFIC EX JAPAN "), (r"EX ?JN\b", " EX JAPAN "),
    (r"HYCP|HY ?CORP", " HIGH YIELD CORPORATE BOND "), (r"NTH\.? ?AMERICA|N\.AMERICA|NORTH ?AM\w*", " NORTH AMERICA "),
    (r"EPRA|NAREIT", " GLOBAL REAL ESTATE "),
    (r"EUROG\b|EUROGOV|EO ?GB\b|EOGB", " EURO GOVERNMENT BOND "), (r"\bIBD\b|IBONDS", " BOND "),
    (r"USTR\b|USTR\.|US ?TREAS", " US TREASURY "), (r"\bH\.Y\.", " HIGH YIELD "), (r"EMEXC", " EMERGING EX CHINA "),
    (r"MSCI ?CN|\bCN\b|C\.M\.CN", " CHINA "), (r"\bU\.S\b|\bU\.S\.", " USA "), (r"ACW(?=[A-Z]|\b)", " ACWI "),
    (r"\bW\b(?= [A-Z])|\bM\.W\.", " WORLD "), (r"\bEUR(?=[A-Z]{2})|MSCI ?EU\b", " EUROPE "),
    (r"STXE ?600|STOXX ?EUROPE ?600|STX ?600|STXX ?EO ?600|STXEO600|ST\.EUR\.600", " STOXX EUROPE 600 "),
    (r"\bEO ?STOXX|\bEO ?STXX", " EURO STOXX "), (r"\bE\.G\.B\b|\bEGB\b", " EURO GOVERNMENT BOND "),
    (r"GABD|GL\.?AG\.?BD", " GLOBAL AGGREGATE BOND "), (r"X ?UK\b|EX ?UK\b|EXUK", " EX UK "),
    (r"\bD\.E\.|DEV\.? ?EUR", " DEVELOPED EUROPE "), (r"BRAZ\w*", " BRAZIL "), (r"NDQ ?100|NDQ\b", " NASDAQ 100 "),
    (r"APACXJ|APAC ?EX ?J", " ASIA PACIFIC EX JAPAN "), (r"\bBO\b", " BOND "),
    (r"EO ?STXX ?50|EURO ?STXX ?50|ESTX ?50|STXX ?50|STOXX ?50", " EURO STOXX 50 "),
    (r"STXX|STX", " STOXX "), (r"NA100|NAS100|NQ100|NASDAQ100|NASD100|NDX100", " NASDAQ 100 "),
    (r"MSCI(?=[A-Z])", "MSCI "), (r"ACWLD|ACWI|AC ?WLD|AC ?WORLD", " ACWI "),
    (r"(?<=[A-Z.])WLD|\bWLD|WRLD|\bWD(?=[A-Z]{0,4}\b)", " WORLD "), (r"\bW\.(?=[A-Z])", " WORLD "),
    (r"A\.?XJP|ASIA ?XJ|ASXJ|AXJ|APXJ|AP ?EX ?JAP", " ASIA PACIFIC EX JAPAN "),
    (r"JPEQ|\bJAP\b|\bJPN\b|\bJP(?=[A-LN-Z])|\bJP\.(?=GOV)|JAPAN", " JAPAN "),
    (r"\bE\.M\.|EMMKT|EMKT|EMERG\w*|\bEM(?=[A-Z]{2})|\bEM\b", " EMERGING "),
    (r"\bGL\b|\bGLB\b|\bGLOB\b|\bGL\.", " GLOBAL "), (r"\bEQ\b", " EQUITY "),
    (r"C\.?BD|CORP\.?BD|CRP\.?BD", " CORPORATE BOND "), (r"\bBDS?\b|(?<=[A-Z.])BD\b", " BOND "),
    (r"GOV(?:T|BD)?|\bGB(?=\d|\b)|GVT", " GOVERNMENT "), (r"\bHY\b|\.HY\.", " HIGH YIELD "),
    (r"\bAGG?\b|\.AG\.", " AGGREGATE "), (r"\bTR\.|\bTRS\b|TREAS\w*", " TREASURY "),
    (r"\bSC\b|(?<=[A-Z])SC(?=ESG|\b)|SMCAP|SM\.C", " SMALL CAP "), (r"\bEU\b|\bEUR\b|EURP", " EUROPE "),
    (r"\bUS(?=[A-Z]{2,}|\b)", " USA "),
]
_COMPACTS = [(re.compile(m), r) for m, r in _COMPACTS]
# code de la part en fin de nom : « EOA », « DLD », « 1CEOA », « HGDEOA », « UETFEOCD », « ETFDLA »…
_CODE_PART = re.compile(r"\b\d?[CD]?(?:U?E?(?:TF)?)?(?:HGD|H)?(?:EO|DL|SF|LS|YN|EUR|USD|GBP|CHF)"
                        r"(?:H|HD|HGD)?(?:A|D|C|HA|HD|CD|AH|ACC|DIS)?\s*$")
_DEVISE_BOND = [(re.compile(r"\bEO\b|(?<=[A-Z.])EO(?=[A-Z.]|\b)"), " EURO "),
                (re.compile(r"\bDL\b|(?<=[A-Z.])DL(?=[A-Z.]|\b)"), " USD ")]


def _decompacter(nom):
    """« AIS-AM.S+P500 SW.UETFEOCD » -> « … S&P 500 … » (noms compacts du fichier Xetra)."""
    texte = str(nom or "").upper()
    texte = _CODE_PART.sub(" ", texte)                    # la devise de la part n'est pas l'exposition
    texte = re.sub(r"\bEO\b(?= [A-Z])", " EURO ", texte)   # « MSCI EO TECH », « EO STOXX » : zone euro
    if re.search(r"BD|BOND|GOV|TREAS|HY\b|AGG", texte):  # obligations : EO / DL = zone euro / dollar
        for motif, remplacement in _DEVISE_BOND:
            texte = motif.sub(remplacement, texte)
    for motif, remplacement in _COMPACTS:
        texte = motif.sub(remplacement, texte)
    texte = re.sub(r"S&P\s*(500|600|400)", r"S&P \1", texte)
    return " ".join(texte.replace(".", " ").replace("-", " ").split()).lower()


def developper(nom):
    """Nom complété par ses abréviations développées (« AM P AP M AC AP EX JAP ETF-C » ->
    « … amundi pea asia pacific msci all country asia pacific ex japan … »). Le nom d'origine est
    gardé en tête : les motifs peuvent porter sur l'un ou l'autre."""
    nom = str(nom or "")
    mots = re.findall(r"[A-Za-z0-9&€$]+", nom.replace("S&P", "S&P"))
    developpes = [ABREVIATIONS.get(m.upper(), m.lower()) if (m.isupper() or len(m) <= 4) else m.lower()
                  for m in mots]
    return nom + " | " + " ".join(developpes) + " | " + _decompacter(nom)


# Catégories Morningstar (données par Yahoo Finance pour les fonds et ETF) -> indice proche
MOTIFS_CATEGORIE = [
    (r"asia[- ]pacific ex[- ]japan|pacific/asia ex-japan|asia ex-japan|asia ex japan", "MSCI AC Asia Pacific ex Japan"),
    (r"china", "MSCI China"), (r"india", "MSCI India"), (r"korea", "MSCI Korea"), (r"taiwan", "MSCI Taiwan"),
    (r"brazil", "MSCI Brazil"), (r"latin america", "MSCI EM Latin America"),
    (r"japan", "MSCI Japan"), (r"pacific", "MSCI Pacific"),
    (r"emerging.*bond|emerging markets bond|em bond", "Obligations émergentes en dollars"),
    (r"global emerging|diversified emerging|emerging markets", "MSCI Emerging Markets"),
    (r"global (small|mid)|world small", "MSCI World Small Cap"),
    (r"global|world|foreign large|international", "MSCI World"),
    (r"(us|u\.s\.) small|small (blend|value|growth)", "Russell 2000"),
    (r"(us|u\.s\.) large|large (blend|value|growth)|us equity", "S&P 500"),
    (r"eurozone|euro large", "MSCI EMU"),
    (r"europe.*(small|mid)", "MSCI Europe Small Cap"),
    (r"europe", "MSCI Europe"),
    (r"uk ", "FTSE 100"), (r"switzerland|swiss", "MSCI Switzerland"), (r"france", "CAC 40"),
    (r"germany", "DAX"),
    (r"eur (government|govt)", "Emprunts d'État zone euro"),
    (r"eur (corporate|corp)", "Obligations d'entreprises euro"),
    (r"eur high yield", "Haut rendement euro"),
    (r"eur inflation", "Obligations indexées sur l'inflation euro"),
    (r"eur diversified bond|eur aggregate", "Obligations agrégées euro"),
    (r"global bond", "Obligations agrégées mondiales"),
    (r"(usd|us) (government|govt)|long government|short government|intermediate government|inflation-protected",
     "Emprunts d'État américains"),
    (r"(usd|us) corporate|corporate bond|high yield bond|intermediate core", "Obligations d'entreprises américaines"),
]
_MOTIFS_CATEGORIE = [(re.compile(m, re.IGNORECASE), i) for m, i in MOTIFS_CATEGORIE]


def indice_de_la_categorie(categorie):
    """Catégorie Morningstar (Yahoo Finance) -> indice proche, ou None."""
    for motif, indice in _MOTIFS_CATEGORIE:
        if motif.search(str(categorie or "")):
            return indice
    return None


MOTIF_COUVERT = re.compile(r"hedged|couvert|\(eur h\)|eur hdg|\bhdg\b", re.IGNORECASE)


# ETC / ETP (matières premières, cryptoactifs, produits à effet de levier ou inversés) : pas un indice
# d'actions ou d'obligations (l'or est reconnu à part, src/classement.py)
MOTIF_PAS_UN_INDICE = re.compile(r"\bETC\b|\bETP\b|OPEN[ -]?END|O\.\s?END|\bOEND\b|BITCOIN|CRYPTO|ETHEREUM|SOLANA|"
                                 r"LEVERAGE SHARES|WITR (?:COM|MET|FOR|SEC)|\b[235]X\b|\bSHORT\b|-1X|DAILY -?\dX",
                                 re.IGNORECASE)


def indice_suivi(ticker, nom="", categorie=""):
    """Indice suivi par un ETF (clé de PAYS_PAR_INDICE), ou None si inconnu : table des ETF connus,
    puis le nom (abréviations développées), puis la catégorie Morningstar donnée par Yahoo Finance."""
    if ticker in ETF_INDICE:
        return ETF_INDICE[ticker]
    if nom and MOTIF_PAS_UN_INDICE.search(str(nom)):
        return indice_de_la_categorie(categorie) if categorie else None
    if nom:
        complet = developper(nom)
        for motif, indice in _MOTIFS_NOM:
            if motif.search(complet):
                return indice
    return indice_de_la_categorie(categorie) if categorie else None


def est_couvert(nom):
    """Vrai si le nom de l'ETF indique une couverture du risque de change (« EUR Hedged »)."""
    return bool(MOTIF_COUVERT.search(str(nom or "")))


def pays_de(indice):
    """Répartition par pays d'un indice, en fractions (total = 1)."""
    poids = pd.Series(PAYS_PAR_INDICE[indice], dtype=float)
    return poids / poids.sum()


def secteurs_de(indice):
    """Répartition par secteur d'un indice actions, en fractions (total = 1), ou None."""
    if indice not in SECTEURS_PAR_INDICE:
        return None
    poids = pd.Series(SECTEURS_PAR_INDICE[indice], dtype=float)
    return poids / poids.sum()


def iso3(pays):
    return PAYS.get(pays, (None,))[0]


def devise_du_pays(pays):
    return PAYS.get(pays, (None, None))[1]


def region_du_pays(pays):
    return PAYS.get(pays, (None, None, None))[2]


def region_de_l_indice(indice):
    """Région dominante d'un indice (au moins 80 % de son poids), sinon « Monde (ETF) » ; None si
    l'indice est inconnu. Ex. MSCI AC Asia Pacific ex Japan -> Asie-Pacifique (Australie, Hong Kong,
    Singapour) + Émergents (Chine, Taïwan, Inde, Corée) : aucune ne dépasse 60 %, mais l'ensemble est
    en Asie -> « Asie-Pacifique »."""
    if indice not in PAYS_PAR_INDICE:
        return None
    poids = pays_de(indice)
    asie = sum(v for p, v in poids.items() if p in ASIE)
    # indice asiatique multi-pays (Asie-Pacifique hors Japon, Pacifique…) : « Asie-Pacifique », même si
    # la Chine, Taïwan, l'Inde ou la Corée y sont classées « émergents » pays par pays
    if asie >= 0.8 and len(poids) >= 3 and "EM " not in indice and "Emerging" not in indice:
        return "Asie-Pacifique"
    par_region = poids.groupby(lambda p: region_du_pays(p) or AUTRES).sum()
    if par_region.max() >= 0.8:
        return str(par_region.idxmax())
    if sum(par_region.get(r, 0) for r in ("Europe", "Royaume-Uni", "Suisse")) >= 0.8:
        return "Europe"                    # Europe au sens large (avec le Royaume-Uni et la Suisse)
    return "Monde (ETF)"


ASIE = {"Japon", "Chine", "Taïwan", "Corée du Sud", "Inde", "Australie", "Nouvelle-Zélande", "Hong Kong", "Singapour",
        "Indonésie", "Malaisie", "Thaïlande", "Philippines"}

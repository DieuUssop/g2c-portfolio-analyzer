"""
places.py — UNE table des places de cotation (revue du 26/11/2026).

Avant, chaque module avait sa propre liste (devise de repli dans devises.py, pays dans
classement.py, préfixe ISIN dans import_fichier.py) : une place ajoutée à l'une était oubliée
dans les autres (Séoul, Taïwan, Johannesburg… : devise « EUR » par défaut, pays inconnu).
Tout part maintenant d'ici ; tests/test_places.py vérifie qu'aucune place n'est incomplète.

Pour ajouter une place : une ligne dans PLACES_COTATION (suffixe Yahoo Finance, devise telle
que Yahoo l'écrit, pays, région, préfixes ISIN du pays). Les sous-unités (pence de Londres,
cents de Johannesburg, agorot de Tel-Aviv) sont dans SOUS_UNITES.
"""

# suffixe Yahoo : (devise de cotation selon Yahoo, pays, région, préfixes ISIN de ce pays)
PLACES_COTATION = {
    # Zone euro
    ".PA": ("EUR", "France", "Europe", ("FR",)),
    ".DE": ("EUR", "Allemagne", "Europe", ("DE",)),
    ".F": ("EUR", "Allemagne", "Europe", ()),
    ".AS": ("EUR", "Pays-Bas", "Europe", ("NL",)),
    ".BR": ("EUR", "Belgique", "Europe", ("BE",)),
    ".MC": ("EUR", "Espagne", "Europe", ("ES",)),
    ".MI": ("EUR", "Italie", "Europe", ("IT",)),
    ".LS": ("EUR", "Portugal", "Europe", ("PT",)),
    ".IR": ("EUR", "Irlande", "Europe", ()),
    ".VI": ("EUR", "Autriche", "Europe", ("AT",)),
    ".HE": ("EUR", "Finlande", "Europe", ("FI",)),
    ".AT": ("EUR", "Grèce", "Émergents", ("GR",)),
    # Reste de l'Europe
    ".L": ("GBp", "Royaume-Uni", "Royaume-Uni", ("GB",)),
    ".SW": ("CHF", "Suisse", "Suisse", ("CH",)),
    ".CO": ("DKK", "Danemark", "Europe", ("DK",)),
    ".ST": ("SEK", "Suède", "Europe", ("SE",)),
    ".OL": ("NOK", "Norvège", "Europe", ("NO",)),
    ".WA": ("PLN", "Pologne", "Émergents", ("PL",)),
    ".PR": ("CZK", "Tchéquie", "Émergents", ("CZ",)),
    ".IS": ("TRY", "Turquie", "Émergents", ("TR",)),
    # Amériques
    "": ("USD", "États-Unis", "États-Unis", ("US",)),
    ".TO": ("CAD", "Canada", "Canada", ("CA",)),
    ".V": ("CAD", "Canada", "Canada", ()),
    ".SA": ("BRL", "Brésil", "Émergents", ("BR",)),
    ".MX": ("MXN", "Mexique", "Émergents", ("MX",)),
    # Asie-Pacifique
    ".T": ("JPY", "Japon", "Japon", ("JP",)),
    ".HK": ("HKD", "Hong Kong", "Asie-Pacifique", ("HK",)),
    ".AX": ("AUD", "Australie", "Asie-Pacifique", ("AU",)),
    ".NZ": ("NZD", "Nouvelle-Zélande", "Asie-Pacifique", ("NZ",)),
    ".SI": ("SGD", "Singapour", "Asie-Pacifique", ("SG",)),
    ".KS": ("KRW", "Corée du Sud", "Émergents", ("KR",)),
    ".KQ": ("KRW", "Corée du Sud", "Émergents", ()),
    ".TW": ("TWD", "Taïwan", "Émergents", ("TW",)),
    ".TWO": ("TWD", "Taïwan", "Émergents", ()),
    ".SS": ("CNY", "Chine", "Émergents", ("CN",)),
    ".SZ": ("CNY", "Chine", "Émergents", ()),
    ".NS": ("INR", "Inde", "Émergents", ("IN",)),
    ".BO": ("INR", "Inde", "Émergents", ()),
    ".KL": ("MYR", "Malaisie", "Émergents", ("MY",)),
    ".JK": ("IDR", "Indonésie", "Émergents", ("ID",)),
    ".BK": ("THB", "Thaïlande", "Émergents", ("TH",)),
    # Afrique et Moyen-Orient
    ".JO": ("ZAc", "Afrique du Sud", "Émergents", ("ZA",)),
    ".TA": ("ILA", "Israël", "Asie-Pacifique", ("IL",)),
}

# Places « secondaires » : un titre étranger y est coté dans une autre devise que sa place d'origine.
# Pas de pays (celui de la société est donné par Yahoo ou par le référentiel), devise de repli seulement.
PLACES_SECONDAIRES = {
    ".IL": "USD",         # Londres, carnet international (certificats GDR : SMSN.IL = Samsung, en dollars)
    ".XC": "EUR", ".XD": "EUR", ".SG": "EUR", ".DU": "EUR", ".MU": "EUR", ".BE": "EUR",
    ".HM": "EUR", ".HA": "EUR", ".TI": "EUR", ".NE": "CAD", ".AQ": "GBp",
}

# Devises cotées en centièmes : code Yahoo -> (devise, facteur)
SOUS_UNITES = {"GBp": ("GBP", 0.01), "GBX": ("GBP", 0.01), "ZAc": ("ZAR", 0.01), "ZAC": ("ZAR", 0.01),
               "ILA": ("ILS", 0.01)}

# Devises reconnues dans une colonne « Devise » d'un fichier ou dans un PDF
DEVISES_CONNUES = sorted({v[0].upper() for v in PLACES_COTATION.values()}
                         | {"EUR", "USD", "GBX", "GBP", "ZAR", "ILS", "HUF", "CNH", "AED", "SAR"})


def suffixe(ticker):
    """« 005930.KS » -> « .KS » ; « AAPL » -> « » (États-Unis)."""
    ticker = str(ticker)
    return ticker[ticker.rfind("."):].upper() if "." in ticker else ""


def devise(ticker):
    """Devise de cotation probable d'après la place (règle de repli, sans Internet)."""
    s = suffixe(ticker)
    if s in PLACES_COTATION:
        return PLACES_COTATION[s][0]
    return PLACES_SECONDAIRES.get(s, "EUR")


def pays_region(ticker):
    """(pays, région) de la place de cotation ; ("", "") si inconnue ou secondaire."""
    s = suffixe(ticker)
    if s in PLACES_COTATION:
        return PLACES_COTATION[s][1], PLACES_COTATION[s][2]
    return "", ""


def suffixes_par_pays_isin():
    """{« KR » : [« .KS »], « FR » : [« .PA »]…} : places à essayer pour un ISIN de ce pays."""
    table = {}
    for s, (_, _, _, prefixes) in PLACES_COTATION.items():
        for p in prefixes:
            table.setdefault(p, []).append(s)
    return table

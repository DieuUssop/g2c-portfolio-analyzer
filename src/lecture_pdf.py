"""
lecture_pdf.py — Lecture d'un avis d'opéré PDF par son CONTENU, quel que soit le courtier.

Les intitulés changent d'un courtier à l'autre (« Quantité : », « Nombre de titres »,
« Qté », « Buy 15 … at 85.12 »…), mais tout avis d'opéré contient les mêmes choses :

    - un code ISIN (reconnu à coup sûr grâce à sa clé de contrôle) ;
    - une date d'exécution ;
    - trois nombres liés par  quantité × cours = montant brut  (au centime près),
      et souvent  montant brut ± frais = montant net ;
    - un mot qui donne le sens (achat, vente, buy, sell, dividende…).

Ce module repère ces éléments sans se fier à la mise en page. Il sert :
    1. de seconde lecture quand la lecture par intitulés (import_fichier.lire_avis_opere)
       ne trouve rien ;
    2. à proposer, si rien n'est sûr, un formulaire pré-rempli (src/vues_pdf.py) avec les
       dates, codes et nombres trouvés : l'utilisateur choisit, rien n'est inventé.
"""

import bisect
import itertools
import re
import unicodedata

import pandas as pd

from . import import_fichier as imp

# ----------------------------------------------------------------------
# 1. Texte « codé » : il s'affiche bien, mais l'extraction donne du charabia
# ----------------------------------------------------------------------
MOTS_COURANTS = re.compile(r"\b(?:le|la|les|de|des|du|et|en|au|date|cours|quantit|montant|frais|total|achat|vente|"
                           r"valeur|the|of|and|to|in|price|buy|sell|value|eur|usd)\w*", re.IGNORECASE)


def date_plausible(date):
    """Une date d'opération ne peut pas être dans le futur (ni avant 1990) : « 28/09/2028 » lu à la
    place de « 28/09/2026 » sur une image est refusé, et le formulaire prend le relais."""
    import datetime
    jour = pd.to_datetime(str(date or "").replace(".", "/").replace("-", "/"), dayfirst=True, errors="coerce")
    if pd.isna(jour):
        return True                               # format inconnu : on ne bloque pas ici
    return pd.Timestamp("1990-01-01") <= jour <= pd.Timestamp(datetime.date.today()) + pd.Timedelta(days=1)


def texte_illisible(texte):
    """Vrai si le texte extrait d'un PDF est inutilisable : glyphes sans correspondance
    « (cid:12) », caractères de contrôle ou privés, ou aucun mot courant."""
    brut = (texte or "").strip()
    if len(brut) < 20:
        return False                         # pas de texte du tout : c'est un scan, traité à part
    if brut.count("(cid:") >= 5:
        return True
    visibles = [c for c in brut if not c.isspace()]
    etranges = sum(1 for c in visibles if unicodedata.category(c) in ("Cc", "Co", "Cn", "Cs") or c == "�")
    if etranges > 0.15 * len(visibles):
        return True
    lettres = sum(c.isalpha() for c in visibles)
    if lettres < 0.25 * len(visibles):
        return True
    return len(brut) > 80 and len(MOTS_COURANTS.findall(brut)) < 2


# ----------------------------------------------------------------------
# 2. Dates (chiffres ou mois en lettres, français ou anglais)
# ----------------------------------------------------------------------
MOIS = {
    "janvier": 1, "janv": 1, "jan": 1, "january": 1, "fevrier": 2, "fevr": 2, "fev": 2, "feb": 2, "february": 2,
    "mars": 3, "mar": 3, "march": 3, "avril": 4, "avr": 4, "apr": 4, "april": 4, "mai": 5, "may": 5,
    "juin": 6, "jun": 6, "june": 6, "juillet": 7, "juil": 7, "jul": 7, "july": 7, "aout": 8, "aug": 8,
    "august": 8, "septembre": 9, "sept": 9, "sep": 9, "september": 9, "octobre": 10, "oct": 10, "october": 10,
    "novembre": 11, "nov": 11, "november": 11, "decembre": 12, "dec": 12, "december": 12,
}
_MOIS = "|".join(sorted(MOIS, key=len, reverse=True))
MOTIF_DATES = re.compile(
    r"(?<![\d.])(?:(?P<j>\d{1,2})[/.\-](?P<m>\d{1,2})[/.\-](?P<a>\d{4})(?!\d)"
    r"|(?P<j5>\d{2})(?P<sep>[/.\-])(?P<m5>\d{2})(?P=sep)(?P<a5>\d{2})(?![\d.,])"
    r"|(?P<a2>\d{4})-(?P<m2>\d{2})-(?P<j2>\d{2})(?!\d)"
    rf"|(?P<j3>\d{{1,2}})(?:er)?[\s\-]+(?P<m3>{_MOIS})\.?[\s\-]+(?P<a3>\d{{4}})"
    rf"|(?P<m4>{_MOIS})\.?\s+(?P<j4>\d{{1,2}}),?\s+(?P<a4>\d{{4}}))",
    re.IGNORECASE)
MOTS_EXECUTION = re.compile(r"(?:ex[ée]cut\w*|n[ée]goci\w*|trade\s*date|transaction\s*date|date\s*d['’]\s*op[ée]r\w*|"
                            r"date\s*de\s*l['’]\s*op[ée]r\w*|date\s*de\s*paiement|pay(?:ment|able)\s*date|"
                            r"achat\s*le|vente\s*le|kauf\s*am|verkauf\s*am|ausf[üu]hrung\w*|ausgef[üu]hrt|"
                            r"handelstag|schlusstag|handelsdatum|handelszeit|trade[\s\-]*datum|trade\s*time|uitvoering|transactiedatum|trade\s*on|executed\s*on|"
                            r"data\s*(?:di\s*)?(?:esecuzione|operazione)|fecha\s*(?:de\s*)?(?:ejecuci[óo]n|operaci[óo]n))"
                            r"[^\n\d]{0,30}$", re.IGNORECASE)
MOTS_DATE_ECARTEE = re.compile(r"(?:[ée]dit\w*|[ée]mi[st]\w*|imprim\w*|r[èe]glement|settlement|livraison|"
                               r"value\s*date|date\s*de\s*valeur|valeur\s*:?|arr[êe]t[ée]\s*au|valuta\w*|zahltag|"
                               r"generiert\s*um|berichtszeitraum|generated\s*at|reporting\s*period|"
                               r"boekingsdatum|gedownload\s*op|beschikbaar\s*sinds|transmission|^\s*au|"
                               r",\s*le|^\s*le)[^\n\d]{0,25}$", re.IGNORECASE)


def _sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c)).lower()


def _plat(texte):
    """Même texte, même longueur, sans accents (« décembre » -> « decembre ») : les positions
    trouvées dans la copie valent pour l'original."""
    return "".join((unicodedata.normalize("NFKD", c)[:1] or c) if len(unicodedata.normalize("NFKD", c)[:1]) == 1
                   else c for c in texte)


def dates(texte):
    """[(date « JJ/MM/AAAA », début, fin, contexte avant)] dans l'ordre du texte."""
    trouvees = []
    for m in MOTIF_DATES.finditer(_plat(texte)):
        g = m.groupdict()
        try:
            if g["j"]:
                j, mo, a = int(g["j"]), int(g["m"]), int(g["a"])
            elif g["j5"]:
                j, mo, a = int(g["j5"]), int(g["m5"]), int(g["a5"])
            elif g["a2"]:
                j, mo, a = int(g["j2"]), int(g["m2"]), int(g["a2"])
            elif g["j3"]:
                j, mo, a = int(g["j3"]), MOIS[_sans_accents(g["m3"]).rstrip(".")], int(g["a3"])
            else:
                j, mo, a = int(g["j4"]), MOIS[_sans_accents(g["m4"]).rstrip(".")], int(g["a4"])
        except (KeyError, ValueError):
            continue
        a = a + 2000 if a < 100 else a
        if not (1 <= j <= 31 and 1 <= mo <= 12 and 1990 <= a <= 2100):
            continue
        debut_ligne = texte.rfind("\n", 0, m.start()) + 1
        trouvees.append((f"{j:02d}/{mo:02d}/{a}", m.start(), m.end(), texte[debut_ligne:m.start()]))
    return trouvees


def date_execution(texte, ligne_operation=None):
    """La date d'exécution : celle qui suit un mot « exécution / négociation / trade date »,
    sinon celle de la ligne de l'opération, sinon la première qui n'est pas une date d'édition,
    de règlement ou de valeur."""
    toutes = dates(texte)
    for d, debut, fin, avant in toutes:
        execution = MOTS_EXECUTION.search(avant)
        ecartee = MOTS_DATE_ECARTEE.search(avant)
        # « Confirmation d'exécution d'ordre — Édité le 13/03 » : le mot le plus proche l'emporte
        if execution and not (ecartee and ecartee.start() > execution.start()):
            return d
    if ligne_operation:
        sur_la_ligne = dates(ligne_operation)
        if sur_la_ligne:
            return sur_la_ligne[0][0]
    for d, debut, fin, avant in toutes:
        if not MOTS_DATE_ECARTEE.search(avant):
            return d
    return toutes[0][0] if toutes else None


# ----------------------------------------------------------------------
# 3. Nombres (formats français et anglais, milliers séparés par des espaces)
# ----------------------------------------------------------------------
_ESPACES = "    "
# un pourcentage (« TVA 20,00 % ») n'est ni une quantité, ni un cours, ni un montant — sauf le cours
# d'une obligation (« 98,05 % » du nominal) : MOTIF_MORCEAU_POURCENT le garde. (?!\d|[.,']\d) empêche de
# couper « 98,05 % » en « 98 ».
MOTIF_MORCEAU = re.compile(r"(?<![\w.,/:])([+\-]?)(\d+(?:[.,']\d+)*)(?!\d|[.,']\d)(?![\w/:])(?!\s*%)")
MOTIF_MORCEAU_POURCENT = re.compile(r"(?<![\w.,/:])([+\-]?)(\d+(?:[.,']\d+)*)(?!\d|[.,']\d)(?![\w/:])")
LIGNES_SANS_MONTANT = re.compile(r"compte|account|client|n°|num[ée]ro|r[ée]f[ée]rence|reference|order\s*id|"
                                 r"ordre\s*n|iban|bic|siren|siret|t[ée]l[ée]phone|phone|\bt[ée]l\b|\bfax\b|code\s*postal|"
                                 r"\brcs\b|capital\s*(?:social\s*)?de|§|\bnr\b\.?|\bhrb\b|trade\s*id|order-id|trade-id|"
                                 r"ust-?id|vat-?id|\bdepot\b|\bseite\b|\bpage\b|\bauftrag\b",
                                 re.IGNORECASE)


def _valeurs(texte_nombre):
    """Lectures possibles d'un nombre écrit : « 3,512 » = 3,512 (français) ou 3 512 (anglais)."""
    lectures = set()
    principal = imp.convertir_nombres(pd.Series([texte_nombre])).iloc[0]
    if principal == principal:
        lectures.add(round(abs(principal), 6))
    nu = texte_nombre.lstrip("+-")
    if re.fullmatch(r"\d{1,3},\d{3}", nu):                      # « 3,512 » : aussi 3 512 à l'anglaise
        lectures.add(float(nu.replace(",", "")))
    if re.fullmatch(r"\d{1,3}\.\d{3}", nu):                     # « 1.705 » : aussi 1 705 à l'allemande
        lectures.add(float(nu.replace(".", "")))
    return lectures


def nombres(texte):
    """Tous les nombres candidats du texte : [dict(valeur, debut, fin, ecrit, signe, ligne)].
    Les dates, heures, codes ISIN et numéros de compte sont écartés. Un nombre écrit avec des
    espaces (« 1 440,00 ») donne plusieurs candidats : « 1 440,00 » et « 1 » + « 440,00 » —
    la cohérence quantité × cours = montant tranchera."""
    obligation = bool(MOTS_OBLIGATION.search(texte))
    masque = list(texte)
    for d in dates(texte):
        masque[d[1]:d[2]] = " " * (d[2] - d[1])
    for m in re.finditer(r"[A-Z]{2}[A-Z0-9]{9}\d", texte):
        masque[m.start():m.end()] = " " * 12
    for m in re.finditer(r"\d{1,2}:\d{2}(?::\d{2})?", texte):
        masque[m.start():m.end()] = " " * (m.end() - m.start())
    # numéros (compte, référence, téléphone, RCS…) : seul le numéro qui suit le mot est écarté,
    # pas toute la ligne (« 29/09/2023 42 AM.PEA … Référence : 493029272303 » garde la quantité 42)
    for m in LIGNES_SANS_MONTANT.finditer(texte):
        suite = re.match(r"[ \t:°#.\-]{0,6}(\d[\d \t\-/.,]*)", texte[m.end():m.end() + 60])
        if suite:
            debut, fin = m.end() + suite.start(1), m.end() + suite.end(1)
            masque[debut:fin] = " " * (fin - debut)
    propre = "".join(masque)
    candidats = []
    debut_ligne = 0
    for ligne in propre.split("\n"):
        if True:
            morceaux = [m for m in (MOTIF_MORCEAU_POURCENT if obligation else MOTIF_MORCEAU).finditer(ligne)]
            for i, m in enumerate(morceaux):
                # le morceau seul, puis regroupé avec les suivants séparés par une espace (milliers)
                groupe, fin = m.group(2), m.end()
                suites = [(groupe, fin)]
                if re.fullmatch(r"\d{1,3}", groupe):
                    for suivant in morceaux[i + 1:]:
                        entre = ligne[fin:suivant.start()]
                        if suivant.group(1) or not entre or entre.strip(_ESPACES) or len(entre) > 2 or \
                                not re.fullmatch(r"\d{3}(?:[.,]\d+)?", suivant.group(2)):
                            break
                        groupe, fin = groupe + suivant.group(2), suivant.end()
                        suites.append((groupe, fin))
                        if not re.fullmatch(r"\d+", groupe):
                            break
                for ecrit, fin_ecrit in suites:
                    if len(re.sub(r"\D", "", ecrit)) >= 9 and not re.search(r"[.,]", ecrit):
                        continue                                 # identifiant, pas un montant
                    for valeur in _valeurs(m.group(1) + ecrit):
                        if valeur > 0:
                            candidats.append({"valeur": valeur, "debut": debut_ligne + m.start(),
                                              "fin": debut_ligne + fin_ecrit, "ecrit": m.group(1) + ecrit,
                                              "signe": m.group(1), "ligne": ligne.strip()})
        debut_ligne += len(ligne) + 1
    return candidats


# ----------------------------------------------------------------------
# 4. Le trio quantité × cours = montant
# ----------------------------------------------------------------------
MOTS_QUANTITE = re.compile(r"quantit|qt[ée]|nombre|titres?\b|parts?\b|actions?\b|shares?\b|units?\b|nominal|"
                           r"buy|sell|bought|sold|achat|vente|stk\b|st[üu]ck|anzahl|cantidad|quantit[àa]|"
                           r"t[íi]tulos|aandelen|menge\b|nominale", re.IGNORECASE)
MOTS_COURS = re.compile(r"cours|prix|price|\bat\b|@|unitaire|dividende\s*unitaire|par\s*action|kurs|preis|"
                        r"valeur\s*liquidative|\bvl\b|\bnav\b|"
                        r"precio|prezzo|koers", re.IGNORECASE)
MOTS_BRUT = re.compile(r"brut|gross|value|valeur|montant|amount|total|consideration|kurswert|betrag|importe|"
                       r"controvalore|bedrag|wert\b", re.IGNORECASE)
MOTS_FRAIS = re.compile(r"courtage|commission|frais|fees?|costs?|brokerage|ttf|taxe\s*sur\s*les\s*transactions|"
                        r"transactions\s*financi[eè]res|stamp\s*duty|provision|geb[üu]hr|entgelt|"
                        r"fremdkosten|kosten|comisi[óo]n|commissioni|spese|transactiekosten|beurstaks|makelaarsloon|"
                        r"droits?\s*(?:d['’]\s*)?entr[ée]e", re.IGNORECASE)
MOTS_NET = re.compile(r"\bnet|total|d[ée]bit|cr[ée]dit|à\s*payer|to\s*pay|settlement\s*amount|gesamt|"
                      r"ausmachender\s*betrag|zu\s*lasten|zu\s*gunsten|endbetrag|importe\s*neto|netto", re.IGNORECASE)


def _contexte(texte, candidat, avant=28):
    """Les derniers caractères avant le nombre, sur la même ligne."""
    debut = max(0, candidat["debut"] - avant, texte.rfind("\n", 0, candidat["debut"]) + 1)
    return texte[debut:candidat["debut"]]


def _ligne_au_dessus(texte, candidat):
    debut = texte.rfind("\n", 0, candidat["debut"])
    return texte[texte.rfind("\n", 0, max(0, debut)) + 1:max(0, debut)] if debut > 0 else ""


def _se_chevauchent(*candidats):
    zones = sorted((c["debut"], c["fin"]) for c in candidats)
    return any(a[1] > b[0] for a, b in zip(zones, zones[1:]))


def trio(texte, candidats=None):
    """Meilleur trio (quantité, cours, montant brut, frais, montant net) ou None (voir trios)."""
    liste = trios(texte, candidats)
    return liste[0] if liste else None


MOTS_OBLIGATION = re.compile(r"obligation|\bbond\b|anleihe|nominal|nominale|\bo\.?a\.?t\b|emprunt|treasury|"
                             r"bund\b|bono\b|obbligazion|% du pair|clean price|dirty price", re.IGNORECASE)
MOTS_COUPON_COURU = re.compile(r"coupons?\s*cour(?:u|us)|int[ée]r[êe]ts?\s*cour(?:u|us)|st[üu]ckzins\w*|"
                               r"accrued\s*interest|bond\s*accrued|rateo|cup[óo]n\s*corrido|opgelopen\s*rente",
                               re.IGNORECASE)


def _cours_en_pourcentage(texte, q, p, obligation):
    """Le cours est-il un pourcentage du nominal (obligation) ? Oui s'il est suivi de « % », ou si
    le document parle d'obligation et que le nominal (quantité) est rond et le cours proche du pair."""
    if re.match(r"\s*%", texte[p["fin"]:p["fin"] + 3]):
        return True
    return obligation and q["valeur"] >= 100 and float(q["valeur"]).is_integer() and 1 <= p["valeur"] <= 250


def _tolerance(q, p, produit):
    """Écart admis entre quantité × cours et le montant : un centime ; pour une quantité
    fractionnée (« 5,0721 × 108,7 = 551,35 ») ou un cours à 3 décimales et plus, le cours affiché
    est arrondi et l'écart peut atteindre quantité × un demi-dernier chiffre du cours (au plus
    0,2 % du montant)."""
    tolerance = 0.0101
    decimales_q = len(re.split(r"[.,]", q["ecrit"])[-1]) if re.search(r"[.,]\d+$", q["ecrit"]) else 0
    ecrit = p["ecrit"].replace(" ", "")
    decimales = len(re.split(r"[.,]", ecrit)[-1]) if re.search(r"[.,]\d+$", ecrit) else 0
    # quantité fractionnée, ou cours à 3 décimales ou plus (« 700 × 32,795 ») : le cours affiché
    # peut lui-même être arrondi (cours moyen de plusieurs exécutions)
    if (not float(q["valeur"]).is_integer() and decimales_q >= 3) or \
            (float(q["valeur"]).is_integer() and decimales >= 3 and q["valeur"] >= 10):
        arrondi = q["valeur"] * 0.5 * 10 ** (-decimales) + 0.0051
        if decimales_q >= 3 and not float(q["valeur"]).is_integer():
            arrondi += p["valeur"] * 0.5 * 10 ** (-decimales_q)   # parts de fonds arrondies (« 19,989 »)
        tolerance = max(tolerance, min(arrondi, 0.002 * produit))
    return tolerance


def trios(texte, candidats=None, nombre=6):
    """Trios (quantité, cours, montant brut, frais, montant net) cohérents, du plus probable au
    moins probable (au plus `nombre`, valeurs distinctes).

    quantité × cours doit retomber sur un autre nombre du texte au centime près (montant brut),
    ou, à défaut, sur montant net ∓ frais. Le score favorise une quantité entière, un cours et
    une quantité placés près de leurs intitulés, et un montant net cohérent avec les frais.
    Les suivants servent à départager avec les cours du marché (arbitrer_par_le_marche)."""
    candidats = candidats if candidats is not None else nombres(texte)
    uniques = {}
    for c in candidats:
        uniques.setdefault((c["valeur"], c["debut"], c["fin"]), c)
    candidats = list(uniques.values())
    par_valeur = {}
    for c in candidats:
        par_valeur.setdefault(round(c["valeur"], 2), []).append(c)
    cles = sorted(par_valeur)
    trouves = []
    petits = [c for c in candidats if c["valeur"] < 1e7]
    obligation = bool(MOTS_OBLIGATION.search(texte))
    for q, p in itertools.permutations(petits, 2):
        if _se_chevauchent(q, p) or q["valeur"] > 1e6:
            continue
        produit = q["valeur"] * p["valeur"]
        # obligation : nominal × cours en % du pair / 100 = montant brut (hors coupon couru) ;
        # la quantité retenue est le nominal / 100 (une « part » de 100 de nominal), pour que
        # quantité × cours = montant reste vrai dans le portefeuille
        variantes = [(1.0, produit)]
        if _cours_en_pourcentage(texte, q, p, obligation):
            variantes.append((0.01, produit / 100))
        for facteur, attendu in variantes:
            if attendu < 0.001:
                continue
            if facteur == 1:
                tolerance = _tolerance(q, p, attendu)
            else:                                 # obligation : seul l'arrondi d'un cours à 3 décimales et plus
                decimales_p = len(re.split(r"[.,]", p["ecrit"])[-1]) if re.search(r"[.,]\d+$", p["ecrit"]) else 0
                tolerance = 0.0101 + (q["valeur"] * facteur * 0.5 * 10 ** -decimales_p if decimales_p >= 3 else 0)
            debut = bisect.bisect_left(cles, attendu - tolerance - 0.005)
            fin = bisect.bisect_right(cles, attendu + tolerance + 0.005)
            cibles = [b for cle in cles[debut:fin] for b in par_valeur[cle]]
            for b in cibles:
                if b is q or b is p or _se_chevauchent(q, p, b) or abs(b["valeur"] - attendu) > tolerance:
                    continue
                if q["valeur"] == 1 and p["valeur"] == b["valeur"] and not MOTS_QUANTITE.search(_contexte(texte, q)) \
                        and not UNITES_QUANTITE.match(texte[q["fin"]:q["fin"] + 12]) \
                        and not re.search(r"quantit|anzahl|quantity|cantidad", _ligne_au_dessus(texte, q), re.IGNORECASE):
                    continue                      # 1 × x = x : coïncidence, sauf « Quantité : 1 », « 1 Stk. »
                if p["valeur"] == 1 and q["valeur"] == b["valeur"] and not MOTS_COURS.search(_etiquette(texte, p)):
                    continue                      # x × 1 = x : idem
                score = _score_trio(texte, q, p, b)
                if facteur != 1:
                    score += 3 if re.match(r"\s*%", texte[p["fin"]:p["fin"] + 3]) else 1
                frais, net, coupon = _frais_et_net(texte, candidats, b, (q, p), avec_coupon=True)
                score += 3 if net is not None else 0
                trouves.append((score, {"quantite": q, "cours": p, "brut": b, "frais": frais, "net": net,
                                        "facteur": facteur, "coupon": coupon}))
    if not trouves:
        # Pas de montant brut écrit : quantité × cours ± frais = montant net
        frais_etiquetes = [c for c in candidats if MOTS_FRAIS.search(_contexte(texte, c))]
        for q, p in itertools.permutations(petits, 2):
            if _se_chevauchent(q, p):
                continue
            if q["valeur"] == 1 and not MOTS_QUANTITE.search(_contexte(texte, q)) \
                    and not UNITES_QUANTITE.match(texte[q["fin"]:q["fin"] + 12]):
                continue
            if p["valeur"] == 1 and not MOTS_COURS.search(_etiquette(texte, p)):
                continue
            produit = q["valeur"] * p["valeur"]
            for f in frais_etiquetes:
                if f is q or f is p:
                    continue
                for total in (produit + f["valeur"], produit - f["valeur"]):
                    for n in par_valeur.get(round(total, 2), []):
                        if n in (q, p, f) or _se_chevauchent(q, p, n) or abs(n["valeur"] - total) > 0.0101:
                            continue
                        trouves.append((_score_trio(texte, q, p, n), {"quantite": q, "cours": p, "brut": None,
                                                                      "frais": f["valeur"], "net": n["valeur"],
                                                                      "facteur": 1.0, "coupon": None}))
    trouves.sort(key=lambda x: -x[0])
    resultat, vus = [], set()
    for score, t in trouves:
        cle = (round(t["quantite"]["valeur"] * t.get("facteur", 1), 6), round(t["cours"]["valeur"], 6))
        if cle in vus:
            continue
        vus.add(cle)
        resultat.append(dict(t, score=score))
        if len(resultat) >= nombre:
            break
    return resultat


MOTS_CHANGE = re.compile(r"change|taux|rate|fx\b|devise|wechselkurs|devisenkurs|umrechnungs\w*|kurs\s*eur", re.IGNORECASE)


UNITES_QUANTITE = re.compile(r"\s*(?:stk\b|st[üu]ck|titres?\b|titre\(s\)|parts?\b|actions?\b|shares?\b|units?\b|"
                             r"pcs\b|pi[èe]ces?\b|pz\b|t[íi]t\b|uds?\b|droits?\b|bons?\b|x\s)", re.IGNORECASE)
APRES_DEVISE = re.compile(r"\s*(?:EUR|USD|GBP|GBX|CHF|JPY|CAD|AUD|HKD|DKK|SEK|NOK|€|\$|£|%)", re.IGNORECASE)


def _etiquette(texte, candidat, avant=28):
    """Le texte entre le nombre précédent de la ligne et ce nombre : son intitulé propre."""
    return re.split(r"\d", _contexte(texte, candidat, avant))[-1]


def _score_trio(texte, q, p, b):
    score = 0.0
    q_unite = bool(UNITES_QUANTITE.match(texte[q["fin"]:q["fin"] + 12]))
    if float(q["valeur"]).is_integer():
        score += 2
    # un taux de change n'est ni une quantité ni un cours ; un trio de tout petits nombres est du bruit
    if MOTS_CHANGE.search(_contexte(texte, q, 40) + " " + _ligne_au_dessus(texte, q)) and not \
            float(q["valeur"]).is_integer() and not q_unite:
        score -= 6
    if len(re.sub(r"\D", "", q["ecrit"].split(",")[-1].split(".")[-1])) >= 5 and not float(q["valeur"]).is_integer() \
            and not q_unite:
        score -= 2
    if b["valeur"] < 20:
        score -= 3
    if re.search(r"[.,]\d{4,}$", b["ecrit"]):
        score -= 4                                # « 25,007144 » : une quantité, pas un montant
    if all(float(c["valeur"]).is_integer() and not re.search(r"[.,]\d", c["ecrit"]) for c in (q, p, b)) \
            and (b["valeur"] < 100 or not any(APRES_DEVISE.match(texte[c["fin"]:c["fin"] + 5]) for c in (p, b))):
        score -= 3                                # « § 4 Nr. 8 » … 32 : des entiers isolés, pas une opération
    if p["valeur"] == 1 and not re.search(r"[.,]\d", p["ecrit"]):
        score -= 10                               # « 10119 × 1 = 10119 » : un cours de 1 sans décimales
    elif p["valeur"] == 1 and not MOTS_COURS.search(_etiquette(texte, p)):
        score -= 3                                # un cours de 1 : c'est la quantité qui est 1
    # « 0,4534 Stk. », « 3 titre(s) » : l'unité suit la quantité ; « 55,13 EUR » : la devise suit le cours
    if q_unite:
        score += 4
    elif MOTS_QUANTITE.search(_etiquette(texte, q)):
        score += 2
    if APRES_DEVISE.match(texte[q["fin"]:q["fin"] + 5]) and not q_unite:
        score -= 2
    if UNITES_QUANTITE.match(texte[p["fin"]:p["fin"] + 12]):
        score -= 4
    if MOTS_COURS.search(_etiquette(texte, p)):
        score += 2
    if MOTS_BRUT.search(_etiquette(texte, b)):
        score += 1
    if MOTS_FRAIS.search(_etiquette(texte, q) + " " + _etiquette(texte, p)):
        score -= 4
    if q["ligne"] == p["ligne"] == b["ligne"]:
        score += 1
    # quantité avant le cours avant le montant : l'ordre habituel d'une ligne d'opération
    if q["debut"] < p["debut"] < b["debut"]:
        score += 0.5
    return score


def _frais_etiquete(texte, c, brut):
    """Nombre annoncé par un mot de frais (« courtage : 1,95 ») : le mot est entre le nombre
    précédent de la ligne et celui-ci, et le montant reste petit devant le brut."""
    contexte = _contexte(texte, c, 45)
    if re.search(r"\b(?:tva|vat|mwst|iva)\b[ \t:]*\d+(?:[.,]\d+)?[ \t]*%[^\d]*$", contexte, re.IGNORECASE) \
            and re.search(r"[.,]\d", c["ecrit"]) and 0 < abs(c["valeur"]) < 0.1 * abs(brut["valeur"]):
        return True                               # « TVA 20,00% EUR 0,17 » : la TVA sur les frais
    contexte = re.sub(r"\d+(?:[.,]\d+)?\s*%", " ", contexte)      # « Beurstaks - 0,12% - 4,28 »
    contexte = re.split(r"\d", contexte)[-1]
    return bool(MOTS_FRAIS.search(contexte)) and 0 < abs(c["valeur"]) < 0.1 * abs(brut["valeur"])


def _coupon_couru(texte, candidats, brut, exclus=()):
    """Coupon couru d'une obligation (« Stückzinsen -75,25 », « Bond Accrued Interest … -30,82 ») :
    nombre annoncé par son intitulé, sur sa ligne ou sur la ligne au-dessus. None s'il n'y en a pas."""
    for c in candidats:
        if c is brut or c in exclus or _se_chevauchent(c, brut) or not re.search(r"[.,]\d", c["ecrit"]):
            continue
        if MOTS_COUPON_COURU.search(_etiquette(texte, c, 45)) or \
                (MOTS_COUPON_COURU.search(_ligne_au_dessus(texte, c)) and not re.search(r"\d[.,]\d", _ligne_au_dessus(texte, c))):
            if 0 < abs(c["valeur"]) < 0.2 * abs(brut["valeur"]):
                return abs(c["valeur"])
    return None


def _frais_et_net(texte, candidats, brut, exclus=(), avec_coupon=False, ecart=True):
    """Frais : nombres précédés de « courtage, commission, frais, costs… » ; montant net : un
    nombre égal à brut ± frais. Si aucun frais n'est écrit, un écart brut/net plausible (< 5 %)
    entre deux nombres sert de frais.
    avec_coupon : obligation ; le coupon couru (payé au vendeur, rendu au prochain coupon) n'est
    pas un frais, mais il entre dans le montant net : net = brut ± frais ± coupon couru. Renvoie
    alors (frais, net, coupon couru)."""
    if avec_coupon:
        coupon = _coupon_couru(texte, candidats, brut, exclus)
        if coupon:
            exclus = tuple(exclus) + tuple(c for c in candidats if abs(abs(c["valeur"]) - coupon) < 0.001)
        frais, net = _frais_et_net(texte, candidats, brut, exclus, ecart=not coupon)
        if coupon and net is None:
            for c in candidats:
                if c is brut or c in exclus or _se_chevauchent(c, brut):
                    continue
                f = frais or 0.0
                for total in (brut["valeur"] + f + coupon, brut["valeur"] - f + coupon, brut["valeur"] - f - coupon):
                    if abs(abs(c["valeur"]) - total) < 0.011:
                        return frais, abs(c["valeur"]), coupon
        return frais, net, coupon
    etiquetes = [c for c in candidats if c is not brut and c not in exclus and _frais_etiquete(texte, c, brut)
                 and not _se_chevauchent(c, brut)]
    if not etiquetes:
        # « Commission Frais divers Montant total des frais » puis, dessous, « 6,95 EUR 0,00 EUR 6,95 EUR » :
        # le total des frais est le dernier nombre de la ligne de valeurs
        for c in candidats:
            dessus = _ligne_au_dessus(texte, c)
            fin_ligne = texte.find("\n", c["fin"])
            reste = texte[c["fin"]:fin_ligne if fin_ligne >= 0 else len(texte)]
            if re.search(r"total\s*(?:des\s*)?(?:frais|fees|costs|kosten)\s*$", dessus.strip(), re.IGNORECASE) \
                    and not re.search(r"\d", reste) and c is not brut and c not in exclus \
                    and 0 < c["valeur"] < 0.1 * abs(brut["valeur"]):
                etiquetes = [c]
                break
    vus, frais = set(), 0.0
    for c in etiquetes:
        if c["debut"] in vus:
            continue
        vus.add(c["debut"])
        frais += c["valeur"]
    for c in candidats:
        if c is brut or _se_chevauchent(c, brut) or c in exclus:
            continue
        for total in (brut["valeur"] + frais, brut["valeur"] - frais) if frais else ():
            if abs(c["valeur"] - total) < 0.011:
                return round(frais, 2), c["valeur"]
    if not frais and ecart:
        valeurs = {round(c["valeur"], 2) for c in candidats}
        for c in candidats:
            ecart = abs(c["valeur"] - brut["valeur"])
            if c is brut or c in exclus or _se_chevauchent(c, brut) or not 0 < ecart < 0.05 * brut["valeur"]:
                continue
            # montant net reconnu à son intitulé (sur sa ligne ou sur la ligne de titres au-dessus),
            # ou parce que l'écart brut / net est lui-même écrit (les frais)
            devise_b = MOTIF_DEVISE.match(texte[brut["fin"]:brut["fin"] + 5].strip() or "-")
            devise_c = MOTIF_DEVISE.match(texte[c["fin"]:c["fin"] + 5].strip() or "-")
            if devise_b and devise_c and devise_b.group(0) != devise_c.group(0):
                continue                          # 200,40 USD et 195,13 EUR : l'écart n'est pas un frais
            if MOTS_NET.search(_contexte(texte, c, 30)) or MOTS_NET.search(_ligne_au_dessus(texte, c)) \
                    or round(ecart, 2) in valeurs:
                return round(ecart, 2), c["valeur"]
    return (round(frais, 2) if frais else None), None


# ----------------------------------------------------------------------
# 5. Une opération par code ISIN
# ----------------------------------------------------------------------
MOTIF_SENS = re.compile(r"(?:(?<=order)|(?<![a-zà-ÿ]))(rachat|achat|vente|souscription|buy|sell|bought|sold|kauf|verkauf|"
                        r"zeichnung|compra|venta|acquisto|vendita|aankoop|verkoop|sparplan|savings\s*plan|round\s*up|saveback|"
                        r"reprise\s+(?:sicav|f\.?\s?c\.?\s?p\b\.?|opc\w*)|"
                        r"investissement\s*programm[ée]|piano\s*d['’i]\s*investimento|plan\s*de\s*inversi[óo]n|"
                        r"dividende|dividend|dividendo|aussch[üu]ttung|coupon|distribution)", re.IGNORECASE)
MOTIF_DEVISE = re.compile(r"(?<![A-Z])(EUR|USD|GBP|GBX|CHF|JPY|CAD|AUD|HKD|DKK|SEK|NOK)(?![A-Z])|(€|\$|£)")
SYMBOLES = {"€": "EUR", "$": "USD", "£": "GBP"}


def isins(texte):
    """Codes ISIN valides et réalistes, dans l'ordre : [(isin, position)]."""
    vus, liste = set(), []
    for m in imp.MOTIF_ISIN_TEXTE.finditer(texte):
        code = m.group(1)
        if imp.isin_plausible(code):
            liste.append((code, m.start()))
            vus.add(code)
    return liste


def _segments(texte):
    """Découpe le texte en une zone par opération. Un seul ISIN (même répété) : tout le texte.
    Plusieurs ISIN différents : chaque zone va du début de la ligne de son ISIN au début de la
    ligne de l'ISIN suivant."""
    trouves = isins(texte)
    distincts = list(dict.fromkeys(code for code, _ in trouves))
    if len(distincts) <= 1:
        return [(distincts[0] if distincts else None, texte, texte)]
    debuts = []
    fin_precedent = 0
    for code, position in trouves:
        if debuts and debuts[-1][0] == code:
            fin_precedent = position
            continue
        debut = texte.rfind("\n", 0, position) + 1
        # l'opération commence souvent avant la ligne de l'ISIN : « 22.03.2024 ACHAT COMPTANT »
        # puis « DE 3 ACTIONS ENGIE (FR0010208488) » ; on remonte à la dernière ligne qui commence
        # par une date, si elle suit le titre précédent
        for m in re.finditer(r"(?m)^[ \t]*\d{2}[./-]\d{2}[./-]\d{4}\b", texte[fin_precedent:debut]):
            debut_date = fin_precedent + m.start()
            if debuts and debut_date <= debuts[-1][1]:
                continue
            if trios(texte[debut_date:debut]):
                continue                          # ce bloc daté est complet : il appartient au titre précédent
            debut = min(debut, debut_date)
        if debuts and debut <= debuts[-1][1]:
            debut = texte.rfind("\n", 0, position) + 1
        debuts.append((code, debut))
        fin_precedent = position
    segments = []
    for i, (code, debut) in enumerate(debuts):
        fin = debuts[i + 1][1] if i + 1 < len(debuts) else len(texte)
        segments.append((code, texte[debut:fin], texte))
    return segments


def _sens(segment, isin):
    trouves = list(MOTIF_SENS.finditer(segment))
    if not trouves:
        return None
    position = segment.find(isin) if isin else 0
    # « Market-Order Kauf am 24.06.2026 » l'emporte sur « Dividend » écrit dans le nom du titre
    forts = [m for m in trouves if re.search(r"order[\s\-]*$", segment[max(0, m.start() - 8):m.start()], re.IGNORECASE)
             or re.match(r"\s+(?:am|le|on|el|il|du|of|vom)\s+\d", segment[m.end():m.end() + 9], re.IGNORECASE)]
    return min(forts or trouves, key=lambda m: abs(m.start() - position)).group(1)


def _devise(segment, cours):
    """Devise écrite juste après (ou juste avant) le cours, sinon la plus fréquente du texte."""
    apres = segment[cours["fin"]:cours["fin"] + 6] if cours else ""
    avant = segment[max(0, cours["debut"] - 5):cours["debut"]] if cours else ""
    for zone in (apres, avant):
        m = MOTIF_DEVISE.search(zone)
        if m:
            return m.group(1) or SYMBOLES[m.group(2)]
    # « COURS EN USD : 79,2 », « TX USD/EUR » : la devise de cotation d'origine, pas celle du cours lu
    ecartees = re.sub(r"(?:cours|price|kurs|prix)\s*(?:en|in)\s*[A-Z]{3}|[A-Z]{3}\s*/\s*[A-Z]{3}", " ", segment,
                      flags=re.IGNORECASE)
    toutes = [m.group(1) or SYMBOLES[m.group(2)] for m in MOTIF_DEVISE.finditer(ecartees)]
    return max(set(toutes), key=toutes.count) if toutes else ""


def _libelle(segment, isin):
    return re.sub(r"^(?:actions?|droits?|parts?|titres?|bons?)\s+", "", _libelle_brut(segment, isin), flags=re.IGNORECASE)


def _libelle_brut(segment, isin):
    nom = imp._nom_apres_isin(segment, isin) if isin else ""
    if nom and re.search(r"[A-Za-z]{2}", nom) and not re.match(r"^(?:at|@|\))", nom) and not dates(nom) \
            and not re.search(r":\s*[+\-]?\d", nom):
        return nom.strip(" ()")
    if isin:
        ligne = next((l for l in segment.splitlines() if isin in l), "")
        avant = ligne.split(isin)[0]
        avant = MOTIF_SENS.sub(" ", avant)
        avant = re.sub(r"\b(?:isin|code|valeur|titre|instrument)\b\s*:?|[():]|[+\-]?\d[\d\s.,]*", " ", avant,
                       flags=re.IGNORECASE)
        avant = re.sub(r"(?<!\w)[%/.,]+(?!\w)", " ", avant)          # « OAT 1,5 % 25/05/2031 » → « OAT »
        avant = re.sub(r"\s{2,}", " ", avant).strip(" -·")
        avant = re.sub(r"^(?:(?:de|du|des|d'|of|au|le|la|les|l')\s*)+", "", avant, flags=re.IGNORECASE).strip()
        if re.search(r"[A-Za-z]{2}", avant):
            return avant
    m = imp.MOTIFS_AVIS["libelle"].search(segment)
    return m.group(1).strip() if m else ""


def _executions(segment):
    """Un même titre exécuté en plusieurs fois (« Exécution fractionnée ») : chaque bloc qui
    commence par une date en début de ligne et contient son propre quantité × cours = montant
    devient une opération ; l'en-tête (nom, ISIN) est repris dans chaque bloc."""
    lignes = segment.split("\n")
    debuts = [i for i, l in enumerate(lignes) if re.match(r"\s*\d{2}[-/.]\d{2}[-/.]\d{4}\b", l)]
    if len(debuts) < 2:
        return [segment]
    tete = lignes[:debuts[0]]
    blocs = [lignes[a:b] for a, b in zip(debuts, debuts[1:] + [len(lignes)])]
    if not all(trios("\n".join(b)) for b in blocs):
        return [segment]
    return ["\n".join(tete + b) for b in blocs]


def lire_par_le_contenu(texte):
    """Opérations lues sans se fier aux intitulés : liste de dict(date, sens, isin, libelle,
    quantite, cours, devise, frais, montant, sur). « sur » est vrai si les quatre éléments
    essentiels sont trouvés (ISIN, date, trio cohérent, mot donnant le sens)."""
    operations = []
    for isin, segment, tout in [(i, b, t) for i, seg, t in _segments(texte) for b in _executions(seg)]:
        if not isin:
            continue
        ligne = next((l for l in segment.splitlines() if isin in l), "")
        date = date_execution(segment, ligne) or date_execution(tout, ligne)
        tous = trios(segment)
        t = tous[0] if tous else None
        deja = next((o for o in operations if o["isin"] == isin and o["sur"]), None)
        if not t and deja:
            # ligne à part pour le même titre (« TAXE TRANSACT FINANCIERES FR0000120271 TTF 1,45 ») :
            # une taxe de plus pour l'opération déjà lue, pas une nouvelle opération
            if re.search(r"tax|ttf|imp[oô]t|stamp|frais|fee", segment, re.IGNORECASE):
                montants = [c["valeur"] for c in nombres(segment) if re.search(r"[.,]\d", c["ecrit"])]
                if montants and deja["montant"] and montants[-1] < 0.05 * deja["montant"]:
                    deja["frais"] = round((deja["frais"] or 0) + montants[-1], 2)
            continue
        sens = _sens(segment, isin) or (_sens(tout, isin) if len(_segments(texte)) == 1 else None)
        if sens is None and t and t["quantite"]["signe"]:
            sens = "VENTE" if t["quantite"]["signe"] == "-" else "ACHAT"
        operations.append({
            "date": date, "sens": sens, "isin": isin, "libelle": _libelle(segment, isin)[:60],
            "quantite": float(t["quantite"]["valeur"]) * t.get("facteur", 1) if t else None,
            "cours": float(t["cours"]["valeur"]) if t else None,
            "devise": _devise(segment, t["cours"] if t else None),
            "frais": t["frais"] if t else None,
            "montant": (float(t["brut"]["valeur"]) if t and t["brut"] else (t["net"] if t else None)),
            "sur": bool(date and t and sens and date_plausible(date)),
            "net": t["net"] if t else None,
            "coupon_couru": t.get("coupon") if t else None,     # obligation : coupon couru payé (hors frais)
            "obligation": bool(t and t.get("facteur", 1) != 1),
            # autres lectures cohérentes, pour départager avec les cours du marché
            "alternatives": [{"quantite": float(a["quantite"]["valeur"]) * a.get("facteur", 1), "cours": float(a["cours"]["valeur"]),
                              "frais": a["frais"], "montant": float(a["brut"]["valeur"]) if a["brut"] else a["net"]}
                             for a in tous[1:]],
        })
        derniere = operations[-1]
        if sens and imp.classer_type(sens) == "DIVIDENDE":
            # dividende : montant brut et retenues (retenue à la source, prélèvements…), contrôlés
            # par brut − retenues − frais = net
            brut, retenues = imp._dividende_brut_et_retenues(segment, derniere["montant"], derniere["frais"])
            if brut is not None and brut != derniere["montant"]:
                derniere["montant"] = float(imp.convertir_nombres(pd.Series([brut])).iloc[0])
            derniere["frais"] = retenues or None
        if date and tous:
            # toutes les lectures cohérentes (la meilleure comprise), quelle que soit la lecture retenue
            ALTERNATIVES[(isin, date)] = [{"quantite": float(a["quantite"]["valeur"]) * a.get("facteur", 1), "cours": float(a["cours"]["valeur"]),
                                           "frais": a["frais"]} for a in tous]
    return operations


# Lectures alternatives des dernières opérations lues : (isin, date) -> [alternatives, quantité, cours]
ALTERNATIVES = {}


def arbitrer_par_le_marche(transactions, historique, isin_par_ticker, tolerance=0.15, proche=0.05):
    """Départage par les cours du marché : si le cours lu s'écarte de plus de 15 % du cours de
    clôture du jour de l'opération alors qu'une autre lecture cohérente du document (quantité ×
    cours = montant) tombe à moins de 5 % de ce cours, c'est cette autre lecture qui est retenue.
    Renvoie (transactions, notes)."""
    if historique is None or transactions is None or transactions.empty:
        return transactions, []
    t = transactions.copy()
    notes = []
    for i, ligne in t.iterrows():
        isin = isin_par_ticker.get(ligne["ticker"])
        if not isin or ligne["type"] not in ("ACHAT", "VENTE") or ligne["ticker"] not in historique.columns:
            continue
        date = pd.Timestamp(ligne["date"]).strftime("%d/%m/%Y")
        entree = ALTERNATIVES.get((isin, date))
        if not entree:
            continue
        cours_marche = imp._valeur_au(historique[ligne["ticker"]], pd.Timestamp(ligne["date"]))
        if not cours_marche or cours_marche != cours_marche:
            continue
        if abs(ligne["prix"] / cours_marche - 1) <= tolerance:
            continue
        meilleure = min(entree, key=lambda a: abs(a["cours"] / cours_marche - 1))
        if abs(meilleure["cours"] / cours_marche - 1) <= proche:
            t.at[i, "quantite"] = meilleure["quantite"]
            t.at[i, "prix"] = meilleure["cours"]
            if meilleure["frais"] is not None:
                t.at[i, "frais"] = meilleure["frais"]
            notes.append({"ticker": ligne["ticker"], "date": date, "ancien": float(ligne["prix"]),
                          "nouveau": meilleure["cours"], "marche": float(cours_marche)})
    return t, notes


def en_ligne_avis(operation):
    """dict -> ligne au format import_fichier.COLONNES_AVIS (textes)."""
    def nombre(x):
        return "" if x is None else f"{x:.6f}".rstrip("0").rstrip(".")
    sens = operation["sens"] or "ACHAT"
    quantite = operation["quantite"]
    return [operation["date"] or "", sens, operation["isin"], operation["libelle"] or operation["isin"],
            nombre(quantite), nombre(operation["cours"]), operation["devise"] or "",
            nombre(operation["frais"]) if operation["frais"] else "", nombre(operation["montant"])]


# ----------------------------------------------------------------------
# 6. Pour le formulaire de secours : tout ce qui a été trouvé
# ----------------------------------------------------------------------
def candidats(textes):
    """Ce que contient le document, pour pré-remplir le formulaire (src/vues_pdf.py) :
    dates, codes ISIN (avec un libellé), nombres (avec leur contexte), sens, devise,
    meilleure proposition, et le texte lu."""
    texte = "\n".join(textes)
    proposition = next(iter(lire_par_le_contenu(texte)), None)
    vus, liste_nombres = set(), []
    # « 5 650,20 » peut être 5 650,20 ou « 5 » puis « 650,20 » : toutes les lectures sont proposées
    for c in nombres(texte):
        cle = (c["ecrit"], c["debut"])
        if cle in vus or c["valeur"] == 0:
            continue
        vus.add(cle)
        contexte = re.sub(r"\s+", " ", (texte[max(0, c["debut"] - 30):c["debut"]] + "[" + c["ecrit"] + "]"
                                        + texte[c["fin"]:c["fin"] + 12]).replace("\n", " ")).strip()
        liste_nombres.append({"valeur": c["valeur"], "ecrit": c["ecrit"], "contexte": contexte})
    sens_trouve = MOTIF_SENS.search(texte)
    return {
        "dates": list(dict.fromkeys(d[0] for d in dates(texte))),
        "date_proposee": date_execution(texte),
        "isins": [(code, _libelle(texte, code)) for code in dict.fromkeys(c for c, _ in isins(texte))],
        "nombres": liste_nombres,
        "sens": imp.classer_type(sens_trouve.group(1)) if sens_trouve else None,
        "devise": _devise(texte, None) or "EUR",
        "proposition": proposition,
        "texte": texte,
    }


# ----------------------------------------------------------------------
# 7. Modèles appris : le formulaire complété une fois sert pour les avis suivants du même type
# ----------------------------------------------------------------------
# Un « modèle » retient, pour un type de document (reconnu à son vocabulaire), l'intitulé qui
# précède chaque information (« Nominal », « Qté exécutée », « Px moyen »…). Il ne contient
# aucun montant ni aucun nom en clair : le vocabulaire du document est gardé sous forme
# d'empreintes (hachage), et seuls les intitulés choisis sont lisibles.
SEUIL_MODELE = 0.6
MOTIF_CODE_SENS = re.compile(r"\b(sens|op[ée]ration|op\.|nature|type|side)\s*:?\s*([A-Za-z]{1,12})\b", re.IGNORECASE)
CHAMPS_MODELE = ("quantite", "cours", "frais", "montant")


def _fichier_modeles():
    from .base_titres import DOSSIER
    return DOSSIER / "modeles_pdf.json"


def _empreinte(texte):
    """Vocabulaire du document (mots de 3 lettres ou plus, sans chiffres), haché."""
    import hashlib
    mots = set(re.findall(r"[a-z]{3,}", _sans_accents(texte or "")))
    mots -= set(MOIS)
    return {hashlib.sha1(m.encode()).hexdigest()[:10] for m in mots}


def _ressemblance(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def charger_modeles():
    import json
    fichier = _fichier_modeles()
    try:
        return json.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else []
    except (OSError, ValueError):
        return []


def _enregistrer_modeles(modeles):
    import json
    fichier = _fichier_modeles()
    try:
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(json.dumps(modeles[-50:], ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass                                     # dossier en lecture seule : on n'apprend pas


def _mots_avant(ligne_avant):
    """Les (au plus) trois derniers mots avant une valeur : son intitulé."""
    mots = re.findall(r"[a-z]+", _sans_accents(ligne_avant))
    return " ".join(mots[-3:])


def _etiquette_de(texte, valeur):
    """Intitulé et rang de la valeur sur sa ligne (rang = nombre de valeurs entre l'intitulé et
    elle). Les écritures « entières » (« 3 251,00 ») sont préférées à leurs morceaux."""
    if valeur is None:
        return None
    possibles = [c for c in nombres(texte) if abs(c["valeur"] - abs(valeur)) <= max(0.0051, 1e-6 * abs(valeur))]
    if not possibles:
        return None
    c = max(possibles, key=lambda x: x["fin"] - x["debut"])
    debut_ligne = texte.rfind("\n", 0, c["debut"]) + 1
    avant = texte[debut_ligne:c["debut"]]
    # découper ce qui précède en « morceaux de mots » séparés par des nombres :
    # l'intitulé est le dernier morceau qui contient des mots ; le rang compte les nombres après lui
    morceaux = re.split(r"[+\-]?\d[\d\s.,']*", avant)
    for rang, morceau in enumerate(reversed(morceaux)):
        etiquette = _mots_avant(morceau)
        if etiquette:
            return {"etiquette": etiquette, "rang": rang}
    return None


def apprendre(texte, operation):
    """Retient le modèle d'un document après que l'utilisateur a complété le formulaire.
    operation : dict(date « JJ/MM/AAAA », type, quantite, cours, frais, montant)."""
    champs = {nom: _etiquette_de(texte, operation.get(nom)) for nom in CHAMPS_MODELE}
    champs = {k: v for k, v in champs.items() if v}
    if not champs.get("quantite") or not champs.get("cours"):
        return False                              # rien de réutilisable
    date = next((d for d in dates(texte) if d[0] == operation.get("date")), None)
    modele = {"empreinte": sorted(_empreinte(texte)), "champs": champs, "type": operation.get("type"),
              "date": _mots_avant(date[3]) if date else "", "sens": {}}
    # sens écrit en code (« Sens : A », « Op. : S ») : on retient la correspondance code -> type
    code = MOTIF_CODE_SENS.search(texte)
    if code and not MOTIF_SENS.search(texte) and operation.get("type"):
        modele["sens"] = {code.group(2).lower(): operation["type"]}
    anciens = [m for m in charger_modeles() if _ressemblance(set(m["empreinte"]), set(modele["empreinte"])) >= 0.85]
    for ancien in anciens:                       # garder les codes de sens déjà appris
        modele["sens"] = {**ancien.get("sens", {}), **modele["sens"]}
    modeles = [m for m in charger_modeles()
               if _ressemblance(set(m["empreinte"]), set(modele["empreinte"])) < 0.85]
    _enregistrer_modeles(modeles + [modele])
    return True


def _valeur_apres(texte, etiquette, rang):
    """La valeur qui suit l'intitulé (au rang donné) sur sa ligne, sinon la première de la ligne
    suivante."""
    lignes = texte.split("\n")
    for i, ligne in enumerate(lignes):
        plat = _sans_accents(ligne)
        mots = [(m.group(0), m.end()) for m in re.finditer(r"[a-z]+", plat)]
        cible = etiquette.split()
        for j in range(len(mots) - len(cible) + 1):
            if [w for w, _ in mots[j:j + len(cible)]] == cible:
                fin = mots[j + len(cible) - 1][1]
                apres = nombres(ligne[fin:])
                # écritures entières, dans l'ordre
                entieres = []
                for c in sorted(apres, key=lambda c: (c["debut"], -(c["fin"] - c["debut"]))):
                    if not entieres or c["debut"] >= entieres[-1]["fin"]:
                        entieres.append(c)
                if len(entieres) > rang:
                    return entieres[rang]["valeur"]
                if not entieres and i + 1 < len(lignes):
                    suivante = nombres(lignes[i + 1])
                    if suivante:
                        return suivante[0]["valeur"]
    return None


def lire_avec_modele(texte, modeles=None):
    """Opération lue avec le modèle appris le plus ressemblant (dict comme lire_par_le_contenu),
    ou None. Le résultat doit rester cohérent : quantité × cours = montant (à 1 % près) quand le
    modèle connaît l'intitulé du montant."""
    modeles = modeles if modeles is not None else charger_modeles()
    if not modeles:
        return None
    empreinte = _empreinte(texte)
    meilleur = max(modeles, key=lambda m: _ressemblance(set(m["empreinte"]), empreinte))
    if _ressemblance(set(meilleur["empreinte"]), empreinte) < SEUIL_MODELE:
        return None
    valeurs = {nom: _valeur_apres(texte, ch["etiquette"], ch["rang"]) for nom, ch in meilleur["champs"].items()}
    trouves = isins(texte)
    if not (trouves and valeurs.get("quantite") and valeurs.get("cours")):
        return None
    q, p, montant = valeurs["quantite"], valeurs["cours"], valeurs.get("montant")
    if montant and abs(q * p - montant) > 0.01 * montant + 0.011 and \
            abs(q * p + (valeurs.get("frais") or 0) - montant) > 0.011 and \
            abs(q * p - (valeurs.get("frais") or 0) - montant) > 0.011:
        return None
    date = None
    if meilleur.get("date"):
        for d in dates(texte):
            if _mots_avant(d[3]) == meilleur["date"]:
                date = d[0]
                break
    date = date or date_execution(texte)
    isin = trouves[0][0]
    sens = _sens(texte, isin)
    if not sens:
        code = MOTIF_CODE_SENS.search(texte)
        sens = meilleur.get("sens", {}).get(code.group(2).lower()) if code else meilleur.get("type")
        if not sens:
            return None                          # code de sens jamais vu : on redemande
    return {"date": date, "sens": sens, "isin": isin, "libelle": _libelle(texte, isin)[:60], "quantite": q,
            "cours": p, "devise": _devise(texte, None), "frais": valeurs.get("frais"),
            "montant": montant or round(q * p, 2), "sur": bool(date), "net": None, "alternatives": []}


# ----------------------------------------------------------------------
# 8. Position des mots : intitulés au-dessus des valeurs (colonnes sans traits de tableau)
# ----------------------------------------------------------------------
def _cellules(mots, ecart=7.0):
    """Mots d'une ligne -> cellules (mots proches regroupés) : [(x0, x1, texte)]."""
    cellules = []
    for m in sorted(mots, key=lambda m: m["x0"]):
        if cellules and m["x0"] - cellules[-1][1] <= ecart:
            x0, _, texte = cellules[-1]
            cellules[-1] = (x0, m["x1"], texte + " " + m["text"])
        else:
            cellules.append((m["x0"], m["x1"], m["text"]))
    return cellules


def texte_par_colonnes(mots):
    """À partir des mots d'une page et de leur position (pdfplumber.extract_words), écrit
    « intitulé : valeur » pour chaque valeur placée sous un intitulé : une ligne d'intitulés
    sans chiffres, suivie d'une ligne de valeurs alignées dessous. Ces lignes s'ajoutent au
    texte de la page pour la lecture par intitulés et par le contenu."""
    lignes = []
    for m in sorted(mots or [], key=lambda m: (round(m["top"]), m["x0"])):
        if lignes and abs(lignes[-1][0] - m["top"]) <= 3:
            lignes[-1][1].append(m)
        else:
            lignes.append([m["top"], [m]])
    paires = []
    for (_, haut), (_, bas) in zip(lignes, lignes[1:]):
        intitules, valeurs = _cellules(haut), _cellules(bas)
        if len(intitules) < 2 or len(valeurs) < 2 or any(re.search(r"\d", c[2]) for c in intitules):
            continue
        if not any(re.search(r"\d", c[2]) for c in valeurs):
            continue
        for x0, x1, valeur in valeurs:
            centre = (x0 + x1) / 2
            # l'intitulé qui recouvre le plus la valeur, sinon le plus proche à gauche
            recouvrement = [(min(x1, b) - max(x0, a), texte) for a, b, texte in intitules]
            meilleur = max(recouvrement)
            if meilleur[0] <= 0:
                gauche = [(centre - a, texte) for a, b, texte in intitules if a <= centre]
                if not gauche:
                    continue
                meilleur = (0, min(gauche)[1])
            paires.append(f"{meilleur[1]} : {valeur}")
    return "\n".join(paires)


# ----------------------------------------------------------------------
# 9. Contrôles après lecture
# ----------------------------------------------------------------------
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def controles(tableau_avis, transactions):
    """Points à vérifier après la lecture d'un PDF : liste de {"texte": modèle de phrase,
    "valeurs": {...}} (traduits à l'affichage).

    tableau_avis : lignes lues (colonnes import_fichier.COLONNES_AVIS), avec le montant écrit ;
    transactions : opérations obtenues (date, type, ticker, quantite, prix, frais)."""
    messages = []
    # 1. montant écrit = quantité × cours ± frais (à 1 % près)
    if tableau_avis is not None and "Montant" in getattr(tableau_avis, "columns", []):
        for _, l in tableau_avis.iterrows():
            q, c, f, m = imp.convertir_nombres(pd.Series([l.get("Quantité"), l.get("Cours"), l.get("Frais") or "0",
                                                          l.get("Montant")]))
            if any(v != v for v in (q, c, m)) or imp.classer_type(l.get("Sens", "")) == "DIVIDENDE":
                continue
            f = 0.0 if f != f else f
            brut = abs(q) * c
            if min(abs(m - brut), abs(m - brut - f), abs(m - brut + f)) > 0.01 * max(brut, 1) + 0.02:
                messages.append({"texte": "{isin} : le montant écrit ({montant}) ne correspond pas à quantité × cours "
                                          "± frais ({calcul}) : vérifiez la quantité et le cours.",
                                 "valeurs": {"isin": l.get("ISIN", ""), "montant": f"{m:.2f}",
                                             "calcul": f"{brut:.2f}"}})
    if transactions is None or transactions.empty:
        return messages
    for _, l in transactions.iterrows():
        date = pd.Timestamp(l["date"])
        # 2. jour sans bourse (samedi, dimanche) : souvent la date d'édition prise pour l'exécution
        if date.weekday() >= 5 and l["type"] in ("ACHAT", "VENTE"):
            messages.append({"texte": "{ticker} : opération datée d'un {jour} ({date}), jour sans bourse : vérifiez "
                                      "la date d'exécution.",
                             "valeurs": {"ticker": l["ticker"], "jour": JOURS[date.weekday()],
                                         "date": date.strftime("%d/%m/%Y")}})
        # 3. frais inhabituels (plus de 3 % du montant)
        brut = abs(l["quantite"]) * l["prix"]
        if l["type"] in ("ACHAT", "VENTE") and brut > 0 and l["frais"] > 0.03 * brut:
            messages.append({"texte": "{ticker} : frais de {frais} pour un montant de {montant} (plus de 3 %) : "
                                      "vérifiez les frais.",
                             "valeurs": {"ticker": l["ticker"], "frais": f"{l['frais']:.2f}", "montant": f"{brut:.2f}"}})
    # 4. même opération deux fois (plusieurs PDF, ou un avis en double dans le même fichier)
    cles = transactions[["date", "type", "ticker", "quantite", "prix"]].astype(str).agg("|".join, axis=1)
    for cle in cles[cles.duplicated()].unique():
        ticker, date = cle.split("|")[2], pd.Timestamp(cle.split("|")[0]).strftime("%d/%m/%Y")
        messages.append({"texte": "{ticker} : la même opération apparaît deux fois ({date}) : avis envoyé en double ?",
                         "valeurs": {"ticker": ticker, "date": date}})
    return messages


# ----------------------------------------------------------------------
# 10. Rapport anonymisé : pour envoyer un PDF mal lu sans données personnelles
# ----------------------------------------------------------------------
MOTS_PERSONNELS = re.compile(r"(?:\b(?:m|mr|mrs|ms|mme|mlle|dr)\.(?=\s)|\b(?:mme|mlle|monsieur|madame|mademoiselle|mr|"
                             r"mrs|ms|titulaire|client|cliente|adresse|address|n[ée]e?\s+le|nom|name|holder|herrn?|"
                             r"frau)\b)", re.IGNORECASE)


MOTIF_RUE = re.compile(r"\b\d{1,4}\s*(?:bis|ter)?,?\s+(?:rue|avenue|av\.|boulevard|bd|place|chemin|all[ée]e|impasse|"
                       r"route|quai|square|street|road|lieu-dit|r[ée]sidence)\b", re.IGNORECASE)


def _masquer_iban(m):
    """Un IBAN est masqué ; un code ISIN suivi d'un mot (« FR0000121014 QUANTITE », qui a la forme
    d'un IBAN) est gardé."""
    code = m.group(0)
    if imp.isin_plausible(code.replace(" ", "")) or imp.isin_valide(code[:12]):
        return code
    return "[IBAN]"


MOTS_NOM_FICHIER = {"avis", "opere", "opéré", "operation", "opération", "releve", "relevé", "compte", "titres",
                    "credit", "crédit", "agricole", "mutuel", "boursorama", "boursobank", "bourse", "direct",
                    "fortuneo", "degiro", "ibkr", "interactive", "brokers", "trade", "republic", "saxo", "bnp",
                    "societe", "société", "generale", "générale", "lcl", "caisse", "epargne", "pea", "cto", "pme",
                    "assurance", "vie", "statement", "activity", "transactions", "account", "export", "portefeuille",
                    "dividende", "achat", "vente", "ordre", "action", "actions", "ost", "coupon", "bulletin", "confirmation", "execution", "pdf", "csv", "xlsx", "flex", "trading212",
                    "scalable", "revolut", "etoro", "swissquote", "keytrade", "linxea", "yomoni", "de", "d", "du", "le",
                    "la", "des", "et"}


def nom_fichier_anonyme(nom):
    """Nom de fichier sans nom propre : seuls les mots courants (avis, opéré, courtier, PEA, dates…)
    sont gardés, les autres deviennent « x » (« avis DUPONT.pdf » → « avis x.pdf »)."""
    nom = str(nom or "")
    base, point, extension = nom.rpartition(".")
    if not point:
        base, extension = nom, ""
    mots = re.split(r"([\s_\-]+)", base)
    garde = [m if (not m.strip(" _-") or m.lower() in MOTS_NOM_FICHIER or re.fullmatch(r"[\d\s._\-/]+", m))
             else "x" for m in mots]
    propre = re.sub(r"[^A-Za-z0-9._ \-]", "_", "".join(garde))[:80]
    return propre + ("." + re.sub(r"[^A-Za-z0-9]", "", extension)[:5] if extension else "")


def anonymiser(texte):
    """Texte sans données personnelles : lignes de nom et d'adresse, adresses électroniques,
    IBAN, téléphones, codes postaux et numéros de compte ou de référence sont masqués.
    Restent : codes ISIN, dates, montants et intitulés, qui suffisent à corriger la lecture."""
    lignes = []
    for ligne in (texte or "").split("\n"):
        if MOTS_PERSONNELS.search(ligne) or re.search(r"\b\d{5}\s+[A-ZÉÈ][A-Za-zÉÈéèêëàâîïôûüç\- ]{2,}$", ligne) \
                or MOTIF_RUE.search(ligne):
            lignes.append("[ligne masquée : nom ou adresse]")
            continue
        sans_montant = LIGNES_SANS_MONTANT.search(ligne)      # testé sur la ligne d'origine
        ligne = re.sub(r"[\w.+\-]+@[\w\-]+\.[\w.]+", "[e-mail]", ligne)
        ligne = re.sub(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b", _masquer_iban, ligne)
        ligne = re.sub(r"(?:\+33\s?|\b0)[1-9](?:[\s.\-]?\d{2}){4}\b", "[téléphone]", ligne)
        if sans_montant:
            ligne = re.sub(r"\d[\d\s\-/.]{3,}\d|\d{4,}", "[numéro]", ligne)
        else:
            # longues suites de chiffres sans virgule (numéros), en gardant les ISIN, dates et montants
            ligne = re.sub(r"(?<![A-Z0-9])\d{7,}(?![,.]\d)", "[numéro]", ligne)
        lignes.append(ligne)
    return "\n".join(lignes)


def rapport_anonymise(textes, resultat=None, nom_fichier=""):
    """Texte à envoyer au créateur du logiciel pour améliorer la lecture d'un PDF."""
    texte = anonymiser("\n".join(textes))
    c = candidats([texte])
    lignes = ["Portfolio Tracker — rapport de lecture d'un PDF (anonymisé)",
              f"Fichier : {nom_fichier_anonyme(nom_fichier)}",
              f"Texte « codé » : {'oui' if texte_illisible(chr(10).join(textes)) else 'non'}",
              f"Codes ISIN : {[i for i, _ in c['isins']]}",
              f"Dates : {c['dates']} · date proposée : {c['date_proposee']}",
              f"Proposition : {c['proposition']}"]
    if resultat:
        lignes.append(f"Saisie de l'utilisateur : {resultat}")
    lignes += ["", "=== Texte lu (anonymisé) ===", texte]
    return "\n".join(lignes)


# ----------------------------------------------------------------------
# 11. Relevé de portefeuille (positions et prix de revient) : un portefeuille de départ
# ----------------------------------------------------------------------
MOTS_RELEVE_POSITIONS = re.compile(
    r"relev[ée]\s*(?:de|du)\s*(?:portefeuille|compte[\s-]*titres|titres|positions)|portefeuille\s*titres|"
    r"[ée]tat\s*(?:du|de)\s*portefeuille|valorisation\s*(?:du|de)\s*portefeuille|inventaire\s*(?:du|de)\s*portefeuille|"
    r"estimation\s*(?:du|de)\s*portefeuille|portfolio\s*(?:statement|valuation)|statement\s*of\s*holdings|"
    r"positions\s*(?:au|as\s*of)", re.IGNORECASE)
MOTS_DATE_RELEVE = re.compile(r"(?:\bau|arr[êe]t[ée]\s*au|as\s*of|valoris\w*|situation|en\s*date\s*du|date)\s*:?\s*$",
                              re.IGNORECASE)


def est_un_releve_de_positions(texte):
    return bool(MOTS_RELEVE_POSITIONS.search(texte or "")) and len({c for c, _ in isins(texte)}) >= 1


def lire_releve_positions(texte):
    """Positions d'un relevé de portefeuille : pour chaque ISIN, quantité × cours = valorisation
    (au centime près) et le prix de revient unitaire (PRU) : le nombre restant de la ligne le plus
    proche du cours, confirmé si quantité × (cours − PRU) = plus-value écrite. Renvoie une liste
    de dict (date du relevé, isin, libelle, quantite, cours, pru, devise) ou [] si une ligne n'est
    pas sûre."""
    if not est_un_releve_de_positions(texte):
        return []
    toutes = dates(texte)
    date = next((d[0] for d in toutes if MOTS_DATE_RELEVE.search(d[3])), toutes[0][0] if toutes else None)
    positions = []
    for isin, segment, _ in _segments(texte):
        if not isin:
            continue
        ligne = next((l for l in segment.splitlines() if isin in l), segment)
        meilleurs = trios(ligne) or trios(segment)
        if not meilleurs:
            return []
        t = meilleurs[0]
        q, cours = t["quantite"], t["cours"]
        utilises = [q, cours, t["brut"]] if t["brut"] else [q, cours]
        restants = [c for c in nombres(ligne) if not any(_se_chevauchent(c, u) for u in utilises if u)]
        pru = None
        etiquete = [c for c in restants if MOTS_PRU.search(_contexte(ligne, c, 30))]
        if etiquete:
            pru = etiquete[0]["valeur"]
        else:
            proches = [c for c in restants if cours["valeur"] / 3 <= c["valeur"] <= cours["valeur"] * 3]
            # confirmation : la plus-value latente écrite = quantité × (cours − PRU)
            for c in proches:
                plus_value = abs(q["valeur"] * (cours["valeur"] - c["valeur"]))
                if any(abs(r["valeur"] - plus_value) < 0.02 for r in restants if r is not c):
                    pru = c["valeur"]
                    break
            if pru is None and proches:
                pru = min(proches, key=lambda c: abs(c["valeur"] - cours["valeur"]))["valeur"]
        positions.append({"date": date, "isin": isin, "libelle": _libelle(ligne, isin)[:60],
                          "quantite": float(q["valeur"]), "cours": float(cours["valeur"]),
                          "pru": float(pru) if pru else None, "devise": _devise(ligne, cours)})
    return positions


MOTS_PRU = re.compile(r"pru|prix\s*de\s*revient|prix\s*moyen|\bpam\b|cost\s*(?:price|basis)|average\s*(?:cost|price)",
                      re.IGNORECASE)


def positions_en_lignes_avis(positions):
    """Chaque position devient un achat au PRU (à défaut au cours), à la date du relevé."""
    def nombre(x):
        return f"{x:.6f}".rstrip("0").rstrip(".")
    return [[p["date"] or "", "ACHAT", p["isin"], p["libelle"] or p["isin"], nombre(p["quantite"]),
             nombre(p["pru"] or p["cours"]), p["devise"] or "", "", nombre(p["quantite"] * (p["pru"] or p["cours"]))]
            for p in positions]


# ----------------------------------------------------------------------
# 12. Opérations sur titres : division (split) ou regroupement d'actions
# ----------------------------------------------------------------------
MOTS_DIVISION = re.compile(r"division\s*(?:du\s*nominal|d['’]\s*actions?|des\s*actions)?|\bsplit\b|fractionnement",
                           re.IGNORECASE)
MOTS_REGROUPEMENT = re.compile(r"regroupement|reverse\s*split|consolidation\s*d", re.IGNORECASE)
MOTIF_DIVISE_PAR = re.compile(r"divis[ée]e?s?\s*par\s*(\d+)", re.IGNORECASE)
MOTIF_PARITE = re.compile(r"(?:parit[ée]|ratio|rapport\s*d['’]\s*[ée]change)?\s*:?\s*(\d+)\s*(?:actions?|titres?|shares?)?"
                          r"\s*(?:anciennes?|old|existantes?)?\s*(?:pour|contre|for|:|→|->)\s*(\d+)\s*"
                          r"(?:actions?|titres?|shares?)?\s*(?:nouvelles?|new)", re.IGNORECASE)
MOTIF_PARITE_SIMPLE = re.compile(r"(?:parit[ée]|ratio)\s*:?\s*(\d+)\s*(?:pour|:|/|for)\s*(\d+)", re.IGNORECASE)
MOTS_DATE_EFFET = re.compile(r"(?:effet|ex[\s-]*date|d[ée]tachement|[àa]\s*compter\s*du|effective|r[ée]alis[ée]e?\s*le|"
                             r"date\s*de\s*l['’]\s*op[ée]ration)[^\n\d]{0,25}$", re.IGNORECASE)


def lire_ost(texte):
    """Avis de division ou de regroupement d'actions : dict(nature, isin, libelle, date,
    facteur) — facteur = nombre de titres nouveaux pour 1 ancien (4 pour une division par 4,
    0,1 pour un regroupement de 10 en 1) — ou None."""
    division, regroupement = MOTS_DIVISION.search(texte or ""), MOTS_REGROUPEMENT.search(texte or "")
    trouves = isins(texte or "")
    if not (division or regroupement) or not trouves:
        return None
    facteur = None
    m = MOTIF_DIVISE_PAR.search(texte)
    if m and int(m.group(1)) > 1:
        facteur = float(m.group(1)) if division else 1 / float(m.group(1))
    else:
        m = MOTIF_PARITE.search(texte) or MOTIF_PARITE_SIMPLE.search(texte)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            if a > 0 and b > 0 and a != b:
                # « 1 ancienne pour 4 nouvelles » (division) ; « 10 anciennes pour 1 nouvelle » (regroupement)
                facteur = b / a if MOTIF_PARITE.search(texte) else (max(a, b) / min(a, b) if division
                                                                     else min(a, b) / max(a, b))
    if not facteur or facteur == 1:
        return None
    toutes = dates(texte)
    date = next((d[0] for d in toutes if MOTS_DATE_EFFET.search(d[3])), None) or date_execution(texte)
    isin = trouves[0][0]
    ligne = next((l for l in texte.splitlines() if isin in l), "")
    avant = MOTS_REGROUPEMENT.sub(" ", MOTS_DIVISION.sub(" ", ligne.split(isin)[0]))
    avant = re.sub(r"\b(?:d['’]\s*actions?|isin|code|valeur|titre)\b\s*:?", " ", avant, flags=re.IGNORECASE)
    libelle = " ".join(avant.split()[-4:]).strip(" :-(") or _libelle(texte, isin)
    return {"nature": "division" if facteur > 1 else "regroupement", "isin": isin,
            "libelle": libelle[:60], "date": date, "facteur": facteur}


# ----------------------------------------------------------------------
# 13. Relevé d'opérations « une ligne par opération » (export ou impression d'un courtier)
# ----------------------------------------------------------------------
# Ex. Interactive Brokers : « U1234 ESE 2026-07-13, 07:05:17 2026-07-15 - BUY 7 33.4540 -234.18 -1.17 0.00 MKT »
MOTS_LIGNE_TOTAL = re.compile(r"\b(?:total|sous-total|subtotal|solde|report)\b", re.IGNORECASE)
MOTS_NON_TITRES = {"BUY", "SELL", "ACHAT", "VENTE", "MKT", "LMT", "LIMIT", "TOTAL", "EUR", "USD", "GBP", "CHF",
                   "ID", "ISIN", "BOT", "SLD", "STK", "ETF", "LE", "DU", "AU", "THE"}


def _lectures_ocr(ecrit):
    """Lectures possibles d'un nombre dont la reconnaissance a pu perdre la virgule :
    « -23418 » peut être 234,18 ; « 72712714286 » peut être 72,712714286. Pour un nombre écrit
    sans séparateur, on propose aussi chaque position possible de la virgule ; seule la
    cohérence quantité × cours = montant décidera."""
    lectures = set(_valeurs(ecrit))
    nu = ecrit.lstrip("+-")
    if re.fullmatch(r"\d{3,12}", nu):
        lectures |= {int(nu) / 10 ** k for k in range(1, len(nu))}
    return lectures


def _titre_de_la_ligne(avant):
    """Le code du titre écrit avant la date : un ISIN, sinon un symbole boursier (« ESE »,
    « PAEJ », « RMS », « LYSXd » -> « LYSX »)."""
    trouves = isins(avant)
    if trouves:
        return trouves[0][0]
    jetons = re.findall(r"[A-Za-z][A-Za-z0-9.]{1,9}", avant)
    candidats = [j for j in jetons if j.upper() not in MOTS_NON_TITRES and not re.fullmatch(r"[uU]\d+.*|[a-z]+", j)
                 and sum(c.isupper() for c in j) >= max(2, len(j) - 1)]
    if not candidats:
        return None
    symbole = candidats[-1]
    if re.fullmatch(r"[A-Z]{3}\.[A-Z]{3}", symbole):          # opération de change IBKR (« EUR.USD ») : pas un titre
        return None
    if re.fullmatch(r"[A-Z0-9]{2,8}[a-z]", symbole):           # suffixe de place du courtier (« LYSXd »)
        symbole = symbole[:-1]
    return symbole


def lire_lignes_operations(texte, minimum=2):
    """Opérations d'un relevé où chaque ligne porte une opération complète : un code (ISIN ou
    symbole), une date, un sens (achat / vente / buy / sell), puis quantité, cours et montant
    (quantité × cours = montant au centime près), et éventuellement commission et taxe.
    Les lignes « Total » sont ignorées. Renvoie une liste de dict (comme lire_par_le_contenu),
    chacun avec « sur » ; [] s'il y a moins de `minimum` lignes d'opération."""
    operations = []
    # la ligne de titres dit s'il y a, après la commission, une colonne de taxe (« Fee », « TTF »…)
    a_une_taxe = bool(re.search(r"\b(?:comm\w*|courtage)\b.{0,40}\b(?:fees?|tax\w*|ttf|taxe)\b", texte or "",
                                re.IGNORECASE))
    for ligne in (texte or "").split("\n"):
        propre = re.sub(r"[|\[\]{}“”‘’\"—]", " ", ligne)
        if MOTS_LIGNE_TOTAL.search(propre):
            continue
        sens = MOTIF_SENS.search(propre)
        les_dates = dates(propre)
        if not les_dates:
            continue
        if sens:
            titre = _titre_de_la_ligne(propre[:les_dates[0][1]]) or _titre_de_la_ligne(propre[:sens.start()])
            reste = propre[sens.end():]
        else:
            # pas de mot achat / vente (relevé DEGIRO…) : un ISIN, puis une quantité signée
            # (négative = vente) suivie du cours et du montant
            codes = [c for c, _ in isins(propre)]
            if len(codes) != 1:
                continue
            titre = codes[0]
            reste = propre[propre.find(titre) + len(titre):]
        if not titre:
            continue
        # nombres après le sens, dans l'ordre, avec toutes leurs lectures possibles
        morceaux = [m for m in MOTIF_MORCEAU.finditer(reste)]
        jetons = [(m.group(1) + m.group(2), _lectures_ocr(m.group(1) + m.group(2))) for m in morceaux]
        # milliers séparés par une espace (« -1 338,00 », relevés DEGIRO) : « 338,00 » peut aussi valoir 1 338,00
        for a, b in zip(range(len(morceaux) - 1), range(1, len(morceaux))):
            ma, mb = morceaux[a], morceaux[b]
            if re.fullmatch(r"\d{1,3}", ma.group(2)) and re.fullmatch(r"\d{3}[.,]\d{2}", mb.group(2)) \
                    and reste[ma.end():mb.start()] in (" ", "\u00a0", "\u202f") and not mb.group(1):
                signe = -1 if ma.group(1) == "-" else 1
                valeur = signe * (int(ma.group(2)) * 1000 + float(mb.group(2).replace(",", ".")))
                jetons[b] = (ma.group(1) + ma.group(2) + mb.group(2), jetons[b][1] | {abs(valeur), valeur})
        trouve = None
        for i in range(len(jetons)):
            for j in range(i + 1, len(jetons)):
                for k in range(j + 1, min(len(jetons), j + 3)):
                    for q in jetons[i][1]:
                        for p in jetons[j][1]:
                            for b in jetons[k][1]:
                                if q > 0 and p > 0 and abs(q * p - b) <= 0.0101 and q < 1e6:
                                    entier = float(q).is_integer()
                                    score = (2 if entier else 0) - i - (j - i - 1) - (k - j - 1)
                                    if not trouve or score > trouve[0]:
                                        trouve = (score, q, p, b, k, jetons[i][0])
        if not trouve and not sens:
            continue                              # sans mot de sens, seule une ligne complète compte
        if not trouve:
            # quantité illisible : cours et montant lisibles, et montant / cours entier
            for j in range(len(jetons)):
                for k in range(j + 1, min(len(jetons), j + 2)):
                    for p in jetons[j][1]:
                        for b in jetons[k][1]:
                            if not (0 < p < 1e9 and 0 < b < 1e12):
                                continue
                            if abs(round(b / p) * p - b) <= 0.0101 and round(b / p) >= 1 \
                                    and re.search(r"[.,]", jetons[j][0] + jetons[k][0]):
                                q = round(b / p)
                                if abs(q * p - b) <= 0.0101 and (not trouve or j < trouve[4]):
                                    trouve = (0, float(q), p, b, k, "")
        if not trouve:
            operations.append({"date": les_dates[0][0], "sens": sens.group(1), "isin": titre, "libelle": titre,
                               "quantite": None, "cours": None, "devise": "", "frais": None, "montant": None,
                               "sur": False, "net": None, "alternatives": []})
            continue
        _, q, p, b, k, ecrit_q = trouve
        # commission (et taxe) : les petits nombres décimaux qui suivent le montant (moins de 5 % du
        # montant) ; les chiffres isolés sans virgule (« 1 », restes de bordures de tableau) sont ignorés
        frais = 0.0
        # (un taux de change « 1,0619 », à quatre décimales, n'est pas un frais)
        suivants = []
        for ecrit, _ in jetons[k + 1:k + 5]:
            valeur = next(iter(_valeurs(ecrit)), None)
            if re.search(r"\d[.,]\d{1,3}$", ecrit) and valeur is not None and 0 < abs(valeur) < 0.05 * b:
                suivants.append(abs(valeur))
        if not sens and suivants:
            suivants = suivants[-1:]           # relevé sans sens : la colonne de frais est la dernière petite
        for valeur in suivants[:2 if a_une_taxe else 1]:
            frais += valeur
        mot = sens.group(1).lower() if sens else ""
        vente = mot.lower() in ("vente", "sell", "sold", "verkauf", "venta", "vendita", "verkoop") or ecrit_q.startswith("-")
        m_devise = MOTIF_DEVISE.search(reste)
        devise = (m_devise.group(1) or SYMBOLES[m_devise.group(2)]) if m_devise else ""
        heure = re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", propre)
        operations.append({"date": les_dates[0][0], "sens": "VENTE" if vente else "ACHAT", "isin": titre,
                           "libelle": titre, "quantite": float(q), "cours": float(p), "devise": devise,
                           "frais": round(frais, 2) if frais else None, "montant": float(b),
                           "sur": date_plausible(les_dates[0][0]), "heure": heure.group(0) if heure else "",
                           "net": None, "alternatives": []})
    # symboles du courtier ou mal lus par la reconnaissance de caractères : « ESEEd » (Interactive
    # Brokers, cotation à Paris), lu « ESEED » en majuscules, « ESEE »… pour le même ETF que « ESE »
    symboles = {o["isin"] for o in operations}
    for o in operations:
        o["isin"] = o["libelle"] = _symbole_ramene(o["isin"], symboles)
    operations = retirer_executions_detaillees(operations)
    return operations if len(operations) >= minimum else []


def retirer_executions_detaillees(operations):
    """Relevé Interactive Brokers (« Rapport de confirmation de transactions ») : chaque ordre est écrit
    sur une ligne, PUIS ses exécutions détaillées (une par bourse : EUDARK, TRWBEN…) avec les mêmes
    quantités. Les exécutions qui suivent un ordre (même titre, même date, même heure à la seconde, même
    sens) et dont les quantités s'additionnent exactement à celle de l'ordre sont retirées : sans cela,
    les quantités seraient comptées deux fois. Sans heure, rien n'est retiré (deux ordres identiques le
    même jour sont possibles)."""
    gardees, i = [], 0
    while i < len(operations):
        ordre = operations[i]
        gardees.append(ordre)
        fin = None
        if ordre.get("heure") and ordre.get("quantite"):
            total, k = 0.0, i + 1
            while k < len(operations):
                o = operations[k]
                if (o["isin"], o["date"], o.get("heure"), o["sens"]) != \
                        (ordre["isin"], ordre["date"], ordre["heure"], ordre["sens"]) or not o.get("quantite"):
                    break
                total += o["quantite"]
                if abs(total - ordre["quantite"]) < 1e-9:
                    fin = k
                    break
                if total > ordre["quantite"]:
                    break
                k += 1
        i = fin + 1 if fin is not None else i + 1
    return gardees


# Symboles propres à un courtier -> symbole de la bourse (Interactive Brokers, Euronext Paris)
SYMBOLES_COURTIER = {"ESEE": "ESE"}


def _symbole_ramene(symbole, symboles):
    """« ESEED » ou « ESEE » -> « ESE » : suffixe de place lu en majuscule (« D »), lettre lue en
    double, symbole propre au courtier. Un ISIN n'est jamais modifié."""
    if not symbole or imp.MOTIF_ISIN.match(symbole):
        return symbole
    candidats = [symbole]
    if len(symbole) > 3 and symbole.endswith("D"):
        candidats.append(symbole[:-1])
    for c in list(candidats):
        if len(c) > 3 and c[-1] == c[-2]:
            candidats.append(c[:-1])
    for c in candidats[1:]:
        if c in symboles and c != symbole:
            return c
    for c in candidats:
        if c in SYMBOLES_COURTIER:
            return SYMBOLES_COURTIER[c]
    return symbole


# ----------------------------------------------------------------------
# 15. Cas particuliers : souscription lors d'une opération sur titres, assurance-vie
# ----------------------------------------------------------------------
def _nombre_fr(texte):
    try:
        return float(re.sub(r"[\s  ]", "", texte).replace(",", "."))
    except ValueError:
        return None


MOTIF_SOUSCRIPTION_OST = re.compile(
    r"souscription\s+de\s+(\d[\d\s  ]*)\s+titre\(?s?\)?\s+(.+?)\s*\(([A-Z]{2}[A-Z0-9]{9}\d)\)", re.IGNORECASE | re.DOTALL)
MOTIF_MONTANT_NET = re.compile(r"montant\s+net\s+(?:de\s*)?:?\s*-?\s*(\d[\d\s  ]*,\d{2})\s*(EUR|€|USD|\$)?",
                               re.IGNORECASE)
MOTIF_LIGNE_UC = re.compile(
    r"^(?P<lib>.*?)\s*(?P<isin>[A-Z]{2}[A-Z0-9]{9}\d)\s+(?P<date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<a>\d[\d\s  ]*,\d+)\s+(?P<b>\d[\d\s  ]*,\d+)\s+(?P<m>\d[\d\s  ]*,\d{2})\s*$", re.MULTILINE)
MOTS_ASSURANCE_VIE = re.compile(r"unit[ée]s?\s+de\s+compte|valeurs?\s+liquidatives?", re.IGNORECASE)
MOTS_SORTIE_AV = re.compile(r"\brachat\b|d[ée]sinvestissement|\bretrait\b", re.IGNORECASE)


def lire_cas_particuliers(texte):
    """Opérations des documents qui ne disent pas « achat / quantité / cours » :
        - souscription lors d'une opération sur titres (augmentation de capital, « titres
          réductibles » : « souscription de 16 titre(s) VEOLIA (FR…) … montant net de : - 363,20 EUR »),
          cours = montant / quantité ;
        - assurance-vie (versement, arbitrage, rachat) : « LYXOR STOXX50 … FR0007054358 05/06/2020
          33,26 90,1984 3 000,00 » = valeur liquidative × nombre d'unités de compte = montant.
    Renvoie une liste d'opérations (même format que lire_lignes_operations), toutes sûres, ou []."""
    texte = texte or ""
    operations = []
    m = MOTIF_SOUSCRIPTION_OST.search(texte)
    n = MOTIF_MONTANT_NET.search(texte)
    if m and n:
        quantite, montant = _nombre_fr(m.group(1)), _nombre_fr(n.group(1))
        date = date_execution(texte)
        if quantite and montant and date:
            operations.append({"date": date, "sens": "ACHAT", "isin": m.group(3),
                               "libelle": " ".join(m.group(2).split())[:60], "quantite": quantite,
                               "cours": round(montant / quantite, 6), "devise": SYMBOLES.get(n.group(2) or "",
                                                                                           n.group(2) or "EUR"),
                               "frais": None, "montant": montant, "sur": date_plausible(date), "net": None,
                               "alternatives": []})
        return operations if operations and all(o["sur"] for o in operations) else []
    if not MOTS_ASSURANCE_VIE.search(texte):
        return []
    # date de l'opération (« Date du versement : 04/06/2020 »), sinon la date de valeur de la ligne
    date_operation = next((d for d, _, _, avant in dates(texte)
                           if re.search(r"date\s+(?:du|de\s+l['’])\s*(?:versement|arbitrage|rachat|op[ée]ration)",
                                        avant, re.IGNORECASE)), None)
    vente = bool(MOTS_SORTIE_AV.search(texte)) and not re.search(r"versement", texte, re.IGNORECASE)
    for ligne in MOTIF_LIGNE_UC.finditer(texte):
        a, b, montant = (_nombre_fr(ligne.group(x)) for x in ("a", "b", "m"))
        if not (a and b and montant) or abs(a * b - montant) > max(0.02, 0.005 * montant):
            continue
        # le nombre d'unités a souvent 4 décimales, la valeur liquidative 2 : à défaut, l'ordre des colonnes
        decimales = [len(ligne.group(x).split(",")[1]) for x in ("a", "b")]
        unites, valeur = (a, b) if decimales[0] > decimales[1] else (b, a)
        libelle = " ".join(ligne.group("lib").split()) or ligne.group("isin")
        date = date_operation or ligne.group("date")
        operations.append({"date": date, "sens": "VENTE" if vente else "ACHAT", "isin": ligne.group("isin"),
                           "libelle": libelle[:60], "quantite": unites, "cours": valeur, "devise": "EUR",
                           "frais": None, "montant": montant, "sur": date_plausible(date), "net": None,
                           "alternatives": []})
    return operations if operations and all(o["sur"] for o in operations) else []


# ----------------------------------------------------------------------
# 16. Relevés Interactive Brokers : tableau « Informations instrument financier »
# ----------------------------------------------------------------------
def instruments_ibkr(texte):
    """Tableau « Informations instrument financier » / « Financial Instrument Information » d'un relevé
    Interactive Brokers : {symbole: {"isin", "place", "libelle"}}. Ex. la ligne
    « PAEJ 155510562 FR0011869312 PAEJ SBF 1 ETF », entourée de sa description sur deux lignes
    (« AM P AP M AC AP EX JAP ETF- » / « C »)."""
    texte = texte or ""
    debut = re.search(r"informations?\s+instrument\s+financier|financial\s+instrument\s+information", texte,
                      re.IGNORECASE)
    if not debut:
        return {}
    lignes = texte[debut.end():].split("\n")
    resultat = {}
    for i, ligne in enumerate(lignes):
        m = re.match(r"^\s*([A-Z0-9.]{1,12}[a-z]?)\s+(?:.*?\s)?(?:\d{4,12}\s+)?([A-Z]{2}[A-Z0-9]{9}\d)\s+\S+\s+"
                     r"([A-Z0-9.]{2,10})\b", ligne)
        if not m or not imp.isin_valide(m.group(2)):
            continue
        symbole, isin, place = m.group(1), m.group(2), m.group(3)
        # description : entre le symbole et le Conid sur la même ligne, sinon la ligne d'avant (+ la suite
        # très courte de la ligne d'après : « C », « ACC », « CAP »)
        milieu = re.sub(r"\b\d{4,12}\b", " ", ligne[m.end(1):ligne.find(isin)]).strip()
        avant = lignes[i - 1].strip() if i and not re.search(r"[A-Z]{2}[A-Z0-9]{9}\d", lignes[i - 1]) else ""
        apres = lignes[i + 1].strip() if i + 1 < len(lignes) and len(lignes[i + 1].strip()) <= 6 else ""
        libelle = milieu or " ".join(x for x in (avant, apres) if x and not re.match(r"^(actions|stocks|etfs?)$", x,
                                                                                      re.IGNORECASE))
        resultat[symbole] = {"isin": isin, "place": place, "libelle": libelle.replace("- ", "-").strip()}
    return resultat


def ticker_ibkr(symbole, instruments):
    """Symbole d'un relevé IBKR -> ticker Yahoo (symbole + suffixe de la place : PAEJ + SBF -> PAEJ.PA),
    sinon l'ISIN, sinon le symbole tel quel."""
    info = instruments.get(symbole) or instruments.get(re.sub(r"[a-z]$", "", symbole or ""))
    if not info:
        return symbole
    suffixe = imp.PLACES.get(info["place"].upper())
    racine = re.sub(r"[a-z]$", "", symbole)
    if suffixe is not None and "." not in racine:
        return racine + suffixe
    return info["isin"] or symbole

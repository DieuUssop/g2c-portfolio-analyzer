"""
classement.py — Classe d'actifs, région, pays et secteur de chaque titre.

Le classement sert partout : répartition de la vue d'ensemble, tableau des positions,
performance par classe et par secteur, éligibilité au PEA, analyse en transparence.
Un titre mal classé finit en « Non classé » : ce module essaie, dans l'ordre :

    1. la fiche du titre (référentiel du projet, puis base locale de titres), avec un
       secteur ramené aux 11 grands secteurs du projet (noms GICS, ICB, Yahoo, en anglais
       comme en français) ;
    2. pour un ETF (reconnu à son ticker ou à son nom : ETF, UCITS, iShares, Amundi…) :
       l'INDICE SUIVI, lu dans le nom (MSCI World, S&P 500, Stoxx 600, émergents,
       obligations d'État…) — un ETF éligible au PEA par réplication synthétique (swap),
       comme « Amundi PEA S&P 500 », détient juridiquement des actions européennes mais
       rapporte la performance du S&P 500 : il est classé selon l'indice suivi ;
    3. pour une action : une table des valeurs françaises (CAC 40, SBF 120 et valeurs
       moyennes courantes) et le pays d'après la place de cotation ;
    4. avec Internet : le secteur et le pays donnés par Yahoo Finance, gardés en mémoire
       (data/cache_classement.csv) pour les fois suivantes.
"""

import re
from pathlib import Path

import pandas as pd

from . import composition_etf

CHEMIN_CACHE = Path(__file__).resolve().parent.parent / "data" / "cache_classement.csv"
NON_CLASSE = "Non classé"

# ----------------------------------------------------------------------
# 1. Secteurs : tous les noms rencontrés -> les 11 secteurs du projet
# ----------------------------------------------------------------------
SECTEURS_PROJET = ["Technologie", "Santé", "Finance", "Consommation discrétionnaire", "Consommation de base",
                   "Industrie", "Énergie", "Matériaux", "Services publics", "Immobilier", "Communication"]
_SYNONYMES = {
    "Technologie": ["information technology", "technology", "tech", "technologie", "technologies de l'information",
                    "logiciels", "semi-conducteurs", "semiconductors", "software", "électronique"],
    "Santé": ["health care", "healthcare", "santé", "sante", "pharmaceuticals", "pharmacie", "biotechnology",
              "biotechnologie", "medical", "médical"],
    "Finance": ["financials", "financial", "financial services", "finance", "sociétés financières",
                "banques", "banks", "bank", "assurance", "assurances", "insurance", "services financiers"],
    "Consommation discrétionnaire": ["consumer discretionary", "consumer cyclical", "consommation discrétionnaire",
                                     "biens de consommation cyclique", "services aux consommateurs",
                                     "consumer services", "automobiles", "automobile", "luxe", "luxury",
                                     "distribution", "retail", "médias et loisirs", "voyages et loisirs",
                                     "travel & leisure", "biens de consommation discrétionnaire"],
    "Consommation de base": ["consumer staples", "consumer defensive", "consommation de base",
                             "biens de consommation de base", "consumer goods", "biens de consommation",
                             "alimentation", "food & beverage", "boissons", "produits ménagers"],
    "Industrie": ["industrials", "industrial", "industrie", "industries", "industriels", "biens industriels",
                  "aéronautique", "aerospace & defense", "construction", "construction et matériaux",
                  "transport", "transports"],
    "Énergie": ["energy", "énergie", "energie", "oil & gas", "pétrole et gaz", "petrole et gaz"],
    "Matériaux": ["materials", "basic materials", "matériaux", "materiaux", "matériaux de base", "chimie",
                  "chemicals", "mines", "mining", "ressources de base", "basic resources"],
    "Services publics": ["utilities", "services publics", "services aux collectivités", "services aux collectivites"],
    "Immobilier": ["real estate", "immobilier", "foncières", "foncieres", "reit"],
    "Communication": ["communication services", "communication", "telecommunications", "télécommunications",
                      "telecommunication services", "telecoms", "télécoms", "médias", "media"],
}
_PAR_SYNONYME = {s: secteur for secteur, liste in _SYNONYMES.items() for s in liste}
# Secteurs du projet propres aux fonds (gardés tels quels)
SECTEURS_FONDS = {"ETF diversifié", "Obligations d'État", "Obligations d'entreprises",
                  "Obligations indexées sur l'inflation", "Obligations à haut rendement", "Obligations émergentes",
                  "Or", "Monétaire"}


def normaliser_secteur(secteur):
    """« Financial Services », « Banques », « Consumer Cyclical »… -> secteur du projet, ou ""."""
    brut = str(secteur or "").strip()
    if not brut or brut.lower() in ("nan", "none", NON_CLASSE.lower()):
        return ""
    if brut in SECTEURS_PROJET or brut in SECTEURS_FONDS:
        return brut
    return _PAR_SYNONYME.get(brut.lower(), "")


# ----------------------------------------------------------------------
# 2. Actions françaises (CAC 40, SBF 120, valeurs moyennes courantes)
# ----------------------------------------------------------------------
def _table(groupes):
    return {ticker: secteur for secteur, tickers in groupes.items() for ticker in tickers.split()}


ACTIONS_FR = _table({
    "Technologie": "CAP.PA STMPA.PA DSY.PA SOP.PA ATO.PA WLN.PA SOI.PA ATE.PA AUB.PA OVH.PA LSS.PA",
    "Santé": "SAN.PA EL.PA BIM.PA ERF.PA IPN.PA VIRP.PA ORP.PA EMEIS.PA CLARI.PA DBV.PA NANO.PA GNFT.PA "
             "VLA.PA ALHYG.PA ABVX.PA BOI.PA",
    "Finance": "BNP.PA GLE.PA ACA.PA CS.PA AMUN.PA EDEN.PA SCR.PA TKO.PA MF.PA COFA.PA ABCA.PA RF.PA ANTIN.PA",
    "Consommation discrétionnaire": "MC.PA RMS.PA KER.PA CDI.PA RNO.PA STLAP.PA ML.PA AC.PA SW.PA FDJ.PA "
                                    "FRVIA.PA VLO.PA SK.PA FNAC.PA BEN.PA OPM.PA ELIOR.PA SMCP.PA TRI.PA",
    "Consommation de base": "OR.PA BN.PA RI.PA CA.PA RCO.PA CO.PA BON.PA LOUP.PA SAVE.PA",
    "Industrie": "AIR.PA SAF.PA SU.PA DG.PA LR.PA HO.PA AM.PA EN.PA SGO.PA BVI.PA TEP.PA GET.PA RXL.PA "
                 "SPIE.PA FGR.PA AF.PA ADP.PA ELIS.PA IDL.PA AYV.PA DBG.PA STF.PA EXA.PA BOL.PA ALO.PA NEX.PA",
    "Énergie": "TTE.PA MAU.PA EC.PA GTT.PA VK.PA",
    "Services publics": "VIE.PA ENGI.PA RUI.PA NEOEN.PA VLTSA.PA",
    "Matériaux": "AI.PA MT.AS ERA.PA AKE.PA NK.PA VCT.PA",
    "Immobilier": "URW.PA COV.PA GFC.PA LI.PA ICAD.PA MERY.PA ARG.PA NXI.PA",
    "Communication": "ORA.PA PUB.PA VIV.PA UBI.PA TFI.PA MMT.PA SESG.PA ETL.PA DEC.PA",
})

# Place de cotation (suffixe Yahoo) -> (pays, région du projet)
PAYS_PAR_SUFFIXE = {
    "": ("États-Unis", "États-Unis"), ".PA": ("France", "Europe"), ".DE": ("Allemagne", "Europe"),
    ".F": ("Allemagne", "Europe"), ".AS": ("Pays-Bas", "Europe"), ".BR": ("Belgique", "Europe"),
    ".MC": ("Espagne", "Europe"), ".MI": ("Italie", "Europe"), ".LS": ("Portugal", "Europe"),
    ".IR": ("Irlande", "Europe"), ".VI": ("Autriche", "Europe"), ".HE": ("Finlande", "Europe"),
    ".CO": ("Danemark", "Europe"), ".ST": ("Suède", "Europe"), ".OL": ("Norvège", "Europe"),
    ".L": ("Royaume-Uni", "Royaume-Uni"), ".SW": ("Suisse", "Suisse"), ".T": ("Japon", "Japon"),
    ".TO": ("Canada", "Canada"), ".AX": ("Australie", "Asie-Pacifique"), ".HK": ("Hong Kong", "Asie-Pacifique"),
}
# Pays du siège (Yahoo Finance, en anglais) -> pays du projet
PAYS_ANGLAIS = {
    "United States": "États-Unis", "France": "France", "Germany": "Allemagne", "Netherlands": "Pays-Bas",
    "Belgium": "Belgique", "Spain": "Espagne", "Italy": "Italie", "Portugal": "Portugal", "Ireland": "Irlande",
    "Austria": "Autriche", "Finland": "Finlande", "Denmark": "Danemark", "Sweden": "Suède", "Norway": "Norvège",
    "United Kingdom": "Royaume-Uni", "Switzerland": "Suisse", "Japan": "Japon", "Canada": "Canada",
    "Australia": "Australie", "Hong Kong": "Hong Kong", "China": "Chine", "Taiwan": "Taïwan",
    "South Korea": "Corée du Sud", "India": "Inde", "Brazil": "Brésil", "Mexico": "Mexique",
    "Luxembourg": "Luxembourg", "Israel": "Israël", "Singapore": "Singapour",
}

# ----------------------------------------------------------------------
# 3. ETF : reconnaissance et classement selon l'indice suivi
# ----------------------------------------------------------------------
MOTIF_ETF = re.compile(r"\betf\b|ucits|\bfund\b|\bfonds\b|ishares|amundi|lyxor|xtrackers|vanguard|spdr|\beasy\b|"
                       r"invesco|bnp paribas easy|\bbnpp\b|\bbnpetf\b|wisdomtree|vaneck|\bhsbc msci|franklin|"
                       r"\btracker\b|\bopcvm\b|\bsicav\b|\bfcp\b|\bpea\b.*(s&p|msci|nasdaq|monde|world|emerg)",
                       re.IGNORECASE)
REGION_PAR_INDICE = {
    "MSCI World": "Monde (ETF)", "MSCI ACWI": "Monde (ETF)", "MSCI EAFE": "Monde (ETF)",
    "MSCI World Small Cap": "Monde (ETF)",
    "S&P 500": "États-Unis", "Nasdaq-100": "États-Unis", "Russell 2000": "États-Unis", "US Total Market": "États-Unis",
    "MSCI Europe": "Europe", "Euro Stoxx 50": "Europe", "CAC 40": "Europe", "DAX": "Europe",
    "MSCI Emerging Markets": "Émergents",
    "Emprunts d'État zone euro": "Europe", "Obligations d'entreprises euro": "Europe", "Haut rendement euro": "Europe",
    "Emprunts d'État américains": "États-Unis", "Obligations d'entreprises américaines": "États-Unis",
    "Obligations émergentes en dollars": "Émergents",
}
SECTEUR_OBLIGATAIRE = {
    "Emprunts d'État japonais": "Obligations d'État", "Emprunts d'État britanniques": "Obligations d'État", "Emprunts d'État mondiaux": "Obligations d'État",
    "Obligations agrégées mondiales": "Obligations d'État", "Obligations agrégées euro": "Obligations d'État",
    "Obligations indexées sur l'inflation euro": "Obligations indexées sur l'inflation",
    "Obligations émergentes en devises locales": "Obligations émergentes",
    "Obligations d'entreprises mondiales": "Obligations d'entreprises",
    "Emprunts d'État zone euro": "Obligations d'État", "Emprunts d'État américains": "Obligations d'État",
    "Obligations d'entreprises euro": "Obligations d'entreprises",
    "Obligations d'entreprises américaines": "Obligations d'entreprises",
    "Haut rendement euro": "Obligations à haut rendement",
    "Obligations émergentes en dollars": "Obligations émergentes",
}
# ETF sectoriels (nom) -> secteur
MOTIFS_ETF_SECTEUR = [
    (r"clean energy|renewable|utilities|services aux collectivit", "Services publics"),
    (r"semiconductor|semi-conducteur|technology|technologie|\btech\b|information tech|cyber|robot|"
     r"artificial intelligence|\bai\b", "Technologie"),
    (r"health|santé|healthcare|biotech|pharma", "Santé"),
    (r"financ|bank|banque|insurance", "Finance"),
    (r"energy|énergie|oil|pétrole", "Énergie"),
    (r"real estate|immobilier|reit|property|epra|nareit", "Immobilier"),
    (r"consumer staples|food|consommation de base", "Consommation de base"),
    (r"consumer discretionary|luxury|luxe", "Consommation discrétionnaire"),
    (r"industrials|industrie|defen[cs]e|aerospace", "Industrie"),
    (r"materials|matériaux|mining|mines", "Matériaux"),
    (r"communication|media|télécom", "Communication"),
]
_MOTIFS_ETF_SECTEUR = [(re.compile(m, re.IGNORECASE), s) for m, s in MOTIFS_ETF_SECTEUR]
MOTIF_OR = re.compile(r"\bgold\b|\bor physique\b|xetra-gold|\bor\b.*etc|bullion", re.IGNORECASE)
MOTIF_MONETAIRE = re.compile(r"overnight|overn\b|\bovern\.|monétaire|monetaire|money market|€str|\bestr\b|cash|\beonia\b",
                             re.IGNORECASE)
MOTIF_OBLIGATION = re.compile(r"bond|govt|government|treasury|aggregate|oblig|corp(orate)?\b|high yield|"
                              r"inflation linked|\btips\b|souverain", re.IGNORECASE)
MOTIF_PEA = re.compile(r"\bpea\b", re.IGNORECASE)
# ETF éligibles au PEA par réplication synthétique (swap) : exposition = l'indice, pas le panier détenu
ETF_PEA_SYNTHETIQUES = {"CW8.PA", "EWLD.PA", "WPEA.PA", "DCAM.PA", "ESE.PA", "PE500.PA", "PSP5.PA", "PUST.PA",
                        "PANX.PA", "PAEEM.PA", "PCEU.PA", "RS2K.PA", "PTPXE.PA", "PAASI.PA", "MEUD.PA"}


def est_un_etf(ticker, nom, fiche=None):
    fiche = fiche or {}
    if ticker in composition_etf.ETF_INDICE or ticker in ETF_PEA_SYNTHETIQUES:
        return True
    if str(fiche.get("secteur", "")) in SECTEURS_FONDS:
        return True
    return bool(MOTIF_ETF.search(str(nom or "")))


def classer_etf(ticker, nom, fiche=None, categorie="", autre_nom=""):
    """Classe, région, secteur d'un ETF d'après l'indice suivi (et son nom). categorie, autre_nom :
    catégorie Morningstar et nom long donnés par Yahoo Finance (quand le nom de l'avis est trop abrégé)."""
    nom = str(nom or "")
    fiche = fiche or {}
    indice = composition_etf.indice_suivi(ticker, nom) or composition_etf.indice_suivi(ticker, autre_nom, categorie)
    nom = nom + " " + str(autre_nom or "")
    if MOTIF_OR.search(nom):
        return {"classe": "Or", "region": "Monde", "secteur": "Or", "indice": None}
    if MOTIF_MONETAIRE.search(nom):
        return {"classe": "Monétaire", "region": "Europe", "secteur": "Monétaire", "indice": None}
    if indice in SECTEUR_OBLIGATAIRE or MOTIF_OBLIGATION.search(nom):
        secteur = SECTEUR_OBLIGATAIRE.get(indice) or normaliser_secteur(fiche.get("secteur")) or \
            ("Obligations indexées sur l'inflation" if re.search(r"inflation|tips", nom, re.IGNORECASE) else
             "Obligations à haut rendement" if re.search(r"high yield|haut rendement", nom, re.IGNORECASE) else
             "Obligations d'entreprises" if re.search(r"corp", nom, re.IGNORECASE) else
             "Obligations émergentes" if re.search(r"emerg", nom, re.IGNORECASE) else "Obligations d'État")
        return {"classe": "Obligations", "region": REGION_PAR_INDICE.get(indice) or
                composition_etf.region_de_l_indice(indice) or fiche.get("region") or "Monde",
                "secteur": secteur, "indice": indice}
    secteur = next((s for m, s in _MOTIFS_ETF_SECTEUR if m.search(nom)), "ETF diversifié")
    region = REGION_PAR_INDICE.get(indice) or composition_etf.region_de_l_indice(indice) or fiche.get("region") \
        or "Monde (ETF)"
    return {"classe": "Actions", "region": region, "secteur": secteur, "indice": indice}


def eligible_pea_synthetique(ticker, nom):
    """ETF éligible au PEA par swap (« Amundi PEA S&P 500 ») : connu, ou « PEA » dans son nom."""
    if ticker in ETF_PEA_SYNTHETIQUES or MOTIF_PEA.search(str(nom or "")):
        return True
    # libellé abrégé d'un avis (« AM P AP M AC AP EX JAP ETF-C » : le « P » est « PEA »)
    return bool(MOTIF_ETF.search(str(nom or ""))) and bool(MOTIF_PEA.search(composition_etf.developper(nom)))


# ----------------------------------------------------------------------
# 4. Données de Yahoo Finance (avec Internet), gardées en mémoire
# ----------------------------------------------------------------------
def _lire_cache():
    try:
        return pd.read_csv(CHEMIN_CACHE, dtype=str).fillna("").set_index("ticker").to_dict("index")
    except Exception:
        return {}


def _ecrire_cache(cache):
    try:
        pd.DataFrame.from_dict(cache, orient="index").rename_axis("ticker").reset_index().to_csv(
            CHEMIN_CACHE, index=False)
    except Exception:
        pass


def infos_yahoo(tickers, en_ligne=True):
    """{ticker: {"secteur", "pays", "type", "nom"}} : cache disque, puis Yahoo Finance pour les titres
    encore inconnus (si en_ligne). Un titre que Yahoo ne connaît pas est noté vide pour ne pas être
    redemandé à chaque analyse."""
    cache = _lire_cache()
    # ancien format du cache (sans la catégorie Morningstar) : redemandé une fois
    manquants = [t for t in tickers if t not in cache or "categorie" not in cache[t]]
    if manquants and en_ligne:
        try:
            import yfinance as yf
        except ImportError:
            yf = None
        modifie = False
        for ticker in manquants[:40]:                    # au plus 40 titres par analyse
            if yf is None:
                break
            try:
                info = yf.Ticker(ticker).info or {}
            except Exception:
                continue
            cache[ticker] = {"secteur": info.get("sector", "") or "", "pays": info.get("country", "") or "",
                             "type": info.get("quoteType", "") or "", "nom": info.get("longName", "") or "",
                             "categorie": info.get("category", "") or ""}
            modifie = True
        if modifie:
            _ecrire_cache(cache)
    return {t: cache[t] for t in tickers if t in cache}


# ----------------------------------------------------------------------
# 5. Classement d'un titre
# ----------------------------------------------------------------------
def classer(ticker, nom="", fiche=None, yahoo=None):
    """{"classe", "region", "pays", "secteur", "pea_synthetique"} d'un titre.
    fiche : ligne du référentiel / de la base de titres (dict) ; yahoo : infos_yahoo()[ticker]."""
    fiche = {k: v for k, v in (fiche or {}).items() if isinstance(v, str) and v.strip() and v != "nan"}
    yahoo = yahoo or {}
    nom = nom or fiche.get("nom", "") or yahoo.get("nom", "")
    suffixe = ticker[ticker.rfind("."):] if "." in ticker else ""
    pays_place, region_place = PAYS_PAR_SUFFIXE.get(suffixe, ("", ""))

    if est_un_etf(ticker, nom, fiche) or yahoo.get("type", "").upper() in ("ETF", "MUTUALFUND") \
            or MOTIF_OR.search(str(nom)) or MOTIF_MONETAIRE.search(str(nom)) \
            or fiche.get("classe") in ("Obligations", "Or", "Monétaire"):
        # second nom : le nom officiel complet (base locale, listes Euronext / Xetra) ou celui de Yahoo,
        # utile quand le libellé de l'avis d'opéré est trop abrégé
        autre = " ".join(n for n in (fiche.get("nom", ""), yahoo.get("nom", "")) if n and n != nom)
        resultat = classer_etf(ticker, nom, fiche, yahoo.get("categorie", ""), autre)
        # une fiche du référentiel du projet, vérifiée à la main, garde la priorité pour la classe
        if fiche.get("classe") in ("Obligations", "Or", "Monétaire"):
            resultat["classe"] = fiche["classe"]
            resultat["secteur"] = normaliser_secteur(fiche.get("secteur")) or resultat["secteur"]
            resultat["region"] = fiche.get("region") or resultat["region"]
        # pays : celui de la fiche ; jamais celui de la place de cotation (un ETF Asie coté à Paris
        # n'est pas français : son exposition est celle de son indice)
        return {"classe": resultat["classe"], "region": resultat["region"],
                "pays": fiche.get("pays") or ("" if resultat.get("indice") else pays_place) or "",
                "secteur": resultat["secteur"], "pea_synthetique": eligible_pea_synthetique(ticker, nom),
                "indice": resultat.get("indice") or ""}

    secteur = (normaliser_secteur(fiche.get("secteur")) or ACTIONS_FR.get(ticker, "")
               or normaliser_secteur(yahoo.get("secteur")))
    pays = fiche.get("pays") or PAYS_ANGLAIS.get(yahoo.get("pays", ""), "") or pays_place
    region = fiche.get("region") or (composition_etf.region_du_pays(pays) if pays else "") or region_place
    return {"classe": fiche.get("classe") or "Actions", "region": region or NON_CLASSE, "pays": pays,
            "secteur": secteur or NON_CLASSE, "pea_synthetique": False, "indice": ""}


def classer_tous(tickers, noms, fiches, en_ligne=False):
    """Tableau (index : ticker) des classements. fiches : DataFrame indexé par ticker (référentiel +
    base de titres) ; noms : {ticker: nom saisi}. Avec en_ligne, Yahoo Finance complète les titres
    restés non classés."""
    fiches_dict = fiches.to_dict("index") if fiches is not None and not fiches.empty else {}
    resultat = {t: classer(t, noms.get(t, ""), fiches_dict.get(t)) for t in tickers}
    # à compléter avec Yahoo : les titres non classés, et les ETF dont l'indice n'a pas été reconnu
    # (nom trop abrégé) : le nom long et la catégorie Morningstar de Yahoo le donnent souvent
    a_completer = [t for t, c in resultat.items() if NON_CLASSE in (c["secteur"], c["region"])
                   or (c["region"] == "Monde (ETF)" and not c.get("indice"))]
    if a_completer:
        infos = infos_yahoo(a_completer, en_ligne=en_ligne)
        for t in a_completer:
            if t in infos:
                resultat[t] = classer(t, noms.get(t, ""), fiches_dict.get(t), infos[t])
    tableau = pd.DataFrame.from_dict(resultat, orient="index")
    tableau.index.name = "ticker"
    return tableau

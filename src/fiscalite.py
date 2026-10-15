"""
fiscalite.py — Performance nette d'impôts selon l'enveloppe fiscale.

Un même portefeuille ne rapporte pas la même somme "dans la poche" de
l'investisseur selon qu'il est détenu sur un compte-titres, un PEA ou un
contrat d'assurance-vie. Ce module compare les trois, pour une sortie
(vente de tout le portefeuille) aujourd'hui ou à un horizon futur.

Règles retenues (France, particulier résident, 2026) :

  Compte-titres ordinaire (CTO)
    - prélèvement forfaitaire unique (PFU, "flat tax") de 31,4 % :
      12,8 % d'impôt sur le revenu + 18,6 % de prélèvements sociaux
      (hausse de la CSG au 1er janvier 2026, auparavant 30 %) ;
    - les dividendes et les plus-values sont imposés ; les moins-values
      s'imputent sur les plus-values (pas sur les dividendes).

  Plan d'épargne en actions (PEA)
    - avant 5 ans : retrait = clôture, gain imposé à 31,4 % ;
    - après 5 ans : gain exonéré d'impôt sur le revenu, seuls les
      prélèvements sociaux de 18,6 % s'appliquent ;
    - réservé aux actions de sociétés européennes (UE / EEE) et aux fonds
      éligibles, plafond de versements de 150 000 €.

  Assurance-vie (unités de compte)
    - prélèvements sociaux de 17,2 % (non concernés par la hausse de 2026) ;
    - avant 8 ans : 12,8 % d'impôt sur le revenu (total 30 %) ;
    - après 8 ans : abattement annuel de 4 600 € sur les gains (9 200 € pour
      un couple), puis 7,5 % d'impôt (primes jusqu'à 150 000 €).

Simplifications (à citer dans le rapport) : option pour le barème progressif
ignorée, primes d'assurance-vie supposées inférieures à 150 000 €, frais de
gestion des contrats ignorés, dividendes supposés conservés dans l'enveloppe.
"""

# Taux en vigueur en 2026 (source : loi n° 2025-1403 du 30 décembre 2025 de financement de
# la sécurité sociale pour 2026, hausse de la CSG sur les revenus du capital)
IR_PFU = 0.128
PS_CAPITAL = 0.186            # dividendes, plus-values mobilières, PEA
PS_ASSURANCE_VIE = 0.172      # l'assurance-vie reste à 17,2 %
PFU_TOTAL = IR_PFU + PS_CAPITAL          # 31,4 %
IR_AV_APRES_8_ANS = 0.075
ABATTEMENT_AV = {"célibataire": 4600, "couple": 9200}

# Les taux ne sont pas lus sur Internet : ils changent avec une nouvelle version de l'application.
# L'utilisateur peut les modifier lui-même (simulation, loi changée entre deux versions) : les
# fonctions ci-dessous acceptent un dictionnaire « taux » ; sans lui, ce sont les taux légaux.
DATE_TAUX = "2026-01-01"
SOURCE_TAUX = "loi n° 2025-1403 du 30 décembre 2025 de financement de la sécurité sociale pour 2026"
TAUX_LEGAUX = {
    "ir_pfu": IR_PFU,                          # impôt sur le revenu du prélèvement forfaitaire unique
    "ps_capital": PS_CAPITAL,                  # prélèvements sociaux (CTO, PEA)
    "ps_assurance_vie": PS_ASSURANCE_VIE,      # prélèvements sociaux de l'assurance-vie
    "ir_av_apres_8_ans": IR_AV_APRES_8_ANS,    # impôt sur le revenu de l'assurance-vie après 8 ans
    "abattement_celibataire": ABATTEMENT_AV["célibataire"],
    "abattement_couple": ABATTEMENT_AV["couple"],
}
AGE_MAX_VERSION = 365          # au-delà (en jours), les taux sont peut-être dépassés : on le signale


def taux_complets(taux=None):
    """Les taux à utiliser : ceux donnés par l'utilisateur, complétés par les taux légaux."""
    complets = dict(TAUX_LEGAUX)
    complets.update({k: float(v) for k, v in (taux or {}).items() if k in TAUX_LEGAUX and v is not None})
    return complets


def taux_personnalises(taux):
    """Vrai si au moins un taux diffère du taux légal."""
    complets = taux_complets(taux)
    return any(abs(complets[k] - TAUX_LEGAUX[k]) > 1e-9 for k in TAUX_LEGAUX)


def taux_peut_etre_depasses(aujourd_hui=None):
    """Vrai si la version de l'application a plus d'un an : la loi a pu changer depuis."""
    from .version import age_en_jours
    return age_en_jours(aujourd_hui) > AGE_MAX_VERSION
DUREE_PEA = 5
DUREE_AV = 8

# Pays de l'Union européenne et de l'EEE (éligibilité PEA)
PAYS_EEE = {
    "France", "Allemagne", "Pays-Bas", "Belgique", "Luxembourg", "Italie", "Espagne", "Portugal",
    "Irlande", "Autriche", "Finlande", "Danemark", "Suède", "Grèce", "Pologne", "Tchéquie",
    "Hongrie", "Roumanie", "Bulgarie", "Croatie", "Slovénie", "Slovaquie", "Estonie", "Lettonie",
    "Lituanie", "Chypre", "Malte", "Norvège", "Islande", "Liechtenstein",
}
# Fonds indiciels connus pour être éligibles au PEA (réplication synthétique)
ETF_ELIGIBLES_PEA = {"CW8.PA", "ESE.PA"}


def _pct(x, anglais=False):
    texte = f"{x * 100:.1f}".replace(".0", "")
    return texte + "%" if anglais else texte.replace(".", ",") + " %"


def resume_taux(taux=None, langue="fr"):
    """Phrase courte des taux utilisés (rapport PDF, notes) :
    « Flat tax 31,4 % (12,8 % + 18,6 %) ; PEA après 5 ans : 18,6 % ; assurance-vie après 8 ans : 7,5 %
    après abattement + 17,2 % »."""
    tx = taux_complets(taux)
    if langue == "en":
        p = lambda x: _pct(x, anglais=True)
        return (f"Flat tax {p(tx['ir_pfu'] + tx['ps_capital'])} ({p(tx['ir_pfu'])} + {p(tx['ps_capital'])}); "
                f"PEA after {DUREE_PEA} years: {p(tx['ps_capital'])}; life insurance after {DUREE_AV} years: "
                f"{p(tx['ir_av_apres_8_ans'])} after allowance + {p(tx['ps_assurance_vie'])}")
    return (f"Flat tax {_pct(tx['ir_pfu'] + tx['ps_capital'])} ({_pct(tx['ir_pfu'])} + {_pct(tx['ps_capital'])}) ; "
            f"PEA après {DUREE_PEA} ans : {_pct(tx['ps_capital'])} ; assurance-vie après {DUREE_AV} ans : "
            f"{_pct(tx['ir_av_apres_8_ans'])} après abattement + {_pct(tx['ps_assurance_vie'])}")


def impot_sortie(gain_total, duree_annees, enveloppe, dividendes=0.0, situation="célibataire", taux=None):
    """Impôt dû si l'on vend tout le portefeuille.

    gain_total   : gain total (plus-values + dividendes), en euros
    duree_annees : ancienneté de l'enveloppe (en années)
    enveloppe    : "CTO", "PEA" ou "Assurance-vie"
    dividendes   : part du gain venant des dividendes (utile pour le CTO :
                   une moins-value ne peut pas effacer des dividendes)

    taux         : taux à utiliser (voir taux_complets) ; par défaut, les taux légaux

    Renvoie un dictionnaire : impôt sur le revenu, prélèvements sociaux, total.
    """
    tx = taux_complets(taux)
    abattement = tx["abattement_couple"] if situation == "couple" else tx["abattement_celibataire"]
    if enveloppe == "CTO":
        plus_values = gain_total - dividendes
        base = max(0.0, plus_values) + max(0.0, dividendes)
        ir, ps = tx["ir_pfu"] * base, tx["ps_capital"] * base
    elif enveloppe == "PEA":
        base = max(0.0, gain_total)
        ir = 0.0 if duree_annees >= DUREE_PEA else tx["ir_pfu"] * base
        ps = tx["ps_capital"] * base
    elif enveloppe == "Assurance-vie":
        base = max(0.0, gain_total)
        ps = tx["ps_assurance_vie"] * base
        if duree_annees >= DUREE_AV:
            ir = tx["ir_av_apres_8_ans"] * max(0.0, base - abattement)
        else:
            ir = tx["ir_pfu"] * base
    else:
        raise ValueError(f"Enveloppe inconnue : {enveloppe}")
    return {"impot_revenu": ir, "prelevements_sociaux": ps, "total": ir + ps}


def comparer_enveloppes(gain_total, capital_investi, duree_annees, dividendes=0.0,
                        situation="célibataire", taux=None):
    """Tableau comparatif des trois enveloppes pour un même gain brut.

    Renvoie une liste de dictionnaires (une ligne par enveloppe) :
    impôts, gain net, performance nette, taux d'imposition effectif, et
    nombre d'années restant avant l'avantage fiscal.
    """
    lignes = []
    for enveloppe, duree_avantage in [("CTO", None), ("PEA", DUREE_PEA), ("Assurance-vie", DUREE_AV)]:
        # duree_annees : une ancienneté commune, ou {enveloppe: ancienneté} (date d'ouverture du PEA,
        # date de souscription de l'assurance-vie)
        duree = duree_annees.get(enveloppe, 0.0) if isinstance(duree_annees, dict) else duree_annees
        imp = impot_sortie(gain_total, duree, enveloppe, dividendes, situation, taux)
        net = gain_total - imp["total"]
        lignes.append({
            "enveloppe": enveloppe,
            "gain_brut": gain_total,
            "impot_revenu": imp["impot_revenu"],
            "prelevements_sociaux": imp["prelevements_sociaux"],
            "impots": imp["total"],
            "gain_net": net,
            "performance_brute": gain_total / capital_investi if capital_investi else 0.0,
            "performance_nette": net / capital_investi if capital_investi else 0.0,
            "taux_effectif": imp["total"] / gain_total if gain_total > 0 else 0.0,
            "annees_avant_avantage": None if duree_avantage is None else max(0.0, duree_avantage - duree),
        })
    return lignes


def eligibilite_pea(positions):
    """Part de la valeur du portefeuille éligible au PEA.

    Éligibles : actions de sociétés dont le siège est dans l'UE / l'EEE, et
    fonds éligibles connus, dont les ETF éligibles par réplication synthétique (swap) : « Amundi PEA
    S&P 500 » détient des actions européennes mais suit le S&P 500. Un ETF coté à Paris sur un indice
    hors Europe sans « PEA » dans son nom n'est pas compté éligible. Les actions américaines, britanniques (depuis le
    Brexit), suisses ou japonaises ne le sont pas, ni les fonds obligataires
    et l'or (le PEA est réservé aux actions).
    Renvoie (part éligible, liste des titres non éligibles).
    """
    from .classement import ETF_PEA_SYNTHETIQUES
    eligible = [
        (t in ETF_ELIGIBLES_PEA) or (t in ETF_PEA_SYNTHETIQUES) or bool(p.get("pea_synthetique", False))
        or (str(p.get("pays", "")) in PAYS_EEE and p.get("classe", "Actions") == "Actions"
            and p.get("region", "Europe") in ("Europe", "", None))
        for t, p in positions.iterrows()
    ]
    valeurs = positions["valeur"]
    part = float(valeurs[eligible].sum() / valeurs.sum()) if valeurs.sum() else 0.0
    non_eligibles = [t for t, e in zip(positions.index, eligible) if not e]
    return part, non_eligibles

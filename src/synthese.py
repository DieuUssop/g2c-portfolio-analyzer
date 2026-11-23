"""
synthese.py — L'encadré « Ce qu'il faut retenir » en haut de la Vue d'ensemble : trois phrases
écrites par des règles simples (aucune IA), à partir des chiffres déjà calculés.

    1. la performance réelle : gain en euros, gain ÷ coût d'achat des titres, et l'écart avec le même argent
       placé dans l'indice aux mêmes dates (revue du 23/11/2026 : plus de TWR) ;
    2. le principal point de vigilance : le constat le plus grave du diagnostic des expositions
       (src/expositions.py), ou « rien d'anormal » ;
    3. ce qu'on peut faire : la première piste de ce constat, ou un rappel utile (solde espèces
       négatif, titres à vérifier, portefeuille trop récent).

Chaque phrase est une clé de traduction (français) + des valeurs : elle est traduite à l'affichage.
"""

JOURS_MIN = 20                 # en dessous, la performance annualisée n'a pas de sens


def _pct(x, signe=True):
    texte = f"{x * 100:+.1f} %" if signe else f"{x * 100:.1f} %"
    return texte.replace(".", ",")


def phrases(res, constats=None, nom_indice="l'indice", f_pct=None, f_eur=None, meme_argent=None):
    """Liste de trois (niveau, prefixe, texte, valeurs) ; niveau : "positive", "negative", "neutre",
    "alerte", "attention" ou "ok" (pastille de couleur) ; prefixe et texte sont des clés de traduction.

    Revue du 23/11/2026 : la première phrase parle de la performance RÉELLE (gain en euros, gain ÷ coût
    d'achat des titres) et la compare au même argent placé dans l'indice aux mêmes dates (meme_argent :
    résultat de livret_a.comparer_tout), jamais au TWR."""
    f_pct = f_pct or _pct
    f_eur = f_eur or (lambda x: f"{x:+,.0f} €".replace(",", " "))
    resume = res["resume"]
    sortie = []

    # 1. performance réelle
    gain = resume["gain_total"]
    rendement = gain / resume["montant_investi"] if resume.get("montant_investi") else 0.0
    valeurs = {"gain": f_eur(gain), "rendement": f_pct(rendement), "indice": nom_indice}
    if res.get("jours_de_cotation", 99) < JOURS_MIN:
        texte = ("Portefeuille récent : gain actuel {gain} ({rendement} du coût d'achat des titres) ; la comparaison "
                 "sera significative après quelques semaines.")
    elif meme_argent and meme_argent.get("indice") is not None:
        ecart = meme_argent["ecart_indice"]
        valeurs["ecart"] = f_eur(abs(ecart)).lstrip("+")
        if abs(ecart) < 0.005 * max(abs(meme_argent["portefeuille"]), 1):
            texte = ("Votre portefeuille a rapporté {gain} ({rendement} du coût d'achat des titres), autant que le "
                     "même argent placé dans {indice}.")
        elif ecart > 0:
            texte = ("Votre portefeuille a rapporté {gain} ({rendement} du coût d'achat des titres), soit {ecart} de "
                     "plus que le même argent placé dans {indice}.")
        else:
            texte = ("Votre portefeuille a rapporté {gain} ({rendement} du coût d'achat des titres), soit {ecart} de "
                     "moins que le même argent placé dans {indice}.")
    else:
        texte = "Votre portefeuille a rapporté {gain} ({rendement} du coût d'achat des titres)."
    sortie.append(("positive" if gain >= 0 else "negative", "", texte, valeurs))

    # 2. vigilance et 3. action
    graves = [c for c in (constats or []) if c["niveau"] in ("alerte", "attention")]
    if graves:
        c = graves[0]
        sortie.append((c["niveau"], "Point de vigilance :", c["titre"], dict(c["valeurs"])))
    else:
        sortie.append(("ok", "", "Aucun point de vigilance dans le diagnostic des expositions.", {}))

    if (resume.get("solde_especes") or 0) < -0.005:
        sortie.append(("attention", "À faire :", "Le solde espèces est négatif, ajoutez vos versements (« Ajouter des "
                       "opérations ») ou saisissez le solde au crayon ✏️.", {}))
    elif graves and graves[0]["pistes"]:
        sortie.append(("neutre", "Piste :", graves[0]["pistes"][0], dict(graves[0]["valeurs"])))
    else:
        sortie.append(("neutre", "", "Rien d'urgent : continuez vos versements réguliers et revenez après vos "
                       "prochains achats.", {}))
    return sortie

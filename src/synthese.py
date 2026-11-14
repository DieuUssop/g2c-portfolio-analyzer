"""
synthese.py — L'encadré « Ce qu'il faut retenir » en haut de la Vue d'ensemble : trois phrases
écrites par des règles simples (aucune IA), à partir des chiffres déjà calculés.

    1. la performance : rendement annualisé et écart avec l'indice sur la même période ;
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


def phrases(res, constats=None, nom_indice="l'indice", f_pct=None, f_eur=None):
    """Liste de trois (niveau, prefixe, texte, valeurs) ; niveau : "positive", "negative", "neutre",
    "alerte", "attention" ou "ok" (pastille de couleur) ; prefixe et texte sont des clés de traduction."""
    f_pct = f_pct or _pct
    f_eur = f_eur or (lambda x: f"{x:+,.0f} €".replace(",", " "))
    ind, av, resume = res["indicateurs"], res["avances"], res["resume"]
    sortie = []

    # 1. performance
    if res.get("jours_de_cotation", 99) < JOURS_MIN:
        sortie.append(("neutre", "", "Portefeuille récent : gain actuel {gain} ; la performance annualisée sera "
                       "significative après quelques semaines.", {"gain": f_eur(resume["gain_total"])}))
    else:
        ecart = av["twr_portefeuille_meme_periode"] - av["twr_indice"]
        if abs(ecart) < 0.005:
            texte = "Votre portefeuille rapporte {perf} par an, au même rythme que {indice} sur la même période."
        elif ecart > 0:
            texte = "Votre portefeuille rapporte {perf} par an, mieux que {indice} ({ecart} sur la même période)."
        else:
            texte = "Votre portefeuille rapporte {perf} par an, moins que {indice} ({ecart} sur la même période)."
        sortie.append(("positive" if ind["twr_annualise"] >= 0 else "negative", "", texte,
                       {"perf": f_pct(ind["twr_annualise"]), "indice": nom_indice, "ecart": f_pct(ecart)}))

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

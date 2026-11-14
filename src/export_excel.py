"""
export_excel.py — Le bouton « Excel » : tout le portefeuille dans un classeur, en un clic.

Feuilles : Résumé, Positions, Performance mensuelle, Transactions, Dividendes, Diagnostic.
Les montants sont en euros (nombres, pas du texte : on peut refaire ses calculs dans Excel).
Les titres de colonnes passent par la fonction de traduction reçue (français ou anglais).
"""

import io

import pandas as pd

from . import dividendes as dv


def _mensuel(res):
    histo = res["historique"]
    rendements = res["indicateurs"]["rendements"].dropna()
    fin_mois = histo[["valeur", "apports_nets"]].resample("ME").last()
    perf = (1 + rendements).resample("ME").prod() - 1
    tableau = fin_mois.join(perf.rename("rendement"), how="left")
    tableau.index = tableau.index.strftime("%Y-%m")
    return tableau


def classeur(res, t=lambda x, **v: x.format(**v) if v else x, constats=None, td=lambda x: x):
    """Contenu du fichier .xlsx (octets)."""
    resume, positions = res["resume"], res["positions"]
    ind = res["indicateurs"]
    lignes_resume = [
        (t("Valeur actuelle"), resume["valeur_actuelle"]),
        (t("Investi au PRU"), resume["montant_investi"]),
        (t("Gain total"), resume["gain_total"]),
        (t("Plus-values latentes"), resume["pv_latentes"]),
        (t("Plus-values réalisées"), resume["pv_realisees"]),
        (t("Dividendes et coupons"), resume["dividendes"]),
        (t("Frais de courtage"), resume["frais_totaux"]),
        (t("Solde espèces"), resume.get("solde_especes")),
        (t("TWR annualisé"), ind["twr_annualise"]),
        (t("Volatilité"), ind["volatilite"]),
        ("Max drawdown", ind["max_drawdown"]),
        (t("Période"), f"{res['historique'].index[0]:%d/%m/%Y} → {res['historique'].index[-1]:%d/%m/%Y}"),
    ]
    feuilles = {t("Résumé"): pd.DataFrame(lignes_resume, columns=[t("Indicateur"), t("Valeur")])}

    colonnes = {"nom": t("Titre"), "classe": t("Classe"), "region": t("Région"), "secteur": t("Secteur"),
                "devise": t("Devise"), "quantite": t("Quantité"), "pru": t("PRU"), "cours": t("Cours"),
                "valeur": t("Valeur"), "pv_latente": t("+/- value latente"), "pv_realisee": t("+/- value réalisée"),
                "dividendes": t("Dividendes"), "frais_totaux": t("Frais de transaction"), "poids_pct": t("Poids")}
    p = positions[[c for c in colonnes if c in positions.columns]].copy()
    for c in ("classe", "region", "secteur"):
        if c in p.columns:
            p[c] = p[c].map(td)
    feuilles[t("Positions")] = p.reset_index().rename(columns={"ticker": "Ticker", **colonnes})

    feuilles[t("Performance mensuelle")] = _mensuel(res).reset_index().rename(columns={
        "date": t("Mois"), "index": t("Mois"), "valeur": t("Valeur"), "apports_nets": t("Argent investi (apports nets)"),
        "rendement": t("Rendement du mois")})

    tr = res["transactions"].copy()
    especes = res.get("especes")
    if especes is not None and len(especes):
        tr = pd.concat([tr, especes], ignore_index=True)
    tr = tr.sort_values("date")
    tr["date"] = pd.to_datetime(tr["date"]).dt.date
    tr["type"] = tr["type"].map(td)
    feuilles[t("Transactions")] = tr[[c for c in ["date", "type", "ticker", "nom", "quantite", "prix", "frais"]
                                      if c in tr.columns]].rename(columns={
        "type": t("Type"), "nom": t("Titre"), "quantite": t("Quantité"), "prix": t("Prix (€)"), "frais": t("Frais")})

    annuel = dv.par_annee(res["transactions"])
    feuilles[t("Dividendes")] = pd.DataFrame({t("Année"): annuel.index, t("Dividendes nets"): annuel.values})

    if constats:
        feuilles[t("Diagnostic")] = pd.DataFrame([{
            t("Niveau"): t({"alerte": "Alerte", "attention": "Attention", "ok": "OK"}[c["niveau"]]),
            t("Constat"): t(c["titre"], **c["valeurs"]),
            t("Piste"): t(c["pistes"][0], **c["valeurs"]) if c["pistes"] else ""} for c in constats])

    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as ecrivain:
        for nom, tableau in feuilles.items():
            tableau.to_excel(ecrivain, sheet_name=nom[:31], index=False)
            feuille = ecrivain.sheets[nom[:31]]
            for colonne in feuille.columns:                       # largeur des colonnes selon le contenu
                largeur = max(len(str(c.value)) if c.value is not None else 0 for c in colonne)
                feuille.column_dimensions[colonne[0].column_letter].width = min(max(10, largeur + 2), 60)
            feuille.freeze_panes = "A2"
    return tampon.getvalue()

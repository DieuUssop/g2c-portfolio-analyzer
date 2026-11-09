"""
Mouvements d'espèces (retours de M. Souissi, 09/11/2026) : versements, retraits, frais de compte et
prélèvements, solde en espèces ; titres saisis par leur code ISIN ; plus-values réalisées et latentes ;
montant total des opérations ; lot de PDF dont certains ne sont pas lus.
Les relevés utilisés ici sont FICTIFS (nom et numéro de compte inventés), au format des « avis
d'opération » d'espèces de Bourse Direct : tableau Date | Désignation | Débit (€) | Crédit (€).
"""
import io

import pandas as pd
import pytest

from src import import_fichier as imp
from src import lecture_pdf
from src.portfolio import Portfolio

TRANSACTIONS = """date,type,ticker,nom,quantite,prix,frais
2024-01-02,VERSEMENT,ESPECES,Versement,0,5000,0
2024-01-02,ACHAT,ESE.PA,BNP Paribas Easy S&P 500,100,30,2
2024-06-03,VENTE,ESE.PA,BNP Paribas Easy S&P 500,40,35,2
2024-11-15,RETRAIT,ESPECES,Virement,0,200,0
2024-11-15,FRAIS,ESPECES,CSG,0,2.11,0
"""


def _portefeuille(texte=TRANSACTIONS):
    return Portfolio(io.BytesIO(texte.encode()))


def test_especes_a_part_des_titres():
    p = _portefeuille()
    assert set(p.transactions["type"]) == {"ACHAT", "VENTE"}
    assert list(p.especes["type"]) == ["VERSEMENT", "RETRAIT", "FRAIS"]
    assert p.tickers() == ["ESE.PA"]                       # « ESPECES » n'est pas un titre


def test_solde_especes():
    p = _portefeuille()
    # 5 000 − (100 × 30 + 2) + (40 × 35 − 2) − 200 − 2,11
    assert p.solde_especes() == pytest.approx(5000 - 3002 + 1398 - 200 - 2.11)
    r = p.resume()
    assert r["versements"] == 5000 and r["retraits"] == 200 and r["frais_compte"] == pytest.approx(2.11)


def test_sans_versement_le_solde_est_inconnu():
    texte = "date,type,ticker,nom,quantite,prix,frais\n2024-01-02,ACHAT,ESE.PA,ESE,10,30,1\n"
    assert _portefeuille(texte).solde_especes() is None


def test_frais_de_compte_dans_le_gain_et_l_historique():
    p = _portefeuille()
    r = p.resume_valorise({"ESE.PA": 40.0})
    attendu = 60 * (40 - 30.02) + (40 * 35 - 2 - 40 * 30.02) - 2.11
    assert r["gain_total"] == pytest.approx(attendu)
    jours = pd.bdate_range("2024-01-02", "2024-12-31")
    histo = p.historique(pd.DataFrame({"ESE.PA": 40.0}, index=jours))
    assert histo["gain"].iloc[-1] == pytest.approx(r["gain_total"])     # contrôle croisé


def test_csv_avec_versements_retraits_frais():
    csv = ("Date;Opération;ISIN;Libellé;Quantité;Cours;Frais;Montant\n"
           "02/01/2025;Versement;;;;;;5000\n"
           "02/01/2025;Achat;FR0011550185;BNP S&P;10;30,50;1,99;-306,99\n"
           "31/03/2025;Droits de garde;;;;;;-12\n"
           "05/04/2025;Retrait;;;;;;-500\n"
           "06/04/2025;Virement;;;;;;-100\n").encode()
    r = imp.importer_automatiquement(csv, chercher=lambda q: [], marche=lambda t: ({}, None))
    assert r["sur"], r["raison"]
    t = r["transactions"]
    assert list(t["type"]) == ["VERSEMENT", "ACHAT", "FRAIS", "RETRAIT", "RETRAIT"]
    assert list(t.loc[t["type"] != "ACHAT", "ticker"].unique()) == ["ESPECES"]
    assert list(t.loc[t["type"] != "ACHAT", "prix"]) == pytest.approx([5000, 12, 500, 100])
    assert t.loc[t["type"] == "FRAIS", "nom"].iloc[0] == "Droits de garde"


def test_versement_en_unites_de_compte_reste_un_achat():
    # assurance-vie : « Versement » investi dans un fonds (ISIN et nombre de parts) = achat de titres
    csv = "Date;Opération;ISIN;Quantité;Cours\n05/06/2020;Versement;FR0007054358;90,1984;33,26\n".encode()
    tableau, _ = imp.lire_tableau_brut(csv)
    df, _ = imp.appliquer_correspondance(tableau, imp.proposer_correspondance(tableau.columns),
                                         identifiants={"FR0007054358": "MSE.PA"})
    assert list(df["type"]) == ["ACHAT"]


# ----------------------------------------------------------------------
# Relevés PDF d'espèces (fictifs)
# ----------------------------------------------------------------------
def _avis_especes(lignes):
    """PDF fictif : en-tête de courtier, puis tableau Date | Désignation | Débit (€) | Crédit (€)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=A4)
    styles = getSampleStyleSheet()
    tableau = Table([["Date", "Désignation", "Débit (€)", "Crédit (€)"]] + lignes)
    tableau.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    doc.build([Paragraph("Avis d'Opération", styles["Title"]),
               Paragraph("MR DUPONT JEAN · COMPTE N° U0000000 PEA", styles["Normal"]), tableau,
               Paragraph("Les montants des colonnes Débit et Crédit sont stipulés TVA Comprise", styles["Normal"])])
    return tampon.getvalue()


def test_pdf_retrait_et_prelevements_sociaux():
    brut = _avis_especes([["15/11/2024", "REGULARISATION PEA VIRT 12345678", "200,00", ""],
                          ["15/11/2024", "REGULARISATION PEA CSG FG 9.2%", "2,11", ""],
                          ["15/11/2024", "REGULARISATION PEA NPS FG 7.5%", "1,72", ""],
                          ["15/11/2024", "REGULARISATION PEA NPS FG 7.5%", "0,11", ""]])
    r = imp.importer_automatiquement(brut, chercher=lambda q: [], marche=lambda t: ({}, None))
    assert r["sur"], r["raison"]
    t = r["transactions"]
    assert list(t["type"]) == ["RETRAIT", "FRAIS", "FRAIS", "FRAIS"]
    assert list(t["prix"]) == pytest.approx([200, 2.11, 1.72, 0.11])
    assert not t["nom"].str.contains("12345678").any()          # numéro de virement non recopié


def test_pdf_versement_et_credit():
    brut = _avis_especes([["11/04/2025", "INVESTISSEMENT ESPECES VRT DE 12345678", "", "1 000,00"]])
    t = imp.importer_automatiquement(brut, chercher=lambda q: [], marche=lambda t: ({}, None))["transactions"]
    assert list(t["type"]) == ["VERSEMENT"] and t["prix"].iloc[0] == pytest.approx(1000)
    brut = _avis_especes([["18/11/2024", "REGULARISATION PEA INT. RBT AMUNDI 202409", "", "3,80"]])
    t = imp.importer_automatiquement(brut, chercher=lambda q: [], marche=lambda t: ({}, None))["transactions"]
    assert list(t["type"]) == ["VERSEMENT"] and t["prix"].iloc[0] == pytest.approx(3.80)


def test_cellules_fusionnees_du_tableau():
    # pdfplumber rend parfois toutes les lignes dans une seule rangée (« 15/11/2024\n15/11/2024 »)
    tableau = [["Date", "Désignation", "Débit (€)", "Crédit (€)"],
               ["15/11/2024\n15/11/2024", "REGULARISATION PEA VIRT 1\nREGULARISATION PEA CSG FG 9.2%",
                "200,00\n2,11", ""]]
    ops = lecture_pdf.lire_mouvements_especes([{"texte": "", "tableaux_bruts": [tableau]}])
    assert [(o["sens"], o["montant"]) for o in ops] == [("RETRAIT", 200.0), ("FRAIS", 2.11)]


def test_ligne_de_titre_pas_lue_comme_especes():
    assert lecture_pdf.nature_mouvement_especes("ACHAT COMPTANT FR0011550185 BNP P.EASY S&P500", "debit") is None
    assert lecture_pdf.nature_mouvement_especes("DIVIDENDE LVMH", "credit") is None


# ----------------------------------------------------------------------
# Titres saisis par leur code ISIN
# ----------------------------------------------------------------------
def test_isin_en_ticker_converti_avec_son_nom():
    csv = ("date,type,ticker,nom,quantite,prix,frais\n"
           "2024-01-05,ACHAT,FR0011550185,FR0011550185,450,21.42,0\n"
           "2024-03-05,ACHAT,FR0013380607,,25,37.41,0\n").encode()
    t = imp.lire_directement(csv)
    assert list(t["ticker"]) == ["ESE.PA", "CACC.PA"]
    assert list(t["nom"]) == ["BNP Paribas Easy S&P 500 UCITS ETF", "Amundi CAC 40 UCITS ETF Acc"]


def test_libelle_egal_a_l_isin_remplace_par_le_nom():
    resolution = imp.resoudre_identifiants(["FR0011550185"], {"FR0011550185": "FR0011550185"},
                                           chercher=lambda q: [])
    assert resolution["nom"].iloc[0] == "BNP Paribas Easy S&P 500 UCITS ETF"


def test_etf_cac40_classe_en_europe():
    from src import classement
    from src.analyse import charger_fiches
    k = classement.classer_tous(["CACC.PA"], {"CACC.PA": "Amundi CAC 40 UCITS ETF Acc"}, charger_fiches())
    assert k.loc["CACC.PA", "region"] == "Europe" and k.loc["CACC.PA", "indice"] == "CAC 40"


def test_nom_du_titre():
    from src.analyse import nom_du_titre
    assert nom_du_titre("ESE.PA", "FR0011550185") == "BNP Paribas Easy S&P 500"
    assert nom_du_titre("ESE.PA", "Mon ETF") == "Mon ETF"


# ----------------------------------------------------------------------
# Montant total, lot de fichiers
# ----------------------------------------------------------------------
def test_montant_total():
    from src.vues_transactions import montant_total
    t = pd.DataFrame({"type": ["ACHAT", "VENTE", "DIVIDENDE", "VERSEMENT", "RETRAIT", "FRAIS"],
                      "quantite": [10, 4, 0, 0, 0, 0], "prix": [30, 35, 12, 1000, 200, 2.11],
                      "frais": [2, 2, 3, 0, 0, 0]})
    assert list(montant_total(t)) == pytest.approx([-302, 138, 9, 1000, -200, -2.11])


def test_lot_operations_identiques_dans_un_meme_fichier():
    from src.vues_pdf import _reunir
    frais = {"date": "2024-11-15", "type": "FRAIS", "ticker": "ESPECES", "nom": "NPS", "quantite": 0.0,
             "prix": 0.11, "frais": 0.0}
    etat = {"operations": {"a": [frais, dict(frais)], "b": [dict(frais)]}, "resumes": {}}
    contenu, _, resume = _reunir(etat, [("a.pdf", b""), ("b.pdf", b"")])
    lu = pd.read_csv(io.BytesIO(contenu))
    assert len(lu) == 2                                   # deux prélèvements dans a ; b ne fait que les répéter


def test_fichier_du_projet_avec_especes_relu_sans_assistant():
    # fichier téléchargé depuis l'application (format du projet, lignes ESPECES), renvoyé tel quel
    r = imp.importer_automatiquement(TRANSACTIONS.encode(), chercher=lambda q: [], marche=lambda t: ({}, None))
    assert r["sur"], r["raison"]
    assert list(r["transactions"]["type"]) == ["VERSEMENT", "ACHAT", "VENTE", "RETRAIT", "FRAIS"]

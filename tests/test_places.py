"""Places de cotation hors Europe / États-Unis (revue du 26/11/2026 : won coréen et Samsung non reconnus).

Données fictives : aucun relevé réel."""

from src import base_titres, classement, devises, import_fichier as imp, places


def test_chaque_place_reconnue_est_complete():
    """Une place acceptée comme suffixe de ticker a une devise, un pays et une région (table unique)."""
    for s in imp.SUFFIXES_YAHOO:
        assert s in places.PLACES_COTATION or s in places.PLACES_SECONDAIRES, s
    for code, s in imp.PLACES.items():
        assert s in places.PLACES_COTATION or s in places.PLACES_SECONDAIRES, (code, s)
    for s, (devise, pays, region, _) in places.PLACES_COTATION.items():
        assert devise and pays and region, s
        assert devises.normaliser(devise)[0] in places.DEVISES_CONNUES, s


def test_coree_et_asie_sans_internet():
    assert devises.devise_par_suffixe("005930.KS") == "KRW"
    assert devises.devise_par_suffixe("2330.TW") == "TWD"
    assert devises.devise_par_suffixe("RELIANCE.NS") == "INR"
    assert devises.devise_par_suffixe("SMSN.IL") == "USD"            # certificat de Londres, en dollars
    c = classement.classer("005930.KS", "Samsung Electronics")
    assert (c["pays"], c["region"], c["secteur"]) == ("Corée du Sud", "Émergents", "Technologie")
    assert classement.classer("SMSN.IL", "Samsung GDR")["pays"] == "Corée du Sud"


def test_sous_unites_johannesburg_et_tel_aviv():
    """Johannesburg cote en cents (ZAc) et Tel-Aviv en agorot (ILA), comme Londres en pence."""
    assert devises.normaliser("ZAc") == ("ZAR", 0.01)
    assert devises.normaliser("ILA") == ("ILS", 0.01)
    assert devises.normaliser("GBp") == ("GBP", 0.01)
    assert devises.normaliser("KRW") == ("KRW", 1.0)


def test_samsung_par_isin_nom_et_codes_de_courtier():
    assert imp.SUFFIXE_PAR_PAYS["KR"][0] == ".KS"
    assert base_titres.chercher_localement("KR7005930003")[0]["symbol"] == "005930.KS"
    assert "005930.KS" in [r["symbol"] for r in base_titres.chercher_localement("Samsung")]
    assert imp.convertir_code_global("005930 KS Equity") == "005930.KS"
    assert imp.convertir_code_global("KRX:005930") == "005930.KS"
    assert imp.convertir_code_global("SMSN LI") == "SMSN.IL"
    assert imp.normaliser_symbole_courtier("005930@KSE") == "005930.KS"
    for isin in base_titres.ISIN_ACTIONS:
        assert imp.isin_valide(isin), isin


def test_colonne_devise_en_won():
    """Une colonne « Devise » remplie de KRW est reconnue comme devise, pas comme un ticker."""
    import pandas as pd
    profil = imp.profil_colonne(pd.Series(["KRW", "KRW", "TWD", "INR"]))
    assert profil["tickers"] == 0


def test_samsung_dans_un_petit_fichier_csv():
    """Fichiers fictifs comme celui de Kévin (26/11) : code entre parenthèses après le nom, ou colonne « Symbol »
    numérique (005930), qui était prise pour les frais."""
    def importer(texte):
        return imp.importer_automatiquement(texte.encode(), chercher=lambda q: [], marche=lambda t: ({}, None))
    r = importer("Date;Titre;Quantité;Cours;Devise\n20/11/2026;SAMSUNG ELECTRONICS CO LTD (005930 KRX);10;71400;KRW\n")
    assert r["sur"], r.get("raison")
    ligne = r["transactions"].iloc[0]
    assert (ligne["ticker"], ligne["nom"]) == ("005930.KS", "SAMSUNG ELECTRONICS CO LTD")
    r = importer("Date,Symbol,Description,Quantity,Price\n2026-11-20,005930,SAMSUNG ELECTRONICS CO LTD,10,71400\n")
    ligne = r["transactions"].iloc[0]
    assert ligne["ticker"] == "005930.KS" and ligne["frais"] == 0
    # sans Internet ni essai des places européennes (sur le PC de Kévin, 005930.PA, .DE… étaient essayés en vain)
    assert imp._ticker_par_code_chiffre("005930") == "005930.KS" and imp._ticker_par_code_chiffre("5930") == "005930.KS"
    assert imp._ticker_par_code_chiffre("2330") == "2330.TW" and imp._ticker_par_code_chiffre("999999") is None
    assert imp.convertir_code_global("LVMH (MC.PA)") == "MC.PA"
    for nom in ("AIR LIQUIDE", "BNP PARIBAS", "SOCIETE GENERALE", "AMUNDI MSCI WORLD"):
        assert imp.convertir_code_global(nom) is None, nom


def test_autres_titres_coreens():
    """Tous les codes de Séoul : zéros du début rendus (Excel les retire), KOSDAQ retrouvé par les cours."""
    import pandas as pd
    assert imp.convertir_code_global("SK HYNIX INC (000660 KRX)") == "000660.KS"
    assert imp.convertir_code_global("SAMSUNG (5930 KRX)") == "005930.KS"          # 005930 lu « 5930 » par Excel
    assert imp.convertir_code_global("ECOPRO BM (247540 KOSDAQ)") == "247540.KQ"
    assert imp.convertir_code_global("247540 KQ Equity") == "247540.KQ"
    assert imp.convertir_code_global("700 HK") == "0700.HK"
    tr = pd.DataFrame({"date": pd.to_datetime(["2026-11-20"] * 2), "type": ["ACHAT"] * 2,
                       "ticker": ["005930.KS", "247540.KS"], "nom": ["Samsung", "Ecopro BM"],
                       "quantite": [1, 1], "prix": [71400.0, 150000.0], "frais": [0.0, 0.0]})
    historique = pd.DataFrame({"005930.KS": [71000.0, 71400.0]})             # rien pour 247540.KS
    corrige, changes = imp.corriger_places_jumelles(tr, historique, a_des_cours=lambda t: t == "247540.KQ")
    assert changes == {"247540.KS": "247540.KQ"} and list(corrige["ticker"]) == ["005930.KS", "247540.KQ"]
    assert imp.corriger_places_jumelles(tr, None, a_des_cours=lambda t: True)[1] == {}  # sans Internet : rien

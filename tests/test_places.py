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

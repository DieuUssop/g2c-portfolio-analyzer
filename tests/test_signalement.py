"""« Signaler un problème » : le diagnostic dit ce qui a coincé, sans aucune donnée personnelle."""
from src import signalement
from tests import avis_fictifs as af

NOM, RUE, VILLE, COMPTE, MAIL, TEL = ("M. JEAN DUPONT", "12 RUE DES LILAS", "14000 CAEN", "00012345678",
                                      "jean.dupont@exemple.fr", "06 12 34 56 78")


def _avis_avec_donnees_personnelles():
    return af._pdf([(60, 40, NOM), (60, 55, RUE), (60, 70, VILLE),
                    (60, 85, f"Compte titres n° {COMPTE}"), (60, 100, f"Contact : {MAIL} - Tél. {TEL}"),
                    (60, 130, "AVIS D'OPERE - ACHAT AU COMPTANT le 04/03/2024"),
                    (60, 150, "LVMH FR0000121014 QUANTITE : 5 COURS : 650,20 BRUT : 3 251,00"),
                    (60, 170, "COURTAGE : 4,90 NET : 3 255,90")])


def _sans_donnees_personnelles(texte):
    for secret in ("DUPONT", "LILAS", COMPTE, MAIL, "12 34 56 78"):
        assert secret not in texte, secret


def test_diagnostic_pdf_anonymise():
    etat = {}
    signalement.noter_erreur(etat, "lecture PDF", f"Opération non reconnue (compte {COMPTE})")
    texte = signalement.diagnostic(etat, _avis_avec_donnees_personnelles(), "avis DUPONT.pdf",
                                   {"Espace": "Analyse du portefeuille"})
    _sans_donnees_personnelles(texte)
    # ce qui sert à corriger la lecture est gardé
    for utile in ("Version de l'application", "FR0000121014", "04/03/2024", "650,20", "PDF texte",
                  "Dernières erreurs", "Opération non reconnue", "Modules"):
        assert utile in texte, utile


def test_diagnostic_csv_et_sans_fichier():
    csv = (f"Compte;{COMPTE}\nTitulaire;{NOM}\ndate;type;ticker;quantite;prix\n"
           "2024-03-04;ACHAT;MC.PA;5;650.2\n").encode("utf-8")
    texte = signalement.diagnostic({}, csv, "export.csv")
    _sans_donnees_personnelles(texte)
    assert "MC.PA" in texte and "csv" in texte
    assert "(aucune)" in signalement.diagnostic({})              # aucune erreur, aucun fichier : pas de plantage


def test_erreurs_gardees_sans_limite_de_memoire():
    etat = {}
    for i in range(30):
        signalement.noter_erreur(etat, "import", f"erreur {i}")
    assert len(etat["erreurs_affichees"]) == signalement.MAX_ERREURS
    assert etat["erreurs_affichees"][-1][2] == "erreur 29"

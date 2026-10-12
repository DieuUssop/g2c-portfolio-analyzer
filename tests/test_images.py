"""Photos et captures d'écran d'avis d'opéré (src/images.py) : préparation de l'image, puis la même
lecture qu'un PDF scanné. Les photos sont fabriquées à partir d'un avis fictif
(tests/avis_fictifs.py : feuille posée de biais sur une table, ombre, flou, JPEG)."""
import io

import pandas as pd
import pytest

from src import images, ocr
from src import import_fichier as imp
from tests import avis_fictifs as af


def _lecture(brut):
    grille, _ = imp.grille_pdf(brut)
    ligne = dict(zip(grille[0], grille[1]))
    q, c = imp.convertir_nombres(pd.Series([ligne["Quantité"], ligne["Cours"]]))
    return ligne["Date"], imp.classer_type(ligne["Sens"]), ligne["ISIN"], q, c


ATTENDU = ("04/03/2024", "ACHAT", "FR0000121014", 5.0, 650.2)


def test_formats_reconnus_a_leur_signature():
    from PIL import Image
    for format_ in ("JPEG", "PNG", "WEBP"):
        sortie = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(sortie, format=format_)
        assert images.est_image(sortie.getvalue()), format_
        assert imp.nature_fichier(sortie.getvalue()) == "pdf"        # lue comme un PDF image
    assert not images.est_image(b"%PDF-1.7 ...") and not images.est_image(b"date;type;ticker\n")
    assert images.est_image(b"\x00\x00\x00\x18ftypheic\x00\x00")     # photo d'iPhone


def test_sens_exif_de_la_photo():
    """Photo prise téléphone à la verticale : l'image est enregistrée couchée avec l'indication
    EXIF « tourner de 90° » ; elle est remise droite à l'ouverture."""
    if not images.opencv_disponible():                  # les photos fictives sont fabriquées avec OpenCV
        return
    brut = af.photo(af.avis_simple(), orientation_exif=6)
    image = images.ouvrir(brut)
    assert image.size == (1800, 2400)                                # portrait, comme la feuille


def test_coins_de_la_feuille_trouves():
    if not images.opencv_disponible():
        return
    coins = ((0.16, 0.10), (0.86, 0.06), (0.92, 0.94), (0.10, 0.90))
    trouves = images.ordonner_coins(images.trouver_coins(images.ouvrir(af.photo(af.avis_simple(), coins=coins))))
    for (x, y), (xa, ya) in zip(trouves, coins):
        assert abs(x - xa * 1800) < 30 and abs(y - ya * 2400) < 30
    # capture d'écran (pas de feuille sur un fond) : aucun coin
    assert images.trouver_coins(images.ouvrir(af.capture_ecran(af.avis_simple()))) is None


def test_redressement_sans_opencv():
    """Les 4 coins cliqués suffisent, même sans OpenCV (calcul de perspective avec Pillow)."""
    from PIL import Image
    image = Image.new("RGB", (400, 300), "white")
    sauvegarde = images._opencv
    images._opencv = lambda: None
    try:
        resultat = images.redresser(image, [(50, 40), (350, 60), (360, 260), (40, 250)])
    finally:
        images._opencv = sauvegarde
    assert 290 <= resultat.width <= 330 and 190 <= resultat.height <= 215


def test_taille_et_eclairage():
    from PIL import Image
    petite = Image.new("RGB", (700, 990), "white")
    assert images.ajuster_taille(petite)[1] == 3                      # capture minuscule : × 3
    assert images.ajuster_taille(Image.new("RGB", (1000, 1400), "white"))[1] == 2
    grande, facteur = images.ajuster_taille(Image.new("RGB", (4000, 3000), "white"))
    assert grande.width == images.LARGEUR_MAX and facteur < 1          # photo de 12 Mpx : réduite
    assert not images.eclairage_inegal(Image.new("RGB", (300, 300), "white"))
    degrade = Image.linear_gradient("L").resize((300, 300)).point(lambda v: 120 + v // 2).convert("RGB")
    assert images.eclairage_inegal(degrade)
    assert not images.eclairage_inegal(Image.new("RGB", (300, 300), (30, 30, 30)))   # mode sombre


@pytest.mark.parametrize("nom", ["photo_de_biais_avec_ombre", "photo_tenue_verticalement", "capture_d_ecran"])
def test_photo_lue_comme_un_pdf(nom):
    if not ocr.disponible() or (nom != "capture_d_ecran" and not images.opencv_disponible()):
        return
    avis = af.avis_simple()
    brut = {"photo_de_biais_avec_ombre": lambda: af.photo(avis),
            "photo_tenue_verticalement": lambda: af.photo(avis, orientation_exif=6),
            "capture_d_ecran": lambda: af.capture_ecran(avis)}[nom]()
    assert _lecture(brut) == ATTENDU


def test_plan_b_coins_indiques_a_la_main():
    """Coin de la feuille hors du cadre : pas de redressement automatique, mais les 4 coins
    indiqués par l'utilisateur permettent de lire la photo."""
    if not ocr.disponible() or not images.opencv_disponible():
        return
    coins = ((-0.05, 0.05), (0.85, 0.02), (0.95, 0.95), (0.08, 0.92))
    brut = af.photo(af.avis_simple(), coins=coins)
    assert images.trouver_coins(images.ouvrir(brut)) is None
    pdf, infos = images.image_en_pdf(brut, coins=[(x * 1800, y * 2400) for x, y in coins])
    assert infos["coins"] and not infos["auto"]
    assert _lecture(pdf) == ATTENDU


def test_message_d_attente_photo():
    message, _ = imp.message_attente(af.capture_ecran(af.avis_simple()))
    assert message.startswith("Photo ou capture d'écran")

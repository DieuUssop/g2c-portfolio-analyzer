"""
images.py — Lire une PHOTO ou une CAPTURE D'ÉCRAN d'avis d'opéré (JPG, PNG, WEBP, HEIC).

Principe : l'image est préparée (sens, perspective, éclairage, taille), puis convertie en un PDF
d'une page, en mémoire. Ce PDF suit ensuite EXACTEMENT la même chaîne qu'un PDF scanné
(src/ocr.py puis src/lecture_pdf.py) : aucune lecture en double, et toute amélioration de l'une
profite à l'autre.

Préparation d'une photo prise au téléphone :
    1. rotation EXIF (le téléphone enregistre le sens de prise de vue à part) ;
    2. redressement de la perspective : les 4 coins de la feuille sont cherchés automatiquement
       (OpenCV : contours de la feuille) ; si la recherche échoue, l'utilisateur peut cliquer
       lui-même sur les 4 coins (« plan B », src/vues_pdf.py) ;
    3. éclairage égalisé : le fond est estimé (flou très large) puis retiré, ce qui efface les
       ombres et le dégradé de lumière d'une photo prise sous une lampe ;
    4. taille : une capture d'écran trop petite est agrandie (×2 ou ×3), une photo trop grande
       est réduite (au-delà de l'équivalent d'une page A4 à 300 points par pouce, la lecture est
       plus lente sans être plus juste).

OpenCV (opencv-python-headless) est facultatif : sans lui, la rotation EXIF, l'agrandissement,
le redressement par les 4 coins cliqués et l'égalisation de l'éclairage (version Pillow) restent
disponibles ; seule la recherche automatique des coins manque.
"""

import io

LARGEUR_MIN = 1500          # en dessous (capture d'écran) : image agrandie
LARGEUR_MAX = 2480          # au-dessus (photo de 12 mégapixels) : image réduite (A4 à 300 points par pouce)
RESOLUTION_PDF = 216        # le PDF est rendu à l'échelle 3 par la lecture : 216 × 3 / 72 = 9 → 1 pixel = 1 pixel
EXTENSIONS = ["jpg", "jpeg", "png", "webp", "heic", "heif"]


# ----------------------------------------------------------------------
# Reconnaître et ouvrir une image
# ----------------------------------------------------------------------
def est_image(brut):
    """Vrai si les octets sont ceux d'une image JPG, PNG, WEBP ou HEIC (d'après leur signature)."""
    debut = bytes(brut[:16])
    return (debut[:3] == b"\xff\xd8\xff" or debut[:8] == b"\x89PNG\r\n\x1a\n"
            or (debut[:4] == b"RIFF" and debut[8:12] == b"WEBP")
            or (debut[4:8] == b"ftyp" and debut[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"heif", b"hevc")))


def ouvrir(brut):
    """Image (Pillow, couleurs RVB) remise dans le bon sens d'après ses données EXIF."""
    from PIL import Image, ImageOps
    if bytes(brut[4:8]) == b"ftyp":
        try:                                   # photo d'iPhone (HEIC) : bibliothèque facultative
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError as erreur:
            raise ValueError("Photo HEIC (iPhone) : convertissez-la en JPG, ou installez pillow-heif "
                             "(pip install pillow-heif).") from erreur
    image = Image.open(io.BytesIO(brut))
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        fond = Image.new("RGB", image.size, "white")
        image = image.convert("RGBA")
        fond.paste(image, mask=image.split()[-1])
        image = fond
    return image.convert("RGB")


def _opencv():
    try:
        import cv2
        return cv2
    except ImportError:
        return None


def opencv_disponible():
    return _opencv() is not None


# ----------------------------------------------------------------------
# Les 4 coins de la feuille
# ----------------------------------------------------------------------
def ordonner_coins(points):
    """4 points dans l'ordre : haut gauche, haut droit, bas droit, bas gauche."""
    import numpy as np
    p = np.asarray(points, dtype="float32").reshape(4, 2)
    somme, ecart = p.sum(axis=1), np.diff(p, axis=1).ravel()
    return np.array([p[np.argmin(somme)], p[np.argmin(ecart)], p[np.argmax(somme)], p[np.argmax(ecart)]],
                    dtype="float32")


def trouver_coins(image):
    """Les 4 coins de la feuille photographiée [(x, y)…] en pixels, ou None si aucune feuille
    nette n'est trouvée (capture d'écran, scan déjà droit, fond trop proche de la feuille…).
    Méthode (OpenCV) : image réduite, flou, contours (Canny), plus grand contour fermé ; il doit
    se ramener à un quadrilatère convexe couvrant au moins 25 % de l'image."""
    cv2 = _opencv()
    if cv2 is None:
        return None
    import numpy as np
    largeur, hauteur = image.size
    echelle = 800.0 / max(largeur, hauteur)
    petit = image.resize((max(1, int(largeur * echelle)), max(1, int(hauteur * echelle))))
    gris = cv2.cvtColor(np.asarray(petit), cv2.COLOR_RGB2GRAY)
    gris = cv2.GaussianBlur(gris, (5, 5), 0)
    bords = cv2.Canny(gris, 40, 120)
    bords = cv2.dilate(bords, np.ones((3, 3), np.uint8), iterations=2)
    contours, _ = cv2.findContours(bords, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    surface_image = petit.size[0] * petit.size[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        perimetre = cv2.arcLength(contour, True)
        for precision in (0.02, 0.03, 0.05):
            approche = cv2.approxPolyDP(contour, precision * perimetre, True)
            if len(approche) == 4 and cv2.isContourConvex(approche):
                break
        else:
            continue
        surface = cv2.contourArea(approche)
        if surface < 0.25 * surface_image:
            continue
        # la feuille occupe toute l'image (capture, scan) : rien à redresser
        x, y, l, h = cv2.boundingRect(approche)
        if l > 0.97 * petit.size[0] and h > 0.97 * petit.size[1]:
            return None
        return [(float(px) / echelle, float(py) / echelle) for px, py in approche.reshape(4, 2)]
    return None


def redresser(image, coins):
    """La feuille délimitée par 4 coins, remise à plat (correction de perspective).
    Fonctionne avec OpenCV, ou à défaut avec Pillow (même calcul)."""
    import numpy as np
    from PIL import Image
    hg, hd, bd, bg = ordonner_coins(coins)
    largeur = int(max(np.linalg.norm(hd - hg), np.linalg.norm(bd - bg)))
    hauteur = int(max(np.linalg.norm(bg - hg), np.linalg.norm(bd - hd)))
    if largeur < 50 or hauteur < 50:
        return image
    arrivee = np.array([[0, 0], [largeur - 1, 0], [largeur - 1, hauteur - 1], [0, hauteur - 1]], dtype="float32")
    depart = np.array([hg, hd, bd, bg], dtype="float32")
    cv2 = _opencv()
    if cv2 is not None:
        matrice = cv2.getPerspectiveTransform(depart, arrivee)
        resultat = cv2.warpPerspective(np.asarray(image), matrice, (largeur, hauteur),
                                       flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
        return _rogner(Image.fromarray(resultat))
    # Pillow : coefficients de la transformation « de l'arrivée vers le départ »
    lignes, valeurs = [], []
    for (x, y), (u, v) in zip(arrivee, depart):
        lignes.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        lignes.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        valeurs += [u, v]
    coefficients = np.linalg.solve(np.array(lignes, dtype=float), np.array(valeurs, dtype=float))
    return _rogner(image.transform((largeur, hauteur), Image.PERSPECTIVE, tuple(coefficients), Image.BICUBIC,
                                   fillcolor="white"))


def _rogner(image, marge=0.008):
    """Retire un mince liseré sur les bords (le bord de la table qui dépasse un peu)."""
    l, h = image.size
    return image.crop((int(l * marge), int(h * marge), l - int(l * marge), h - int(h * marge)))


# ----------------------------------------------------------------------
# Éclairage et taille
# ----------------------------------------------------------------------
def egaliser_eclairage(image):
    """Ombres et dégradé de lumière retirés : chaque point est divisé par le fond estimé autour
    de lui (flou très large), puis le contraste est étiré. Résultat en niveaux de gris."""
    import numpy as np
    from PIL import Image, ImageFilter, ImageOps
    gris = image.convert("L")
    cv2 = _opencv()
    pixels = np.asarray(gris).astype(np.float32)
    rayon = max(15, min(gris.size) // 25)
    if cv2 is not None:
        noyau = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (rayon, rayon))
        fond = cv2.morphologyEx(pixels, cv2.MORPH_CLOSE, noyau)          # le texte disparaît du fond
        fond = cv2.GaussianBlur(fond, (0, 0), rayon / 2)
    else:
        fond = np.asarray(gris.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(rayon / 2)),
                          dtype=np.float32)
    plat = np.clip(pixels / np.maximum(fond, 1.0) * 255.0, 0, 255).astype(np.uint8)
    return ImageOps.autocontrast(Image.fromarray(plat), cutoff=1)


def eclairage_inegal(image):
    """Vrai pour une page claire au fond inégal (ombre, lampe) : le fond, estimé sur une image
    réduite où le texte est effacé, varie de plus de 40 niveaux de gris."""
    import numpy as np
    from PIL import ImageFilter
    petit = image.convert("L").resize((96, 96)).filter(ImageFilter.MaxFilter(5))
    fond = np.asarray(petit, dtype=float)
    if np.median(fond) < 120:
        return False                           # page sombre : pas une ombre
    return float(np.percentile(fond, 95) - np.percentile(fond, 5)) > 40


def ajuster_taille(image):
    """Capture d'écran trop petite agrandie (×2 ou ×3), photo trop grande réduite."""
    from PIL import Image
    largeur, hauteur = image.size
    if largeur < LARGEUR_MIN and LARGEUR_MAX // largeur >= 2:
        facteur = min(3, LARGEUR_MAX // largeur)
        return image.resize((largeur * facteur, hauteur * facteur), Image.LANCZOS), facteur
    if largeur > LARGEUR_MAX:
        facteur = LARGEUR_MAX / largeur
        return image.resize((LARGEUR_MAX, max(1, int(hauteur * facteur))), Image.LANCZOS), facteur
    return image, 1


def preparer(image, coins=None):
    """Image prête pour la reconnaissance de caractères, et ce qui a été fait :
    (image, {"coins": coins utilisés ou None, "auto": coins trouvés automatiquement, "facteur": …})."""
    infos = {"coins": None, "auto": False, "facteur": 1}
    if coins is None:
        coins = trouver_coins(image)
        infos["auto"] = coins is not None
    if coins is not None:
        image = redresser(image, coins)
        infos["coins"] = [tuple(map(float, c)) for c in coins]
    # éclairage : seulement pour une photo (feuille redressée, ou fond inégal) ; une capture d'écran
    # (fond uniforme) ou une page en mode sombre (gérée par la lecture, zone par zone) est laissée telle quelle
    infos["eclairage"] = coins is not None or eclairage_inegal(image)
    if infos["eclairage"]:
        image = egaliser_eclairage(image)
    image, infos["facteur"] = ajuster_taille(image)
    return image, infos


def en_pdf(image):
    """Un PDF d'une page contenant l'image (sans texte : il sera lu par reconnaissance)."""
    sortie = io.BytesIO()
    image.convert("L").save(sortie, format="PDF", resolution=RESOLUTION_PDF)
    return sortie.getvalue()


def image_en_pdf(brut, coins=None):
    """Octets d'une image -> (octets d'un PDF prêt à lire, infos de préparation)."""
    image, infos = preparer(ouvrir(brut), coins)
    return en_pdf(image), infos

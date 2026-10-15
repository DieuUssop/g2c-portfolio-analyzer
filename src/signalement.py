"""
signalement.py — « Signaler un problème » : un fichier de diagnostic SANS données personnelles.

Quand un import échoue (ou à tout moment), l'étudiant télécharge un petit fichier texte qu'il
envoie au créateur du logiciel. Ce fichier dit ce qui a coincé, sans rien révéler de la personne :

    - version de l'application, système, modules de lecture installés (OCR, Excel, photos) ;
    - où l'on était (espace, langue) et les dernières erreurs affichées ;
    - pour le fichier envoyé : sa nature (PDF texte / image, Excel, CSV), sa taille, et son contenu
      ANONYMISÉ (lecture_pdf.anonymiser : nom, adresse, e-mail, téléphone, IBAN et numéros de
      compte masqués ; ISIN, dates, intitulés et montants gardés : ce qu'il faut pour corriger
      la lecture).

L'étudiant voit le contenu avant de le télécharger (transparence, RGPD) et décide seul de l'envoyer :
rien n'est jamais transmis automatiquement.
"""

import datetime
import platform

# Adresse (ou lien) où envoyer le diagnostic : à renseigner par l'auteur de l'application.
# Vide : le texte dit « envoyez-le à la personne qui vous a transmis l'application ».
CONTACT = "kevin.brule@etu.unicaen.fr"

MAX_ERREURS = 10
MAX_LIGNES_TABLEUR = 40          # lignes d'un CSV / Excel recopiées (anonymisées)
MAX_CARACTERES_PDF = 12000


def noter_erreur(etat, etape, message):
    """Garde une erreur affichée à l'utilisateur (etat : st.session_state ou un dictionnaire)."""
    erreurs = etat.setdefault("erreurs_affichees", [])
    erreurs.append((datetime.datetime.now().strftime("%H:%M:%S"), str(etape), str(message)[:500]))
    del erreurs[:-MAX_ERREURS]


def _modules():
    """Modules de lecture présents (ou absents) sur cet ordinateur."""
    presents = []
    for nom, module in (("Excel (openpyxl)", "openpyxl"), ("PDF (pdfplumber)", "pdfplumber"),
                        ("PDF (pypdfium2)", "pypdfium2"), ("OCR RapidOCR", "rapidocr_onnxruntime"),
                        ("OCR Tesseract", "pytesseract"), ("Photos (OpenCV)", "cv2"), ("Photos iPhone", "pillow_heif"),
                        ("Rapport PDF (reportlab)", "reportlab"), ("Yahoo Finance (yfinance)", "yfinance")):
        try:
            __import__(module)
            presents.append(f"{nom} : oui")
        except Exception:
            presents.append(f"{nom} : non")
    return presents


def _nom_sur(nom):
    """Nom de fichier sans nom propre (lecture_pdf.nom_fichier_anonyme)."""
    from .lecture_pdf import nom_fichier_anonyme
    return nom_fichier_anonyme(nom)


def _contenu_fichier(brut, nom):
    """Nature et contenu anonymisé du fichier envoyé."""
    from . import import_fichier as imp
    from . import lecture_pdf
    lignes = [f"Fichier : {_nom_sur(nom)} ({len(brut) // 1024} Ko)"]
    try:
        nature = imp.nature_fichier(brut)
    except Exception as erreur:
        return lignes + [f"Nature : inconnue ({erreur})"]
    if nature == "pdf":
        from . import images
        if images.est_image(brut):
            return lignes + ["Nature : photo / capture d'écran (contenu non recopié : image)"]
        try:
            pages = imp._pages_pdf(brut)
            texte = "\n".join(p["texte"] for p in pages)
        except Exception as erreur:
            return lignes + [f"Nature : PDF illisible ou protégé ({type(erreur).__name__})"]
        code = lecture_pdf.texte_illisible(texte)
        if len(texte.strip()) < 20 or code:
            return lignes + [f"Nature : PDF image ({len(pages)} page(s)) ou texte « codé » : contenu non recopié "
                             "(il faudrait la reconnaissance de caractères)"]
        lignes.append(f"Nature : PDF texte, {len(pages)} page(s)")
        return lignes + ["", lecture_pdf.rapport_anonymise([texte[:MAX_CARACTERES_PDF]], nom_fichier=_nom_sur(nom))]
    try:
        grille, _ = imp._grille(brut)
    except Exception as erreur:
        return lignes + [f"Nature : {nature}, illisible ({type(erreur).__name__} : {erreur})"]
    lignes.append(f"Nature : {nature}, {len(grille)} ligne(s)")
    extrait = "\n".join(" ; ".join(str(c) for c in ligne) for ligne in grille[:MAX_LIGNES_TABLEUR])
    return lignes + ["", "=== Début du fichier (anonymisé) ===", lecture_pdf.anonymiser(extrait)]


def diagnostic(etat=None, brut=None, nom_fichier=None, contexte=None):
    """Texte du diagnostic. etat : st.session_state (ou dictionnaire) ; brut / nom_fichier : le
    fichier envoyé (facultatif) ; contexte : {clé: valeur} libres (espace, langue…)."""
    from . import lecture_pdf
    from .version import VERSION
    etat = etat if etat is not None else {}
    lignes = ["Portfolio Tracker — signalement d'un problème (anonymisé)",
              f"Date : {datetime.datetime.now():%d/%m/%Y %H:%M}",
              f"Version de l'application : {VERSION}",
              f"Système : {platform.system()} {platform.release()} ({platform.machine()}) · "
              f"Python {platform.python_version()}"]
    lignes += ["", "=== Modules ==="] + _modules()
    if contexte:
        lignes += ["", "=== Où ==="] + [f"{k} : {v}" for k, v in contexte.items()]
    erreurs = etat.get("erreurs_affichees") or []
    lignes += ["", "=== Dernières erreurs affichées ==="]
    lignes += [f"{h} · {etape} · {lecture_pdf.anonymiser(message)}" for h, etape, message in erreurs] or ["(aucune)"]
    if brut:
        lignes += ["", "=== Fichier envoyé ==="]
        try:
            lignes += _contenu_fichier(bytes(brut), nom_fichier)
        except Exception as erreur:                     # le diagnostic ne doit jamais planter
            lignes.append(f"(contenu non lu : {type(erreur).__name__})")
    return "\n".join(lignes)


def consigne():
    """Où envoyer le fichier."""
    if CONTACT:
        return CONTACT
    return ""

"""
compatibilite_mac.py — Garde l'application Mac utilisable sur macOS 12 et plus.

Lancé par installateur/fabriquer_mac.sh avec le Python rangé dans l'application, APRÈS l'installation des
bibliothèques. GitHub fabrique l'application sur une machine récente (macOS 15) : pip y choisit parfois des
bibliothèques compilées pour macOS 14 ou 15 (numpy, pandas…), qui ne s'ouvriraient pas chez un étudiant
resté sur un Mac plus ancien. Ce script :
    1. lit, dans chaque fichier compilé (.so, .dylib) de chaque bibliothèque, la version minimale de macOS
       qu'il demande (« minos », commande otool) ;
    2. pour chaque bibliothèque qui demande plus que macOS 12, télécharge la version compatible macOS 12
       (pip download --platform macosx_12_0_arm64), de préférence la même version, sinon la plus récente
       compatible, et la réinstalle ;
    3. affiche ce qui reste incompatible (sans arrêter la fabrication).
Usage : python compatibilite_mac.py [version macOS minimale, 12.0 par défaut]
"""

import re
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

CIBLE = sys.argv[1] if len(sys.argv) > 1 else "12.0"
PLATEFORME = "macosx_" + CIBLE.replace(".", "_") + "_arm64"


def _version(texte):
    return tuple(int(x) for x in texte.split("."))


def _minos(fichier):
    """Version minimale de macOS demandée par un fichier compilé (None si illisible)."""
    try:
        sortie = subprocess.run(["otool", "-l", str(fichier)], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return None
    m = re.search(r"\bminos\s+([\d.]+)", sortie) or re.search(r"LC_VERSION_MIN_MACOSX.*?\n.*?version\s+([\d.]+)",
                                                             sortie, re.DOTALL)
    return m.group(1) if m else None


def trop_recentes():
    """{(nom, version): version macOS demandée} pour les bibliothèques qui demandent plus que la cible."""
    resultat = {}
    for dist in metadata.distributions():
        for fichier in dist.files or []:
            if not str(fichier).endswith((".so", ".dylib")):
                continue
            minos = _minos(dist.locate_file(fichier))
            if minos and _version(minos) > _version(CIBLE):
                cle = (dist.metadata["Name"], dist.version)
                resultat[cle] = max(resultat.get(cle, "0"), minos, key=_version)
    return resultat


def remplacer(nom, version):
    """Télécharge et réinstalle la bibliothèque compilée pour macOS {CIBLE}. Vrai si c'est fait."""
    python = f"{sys.version_info.major}{sys.version_info.minor}"
    with tempfile.TemporaryDirectory() as dossier:
        for demande in (f"{nom}=={version}", nom):
            commande = [sys.executable, "-m", "pip", "download", demande, "--no-deps", "--only-binary=:all:",
                        "--platform", PLATEFORME, "--python-version", python, "--implementation", "cp",
                        "-d", dossier, "--quiet"]
            if subprocess.run(commande).returncode == 0:
                roues = list(Path(dossier).glob("*.whl"))
                if roues and subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps",
                                             "--force-reinstall", "--quiet", str(roues[0])]).returncode == 0:
                    print(f"    {nom} : remplacé par {roues[0].name}")
                    return True
    print(f"    {nom} {version} : aucune version compatible macOS {CIBLE} trouvée")
    return False


def main():
    print(f"    Bibliothèques compilées pour une version de macOS > {CIBLE} :")
    a_remplacer = trop_recentes()
    if not a_remplacer:
        print("    aucune : l'application s'ouvrira sur macOS " + CIBLE + " et plus.")
        return
    for (nom, version), minos in sorted(a_remplacer.items()):
        print(f"    - {nom} {version} (demande macOS {minos})")
        remplacer(nom, version)
    restantes = trop_recentes()
    if restantes:
        plus_haute = max(restantes.values(), key=_version)
        print(f"    ATTENTION : encore {len(restantes)} bibliothèque(s) trop récente(s) : macOS {plus_haute} minimum.")
        for (nom, version), minos in sorted(restantes.items()):
            print(f"      {nom} {version} : macOS {minos}")
    else:
        print(f"    Tout est compatible avec macOS {CIBLE} et plus.")


if __name__ == "__main__":
    main()

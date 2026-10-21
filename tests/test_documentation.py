"""
Garde-fous de la documentation de reprise : CLAUDE.md et docs/REPRISE.md
doivent suivre le code. Ces tests échouent quand on ajoute un fichier Python sans le décrire
dans CLAUDE.md, ou un chapitre du manuel dans une seule langue.
"""

from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _texte(chemin):
    return (RACINE / chemin).read_text(encoding="utf-8")


def test_fichiers_de_reprise_presents():
    for chemin in ("CLAUDE.md", "docs/REPRISE.md"):
        assert (RACINE / chemin).is_file(), f"{chemin} manquant"


def test_chaque_module_est_decrit_dans_claude_md():
    carte = _texte("CLAUDE.md")
    oublies = [f"src/{f.name}" for f in sorted((RACINE / "src").glob("*.py"))
               if f.name != "__init__.py" and f"`{f.name}`" not in carte]
    oublies += [f.name for f in sorted(RACINE.glob("*.py")) if f"`{f.name}`" not in carte]
    assert not oublies, "À décrire dans la carte des fichiers de CLAUDE.md : " + ", ".join(oublies)


def test_manuel_dans_les_deux_langues():
    fr = {f.name for f in (RACINE / "docs/manuel/fr").glob("*.md")}
    en = {f.name for f in (RACINE / "docs/manuel/en").glob("*.md")}
    assert fr == en, f"Chapitres dans une seule langue : {sorted(fr ^ en)}"

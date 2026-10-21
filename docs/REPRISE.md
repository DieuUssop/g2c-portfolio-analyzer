# Reprendre le projet Portfolio Tracker

Guide pour les promotions suivantes du Master G2C (et tout étudiant de l'IAE Caen) qui
reprennent le projet. Aucune connaissance préalable du code n'est nécessaire.

## Contact

Pour toute question ou tout problème sur le projet, contactez directement Kévin Brulé
(équipe 2026-2027) par e-mail : **Kevin.brule2004@gmail.com**.

## 1. Récupérer le projet

1. Créer un compte GitHub (gratuit) et demander l'accès au dépôt à l'enseignant responsable.
2. Installer **GitHub Desktop** (le plus simple) puis « Clone repository » ; ou en ligne de
   commande : `git clone <adresse du dépôt>`.
3. Installer **Python 3.12** (python.org, cocher « Add Python to PATH » sous Windows).
4. Dans le dossier du projet :

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-ocr.txt      # facultatif : lecture des PDF image
python -m streamlit run app.py                     # ouvre l'application
python -m pytest                                   # vérifie que tout fonctionne
```

Si `python -m pytest` affiche « 292 passed » (ou plus), l'installation est bonne.

## 2. Travailler avec Claude

Le projet a été développé avec l'aide de Claude. Pour continuer de la même façon :

- **Claude Code** (dans un terminal ou dans VS Code) ouvert dans le dossier du projet lit
  automatiquement le fichier `CLAUDE.md` à la racine : il connaît alors l'organisation du code,
  les règles et les commandes, sans qu'il faille tout réexpliquer.
- Avec **Claude sur le web**, joindre `CLAUDE.md` et les fichiers concernés
  au début de la conversation.
- Bonnes pratiques :
  - demander une chose à la fois et faire lancer `python -m pytest` après chaque modification ;
  - lui demander de mettre à jour le manuel et la documentation (c'est écrit dans `CLAUDE.md`) ;
  - ne jamais lui envoyer un vrai relevé de compte : utiliser `python diagnostic_pdf.py
    relevé.pdf --anonyme` et envoyer le fichier anonymisé produit.

## 3. Comprendre le code

`CLAUDE.md` contient la carte complète des fichiers. Le chemin d'une analyse :

```
fichier de l'utilisateur (PDF, CSV, Excel, photo)
  └─ src/import_fichier.py  (+ lecture_pdf.py, ocr.py, images.py, releves_courtiers.py)
       └─ tableau de transactions : date, ticker, sens, quantité, prix, frais, devise
            └─ src/analyse.py : analyse_complete()
                 ├─ market_data.py / sources_secours.py : cours
                 ├─ portfolio.py : positions, valeur quotidienne
                 ├─ metrics.py, optimisation.py, simulation.py, fiscalite.py…
                 └─ classement.py / composition_etf.py : pays, secteurs, ETF
                      └─ affichage : app.py + src/vues_*.py   |   rapport PDF : src/rapport.py
```

Les guides de `docs/` (GUIDE_ETAPE_1 à 10, GUIDE_IMPORT, GUIDE_EXPOSITIONS…) expliquent la
finance et les choix de chaque étape. Le manuel (`docs/manuel/`) explique l'application du point
de vue de l'utilisateur, avec les formules (chapitre 9).

## 4. Ajouter une fonctionnalité : la marche à suivre

1. Choisir l'amélioration à apporter (idées de l'équipe, retours des utilisateurs, diagnostics reçus).
2. Créer une branche dans GitHub Desktop (« Current branch » > « New branch »).
3. Écrire le code dans le module concerné (`src/…`) et un test dans `tests/`.
4. `python -m pytest` : tout doit passer.
5. Mettre à jour : manuel FR et EN, `src/traductions.py`, README,
   `CLAUDE.md` si un fichier est ajouté.
6. Commit, push, puis « Pull request » sur GitHub pour que l'enseignant ou un camarade relise.

## 5. Publier une nouvelle version

1. Mettre à jour `src/version.py` (`VERSION = "AAAA.MM.JJ"`).
2. Sur GitHub : onglet **Actions** > « Fabriquer les installateurs » > **Run workflow**.
3. Après 20 à 40 minutes, l'installateur Windows (.exe) et Mac (.dmg) sont dans l'onglet
   **Releases**. Voir `docs/GUIDE_INSTALLATEUR.md`.

## 6. À adapter par chaque nouvelle équipe

- `src/signalement.py` : `CONTACT` = adresse e-mail qui reçoit les diagnostics « Signaler un
  problème » (aujourd'hui celle de l'équipe 2026-2027).
- Noms des auteurs : README, `src/rapport.py` (`AUTEURS`), fiche de présentation du manuel.
- `src/fiscalite.py` : taux d'imposition à vérifier chaque 1er janvier (loi de financement de la
  sécurité sociale, loi de finances) ; l'application avertit si la version a plus d'un an.
- `src/composition_etf.py` : compositions des indices à rafraîchir de temps en temps (fiches
  gratuites MSCI, S&P, FTSE, Stoxx).

## 7. Règles à ne pas oublier

- Gratuit et local : pas d'IA en ligne ni de service payant.
- Aucune donnée personnelle dans le dépôt (vrais relevés, noms, numéros de compte).
- Mieux vaut un formulaire « à compléter » qu'une valeur fausse.
- Chaque correction ajoute un test.

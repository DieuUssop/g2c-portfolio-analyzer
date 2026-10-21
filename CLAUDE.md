# CLAUDE.md — Instructions pour Claude (et pour tout développeur qui reprend le projet)

Ce fichier est lu automatiquement par Claude Code quand il ouvre le projet. Il dit ce qu'est le
projet, comment il est organisé, les règles à respecter et comment le faire évoluer.
Les étudiants trouveront un guide plus détaillé dans `docs/REPRISE.md`.

**Contact** pour toute question ou tout problème : Kévin Brulé (équipe 2026-2027),
Kevin.brule2004@gmail.com. Si une question dépasse ce qui est écrit ici, propose à
l'utilisateur de lui écrire.

## Le projet en bref

Portfolio Tracker : application de suivi et d'analyse de portefeuille boursier (actions, ETF,
obligations, fonds), en Python + Streamlit, réalisée par un groupe de 4 étudiants du Master G2C
(Gestion d'actifs, Contrôle des risques et Conformité) de l'IAE Caen, Université de Caen
Normandie (2026-2027). Elle est destinée à tous les étudiants de l'IAE et doit être reprise et
améliorée par les promotions suivantes.

- Langue du projet : **français** (code, commentaires, documentation, messages). L'interface
  existe aussi en anglais (`src/traductions.py`).
- L'utilisateur importe ses relevés de courtier (PDF, CSV, Excel, photo), l'application calcule
  performance, risque, expositions, fiscalité, optimisation, et produit un rapport PDF.
- Distribution : installateurs Windows (.exe) et Mac (.dmg) fabriqués par GitHub Actions
  (`.github/workflows/installateurs.yml`, bouton « Run workflow »).

## Règles impératives

1. **Gratuit et local.** Pas d'IA en ligne, pas d'API payante, pas de service avec clé ou compte.
   Les sources de cours sont gratuites : Yahoo Finance (yfinance), puis BCE et Stooq en secours.
2. **Données personnelles.** Ne jamais ajouter au dépôt un vrai relevé, un vrai avis d'opéré ou
   un fichier contenant un nom, une adresse, un numéro de compte ou un IBAN. Les tests utilisent
   des données FICTIVES (ex. compte `U0000000`) ou des textes anonymisés
   (`lecture_pdf.anonymiser`). Les relevés restent sur l'ordinateur de l'utilisateur.
3. **Ne jamais écraser `data/transactions.csv`** (portefeuille d'exemple utilisé par `main.py` et
   les tests). Ne jamais publier `data/comptes/` (comptes chiffrés), les caches, le journal des
   questions sans réponse ni les fichiers de diagnostic (voir `.gitignore`). La base
   `data/base/` est construite par `construire_base_titres.py` et `mettre_a_jour_titres.py` :
   ne pas la remplacer par une base de test.
4. **Jamais de valeur fausse en silence.** En cas de doute à l'import, ouvrir le formulaire
   « Compléter l'opération » ou afficher un avertissement plutôt que deviner.
5. **Tout doit passer les tests** : `python -m pytest` (292 tests au 21/10/2026). Toute
   correction ou fonctionnalité ajoute au moins un test.
6. **Pas de code en double** : une amélioration de lecture doit profiter à tous les chemins
   (PDF texte, PDF image, photo, CSV, Excel).

## Règle de mise à jour de la documentation (à chaque modification)

Quand tu modifies le projet, mets à jour dans le même commit :

- ce fichier `CLAUDE.md` : la carte des fichiers ci-dessous si un fichier est ajouté, renommé ou
  supprimé, et les règles si une décision change ;
- le manuel FR **et** EN (`docs/manuel/fr/` et `docs/manuel/en/`, mêmes fiches), puis
  `python exporter_manuel.py` pour régénérer Word et PDF ; les questions de test de l'assistant
  (`tests/questions_assistant.csv`, `_en.csv`) si une fiche est ajoutée ;
- `src/traductions.py` pour tout nouveau texte affiché ;
- le README (fonctionnalités, nombre de tests) et `docs/CHECKLIST_RENDU.md` ;
- `src/version.py` (`VERSION = "AAAA.MM.JJ"`) avant de publier une nouvelle version.

Le test `tests/test_documentation.py` échoue si un fichier Python du projet n'est pas décrit
ici ou si un chapitre du manuel n'existe que dans une langue.

## Commandes

```bash
python -m pip install -r requirements.txt        # dépendances (une fois)
python -m pip install -r requirements-ocr.txt    # facultatif : PDF image (OCR)
python -m pip install -r requirements-photos.txt # facultatif : photos
python -m streamlit run app.py                   # tableau de bord
python main.py                                   # analyse en ligne de commande
python -m pytest                                 # tous les tests
python -m pytest tests/test_classement.py -q     # un fichier de tests
python exporter_manuel.py                        # manuel Word + PDF
python mettre_a_jour_titres.py                   # listes officielles Euronext / Xetra -> base locale
python construire_base_titres.py --mise-a-jour   # derniers cours de la base hors connexion
python diagnostic_pdf.py relevé.pdf --anonyme    # ce que l'application lit dans un PDF
```

## Carte des fichiers

### Racine

| Fichier | Rôle |
|---|---|
| `app.py` | Tableau de bord Streamlit : barre latérale, 4 espaces, aiguillage vers les vues |
| `main.py` | Analyse complète en ligne de commande (terminal, graphiques, rapport PDF) |
| `lanceur.py` | Ouvre le tableau de bord dans une fenêtre d'application (utilisé par l'installateur) |
| `construire_base_titres.py` | Remplit la base locale hors connexion (`data/base/`) : titres et cours depuis 2015 |
| `mettre_a_jour_titres.py` | Télécharge les listes officielles Euronext et Xetra vers `data/base/titres.csv` |
| `diagnostic_pdf.py` | Montre ce que l'application lit dans un PDF (option `--anonyme`) |
| `exporter_manuel.py` | Fabrique le manuel Word et PDF à partir de `docs/manuel/<langue>/*.md` |
| `generer_transactions.py`, `generer_portefeuille_mondial.py`, `generer_portefeuille_diversifie.py` | Portefeuilles d'exemple |
| `*.bat`, `fabriquer_installateur.ps1`, `installateur/` | Lancement sous Windows et fabrication des installateurs (Inno Setup, script Mac) |

### `src/` — calculs

| Fichier | Rôle |
|---|---|
| `portfolio.py` | Classe `Portfolio` : positions, PRU, plus-values, dividendes, valorisation quotidienne |
| `analyse.py` | `analyse_complete` : toute l'analyse en une fonction (utilisée par app, main, rapport) |
| `metrics.py` | Indicateurs de performance et de risque (TWR, TRI, volatilité, VaR, Sharpe…) |
| `market_data.py` | Cours de bourse (yfinance), caches, mode hors connexion |
| `sources_secours.py` | Cours de secours BCE et Stooq si Yahoo ne répond pas |
| `devises.py` | Titres en devises : conversion, effet marché / effet change |
| `mouvements.py` | Ajout d'opérations, doublons, divisions et regroupements (`OPERATIONS_CONNUES`) |
| `optimisation.py` | Markowitz : frontière efficiente, Sharpe max, variance min |
| `simulation.py` | Projection Monte-Carlo |
| `stress.py` | Stress tests (crises historiques, chocs) |
| `attribution.py` | Attribution de Brinson-Fachler, performance par classe et secteur |
| `budget_risque.py` | Budget de risque, parité des risques |
| `backtest.py` | Backtest de stratégies de rééquilibrage |
| `fiscalite.py` | Fiscalité CTO / PEA / assurance-vie, taux légaux et personnalisés |
| `expositions.py` | Diagnostic d'exposition (pays, secteurs, devises, concentration) |
| `extensions.py` | Calcul groupé des analyses complémentaires |
| `indices.py` | Indices de référence (dont composites 20/80, 60/40, 80/20) |
| `version.py` | Numéro de version (date) |
| `config.py` | Réglages du projet |

### `src/` — titres et classement

| Fichier | Rôle |
|---|---|
| `base_titres.py` | Base locale des titres (ISIN, ticker, nom, classement), mémoire des titres reconnus |
| `base_officielle.py` | Lecture des listes officielles Euronext et Xetra |
| `classement.py` | Classe d'actifs, région, pays, secteur de chaque titre ; ETF PEA par swap |
| `composition_etf.py` | Composition des indices et des ETF (pays, secteurs), libellés abrégés, ETF connus |

### `src/` — import des fichiers

| Fichier | Rôle |
|---|---|
| `import_fichier.py` | Import universel CSV / Excel / PDF : colonnes, tickers, places (`PLACES`), symboles de courtiers |
| `lecture_pdf.py` | Lecture des avis d'opéré PDF par leur contenu, anonymisation, modèles appris |
| `releves_courtiers.py` | Relevé d'activité CSV d'Interactive Brokers (plusieurs tableaux) |
| `ocr.py` | Reconnaissance de caractères (RapidOCR ou Tesseract) pour les PDF image |
| `images.py` | Photos et captures d'écran (redressement OpenCV) |

### `src/` — interface Streamlit

| Fichier | Rôle |
|---|---|
| `interface.py`, `theme.py`, `graphiques_interactifs.py`, `fond_de_carte.py` | Briques visuelles, mode clair / nuit, graphiques Plotly, carte du monde |
| `graphiques.py`, `rapport.py`, `lecture.py` | Graphiques matplotlib, rapport PDF, phrases de lecture des graphiques |
| `langues.py`, `traductions.py` | Français / anglais |
| `vues_conseil.py`, `vues_gestion.py`, `vues_expositions.py`, `vues_transactions.py` | Espaces et onglets du tableau de bord |
| `vues_import.py`, `vues_mouvements.py`, `vues_pdf.py` | Assistant d'import, ajout d'opérations, formulaire « Compléter l'opération » |
| `vues_compte.py`, `comptes.py`, `coffre.py` | Comptes utilisateurs, chiffrement (PBKDF2 + AES) |
| `manuel.py`, `vues_manuel.py` | Manuel et assistant « Poser une question » (hors connexion, sans IA générative) |
| `signalement.py`, `vues_signalement.py` | « Signaler un problème » : diagnostic anonymisé (`CONTACT` = adresse du responsable) |

### Autres dossiers

- `tests/` : tests pytest ; `tests/donnees/` (avis fictifs, textes anonymisés, banc Portfolio
  Performance sous licence EPL-1.0 avec son README d'attribution).
- `docs/` : guides par thème, manuel FR/EN, `REPRISE.md`, `CHECKLIST_RENDU.md`.
- `assets/` : CSS, icônes. `data/` : portefeuille d'exemple, référentiel, base locale.

## Pièges connus

- **pandas 3 + pyarrow** (installé chez les utilisateurs) : les colonnes de texte sont au format
  Arrow ; ne pas additionner une colonne texte et une colonne `object` avec `+` (faire la
  concaténation élément par élément).
- **Streamlit** : chaque widget doit avoir une clé unique (un même bouton affiché à deux endroits
  a besoin de deux clés). Le CSS de `assets/style.css` vise des `data-testid` qui peuvent changer
  avec les versions de Streamlit : vérifier le rendu réel.
- **Tests hors ligne** : les tests ne doivent pas dépendre d'Internet ;
  `PORTFOLIO_SANS_SECOURS=1` coupe les sources de secours.
- **Regroupements d'actions** : Yahoo ne les signale pas toujours (ORPEA, Casino, Atos) ;
  les ajouter à `mouvements.OPERATIONS_CONNUES` avec la source officielle.
- **ETF PEA par swap** : l'exposition est celle de l'indice suivi (ex. S&P 500), pas celle du
  panier d'actions européennes détenu ; ne jamais alerter « hors Europe » pour ces ETF.
- Le pays d'un ETF n'est jamais déduit de sa place de cotation.

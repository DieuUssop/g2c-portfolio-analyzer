# Banc d'essai « Portfolio Performance »

Ce dossier contient **160 textes d'avis d'opéré réels** de 10 courtiers européens
(Bourse Direct, BoursoBank, Fortuneo / Arkéa Direct Bank, Keytrade Bank, DEGIRO,
Trade Republic, Crédit Mutuel, Saxo Bank, Swissquote, Trading 212) et le fichier
`attendus.json` des opérations qu'ils contiennent.

## Origine et licence

Ces fichiers proviennent des tests du logiciel libre **Portfolio Performance**
(© Andreas Buchen et les contributeurs du projet) :

- dépôt : <https://github.com/portfolio-performance/portfolio>
- chemin d'origine : `name.abuchen.portfolio.tests/src/name/abuchen/portfolio/datatransfer/pdf/<courtier>/`
- version utilisée : commit `ecc7db38f23d35882f0d100deb7c4f62e89fb10d` (octobre 2026)
- licence : **Eclipse Public License v1.0** — texte complet dans le fichier [`LICENSE`](LICENSE)
  de ce dossier.

Les fichiers `.txt` sont copiés **sans modification** (l'en-tête technique « PDFBox
Version… / Portfolio Performance Version… / ----- » est retiré au moment de la lecture,
dans le test). Les données personnelles qu'ils contenaient ont été anonymisées par les
auteurs de Portfolio Performance avant publication.

`attendus.json` est **dérivé** des tests Java du même projet (fichiers
`*PDFExtractorTest.java`) : pour chaque fichier, la date, le sens, la quantité, le
montant brut, les frais et les taxes que le lecteur de Portfolio Performance en tire.

## Utilisation

`tests/test_portfolio_performance.py` fait lire chaque texte par la lecture universelle
de l'application (`src/lecture_pdf.py`, **sans aucun modèle propre au courtier**) et
compare avec les attendus. Les seuils du test sont les résultats obtenus lors de l'ajout
du banc : ils empêchent qu'une modification fasse reculer la qualité de lecture.

Ces fichiers ne servent qu'aux tests : ils ne sont pas inclus dans les installateurs.

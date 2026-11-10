"""
portfolio.py — Le cœur du projet : la classe Portfolio.

Rôle de ce fichier :
    1. Lire l'historique des transactions (fichier CSV).
    2. Rejouer ces transactions dans l'ordre chronologique.
    3. En déduire, pour chaque titre :
         - la quantité détenue,
         - le PRU (Prix de Revient Unitaire),
         - les plus-values réalisées (ventes),
         - les dividendes perçus.

Convention du fichier CSV :
    - type = ACHAT, VENTE, DIVIDENDE, ou mouvement d'espèces VERSEMENT, RETRAIT, FRAIS
    - pour un ACHAT / une VENTE : "prix" = prix unitaire d'une action
    - pour un DIVIDENDE : "quantite" = 0 et "prix" = montant TOTAL reçu
    - pour un VERSEMENT (d’espèces sur le compte), un RETRAIT (retrait d'espèces) ou des FRAIS
      (droits de garde, frais de tenue de compte…) : ticker = ESPECES, "quantite" = 0, "prix" = montant
    - "frais" = frais de courtage en euros

Les mouvements d'espèces ne sont pas des titres : ils sont gardés à part (self.especes) et servent au
solde en espèces du compte ; les FRAIS de compte diminuent aussi le gain du portefeuille.
"""

# On importe pandas, la bibliothèque de référence pour manipuler des tableaux
# de données en Python. "pd" est le surnom qu'on lui donne par convention.
import pandas as pd


# Les seuls types de transaction que l'on accepte.
TYPES_TITRES = {"ACHAT", "VENTE", "DIVIDENDE"}
# Mouvements d'espèces du compte (pas des titres). SOLDE : solde disponible saisi à la main à une date
# (crayon de la carte « Solde espèces ») ; c'est un point de départ, pas un mouvement.
TYPES_ESPECES = {"VERSEMENT", "RETRAIT", "FRAIS", "SOLDE"}
TYPES_VALIDES = TYPES_TITRES | TYPES_ESPECES
TICKER_ESPECES = "ESPECES"


# Ordre des opérations d'une même journée pour le solde : le versement d'abord (il finance l'achat),
# puis les opérations sur titres, retraits et frais ; le solde saisi vaut en FIN de journée.
ORDRE_JOUR = {"VERSEMENT": 0, "ACHAT": 1, "DIVIDENDE": 1, "VENTE": 1, "RETRAIT": 2, "FRAIS": 2, "SOLDE": 3}


def montant_especes(type_, quantite, prix, frais):
    """Effet d'une opération sur les espèces du compte (+ entrée, − sortie), en euros."""
    if type_ == "ACHAT":
        return -(quantite * prix + frais)
    if type_ == "VENTE":
        return quantite * prix - frais
    if type_ == "DIVIDENDE":
        return prix - frais
    if type_ == "VERSEMENT":
        return float(prix)
    if type_ in ("RETRAIT", "FRAIS"):
        return -float(prix)
    return 0.0


def cumul_especes(operations):
    """Solde des espèces opération par opération.
    operations : tableau date, type, ticker, quantite, prix, frais (en euros), titres et espèces mêlés.
    Une ligne SOLDE (saisie à la main) remet le solde à son montant : les opérations antérieures n'y
    comptent plus (elles sont dans le montant saisi), les suivantes le font varier.
    Renvoie date, type, ticker, montant, solde (dans l'ordre chronologique)."""
    t = operations.copy()
    t["date"] = pd.to_datetime(t["date"])
    t["_ordre"] = t["type"].map(ORDRE_JOUR).fillna(1)
    t = t.sort_values(["date", "_ordre"], kind="stable").reset_index(drop=True)
    soldes, montants, solde = [], [], 0.0
    for _, o in t.iterrows():
        if o["type"] == "SOLDE":
            montant = float(o["prix"]) - solde
            solde = float(o["prix"])
        else:
            montant = montant_especes(o["type"], float(o["quantite"]), float(o["prix"]), float(o["frais"]))
            solde += montant
        montants.append(montant)
        soldes.append(solde)
    t["montant"], t["solde"] = montants, soldes
    return t[["date", "type", "ticker", "montant", "solde"]]


def separer_especes(transactions):
    """(opérations sur titres, mouvements d'espèces) d'un tableau de transactions."""
    especes = transactions["type"].isin(TYPES_ESPECES)
    return transactions[~especes].reset_index(drop=True), transactions[especes].reset_index(drop=True)


def lire_fichier_transactions(source):
    """Lit un fichier de transactions, même préparé ou réenregistré avec Excel :
    CSV à virgules ou à points-virgules, fichier .xlsx, lignes de titre avant le
    tableau, nombres "1 234,50", dates "15/01/2024", noms de colonnes avec accents
    ou en anglais... Le travail est fait par src/import_fichier.py.

    source : chemin, fichier ouvert (ex. envoyé depuis le tableau de bord) ou octets.
    Renvoie un tableau avec les colonnes date, type, ticker, nom, quantite, prix, frais.
    """
    from .import_fichier import lire_directement
    if isinstance(source, (bytes, bytearray)):
        brut = bytes(source)
    elif hasattr(source, "read"):
        brut = source.read()
        brut = brut.encode("utf-8") if isinstance(brut, str) else brut
    else:
        with open(source, "rb") as f:
            brut = f.read()
    return lire_directement(brut)


class Portfolio:
    """
    Une "classe" est un plan de construction. Ici, elle décrit ce qu'est un
    portefeuille : des données (les transactions, les positions) et des
    actions possibles sur ces données (les méthodes, écrites avec "def").
    """

    def __init__(self, chemin_csv):
        """
        __init__ est appelée automatiquement quand on crée un portefeuille :
            mon_portefeuille = Portfolio("data/transactions.csv")
        "self" désigne le portefeuille lui-même.
        """
        toutes = self._charger_transactions(chemin_csv)
        # Mouvements d'espèces (versements, retraits, frais de compte) : gardés à part, ce ne sont pas des titres
        self.transactions, self.especes = separer_especes(toutes)
        if self.transactions.empty:
            raise ValueError("Aucune opération sur titres (achat, vente, dividende) : seulement des mouvements "
                             "d'espèces. Ajoutez au moins un achat.")
        # Points d'attention relevés pendant le calcul (titres reçus sans prix d'achat…)
        self.alertes = []
        # On calcule les positions dès la création du portefeuille.
        self.positions = self._calculer_positions()

    # ------------------------------------------------------------------
    # 1. Lecture et vérification des données
    # ------------------------------------------------------------------
    def _charger_transactions(self, chemin_csv):
        """Lit le CSV et vérifie qu'il est cohérent.

        Le "_" au début du nom signale une méthode interne : elle sert à la
        classe elle-même, l'utilisateur n'a pas besoin de l'appeler.
        """
        # On accepte soit un fichier CSV, soit un tableau pandas déjà prêt
        # (utile à l'étape 8 : transactions converties en euros).
        if isinstance(chemin_csv, pd.DataFrame):
            df = chemin_csv.copy()
            df["date"] = pd.to_datetime(df["date"])
        else:
            # Lecture tolérante : CSV à virgules ou points-virgules (Excel en
            # français), fichier Excel .xlsx, colonnes avec accents... (voir plus haut)
            df = lire_fichier_transactions(chemin_csv)

        # Mise en forme : "achat " devient "ACHAT" (majuscules, sans espaces).
        df["type"] = df["type"].str.strip().str.upper()
        df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
        df.loc[df["type"].isin(TYPES_ESPECES), "ticker"] = TICKER_ESPECES

        # Contrôles de cohérence : mieux vaut une erreur claire qu'un
        # résultat faux sans s'en rendre compte.
        types_inconnus = set(df["type"]) - TYPES_VALIDES
        if types_inconnus:
            raise ValueError(f"Type(s) de transaction inconnu(s) : {types_inconnus}")

        if (df["prix"] < 0).any() or (df["quantite"] < 0).any():
            raise ValueError("Les prix et les quantités doivent être positifs.")

        # On trie par date : l'ordre compte pour calculer le PRU.
        return df.sort_values("date").reset_index(drop=True)

    # ------------------------------------------------------------------
    # 2. Calcul des positions (quantité, PRU, plus-values réalisées)
    # ------------------------------------------------------------------
    def _calculer_positions(self):
        """Rejoue toutes les transactions une par une.

        Règles de calcul (méthode du PRU, utilisée en France) :
          * ACHAT : le PRU devient la moyenne pondérée entre l'ancien stock
                    et les nouveaux titres. Les frais d'achat sont inclus
                    dans le PRU (ils augmentent le coût de revient).
                    nouveau PRU = (qté × PRU + q × prix + frais) / (qté + q)
          * VENTE : le PRU ne change pas. On calcule la plus-value réalisée :
                    PV = q × (prix de vente − PRU) − frais
          * DIVIDENDE : prix = montant BRUT, frais = retenue à la source, prélèvements et frais
                    retenus ; le dividende NET (brut − retenues) s'ajoute au total des dividendes.
                    Les retenues ne sont pas des frais de courtage : elles sont comptées à part.
        """
        # Un dictionnaire : pour chaque ticker, on stocke ses informations.
        positions = {}

        # iterrows() parcourt le tableau ligne par ligne.
        for _, t in self.transactions.iterrows():
            ticker = t["ticker"]

            # Première fois qu'on voit ce titre : on crée une fiche vide.
            if ticker not in positions:
                positions[ticker] = {
                    "nom": t["nom"],
                    "quantite": 0.0,
                    "pru": 0.0,
                    "pv_realisee": 0.0,
                    "dividendes": 0.0,
                    "frais_totaux": 0.0,
                    "dividendes_bruts": 0.0,
                    "retenues": 0.0,
                    "achats_payants": 0,
                }
            p = positions[ticker]
            if t["type"] == "DIVIDENDE":
                p["dividendes_bruts"] += t["prix"]
                p["retenues"] += t["frais"]
            else:
                p["frais_totaux"] += t["frais"]

            if t["type"] == "ACHAT":
                if t["prix"] > 0:
                    p["achats_payants"] += 1
                cout_ancien = p["quantite"] * p["pru"]
                cout_nouveau = t["quantite"] * t["prix"] + t["frais"]
                p["quantite"] += t["quantite"]
                p["pru"] = (cout_ancien + cout_nouveau) / p["quantite"]

            elif t["type"] == "VENTE":
                if p["quantite"] == 0 and p["achats_payants"] == 0 and \
                        not ((self.transactions["ticker"] == ticker) & (self.transactions["type"] == "ACHAT")).any():
                    # Vente d'un titre jamais acheté : titres reçus sans prix (scission / spin-off,
                    # attribution gratuite). Plutôt que d'arrêter le calcul, on les compte reçus à un
                    # prix de revient nul — toute la vente est une plus-value — et on le signale.
                    p["pv_realisee"] += t["quantite"] * t["prix"] - t["frais"]
                    self.alertes.append({"type": "vente_sans_achat", "ticker": ticker, "nom": t["nom"],
                                         "date": t["date"], "quantite": float(t["quantite"])})
                    continue
                if t["quantite"] > p["quantite"]:
                    raise ValueError(
                        f"Vente impossible le {t['date'].date()} : on vend "
                        f"{t['quantite']} {ticker} mais on n'en détient que "
                        f"{p['quantite']}."
                    )
                p["pv_realisee"] += t["quantite"] * (t["prix"] - p["pru"]) - t["frais"]
                p["quantite"] -= t["quantite"]
                # Si on a tout vendu, le PRU repart de zéro.
                if p["quantite"] == 0:
                    p["pru"] = 0.0

            elif t["type"] == "DIVIDENDE":
                p["dividendes"] += t["prix"] - t["frais"]

        # Titres détenus sans aucun achat payant : reçus gratuitement (scission, attribution)
        for ticker, p in positions.items():
            if p["quantite"] > 0 and p["achats_payants"] == 0:
                self.alertes.append({"type": "pru_nul", "ticker": ticker, "nom": p["nom"],
                                     "quantite": float(p["quantite"])})

        # On transforme le dictionnaire en tableau pandas, plus pratique.
        tableau = pd.DataFrame.from_dict(positions, orient="index")
        tableau.index.name = "ticker"
        # Montant investi encore en portefeuille = quantité × PRU.
        tableau["montant_investi"] = tableau["quantite"] * tableau["pru"]
        return tableau

    # ------------------------------------------------------------------
    # 3. Méthodes utiles pour la suite du projet
    # ------------------------------------------------------------------
    def positions_ouvertes(self):
        """Renvoie uniquement les titres encore détenus (quantité > 0)."""
        return self.positions[self.positions["quantite"] > 0]

    def tickers(self):
        """Liste des codes des titres encore détenus (ex. ["MC.PA", ...])."""
        return list(self.positions_ouvertes().index)

    def resume(self):
        """Renvoie un petit résumé chiffré du portefeuille."""
        return {
            "nb_lignes": len(self.positions_ouvertes()),
            "montant_investi": self.positions["montant_investi"].sum(),
            "pv_realisees": self.positions["pv_realisee"].sum(),
            "dividendes": self.positions["dividendes"].sum(),
            "dividendes_bruts": self.positions["dividendes_bruts"].sum(),
            "retenues": self.positions["retenues"].sum(),
            "frais_totaux": self.positions["frais_totaux"].sum(),
            "frais_compte": self.frais_de_compte(),
            "solde_especes": self.solde_especes(),
            "versements": self._total_especes("VERSEMENT"),
            "retraits": self._total_especes("RETRAIT"),
        }

    # ------------------------------------------------------------------
    # 3 bis. Espèces : versements, retraits, frais de compte, solde
    # ------------------------------------------------------------------
    def _total_especes(self, type_):
        especes = getattr(self, "especes", None)
        if especes is None or especes.empty:
            return 0.0
        return float((especes.loc[especes["type"] == type_, "prix"]).sum())

    def frais_de_compte(self):
        """Droits de garde, frais de tenue de compte… (lignes FRAIS) : payés en espèces, sans titre."""
        return self._total_especes("FRAIS")

    def a_des_especes(self):
        """Vrai si le solde des espèces est connu : versements ou retraits importés, ou solde saisi."""
        especes = getattr(self, "especes", None)
        return especes is not None and especes["type"].isin(["VERSEMENT", "RETRAIT", "SOLDE"]).any()

    def solde_saisi(self):
        """(date, montant) du solde saisi à la main (le plus récent), ou None."""
        especes = getattr(self, "especes", None)
        if especes is None or not (especes["type"] == "SOLDE").any():
            return None
        ligne = especes[especes["type"] == "SOLDE"].sort_values("date").iloc[-1]
        return pd.Timestamp(ligne["date"]), float(ligne["prix"])

    def mouvements_especes(self):
        """Toutes les entrées (+) et sorties (−) d'espèces du compte, par date : versements, retraits,
        frais de compte, l'argent des opérations sur titres (achat −, vente +, dividende net +), et le
        solde saisi à la main (point de départ). Colonnes date, type, ticker, montant, solde."""
        colonnes = ["date", "type", "ticker", "quantite", "prix", "frais"]
        especes = getattr(self, "especes", None)
        morceaux = [self.transactions[colonnes]] + ([especes[colonnes]] if especes is not None and len(especes) else [])
        return cumul_especes(pd.concat(morceaux, ignore_index=True))

    def solde_especes(self):
        """Solde en espèces du compte = versements − retraits − achats (frais compris) + ventes (nettes de
        frais) + dividendes nets − frais de compte. None si le fichier ne contient aucun versement ni
        retrait : le solde n'est alors pas connu (seules les opérations sur titres ont été importées)."""
        if not self.a_des_especes():
            return None
        return float(self.mouvements_especes()["solde"].iloc[-1])

    # ------------------------------------------------------------------
    # 4. Valorisation aux cours du marché (étape 2)
    # ------------------------------------------------------------------
    def valoriser(self, prix):
        """Calcule la valeur actuelle de chaque ligne à partir des cours.

        Paramètre : prix = dictionnaire {ticker: cours}, fourni par
                    market_data.py (ou inventé dans les tests).

        Formules :
          valeur             = quantité × cours
          plus-value latente = valeur − montant investi
                             = quantité × (cours − PRU)
          plus-value en %    = plus-value latente / montant investi
          poids              = valeur de la ligne / valeur totale

        "Latente" = non encaissée : c'est ce qu'on gagnerait (ou perdrait)
        si on vendait tout aujourd'hui, hors frais de vente.
        """
        # .copy() évite de modifier le tableau d'origine par erreur.
        tableau = self.positions_ouvertes().copy()

        # .map() va chercher, pour chaque ticker, son cours dans le dictionnaire.
        tableau["cours"] = tableau.index.map(prix)

        if tableau["cours"].isna().any():
            manquants = list(tableau.index[tableau["cours"].isna()])
            raise ValueError(f"Cours manquant pour : {manquants}")

        tableau["valeur"] = tableau["quantite"] * tableau["cours"]
        tableau["pv_latente"] = tableau["valeur"] - tableau["montant_investi"]
        tableau["pv_latente_pct"] = tableau["pv_latente"] / tableau["montant_investi"] * 100
        tableau["poids_pct"] = tableau["valeur"] / tableau["valeur"].sum() * 100

        # On trie par poids décroissant : les plus grosses lignes en premier.
        return tableau.sort_values("valeur", ascending=False)

    def resume_valorise(self, prix):
        """Résumé complet, y compris la valeur de marché.

        Performance globale (en €) = ce que le portefeuille a rapporté
        depuis le début, tout compris :
            plus-values latentes + plus-values réalisées + dividendes
        (les frais sont déjà déduits dans le PRU et dans les plus-values)
        """
        tableau = self.valoriser(prix)
        r = self.resume()
        r["valeur_actuelle"] = tableau["valeur"].sum()
        r["pv_latentes"] = tableau["pv_latente"].sum()
        # frais de compte (droits de garde…) : de l'argent dépensé sans contrepartie en titres
        r["gain_total"] = r["pv_latentes"] + r["pv_realisees"] + r["dividendes"] - r["frais_compte"]
        # Valeur du compte = titres + espèces (si le solde en espèces est connu)
        r["valeur_compte"] = r["valeur_actuelle"] + (r["solde_especes"] or 0.0)
        return r

    # ------------------------------------------------------------------
    # 5. Historique jour par jour (étape 3)
    # ------------------------------------------------------------------
    def tous_les_tickers(self):
        """Tous les titres détenus à un moment donné, même vendus depuis.
        (Il faut leur historique : ils ont compté dans la valeur passée.)"""
        return list(self.positions.index)

    def date_debut(self):
        """Date de la toute première transaction."""
        return self.transactions["date"].min()

    def historique(self, prix_hist):
        """Reconstitue la vie du portefeuille, jour de bourse par jour de bourse.

        Paramètre : prix_hist = tableau des cours de clôture
                    (une ligne par jour, une colonne par ticker).

        Renvoie un tableau avec, pour chaque jour :
          valeur              = Σ (quantité détenue ce jour-là × cours du jour)
          flux                = argent que l'investisseur a mis (+) ou
                                récupéré (−) ce jour-là :
                                  ACHAT     : + (quantité × prix + frais)
                                  VENTE     : − (quantité × prix − frais)
                                  DIVIDENDE : − (montant − frais)
          apports_nets        = somme de tous les flux depuis le début
                                = argent "de sa poche" encore investi
          gain                = valeur − apports_nets
                                = ce que le portefeuille a rapporté à cette date

        Le dernier jour, "gain" doit être égal au "GAIN TOTAL" de l'étape 2 :
        c'est une vérification croisée de nos deux méthodes de calcul.
        """
        # --- a) Le calendrier : les jours de bourse depuis le 1er achat ---
        prix = prix_hist.sort_index()
        prix = prix[prix.index >= self.date_debut()]
        if prix.empty:
            raise ValueError("Aucun cours disponible après la première transaction.")
        calendrier = prix.index

        recus = {(a["ticker"], a["date"]) for a in self.alertes if a["type"] == "vente_sans_achat"}
        jamais_achetes = {a["ticker"] for a in self.alertes if a["type"] == "vente_sans_achat"} - \
            set(self.transactions.loc[self.transactions["type"] == "ACHAT", "ticker"])
        manquants = [t for t in self.tous_les_tickers() if t not in prix.columns and t not in jamais_achetes]
        if manquants:
            raise ValueError(f"Historique de cours manquant pour : {manquants}")

        # --- b) On rattache chaque transaction à un jour de bourse ---
        # Une opération saisie un samedi est rattachée au lundi suivant.
        # searchsorted() donne la position du 1er jour du calendrier >= la date.
        t = self.transactions.copy()
        position = calendrier.searchsorted(t["date"])
        position = position.clip(max=len(calendrier) - 1)  # sécurité : date future
        t["jour"] = calendrier[position]

        # --- c) Variation de quantité de chaque transaction ---
        # ACHAT : +quantité, VENTE : −quantité, DIVIDENDE : 0
        signe = t["type"].map({"ACHAT": 1, "VENTE": -1, "DIVIDENDE": 0})
        t["variation_qte"] = signe * t["quantite"]
        # titres reçus sans achat (scission) puis vendus : la vente n'enlève rien de ce qui a été compté
        if recus:
            sans_achat = pd.Series([(tk, d) in recus for tk, d in zip(t["ticker"], t["date"])], index=t.index)
            t.loc[sans_achat & (t["type"] == "VENTE"), "variation_qte"] = 0.0

        # --- d) Flux d'argent de chaque transaction (voir la docstring) ---
        montant = t["quantite"] * t["prix"]
        t["flux"] = 0.0
        t.loc[t["type"] == "ACHAT", "flux"] = montant + t["frais"]
        t.loc[t["type"] == "VENTE", "flux"] = -(montant - t["frais"])
        t.loc[t["type"] == "DIVIDENDE", "flux"] = -(t["prix"] - t["frais"])

        # --- e) Quantité détenue chaque jour, pour chaque titre ---
        # pivot_table : on range les variations dans un tableau
        #   lignes = jours, colonnes = tickers (somme si plusieurs le même jour).
        # reindex : on ajoute tous les jours du calendrier (0 = rien ne bouge).
        # cumsum  : somme cumulée -> la quantité détenue à chaque date.
        variations = t.pivot_table(index="jour", columns="ticker",
                                   values="variation_qte", aggfunc="sum")
        quantites = variations.reindex(calendrier).fillna(0).cumsum()

        # --- f) Valeur du portefeuille chaque jour ---
        # ffill : un jour férié sur une seule place, on garde le dernier cours.
        # bfill : sécurité si le tout premier cours manque.
        quantites = quantites[[c for c in quantites.columns if c in prix.columns]]
        cours = prix[quantites.columns].ffill().bfill()
        valeur_par_titre = quantites * cours
        valeur = valeur_par_titre.sum(axis=1)
        # On garde la valeur de chaque ligne jour par jour : elle sert à
        # l'attribution de performance (étape 10).
        self.valeur_par_titre = valeur_par_titre

        # --- g) Flux, apports nets et gain ---
        flux = t.groupby("jour")["flux"].sum().reindex(calendrier).fillna(0)
        # frais de compte (droits de garde…) : un apport qui ne crée aucune valeur -> le gain baisse d'autant
        # (les versements et retraits d'espèces ne changent rien à la poche titres : ils ne sont pas des flux ici)
        frais = getattr(self, "especes", None)
        frais = frais[frais["type"] == "FRAIS"] if frais is not None and not frais.empty else None
        if frais is not None and not frais.empty:
            jours = calendrier[calendrier.searchsorted(frais["date"]).clip(max=len(calendrier) - 1)]
            flux = flux.add(pd.Series(frais["prix"].values, index=jours).groupby(level=0).sum(), fill_value=0.0)

        resultat = pd.DataFrame({
            "valeur": valeur,
            "flux": flux,
            "apports_nets": flux.cumsum(),
        })
        resultat["gain"] = resultat["valeur"] - resultat["apports_nets"]
        resultat.index.name = "date"
        return resultat

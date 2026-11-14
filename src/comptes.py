"""
comptes.py — Les comptes utilisateurs et leur espace personnel chiffré.

Chaque utilisateur crée un compte (identifiant + mot de passe) et enregistre
ses portefeuilles dans son espace. Personne d'autre ne peut les lire.

Organisation sur le disque (dossier data/comptes/) :
    comptes.json          identifiant, sels et empreinte de chaque compte
                          (AUCUN mot de passe, AUCUNE donnée de portefeuille)
    3f9a2c.../            un dossier par compte, au nom aléatoire
        index.enc         la liste chiffrée de ses portefeuilles (noms, dates)
        8b1e....enc       chaque portefeuille, chiffré

Sécurité (voir coffre.py) :
    - mot de passe remplacé par une empreinte salée (PBKDF2, 600 000 itérations) ;
    - données chiffrées avec une clé tirée du mot de passe, gardée en mémoire ;
    - message d'erreur identique pour un identifiant inconnu ou un mauvais mot
      de passe (on ne révèle pas quels comptes existent) ;
    - blocage d'une minute après 5 essais ratés.
"""

import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path

import pandas as pd

from . import coffre

DOSSIER = Path(os.environ.get("PORTFOLIO_COMPTES", Path(__file__).resolve().parent.parent / "data" / "comptes"))
MOTIF_IDENTIFIANT = re.compile(r"^[a-z0-9._-]{3,30}$")
LONGUEUR_MIN = 8
ESSAIS_MAX = 5
DUREE_BLOCAGE = 60                 # secondes
VERSIONS_MAX = 5                   # versions précédentes gardées par portefeuille (« Annuler »)
JOURNAL_MAX = 50                   # lignes du journal des modifications gardées par portefeuille
SAUVEGARDE_JOURS = 7               # une sauvegarde automatique par semaine...
SAUVEGARDES_MAX = 4                # ... les 4 dernières sont gardées
# Type de compte d'un portefeuille (enveloppe fiscale) : sert à la fiscalité et à la vue « Tous mes comptes »
ENVELOPPES = ["PEA", "CTO", "Assurance-vie", "Autre"]


class ErreurCompte(Exception):
    """Erreur à afficher à l'utilisateur. Le message (en français) sert aussi de clé
    de traduction ; les valeurs variables sont gardées à part."""

    def __init__(self, message, **valeurs):
        super().__init__(message)
        self.message, self.valeurs = message, valeurs

    def __str__(self):
        return self.message.format(**self.valeurs)


# ======================================================================
# Le registre des comptes
# ======================================================================
def _dossier():
    return Path(DOSSIER)


def _ecrire(chemin, octets):
    """Écriture "atomique" : fichier temporaire puis renommage (jamais de fichier à moitié écrit)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_name(chemin.name + ".tmp")
    temporaire.write_bytes(octets)
    os.replace(temporaire, chemin)


def _lire_registre():
    chemin = _dossier() / "comptes.json"
    if not chemin.exists():
        return {"version": 1, "comptes": {}}
    return json.loads(chemin.read_text(encoding="utf-8"))


def _ecrire_registre(registre):
    _ecrire(_dossier() / "comptes.json", json.dumps(registre, indent=1, ensure_ascii=False).encode("utf-8"))


def normaliser_identifiant(identifiant):
    return str(identifiant).strip().lower()


def nombre_de_comptes():
    return len(_lire_registre()["comptes"])


# ======================================================================
# Création et connexion
# ======================================================================
def creer_compte(identifiant, mot_de_passe, confirmation=None):
    """Crée un compte et renvoie la session ouverte."""
    identifiant = normaliser_identifiant(identifiant)
    if not MOTIF_IDENTIFIANT.match(identifiant):
        raise ErreurCompte("Identifiant invalide : 3 à 30 caractères parmi lettres minuscules, chiffres, « . », "
                           "« _ » et « - ».")
    if len(mot_de_passe) < LONGUEUR_MIN:
        raise ErreurCompte("Le mot de passe doit contenir au moins {n} caractères.", n=LONGUEUR_MIN)
    if confirmation is not None and confirmation != mot_de_passe:
        raise ErreurCompte("Les deux mots de passe ne sont pas identiques.")
    registre = _lire_registre()
    if identifiant in registre["comptes"]:
        raise ErreurCompte("Cet identifiant est déjà utilisé.")
    fiche = {
        "dossier": uuid.uuid4().hex,
        "sel_empreinte": coffre.nouveau_sel(),
        "sel_cle": coffre.nouveau_sel(),
        "iterations": coffre.ITERATIONS,
        "cree": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "echecs": 0,
        "bloque_jusqua": 0,
    }
    fiche["empreinte"] = coffre.empreinte(mot_de_passe, fiche["sel_empreinte"], fiche["iterations"])
    registre["comptes"][identifiant] = fiche
    _ecrire_registre(registre)
    session = Session(identifiant, fiche, coffre.cle_de_chiffrement(mot_de_passe, fiche["sel_cle"], fiche["iterations"]))
    session._sauver_index([])
    return session


def connecter(identifiant, mot_de_passe):
    """Ouvre la session d'un compte. Même message d'erreur pour un identifiant
    inconnu et un mauvais mot de passe."""
    identifiant = normaliser_identifiant(identifiant)
    registre = _lire_registre()
    fiche = registre["comptes"].get(identifiant)
    if fiche is None:
        coffre.empreinte(mot_de_passe, coffre.nouveau_sel())      # même durée de calcul qu'un vrai essai
        raise ErreurCompte("Identifiant ou mot de passe incorrect.")
    attente = int(fiche.get("bloque_jusqua", 0) - time.time())
    if attente > 0:
        raise ErreurCompte("Trop d'essais ratés : réessayez dans {n} secondes.", n=attente)
    if not coffre.verifier(mot_de_passe, fiche["sel_empreinte"], fiche["empreinte"], fiche["iterations"]):
        fiche["echecs"] = fiche.get("echecs", 0) + 1
        if fiche["echecs"] >= ESSAIS_MAX:
            fiche["echecs"], fiche["bloque_jusqua"] = 0, time.time() + DUREE_BLOCAGE
        _ecrire_registre(registre)
        raise ErreurCompte("Identifiant ou mot de passe incorrect.")
    if fiche.get("echecs"):
        fiche["echecs"] = 0
        _ecrire_registre(registre)
    return Session(identifiant, fiche, coffre.cle_de_chiffrement(mot_de_passe, fiche["sel_cle"], fiche["iterations"]))


# ======================================================================
# L'espace personnel d'un utilisateur connecté
# ======================================================================
class Session:
    """Un utilisateur connecté. La clé de chiffrement n'existe qu'ici, en mémoire."""

    def __init__(self, identifiant, fiche, cle):
        self.identifiant = identifiant
        self.dossier = _dossier() / fiche["dossier"]
        self._cle = cle
        self.derniere_activite = time.time()

    def __repr__(self):                     # la clé n'apparaît jamais dans un affichage
        return f"Session({self.identifiant!r})"

    # -- index (liste des portefeuilles) --
    def _index(self):
        chemin = self.dossier / "index.enc"
        if not chemin.exists():
            return []
        return json.loads(coffre.dechiffrer(self._cle, chemin.read_bytes()).decode("utf-8"))

    def _sauver_index(self, index):
        _ecrire(self.dossier / "index.enc", coffre.chiffrer(self._cle, json.dumps(index, ensure_ascii=False)))

    # -- préférences d'affichage (mode nuit...) : chiffrées comme le reste --
    def preferences(self):
        chemin = self.dossier / "preferences.enc"
        if not chemin.exists():
            return {}
        try:
            return json.loads(coffre.dechiffrer(self._cle, chemin.read_bytes()).decode("utf-8"))
        except Exception:
            return {}

    def preference(self, cle, defaut=None):
        return self.preferences().get(cle, defaut)

    def definir_preference(self, cle, valeur):
        prefs = self.preferences()
        if prefs.get(cle) == valeur:
            return
        prefs[cle] = valeur
        _ecrire(self.dossier / "preferences.enc", coffre.chiffrer(self._cle, json.dumps(prefs, ensure_ascii=False)))

    # -- portefeuilles --
    def lister(self):
        """Portefeuilles de l'utilisateur : liste de dictionnaires (id, nom, cree, maj, operations)."""
        return sorted(self._index(), key=lambda p: p["nom"].lower())

    def enregistrer(self, nom, contenu, identifiant=None, garder_precedente=False, action=None):
        """Enregistre (ou remplace) un portefeuille ; contenu = fichier CSV au format du projet (octets).

        La version remplacée est toujours conservée (chiffrée, VERSIONS_MAX au plus) pour pouvoir
        « Annuler la dernière modification » plusieurs fois. garder_precedente est gardé pour les
        appels existants. action : texte du journal ; sinon déduit du nombre d'opérations."""
        nom = str(nom).strip() or "Portefeuille"
        index = self._index()
        if identifiant is None:
            existant = next((p for p in index if p["nom"].lower() == nom.lower()), None)
            identifiant = existant["id"] if existant else uuid.uuid4().hex
        maintenant = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
        operations = max(0, contenu.count(b"\n") - 1) if isinstance(contenu, bytes) else 0
        fichier = self.dossier / f"{identifiant}.enc"
        fiche = next((p for p in index if p["id"] == identifiant), None)
        if fiche and fichier.exists():
            if coffre.dechiffrer(self._cle, fichier.read_bytes()) == contenu:     # contenu identique :
                fiche["nom"] = nom                                                  # pas de nouvelle version
                self._sauver_index(index)
                return identifiant
            versions = _versions(fiche, self.dossier, identifiant)
            nom_version = f"{identifiant}.v{uuid.uuid4().hex[:8]}.enc"
            os.replace(fichier, self.dossier / nom_version)
            versions.append({"fichier": nom_version, "maj": fiche.get("maj"), "operations": fiche.get("operations")})
            while len(versions) > VERSIONS_MAX:
                (self.dossier / versions.pop(0)["fichier"]).unlink(missing_ok=True)
            fiche["versions"] = versions
            fiche["precedente"] = {k: versions[-1][k] for k in ("maj", "operations")}
            avant = fiche.get("operations") or 0
            if action is None:
                action = ("ajout" if operations > avant else "suppression" if operations < avant else "modification")
            _noter(fiche, maintenant, action, abs(operations - avant), operations)
        _ecrire(fichier, coffre.chiffrer(self._cle, contenu))
        if fiche:
            fiche.update({"nom": nom, "maj": maintenant, "operations": operations})
        else:
            fiche = {"id": identifiant, "nom": nom, "cree": maintenant, "maj": maintenant, "operations": operations}
            _noter(fiche, maintenant, action or "creation", operations, operations)
            index.append(fiche)
        self._sauver_index(index)
        return identifiant

    def lire(self, identifiant):
        """Contenu (octets, CSV en clair) d'un portefeuille de l'utilisateur."""
        if identifiant not in {p["id"] for p in self._index()}:
            raise ErreurCompte("Portefeuille introuvable.")
        return coffre.dechiffrer(self._cle, (self.dossier / f"{identifiant}.enc").read_bytes())

    def annuler_dernier_ajout(self, identifiant):
        """Revient à la version précédente d'un portefeuille (avant le dernier ajout, la dernière
        suppression ou correction). Peut être répété : jusqu'à VERSIONS_MAX versions en arrière."""
        index = self._index()
        fiche = next((p for p in index if p["id"] == identifiant), None)
        versions = _versions(fiche, self.dossier, identifiant) if fiche else []
        if not versions or not (self.dossier / versions[-1]["fichier"]).exists():
            raise ErreurCompte("Aucun ajout à annuler.")
        derniere = versions.pop()
        os.replace(self.dossier / derniere["fichier"], self.dossier / f"{identifiant}.enc")
        _noter(fiche, pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), "annulation", 0, derniere["operations"])
        fiche.update({"maj": derniere["maj"], "operations": derniere["operations"], "versions": versions})
        if versions:
            fiche["precedente"] = {k: versions[-1][k] for k in ("maj", "operations")}
        else:
            fiche.pop("precedente", None)
        self._sauver_index(index)

    def journal(self, identifiant):
        """Journal des modifications d'un portefeuille, de la plus récente à la plus ancienne :
        liste de {date, action, n, operations}."""
        fiche = next((p for p in self._index() if p["id"] == identifiant), None)
        return list(reversed((fiche or {}).get("journal", [])))

    def definir_enveloppe(self, identifiant, enveloppe):
        """Type de compte du portefeuille (PEA, CTO, Assurance-vie, Autre) ; None l'efface."""
        if enveloppe is not None and enveloppe not in ENVELOPPES:
            raise ErreurCompte("Type de compte inconnu.")
        index = self._index()
        for p in index:
            if p["id"] == identifiant:
                if enveloppe is None:
                    p.pop("enveloppe", None)
                else:
                    p["enveloppe"] = enveloppe
        self._sauver_index(index)

    def enveloppe(self, identifiant):
        return next((p.get("enveloppe") for p in self._index() if p["id"] == identifiant), None)

    # -- sauvegardes automatiques (copies des fichiers chiffrés, dans le dossier du compte) --
    def _dossier_sauvegardes(self):
        return self.dossier / "sauvegardes"

    def sauvegardes(self):
        """Sauvegardes disponibles, de la plus récente à la plus ancienne : liste de {id, date, portefeuilles}."""
        dossier = self._dossier_sauvegardes()
        if not dossier.exists():
            return []
        liste = []
        for d in sorted((x for x in dossier.iterdir() if x.is_dir()), reverse=True):
            liste.append({"id": d.name, "date": f"{d.name[:4]}-{d.name[4:6]}-{d.name[6:8]} {d.name[9:11]}:{d.name[11:13]}",
                          "portefeuilles": sum(1 for f in d.glob("*.enc") if f.name.count(".") == 1
                                               and f.name not in ("index.enc", "preferences.enc"))})
        return liste

    def sauvegarder(self, maintenant=None):
        """Copie chiffrée de tout l'espace (index, portefeuilles, préférences). Garde les SAUVEGARDES_MAX
        dernières. Renvoie l'identifiant de la sauvegarde."""
        maintenant = pd.Timestamp(maintenant) if maintenant is not None else pd.Timestamp.now()
        nom = maintenant.strftime("%Y%m%d-%H%M%S")
        cible = self._dossier_sauvegardes() / nom
        cible.mkdir(parents=True, exist_ok=True)
        for f in self.dossier.glob("*.enc"):
            if ".v" not in f.name and ".prec." not in f.name:          # pas les versions d'annulation
                shutil.copy2(f, cible / f.name)
        for ancienne in [x["id"] for x in self.sauvegardes()][SAUVEGARDES_MAX:]:
            shutil.rmtree(self._dossier_sauvegardes() / ancienne, ignore_errors=True)
        return nom

    def sauvegarde_automatique(self, maintenant=None):
        """Sauvegarde si la dernière date de plus de SAUVEGARDE_JOURS jours (et s'il y a des portefeuilles).
        Renvoie l'identifiant de la nouvelle sauvegarde, ou None."""
        maintenant = pd.Timestamp(maintenant) if maintenant is not None else pd.Timestamp.now()
        if not self._index():
            return None
        existantes = self.sauvegardes()
        if existantes and maintenant - pd.Timestamp(existantes[0]["date"]) < pd.Timedelta(days=SAUVEGARDE_JOURS):
            return None
        return self.sauvegarder(maintenant)

    def restaurer(self, id_sauvegarde):
        """Remet l'espace dans l'état de la sauvegarde. L'état actuel est d'abord sauvegardé lui-même
        (on peut donc revenir en arrière)."""
        source = self._dossier_sauvegardes() / str(id_sauvegarde)
        if not re.fullmatch(r"\d{8}-\d{6}", str(id_sauvegarde)) or not (source / "index.enc").exists():
            raise ErreurCompte("Sauvegarde introuvable.")
        coffre.dechiffrer(self._cle, (source / "index.enc").read_bytes())       # lisible avec ce mot de passe ?
        self.sauvegarder(pd.Timestamp.now() + pd.Timedelta(seconds=1))
        for f in self.dossier.glob("*.enc"):
            f.unlink()
        for f in source.glob("*.enc"):
            shutil.copy2(f, self.dossier / f.name)
        index = self._index()                    # les versions d'annulation ne sont pas dans la sauvegarde
        for p in index:
            p.pop("versions", None)
            p.pop("precedente", None)
            _noter(p, pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), "restauration", 0, p.get("operations"))
        self._sauver_index(index)

    annuler_derniere_modification = annuler_dernier_ajout      # ajout, suppression ou correction d'opérations

    def renommer(self, identifiant, nom):
        index = self._index()
        for p in index:
            if p["id"] == identifiant:
                p["nom"] = str(nom).strip() or p["nom"]
        self._sauver_index(index)

    def supprimer(self, identifiant):
        index = [p for p in self._index() if p["id"] != identifiant]
        for f in self.dossier.glob(f"{identifiant}.*enc"):
            f.unlink(missing_ok=True)
        self._sauver_index(index)

    # -- compte --
    def changer_mot_de_passe(self, ancien, nouveau, confirmation=None):
        """Vérifie l'ancien mot de passe, puis RECHIFFRE toutes les données avec la nouvelle clé."""
        registre = _lire_registre()
        fiche = registre["comptes"][self.identifiant]
        if not coffre.verifier(ancien, fiche["sel_empreinte"], fiche["empreinte"], fiche["iterations"]):
            raise ErreurCompte("Mot de passe actuel incorrect.")
        if len(nouveau) < LONGUEUR_MIN:
            raise ErreurCompte("Le mot de passe doit contenir au moins {n} caractères.", n=LONGUEUR_MIN)
        if confirmation is not None and confirmation != nouveau:
            raise ErreurCompte("Les deux mots de passe ne sont pas identiques.")
        # tous les fichiers chiffrés de l'espace (portefeuilles, versions, préférences, sauvegardes)
        # sont déchiffrés en mémoire avec l'ancienne clé...
        fichiers = {f: coffre.dechiffrer(self._cle, f.read_bytes()) for f in self.dossier.rglob("*.enc")}
        fiche["sel_empreinte"], fiche["sel_cle"] = coffre.nouveau_sel(), coffre.nouveau_sel()
        fiche["iterations"] = coffre.ITERATIONS
        fiche["empreinte"] = coffre.empreinte(nouveau, fiche["sel_empreinte"], fiche["iterations"])
        nouvelle_cle = coffre.cle_de_chiffrement(nouveau, fiche["sel_cle"], fiche["iterations"])
        for chemin, contenu in fichiers.items():                       # ... puis rechiffrés
            _ecrire(chemin, coffre.chiffrer(nouvelle_cle, contenu))
        self._cle = nouvelle_cle
        _ecrire_registre(registre)

    def supprimer_compte(self, mot_de_passe):
        """Supprime définitivement le compte et toutes ses données (droit à l'effacement)."""
        registre = _lire_registre()
        fiche = registre["comptes"].get(self.identifiant)
        if fiche is None or not coffre.verifier(mot_de_passe, fiche["sel_empreinte"], fiche["empreinte"],
                                                fiche["iterations"]):
            raise ErreurCompte("Mot de passe incorrect.")
        shutil.rmtree(self.dossier, ignore_errors=True)
        del registre["comptes"][self.identifiant]
        _ecrire_registre(registre)
        self._cle = None


def _versions(fiche, dossier, identifiant):
    """Versions précédentes d'un portefeuille (la plus récente en dernier). Reprend l'ancien format
    (une seule version « .prec.enc »)."""
    versions = list(fiche.get("versions", []))
    if not versions and fiche.get("precedente") and (dossier / f"{identifiant}.prec.enc").exists():
        versions = [{"fichier": f"{identifiant}.prec.enc", **fiche["precedente"]}]
    return versions


def _noter(fiche, date, action, n, operations):
    """Ajoute une ligne au journal des modifications du portefeuille."""
    journal = fiche.setdefault("journal", [])
    journal.append({"date": date, "action": action, "n": int(n), "operations": int(operations or 0)})
    del journal[:-JOURNAL_MAX]

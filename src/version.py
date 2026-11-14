"""Version de l'application (date de publication), affichée dans l'application et dans le
diagnostic « Signaler un problème ». À mettre à jour à chaque nouvelle version."""
import datetime

VERSION = "2026.11.14-2"            # deuxième version publiée le 14/11/2026
DATE_VERSION = datetime.date(2026, 11, 14)


def age_en_jours(aujourd_hui=None):
    """Nombre de jours depuis la publication de cette version."""
    return ((aujourd_hui or datetime.date.today()) - DATE_VERSION).days

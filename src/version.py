"""Version de l'application (date de publication), affichée dans l'application et dans le
diagnostic « Signaler un problème ». À mettre à jour à chaque nouvelle version."""
import datetime

VERSION = "2026.10.15"
DATE_VERSION = datetime.date(2026, 10, 15)


def age_en_jours(aujourd_hui=None):
    """Nombre de jours depuis la publication de cette version."""
    return ((aujourd_hui or datetime.date.today()) - DATE_VERSION).days

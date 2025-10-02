"""Central clinic metadata for reuse across UI and exports."""

from pathlib import Path

from backup import LOGO_PNG  # canonical logo path if bundled; may not exist at runtime

CLINIC_NAME = "Pet Wellness Vets"
CLINIC_ADDR1 = "Kyriakou Adamou no.2, Shop 2&3, 8220"
CLINIC_ADDR2 = ""
CLINIC_PHONE = "+357 99 941 186"
CLINIC_EMAIL = "contact@petwellnessvets.com"


def clinic_logo_path() -> str | None:
    p = Path(LOGO_PNG)
    return str(p) if p.exists() else None

import os
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JOBHUNT_DATA") or ROOT / "data")   # the server sets JOBHUNT_DATA=/data
UPLOADS = DATA / "uploads"
SCREENSHOTS = DATA / "screenshots"
BROWSER_PROFILE = DATA / "browser"
DB_PATH = DATA / "jobhunt.db"

for p in (DATA, UPLOADS, SCREENSHOTS, BROWSER_PROFILE):
    p.mkdir(parents=True, exist_ok=True)


def resolve(stored: str | None) -> Path | None:
    """A file path saved in the DB, made valid on this machine. Paths written on the PC look like
    C:\\Projects\\jobhunt\\data\\uploads\\x.pdf; after moving the data folder to the server they live
    under DATA instead, so re-root everything after the 'data' segment."""
    if not stored:
        return None
    p = Path(stored)
    if p.exists():
        return p
    parts = PureWindowsPath(stored).parts if "\\" in stored else Path(stored).parts
    lower = [x.lower() for x in parts]
    if "data" in lower:
        i = len(lower) - 1 - lower[::-1].index("data")
        cand = DATA.joinpath(*parts[i + 1:])
        if cand.exists():
            return cand
    return None

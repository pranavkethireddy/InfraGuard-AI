"""Download Backblaze Drive Stats Q1 2025 (~1 GB), verify it, and build the sampled drive-day table.

Usage: python scripts/prepare_backblaze.py
"""

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from infraguard_ml import backblaze as bb  # noqa: E402

ZIP = ROOT / "data" / "raw" / "backblaze" / bb.ZIP_NAME
OUT = ROOT / "data" / "processed" / "backblaze_q1_2025.pkl"


def main() -> None:
    if not (ZIP.is_file() and bb.sha256(ZIP) == bb.ZIP_SHA256):
        ZIP.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(bb.SOURCE_URL, ZIP)
        if bb.sha256(ZIP) != bb.ZIP_SHA256:
            ZIP.unlink()
            sys.exit("checksum mismatch")
    df = bb.build(ZIP)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(OUT)
    print(bb.summary(df))


if __name__ == "__main__":
    main()

"""Download UCI AI4I 2020 into data/raw/ai4i/ and verify its checksum.

Usage: python scripts/prepare_ai4i.py
"""

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from infraguard_ml import ai4i  # noqa: E402

OUT = ROOT / "data" / "raw" / "ai4i" / ai4i.CSV_NAME


def main() -> None:
    if OUT.is_file() and ai4i.sha256(OUT) == ai4i.CSV_SHA256:
        print(f"ok {OUT} (cached)")
        return
    with urllib.request.urlopen(ai4i.SOURCE_URL, timeout=60) as resp:
        blob = resp.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        data = zf.read(ai4i.CSV_NAME)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    digest = ai4i.sha256(OUT)
    if digest != ai4i.CSV_SHA256:
        OUT.unlink()
        sys.exit(f"checksum mismatch: {digest}")
    ai4i.load_raw(OUT)
    print(f"ok {OUT}")


if __name__ == "__main__":
    main()

"""Train drive-failure-v1 and write artifacts under ml/artifacts/.

Usage: python scripts/prepare_backblaze.py && python scripts/train_drive.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from infraguard_ml import backblaze as bb, train_drive  # noqa: E402

DATA = ROOT / "data" / "processed" / "backblaze_q1_2025.pkl"


def main() -> None:
    if not DATA.is_file():
        sys.exit("missing data; run: python scripts/prepare_backblaze.py")
    m = train_drive.train(pd.read_pickle(DATA), ROOT / "data" / "raw" / "backblaze" / bb.ZIP_NAME, ROOT / "ml" / "artifacts")
    print(json.dumps({"chosen": m["chosen_candidate"], **m["contract_metrics"], "risk_thresholds": m["risk_thresholds"]}, indent=2))


if __name__ == "__main__":
    main()

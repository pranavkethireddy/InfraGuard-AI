"""Train industrial-failure-v1 and write artifacts under ml/artifacts/.

Usage: python scripts/prepare_ai4i.py && python scripts/train_industrial.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from infraguard_ml import ai4i, train_industrial  # noqa: E402


def main() -> None:
    csv = ROOT / "data" / "raw" / "ai4i" / ai4i.CSV_NAME
    if not csv.is_file():
        sys.exit("missing data; run: python scripts/prepare_ai4i.py")
    m = train_industrial.train(csv, ROOT / "ml" / "artifacts")
    print(json.dumps({"chosen": m["chosen_candidate"], **m["contract_metrics"], "risk_thresholds": m["risk_thresholds"]}, indent=2))


if __name__ == "__main__":
    main()

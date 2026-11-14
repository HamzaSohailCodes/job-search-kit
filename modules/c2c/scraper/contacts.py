"""For each Dice job in a results CSV: how to apply (Dice apply, email, or external site),
the apply email when there is one, and Dice's own contract types (e.g. Corp-to-Corp, W2).

Usage: python3 modules/c2c/scraper/contacts.py batches/<date>-c2c/shortlist.csv
       -> contacts_<...>.csv next to it (c2c_jobs_<date>.csv -> contacts_<date>.csv; any other name -> contacts_<name>)
"""
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fetch  # noqa: E402

EMAIL_IN_TEXT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def dice_apply_info(url):
    h = fetch(url).replace('\\"', '"')
    m = re.search(r'"applicationDetail":(\{.*?\}),"employmentDetail":(\{.*?\}\}?\})', h)
    if not m:
        return {}
    try:
        app = json.loads(m.group(1))
    except Exception:
        app = {}
    types = re.findall(r'"(CONTRACT_[A-Z_]+|FULLTIME|PARTTIME|THIRD_PARTY)"', m.group(2))
    return {
        "apply_type": app.get("type", ""),
        "apply_email": app.get("email") or "",
        "apply_url": app.get("url") or "",
        "contract_types": ", ".join(t.replace("CONTRACT_", "").replace("_", " ").title() for t in dict.fromkeys(types)),
    }


def main(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    base = os.path.basename(path)
    out_path = os.path.join(os.path.dirname(path),
                            base.replace("c2c_jobs_", "contacts_") if "c2c_jobs_" in base else "contacts_" + base)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Link", "Apply type", "Apply email", "Apply URL", "Contract types"])
        for i, r in enumerate(rows, 1):
            info = dice_apply_info(r["Link"]) if "dice.com/job-detail" in r["Link"] else {}
            w.writerow([r["Link"], info.get("apply_type", ""), info.get("apply_email", ""),
                        info.get("apply_url", ""), info.get("contract_types", "")])
            print(f"{i}/{len(rows)}", file=sys.stderr, end="\r")
    print(f"\nWrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1])

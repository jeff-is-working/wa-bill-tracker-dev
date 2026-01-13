
#!/usr/bin/env python3
"""
Washington State Legislature Comprehensive Bill Fetcher
Fetches ALL bills, initiatives, and referendums for the 2026 session.

Enhancements:
- Writes canonical dataset to data/bills.json
- ALSO writes a timestamped snapshot to data/sync/<YYYYMMDD-HHMMSS>_bills.json
- Uses atomic writes to avoid partial/corrupt files on failure

LegiScan references have been removed; bills are sourced from curated local data.
"""

import json
from datetime import datetime, timedelta
import os
from pathlib import Path
from typing import Dict, List, Optional

# -----------------------------------
# Configuration
# -----------------------------------
BASE_URL = "https://app.leg.wa.gov"
YEAR = 2026
DATA_DIR = Path("data")
SESSION = "2025-26"  # Biennial session
SNAPSHOT_DIR = DATA_DIR / "sync"  # snapshot directory


# -----------------------------------
# Directory helpers
# -----------------------------------
def ensure_data_dir():
    """Ensure data directory exists"""
    DATA_DIR.mkdir(exist_ok=True)


def ensure_sync_dir():
    """Ensure data/sync directory exists (for timestamped snapshots)"""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------------
# Safe write helper
# -----------------------------------
def write_json_atomic(target_path: Path, obj: dict):
    """
    Write JSON atomically: write to a temporary file in the same directory,
    then os.replace() to the target (atomic on POSIX and Windows).
    """
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, target_path)  # atomic replace


# -----------------------------------
# Curated bill data (replace/extend as session progresses)
# -----------------------------------
def fetch_prefiled_bills() -> List[Dict]:
    """
    Return a curated list of prefiled WA bills for the 2026 session.
    Update/extend this list from official WA Legislature sources as needed.
    """
    curated = [
       
        
        
    ]

    bills: List[Dict] = []
    for bill_data in curated:
        bill_id = bill_data["number"].replace(" ", "")
        bill = {
            "id": bill_id,
            "number": bill_data["number"],
            "title": bill_data["title"],
            "sponsor": bill_data["sponsor"],
            "description": f"A bill relating to {bill_data['title'].lower()}",
            "status": bill_data["status"],
            "committee": determine_committee(bill_data["number"], bill_data["title"]),
            "priority": determine_priority(bill_data["title"]),
            "topic": determine_topic(bill_data["title"]),
            "introducedDate": "2026-01-12",
            "lastUpdated": datetime.now().isoformat(),

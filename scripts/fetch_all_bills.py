
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
    curated = []

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
            "legUrl": f"{BASE_URL}/billsummary?BillNumber={bill_data['number'].split()[1]}&Year={YEAR}",
            "hearings": []
        }
        bills.append(bill)

    return bills


# -----------------------------------
# Topic / committee / priority helpers
# -----------------------------------
def determine_topic(title: str) -> str:
    """Determine bill topic from title"""
    title_lower = title.lower()
    if any(word in title_lower for word in ["education", "school", "student", "teacher"]):
        return "Education"
    elif any(word in title_lower for word in ["tax", "revenue", "budget", "fiscal"]):
        return "Tax & Revenue"
    elif any(word in title_lower for word in ["housing", "rent", "tenant", "landlord"]):
        return "Housing"
    elif any(word in title_lower for word in ["health", "medical", "hospital", "mental"]):
        return "Healthcare"
    elif any(word in title_lower for word in ["environment", "climate", "energy", "pollution"]):
        return "Environment"
    elif any(word in title_lower for word in ["transport", "road", "highway", "transit"]):
        return "Transportation"
    elif any(word in title_lower for word in ["crime", "safety", "police", "justice"]):
        return "Public Safety"
    elif any(word in title_lower for word in ["business", "commerce", "trade", "economy"]):
        return "Business"
    elif any(word in title_lower for word in ["technology", "internet", "data", "privacy"]):
        return "Technology"
    else:
        return "General Government"


def determine_committee(bill_number: str, title: str) -> str:
    """Determine committee assignment based on bill number and title"""
    title_lower = title.lower()
    if "education" in title_lower or "school" in title_lower:
        return "Education"
    elif "transportation" in title_lower or "road" in title_lower:
        return "Transportation"
    elif "housing" in title_lower or "rent" in title_lower:
        return "Housing"
    elif "health" in title_lower or "medical" in title_lower:
        return "Health & Long-Term Care"
    elif "environment" in title_lower or "energy" in title_lower:
        return "Environment & Energy"
    elif "tax" in title_lower or "revenue" in title_lower:
        return "Finance" if bill_number.startswith("HB") else "Ways & Means"
    elif "consumer" in title_lower or "business" in title_lower:
        return "Consumer Protection & Business"
    elif "crime" in title_lower or "safety" in title_lower or "justice" in title_lower:
        return "Law & Justice"
    else:
        return "State Government & Tribal Relations"


def determine_priority(title: str) -> str:
    """Determine bill priority based on keywords in title"""
    title_lower = title.lower()
    # High priority keywords
    high_priority = [
        "emergency", "budget", "education funding", "public safety",
        "housing crisis", "climate", "healthcare access", "tax relief"
    ]
    # Low priority keywords
    low_priority = ["technical", "clarifying", "housekeeping", "minor", "study"]

    for keyword in high_priority:
        if keyword in title_lower:
            return "high"
    for keyword in low_priority:
        if keyword in title_lower:
            return "low"
    return "medium"


# -----------------------------------
# Persistence
# -----------------------------------
def save_bills_data(bills: List[Dict]) -> Dict:
    """
    Save bills data to JSON file and a timestamped snapshot for quick restore.
    - Canonical: data/bills.json
    - Snapshot:  data/sync/<YYYYMMDD-HHMMSS>_bills.json
    Uses atomic writes for both.
    """
    # Sort bills by number (type + numeric)
    bills.sort(
        key=lambda x: (
            x['number'].split()[0],
            int(x['number'].split()[1]) if len(x['number'].split()) > 1 else 0
        )
    )

    data = {
        "lastSync": datetime.now().isoformat(),
        "sessionYear": YEAR,
        "sessionStart": "2026-01-12",
        "sessionEnd": "2026-03-12",
        "totalBills": len(bills),
        "bills": bills,
        "metadata": {
            "source": "Washington State Legislature",
            "updateFrequency": "daily",
            "dataVersion": "2.0.0",
            "includesRevived": True,
            "billTypes": ["HB", "SB", "HJR", "SJR", "HJM", "SJM", "HCR", "SCR", "I", "R"]
        }
    }

    # Ensure output directories exist
    ensure_data_dir()
    ensure_sync_dir()

    # 1) Canonical file: data/bills.json (atomic write)
    data_file = DATA_DIR / "bills.json"
    write_json_atomic(data_file, data)

    # 2) Timestamped snapshot: data/sync/<YYYYMMDD-HHMMSS>_bills.json (atomic write)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot_file = SNAPSHOT_DIR / f"{ts}_bills.json"
    write_json_atomic(snapshot_file, data)

    print(f"✅ Saved {len(bills)} bills to {data_file}")
    print(f"🗂️ Snapshot created at {snapshot_file}")

    return data


def create_sync_log(bills_count: int, new_count: int = 0, status: str = "success"):
    """Create sync log for monitoring"""
    log = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "billsCount": bills_count,
        "newBillsAdded": new_count,
        "nextSync": (datetime.now() + timedelta(hours=6)).isoformat()
    }
    log_file = DATA_DIR / "sync-log.json"

    # Load existing logs
    logs = []
    if log_file.exists():
        with open(log_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logs = data.get('logs', [])

    # Add new log entry (keep last 100 entries)
    logs.insert(0, log)
    logs = logs[:100]

    # Save logs (atomic)
    write_json_atomic(log_file, {"logs": logs})
    print(f"📝 Sync log updated: {status} - {bills_count} bills, {new_count} new")


def load_existing_data() -> Optional[Dict]:
    """Load existing bills data if it exists"""
    data_file = DATA_DIR / "bills.json"
    if data_file.exists():
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


# -----------------------------------
# Optional: quick-restore helper
# -----------------------------------
def restore_latest_snapshot() -> Optional[Path]:
    """
    Restore the most recent snapshot into data/bills.json.
    Call this manually if you need to roll back to the last good state.
    """
    ensure_sync_dir()
    snapshots = sorted(SNAPSHOT_DIR.glob("*_bills.json"))
    if not snapshots:
        print("ℹ️ No snapshots found; nothing to restore.")
        return None

    latest = snapshots[-1]
    target = DATA_DIR / "bills.json"

    # Read and rewrite via atomic function for integrity
    with open(latest, 'r', encoding='utf-8') as src:
        data = json.load(src)
    write_json_atomic(target, data)

    print(f"♻️ Restored {latest.name} → {target}")
    return latest


# -----------------------------------
# Stats
# -----------------------------------
def create_stats_file(bills: List[Dict]):
    """Create comprehensive statistics file"""
    stats = {
        "generated": datetime.now().isoformat(),
        "totalBills": len(bills),
        "byStatus": {},
        "byCommittee": {},
        "byPriority": {},
        "byTopic": {},
        "bySponsor": {},
        "byType": {},
        "recentlyUpdated": 0,
        "updatedToday": 0,
        "upcomingHearings": 0,
        "billsWithHearings": 0
    }

    # Calculate statistics
    today = datetime.now().date()
    for bill in bills:
        # By status
        status = bill.get('status', 'unknown')
        stats['byStatus'][status] = stats['byStatus'].get(status, 0) + 1

        # By committee
        committee = bill.get('committee', 'unknown')
        stats['byCommittee'][committee] = stats['byCommittee'].get(committee, 0) + 1

        # By priority
        priority = bill.get('priority', 'unknown')
        stats['byPriority'][priority] = stats['byPriority'].get(priority, 0) + 1

        # By topic
        topic = bill.get('topic', 'unknown')
        stats['byTopic'][topic] = stats['byTopic'].get(topic, 0) + 1

        # By sponsor
        sponsor = bill.get('sponsor', 'unknown')
        stats['bySponsor'][sponsor] = stats['bySponsor'].get(sponsor, 0) + 1

        # By type (HB, SB, etc.)
        bill_type = bill['number'].split()[0] if ' ' in bill['number'] else 'unknown'
        stats['byType'][bill_type] = stats['byType'].get(bill_type, 0) + 1

        # Recently updated
        try:
            last_updated = datetime.fromisoformat(bill.get('lastUpdated', ''))
            days_diff = (datetime.now() - last_updated).days
            if days_diff < 1:
                stats['recentlyUpdated'] += 1
            if last_updated.date() == today:
                stats['updatedToday'] += 1
        except Exception:
            pass

        # Hearings
        hearings = bill.get('hearings', [])
        if hearings:
            stats['billsWithHearings'] += 1
        for hearing in hearings:
            try:
                hearing_date = datetime.strptime(hearing['date'], '%Y-%m-%d')
                if 0 <= (hearing_date.date() - today).days <= 7:
                    stats['upcomingHearings'] += 1
            except Exception:
                pass

    # Sort sponsors by count
    stats['topSponsors'] = sorted(
        stats['bySponsor'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]

    stats_file = DATA_DIR / "stats.json"
    write_json_atomic(stats_file, stats)
    print(f"📊 Statistics file updated with {len(stats['byStatus'])} statuses, {len(stats['byCommittee'])} committees")


# -----------------------------------
# Main
# -----------------------------------
def main():
    """Main execution function"""
    print(f"🚀 Starting Comprehensive WA Legislature Bill Fetcher - {datetime.now()}")
    print("=" * 60)

    # Ensure data and snapshot directories exist
    ensure_data_dir()
    ensure_sync_dir()

    # Load existing data
    existing_data = load_existing_data()
    existing_bills: Dict[str, Dict] = {}
    if existing_data:
        existing_bills = {bill['id']: bill for bill in existing_data.get('bills', [])}
        print(f"📚 Loaded {len(existing_bills)} existing bills")

    # Fetch curated bill list (no LegiScan)
    print("📥 Fetching curated bill data from local list...")
    all_bills = fetch_prefiled_bills()

    # Track new and updated bills
    new_bills = []
    updated_bills = []
    for bill in all_bills:
        if bill['id'] not in existing_bills:
            new_bills.append(bill)
        elif bill != existing_bills[bill['id']]:
            updated_bills.append(bill)

    print(f" ✨ Found {len(new_bills)} new bills")
    print(f" 🔄 Updated {len(updated_bills)} existing bills")

    # Merge with existing bills
    for bill in all_bills:
        existing_bills[bill['id']] = bill

    # Convert back to list
    final_bills = list(existing_bills.values())

    # Save bills data + snapshot (atomic)
    save_bills_data(final_bills)

    # Create statistics (atomic)
    create_stats_file(final_bills)

    # Create sync log (atomic)
    create_sync_log(len(final_bills), len(new_bills), "success")

    print("=" * 60)
    print(f"✅ Successfully updated database:")
    print(f" - Total bills: {len(final_bills)}")
    print(f" - New bills: {len(new_bills)}")
    print(f" - Updated bills: {len(updated_bills)}")
    print(f"🏁 Update complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""
WA Legislature — Bills, Status, Sponsors & Hearings (2026)
Standard-library-only client for Washington State Legislative Web Services.

Data sources:
- SOAP 1.1: GetLegislationIntroducedSince("2026-01-01T00:00:00")
  -> detailed <Legislation> items including CurrentStatus, Sponsor, IntroducedDate.
  (https://wslwebservices.leg.wa.gov/LegislationService.asmx?op=GetLegislationIntroducedSince)
- SOAP 1.1: CommitteeMeetingService.GetCommitteeMeetings(begin, end)
  + CommitteeMeetingService.GetCommitteeMeetingItems(agendaId)
  -> hearings & committees per bill via Agenda items.
  (https://wslwebservices.leg.wa.gov/committeemeetingservice.asmx?op=GetCommitteeMeetings)
  (https://wslwebservices.leg.wa.gov/CommitteeMeetingService.asmx?op=GetCommitteeMeetingItems)

Writes (atomic):
- data/bills.json (canonical)
- data/sync/<YYYYMMDD-HHMMSS>_bills.json (snapshot)
- data/stats.json
- data/sync-log.json

Env (optional):
- WALEG_TIMEOUT (default 45)
- HEARINGS_BEGIN_DATE (default 2026-01-01T00:00:00)
- HEARINGS_END_DATE   (default now, ISO)
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import urlopen, Request
import xml.etree.ElementTree as ET

# -----------------------------
# Config
# -----------------------------
YEAR = 2026
SESSION_BIENNIUM = "2025-26"
SINCE_DATE = "2026-01-01T00:00:00"

LEGISLATION_SERVICE = "https://wslwebservices.leg.wa.gov/LegislationService.asmx"
COMMITTEE_MEETING_SERVICE = "https://wslwebservices.leg.wa.gov/CommitteeMeetingService.asmx"

LEG_SUMMARY_URL = "https://app.leg.wa.gov/billsummary?BillNumber={num}&Year={year}"

DATA_DIR = Path("data")
SNAPSHOT_DIR = DATA_DIR / "sync"

HTTP_TIMEOUT = int(os.getenv("WALEG_TIMEOUT", "45"))
HEARINGS_BEGIN_DATE = os.getenv("HEARINGS_BEGIN_DATE", SINCE_DATE)
HEARINGS_END_DATE = os.getenv("HEARINGS_END_DATE", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))

# -----------------------------
# SOAP helpers (standard library)
# -----------------------------
def soap_post(service_base: str, action: str, body_xml: str) -> ET.Element:
    """
    Perform a SOAP 1.1 POST with SOAPAction header and parse XML.
    """
    envelope = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                   xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        {body_xml}
      </soap:Body>
    </soap:Envelope>""".encode("utf-8")

    headers = {
        "User-Agent": "wa-leg-collector/1.0",
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f"http://WSLWebServices.leg.wa.gov/{action}",
    }
    req = Request(service_base, data=envelope, headers=headers, method="POST")
    with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        content = resp.read()
    return ET.fromstring(content)

# -----------------------------
# XML utilities (namespace-agnostic)
# -----------------------------
def find_text(elem: ET.Element, tag_suffix: str, default: Optional[str] = None) -> Optional[str]:
    for child in list(elem):
        if child.tag.endswith(tag_suffix):
            return (child.text or "").strip() if child.text else default
    return default

def find_first(elem: ET.Element, tag_suffix: str) -> Optional[ET.Element]:
    for e in elem.iter():
        if e.tag.endswith(tag_suffix):
            return e
    return None

def iter_children(elem: ET.Element, tag_suffix: str) -> List[ET.Element]:
    return [e for e in elem.iter() if e.tag.endswith(tag_suffix)]

# -----------------------------
# Fetch legislation (single call)
# -----------------------------
def get_legislation_introduced_since(since_iso: str) -> List[ET.Element]:
    """
    Get detailed <Legislation> items introduced since since_iso.
    (Has CurrentStatus, Sponsor, IntroducedDate, titles)
    """
    # Operation reference: GetLegislationIntroducedSince [1](https://wslwebservices.leg.wa.gov/)
    body_xml = f"""
      <GetLegislationIntroducedSince xmlns="http://WSLWebServices.leg.wa.gov/">
        <sinceDate>{since_iso}</sinceDate>
      </GetLegislationIntroducedSince>
    """.strip()
    env = soap_post(LEGISLATION_SERVICE, "GetLegislationIntroducedSince", body_xml)
    result = find_first(env, "GetLegislationIntroducedSinceResult") or env
    return iter_children(result, "Legislation")

# -----------------------------
# Fetch hearings in bulk (few calls)
# -----------------------------
def get_committee_meetings(begin_iso: str, end_iso: str) -> List[ET.Element]:
    """
    Get CommitteeMeetings for a date range.
    """
    # Operation reference: CommitteeMeetingService.GetCommitteeMeetings [2](https://wslwebservices.leg.wa.gov/committeemeetingservice.asmx?op=GetCommitteeMeetings)
    body_xml = f"""
      <GetCommitteeMeetings xmlns="http://WSLWebServices.leg.wa.gov/">
        <beginDate>{begin_iso}</beginDate>
        <endDate>{end_iso}</endDate>
      </GetCommitteeMeetings>
    """.strip()
    env = soap_post(COMMITTEE_MEETING_SERVICE, "GetCommitteeMeetings", body_xml)
    result = find_first(env, "GetCommitteeMeetingsResult") or env
    return iter_children(result, "CommitteeMeeting")

def get_committee_meeting_items(agenda_id: int) -> List[ET.Element]:
    """
    Get items (bills on the agenda) for a committee meeting.
    """
    # Operation reference: CommitteeMeetingService.GetCommitteeMeetingItems [3](https://wslwebservices.leg.wa.gov/CommitteeMeetingService.asmx?op=GetCommitteeMeetingItems)
    body_xml = f"""
      <GetCommitteeMeetingItems xmlns="http://WSLWebServices.leg.wa.gov/">
        <agendaId>{agenda_id}</agendaId>
      </GetCommitteeMeetingItems>
    """.strip()
    env = soap_post(COMMITTEE_MEETING_SERVICE, "GetCommitteeMeetingItems", body_xml)
    result = find_first(env, "GetCommitteeMeetingItemsResult") or env
    return iter_children(result, "CommitteeMeetingItem")

def collect_hearings_map(begin_iso: str, end_iso: str) -> Dict[str, List[Dict[str, str]]]:
    """
    Build map: BillId -> [ {date, committee, type, location} ... ]
    by enumerating meetings and their agenda items.
    """
    hearings_map: Dict[str, List[Dict[str, str]]] = {}
    meetings = get_committee_meetings(begin_iso, end_iso)

    for mtg in meetings:
        agenda_id_text = find_text(mtg, "AgendaId") or ""
        if not agenda_id_text.isdigit():
            continue
        agenda_id = int(agenda_id_text)

        # meeting-level properties
        date_dt = find_text(mtg, "Date") or ""
        date_str = date_dt.split("T")[0] if "T" in date_dt else date_dt
        agency = find_text(mtg, "Agency") or ""
        # committee names may be in <Committees><Committee><Name>…</Name></Committee>…
        committees_elem = find_first(mtg, "Committees")
        committee_names = []
        if committees_elem is not None:
            for c in iter_children(committees_elem, "Committee"):
                nm = find_text(c, "Name")
                if nm:
                    committee_names.append(nm)
        committee_str = ", ".join(committee_names) if committee_names else agency or "unknown"

        building = find_text(mtg, "Building") or ""
        room = find_text(mtg, "Room") or ""
        location = " ".join(x for x in [building, room] if x).strip()

        # items contain BillId & hearing type description
        items = get_committee_meeting_items(agenda_id)
        for it in items:
            bill_id = find_text(it, "BillId") or ""
            if not bill_id:
                continue
            htype_desc = find_text(it, "HearingTypeDescription") or (find_text(it, "HearingType") or "")
            entry = {
                "date": date_str,
                "committee": committee_str or "unknown",
                "type": htype_desc or "",
                "location": location,
            }
            hearings_map.setdefault(bill_id, []).append(entry)

    return hearings_map

# -----------------------------
# Normalize + enrich
# -----------------------------
def normalize_number(leg: ET.Element) -> Tuple[str, Optional[int]]:
    display = find_text(leg, "DisplayNumber") or ""
    bill_id = find_text(leg, "BillId") or ""
    bill_num_text = find_text(leg, "BillNumber") or ""
    bill_num = int(bill_num_text) if bill_num_text.isdigit() else None
    number = display or bill_id or (str(bill_num) if bill_num is not None else "")
    return number, bill_num

def determine_topic(title: str) -> str:
    t = (title or "").lower()
    if any(w in t for w in ["education", "school", "student", "teacher"]): return "Education"
    if any(w in t for w in ["tax", "revenue", "budget", "fiscal"]):        return "Tax & Revenue"
    if any(w in t for w in ["housing", "rent", "tenant", "landlord"]):     return "Housing"
    if any(w in t for w in ["health", "medical", "hospital", "mental"]):   return "Healthcare"
    if any(w in t for w in ["environment", "climate", "energy", "pollution"]): return "Environment"
    if any(w in t for w in ["transport", "road", "highway", "transit"]):   return "Transportation"
    if any(w in t for w in ["crime", "safety", "police", "justice"]):      return "Public Safety"
    if any(w in t for w in ["business", "commerce", "trade", "economy"]):  return "Business"
    if any(w in t for w in ["technology", "internet", "data", "privacy"]): return "Technology"
    return "General Government"

def determine_priority(title: str) -> str:
    t = (title or "").lower()
    high = ["emergency", "budget", "education funding", "public safety", "housing crisis", "climate", "healthcare access", "tax relief"]
    low  = ["technical", "clarifying", "housekeeping", "minor", "study"]
    if any(k in t for k in high): return "high"
    if any(k in t for k in low):  return "low"
    return "medium"

def build_record(leg: ET.Element, hearings_map: Dict[str, List[Dict[str, str]]]) -> Optional[Dict[str, Any]]:
    number, bill_num = normalize_number(leg)
    if not number:
        return None

    # Titles & description
    title = (
        find_text(leg, "LegalTitle")
        or find_text(leg, "LongDescription")
        or find_text(leg, "ShortDescription")
        or ""
    )
    description = f"A bill relating to {title.lower()}" if title else ""

    # Status, sponsor, introduced date from detailed legislation node
    cur = find_first(leg, "CurrentStatus")
    status = find_text(cur, "Status", default="unknown") if cur is not None else "unknown"
    introduced_dt = find_text(leg, "IntroducedDate") or ""
    introduced = introduced_dt.split("T")[0] if "T" in introduced_dt else introduced_dt
    sponsor = find_text(leg, "Sponsor") or ""  # this is a string in the detailed response

    hearings = hearings_map.get(number, []) or hearings_map.get(number.strip(), []) or []

    # Committee => pick from hearings if any, else "unknown"
    committee = hearings[0]["committee"] if hearings else "unknown"

    # Topic & priority
    topic = determine_topic(title)
    priority = determine_priority(title)

    return {
        "id": number.replace(" ", ""),
        "number": number,
        "title": title,
        "sponsor": sponsor,
        "description": description,
        "status": status,
        "committee": committee,
        "priority": priority,
        "topic": topic,
        "introducedDate": introduced,
        "lastUpdated": datetime.now().isoformat(),
        "legUrl": LEG_SUMMARY_URL.format(num=bill_num if bill_num is not None else "", year=YEAR),
        "hearings": hearings,
    }

# -----------------------------
# Persistence (atomic writes)
# -----------------------------
def ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

def write_json_atomic(path: Path, payload: Dict[str, Any]):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def save_bills_data(bills: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Sort: by type prefix then numeric
    def sort_key(b: Dict[str, Any]) -> Tuple[str, int]:
        parts = (b.get("number") or "").split()
        t = parts[0] if parts else ""
        n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return (t, n)

    bills.sort(key=sort_key)

    data = {
        "lastSync": datetime.now().isoformat(),
        "sessionYear": YEAR,
        "biennium": SESSION_BIENNIUM,
        "totalBills": len(bills),
        "bills": bills,
        "metadata": {
            "source": "Washington State Legislative Web Services",
            "endpoints": {
                "LegislationService": LEGISLATION_SERVICE,
                "CommitteeMeetingService": COMMITTEE_MEETING_SERVICE
            },
            "sinceDate": SINCE_DATE,
            "hearingsRange": {"begin": HEARINGS_BEGIN_DATE, "end": HEARINGS_END_DATE},
        },
    }
    ensure_dirs()
    canonical = DATA_DIR / "bills.json"
    write_json_atomic(canonical, data)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot = SNAPSHOT_DIR / f"{ts}_bills.json"
    write_json_atomic(snapshot, data)
    print(f"✅ Saved {len(bills)} bills to {canonical}\n🗂️ Snapshot: {snapshot}")
    return data

# -----------------------------
# Stats & Sync Log (as in your original)
# -----------------------------
def create_stats_file(bills: List[Dict[str, Any]]):
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
    today = datetime.now().date()

    for bill in bills:
        stats["byStatus"][bill.get("status","unknown")]      = stats["byStatus"].get(bill.get("status","unknown"), 0) + 1
        stats["byCommittee"][bill.get("committee","unknown")] = stats["byCommittee"].get(bill.get("committee","unknown"), 0) + 1
        stats["byPriority"][bill.get("priority","unknown")]   = stats["byPriority"].get(bill.get("priority","unknown"), 0) + 1
        stats["byTopic"][bill.get("topic","unknown")]         = stats["byTopic"].get(bill.get("topic","unknown"), 0) + 1
        stats["bySponsor"][bill.get("sponsor","unknown")]     = stats["bySponsor"].get(bill.get("sponsor","unknown"), 0) + 1

        bill_type = (bill.get("number") or "unknown").split()[0] if " " in (bill.get("number") or "") else "unknown"
        stats["byType"][bill_type] = stats["byType"].get(bill_type, 0) + 1

        try:
            last_updated = datetime.fromisoformat(bill.get("lastUpdated",""))
            if (datetime.now() - last_updated).days < 1:
                stats["recentlyUpdated"] += 1
            if last_updated.date() == today:
                stats["updatedToday"] += 1
        except:
            pass

        hearings = bill.get("hearings", [])
        if hearings:
            stats["billsWithHearings"] += 1
        for hearing in hearings:
            try:
                hdate = hearing.get("date","")
                if hdate:
                    d = datetime.strptime(hdate, "%Y-%m-%d").date()
                    if 0 <= (d - today).days <= 7:
                        stats["upcomingHearings"] += 1
            except:
                pass

    stats["topSponsors"] = sorted(stats["bySponsor"].items(), key=lambda x: x[1], reverse=True)[:10]

    write_json_atomic(DATA_DIR / "stats.json", stats)
    print(f"📊 Stats updated ({len(stats['byStatus'])} statuses, {len(stats['byCommittee'])} committees)")

def create_sync_log(bills_count: int, new_count: int = 0, status: str = "success"):
    log_file = DATA_DIR / "sync-log.json"
    log = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "billsCount": bills_count,
        "newBillsAdded": new_count,
        "nextSync": (datetime.now()).isoformat()
    }
    logs = []
    if log_file.exists():
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                logs = data.get("logs", [])
        except:
            logs = []
    logs.insert(0, log)
    logs = logs[:100]
    write_json_atomic(log_file, {"logs": logs})
    print(f"📝 Sync log updated: {status} — {bills_count} bills, {new_count} new")

# -----------------------------
# Main
# -----------------------------
def main():
    print(f"🚀 Collecting WA bills (2026) with status, sponsors & hearings")
    try:
        # 1) Fetch detailed bills introduced since session start (includes status/sponsor/introduced)
        leg_nodes = get_legislation_introduced_since(SINCE_DATE)  # single call
    except Exception as e:
        create_sync_log(0, 0, "failed")
        raise SystemExit(f"Failed to fetch legislation: {e}")

    # 2) Build hearings map in bulk (meetings -> agenda items)
    try:
        hearings_map = collect_hearings_map(HEARINGS_BEGIN_DATE, HEARINGS_END_DATE)
    except Exception as e:
        print(f"⚠️ Hearings collection failed: {e}")
        hearings_map = {}

    # 3) Normalize & enrich
    bills: List[Dict[str, Any]] = []
    for i, leg in enumerate(leg_nodes, 1):
        try:
            rec = build_record(leg, hearings_map)
            if rec:
                bills.append(rec)
        except Exception as e:
            print(f"⚠️ Skipping item {i}: {e}")

    # 4) Save + stats + log
    save_bills_data(bills)
    create_stats_file(bills)
    create_sync_log(len(bills), new_count=0, status="success")

    print(f"🏁 Done at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()

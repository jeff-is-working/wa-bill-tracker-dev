
#!/usr/bin/env python3
"""
WA Legislature - Current Bills & Status (2026)
Fast standard-library-only client for Washington State Legislative Web Services.

Strategy:
- SOAP 1.1: GetLegislationByYear(2026) -> <LegislationInfo>*  (single call)
- SOAP 1.1: GetLegislativeStatusChangesByDateRange("2025-26", 2026-01-01 .. now) -> <LegislativeStatus>* (single call)
- Compute latest status per bill and merge, then write outputs with atomic writes.

Refs:
- GetLegislationByYear SOAP: https://wslwebservices.leg.wa.gov/LegislationService.asmx?op=GetLegislationByYear
- GetLegislativeStatusChangesByDateRange SOAP: https://wslwebservices.leg.wa.gov/legislationservice.asmx?op=GetLegislativeStatusChangesByDateRange
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
# Configuration
# -----------------------------
YEAR = 2026
BIENNIUM = "2025-26"
SERVICE_BASE = "https://wslwebservices.leg.wa.gov/LegislationService.asmx"
LEG_SUMMARY_URL = "https://app.leg.wa.gov/billsummary?BillNumber={num}&Year={year}"

DATA_DIR = Path("data")
SNAPSHOT_DIR = DATA_DIR / "sync"

HTTP_TIMEOUT = 60  # seconds
RETRIES = int(os.getenv("WALEG_RETRIES", "3"))
BACKOFF_BASE = float(os.getenv("WALEG_BACKOFF_BASE", "0.7"))  # seconds

# -----------------------------
# HTTP helpers (SOAP 1.1)
# -----------------------------
def http_post_soap(action: str, body_xml: str) -> ET.Element:
    """
    Perform a SOAP 1.1 POST with SOAPAction header and parse XML.
    Includes simple retry with exponential backoff.
    """
    soap_envelope = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                   xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        {body_xml}
      </soap:Body>
    </soap:Envelope>""".encode("utf-8")

    headers = {
        "User-Agent": "wa-leg-status-bot/1.2",
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f"http://WSLWebServices.leg.wa.gov/{action}",
    }

    last_exc = None
    for attempt in range(RETRIES):
        try:
            req = Request(SERVICE_BASE, data=soap_envelope, headers=headers, method="POST")
            with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                content = resp.read()
            return ET.fromstring(content)
        except Exception as e:
            last_exc = e
            # exponential backoff with jitter
            sleep = BACKOFF_BASE * (2 ** attempt)
            time.sleep(sleep)
    raise SystemExit(f"SOAP call failed for action {action}: {last_exc}")

# -----------------------------
# XML utilities (namespace-agnostic)
# -----------------------------
def xml_find_first(elem: ET.Element, tag_suffix: str) -> Optional[ET.Element]:
    for e in elem.iter():
        if e.tag.endswith(tag_suffix):
            return e
    return None

def xml_find_text(elem: ET.Element, tag_suffix: str, default: Optional[str] = None) -> Optional[str]:
    for child in list(elem):
        if child.tag.endswith(tag_suffix):
            return (child.text or "").strip() if child.text else default
    return default

def xml_iter_children(elem: ET.Element, tag_suffix: str) -> List[ET.Element]:
    return [e for e in elem.iter() if e.tag.endswith(tag_suffix)]

# -----------------------------
# LWS calls
# -----------------------------
def get_legislation_by_year(year: int) -> List[ET.Element]:
    """
    SOAP: GetLegislationByYear -> list of <LegislationInfo> nodes
    """
    body_xml = f"""
      <GetLegislationByYear xmlns="http://WSLWebServices.leg.wa.gov/">
        <year>{year}</year>
      </GetLegislationByYear>
    """.strip()
    env = http_post_soap("GetLegislationByYear", body_xml)
    result = xml_find_first(env, "GetLegislationByYearResult") or env
    return xml_iter_children(result, "LegislationInfo")

def get_status_changes_by_date_range(biennium: str, begin_iso: str, end_iso: str) -> List[ET.Element]:
    """
    SOAP: GetLegislativeStatusChangesByDateRange -> list of <LegislativeStatus>
    """
    body_xml = f"""
      <GetLegislativeStatusChangesByDateRange xmlns="http://WSLWebServices.leg.wa.gov/">
        <biennium>{biennium}</biennium>
        <beginDate>{begin_iso}</beginDate>
        <endDate>{end_iso}</endDate>
      </GetLegislativeStatusChangesByDateRange>
    """.strip()
    env = http_post_soap("GetLegislativeStatusChangesByDateRange", body_xml)
    result = xml_find_first(env, "GetLegislativeStatusChangesByDateRangeResult") or env
    return xml_iter_children(result, "LegislativeStatus")

# -----------------------------
# Build status map (latest per bill)
# -----------------------------
def build_latest_status_map(status_nodes: List[ET.Element]) -> Dict[str, Dict[str, str]]:
    """
    Return map: key="HB 1001" -> {"Status": "...", "ActionDate": "YYYY-MM-DDTHH:MM:SS"}
    Uses the latest ActionDate per BillId.
    """
    latest: Dict[str, Dict[str, str]] = {}
    for node in status_nodes:
        bill_id = xml_find_text(node, "BillId", default="") or ""
        status = xml_find_text(node, "Status", default="unknown") or "unknown"
        action_dt = xml_find_text(node, "ActionDate", default="") or ""
        if not bill_id or not action_dt:
            # skip incomplete entries
            continue
        prev = latest.get(bill_id)
        if not prev or (action_dt > prev.get("ActionDate", "")):
            latest[bill_id] = {"Status": status, "ActionDate": action_dt}
    return latest

# -----------------------------
# Transform & merge
# -----------------------------
def normalize_number(info: ET.Element) -> Tuple[str, Optional[int]]:
    """
    Determine display number and numeric part:
    - Prefer DisplayNumber (e.g., "HB 1001")
    - Fallback to BillId
    - Fallback to BillNumber if needed (no prefix)
    """
    display_number = xml_find_text(info, "DisplayNumber")
    bill_id = xml_find_text(info, "BillId")
    bill_num_text = xml_find_text(info, "BillNumber") or ""
    bill_num_int = None
    if bill_num_text.isdigit():
        bill_num_int = int(bill_num_text)
    if display_number:
        return display_number, bill_num_int
    if bill_id:
        return bill_id, bill_num_int
    if bill_num_int is not None:
        return str(bill_num_int), bill_num_int
    return "", None

def build_record(info: ET.Element, latest_map: Dict[str, Dict[str, str]]) -> Optional[Dict[str, Any]]:
    number, bill_num_int = normalize_number(info)
    if not number:
        return None
    status_entry = latest_map.get(number) or latest_map.get(number.strip())
    status = (status_entry or {}).get("Status", "unknown")

    return {
        "id": number.replace(" ", ""),
        "number": number,
        "title": "",  # LegislationInfo is summary only; detailed titles require another op.
        "status": status,
        "lastUpdated": datetime.now().isoformat(),
        "legUrl": LEG_SUMMARY_URL.format(num=bill_num_int if bill_num_int is not None else "", year=YEAR),
    }

# -----------------------------
# Persistence (atomic)
# -----------------------------
def ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

def write_json_atomic(path: Path, payload: Dict[str, Any]):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def save_outputs(bills: List[Dict[str, Any]]):
    data = {
        "lastSync": datetime.now().isoformat(),
        "sessionYear": YEAR,
        "biennium": BIENNIUM,
        "totalBills": len(bills),
        "bills": bills,
        "metadata": {
            "source": "Washington State Legislative Web Services",
            "endpoint": SERVICE_BASE,
        },
    }
    ensure_dirs()
    canonical = DATA_DIR / "bills.json"
    write_json_atomic(canonical, data)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot = SNAPSHOT_DIR / f"{ts}_bills.json"
    write_json_atomic(snapshot, data)

    print(f"✅ Wrote {len(bills)} bills")
    print(f"  - Canonical: {canonical}")
    print(f"  - Snapshot : {snapshot}")

# -----------------------------
# Main
# -----------------------------
def main():
    print(f"🚀 Fetching WA bills for {YEAR} + current status (biennium {BIENNIUM})")

    # 1) Enumerate bills (single SOAP call)
    infos = get_legislation_by_year(YEAR)
    if not infos:
        print("⚠️ No legislation returned by GetLegislationByYear; continuing with empty set.")

    # 2) Fetch all status changes in date range (single SOAP call)
    begin_iso = f"{YEAR}-01-01T00:00:00"
    end_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    status_nodes = get_status_changes_by_date_range(BIENNIUM, begin_iso, end_iso)
    latest_map = build_latest_status_map(status_nodes)

    # 3) Merge
    bills: List[Dict[str, Any]] = []
    for i, info in enumerate(infos, 1):
        try:
            rec = build_record(info, latest_map)
            if rec:
                bills.append(rec)
        except Exception as e:
            print(f"⚠️  Skipping item {i} due to error: {e}")

    # Stable sort: by prefix (HB/SB/…) then numeric
    def sort_key(b: Dict[str, Any]) -> Tuple[str, int]:
        parts = (b.get("number") or "").split()
        t = parts[0] if parts else ""
        try:
            n = int(parts[1]) if len(parts) > 1 else 0
        except Exception:
            n = 0
        return (t, n)

    bills.sort(key=sort_key)
    save_outputs(bills)

if __name__ == "__main__":
    main()

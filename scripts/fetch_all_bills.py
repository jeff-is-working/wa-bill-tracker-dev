
#!/usr/bin/env python3
"""
WA Legislature - Current Bills & Status (2026)
Standard-library-only client for Washington State Legislative Web Services.

Fixes:
- Call GetLegislationByYear via SOAP 1.1 and parse <LegislationInfo> items.
- Call GetCurrentStatus via HTTP GET (as documented).
- Preserve atomic writes + timestamped snapshots.

Refs:
- GetLegislationByYear SOAP 1.1 shape & response: https://wslwebservices.leg.wa.gov/LegislationService.asmx?op=GetLegislationByYear
- GetCurrentStatus HTTP GET shape: https://wslwebservices.leg.wa.gov/LegislationService.asmx?op=GetCurrentStatus
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
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

THROTTLE_SECONDS = float(os.getenv("WALEG_THROTTLE_SECONDS", "0.10"))
HTTP_TIMEOUT = 60  # seconds

# -----------------------------
# HTTP helpers (standard lib)
# -----------------------------
def http_get_xml(endpoint: str, params: Dict[str, Any]) -> ET.Element:
    """
    Perform an HTTP GET to an LWS endpoint with query params and parse the XML response.
    """
    qs = urlencode(params)
    url = f"{endpoint}?{qs}"
    req = Request(url, headers={"User-Agent": "wa-leg-status-bot/1.1"})
    with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        content = resp.read()
    try:
        return ET.fromstring(content)
    except ET.ParseError as e:
        raise RuntimeError(f"XML parse error at {endpoint} with params {params}: {e}") from e

def http_post_soap(action: str, body_xml: str) -> ET.Element:
    """
    Perform a SOAP 1.1 POST with the required SOAPAction header and parse XML.
    """
    soap_envelope = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                   xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        {body_xml}
      </soap:Body>
    </soap:Envelope>"""
    data = soap_envelope.encode("utf-8")
    headers = {
        "User-Agent": "wa-leg-status-bot/1.1",
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f"http://WSLWebServices.leg.wa.gov/{action}",
    }
    req = Request(SERVICE_BASE, data=data, headers=headers, method="POST")
    with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        content = resp.read()
    try:
        return ET.fromstring(content)
    except ET.ParseError as e:
        raise RuntimeError(f"SOAP parse error for action {action}: {e}") from e

def sleep_throttle():
    if THROTTLE_SECONDS > 0:
        time.sleep(THROTTLE_SECONDS)

# -----------------------------
# XML utilities (namespace-agnostic)
# -----------------------------
def xml_find_text(elem: ET.Element, tag_suffix: str, default: Optional[str] = None) -> Optional[str]:
    """
    Find direct child text where child's tag endswith(tag_suffix).
    """
    for child in list(elem):
        if child.tag.endswith(tag_suffix):
            return (child.text or "").strip() if child.text else default
    return default

def xml_find_first(elem: ET.Element, tag_suffix: str) -> Optional[ET.Element]:
    for e in elem.iter():
        if e.tag.endswith(tag_suffix):
            return e
    return None

def xml_iter_children(elem: ET.Element, tag_suffix: str) -> List[ET.Element]:
    """
    Return all descendant elements whose tag ends with tag_suffix.
    """
    matches = []
    for e in elem.iter():
        if e.tag.endswith(tag_suffix):
            matches.append(e)
    return matches

# -----------------------------
# LWS calls
# -----------------------------
def get_legislation_by_year_soap(year: int) -> List[ET.Element]:
    """
    Call GetLegislationByYear via SOAP 1.1 and return a list of <LegislationInfo> nodes.
    """
    body_xml = f"""
      <GetLegislationByYear xmlns="http://WSLWebServices.leg.wa.gov/">
        <year>{year}</year>
      </GetLegislationByYear>
    """.strip()
    envelope = http_post_soap("GetLegislationByYear", body_xml)
    # We expect: Envelope -> Body -> GetLegislationByYearResponse -> GetLegislationByYearResult -> LegislationInfo*
    result = xml_find_first(envelope, "GetLegislationByYearResult")
    if result is None:
        # Some environments return the result directly; be flexible
        result = envelope
    items = xml_iter_children(result, "LegislationInfo")
    return items

def get_current_status(biennium: str, bill_number: int) -> Dict[str, Optional[str]]:
    """
    Call GetCurrentStatus and return a dict with 'Status' and 'ActionDate' (best effort).
    HTTP GET interface documented on the operation page.
    """
    root = http_get_xml(f"{SERVICE_BASE}/GetCurrentStatus", {"biennium": biennium, "billNumber": bill_number})
    status = xml_find_text(root, "Status", default="unknown")
    action_date = xml_find_text(root, "ActionDate", default=None)
    return {"Status": status, "ActionDate": action_date}

# -----------------------------
# Transform/normalize
# -----------------------------
def build_bill_record(item: ET.Element) -> Optional[Dict[str, Any]]:
    """
    Convert a <LegislationInfo> element to our canonical record and enrich with current status.
    """
    display_number = xml_find_text(item, "DisplayNumber")
    bill_number_text = xml_find_text(item, "BillNumber")
    bill_number_int = None
    if bill_number_text and bill_number_text.isdigit():
        bill_number_int = int(bill_number_text)

    bill_id = xml_find_text(item, "BillId")  # sometimes "HB 1001"
    # For this 'current bills & status' task, Title is not provided by the summary call. Leave empty.
    title = ""

    if display_number:
        number = display_number
    elif bill_id:
        number = bill_id
    elif bill_number_int is not None:
        # As a last resort, we can't derive prefix (HB/SB) reliably here; skip if no displayNumber/billId.
        number = f"{bill_number_int}"
    else:
        return None

    # Enrich with current status
    status = "unknown"
    try:
        if bill_number_int is not None:
            sleep_throttle()
            sdata = get_current_status(BIENNIUM, bill_number_int)
            status = (sdata.get("Status") or "unknown").strip()
    except Exception:
        status = "unknown"

    record: Dict[str, Any] = {
        "id": number.replace(" ", ""),
        "number": number,
        "title": title,
        "status": status,
        "lastUpdated": datetime.now().isoformat(),
        "legUrl": LEG_SUMMARY_URL.format(num=bill_number_int if bill_number_int is not None else "", year=YEAR),
    }
    return record

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
    try:
        items = get_legislation_by_year_soap(YEAR)
    except Exception as e:
        raise SystemExit(f"Failed to fetch legislation list for {YEAR}: {e}")

    if not items:
        print("⚠️ No legislation returned. The service may be temporarily empty or you may be early in the session.")
        print("   Try re-running later or using GetLegislationInfoIntroducedSince as an alternative.")
        # continue; we still write empty files for CI stability

    bills: List[Dict[str, Any]] = []
    for i, item in enumerate(items, 1):
        try:
            rec = build_bill_record(item)
            if rec:
                bills.append(rec)
        except Exception as e:
            print(f"⚠️  Skipping item {i} due to error: {e}")

    # Sort: by prefix (HB/SB/…) then numeric
    def sort_key(b: Dict[str, Any]) -> Tuple[str, int]:
        parts = (b.get("number") or "").split()
        t = parts[0] if parts else ""
        n = 0
        if len(parts) > 1:
            try:
                n = int(parts[1])
            except Exception:
                n = 0
        return (t, n)

    bills.sort(key=sort_key)
    save_outputs(bills)

if __name__ == "__main__":
    main()

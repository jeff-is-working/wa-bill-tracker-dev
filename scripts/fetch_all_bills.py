#!/usr/bin/env python3
"""
Washington State Legislature Bill Fetcher
Fetches bills and committee meetings from the official WA Legislature Web Services API
NO SAMPLE DATA - Only real bills from the API

API Documentation: https://wslwebservices.leg.wa.gov/
"""

import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
import re
from typing import Dict, List, Optional
import time
import logging

# Configuration
API_BASE_URL = "https://wslwebservices.leg.wa.gov"
APP_BASE_URL = "https://app.leg.wa.gov"
BIENNIUM = "2025-26"
YEAR = 2026
DATA_DIR = Path("data")

# API Service endpoints
LEGISLATION_SERVICE = f"{API_BASE_URL}/LegislationService.asmx"
COMMITTEE_MEETING_SERVICE = f"{API_BASE_URL}/CommitteeMeetingService.asmx"
SPONSOR_SERVICE = f"{API_BASE_URL}/SponsorService.asmx"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def ensure_data_dir():
    """Ensure data directory exists"""
    DATA_DIR.mkdir(exist_ok=True)


def make_soap_request(url: str, soap_body: str, soap_action: str, 
                      timeout: int = 60, debug: bool = False) -> Optional[ET.Element]:
    """
    Make SOAP 1.1 request to WA Legislature Web Services
    
    Args:
        url: Service endpoint URL
        soap_body: SOAP body content (without envelope)
        soap_action: SOAPAction header value
        timeout: Request timeout in seconds
        debug: If True, save request/response to files
    
    Returns:
        Parsed XML root element or None if request fails
    """
    # Build complete SOAP envelope
    soap_envelope = f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
               xmlns:xsd="http://www.w3.org/2001/XMLSchema" 
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    {soap_body}
  </soap:Body>
</soap:Envelope>'''

    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': f'"{soap_action}"'
    }
    
    if debug:
        logger.info(f"SOAP Request to {url}")
        logger.info(f"Action: {soap_action}")
        
        # Save request for debugging
        debug_dir = DATA_DIR / "debug"
        debug_dir.mkdir(exist_ok=True)
        with open(debug_dir / "last_request.xml", 'w') as f:
            f.write(soap_envelope)
    
    try:
        response = requests.post(url, data=soap_envelope, headers=headers, timeout=timeout)
        
        if debug:
            logger.info(f"Response Status: {response.status_code}")
            with open(debug_dir / "last_response.xml", 'w') as f:
                f.write(response.text)
        
        if response.status_code != 200:
            logger.error(f"HTTP Error {response.status_code}")
            if debug:
                logger.error(response.text[:500])
            return None
        
        # Check for SOAP fault
        if '<soap:Fault>' in response.text or '<faultcode>' in response.text:
            logger.error("SOAP Fault received")
            if debug:
                logger.error(response.text[:500])
            return None
        
        # Parse XML response
        root = ET.fromstring(response.text)
        return root
        
    except requests.exceptions.Timeout:
        logger.error(f"Request timeout after {timeout} seconds")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        return None
    except ET.ParseError as e:
        logger.error(f"XML parse error: {e}")
        return None


def make_http_get_request(service: str, operation: str, params: Dict) -> Optional[str]:
    """
    Make HTTP GET request to WA Legislature Web Services
    This is an alternative to SOAP that some endpoints support
    
    Args:
        service: Service name (e.g., 'LegislationService.asmx')
        operation: Operation name
        params: Query parameters
    
    Returns:
        XML response string or None
    """
    url = f"{API_BASE_URL}/{service}/{operation}"
    
    try:
        response = requests.get(url, params=params, timeout=60)
        
        if response.status_code != 200:
            logger.warning(f"HTTP GET {operation} returned status {response.status_code}")
            return None
        
        return response.text
        
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP GET request failed: {e}")
        return None


def parse_xml_text(elem: ET.Element, tag: str, default: str = "") -> str:
    """Safely extract text from an XML element"""
    # Try with namespace
    child = elem.find(f"{{http://WSLWebServices.leg.wa.gov/}}{tag}")
    if child is not None and child.text:
        return child.text.strip()
    
    # Try without namespace
    child = elem.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    
    # Try local name match
    for child in elem:
        local_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if local_name == tag and child.text:
            return child.text.strip()
    
    return default


def parse_xml_bool(elem: ET.Element, tag: str, default: bool = False) -> bool:
    """Safely extract boolean from an XML element"""
    text = parse_xml_text(elem, tag, "")
    if text.lower() == "true":
        return True
    elif text.lower() == "false":
        return False
    return default


def determine_topic(title: str) -> str:
    """Determine bill topic from title keywords"""
    title_lower = title.lower()
    
    topic_keywords = {
        "Education": ["education", "school", "student", "teacher", "college", "university", "learning"],
        "Tax & Revenue": ["tax", "revenue", "budget", "fiscal", "fee", "levy"],
        "Housing": ["housing", "rent", "tenant", "landlord", "zoning", "homeless"],
        "Healthcare": ["health", "medical", "hospital", "mental", "drug", "pharmacy", "insurance"],
        "Environment": ["environment", "climate", "energy", "pollution", "water", "wildlife"],
        "Transportation": ["transport", "road", "highway", "transit", "traffic", "vehicle"],
        "Public Safety": ["crime", "safety", "police", "prison", "firearm", "emergency"],
        "Business": ["business", "commerce", "trade", "economy", "employment", "labor"],
        "Technology": ["technology", "internet", "data", "privacy", "cyber", "artificial intelligence"],
        "Agriculture": ["agriculture", "farm", "food", "livestock", "crop"],
        "Natural Resources": ["forest", "fish", "hunting", "mining", "land"],
    }
    
    for topic, keywords in topic_keywords.items():
        if any(kw in title_lower for kw in keywords):
            return topic
    
    return "General Government"


def determine_committee(bill_id: str, title: str) -> str:
    """Determine committee assignment based on bill type and title"""
    title_lower = title.lower()
    is_house = bill_id.startswith("H")
    
    committee_keywords = {
        "Education": ["education", "school", "student", "teacher"],
        "Transportation": ["transport", "road", "highway", "transit"],
        "Finance": ["tax", "revenue", "budget", "appropriation"] if is_house else [],
        "Ways & Means": ["tax", "revenue", "budget", "appropriation"] if not is_house else [],
        "Health Care": ["health", "medical", "hospital"] if is_house else [],
        "Health & Long Term Care": ["health", "medical", "hospital"] if not is_house else [],
        "Housing": ["housing", "rent", "tenant", "zoning"],
        "Environment & Energy": ["environment", "climate", "energy"],
        "Law & Justice": ["crime", "police", "court", "legal"],
    }
    
    for committee, keywords in committee_keywords.items():
        if any(kw in title_lower for kw in keywords):
            return committee
    
    return "State Government & Tribal Relations" if is_house else "State Government & Elections"


def determine_priority(title: str, requested_by_governor: bool = False, 
                       appropriations: bool = False) -> str:
    """Determine bill priority based on various factors"""
    title_lower = title.lower()
    
    high_priority_keywords = [
        "emergency", "budget", "appropriation", "education funding",
        "public safety", "housing crisis", "climate", "healthcare access"
    ]
    
    low_priority_keywords = [
        "technical", "clarifying", "housekeeping", "minor", "study",
        "report", "advisory"
    ]
    
    if requested_by_governor or appropriations:
        return "high"
    
    for keyword in high_priority_keywords:
        if keyword in title_lower:
            return "high"
    
    for keyword in low_priority_keywords:
        if keyword in title_lower:
            return "low"
    
    return "medium"


def determine_status_from_text(status_text: str) -> str:
    """Convert API status text to simplified status category"""
    status_lower = status_text.lower()
    
    if "prefil" in status_lower or "pre-fil" in status_lower:
        return "prefiled"
    elif "introduc" in status_lower or "first reading" in status_lower:
        return "introduced"
    elif "committee" in status_lower or "referred" in status_lower:
        return "committee"
    elif "passed" in status_lower and "senate" in status_lower and "house" in status_lower:
        return "passed"
    elif "governor" in status_lower and "signed" in status_lower:
        return "enacted"
    elif "veto" in status_lower:
        return "vetoed"
    elif "failed" in status_lower or "indefinitely" in status_lower:
        return "failed"
    elif "passed" in status_lower:
        return "passed"
    
    return "introduced"


def parse_legislation_info(leg_elem: ET.Element) -> Optional[Dict]:
    """Parse a LegislationInfo or Legislation XML element into a bill dict"""
    try:
        biennium = parse_xml_text(leg_elem, "Biennium", BIENNIUM)
        bill_id = parse_xml_text(leg_elem, "BillId", "")
        bill_number = parse_xml_text(leg_elem, "BillNumber", "")
        
        if not bill_id and not bill_number:
            return None
        
        # Get descriptions
        short_desc = parse_xml_text(leg_elem, "ShortDescription", "")
        long_desc = parse_xml_text(leg_elem, "LongDescription", "")
        title = short_desc if short_desc else long_desc
        
        if not title:
            title = "No title available"
        
        # Determine status
        current_status = parse_xml_text(leg_elem, "CurrentStatus", "")
        history_line = parse_xml_text(leg_elem, "HistoryLine", "")
        status = determine_status_from_text(current_status or history_line or "prefiled")
        
        # Parse introduced date
        intro_date = parse_xml_text(leg_elem, "IntroducedDate", "")
        if intro_date:
            try:
                dt = datetime.fromisoformat(intro_date.replace('Z', '+00:00').split('+')[0])
                intro_date = dt.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                intro_date = intro_date[:10] if len(intro_date) >= 10 else intro_date
        
        # Build clean bill number
        bill_type_match = re.match(r'^([A-Z]+)\s*(\d+)', bill_id)
        if bill_type_match:
            bill_type = bill_type_match.group(1)
            num = bill_type_match.group(2)
            clean_bill_number = f"{bill_type} {num}"
        else:
            clean_bill_number = bill_id
        
        # Get sponsor info
        sponsor = parse_xml_text(leg_elem, "Sponsor", "")
        prime_sponsor_id = parse_xml_text(leg_elem, "PrimeSponsorID", "")
        original_agency = parse_xml_text(leg_elem, "OriginalAgency", "")
        
        if not sponsor:
            if original_agency:
                sponsor = f"{original_agency} Member"
            else:
                sponsor = "Unknown"
        
        # Get request flags
        requested_by_governor = parse_xml_bool(leg_elem, "RequestedByGovernor")
        appropriations = parse_xml_bool(leg_elem, "Appropriations")
        
        # Build bill URL
        num_only = bill_number if bill_number else re.sub(r'[^0-9]', '', bill_id)
        leg_url = f"{APP_BASE_URL}/billsummary?BillNumber={num_only}&Year={YEAR}"
        
        bill = {
            "id": bill_id.replace(" ", ""),
            "number": clean_bill_number,
            "title": title,
            "description": long_desc if long_desc else title,
            "sponsor": sponsor,
            "status": status,
            "committee": determine_committee(bill_id, title),
            "priority": determine_priority(title, requested_by_governor, appropriations),
            "topic": determine_topic(title),
            "introducedDate": intro_date if intro_date else datetime.now().strftime("%Y-%m-%d"),
            "lastUpdated": datetime.now().isoformat(),
            "legUrl": leg_url,
            "hearings": [],
            "biennium": biennium,
            "requestedByGovernor": requested_by_governor,
            "appropriations": appropriations
        }
        
        return bill
        
    except Exception as e:
        logger.error(f"Error parsing legislation element: {e}")
        return None


def fetch_legislation_introduced_since(since_date: str) -> List[Dict]:
    """Fetch legislation introduced since a specific date"""
    logger.info(f"Fetching legislation introduced since {since_date}...")
    
    bills = []
    
    soap_body = f'''<GetLegislationIntroducedSince xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
      <sinceDate>{since_date}</sinceDate>
    </GetLegislationIntroducedSince>'''
    
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislationIntroducedSince",
        debug=True
    )
    
    if root is None:
        logger.warning("No response from GetLegislationIntroducedSince")
        return bills
    
    # Find all LegislationInfo elements
    for elem in root.iter():
        local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if local_name == 'LegislationInfo':
            bill = parse_legislation_info(elem)
            if bill:
                bills.append(bill)
    
    logger.info(f"    Found {len(bills)} bills introduced since {since_date}")
    return bills


def fetch_legislation_by_year(year: int) -> List[Dict]:
    """Fetch all legislation for a specific year"""
    logger.info(f"Fetching legislation for year {year}...")
    
    bills = []
    
    soap_body = f'''<GetLegislationByYear xmlns="http://WSLWebServices.leg.wa.gov/">
      <year>{year}</year>
    </GetLegislationByYear>'''
    
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislationByYear",
        debug=True
    )
    
    if root is None:
        logger.warning(f"No response from GetLegislationByYear for {year}")
        return bills
    
    # Find all LegislationInfo elements
    for elem in root.iter():
        local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if local_name == 'LegislationInfo':
            bill = parse_legislation_info(elem)
            if bill:
                bills.append(bill)
    
    logger.info(f"    Found {len(bills)} bills for year {year}")
    return bills


def fetch_prefiled_legislation() -> List[Dict]:
    """Fetch prefiled legislation for the biennium"""
    logger.info(f"Fetching prefiled legislation for biennium {BIENNIUM}...")
    
    bills = []
    
    soap_body = f'''<GetPrefiledLegislation xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
    </GetPrefiledLegislation>'''
    
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetPrefiledLegislation",
        debug=True
    )
    
    if root is None:
        logger.warning("No response from GetPrefiledLegislation")
        return bills
    
    # Find all Legislation elements (this endpoint returns full Legislation, not LegislationInfo)
    for elem in root.iter():
        local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if local_name in ('Legislation', 'LegislationInfo'):
            bill = parse_legislation_info(elem)
            if bill:
                bills.append(bill)
    
    logger.info(f"    Found {len(bills)} prefiled bills")
    return bills


def fetch_legislation_status_changes(begin_date: str, end_date: str) -> List[Dict]:
    """Fetch legislation with status changes in date range"""
    logger.info(f"Fetching status changes from {begin_date} to {end_date}...")
    
    bills = []
    
    soap_body = f'''<GetLegislativeStatusChangesByDateRange xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
      <beginDate>{begin_date}</beginDate>
      <endDate>{end_date}</endDate>
    </GetLegislativeStatusChangesByDateRange>'''
    
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislativeStatusChangesByDateRange",
        debug=False
    )
    
    if root is None:
        logger.warning("No response from GetLegislativeStatusChangesByDateRange")
        return bills
    
    for elem in root.iter():
        local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if local_name == 'LegislationInfo':
            bill = parse_legislation_info(elem)
            if bill:
                bills.append(bill)
    
    logger.info(f"    Found {len(bills)} bills with status changes")
    return bills


def parse_committee_meeting(meeting_elem: ET.Element) -> Optional[Dict]:
    """Parse a CommitteeMeeting XML element"""
    try:
        agenda_id = parse_xml_text(meeting_elem, "AgendaId", "")
        
        if not agenda_id:
            return None
        
        # Parse date and time
        date_str = parse_xml_text(meeting_elem, "Date", "")
        time_str = parse_xml_text(meeting_elem, "Time", "")
        
        meeting_date = ""
        meeting_time = ""
        
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00').split('+')[0])
                meeting_date = dt.strftime("%Y-%m-%d")
                meeting_time = dt.strftime("%I:%M %p")
            except (ValueError, AttributeError):
                meeting_date = date_str[:10] if len(date_str) >= 10 else date_str
        
        if time_str:
            meeting_time = time_str
        
        # Get other fields
        committee = parse_xml_text(meeting_elem, "Committees", "")
        if not committee:
            committee = parse_xml_text(meeting_elem, "Committee", "")
        
        agency = parse_xml_text(meeting_elem, "Agency", "")
        room = parse_xml_text(meeting_elem, "Room", "")
        building = parse_xml_text(meeting_elem, "Building", "")
        city = parse_xml_text(meeting_elem, "City", "")
        state = parse_xml_text(meeting_elem, "State", "")
        cancelled = parse_xml_bool(meeting_elem, "Cancelled")
        revised_date = parse_xml_text(meeting_elem, "RevisedDate", "")
        notes = parse_xml_text(meeting_elem, "Notes", "")
        
        # Build location
        location_parts = [p for p in [room, building, city, state] if p]
        location = ", ".join(location_parts) if location_parts else "TBD"
        
        # Build agenda URL
        agenda_url = f"{APP_BASE_URL}/committeeschedules/?agenda={agenda_id}"
        
        meeting = {
            "agendaId": agenda_id,
            "date": meeting_date,
            "time": meeting_time,
            "committee": committee,
            "agency": agency,
            "location": location,
            "room": room,
            "building": building,
            "cancelled": cancelled,
            "notes": notes,
            "agendaUrl": agenda_url,
            "revisedDate": revised_date
        }
        
        return meeting
        
    except Exception as e:
        logger.error(f"Error parsing committee meeting: {e}")
        return None


def fetch_committee_meetings() -> List[Dict]:
    """Fetch committee meetings for the current period"""
    logger.info("Fetching committee meetings...")
    
    meetings = []
    
    # Get meetings revised since 30 days ago to catch upcoming meetings
    changed_since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
    
    soap_body = f'''<GetRevisedCommitteeMeetings xmlns="http://WSLWebServices.leg.wa.gov/">
      <changedSinceDate>{changed_since}</changedSinceDate>
    </GetRevisedCommitteeMeetings>'''
    
    root = make_soap_request(
        COMMITTEE_MEETING_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetRevisedCommitteeMeetings",
        debug=True
    )
    
    if root is None:
        logger.warning("No response from GetRevisedCommitteeMeetings")
        return meetings
    
    for elem in root.iter():
        local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if local_name == 'CommitteeMeeting':
            meeting = parse_committee_meeting(elem)
            if meeting:
                meetings.append(meeting)
    
    # Filter to only upcoming meetings (not cancelled)
    today = datetime.now().date()
    upcoming = []
    for m in meetings:
        if m['date'] and not m['cancelled']:
            try:
                meeting_date = datetime.strptime(m['date'], "%Y-%m-%d").date()
                if meeting_date >= today:
                    upcoming.append(m)
            except ValueError:
                pass
    
    # Sort by date
    upcoming.sort(key=lambda x: x['date'])
    
    logger.info(f"    Found {len(upcoming)} upcoming committee meetings")
    return upcoming


def load_existing_data() -> Dict:
    """Load existing bills data if it exists"""
    data_file = DATA_DIR / "bills.json"
    if data_file.exists():
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not load existing data: {e}")
    return {}


def save_bills_data(bills: List[Dict]) -> Dict:
    """Save bills data to JSON file"""
    # Sort bills by type then number
    def sort_key(bill):
        parts = bill['number'].split()
        bill_type = parts[0] if parts else ""
        bill_num = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return (bill_type, bill_num)
    
    bills.sort(key=sort_key)
    
    data = {
        "lastSync": datetime.now().isoformat(),
        "sessionYear": YEAR,
        "biennium": BIENNIUM,
        "sessionStart": "2026-01-12",
        "sessionEnd": "2026-03-12",
        "totalBills": len(bills),
        "bills": bills,
        "metadata": {
            "source": "Washington State Legislature Web Services",
            "apiUrl": API_BASE_URL,
            "updateFrequency": "daily",
            "dataVersion": "3.0.0",
            "billTypes": ["HB", "SB", "HJR", "SJR", "HJM", "SJM", "HCR", "SCR", "HI", "SI"]
        }
    }
    
    data_file = DATA_DIR / "bills.json"
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved {len(bills)} bills to {data_file}")
    return data


def save_meetings_data(meetings: List[Dict]) -> Dict:
    """Save meetings data to JSON file"""
    # Filter to upcoming meetings in next 14 days
    today = datetime.now().date()
    cutoff = today + timedelta(days=14)
    
    upcoming = []
    this_week = []
    
    for m in meetings:
        if m['date']:
            try:
                meeting_date = datetime.strptime(m['date'], "%Y-%m-%d").date()
                if today <= meeting_date <= cutoff:
                    upcoming.append(m)
                    if meeting_date <= today + timedelta(days=7):
                        this_week.append(m)
            except ValueError:
                pass
    
    data = {
        "lastSync": datetime.now().isoformat(),
        "totalMeetings": len(meetings),
        "upcomingMeetings": len(upcoming),
        "meetingsThisWeek": len(this_week),
        "meetings": meetings
    }
    
    data_file = DATA_DIR / "meetings.json"
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved {len(meetings)} meetings to {data_file}")
    return data


def create_stats_file(bills: List[Dict], meetings: List[Dict]):
    """Create comprehensive statistics file"""
    today = datetime.now().date()
    week_end = today + timedelta(days=7)
    
    stats = {
        "generated": datetime.now().isoformat(),
        "totalBills": len(bills),
        "byStatus": {},
        "byCommittee": {},
        "byPriority": {},
        "byTopic": {},
        "byType": {},
        "bySponsor": {},
        "recentlyUpdated": 0,
        "updatedToday": 0,
        "meetingsThisWeek": 0,
        "upcomingHearings": 0
    }
    
    for bill in bills:
        # By status
        status = bill.get('status', 'unknown')
        stats['byStatus'][status] = stats['byStatus'].get(status, 0) + 1
        
        # By committee
        committee = bill.get('committee', 'unknown')
        stats['byCommittee'][committee] = stats['byCommittee'].get(committee, 0) + 1
        
        # By priority
        priority = bill.get('priority', 'medium')
        stats['byPriority'][priority] = stats['byPriority'].get(priority, 0) + 1
        
        # By topic
        topic = bill.get('topic', 'General Government')
        stats['byTopic'][topic] = stats['byTopic'].get(topic, 0) + 1
        
        # By type
        bill_type = bill['number'].split()[0] if ' ' in bill['number'] else 'Unknown'
        stats['byType'][bill_type] = stats['byType'].get(bill_type, 0) + 1
        
        # By sponsor
        sponsor = bill.get('sponsor', 'Unknown')
        stats['bySponsor'][sponsor] = stats['bySponsor'].get(sponsor, 0) + 1
        
        # Recently updated
        try:
            last_updated = datetime.fromisoformat(bill.get('lastUpdated', ''))
            if (datetime.now() - last_updated).days < 1:
                stats['recentlyUpdated'] += 1
            if last_updated.date() == today:
                stats['updatedToday'] += 1
        except (ValueError, TypeError):
            pass
    
    # Count meetings this week
    for meeting in meetings:
        if meeting.get('date') and not meeting.get('cancelled'):
            try:
                meeting_date = datetime.strptime(meeting['date'], "%Y-%m-%d").date()
                if today <= meeting_date <= week_end:
                    stats['meetingsThisWeek'] += 1
            except ValueError:
                pass
    
    stats['upcomingHearings'] = stats['meetingsThisWeek']
    
    # Top sponsors
    stats['topSponsors'] = sorted(
        stats['bySponsor'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]
    
    stats_file = DATA_DIR / "stats.json"
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2)
    
    logger.info(f"Statistics: {len(stats['byStatus'])} statuses, {len(stats['byCommittee'])} committees")


def create_sync_log(bills_count: int, meetings_count: int, new_count: int, status: str):
    """Create sync log for monitoring"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "billsCount": bills_count,
        "meetingsCount": meetings_count,
        "newBillsAdded": new_count,
        "nextSync": (datetime.now() + timedelta(hours=6)).isoformat()
    }
    
    log_file = DATA_DIR / "sync-log.json"
    
    logs = []
    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
                data = json.load(f)
                logs = data.get('logs', [])
        except (json.JSONDecodeError, IOError):
            pass
    
    logs.insert(0, log_entry)
    logs = logs[:100]  # Keep last 100 entries
    
    with open(log_file, 'w') as f:
        json.dump({"logs": logs}, f, indent=2)
    
    logger.info(f"Sync log updated: {status} - {bills_count} bills, {meetings_count} meetings")


def main():
    """Main execution function"""
    print(f"Starting WA Legislature Bill Fetcher - {datetime.now()}")
    print("=" * 60)
    
    ensure_data_dir()
    
    # Load existing data for comparison
    existing_data = load_existing_data()
    existing_bills = {bill['id']: bill for bill in existing_data.get('bills', [])}
    logger.info(f"Loaded {len(existing_bills)} existing bills")
    
    # Collect bills from multiple sources
    all_bills = {}
    
    # Method 1: Get bills introduced since December 1, 2025 (pre-filing period)
    print("\n[STEP 1] Fetching legislation from multiple sources...")
    
    since_date = "2025-12-01T00:00:00"
    introduced_bills = fetch_legislation_introduced_since(since_date)
    for bill in introduced_bills:
        all_bills[bill['id']] = bill
    
    # Method 2: Get bills by year 2026
    year_bills = fetch_legislation_by_year(YEAR)
    for bill in year_bills:
        if bill['id'] not in all_bills:
            all_bills[bill['id']] = bill
    
    # Method 3: Get prefiled legislation
    prefiled_bills = fetch_prefiled_legislation()
    for bill in prefiled_bills:
        if bill['id'] not in all_bills:
            all_bills[bill['id']] = bill
    
    # Method 4: Get recent status changes
    begin_date = "2025-12-01T00:00:00"
    end_date = datetime.now().isoformat()
    status_change_bills = fetch_legislation_status_changes(begin_date, end_date)
    for bill in status_change_bills:
        if bill['id'] not in all_bills:
            all_bills[bill['id']] = bill
    
    final_bills = list(all_bills.values())
    logger.info(f"Total bills after deduplication: {len(final_bills)}")
    
    # Count new bills
    new_bills = [b for b in final_bills if b['id'] not in existing_bills]
    logger.info(f"New bills: {len(new_bills)}")
    
    # Fetch committee meetings
    print("\n[STEP 2] Fetching committee meetings...")
    meetings = fetch_committee_meetings()
    
    # Save data
    print("\n[STEP 3] Saving data...")
    save_bills_data(final_bills)
    save_meetings_data(meetings)
    
    # Create statistics
    print("\n[STEP 4] Creating statistics...")
    create_stats_file(final_bills, meetings)
    
    # Create sync log
    create_sync_log(len(final_bills), len(meetings), len(new_bills), "success")
    
    print("\n" + "=" * 60)
    print(f"[COMPLETE] Database updated successfully:")
    print(f"   - Total bills: {len(final_bills)}")
    print(f"   - New bills: {len(new_bills)}")
    print(f"   - Committee meetings: {len(meetings)}")
    print(f"   - Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if len(final_bills) == 0:
        print("\n[WARNING] No bills were retrieved from the API.")
        print("This may indicate:")
        print("  - The API may not have data for this biennium yet")
        print("  - Network connectivity issues")
        print("  - Check data/debug/ folder for request/response XML files")
    
    print("=" * 60)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Washington State Legislature Bill Fetcher
Fetches bills from the official WA Legislature Web Services API
NO SAMPLE DATA - Only real bills from the API
"""

import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
from pathlib import Path
import time
from typing import Dict, List, Optional
import re

# Configuration
BASE_API_URL = "https://wslwebservices.leg.wa.gov"
BASE_WEB_URL = "https://app.leg.wa.gov"
BIENNIUM = "2025-26"
CURRENT_YEAR = 2026
DATA_DIR = Path("data")

# SOAP Service Endpoints
LEGISLATION_SERVICE = f"{BASE_API_URL}/LegislationService.asmx"
COMMITTEE_SERVICE = f"{BASE_API_URL}/CommitteeService.asmx"
COMMITTEE_MEETING_SERVICE = f"{BASE_API_URL}/CommitteeMeetingService.asmx"

# Namespace definitions for XML parsing
NAMESPACES = {
    'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
    'wsl': 'http://WSLWebServices.leg.wa.gov/'
}

def ensure_data_dir():
    """Ensure data directory exists"""
    DATA_DIR.mkdir(exist_ok=True)

def make_soap_request(url: str, soap_body: str, soap_action: str) -> Optional[ET.Element]:
    """Make SOAP request to WA Legislature API"""
    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': soap_action
    }
    
    soap_envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
               xmlns:xsd="http://www.w3.org/2001/XMLSchema" 
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    {soap_body}
  </soap:Body>
</soap:Envelope>"""
    
    try:
        response = requests.post(url, data=soap_envelope, headers=headers, timeout=60)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            return root
        else:
            print(f"API Error {response.status_code}: {response.text[:500]}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None
    except ET.ParseError as e:
        print(f"XML parsing error: {e}")
        return None

def fetch_all_legislation() -> List[Dict]:
    """Fetch all legislation for the current biennium"""
    print(f"Fetching all legislation for biennium {BIENNIUM}")
    
    soap_body = f"""
    <GetLegislationByYear xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
      <year>{CURRENT_YEAR}</year>
    </GetLegislationByYear>"""
    
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislationByYear"
    )
    
    if root is None:
        print("Failed to fetch legislation data")
        return []
    
    bills = []
    
    # Parse the XML response
    # Find all legislation items in the response
    for legislation in root.findall('.//wsl:LegislationInfo', NAMESPACES):
        bill_data = parse_legislation_info(legislation)
        if bill_data:
            bills.append(bill_data)
    
    # Also try without namespace if the above doesn't work
    if not bills:
        for legislation in root.findall('.//LegislationInfo'):
            bill_data = parse_legislation_info(legislation)
            if bill_data:
                bills.append(bill_data)
    
    return bills

def fetch_prefiled_legislation() -> List[Dict]:
    """Fetch prefiled legislation for the biennium"""
    print(f"Fetching prefiled legislation for biennium {BIENNIUM}")
    
    soap_body = f"""
    <GetPrefiledLegislationInfo xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
    </GetPrefiledLegislationInfo>"""
    
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetPrefiledLegislationInfo"
    )
    
    if root is None:
        return []
    
    bills = []
    
    # Parse the XML response
    for legislation in root.findall('.//wsl:LegislationInfo', NAMESPACES):
        bill_data = parse_legislation_info(legislation)
        if bill_data:
            bills.append(bill_data)
    
    # Also try without namespace
    if not bills:
        for legislation in root.findall('.//LegislationInfo'):
            bill_data = parse_legislation_info(legislation)
            if bill_data:
                bills.append(bill_data)
    
    return bills

def parse_legislation_info(elem: ET.Element) -> Optional[Dict]:
    """Parse LegislationInfo XML element into bill dictionary"""
    try:
        # Helper function to safely get text from element
        def get_text(name: str, default: str = "") -> str:
            child = elem.find(name)
            if child is None:
                child = elem.find(f".//{name}")
            return child.text if child is not None and child.text else default
        
        # Extract bill information
        biennium = get_text("Biennium", BIENNIUM)
        bill_id = get_text("BillId")
        bill_number = get_text("BillNumber")
        
        # Skip if no bill ID or number
        if not bill_id or not bill_number:
            return None
        
        # Get bill type from bill number (e.g., "5872" -> need to determine if HB or SB)
        # The CurrentStatus or other fields might indicate chamber
        substitute_version = get_text("SubstituteVersion", "")
        engrossed_version = get_text("EngrossedVersion", "")
        
        # Determine chamber from various indicators
        original_agency = get_text("OriginalAgency", "").upper()
        if "HOUSE" in original_agency:
            bill_prefix = "HB"
        elif "SENATE" in original_agency:
            bill_prefix = "SB"
        else:
            # Try to infer from bill number range
            try:
                num = int(bill_number)
                if num >= 5000:
                    bill_prefix = "SB"
                else:
                    bill_prefix = "HB"
            except:
                bill_prefix = ""
        
        # Build full bill number with prefix
        if substitute_version:
            full_bill_number = f"{substitute_version}{bill_prefix} {bill_number}"
        elif engrossed_version:
            full_bill_number = f"{engrossed_version}{bill_prefix} {bill_number}"
        else:
            full_bill_number = f"{bill_prefix} {bill_number}" if bill_prefix else bill_number
        
        # Clean up the bill number
        full_bill_number = re.sub(r'\s+', ' ', full_bill_number.strip())
        
        # Get other bill details
        short_description = get_text("ShortDescription", "No title available")
        long_description = get_text("LongDescription", "")
        
        # Get sponsor information
        prime_sponsor_id = get_text("PrimeSponsorID")
        prime_sponsor = get_text("PrimeSponsor", "")
        request_exec = get_text("RequestExec", "")
        htmurl = get_text("HtmUrl", "")
        
        # Get status information
        current_status = get_text("CurrentStatus", "")
        if not current_status:
            # Try alternate status fields
            status = get_text("Status", "prefiled")
        else:
            status = current_status.lower()
            if "prefiled" in status:
                status = "prefiled"
            elif "introduced" in status:
                status = "introduced"
            elif "committee" in status:
                status = "committee"
            elif "passed" in status:
                status = "passed"
            elif "failed" in status:
                status = "failed"
            else:
                status = "active"
        
        # Get dates
        introduced_date = get_text("IntroducedDate", "")
        action_date = get_text("ActionDate", "")
        
        # Parse date strings
        try:
            if introduced_date:
                introduced_date = datetime.fromisoformat(introduced_date.replace('Z', '+00:00')).date().isoformat()
            else:
                introduced_date = "2026-01-12"  # Session start date as default
        except:
            introduced_date = "2026-01-12"
        
        # Determine committee from short description or other fields
        committee = determine_committee(full_bill_number, short_description)
        
        # Create bill dictionary
        bill = {
            "id": bill_id,
            "number": full_bill_number,
            "title": short_description,
            "sponsor": prime_sponsor if prime_sponsor else request_exec if request_exec else "Unknown",
            "description": long_description if long_description else f"A bill relating to {short_description.lower()}",
            "status": status,
            "committee": committee,
            "priority": determine_priority(short_description),
            "topic": determine_topic(short_description),
            "introducedDate": introduced_date,
            "lastUpdated": datetime.now().isoformat(),
            "legUrl": f"{BASE_WEB_URL}/billsummary?BillNumber={bill_number}&Year={CURRENT_YEAR}",
            "biennium": biennium,
            "hearings": []
        }
        
        return bill
        
    except Exception as e:
        print(f"Error parsing legislation: {e}")
        return None

def fetch_legislation_by_request_number(request_number: str) -> Optional[Dict]:
    """Fetch specific legislation by request number"""
    soap_body = f"""
    <GetLegislationByRequestNumber xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
      <requestNumber>{request_number}</requestNumber>
    </GetLegislationByRequestNumber>"""
    
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislationByRequestNumber"
    )
    
    if root:
        # Parse single legislation response
        legislation = root.find('.//wsl:LegislationInfo', NAMESPACES)
        if legislation is None:
            legislation = root.find('.//LegislationInfo')
        
        if legislation:
            return parse_legislation_info(legislation)
    
    return None

def fetch_committee_meetings() -> List[Dict]:
    """Fetch committee meetings to get hearing information"""
    print("Fetching committee meetings for hearing information")
    
    soap_body = f"""
    <GetCommitteeMeetings xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
    </GetCommitteeMeetings>"""
    
    root = make_soap_request(
        COMMITTEE_MEETING_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetCommitteeMeetings"
    )
    
    hearings = []
    if root:
        for meeting in root.findall('.//Meeting'):
            try:
                date = meeting.find('Date')
                committee = meeting.find('Committee')
                location = meeting.find('Location')
                
                if date is not None and committee is not None:
                    hearing = {
                        "date": date.text,
                        "committee": committee.text,
                        "location": location.text if location is not None else "TBD"
                    }
                    hearings.append(hearing)
            except Exception as e:
                print(f"Error parsing meeting: {e}")
                continue
    
    return hearings

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
    elif "tax" in title_lower or "revenue" in title_lower or "budget" in title_lower:
        if bill_number.startswith("HB"):
            return "Finance"
        else:
            return "Ways & Means"
    elif "consumer" in title_lower or "business" in title_lower:
        return "Consumer Protection & Business"
    elif "crime" in title_lower or "safety" in title_lower or "justice" in title_lower:
        return "Law & Justice"
    elif "labor" in title_lower or "employment" in title_lower or "worker" in title_lower:
        return "Labor & Commerce"
    else:
        return "State Government & Tribal Relations"

def determine_topic(title: str) -> str:
    """Determine bill topic from title"""
    title_lower = title.lower()
    
    topics = {
        "Education": ["education", "school", "student", "teacher", "learning", "academic"],
        "Tax & Revenue": ["tax", "revenue", "budget", "fiscal", "fee", "expenditure"],
        "Housing": ["housing", "rent", "tenant", "landlord", "affordable", "homeless"],
        "Healthcare": ["health", "medical", "hospital", "mental", "behavioral", "insurance"],
        "Environment": ["environment", "climate", "energy", "pollution", "conservation", "water"],
        "Transportation": ["transport", "road", "highway", "transit", "traffic", "vehicle"],
        "Public Safety": ["crime", "safety", "police", "justice", "criminal", "enforcement"],
        "Business": ["business", "commerce", "trade", "economy", "corporation", "industry"],
        "Technology": ["technology", "internet", "data", "privacy", "cyber", "digital"],
        "Labor": ["labor", "employment", "worker", "wage", "union", "workplace"],
        "Agriculture": ["agriculture", "farm", "food", "rural", "agricultural"],
    }
    
    for topic, keywords in topics.items():
        if any(keyword in title_lower for keyword in keywords):
            return topic
    
    return "General Government"

def determine_priority(title: str) -> str:
    """Determine bill priority based on keywords in title"""
    title_lower = title.lower()
    
    # High priority keywords
    high_priority = ["emergency", "urgent", "crisis", "immediate", "critical",
                    "budget", "appropriations", "supplemental"]
    
    # Low priority keywords  
    low_priority = ["technical", "clarifying", "housekeeping", "minor", "study",
                   "memorial", "proclamation", "commendation"]
    
    for keyword in high_priority:
        if keyword in title_lower:
            return "high"
    
    for keyword in low_priority:
        if keyword in title_lower:
            return "low"
    
    return "medium"

def save_bills_data(bills: List[Dict]) -> Dict:
    """Save bills data to JSON file"""
    # Remove duplicates based on bill ID
    unique_bills = {}
    for bill in bills:
        bill_id = bill.get('id')
        if bill_id and bill_id not in unique_bills:
            unique_bills[bill_id] = bill
    
    bills = list(unique_bills.values())
    
    # Sort bills by type and number
    def sort_key(bill):
        number = bill.get('number', '')
        parts = number.split()
        if len(parts) >= 2:
            # Extract type and number
            bill_type = re.sub(r'[0-9]', '', parts[0])  # Remove numbers from type
            try:
                bill_num = int(re.findall(r'\d+', parts[-1])[0])
            except:
                bill_num = 0
            return (bill_type, bill_num)
        return ('', 0)
    
    bills.sort(key=sort_key)
    
    data = {
        "lastSync": datetime.now().isoformat(),
        "sessionYear": CURRENT_YEAR,
        "biennium": BIENNIUM,
        "sessionStart": "2026-01-12",
        "sessionEnd": "2026-03-12",
        "totalBills": len(bills),
        "bills": bills,
        "metadata": {
            "source": "Washington State Legislature Web Services",
            "apiUrl": BASE_API_URL,
            "updateFrequency": "daily",
            "dataVersion": "3.0.0",
            "billTypes": ["HB", "SB", "HJR", "SJR", "HJM", "SJM", "HCR", "SCR", "I", "R"]
        }
    }
    
    data_file = DATA_DIR / "bills.json"
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(bills)} bills to {data_file}")
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
        with open(log_file, 'r') as f:
            data = json.load(f)
            logs = data.get('logs', [])
    
    # Add new log entry (keep last 100 entries)
    logs.insert(0, log)
    logs = logs[:100]
    
    # Save logs
    with open(log_file, 'w') as f:
        json.dump({"logs": logs}, f, indent=2)
    
    print(f"Sync log updated: {status} - {bills_count} bills, {new_count} new")

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
        bill_number = bill.get('number', '')
        bill_type = bill_number.split()[0] if ' ' in bill_number else 'unknown'
        bill_type = re.sub(r'[0-9]', '', bill_type)  # Remove numbers
        stats['byType'][bill_type] = stats['byType'].get(bill_type, 0) + 1
        
        # Recently updated
        try:
            last_updated = datetime.fromisoformat(bill.get('lastUpdated', ''))
            days_diff = (datetime.now() - last_updated).days
            
            if days_diff < 1:
                stats['recentlyUpdated'] += 1
            
            if last_updated.date() == today:
                stats['updatedToday'] += 1
                
        except:
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
                except:
                    pass
    
    # Sort sponsors by count (top 20)
    stats['topSponsors'] = sorted(
        stats['bySponsor'].items(), 
        key=lambda x: x[1], 
        reverse=True
    )[:20]
    
    stats_file = DATA_DIR / "stats.json"
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f"Statistics file updated")

def main():
    """Main execution function"""
    print(f"Starting WA Legislature Bill Fetcher - {datetime.now()}")
    print("=" * 60)
    
    # Ensure data directory exists
    ensure_data_dir()
    
    # Keep track of all bills
    all_bills = {}
    
    # 1. Fetch all legislation for current year
    print("\n1. Fetching all legislation for current year...")
    current_year_bills = fetch_all_legislation()
    for bill in current_year_bills:
        if bill['id'] not in all_bills:
            all_bills[bill['id']] = bill
    print(f"   Found {len(current_year_bills)} bills from current year")
    
    # 2. Fetch prefiled legislation
    print("\n2. Fetching prefiled legislation...")
    prefiled_bills = fetch_prefiled_legislation()
    new_prefiled = 0
    for bill in prefiled_bills:
        if bill['id'] not in all_bills:
            all_bills[bill['id']] = bill
            new_prefiled += 1
    print(f"   Found {len(prefiled_bills)} prefiled bills ({new_prefiled} new)")
    
    # 3. Fetch committee meetings for hearings
    print("\n3. Fetching committee meetings...")
    hearings = fetch_committee_meetings()
    print(f"   Found {len(hearings)} committee meetings")
    
    # Convert to list for saving
    final_bills = list(all_bills.values())
    
    print("\n" + "=" * 60)
    print(f"Total unique bills collected: {len(final_bills)}")
    
    # Save bills data
    save_bills_data(final_bills)
    
    # Create statistics
    create_stats_file(final_bills)
    
    # Create sync log
    create_sync_log(len(final_bills), 0, "success")
    
    print("=" * 60)
    print(f"Successfully fetched and saved {len(final_bills)} bills")
    print(f"Update complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()

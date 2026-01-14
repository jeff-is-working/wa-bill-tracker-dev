#!/usr/bin/env python3
"""
Washington State Legislature Bill Fetcher - SOAP API Version
Fetches ALL bills from the official WA Legislature SOAP Web Services
NO SAMPLE DATA - Only real bills from the API
"""

import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple
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
SPONSOR_SERVICE = f"{BASE_API_URL}/SponsorService.asmx"

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
            # Parse the XML response
            root = ET.fromstring(response.content)
            return root
        else:
            print(f"API Error {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None
    except ET.ParseError as e:
        print(f"XML parsing error: {e}")
        return None

def parse_xml_response(root: ET.Element) -> List[Dict]:
    """Parse SOAP XML response and extract bill data"""
    bills = []
    
    # Define namespace
    ns = {
        'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
        'wsl': 'http://WSLWebServices.leg.wa.gov/'
    }
    
    # Find all ArrayOfLegislationInfo elements
    for elem in root.iter():
        if 'LegislationInfo' in elem.tag:
            bill_data = parse_legislation_element(elem)
            if bill_data:
                bills.append(bill_data)
    
    return bills

def parse_legislation_element(elem: ET.Element) -> Optional[Dict]:
    """Parse a single LegislationInfo element"""
    try:
        # Helper function to get text from child element
        def get_text(tag_name: str, default: str = '') -> str:
            child = elem.find(f'.//{tag_name}')
            if child is not None and child.text:
                return child.text.strip()
            # Try without namespace
            for child in elem:
                if tag_name in child.tag:
                    if child.text:
                        return child.text.strip()
            return default
        
        # Extract basic information
        biennium = get_text('Biennium', BIENNIUM)
        bill_id = get_text('BillId', '')
        bill_number = get_text('BillNumber', '')
        
        # Skip if no bill ID
        if not bill_id and not bill_number:
            return None
        
        # Get title and description
        short_desc = get_text('ShortDescription', '')
        long_desc = get_text('LongDescription', '')
        
        # Skip bills with no title
        if not short_desc and not long_desc:
            return None
        
        title = short_desc if short_desc else (long_desc[:100] + '...' if len(long_desc) > 100 else long_desc)
        
        # Format bill number properly
        if bill_id:
            # Extract type and number from BillId (e.g., "HB 1001", "SB 5001")
            # Handle various formats like "2SHB 1001", "ESSB 5001", etc.
            match = re.search(r'([A-Z]+)\s*(\d+)', bill_id)
            if match:
                # Find the actual bill type (HB, SB, HJR, etc.)
                if 'HB' in bill_id:
                    bill_type = 'HB'
                elif 'SB' in bill_id:
                    bill_type = 'SB'
                elif 'HJR' in bill_id:
                    bill_type = 'HJR'
                elif 'SJR' in bill_id:
                    bill_type = 'SJR'
                elif 'HJM' in bill_id:
                    bill_type = 'HJM'
                elif 'SJM' in bill_id:
                    bill_type = 'SJM'
                elif 'HCR' in bill_id:
                    bill_type = 'HCR'
                elif 'SCR' in bill_id:
                    bill_type = 'SCR'
                else:
                    bill_type = match.group(1)
                
                number = match.group(2)
                formatted_number = f"{bill_type} {number}"
                formatted_id = f"{bill_type}{number}"
            else:
                formatted_number = bill_id
                formatted_id = bill_id.replace(' ', '')
        else:
            formatted_number = f"BILL {bill_number}"
            formatted_id = f"BILL{bill_number}"
        
        # Get sponsor
        prime_sponsor = get_text('PrimeSponsor', '')
        if not prime_sponsor:
            # Try to get from Sponsors list
            sponsor_elem = elem.find('.//Sponsor')
            if sponsor_elem is not None:
                prime_sponsor = get_text('Name', 'Unknown')
            else:
                prime_sponsor = 'Unknown'
        
        # Get status
        current_status = get_text('CurrentStatus', '')
        if not current_status:
            # Try to get from nested Status element
            status_elem = elem.find('.//Status')
            if status_elem is not None:
                current_status = status_elem.text if status_elem.text else 'Introduced'
            else:
                current_status = 'Introduced'
        
        # Get dates
        introduced_date = get_text('IntroducedDate', '')
        if introduced_date:
            try:
                # Parse ISO format date
                dt = datetime.fromisoformat(introduced_date.replace('Z', '+00:00').split('T')[0])
                introduced_date = dt.strftime('%Y-%m-%d')
            except:
                pass
        
        # Get committee
        committee = get_text('Committee', '')
        if not committee:
            # Determine from bill type
            if formatted_number.startswith('HB') or formatted_number.startswith('HJR'):
                committee = "House Rules"
            elif formatted_number.startswith('SB') or formatted_number.startswith('SJR'):
                committee = "Senate Rules"
            else:
                committee = "Rules"
        
        # Create bill object matching app.js structure
        bill = {
            "id": formatted_id,
            "number": formatted_number,
            "title": title,
            "sponsor": prime_sponsor,
            "description": long_desc if long_desc else title,
            "status": current_status,
            "committee": committee,
            "priority": determine_priority(title),
            "topic": determine_topic(title),
            "introducedDate": introduced_date,
            "lastUpdated": datetime.now().isoformat(),
            "legUrl": f"{BASE_WEB_URL}/billsummary?BillNumber={number if 'number' in locals() else bill_number}&Year={CURRENT_YEAR}",
            "hearings": [],
            "biennium": biennium,
            "originalBillId": bill_id
        }
        
        return bill
        
    except Exception as e:
        # Silently skip malformed bills
        return None

def fetch_all_legislation_by_biennium() -> List[Dict]:
    """Fetch ALL bills for the current biennium using GetLegislationInfoBiennium"""
    bills = []
    
    soap_body = f"""
    <GetLegislationInfoBiennium xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
    </GetLegislationInfoBiennium>"""
    
    print(f"Fetching ALL legislation for biennium {BIENNIUM}...")
    
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislationInfoBiennium"
    )
    
    if root:
        bills = parse_xml_response(root)
        print(f"  Found {len(bills)} bills from GetLegislationInfoBiennium")
    else:
        print("  Failed to get response from GetLegislationInfoBiennium")
    
    return bills

def fetch_active_legislation() -> List[Dict]:
    """Fetch active/current legislation using GetLegislativeStatusChangesByDateRange"""
    bills = []
    
    # Get bills with status changes in the last 60 days
    begin_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    soap_body = f"""
    <GetLegislativeStatusChangesByDateRange xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
      <beginDate>{begin_date}</beginDate>
      <endDate>{end_date}</endDate>
    </GetLegislativeStatusChangesByDateRange>"""
    
    print(f"Fetching active legislation from {begin_date} to {end_date}...")
    
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislativeStatusChangesByDateRange"
    )
    
    if root:
        # Parse status change records
        for elem in root.iter():
            if 'LegislativeStatus' in elem.tag or 'StatusChange' in elem.tag:
                bill_id = None
                for child in elem:
                    if 'BillId' in child.tag and child.text:
                        bill_id = child.text.strip()
                        break
                
                if bill_id:
                    # Fetch full details for this bill
                    bill_data = fetch_bill_details(bill_id)
                    if bill_data:
                        bills.append(bill_data)
        
        print(f"  Found {len(bills)} active bills")
    
    return bills

def fetch_bill_details(bill_id: str) -> Optional[Dict]:
    """Fetch detailed information for a specific bill"""
    # Extract bill number from ID
    match = re.search(r'(\d+)', bill_id)
    if not match:
        return None
    
    bill_number = match.group(1)
    
    soap_body = f"""
    <GetLegislation xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
      <billNumber>{bill_number}</billNumber>
    </GetLegislation>"""
    
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislation"
    )
    
    if root:
        # Find the Legislation element
        for elem in root.iter():
            if 'Legislation' in elem.tag and 'Service' not in elem.tag:
                return parse_legislation_element(elem)
    
    return None

def fetch_hearings_for_bills(bills: List[Dict]) -> None:
    """Fetch hearing information for bills"""
    print("Fetching hearing information...")
    
    soap_body = f"""
    <GetCommitteeMeetings xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
    </GetCommitteeMeetings>"""
    
    root = make_soap_request(
        COMMITTEE_MEETING_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetCommitteeMeetings"
    )
    
    if root:
        # Parse committee meetings and match to bills
        hearings_by_bill = {}
        
        for meeting in root.iter():
            if 'Meeting' in meeting.tag:
                meeting_date = ''
                meeting_time = ''
                committee_name = ''
                agenda_items = []
                
                for child in meeting:
                    if 'Date' in child.tag and child.text:
                        meeting_date = child.text.split('T')[0]
                    elif 'Time' in child.tag and child.text:
                        meeting_time = child.text
                    elif 'CommitteeName' in child.tag and child.text:
                        committee_name = child.text
                    elif 'AgendaItem' in child.tag:
                        for item_child in child:
                            if 'BillId' in item_child.tag and item_child.text:
                                agenda_items.append(item_child.text.strip())
                
                # Add hearings to bills
                for bill_id in agenda_items:
                    if bill_id not in hearings_by_bill:
                        hearings_by_bill[bill_id] = []
                    
                    hearings_by_bill[bill_id].append({
                        "date": meeting_date,
                        "time": meeting_time,
                        "committee": committee_name,
                        "type": "Public Hearing"
                    })
        
        # Apply hearings to bills
        for bill in bills:
            original_id = bill.get('originalBillId', '')
            if original_id in hearings_by_bill:
                bill['hearings'] = hearings_by_bill[original_id]

def determine_topic(title: str) -> str:
    """Determine bill topic from title"""
    if not title:
        return "General Government"
    
    title_lower = title.lower()
    
    topic_keywords = {
        "Education": ["education", "school", "student", "teacher", "learning", "academic"],
        "Tax & Revenue": ["tax", "revenue", "budget", "fiscal", "finance", "appropriation"],
        "Housing": ["housing", "rent", "tenant", "landlord", "homelessness", "affordable"],
        "Healthcare": ["health", "medical", "hospital", "mental", "pharmacy", "insurance"],
        "Environment": ["environment", "climate", "energy", "pollution", "conservation"],
        "Transportation": ["transport", "road", "highway", "transit", "vehicle", "traffic"],
        "Public Safety": ["crime", "safety", "police", "justice", "corrections", "emergency"],
        "Business": ["business", "commerce", "trade", "economy", "corporation", "employment"],
        "Technology": ["technology", "internet", "data", "privacy", "cyber", "artificial"],
        "Agriculture": ["agriculture", "farm", "rural", "livestock", "crop", "food"]
    }
    
    for topic, keywords in topic_keywords.items():
        if any(keyword in title_lower for keyword in keywords):
            return topic
    
    return "General Government"

def determine_priority(title: str) -> str:
    """Determine bill priority from title"""
    if not title:
        return "medium"
    
    title_lower = title.lower()
    
    # High priority keywords
    if any(word in title_lower for word in 
           ["emergency", "budget", "appropriation", "supplemental", "capital"]):
        return "high"
    
    # Low priority keywords
    if any(word in title_lower for word in 
           ["technical", "clarifying", "housekeeping", "minor", "memorial"]):
        return "low"
    
    return "medium"

def save_bills_data(bills: List[Dict]) -> Dict:
    """Save bills data to JSON file matching app.js structure"""
    # Sort bills by type and number
    def sort_key(bill):
        match = re.match(r'([A-Z]+)\s*(\d+)', bill['number'])
        if match:
            bill_type = match.group(1)
            number = int(match.group(2))
            # Sort order for bill types
            type_order = {'HB': 1, 'SB': 2, 'HJR': 3, 'SJR': 4, 'HJM': 5, 'SJM': 6, 'HCR': 7, 'SCR': 8}
            return (type_order.get(bill_type, 9), number)
        return (10, 0)
    
    bills.sort(key=sort_key)
    
    # Remove originalBillId from final output (internal use only)
    for bill in bills:
        if 'originalBillId' in bill:
            del bill['originalBillId']
    
    data = {
        "lastSync": datetime.now().isoformat(),
        "sessionYear": CURRENT_YEAR,
        "sessionStart": "2026-01-12",
        "sessionEnd": "2026-03-12",
        "totalBills": len(bills),
        "bills": bills,
        "metadata": {
            "source": "Washington State Legislature Web Services API",
            "apiVersion": "1.0",
            "updateFrequency": "hourly",
            "dataVersion": "5.0.0",
            "biennium": BIENNIUM,
            "billTypes": list(set(re.match(r'([A-Z]+)', b['number']).group(1) 
                               for b in bills if re.match(r'([A-Z]+)', b['number'])))
        }
    }
    
    # Ensure data directory exists
    ensure_data_dir()
    
    data_file = DATA_DIR / "bills.json"
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Saved {len(bills)} bills to {data_file}")
    return data

def create_sync_log(bills_count: int, new_count: int = 0, status: str = "success"):
    """Create sync log for monitoring"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "billsCount": bills_count,
        "newBillsAdded": new_count,
        "biennium": BIENNIUM,
        "nextSync": (datetime.now() + timedelta(hours=1)).isoformat()
    }
    
    log_file = DATA_DIR / "sync-log.json"
    
    # Load existing logs
    logs = []
    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
                data = json.load(f)
                logs = data.get('logs', [])
        except:
            logs = []
    
    # Add new log entry (keep last 100 entries)
    logs.insert(0, log_entry)
    logs = logs[:100]
    
    # Save logs
    with open(log_file, 'w') as f:
        json.dump({"logs": logs, "lastSuccessfulSync": datetime.now().isoformat()}, f, indent=2)
    
    print(f"📝 Sync log updated")

def create_stats_file(bills: List[Dict]):
    """Create statistics file"""
    stats = {
        "generated": datetime.now().isoformat(),
        "totalBills": len(bills),
        "byStatus": {},
        "byCommittee": {},
        "byPriority": {},
        "byTopic": {},
        "byType": {},
        "bySponsor": {},
        "billsWithHearings": 0
    }
    
    for bill in bills:
        # By status
        status = bill.get('status', 'Unknown')
        stats['byStatus'][status] = stats['byStatus'].get(status, 0) + 1
        
        # By committee
        committee = bill.get('committee', 'Unknown')
        stats['byCommittee'][committee] = stats['byCommittee'].get(committee, 0) + 1
        
        # By priority
        priority = bill.get('priority', 'medium')
        stats['byPriority'][priority] = stats['byPriority'].get(priority, 0) + 1
        
        # By topic
        topic = bill.get('topic', 'General Government')
        stats['byTopic'][topic] = stats['byTopic'].get(topic, 0) + 1
        
        # By type
        match = re.match(r'([A-Z]+)', bill['number'])
        if match:
            bill_type = match.group(1)
            stats['byType'][bill_type] = stats['byType'].get(bill_type, 0) + 1
        
        # By sponsor
        sponsor = bill.get('sponsor', 'Unknown')
        if sponsor != 'Unknown':
            stats['bySponsor'][sponsor] = stats['bySponsor'].get(sponsor, 0) + 1
        
        # Hearings
        if bill.get('hearings'):
            stats['billsWithHearings'] += 1
    
    stats_file = DATA_DIR / "stats.json"
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f"📊 Statistics file created")

def main():
    """Main execution function"""
    print(f"🚀 Washington State Legislature Bill Fetcher (SOAP API)")
    print(f"📅 Biennium: {BIENNIUM} | Year: {CURRENT_YEAR}")
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        # Fetch all bills from the biennium
        all_bills = {}
        
        # Method 1: Get all bills for biennium
        biennium_bills = fetch_all_legislation_by_biennium()
        for bill in biennium_bills:
            if bill and bill.get('title') and bill['title'] != 'No title available':
                all_bills[bill['id']] = bill
        
        # Method 2: Get recently active bills (if Method 1 returns few results)
        if len(all_bills) < 100:
            print("\nFetching additional active bills...")
            active_bills = fetch_active_legislation()
            for bill in active_bills:
                if bill and bill.get('title') and bill['title'] != 'No title available':
                    if bill['id'] not in all_bills:
                        all_bills[bill['id']] = bill
        
        # Convert to list
        bills_list = list(all_bills.values())
        
        # Fetch hearings if we have bills
        if bills_list:
            fetch_hearings_for_bills(bills_list)
        
        # Save data
        if bills_list:
            save_bills_data(bills_list)
            create_stats_file(bills_list)
            create_sync_log(len(bills_list), status="success")
            
            print("\n" + "=" * 60)
            print(f"✅ Successfully fetched {len(bills_list)} bills")
            print(f"📊 Bill types found: {', '.join(set(re.match(r'([A-Z]+)', b['number']).group(1) for b in bills_list if re.match(r'([A-Z]+)', b['number'])))}")
        else:
            print("\n⚠️  No bills retrieved from API")
            print("   The legislature may not have data available yet.")
            print("   Session starts: January 12, 2026")
            
            # Save empty structure
            save_bills_data([])
            create_stats_file([])
            create_sync_log(0, status="no_data")
        
        print(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"\n❌ Error during fetch: {e}")
        create_sync_log(0, status=f"error: {str(e)}")
        raise

if __name__ == "__main__":
    main()#!/usr/bin/env python3
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
from typing import Dict, List, Optional, Tuple
import re

# Configuration
BASE_API_URL = "https://wslwebservices.leg.wa.gov"
BASE_WEB_URL = "https://app.leg.wa.gov"
BIENNIUM = "2025-26"
YEAR = 2026
DATA_DIR = Path("data")

# API Endpoints
LEGISLATION_SERVICE = f"{BASE_API_URL}/LegislationService.asmx"
COMMITTEE_SERVICE = f"{BASE_API_URL}/CommitteeService.asmx"
COMMITTEE_MEETING_SERVICE = f"{BASE_API_URL}/CommitteeMeetingService.asmx"

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
        response = requests.post(url, data=soap_envelope, headers=headers, timeout=30)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            # Remove namespace prefixes for easier parsing
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}')[1]
            return root
        else:
            print(f"API Error {response.status_code}: {response.text[:200]}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None
    except ET.ParseError as e:
        print(f"XML parsing error: {e}")
        return None

def fetch_legislation_by_year() -> List[Dict]:
    """Fetch all legislation for the current year"""
    bills = []
    
    soap_body = f"""
    <GetLegislationByYear xmlns="http://WSLWebServices.leg.wa.gov/">
      <year>{YEAR}</year>
    </GetLegislationByYear>"""
    
    print(f"Fetching legislation for year {YEAR}...")
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislationByYear"
    )
    
    if root:
        # Parse the response
        for legislation in root.findall('.//LegislationInfo'):
            bill_data = parse_legislation_info(legislation)
            if bill_data:
                bills.append(bill_data)
        print(f"  Found {len(bills)} bills from API")
    
    return bills

def fetch_prefiled_legislation() -> List[Dict]:
    """Fetch prefiled legislation for the biennium"""
    bills = []
    
    soap_body = f"""
    <GetPrefiledLegislationInfo xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
    </GetPrefiledLegislationInfo>"""
    
    print(f"Fetching prefiled legislation for {BIENNIUM}...")
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetPrefiledLegislationInfo"
    )
    
    if root:
        for legislation in root.findall('.//LegislationInfo'):
            bill_data = parse_legislation_info(legislation)
            if bill_data:
                bills.append(bill_data)
        print(f"  Found {len(bills)} prefiled bills")
    
    return bills

def parse_legislation_info(elem: ET.Element) -> Optional[Dict]:
    """Parse LegislationInfo XML element into bill dict"""
    try:
        # Extract bill number
        bill_number = elem.findtext('BillNumber', '')
        if not bill_number:
            return None
        
        # Parse bill ID components
        biennium = elem.findtext('Biennium', BIENNIUM)
        bill_id = elem.findtext('BillId', '')
        
        # Create standardized bill number format
        if bill_id:
            # Extract type from BillId (e.g., HB, SB, HJR, etc.)
            match = re.match(r'([A-Z]+)\s*(\d+)', bill_id)
            if match:
                bill_type, number = match.groups()
                formatted_number = f"{bill_type} {number}"
            else:
                formatted_number = bill_id
        else:
            formatted_number = f"BILL {bill_number}"
        
        # Get status from CurrentStatus element
        status_elem = elem.find('CurrentStatus')
        if status_elem is not None:
            status = status_elem.findtext('Status', 'Introduced')
            status_date = status_elem.findtext('ActionDate', '')
            history_line = status_elem.findtext('HistoryLine', '')
        else:
            status = 'Introduced'
            status_date = ''
            history_line = ''
        
        # Extract committee from history or status
        committee = extract_committee_from_history(history_line, formatted_number)
        
        # Get sponsor information
        prime_sponsor_id = elem.findtext('PrimeSponsorID', '')
        sponsor = elem.findtext('PrimeSponsor', '')
        if not sponsor and elem.find('Sponsors'):
            sponsors = elem.findall('.//Sponsor')
            if sponsors:
                sponsor = sponsors[0].findtext('Name', 'Unknown')
        
        # Build bill data
        bill_data = {
            "id": formatted_number.replace(" ", ""),
            "number": formatted_number,
            "title": elem.findtext('ShortDescription', elem.findtext('LongDescription', 'No title available')),
            "sponsor": sponsor or "Unknown",
            "description": elem.findtext('LongDescription', ''),
            "status": status,
            "committee": committee,
            "priority": determine_priority(elem.findtext('ShortDescription', '')),
            "topic": determine_topic(elem.findtext('ShortDescription', '')),
            "introducedDate": elem.findtext('IntroducedDate', ''),
            "lastUpdated": status_date or datetime.now().isoformat(),
            "legUrl": f"{BASE_WEB_URL}/billsummary?BillNumber={number if 'number' in locals() else bill_number}&Year={YEAR}",
            "hearings": [],
            "historyLine": history_line,
            "biennium": biennium
        }
        
        # Add companions if present
        companions = elem.findall('.//Companion')
        if companions:
            bill_data['companions'] = [c.findtext('BillId', '') for c in companions]
        
        return bill_data
        
    except Exception as e:
        print(f"Error parsing legislation: {e}")
        return None

def fetch_bill_hearings(bill_id: str, biennium: str) -> List[Dict]:
    """Fetch hearings for a specific bill"""
    hearings = []
    
    soap_body = f"""
    <GetHearings xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{biennium}</biennium>
      <billNumber>{bill_id}</billNumber>
    </GetHearings>"""
    
    root = make_soap_request(
        COMMITTEE_MEETING_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetHearings"
    )
    
    if root:
        for hearing in root.findall('.//Hearing'):
            hearing_data = {
                "date": hearing.findtext('Date', ''),
                "time": hearing.findtext('Time', ''),
                "committee": hearing.findtext('CommitteeName', ''),
                "location": hearing.findtext('Building', '') + " " + hearing.findtext('Room', ''),
                "type": hearing.findtext('AgendaType', 'Public Hearing')
            }
            if hearing_data["date"]:
                hearings.append(hearing_data)
    
    return hearings

def extract_committee_from_history(history_line: str, bill_number: str) -> str:
    """Extract committee from history line"""
    if not history_line:
        return determine_default_committee(bill_number)
    
    # Common committee patterns in history
    committee_patterns = [
        r'(?:Referred to|First reading, referred to|Reintroduced and referred to)\s+([^.]+)',
        r'(?:In|By)\s+(?:committee on|Committee on)\s+([^.]+)',
        r'Executive action taken in the (?:House|Senate) Committee on\s+([^.]+)'
    ]
    
    for pattern in committee_patterns:
        match = re.search(pattern, history_line, re.IGNORECASE)
        if match:
            committee = match.group(1).strip()
            # Clean up committee name
            committee = committee.replace('&', '&')
            committee = re.sub(r'\s+', ' ', committee)
            return committee
    
    return determine_default_committee(bill_number)

def determine_default_committee(bill_number: str) -> str:
    """Determine default committee based on bill type"""
    if bill_number.startswith('HB') or bill_number.startswith('HJR'):
        return "House Rules"
    elif bill_number.startswith('SB') or bill_number.startswith('SJR'):
        return "Senate Rules"
    else:
        return "Rules"

def determine_topic(title: str) -> str:
    """Determine bill topic from title"""
    if not title:
        return "General Government"
    
    title_lower = title.lower()
    
    topic_keywords = {
        "Education": ["education", "school", "student", "teacher", "learning", "academic"],
        "Tax & Revenue": ["tax", "revenue", "budget", "fiscal", "finance", "appropriation"],
        "Housing": ["housing", "rent", "tenant", "landlord", "homelessness", "affordable"],
        "Healthcare": ["health", "medical", "hospital", "mental", "pharmacy", "insurance"],
        "Environment": ["environment", "climate", "energy", "pollution", "conservation", "sustainable"],
        "Transportation": ["transport", "road", "highway", "transit", "vehicle", "traffic"],
        "Public Safety": ["crime", "safety", "police", "justice", "corrections", "emergency"],
        "Business": ["business", "commerce", "trade", "economy", "corporation", "employment"],
        "Technology": ["technology", "internet", "data", "privacy", "cyber", "artificial intelligence"],
        "Agriculture": ["agriculture", "farm", "rural", "livestock", "crop", "agricultural"]
    }
    
    for topic, keywords in topic_keywords.items():
        if any(keyword in title_lower for keyword in keywords):
            return topic
    
    return "General Government"

def determine_priority(title: str) -> str:
    """Determine bill priority based on keywords in title"""
    if not title:
        return "medium"
    
    title_lower = title.lower()
    
    # High priority keywords
    high_priority = ["emergency", "budget", "appropriation", "supplemental", "capital",
                    "education funding", "public safety", "housing crisis", "climate",
                    "healthcare access", "tax relief", "essential"]
    
    # Low priority keywords  
    low_priority = ["technical", "clarifying", "housekeeping", "minor", "study",
                   "memorial", "recognizing", "designating", "honoring"]
    
    for keyword in high_priority:
        if keyword in title_lower:
            return "high"
    
    for keyword in low_priority:
        if keyword in title_lower:
            return "low"
    
    return "medium"

def fetch_all_bills() -> List[Dict]:
    """Fetch all bills from various API endpoints"""
    all_bills = {}
    
    # 1. Fetch current year legislation
    current_year_bills = fetch_legislation_by_year()
    for bill in current_year_bills:
        all_bills[bill['id']] = bill
    
    # 2. Fetch prefiled legislation
    prefiled_bills = fetch_prefiled_legislation()
    for bill in prefiled_bills:
        # Update or add prefiled bills
        if bill['id'] in all_bills:
            # Update status if prefiled is more recent
            all_bills[bill['id']].update(bill)
        else:
            all_bills[bill['id']] = bill
    
    # 3. Fetch introduced bills for current biennium
    introduced_bills = fetch_introduced_legislation()
    for bill in introduced_bills:
        if bill['id'] not in all_bills:
            all_bills[bill['id']] = bill
    
    # Convert to list
    bills_list = list(all_bills.values())
    
    # 4. Fetch hearings for each bill (with rate limiting)
    print("Fetching hearing information...")
    for i, bill in enumerate(bills_list):
        if i % 10 == 0 and i > 0:
            print(f"  Processed {i}/{len(bills_list)} bills...")
            time.sleep(1)  # Rate limiting
        
        hearings = fetch_bill_hearings(bill['number'], bill.get('biennium', BIENNIUM))
        if hearings:
            bill['hearings'] = hearings
    
    return bills_list

def fetch_introduced_legislation() -> List[Dict]:
    """Fetch all introduced legislation for the biennium"""
    bills = []
    
    soap_body = f"""
    <GetLegislationIntroducedSince xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
      <sinceDate>2025-01-01T00:00:00</sinceDate>
    </GetLegislationIntroducedSince>"""
    
    print(f"Fetching introduced legislation since 2025-01-01...")
    root = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislationIntroducedSince"
    )
    
    if root:
        for legislation in root.findall('.//LegislationInfo'):
            bill_data = parse_legislation_info(legislation)
            if bill_data:
                bills.append(bill_data)
        print(f"  Found {len(bills)} introduced bills")
    
    return bills

def save_bills_data(bills: List[Dict]) -> Dict:
    """Save bills data to JSON file"""
    # Sort bills by type and number
    def sort_key(bill):
        match = re.match(r'([A-Z]+)\s*(\d+)', bill['number'])
        if match:
            return (match.group(1), int(match.group(2)))
        return (bill['number'], 0)
    
    bills.sort(key=sort_key)
    
    # Calculate session dates
    session_start = "2026-01-12"
    session_end = "2026-03-12"
    
    data = {
        "lastSync": datetime.now().isoformat(),
        "sessionYear": YEAR,
        "sessionStart": session_start,
        "sessionEnd": session_end,
        "totalBills": len(bills),
        "bills": bills,
        "metadata": {
            "source": "Washington State Legislature Web Services API",
            "apiVersion": "1.0",
            "updateFrequency": "hourly",
            "dataVersion": "3.0.0",
            "biennium": BIENNIUM,
            "billTypes": list(set(re.match(r'([A-Z]+)', b['number']).group(1) 
                               for b in bills if re.match(r'([A-Z]+)', b['number'])))
        }
    }
    
    # Ensure data directory exists
    ensure_data_dir()
    
    data_file = DATA_DIR / "bills.json"
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved {len(bills)} bills to {data_file}")
    return data

def create_sync_log(bills_count: int, new_count: int = 0, updated_count: int = 0, status: str = "success"):
    """Create sync log for monitoring"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "billsCount": bills_count,
        "newBillsAdded": new_count,
        "billsUpdated": updated_count,
        "apiCalls": 4,  # Tracks number of API endpoints called
        "nextSync": (datetime.now() + timedelta(hours=1)).isoformat()
    }
    
    log_file = DATA_DIR / "sync-log.json"
    
    # Load existing logs
    logs = []
    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
                data = json.load(f)
                logs = data.get('logs', [])
        except:
            logs = []
    
    # Add new log entry (keep last 100 entries)
    logs.insert(0, log_entry)
    logs = logs[:100]
    
    # Save logs
    with open(log_file, 'w') as f:
        json.dump({"logs": logs, "lastSuccessfulSync": datetime.now().isoformat()}, f, indent=2)
    
    print(f"📝 Sync log updated: {status} - {bills_count} bills, {new_count} new, {updated_count} updated")

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
        "billsWithHearings": 0,
        "prefiledBills": 0,
        "introducedBills": 0,
        "passedHouse": 0,
        "passedSenate": 0,
        "signedIntoLaw": 0
    }
    
    # Calculate statistics
    today = datetime.now().date()
    week_from_now = today + timedelta(days=7)
    
    for bill in bills:
        # By status
        status = bill.get('status', 'Unknown')
        stats['byStatus'][status] = stats['byStatus'].get(status, 0) + 1
        
        # Track progress
        if 'prefiled' in status.lower():
            stats['prefiledBills'] += 1
        elif 'introduced' in status.lower():
            stats['introducedBills'] += 1
        elif 'passed house' in status.lower():
            stats['passedHouse'] += 1
        elif 'passed senate' in status.lower():
            stats['passedSenate'] += 1
        elif 'signed' in status.lower() or 'enacted' in status.lower():
            stats['signedIntoLaw'] += 1
        
        # By committee
        committee = bill.get('committee', 'Unknown')
        if committee:
            stats['byCommittee'][committee] = stats['byCommittee'].get(committee, 0) + 1
        
        # By priority
        priority = bill.get('priority', 'medium')
        stats['byPriority'][priority] = stats['byPriority'].get(priority, 0) + 1
        
        # By topic
        topic = bill.get('topic', 'General Government')
        stats['byTopic'][topic] = stats['byTopic'].get(topic, 0) + 1
        
        # By sponsor
        sponsor = bill.get('sponsor', 'Unknown')
        if sponsor and sponsor != 'Unknown':
            stats['bySponsor'][sponsor] = stats['bySponsor'].get(sponsor, 0) + 1
        
        # By type (HB, SB, etc.)
        match = re.match(r'([A-Z]+)', bill['number'])
        if match:
            bill_type = match.group(1)
            stats['byType'][bill_type] = stats['byType'].get(bill_type, 0) + 1
        
        # Recently updated
        try:
            if bill.get('lastUpdated'):
                last_updated = datetime.fromisoformat(bill['lastUpdated'].replace('Z', '+00:00'))
                days_diff = (datetime.now() - last_updated).days
                
                if days_diff <= 7:
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
                    if hearing.get('date'):
                        hearing_date = datetime.fromisoformat(hearing['date'].replace('Z', '+00:00'))
                        if today <= hearing_date.date() <= week_from_now:
                            stats['upcomingHearings'] += 1
                except:
                    pass
    
    # Sort sponsors by count (top 20)
    if stats['bySponsor']:
        stats['topSponsors'] = sorted(
            stats['bySponsor'].items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:20]
    
    # Sort committees by activity
    if stats['byCommittee']:
        stats['mostActiveCommittees'] = sorted(
            stats['byCommittee'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
    
    stats_file = DATA_DIR / "stats.json"
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f"📊 Statistics file created with detailed breakdown")

def load_existing_data() -> Optional[Dict]:
    """Load existing bills data if it exists"""
    data_file = DATA_DIR / "bills.json"
    if data_file.exists():
        try:
            with open(data_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading existing data: {e}")
            return None
    return None

def main():
    """Main execution function"""
    print(f"🚀 Washington State Legislature Bill Fetcher")
    print(f"📅 Session: {BIENNIUM} | Year: {YEAR}")
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        # Load existing data for comparison
        existing_data = load_existing_data()
        existing_bills = {}
        if existing_data:
            existing_bills = {bill['id']: bill for bill in existing_data.get('bills', [])}
            print(f"📚 Loaded {len(existing_bills)} existing bills from cache")
        
        # Fetch all bills from API
        print("\n🔄 Fetching data from WA Legislature API...")
        all_bills = fetch_all_bills()
        
        if not all_bills:
            print("⚠️  No bills retrieved from API. The legislature may not have data available yet.")
            print("    The session starts on January 12, 2026.")
            # Create empty data file
            save_bills_data([])
            create_stats_file([])
            create_sync_log(0, 0, 0, "no_data")
            return
        
        # Track changes
        new_bills = []
        updated_bills = []
        
        for bill in all_bills:
            if bill['id'] not in existing_bills:
                new_bills.append(bill)
            elif bill != existing_bills[bill['id']]:
                updated_bills.append(bill)
        
        # Save data
        save_bills_data(all_bills)
        create_stats_file(all_bills)
        create_sync_log(len(all_bills), len(new_bills), len(updated_bills), "success")
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"✅ Sync completed successfully!")
        print(f"   📊 Total bills: {len(all_bills)}")
        print(f"   ✨ New bills: {len(new_bills)}")
        print(f"   🔄 Updated bills: {len(updated_bills)}")
        print(f"   📁 Data saved to: {DATA_DIR}/bills.json")
        print(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"\n❌ Error during fetch: {e}")
        create_sync_log(0, 0, 0, f"error: {str(e)}")
        raise

if __name__ == "__main__":
    main()

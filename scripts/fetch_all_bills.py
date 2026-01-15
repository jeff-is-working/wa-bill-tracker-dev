#!/usr/bin/env python3
"""
Washington State Legislature Bill Fetcher with Debug Support
Fetches bills from the official WA Legislature Web Services API
Saves raw responses for debugging in sync folder
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
import sys

# Configuration
BASE_API_URL = "https://wslwebservices.leg.wa.gov"
BASE_WEB_URL = "https://app.leg.wa.gov"
BIENNIUM = "2025-26"
CURRENT_YEAR = 2026
DATA_DIR = Path("data")
SYNC_DIR = DATA_DIR / "sync"
DEBUG_MODE = True  # Set to True to save raw API responses

# SOAP Service Endpoints
LEGISLATION_SERVICE = f"{BASE_API_URL}/LegislationService.asmx"
COMMITTEE_SERVICE = f"{BASE_API_URL}/CommitteeService.asmx"

def ensure_directories():
    """Ensure data and sync directories exist"""
    DATA_DIR.mkdir(exist_ok=True)
    SYNC_DIR.mkdir(exist_ok=True)
    print(f"Data directory: {DATA_DIR.absolute()}")
    print(f"Sync directory: {SYNC_DIR.absolute()}")

def save_raw_response(filename: str, content: str):
    """Save raw API response to sync folder for debugging"""
    if DEBUG_MODE:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = SYNC_DIR / f"{timestamp}_{filename}"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Saved raw response to: {filepath}")
        return filepath
    return None

def make_soap_request(url: str, soap_body: str, soap_action: str, operation_name: str) -> Tuple[Optional[ET.Element], Optional[str]]:
    """Make SOAP request to WA Legislature API and return parsed XML and raw response"""
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
    
    print(f"Making SOAP request to: {url}")
    print(f"Operation: {operation_name}")
    
    # Save request for debugging
    save_raw_response(f"{operation_name}_request.xml", soap_envelope)
    
    try:
        response = requests.post(url, data=soap_envelope, headers=headers, timeout=60)
        print(f"Response status code: {response.status_code}")
        
        # Save raw response
        response_file = save_raw_response(f"{operation_name}_response.xml", response.text)
        
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.content)
                return root, response.text
            except ET.ParseError as e:
                print(f"XML parsing error: {e}")
                print(f"Response preview: {response.text[:500]}")
                return None, response.text
        else:
            print(f"API Error {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return None, response.text
            
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None, None

def parse_bills_from_response(root: ET.Element, raw_response: str) -> List[Dict]:
    """Parse bills from SOAP response with multiple parsing strategies"""
    bills = []
    
    # Define multiple namespace variations to try
    namespace_sets = [
        # Standard SOAP namespaces
        {'soap': 'http://schemas.xmlsoap.org/soap/envelope/', 'wsl': 'http://WSLWebServices.leg.wa.gov/'},
        # Without WSL namespace
        {'soap': 'http://schemas.xmlsoap.org/soap/envelope/'},
        # Empty namespace
        {}
    ]
    
    # Try different XPath patterns
    xpath_patterns = [
        './/wsl:LegislationInfo',
        './/LegislationInfo',
        './/wsl:ArrayOfLegislationInfo/wsl:LegislationInfo',
        './/ArrayOfLegislationInfo/LegislationInfo',
        './/{http://WSLWebServices.leg.wa.gov/}LegislationInfo',
        './/GetLegislationByYearResult//LegislationInfo',
        './/GetPrefiledLegislationInfoResult//LegislationInfo',
        './/soap:Body//LegislationInfo',
        './/soap:Body/*/LegislationInfo',
        './/soap:Body/*/*/LegislationInfo'
    ]
    
    # Try each combination
    for namespaces in namespace_sets:
        for pattern in xpath_patterns:
            try:
                if namespaces:
                    elements = root.findall(pattern, namespaces)
                else:
                    elements = root.findall(pattern)
                
                if elements:
                    print(f"  Found {len(elements)} elements with pattern: {pattern}")
                    for elem in elements:
                        bill_data = parse_legislation_element(elem)
                        if bill_data:
                            bills.append(bill_data)
                    
                    if bills:
                        return bills
            except Exception as e:
                continue
    
    # If no bills found with XPath, try parsing raw response as fallback
    if not bills and raw_response:
        print("  Attempting raw XML parsing...")
        bills = parse_bills_from_raw_xml(raw_response)
    
    return bills

def parse_bills_from_raw_xml(raw_xml: str) -> List[Dict]:
    """Parse bills directly from raw XML string"""
    bills = []
    
    # Find all LegislationInfo blocks using regex
    pattern = r'<LegislationInfo[^>]*>(.*?)</LegislationInfo>'
    matches = re.findall(pattern, raw_xml, re.DOTALL)
    
    print(f"  Found {len(matches)} LegislationInfo blocks in raw XML")
    
    for match in matches:
        try:
            # Reconstruct the XML element
            elem_str = f'<LegislationInfo>{match}</LegislationInfo>'
            elem = ET.fromstring(elem_str)
            bill_data = parse_legislation_element(elem)
            if bill_data:
                bills.append(bill_data)
        except Exception as e:
            continue
    
    return bills

def parse_legislation_element(elem: ET.Element) -> Optional[Dict]:
    """Parse a LegislationInfo XML element into bill dictionary"""
    try:
        # Helper to get text from child element
        def get_text(element: ET.Element, tag: str, default: str = "") -> str:
            child = element.find(tag)
            if child is None:
                # Try with namespace
                child = element.find(f'{{{element.tag.split("}")[0][1:] if "}" in element.tag else ""}}}{tag}')
            if child is None:
                # Try searching deeper
                child = element.find(f'.//{tag}')
            return child.text if child is not None and child.text else default
        
        # Extract essential fields
        biennium = get_text(elem, "Biennium", BIENNIUM)
        bill_id = get_text(elem, "BillId")
        bill_number = get_text(elem, "BillNumber")
        
        # Skip if no bill number
        if not bill_number:
            return None
        
        # Get description fields
        short_description = get_text(elem, "ShortDescription")
        long_description = get_text(elem, "LongDescription")
        abbreviated_title = get_text(elem, "AbbreviatedTitle")
        
        # Use any available title
        title = short_description or abbreviated_title or long_description or "No title available"
        
        # Get version information
        substitute_version = get_text(elem, "SubstituteVersion")
        engrossed_version = get_text(elem, "EngrossedVersion")
        
        # Get agency/chamber info
        original_agency = get_text(elem, "OriginalAgency", "").upper()
        current_agency = get_text(elem, "CurrentAgency", "").upper()
        
        # Determine bill prefix
        if "HOUSE" in original_agency or "HOUSE" in current_agency:
            prefix = "HB"
        elif "SENATE" in original_agency or "SENATE" in current_agency:
            prefix = "SB"
        else:
            # Try to infer from bill number
            try:
                num = int(bill_number)
                if num >= 5000:
                    prefix = "SB"
                elif num >= 4000:
                    # Could be HJR, SJR, etc.
                    prefix = "HJR" if num < 4100 else "HJM" if num < 4400 else "HCR"
                else:
                    prefix = "HB"
            except:
                prefix = ""
        
        # Build full bill number
        version_prefix = ""
        if substitute_version:
            version_prefix = substitute_version
        elif engrossed_version:
            version_prefix = engrossed_version
        
        full_bill_number = f"{version_prefix}{prefix} {bill_number}".strip()
        
        # Get sponsor information
        prime_sponsor = get_text(elem, "PrimeSponsor")
        prime_sponsor_id = get_text(elem, "PrimeSponsorID")
        request_exec = get_text(elem, "RequestExec")
        companions = get_text(elem, "Companions")
        
        # Determine sponsor
        if prime_sponsor:
            sponsor = prime_sponsor
        elif request_exec:
            sponsor = request_exec
        else:
            sponsor = "Unknown"
        
        # Get status information
        current_status = get_text(elem, "CurrentStatus")
        history_line = get_text(elem, "HistoryLine")
        
        # Parse status
        status = "prefiled"  # default
        if current_status:
            status_lower = current_status.lower()
            if "introduced" in status_lower:
                status = "introduced"
            elif "committee" in status_lower:
                status = "committee"
            elif "passed" in status_lower:
                status = "passed"
            elif "failed" in status_lower or "dead" in status_lower:
                status = "failed"
            elif "governor" in status_lower:
                status = "governor"
            elif "signed" in status_lower or "law" in status_lower:
                status = "enacted"
        
        # Get dates
        introduced_date = get_text(elem, "IntroducedDate")
        action_date = get_text(elem, "ActionDate")
        
        # Parse dates
        if introduced_date:
            try:
                # Handle various date formats
                if 'T' in introduced_date:
                    introduced_date = introduced_date.split('T')[0]
                elif '/' in introduced_date:
                    # Convert MM/DD/YYYY to YYYY-MM-DD
                    parts = introduced_date.split('/')
                    if len(parts) == 3:
                        introduced_date = f"{parts[2]}-{parts[0]:0>2}-{parts[1]:0>2}"
            except:
                introduced_date = "2026-01-12"
        else:
            introduced_date = "2026-01-12"
        
        # Create bill dictionary
        bill = {
            "id": bill_id or full_bill_number.replace(" ", ""),
            "number": full_bill_number,
            "billNumber": bill_number,
            "title": title,
            "sponsor": sponsor,
            "description": long_description if long_description else f"A bill relating to {title.lower()}",
            "status": status,
            "historyLine": history_line,
            "committee": determine_committee(full_bill_number, title),
            "priority": determine_priority(title),
            "topic": determine_topic(title),
            "introducedDate": introduced_date,
            "lastUpdated": datetime.now().isoformat(),
            "legUrl": f"{BASE_WEB_URL}/billsummary?BillNumber={bill_number}&Year={CURRENT_YEAR}",
            "biennium": biennium,
            "companions": companions,
            "hearings": []
        }
        
        return bill
        
    except Exception as e:
        print(f"    Error parsing element: {e}")
        return None

def fetch_legislation_by_year() -> List[Dict]:
    """Fetch all legislation for the current year"""
    print(f"\nFetching legislation for year {CURRENT_YEAR}...")
    
    soap_body = f"""
    <GetLegislationByYear xmlns="http://WSLWebServices.leg.wa.gov/">
      <year>{CURRENT_YEAR}</year>
    </GetLegislationByYear>"""
    
    root, raw_response = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislationByYear",
        "GetLegislationByYear"
    )
    
    if root is None:
        print("  Failed to get valid response")
        return []
    
    bills = parse_bills_from_response(root, raw_response)
    print(f"  Parsed {len(bills)} bills from response")
    
    # Show sample bills if found
    if bills:
        print("  Sample bills found:")
        for bill in bills[:3]:
            print(f"    - {bill['number']}: {bill['title']}")
    
    return bills

def fetch_prefiled_legislation() -> List[Dict]:
    """Fetch prefiled legislation for the biennium"""
    print(f"\nFetching prefiled legislation for biennium {BIENNIUM}...")
    
    soap_body = f"""
    <GetPrefiledLegislationInfo xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
    </GetPrefiledLegislationInfo>"""
    
    root, raw_response = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetPrefiledLegislationInfo",
        "GetPrefiledLegislationInfo"
    )
    
    if root is None:
        print("  Failed to get valid response")
        return []
    
    bills = parse_bills_from_response(root, raw_response)
    print(f"  Parsed {len(bills)} bills from response")
    
    # Show sample bills if found
    if bills:
        print("  Sample bills found:")
        for bill in bills[:3]:
            print(f"    - {bill['number']}: {bill['title']}")
    
    return bills

def fetch_legislation_info_by_biennium() -> List[Dict]:
    """Fetch all legislation info for the biennium"""
    print(f"\nFetching all legislation for biennium {BIENNIUM}...")
    
    soap_body = f"""
    <GetLegislationInfoByBiennium xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
    </GetLegislationInfoByBiennium>"""
    
    root, raw_response = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislationInfoByBiennium",
        "GetLegislationInfoByBiennium"
    )
    
    if root is None:
        print("  Failed to get valid response")
        return []
    
    bills = parse_bills_from_response(root, raw_response)
    print(f"  Parsed {len(bills)} bills from response")
    
    # Show sample bills if found
    if bills:
        print("  Sample bills found:")
        for bill in bills[:3]:
            print(f"    - {bill['number']}: {bill['title']}")
    
    return bills

def fetch_legislative_status_changes() -> List[Dict]:
    """Fetch bills with recent status changes"""
    print("\nFetching legislative status changes...")
    
    # Get bills changed in last 30 days
    begin_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")
    
    soap_body = f"""
    <GetLegislativeStatusChangesByDateRange xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
      <beginDate>{begin_date}</beginDate>
      <endDate>{end_date}</endDate>
    </GetLegislativeStatusChangesByDateRange>"""
    
    root, raw_response = make_soap_request(
        LEGISLATION_SERVICE,
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislativeStatusChangesByDateRange",
        "GetLegislativeStatusChangesByDateRange"
    )
    
    if root is None:
        print("  Failed to get valid response")
        return []
    
    bills = parse_bills_from_response(root, raw_response)
    print(f"  Parsed {len(bills)} bills from response")
    
    return bills

def determine_committee(bill_number: str, title: str) -> str:
    """Determine committee assignment based on bill number and title"""
    title_lower = title.lower()
    
    committees = {
        "Education": ["education", "school", "student", "teacher", "learning"],
        "Transportation": ["transportation", "road", "highway", "transit", "vehicle"],
        "Housing": ["housing", "rent", "tenant", "landlord", "homeless"],
        "Health & Long-Term Care": ["health", "medical", "hospital", "mental", "behavioral"],
        "Environment & Energy": ["environment", "climate", "energy", "pollution", "conservation"],
        "Finance": ["tax", "revenue", "budget", "fiscal", "appropriation"],
        "Ways & Means": ["budget", "fiscal", "appropriation", "revenue"],
        "Consumer Protection & Business": ["consumer", "business", "commerce", "corporation"],
        "Law & Justice": ["crime", "criminal", "justice", "court", "legal"],
        "Labor & Commerce": ["labor", "employment", "worker", "wage", "workplace"],
        "State Government & Tribal Relations": ["state", "government", "tribal", "agency"]
    }
    
    for committee, keywords in committees.items():
        if any(keyword in title_lower for keyword in keywords):
            # Finance vs Ways & Means depends on chamber
            if committee == "Finance" and bill_number.startswith("SB"):
                return "Ways & Means"
            elif committee == "Ways & Means" and bill_number.startswith("HB"):
                return "Finance"
            return committee
    
    return "Rules" if bill_number.startswith("HCR") or bill_number.startswith("SCR") else "State Government & Tribal Relations"

def determine_topic(title: str) -> str:
    """Determine bill topic from title"""
    title_lower = title.lower()
    
    topics = {
        "Education": ["education", "school", "student", "teacher", "learning", "academic"],
        "Tax & Revenue": ["tax", "revenue", "budget", "fiscal", "fee", "appropriation"],
        "Housing": ["housing", "rent", "tenant", "landlord", "affordable", "homeless"],
        "Healthcare": ["health", "medical", "hospital", "mental", "behavioral", "insurance"],
        "Environment": ["environment", "climate", "energy", "pollution", "conservation", "water"],
        "Transportation": ["transport", "road", "highway", "transit", "traffic", "vehicle"],
        "Public Safety": ["crime", "safety", "police", "justice", "criminal", "enforcement"],
        "Business": ["business", "commerce", "trade", "economy", "corporation", "industry"],
        "Technology": ["technology", "internet", "data", "privacy", "cyber", "artificial"],
        "Labor": ["labor", "employment", "worker", "wage", "union", "workplace"],
        "Agriculture": ["agriculture", "farm", "food", "rural", "agricultural"]
    }
    
    for topic, keywords in topics.items():
        if any(keyword in title_lower for keyword in keywords):
            return topic
    
    return "General Government"

def determine_priority(title: str) -> str:
    """Determine bill priority based on keywords in title"""
    title_lower = title.lower()
    
    high_priority = ["emergency", "urgent", "crisis", "immediate", "critical", "budget", "appropriations"]
    low_priority = ["technical", "clarifying", "housekeeping", "minor", "study", "memorial"]
    
    for keyword in high_priority:
        if keyword in title_lower:
            return "high"
    
    for keyword in low_priority:
        if keyword in title_lower:
            return "low"
    
    return "medium"

def test_api_connection() -> bool:
    """Test basic API connectivity"""
    print("\n" + "=" * 60)
    print("TESTING API CONNECTION")
    print("=" * 60)
    
    try:
        # Simple test request
        response = requests.get(f"{BASE_API_URL}/LegislationService.asmx", timeout=10)
        if response.status_code == 200:
            print("SUCCESS: API endpoint is reachable")
            return True
        else:
            print(f"WARNING: API returned status code {response.status_code}")
            return False
    except Exception as e:
        print(f"ERROR: Cannot reach API - {e}")
        return False

def save_bills_data(bills: List[Dict]) -> Dict:
    """Save bills data to JSON file"""
    # Remove duplicates
    unique_bills = {}
    for bill in bills:
        bill_id = bill.get('id')
        if bill_id and bill_id not in unique_bills:
            unique_bills[bill_id] = bill
    
    bills = list(unique_bills.values())
    
    # Sort bills
    def sort_key(bill):
        number = bill.get('number', '')
        parts = number.split()
        if len(parts) >= 2:
            bill_type = re.sub(r'[0-9]', '', parts[0])
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
            "dataVersion": "3.1.0"
        }
    }
    
    # Save to main data file
    data_file = DATA_DIR / "bills.json"
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(bills)} bills to {data_file}")
    
    # Also save timestamped copy in sync folder
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sync_file = SYNC_DIR / f"bills_{timestamp}.json"
    with open(sync_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Backup saved to {sync_file}")
    
    return data

def validate_bills(bills: List[Dict]) -> Tuple[bool, List[str]]:
    """Validate bill data and return status with any issues"""
    issues = []
    
    if not bills:
        issues.append("No bills retrieved")
        return False, issues
    
    # Check for required fields
    required_fields = ['id', 'number', 'title']
    sample_bill = bills[0] if bills else {}
    
    for field in required_fields:
        if field not in sample_bill:
            issues.append(f"Missing required field: {field}")
    
    # Check for valid data
    bills_with_titles = [b for b in bills if b.get('title') and b['title'] != 'No title available']
    if len(bills_with_titles) == 0:
        issues.append("No bills have valid titles")
    
    # Check bill number format
    valid_bills = [b for b in bills if re.match(r'^[A-Z]+\s+\d+', b.get('number', ''))]
    if len(valid_bills) < len(bills) * 0.5:
        issues.append(f"Less than 50% of bills have valid number format")
    
    return len(issues) == 0, issues

def main():
    """Main execution function"""
    print(f"Washington State Legislature Bill Fetcher")
    print(f"Started at: {datetime.now()}")
    print("=" * 60)
    
    # Ensure directories exist
    ensure_directories()
    
    # Test API connection
    if not test_api_connection():
        print("\nWARNING: API connection test failed, but continuing...")
    
    # Track all bills
    all_bills = {}
    
    # Try multiple methods to get bills
    methods = [
        ("By Year", fetch_legislation_by_year),
        ("Prefiled", fetch_prefiled_legislation),
        ("By Biennium", fetch_legislation_info_by_biennium),
        ("Status Changes", fetch_legislative_status_changes)
    ]
    
    for method_name, method_func in methods:
        print(f"\n{'=' * 60}")
        print(f"Method: {method_name}")
        print('=' * 60)
        
        try:
            bills = method_func()
            new_count = 0
            for bill in bills:
                if bill['id'] not in all_bills:
                    all_bills[bill['id']] = bill
                    new_count += 1
            
            print(f"  Result: {len(bills)} bills found, {new_count} new unique bills")
            
        except Exception as e:
            print(f"  ERROR in {method_name}: {e}")
            continue
    
    # Convert to list
    final_bills = list(all_bills.values())
    
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Total unique bills collected: {len(final_bills)}")
    
    # Validate bills
    is_valid, issues = validate_bills(final_bills)
    
    if is_valid:
        print("Data validation: PASSED")
    else:
        print("Data validation: FAILED")
        for issue in issues:
            print(f"  - {issue}")
    
    # Save even if validation fails (for debugging)
    if final_bills:
        save_bills_data(final_bills)
        
        # Show sample of bills
        print("\nSample of bills retrieved:")
        for bill in final_bills[:10]:
            print(f"  {bill['number']}: {bill['title'][:60]}...")
    else:
        print("\nERROR: No bills were retrieved from any method")
        print("Check the sync folder for raw API responses to debug")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print(f"Completed at: {datetime.now()}")
    
    # Exit with appropriate code
    if not is_valid or len(final_bills) == 0:
        sys.exit(1)
    
    return len(final_bills)

if __name__ == "__main__":
    bill_count = main()
    print(f"\nFinal bill count: {bill_count}")

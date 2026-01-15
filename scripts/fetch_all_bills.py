#!/usr/bin/env python3
"""
Washington State Legislature Bill Fetcher - Fixed for proper SOAP handling
Fetches bills from the official WA Legislature Web Services API
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
DEBUG_MODE = True

# SOAP Service Endpoints
LEGISLATION_SERVICE = f"{BASE_API_URL}/LegislationService.asmx"

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

def make_soap_request(operation: str, parameters: Dict[str, str]) -> Tuple[Optional[ET.Element], Optional[str]]:
    """Make SOAP request with proper formatting"""
    
    # Build SOAP body based on operation
    param_xml = ""
    for key, value in parameters.items():
        param_xml += f"      <{key}>{value}</{key}>\n"
    
    soap_envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
               xmlns:xsd="http://www.w3.org/2001/XMLSchema" 
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <{operation} xmlns="http://WSLWebServices.leg.wa.gov/">
{param_xml}    </{operation}>
  </soap:Body>
</soap:Envelope>"""
    
    # Proper SOAPAction header format (with quotes)
    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': f'"http://WSLWebServices.leg.wa.gov/{operation}"'  # Note the quotes!
    }
    
    print(f"Making SOAP request: {operation}")
    print(f"Parameters: {parameters}")
    
    # Save request for debugging
    save_raw_response(f"{operation}_request.xml", soap_envelope)
    
    try:
        response = requests.post(LEGISLATION_SERVICE, data=soap_envelope, headers=headers, timeout=60)
        print(f"Response status code: {response.status_code}")
        
        # Save raw response
        save_raw_response(f"{operation}_response.xml", response.text)
        
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.content)
                # Check for SOAP fault
                fault = root.find('.//{http://schemas.xmlsoap.org/soap/envelope/}Fault')
                if fault:
                    faultstring = fault.find('.//faultstring')
                    if faultstring is not None:
                        print(f"SOAP Fault: {faultstring.text}")
                    return None, response.text
                
                return root, response.text
            except ET.ParseError as e:
                print(f"XML parsing error: {e}")
                return None, response.text
        else:
            print(f"HTTP Error {response.status_code}")
            if response.status_code == 500:
                # Parse SOAP fault
                try:
                    root = ET.fromstring(response.content)
                    faultstring = root.find('.//faultstring')
                    if faultstring is not None:
                        print(f"SOAP Fault: {faultstring.text}")
                except:
                    pass
            return None, response.text
            
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None, None

def extract_bill_info(elem: ET.Element) -> Optional[Dict]:
    """Extract bill information from XML element"""
    
    def get_text(tag: str, default: str = "") -> str:
        """Get text from child element, handling namespaces"""
        # Try without namespace
        child = elem.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        
        # Try with various namespace patterns
        for ns_prefix in ['', './/']:
            child = elem.find(f'{ns_prefix}{tag}')
            if child is not None and child.text:
                return child.text.strip()
        
        # Try ignoring namespace
        for child in elem:
            if child.tag.endswith(tag) and child.text:
                return child.text.strip()
        
        return default
    
    # Extract core fields
    biennium = get_text("Biennium", BIENNIUM)
    bill_id = get_text("BillId")
    bill_number = get_text("BillNumber")
    substitute_version = get_text("SubstituteVersion", "")
    engrossed_version = get_text("EngrossedVersion", "")
    
    # Skip if no bill number
    if not bill_number:
        return None
    
    # Get title/description
    short_description = get_text("ShortDescription", "")
    long_description = get_text("LongDescription", "")
    abbreviated_title = get_text("AbbreviatedTitle", "")
    request_title = get_text("RequestTitle", "")
    
    # Use the first available title
    title = short_description or abbreviated_title or request_title or long_description
    if not title or title == "":
        title = "No title available"
    
    # Determine bill type and format number
    original_agency = get_text("OriginalAgency", "").upper()
    current_agency = get_text("CurrentAgency", "").upper()
    
    # Determine prefix based on agency or bill number range
    try:
        num = int(bill_number) if bill_number.isdigit() else 0
        
        # House bills
        if "HOUSE" in original_agency or "HOUSE" in current_agency or (1000 <= num < 4000):
            prefix = "HB"
        # Senate bills  
        elif "SENATE" in original_agency or "SENATE" in current_agency or (5000 <= num < 8000):
            prefix = "SB"
        # House Joint Resolutions
        elif 4000 <= num < 4200:
            prefix = "HJR"
        # House Joint Memorials
        elif 4200 <= num < 4400:
            prefix = "HJM"
        # House Concurrent Resolutions
        elif 4400 <= num < 4500:
            prefix = "HCR"
        # Senate Joint Resolutions
        elif 8000 <= num < 8200:
            prefix = "SJR"
        # Senate Joint Memorials
        elif 8200 <= num < 8400:
            prefix = "SJM"
        # Senate Concurrent Resolutions
        elif 8400 <= num < 8500:
            prefix = "SCR"
        else:
            # Default based on first digit
            if num >= 5000:
                prefix = "SB"
            else:
                prefix = "HB"
    except:
        # If we can't determine, default to HB
        prefix = "HB"
    
    # Build full bill number with version prefix if available
    version_prefix = ""
    if substitute_version and substitute_version != "0":
        version_prefix = substitute_version
    elif engrossed_version and engrossed_version != "0":
        version_prefix = engrossed_version
    
    full_bill_number = f"{version_prefix}{prefix} {bill_number}".strip()
    
    # Get sponsor info
    prime_sponsor = get_text("PrimeSponsor", "")
    sponsor_name = get_text("SponsorName", "")
    request_exec = get_text("RequestExec", "")
    
    sponsor = prime_sponsor or sponsor_name or request_exec or "Unknown"
    
    # Get status
    current_status = get_text("CurrentStatus", "")
    history_line = get_text("HistoryLine", "")
    action_date = get_text("ActionDate", "")
    
    # Parse status to simple value
    status = "prefiled"
    if current_status:
        status_lower = current_status.lower()
        if "introduced" in status_lower or "first reading" in status_lower:
            status = "introduced"
        elif "committee" in status_lower:
            status = "committee"
        elif "rules" in status_lower:
            status = "rules"
        elif "passed" in status_lower:
            if "house" in status_lower and "senate" in status_lower:
                status = "passed"
            elif "house" in status_lower:
                status = "passed house"
            elif "senate" in status_lower:
                status = "passed senate"
            else:
                status = "passed"
        elif "governor" in status_lower:
            status = "governor"
        elif "veto" in status_lower:
            status = "vetoed"
        elif "signed" in status_lower or "chapter" in status_lower or "session law" in status_lower:
            status = "enacted"
        elif "failed" in status_lower or "dead" in status_lower:
            status = "failed"
    
    # Get dates
    introduced_date = get_text("IntroducedDate", "")
    if introduced_date:
        try:
            # Parse various date formats
            if 'T' in introduced_date:
                introduced_date = introduced_date.split('T')[0]
            elif '/' in introduced_date:
                parts = introduced_date.split('/')
                if len(parts) == 3:
                    month, day, year = parts
                    if len(year) == 2:
                        year = "20" + year
                    introduced_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        except:
            pass
    
    if not introduced_date or introduced_date == "":
        introduced_date = "2026-01-12"
    
    # Get committee info
    committee = get_text("Committee", "")
    if not committee:
        committee = determine_committee(full_bill_number, title)
    
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
        "committee": committee,
        "priority": determine_priority(title),
        "topic": determine_topic(title),
        "introducedDate": introduced_date,
        "actionDate": action_date,
        "lastUpdated": datetime.now().isoformat(),
        "legUrl": f"{BASE_WEB_URL}/billsummary?BillNumber={bill_number}&Year={CURRENT_YEAR}",
        "biennium": biennium,
        "hearings": []
    }
    
    return bill

def parse_legislation_response(root: ET.Element, raw_response: str) -> List[Dict]:
    """Parse legislation from SOAP response"""
    bills = []
    
    # Method 1: Try parsing with ElementTree
    # Look for LegislationInfo elements with various namespace patterns
    patterns = [
        './/{http://WSLWebServices.leg.wa.gov/}LegislationInfo',
        './/LegislationInfo',
        './/*[local-name()="LegislationInfo"]',
        './/ArrayOfLegislationInfo/LegislationInfo',
        './/GetLegislationByYearResult//LegislationInfo',
        './/soap:Body//LegislationInfo'
    ]
    
    for pattern in patterns:
        try:
            elements = root.findall(pattern)
            if elements:
                print(f"  Found {len(elements)} LegislationInfo elements with pattern: {pattern}")
                for elem in elements:
                    bill = extract_bill_info(elem)
                    if bill and bill['title'] != "No title available":
                        bills.append(bill)
                
                if bills:
                    print(f"  Successfully parsed {len(bills)} bills with valid titles")
                    return bills
        except:
            continue
    
    # Method 2: Parse raw XML with regex as fallback
    if not bills and raw_response and "LegislationInfo" in raw_response:
        print("  Attempting regex extraction from raw XML...")
        
        # Extract LegislationInfo blocks
        pattern = r'<(?:\w+:)?LegislationInfo[^>]*>(.*?)</(?:\w+:)?LegislationInfo>'
        matches = re.findall(pattern, raw_response, re.DOTALL)
        
        print(f"  Found {len(matches)} LegislationInfo blocks via regex")
        
        for match in matches:
            try:
                # Create a simple XML element from the match
                xml_str = f'<LegislationInfo>{match}</LegislationInfo>'
                elem = ET.fromstring(xml_str)
                bill = extract_bill_info(elem)
                if bill and bill['title'] != "No title available":
                    bills.append(bill)
            except:
                continue
        
        if bills:
            print(f"  Successfully extracted {len(bills)} bills via regex")
    
    return bills

def fetch_legislation_by_year() -> List[Dict]:
    """Fetch legislation for current year"""
    print(f"\nFetching legislation for year {CURRENT_YEAR}...")
    
    root, raw_response = make_soap_request(
        "GetLegislationByYear",
        {"year": str(CURRENT_YEAR)}
    )
    
    if root is None:
        print("  Failed to get valid response")
        return []
    
    bills = parse_legislation_response(root, raw_response)
    
    # Show sample bills
    if bills:
        print("  Sample bills found:")
        for bill in bills[:3]:
            print(f"    - {bill['number']}: {bill['title'][:60]}...")
    
    return bills

def fetch_prefiled_legislation() -> List[Dict]:
    """Fetch prefiled legislation"""
    print(f"\nFetching prefiled legislation for biennium {BIENNIUM}...")
    
    root, raw_response = make_soap_request(
        "GetPrefiledLegislationInfo",
        {"biennium": BIENNIUM}
    )
    
    if root is None:
        print("  Failed to get valid response")
        return []
    
    bills = parse_legislation_response(root, raw_response)
    
    # Show sample bills
    if bills:
        print("  Sample bills found:")
        for bill in bills[:3]:
            print(f"    - {bill['number']}: {bill['title'][:60]}...")
    
    return bills

def fetch_legislation_by_biennium() -> List[Dict]:
    """Fetch all legislation for biennium"""
    print(f"\nFetching all legislation for biennium {BIENNIUM}...")
    
    root, raw_response = make_soap_request(
        "GetLegislationInfoByBiennium",
        {"biennium": BIENNIUM}
    )
    
    if root is None:
        print("  Failed to get valid response")
        return []
    
    bills = parse_legislation_response(root, raw_response)
    
    # Show sample bills
    if bills:
        print("  Sample bills found:")
        for bill in bills[:3]:
            print(f"    - {bill['number']}: {bill['title'][:60]}...")
    
    return bills

def fetch_legislative_status_changes() -> List[Dict]:
    """Fetch bills with recent status changes"""
    print("\nFetching legislative status changes...")
    
    # Get changes from last 60 days
    begin_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")
    
    root, raw_response = make_soap_request(
        "GetLegislativeStatusChangesByDateRange",
        {
            "biennium": BIENNIUM,
            "beginDate": begin_date,
            "endDate": end_date
        }
    )
    
    if root is None:
        print("  Failed to get valid response")
        return []
    
    bills = parse_legislation_response(root, raw_response)
    
    # Show sample bills
    if bills:
        print("  Sample bills found:")
        for bill in bills[:3]:
            print(f"    - {bill['number']}: {bill['title'][:60]}...")
    
    return bills

def fetch_legislation_introduced() -> List[Dict]:
    """Fetch recently introduced legislation"""
    print("\nFetching recently introduced legislation...")
    
    # Try to get legislation introduced since December 2025
    since_date = "2025-12-01"
    
    root, raw_response = make_soap_request(
        "GetLegislationIntroducedSince",
        {"sinceDate": since_date}
    )
    
    if root is None:
        print("  Failed to get valid response")
        return []
    
    bills = parse_legislation_response(root, raw_response)
    
    # Show sample bills
    if bills:
        print("  Sample bills found:")
        for bill in bills[:3]:
            print(f"    - {bill['number']}: {bill['title'][:60]}...")
    
    return bills

def determine_committee(bill_number: str, title: str) -> str:
    """Determine committee based on bill and title"""
    title_lower = title.lower()
    
    committees = {
        "Education": ["education", "school", "student", "teacher", "learning"],
        "Transportation": ["transportation", "road", "highway", "transit", "vehicle"],
        "Housing": ["housing", "rent", "tenant", "landlord", "homeless", "affordable"],
        "Health & Long-Term Care": ["health", "medical", "hospital", "mental", "behavioral", "medicare"],
        "Environment & Energy": ["environment", "climate", "energy", "pollution", "conservation", "water"],
        "Finance": ["tax", "revenue", "budget", "fiscal", "appropriation"],
        "Consumer Protection & Business": ["consumer", "business", "commerce", "corporation", "insurance"],
        "Law & Justice": ["crime", "criminal", "justice", "court", "legal", "police"],
        "Labor & Commerce": ["labor", "employment", "worker", "wage", "workplace", "unemployment"],
        "State Government": ["state", "government", "agency", "administration"],
        "Agriculture": ["agriculture", "farm", "food", "rural", "crop"]
    }
    
    for committee, keywords in committees.items():
        if any(keyword in title_lower for keyword in keywords):
            return committee
    
    return "Rules"

def determine_topic(title: str) -> str:
    """Determine topic from title"""
    title_lower = title.lower()
    
    topics = {
        "Education": ["education", "school", "student", "teacher", "learning", "college"],
        "Tax & Revenue": ["tax", "revenue", "budget", "fiscal", "fee", "appropriation"],
        "Housing": ["housing", "rent", "tenant", "landlord", "affordable", "homeless"],
        "Healthcare": ["health", "medical", "hospital", "mental", "behavioral", "insurance", "medicare"],
        "Environment": ["environment", "climate", "energy", "pollution", "conservation", "water", "wildlife"],
        "Transportation": ["transportation", "road", "highway", "transit", "traffic", "vehicle"],
        "Public Safety": ["crime", "safety", "police", "justice", "criminal", "enforcement", "firearm"],
        "Business": ["business", "commerce", "trade", "economy", "corporation", "industry"],
        "Technology": ["technology", "internet", "data", "privacy", "cyber", "artificial", "digital"],
        "Labor": ["labor", "employment", "worker", "wage", "union", "workplace"],
        "Agriculture": ["agriculture", "farm", "food", "rural", "agricultural", "crop"]
    }
    
    for topic, keywords in topics.items():
        if any(keyword in title_lower for keyword in keywords):
            return topic
    
    return "General Government"

def determine_priority(title: str) -> str:
    """Determine priority from title"""
    title_lower = title.lower()
    
    high_priority = ["emergency", "urgent", "crisis", "immediate", "critical", "supplemental budget", "omnibus"]
    low_priority = ["technical", "clarifying", "housekeeping", "minor", "study", "memorial", "proclamation"]
    
    for keyword in high_priority:
        if keyword in title_lower:
            return "high"
    
    for keyword in low_priority:
        if keyword in title_lower:
            return "low"
    
    return "medium"

def validate_bills(bills: List[Dict]) -> Tuple[bool, List[str]]:
    """Validate bill data"""
    issues = []
    
    if not bills:
        issues.append("No bills retrieved")
        return False, issues
    
    # Check for valid titles
    bills_with_titles = [b for b in bills if b.get('title') and b['title'] != 'No title available']
    if len(bills_with_titles) == 0:
        issues.append("No bills have valid titles")
    elif len(bills_with_titles) < len(bills) * 0.5:
        issues.append(f"Only {len(bills_with_titles)}/{len(bills)} bills have valid titles")
    
    # Check bill number format
    valid_format = [b for b in bills if re.match(r'^[A-Z]+\s+\d+', b.get('number', ''))]
    if len(valid_format) < len(bills) * 0.8:
        issues.append(f"Only {len(valid_format)}/{len(bills)} bills have valid number format")
    
    return len(issues) == 0, issues

def save_bills_data(bills: List[Dict]) -> Dict:
    """Save bills to JSON"""
    # Remove duplicates by ID
    unique_bills = {}
    for bill in bills:
        bill_id = bill.get('id')
        if bill_id and bill_id not in unique_bills:
            unique_bills[bill_id] = bill
        elif bill_id:
            # Prefer bills with titles
            if bill['title'] != "No title available" and unique_bills[bill_id]['title'] == "No title available":
                unique_bills[bill_id] = bill
    
    bills = list(unique_bills.values())
    
    # Sort bills
    def sort_key(bill):
        number = bill.get('number', '')
        match = re.match(r'^([A-Z]+)\s+(\d+)', number)
        if match:
            return (match.group(1), int(match.group(2)))
        return ('ZZZ', 99999)
    
    bills.sort(key=sort_key)
    
    data = {
        "lastSync": datetime.now().isoformat(),
        "sessionYear": CURRENT_YEAR,
        "biennium": BIENNIUM,
        "sessionStart": "2026-01-12",
        "sessionEnd": "2026-04-23",  # Corrected end date
        "totalBills": len(bills),
        "bills": bills,
        "metadata": {
            "source": "Washington State Legislature Web Services",
            "apiUrl": BASE_API_URL,
            "updateFrequency": "daily",
            "dataVersion": "3.2.0"
        }
    }
    
    # Save main file
    data_file = DATA_DIR / "bills.json"
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(bills)} bills to {data_file}")
    
    # Save timestamped backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sync_file = SYNC_DIR / f"bills_{timestamp}.json"
    with open(sync_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Backup saved to {sync_file}")
    
    return data

def test_api_connection() -> bool:
    """Test basic API connectivity"""
    print("\n" + "=" * 60)
    print("TESTING API CONNECTION")
    print("=" * 60)
    
    try:
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

def main():
    """Main execution"""
    print(f"Washington State Legislature Bill Fetcher")
    print(f"Started at: {datetime.now()}")
    print("=" * 60)
    
    # Setup
    ensure_directories()
    
    # Test connection
    if not test_api_connection():
        print("\nWARNING: API connection test failed, but continuing...")
    
    # Collect bills
    all_bills = {}
    
    methods = [
        ("By Year", fetch_legislation_by_year),
        ("Prefiled", fetch_prefiled_legislation),
        ("By Biennium", fetch_legislation_by_biennium),
        ("Status Changes", fetch_legislative_status_changes),
        ("Recently Introduced", fetch_legislation_introduced)
    ]
    
    for method_name, method_func in methods:
        print(f"\n{'=' * 60}")
        print(f"Method: {method_name}")
        print('=' * 60)
        
        try:
            bills = method_func()
            new_count = 0
            updated_count = 0
            
            for bill in bills:
                bill_id = bill['id']
                if bill_id not in all_bills:
                    all_bills[bill_id] = bill
                    new_count += 1
                elif bill['title'] != "No title available" and all_bills[bill_id]['title'] == "No title available":
                    # Update with better data
                    all_bills[bill_id] = bill
                    updated_count += 1
            
            print(f"  Result: {len(bills)} bills found, {new_count} new, {updated_count} updated")
            
        except Exception as e:
            print(f"  ERROR in {method_name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Final results
    final_bills = list(all_bills.values())
    
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Total unique bills collected: {len(final_bills)}")
    
    # Validate
    is_valid, issues = validate_bills(final_bills)
    
    if is_valid:
        print("Data validation: PASSED")
    else:
        print("Data validation: WARNINGS")
        for issue in issues:
            print(f"  - {issue}")
    
    # Save data
    if final_bills:
        save_bills_data(final_bills)
        
        # Show samples
        bills_with_titles = [b for b in final_bills if b['title'] != "No title available"]
        if bills_with_titles:
            print(f"\nSample bills with titles ({len(bills_with_titles)} total):")
            for bill in bills_with_titles[:10]:
                print(f"  {bill['number']}: {bill['title'][:60]}...")
    else:
        print("\nERROR: No bills retrieved")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print(f"Completed at: {datetime.now()}")
    
    # Exit code based on results
    if len(final_bills) == 0:
        sys.exit(1)
    elif not is_valid:
        sys.exit(2)  # Partial success
    
    return len(final_bills)

if __name__ == "__main__":
    bill_count = main()
    print(f"\nFinal bill count: {bill_count}")

#!/usr/bin/env python3
"""
Washington State Legislature Bill Fetcher
Fixed version based on successful previous implementations
Uses proper SOAP parsing and correct API methods
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
YEAR = 2025
DATA_DIR = Path("data")

# SOAP Service Endpoints
LEGISLATION_SERVICE = f"{BASE_API_URL}/LegislationService.asmx"

def ensure_data_dir():
    """Ensure data directory exists"""
    DATA_DIR.mkdir(exist_ok=True)

def make_soap_request(soap_body: str, soap_action: str, debug: bool = False) -> Optional[ET.Element]:
    """Make SOAP request to WA Legislature API with proper headers"""
    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': soap_action  # No quotes needed here
    }
    
    soap_envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
               xmlns:xsd="http://www.w3.org/2001/XMLSchema" 
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    {soap_body}
  </soap:Body>
</soap:Envelope>"""
    
    if debug:
        print(f"SOAP Action: {soap_action}")
        with open('debug_request.xml', 'w') as f:
            f.write(soap_envelope)
        print("Request saved to debug_request.xml")
    
    try:
        response = requests.post(LEGISLATION_SERVICE, 
                                data=soap_envelope, 
                                headers=headers, 
                                timeout=120)
        
        if debug:
            print(f"Response Status: {response.status_code}")
            with open('debug_response.xml', 'w') as f:
                f.write(response.text)
            print("Response saved to debug_response.xml")
        
        if response.status_code == 200:
            # Check for SOAP faults
            if 'soap:Fault' in response.text:
                print("SOAP Fault detected:")
                # Parse the fault
                try:
                    fault_root = ET.fromstring(response.text)
                    fault_string = fault_root.find('.//faultstring')
                    if fault_string is not None:
                        print(f"Fault: {fault_string.text}")
                except:
                    print(response.text[:500])
                return None
            
            try:
                root = ET.fromstring(response.text)
                return root
            except ET.ParseError as e:
                print(f"XML Parse Error: {e}")
                print("Response content:")
                print(response.text[:1000])
                return None
        else:
            print(f"HTTP Error {response.status_code}")
            print(response.text[:500])
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None

def fetch_legislation_by_biennium() -> List[Dict]:
    """Fetch legislation using GetLegislationByBiennium method"""
    print(f"Fetching legislation for biennium {BIENNIUM}")
    
    soap_body = f"""
    <GetLegislationByBiennium xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
    </GetLegislationByBiennium>"""
    
    root = make_soap_request(
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislationByBiennium",
        debug=True
    )
    
    if root is None:
        return []
    
    return parse_legislation_response(root)

def fetch_legislation_by_year() -> List[Dict]:
    """Fetch legislation using GetLegislationByYear method"""
    print(f"Fetching legislation for year {YEAR}")
    
    soap_body = f"""
    <GetLegislationByYear xmlns="http://WSLWebServices.leg.wa.gov/">
      <year>{YEAR}</year>
    </GetLegislationByYear>"""
    
    root = make_soap_request(
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislationByYear",
        debug=True
    )
    
    if root is None:
        return []
    
    return parse_legislation_response(root)

def fetch_legislation_by_request_number(request_number: str = "26-0001") -> List[Dict]:
    """Fetch a specific piece of legislation by request number for testing"""
    print(f"Fetching legislation by request number {request_number}")
    
    soap_body = f"""
    <GetLegislationByRequestNumber xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>{BIENNIUM}</biennium>
      <requestNumber>{request_number}</requestNumber>
    </GetLegislationByRequestNumber>"""
    
    root = make_soap_request(
        soap_body,
        "http://WSLWebServices.leg.wa.gov/GetLegislationByRequestNumber",
        debug=True
    )
    
    if root is None:
        return []
    
    return parse_legislation_response(root)

def parse_legislation_response(root: ET.Element) -> List[Dict]:
    """Parse XML response and extract legislation info"""
    bills = []
    
    # Remove namespaces by converting to string and back
    xml_str = ET.tostring(root, encoding='unicode')
    # Remove namespace declarations
    xml_str = re.sub(r'xmlns[^=]*="[^"]*"', '', xml_str)
    xml_str = re.sub(r'xsi:[^=]*="[^"]*"', '', xml_str)
    xml_str = re.sub(r'xsd:[^=]*="[^"]*"', '', xml_str)
    
    try:
        clean_root = ET.fromstring(xml_str)
    except ET.ParseError:
        print("Could not parse cleaned XML")
        return []
    
    # Look for various possible containers
    containers = [
        './/GetLegislationByBienniumResult',
        './/GetLegislationByYearResult',  
        './/GetLegislationByRequestNumberResult',
        './/ArrayOfLegislationInfo',
        './/LegislationInfo'
    ]
    
    legislation_elements = []
    for container_path in containers:
        found = clean_root.findall(container_path)
        if found:
            print(f"Found container: {container_path} with {len(found)} elements")
            for container in found:
                # If this is already a LegislationInfo element
                if container.tag == 'LegislationInfo':
                    legislation_elements.append(container)
                else:
                    # Look for LegislationInfo children
                    leg_infos = container.findall('.//LegislationInfo')
                    legislation_elements.extend(leg_infos)
            break  # Use the first container type we find
    
    # If we didn't find any containers, search the entire document
    if not legislation_elements:
        legislation_elements = clean_root.findall('.//LegislationInfo')
    
    print(f"Found {len(legislation_elements)} LegislationInfo elements total")
    
    for i, leg_elem in enumerate(legislation_elements):
        if i < 5:  # Debug first 5 elements
            print(f"\nElement {i+1}:")
            for child in leg_elem:
                if child.text and child.text.strip():
                    print(f"  {child.tag}: {child.text.strip()}")
        
        bill = parse_legislation_element(leg_elem)
        if bill:
            bills.append(bill)
    
    return bills

def parse_legislation_element(elem: ET.Element) -> Optional[Dict]:
    """Parse a single LegislationInfo element"""
    try:
        def get_text(tag: str, default: str = "") -> str:
            """Get text from element, handling various cases"""
            child = elem.find(tag)
            if child is not None and child.text:
                return child.text.strip()
            return default
        
        # Extract key fields
        biennium = get_text('Biennium', BIENNIUM)
        bill_id = get_text('BillId')
        bill_number = get_text('BillNumber')
        
        if not bill_id and not bill_number:
            return None
        
        # Get descriptions
        short_desc = get_text('ShortDescription')
        long_desc = get_text('LongDescription') 
        legal_title = get_text('LegalTitle')
        
        title = short_desc or legal_title or long_desc or "No title available"
        if not title or title == "No title available":
            return None
        
        # Get other fields
        substitute_version = get_text('SubstituteVersion', '')
        engrossed_version = get_text('EngrossedVersion', '')
        original_agency = get_text('OriginalAgency', '')
        display_number = get_text('DisplayNumber', '')
        active = get_text('Active', 'true')
        
        # Build display number
        if display_number:
            full_number = display_number
        else:
            full_number = build_bill_number(bill_number, original_agency, substitute_version, engrossed_version)
        
        # Get sponsor info
        prime_sponsor = get_text('PrimeSponsor', '')
        requested_by = get_text('RequestedBy', '')
        sponsor = prime_sponsor or requested_by or "Unknown"
        
        # Get status
        current_status = get_text('CurrentStatus', '')
        history_line = get_text('HistoryLine', '')
        status = parse_status(current_status, history_line, active)
        
        # Get dates
        introduced_date = get_text('IntroducedDate', '')
        prefiled_date = get_text('PrefiledDate', '')
        date_to_use = introduced_date or prefiled_date or "2025-12-01"
        
        # Format date
        if 'T' in date_to_use:
            try:
                dt = datetime.fromisoformat(date_to_use.replace('Z', '+00:00'))
                formatted_date = dt.date().isoformat()
            except:
                formatted_date = "2025-12-01"
        else:
            formatted_date = date_to_use[:10] if len(date_to_use) >= 10 else "2025-12-01"
        
        # Create bill dict
        bill = {
            "id": bill_id or f"bill_{bill_number}",
            "number": full_number,
            "billNumber": bill_number,
            "title": title,
            "sponsor": sponsor,
            "description": long_desc or f"A bill relating to {title.lower()}",
            "status": status,
            "committee": determine_committee(full_number, title),
            "priority": determine_priority(title),
            "topic": determine_topic(title),
            "introducedDate": formatted_date,
            "lastUpdated": datetime.now().isoformat(),
            "legUrl": f"{BASE_WEB_URL}/billsummary?BillNumber={bill_number}&Year=2026",
            "biennium": biennium,
            "active": active.lower() == 'true',
            "hearings": []
        }
        
        return bill
        
    except Exception as e:
        print(f"Error parsing element: {e}")
        return None

def build_bill_number(bill_number: str, original_agency: str, substitute_version: str, engrossed_version: str) -> str:
    """Build the full bill number with prefix and version info"""
    
    # Determine prefix
    if 'House' in original_agency:
        prefix = 'HB'
    elif 'Senate' in original_agency:
        prefix = 'SB'
    else:
        # Guess from number
        try:
            num = int(bill_number)
            if num >= 5000:
                prefix = 'SB'
            elif num >= 4000:
                if num >= 4400:
                    prefix = 'HCR'
                elif num >= 4100:
                    prefix = 'HJM'
                else:
                    prefix = 'HJR'
            else:
                prefix = 'HB'
        except:
            prefix = 'HB'
    
    # Add version info
    version_prefix = ''
    if substitute_version:
        if '2S' in substitute_version:
            version_prefix = '2S'
        elif 'S' in substitute_version:
            version_prefix = 'S'
    
    if engrossed_version and 'E' in engrossed_version:
        version_prefix += 'E'
    
    # Combine
    if version_prefix:
        return f"{version_prefix}{prefix} {bill_number}"
    else:
        return f"{prefix} {bill_number}"

def parse_status(current_status: str, history_line: str, active: str) -> str:
    """Parse bill status from available fields"""
    status_text = f"{current_status} {history_line}".lower()
    
    if active.lower() == 'false':
        return 'failed'
    elif 'signed' in status_text or 'law' in status_text:
        return 'enacted'
    elif 'veto' in status_text:
        return 'vetoed'
    elif 'passed' in status_text:
        return 'passed'
    elif 'committee' in status_text:
        return 'committee'
    elif 'introduced' in status_text or 'first reading' in status_text:
        return 'introduced'
    elif 'prefiled' in status_text:
        return 'prefiled'
    else:
        return 'active'

def determine_committee(bill_number: str, title: str) -> str:
    """Determine committee based on bill content"""
    title_lower = title.lower()
    
    if any(word in title_lower for word in ['education', 'school', 'student']):
        return "Education"
    elif any(word in title_lower for word in ['transportation', 'road', 'highway']):
        return "Transportation"
    elif any(word in title_lower for word in ['housing', 'rent', 'tenant']):
        return "Housing"
    elif any(word in title_lower for word in ['health', 'medical', 'hospital']):
        return "Health & Long-Term Care"
    elif any(word in title_lower for word in ['environment', 'energy', 'climate']):
        return "Environment & Energy"
    elif any(word in title_lower for word in ['tax', 'revenue', 'budget']):
        return "Finance" if bill_number.startswith('HB') else "Ways & Means"
    else:
        return "State Government & Tribal Relations"

def determine_topic(title: str) -> str:
    """Determine topic from title"""
    title_lower = title.lower()
    
    topics = {
        "Education": ["education", "school", "student"],
        "Tax & Revenue": ["tax", "revenue", "budget"],
        "Housing": ["housing", "rent", "tenant"],
        "Healthcare": ["health", "medical", "hospital"],
        "Environment": ["environment", "energy", "climate"],
        "Transportation": ["transport", "road", "highway"],
        "Public Safety": ["crime", "safety", "police"],
        "Business": ["business", "commerce", "trade"],
        "Technology": ["technology", "internet", "data"],
        "Labor": ["labor", "employment", "worker"]
    }
    
    for topic, keywords in topics.items():
        if any(keyword in title_lower for keyword in keywords):
            return topic
    
    return "General Government"

def determine_priority(title: str) -> str:
    """Determine priority from title"""
    title_lower = title.lower()
    
    if any(word in title_lower for word in ['emergency', 'urgent', 'budget']):
        return "high"
    elif any(word in title_lower for word in ['technical', 'clarifying', 'housekeeping']):
        return "low"
    
    return "medium"

def save_bills_data(bills: List[Dict]) -> Dict:
    """Save bills to JSON file"""
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
        match = re.match(r'([A-Z]+)\s*(\d+)', number)
        if match:
            return (match.group(1), int(match.group(2)))
        return ('ZZ', 99999)
    
    bills.sort(key=sort_key)
    
    data = {
        "lastSync": datetime.now().isoformat(),
        "sessionYear": 2026,
        "biennium": BIENNIUM,
        "sessionStart": "2026-01-12",
        "sessionEnd": "2026-03-12",
        "totalBills": len(bills),
        "bills": bills,
        "metadata": {
            "source": "Washington State Legislature Web Services",
            "apiUrl": BASE_API_URL,
            "updateFrequency": "daily",
            "dataVersion": "3.2.0"
        }
    }
    
    data_file = DATA_DIR / "bills.json"
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Saved {len(bills)} bills to {data_file}")
    return data

def main():
    """Main execution function"""
    print(f"Starting WA Legislature Bill Fetcher - {datetime.now()}")
    print("Using corrected API methods and XML parsing")
    print("=" * 60)
    
    ensure_data_dir()
    
    all_bills = {}
    
    # Try multiple methods to get bills
    methods = [
        ("GetLegislationByBiennium", fetch_legislation_by_biennium),
        ("GetLegislationByYear", fetch_legislation_by_year),
    ]
    
    for method_name, method_func in methods:
        print(f"\nTrying {method_name}...")
        try:
            bills = method_func()
            new_bills = 0
            for bill in bills:
                if bill['id'] not in all_bills:
                    all_bills[bill['id']] = bill
                    new_bills += 1
            print(f"  Found {len(bills)} bills ({new_bills} new)")
        except Exception as e:
            print(f"  Error with {method_name}: {e}")
    
    # If no bills found, try a specific request number as a test
    if len(all_bills) == 0:
        print("\nTrying GetLegislationByRequestNumber as test...")
        try:
            test_bills = fetch_legislation_by_request_number()
            for bill in test_bills:
                all_bills[bill['id']] = bill
            print(f"  Found {len(test_bills)} bills from test request")
        except Exception as e:
            print(f"  Error with test request: {e}")
    
    final_bills = list(all_bills.values())
    
    print(f"\n" + "=" * 60)
    print(f"Total unique bills collected: {len(final_bills)}")
    
    if final_bills:
        print("\nSample bills:")
        for bill in final_bills[:3]:
            print(f"  {bill['number']}: {bill['title']}")
        
        save_bills_data(final_bills)
    else:
        print("No bills found. Check debug files for details.")
    
    print("=" * 60)
    print(f"Complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()

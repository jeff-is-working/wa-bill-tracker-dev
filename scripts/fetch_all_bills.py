#!/usr/bin/env python3
"""
Washington State Legislature Bill Fetcher
Fetches bills for the 2026 session using the official WA Legislature Web Services API
Compliant with https://wslwebservices.leg.wa.gov/
"""

import json
import requests
from datetime import datetime, timedelta
import os
from pathlib import Path
import time
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET

# Configuration
WS_BASE_URL = "https://wslwebservices.leg.wa.gov"
YEAR = 2026
DATA_DIR = Path("data")
SESSION = "2025-26"  # Biennial session

def ensure_data_dir():
    """Ensure data directory exists"""
    DATA_DIR.mkdir(exist_ok=True)

def fetch_legislation_from_api(year: int) -> List[Dict]:
    """
    Fetch all legislation for a given year using the WA Legislature Web Services API
    Uses the Legislation Service to get all bills, resolutions, etc.
    """
    bills = []
    
    try:
        # Use the Legislation Service to get all legislation for the year
        url = f"{WS_BASE_URL}/LegislationService.asmx/GetLegislation"
        params = {
            'year': year
        }
        
        print(f"📡 Fetching legislation from WA Legislature Web Services API...")
        print(f"   URL: {url}")
        print(f"   Year: {year}")
        
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            # Parse XML response
            root = ET.fromstring(response.content)
            
            # Process each legislation item
            for item in root.findall('.//LegislationInfo'):
                bill_id = item.findtext('BillId', '')
                bill_number = item.findtext('BillNumber', '')
                
                if not bill_id or not bill_number:
                    continue
                
                # Get detailed information for this bill
                bill_details = fetch_bill_details(bill_id, year)
                
                if bill_details:
                    bills.append(bill_details)
                    
                # Rate limiting - be respectful of the API
                time.sleep(0.1)
            
            print(f"✅ Fetched {len(bills)} bills from API")
            
        else:
            print(f"❌ API request failed with status code: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error fetching from API: {e}")
    
    return bills

def fetch_bill_details(bill_id: str, year: int) -> Optional[Dict]:
    """
    Fetch detailed information for a specific bill using the Legislation Service
    """
    try:
        url = f"{WS_BASE_URL}/LegislationService.asmx/GetLegislation"
        params = {
            'year': year,
            'billNumber': bill_id
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            item = root.find('.//LegislationInfo')
            
            if item is not None:
                bill_number = item.findtext('BillNumber', '')
                short_description = item.findtext('ShortDescription', '')
                long_description = item.findtext('LongDescription', '')
                sponsor_name = item.findtext('PrimeSponsorName', '')
                
                # Determine status
                status = determine_status_from_api(item)
                
                # Determine chamber and committee
                chamber = "House" if bill_number.startswith('H') else "Senate"
                committee = item.findtext('CurrentCommittee', 'Unknown')
                
                # Create bill object
                bill = {
                    "id": bill_number.replace(" ", ""),
                    "number": bill_number,
                    "title": short_description or long_description[:100],
                    "sponsor": sponsor_name or f"{chamber} Member",
                    "description": long_description or short_description,
                    "status": status,
                    "committee": committee,
                    "priority": determine_priority(short_description or long_description),
                    "topic": determine_topic(short_description or long_description),
                    "introducedDate": item.findtext('IntroducedDate', datetime.now().strftime('%Y-%m-%d')),
                    "lastUpdated": datetime.now().isoformat(),
                    "legUrl": f"https://app.leg.wa.gov/billsummary?BillNumber={bill_number.split()[1]}&Year={year}",
                    "hearings": []
                }
                
                return bill
                
    except Exception as e:
        print(f"   ⚠️  Error fetching details for {bill_id}: {e}")
    
    return None

def determine_status_from_api(item: ET.Element) -> str:
    """Determine bill status from API data"""
    status_text = item.findtext('Status', '').lower()
    
    if 'passed' in status_text or 'enacted' in status_text:
        return 'passed'
    elif 'failed' in status_text or 'dead' in status_text:
        return 'failed'
    elif 'committee' in status_text:
        return 'committee'
    elif 'introduced' in status_text:
        return 'introduced'
    else:
        return 'prefiled'

def determine_topic(description: str) -> str:
    """Determine bill topic from description"""
    if not description:
        return "General Government"
    
    desc_lower = description.lower()
    
    if any(word in desc_lower for word in ["education", "school", "student", "teacher", "university", "college"]):
        return "Education"
    elif any(word in desc_lower for word in ["tax", "revenue", "budget", "fiscal", "finance"]):
        return "Tax & Revenue"
    elif any(word in desc_lower for word in ["housing", "rent", "tenant", "landlord", "homeless"]):
        return "Housing"
    elif any(word in desc_lower for word in ["health", "medical", "hospital", "mental", "healthcare"]):
        return "Healthcare"
    elif any(word in desc_lower for word in ["environment", "climate", "energy", "pollution", "clean"]):
        return "Environment"
    elif any(word in desc_lower for word in ["transport", "road", "highway", "transit", "traffic"]):
        return "Transportation"
    elif any(word in desc_lower for word in ["crime", "safety", "police", "justice", "court"]):
        return "Public Safety"
    elif any(word in desc_lower for word in ["business", "commerce", "trade", "economy"]):
        return "Business"
    elif any(word in desc_lower for word in ["technology", "internet", "data", "privacy", "cyber"]):
        return "Technology"
    else:
        return "General Government"

def determine_priority(description: str) -> str:
    """Determine bill priority based on keywords"""
    if not description:
        return "medium"
    
    desc_lower = description.lower()
    
    # High priority keywords
    high_priority = ["emergency", "budget", "funding", "public safety", 
                    "crisis", "healthcare access", "relief"]
    
    # Low priority keywords  
    low_priority = ["technical", "clarifying", "housekeeping", "minor", "study"]
    
    for keyword in high_priority:
        if keyword in desc_lower:
            return "high"
    
    for keyword in low_priority:
        if keyword in desc_lower:
            return "low"
    
    return "medium"

def save_bills_data(bills: List[Dict]) -> Dict:
    """Save bills data to JSON file"""
    # Sort bills by number
    bills.sort(key=lambda x: (x['number'].split()[0], 
                              int(''.join(filter(str.isdigit, x['number']))) if any(c.isdigit() for c in x['number']) else 0))
    
    data = {
        "lastSync": datetime.now().isoformat(),
        "sessionYear": YEAR,
        "sessionStart": "2026-01-12",
        "sessionEnd": "2026-03-12",
        "totalBills": len(bills),
        "bills": bills,
        "metadata": {
            "source": "Washington State Legislature Web Services API",
            "apiUrl": "https://wslwebservices.leg.wa.gov/",
            "updateFrequency": "daily",
            "dataVersion": "3.0.0",
            "billTypes": ["HB", "SB", "HJR", "SJR", "HJM", "SJM", "HCR", "SCR"]
        }
    }
    
    data_file = DATA_DIR / "bills.json"
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved {len(bills)} bills to {data_file}")
    return data

def create_sync_log(bills_count: int, new_count: int = 0, status: str = "success"):
    """Create sync log for monitoring"""
    log = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "billsCount": bills_count,
        "newBillsAdded": new_count,
        "nextSync": (datetime.now() + timedelta(hours=24)).isoformat()
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
    
    print(f"📋 Sync log updated: {status} - {bills_count} bills, {new_count} new")

def load_existing_data() -> Optional[Dict]:
    """Load existing bills data if it exists"""
    data_file = DATA_DIR / "bills.json"
    if data_file.exists():
        with open(data_file, 'r') as f:
            return json.load(f)
    return None

def main():
    """Main execution function"""
    print(f"🚀 Starting WA Legislature Bill Fetcher - {datetime.now()}")
    print(f"📡 Using WA Legislature Web Services API")
    print(f"   API Base: {WS_BASE_URL}")
    print("=" * 60)
    
    # Ensure data directory exists
    ensure_data_dir()
    
    # Load existing data
    existing_data = load_existing_data()
    existing_bills = {}
    if existing_data:
        existing_bills = {bill['id']: bill for bill in existing_data.get('bills', [])}
        print(f"📚 Loaded {len(existing_bills)} existing bills")
    
    # Fetch bills from API
    print(f"📥 Fetching bills for {YEAR} session...")
    all_bills = fetch_legislation_from_api(YEAR)
    
    if not all_bills:
        print("⚠️  No bills fetched from API, keeping existing data")
        if existing_bills:
            all_bills = list(existing_bills.values())
        else:
            print("❌ No existing data available")
            create_sync_log(0, 0, "failed")
            return
    
    # Track new bills
    new_bills = []
    updated_bills = []
    
    for bill in all_bills:
        if bill['id'] not in existing_bills:
            new_bills.append(bill)
        elif bill != existing_bills[bill['id']]:
            updated_bills.append(bill)
    
    print(f"   ✨ Found {len(new_bills)} new bills")
    print(f"   🔄 Updated {len(updated_bills)} existing bills")
    
    # Merge with existing bills
    for bill in all_bills:
        existing_bills[bill['id']] = bill
    
    # Convert back to list
    final_bills = list(existing_bills.values())
    
    # Save bills data
    save_bills_data(final_bills)
    
    # Create sync log
    create_sync_log(len(final_bills), len(new_bills), "success")
    
    print("=" * 60)
    print(f"✅ Successfully updated database:")
    print(f"   - Total bills: {len(final_bills)}")
    print(f"   - New bills: {len(new_bills)}")
    print(f"   - Updated bills: {len(updated_bills)}")
    print(f"🏁 Update complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Washington State Legislature Bill Fetcher - Corrected Version
Uses the REST API endpoints properly without any sample data
Only fetches real bills from the official API
"""

import json
import requests
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

def ensure_data_dir():
    """Ensure data directory exists"""
    DATA_DIR.mkdir(exist_ok=True)

def fetch_bills_via_rest() -> List[Dict]:
    """
    Fetch bills using the REST API endpoint
    This is the correct way to get bill data from WA Legislature
    """
    bills = []
    
    # The correct REST endpoint for getting legislation
    api_url = f"{BASE_API_URL}/LegislativeDocumentService/v1/documents"
    
    # Parameters for the API call
    params = {
        "biennium": BIENNIUM,
        "documentClass": "Bills"
    }
    
    print(f"Fetching bills from REST API for biennium {BIENNIUM}...")
    
    try:
        response = requests.get(api_url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            # Process each bill in the response
            for item in data:
                bill = process_api_bill(item)
                if bill and bill.get('title') != 'No title available':
                    bills.append(bill)
                    
            print(f"  Successfully fetched {len(bills)} bills")
        else:
            print(f"  API returned status code: {response.status_code}")
            # Try alternative endpoint
            bills = fetch_bills_alternative()
            
    except requests.exceptions.RequestException as e:
        print(f"  Error fetching from REST API: {e}")
        bills = fetch_bills_alternative()
    except json.JSONDecodeError as e:
        print(f"  Error parsing JSON response: {e}")
        bills = []
    
    return bills

def fetch_bills_alternative() -> List[Dict]:
    """
    Alternative method using the bill summary endpoint
    Fetches bills by iterating through known bill number ranges
    """
    bills = []
    
    print("Using alternative fetch method...")
    
    # Known bill number ranges for WA Legislature
    # These are the typical ranges, we'll check which ones exist
    ranges = [
        ("HB", 1000, 1100),  # House Bills start at 1000
        ("HB", 1100, 1200),
        ("HB", 1200, 1300),
        ("SB", 5000, 5100),  # Senate Bills start at 5000
        ("SB", 5100, 5200),
        ("SB", 5200, 5300),
    ]
    
    for bill_type, start, end in ranges:
        print(f"  Checking {bill_type} {start}-{end}...")
        for bill_num in range(start, min(start + 10, end)):  # Check first 10 in each range
            bill_data = fetch_single_bill(bill_type, bill_num)
            if bill_data:
                bills.append(bill_data)
                time.sleep(0.1)  # Rate limiting
                
        # If we found bills in this range, continue checking
        if len(bills) > 0:
            break
    
    return bills

def fetch_single_bill(bill_type: str, bill_number: int) -> Optional[Dict]:
    """
    Fetch a single bill using the document retrieval endpoint
    """
    try:
        # Use the bill summary API endpoint
        api_url = f"{BASE_API_URL}/LegislativeDocumentService/v1/documents/{BIENNIUM}/{bill_type}/{bill_number}"
        
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return process_api_bill(data)
        elif response.status_code == 404:
            # Bill doesn't exist
            return None
        else:
            return None
            
    except:
        return None

def process_api_bill(data: Dict) -> Optional[Dict]:
    """
    Process bill data from API response
    Maps API fields to our schema
    """
    try:
        # Extract bill identifier
        bill_id = data.get('billId', data.get('documentId', ''))
        if not bill_id:
            return None
        
        # Parse bill number from ID
        match = re.match(r'(\d{4}-\d{2})\s+([A-Z]+)\s+(\d+)', bill_id)
        if match:
            biennium, bill_type, number = match.groups()
        else:
            # Try simpler format
            match = re.match(r'([A-Z]+)\s+(\d+)', bill_id)
            if match:
                bill_type, number = match.groups()
                biennium = BIENNIUM
            else:
                return None
        
        formatted_number = f"{bill_type} {number}"
        formatted_id = f"{bill_type}{number}"
        
        # Get title and description
        title = data.get('shortDescription', data.get('title', ''))
        if not title or title == '':
            title = data.get('longDescription', '')
            if not title:
                return None  # Skip bills with no title
        
        # Get sponsor
        sponsor = data.get('primeSponsor', data.get('sponsor', 'Unknown'))
        if isinstance(sponsor, dict):
            sponsor = sponsor.get('name', 'Unknown')
        
        # Get status
        status = data.get('status', 'Introduced')
        if isinstance(status, dict):
            status = status.get('description', 'Introduced')
        
        # Get dates
        introduced_date = data.get('introducedDate', '')
        if introduced_date:
            try:
                dt = datetime.fromisoformat(introduced_date.replace('Z', '+00:00'))
                introduced_date = dt.strftime('%Y-%m-%d')
            except:
                pass
        
        # Get committee
        committee = data.get('currentCommittee', data.get('committee', ''))
        if isinstance(committee, dict):
            committee = committee.get('name', '')
        if not committee:
            committee = determine_committee_from_type(bill_type)
        
        # Build the bill object
        bill = {
            "id": formatted_id,
            "number": formatted_number,
            "title": title,
            "sponsor": sponsor,
            "description": data.get('longDescription', title),
            "status": status,
            "committee": committee,
            "priority": determine_priority(title),
            "topic": determine_topic(title),
            "introducedDate": introduced_date,
            "lastUpdated": data.get('lastActionDate', datetime.now().isoformat()),
            "legUrl": f"{BASE_WEB_URL}/billsummary?BillNumber={number}&Year={CURRENT_YEAR}",
            "hearings": [],
            "biennium": biennium
        }
        
        # Add companions if present
        if 'companions' in data:
            bill['companions'] = data['companions']
        
        return bill
        
    except Exception as e:
        print(f"    Error processing bill data: {e}")
        return None

def fetch_session_cutoff_calendar() -> Dict:
    """
    Fetch session cutoff dates to determine bill status
    """
    try:
        api_url = f"{BASE_API_URL}/LegislativeDocumentService/v1/biennium/{BIENNIUM}/cutoffs"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            return response.json()
    except:
        pass
    
    # Return default cutoff dates
    return {
        "firstReading": "2026-01-26",
        "committeePassed": "2026-02-07",
        "oppositeChamber": "2026-02-28",
        "sessionEnd": "2026-03-12"
    }

def determine_committee_from_type(bill_type: str) -> str:
    """Determine committee based on bill type"""
    if bill_type.startswith('H'):
        return "House Rules"
    elif bill_type.startswith('S'):
        return "Senate Rules"
    return "Rules"

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

def determine_topic(title: str) -> str:
    """Determine bill topic from title"""
    if not title:
        return "General Government"
    
    title_lower = title.lower()
    
    topic_map = {
        "Education": ["education", "school", "student", "teacher"],
        "Tax & Revenue": ["tax", "revenue", "budget", "fiscal"],
        "Housing": ["housing", "rent", "tenant", "landlord"],
        "Healthcare": ["health", "medical", "hospital", "mental"],
        "Environment": ["environment", "climate", "energy", "pollution"],
        "Transportation": ["transport", "road", "highway", "transit"],
        "Public Safety": ["crime", "safety", "police", "justice"],
        "Business": ["business", "commerce", "trade", "economy"],
        "Technology": ["technology", "internet", "data", "privacy"],
        "Agriculture": ["agriculture", "farm", "rural", "livestock"]
    }
    
    for topic, keywords in topic_map.items():
        if any(keyword in title_lower for keyword in keywords):
            return topic
    
    return "General Government"

def fetch_active_bills_rss() -> List[Dict]:
    """
    Fetch recently active bills from RSS feed
    """
    bills = []
    
    try:
        # WA Legislature provides RSS feeds for bill activity
        rss_url = f"{BASE_WEB_URL}/rss/bills.aspx?year={CURRENT_YEAR}"
        
        response = requests.get(rss_url, timeout=10)
        if response.status_code == 200:
            # Parse RSS (simplified - in production use feedparser library)
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)
            
            for item in root.findall('.//item'):
                title = item.findtext('title', '')
                link = item.findtext('link', '')
                
                # Extract bill number from title
                match = re.search(r'([A-Z]+)\s+(\d+)', title)
                if match:
                    bill_type, number = match.groups()
                    
                    # Create basic bill object
                    bill = {
                        "id": f"{bill_type}{number}",
                        "number": f"{bill_type} {number}",
                        "title": title.split('-', 1)[1].strip() if '-' in title else title,
                        "sponsor": "Unknown",
                        "description": "",
                        "status": "Active",
                        "committee": determine_committee_from_type(bill_type),
                        "priority": "medium",
                        "topic": "General Government",
                        "introducedDate": "",
                        "lastUpdated": datetime.now().isoformat(),
                        "legUrl": link,
                        "hearings": [],
                        "biennium": BIENNIUM
                    }
                    bills.append(bill)
                    
            print(f"  Found {len(bills)} bills from RSS feed")
    except Exception as e:
        print(f"  Error fetching RSS feed: {e}")
    
    return bills

def main():
    """Main execution function"""
    print(f"🚀 Washington State Legislature Bill Fetcher")
    print(f"📅 Biennium: {BIENNIUM} | Current Year: {CURRENT_YEAR}")
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    ensure_data_dir()
    
    # Fetch bills from multiple sources
    all_bills = {}
    
    # 1. Try REST API
    rest_bills = fetch_bills_via_rest()
    for bill in rest_bills:
        all_bills[bill['id']] = bill
    
    # 2. Try RSS feed for recent activity
    if len(all_bills) < 10:
        rss_bills = fetch_active_bills_rss()
        for bill in rss_bills:
            if bill['id'] not in all_bills:
                all_bills[bill['id']] = bill
    
    # Convert to list
    bills_list = list(all_bills.values())
    
    # Sort bills
    def sort_key(bill):
        match = re.match(r'([A-Z]+)\s*(\d+)', bill['number'])
        if match:
            return (match.group(1), int(match.group(2)))
        return (bill['number'], 0)
    
    bills_list.sort(key=sort_key)
    
    # Save data
    data = {
        "lastSync": datetime.now().isoformat(),
        "sessionYear": CURRENT_YEAR,
        "sessionStart": "2026-01-12",
        "sessionEnd": "2026-03-12",
        "totalBills": len(bills_list),
        "bills": bills_list,
        "metadata": {
            "source": "Washington State Legislature API",
            "apiVersion": "1.0",
            "updateFrequency": "hourly",
            "dataVersion": "4.0.0",
            "biennium": BIENNIUM,
            "note": "Live data from official API - no sample data"
        }
    }
    
    # Save to file
    data_file = DATA_DIR / "bills.json"
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Create empty data if no bills found
    if len(bills_list) == 0:
        print("\n⚠️  No bills retrieved from API")
        print("   The legislature may not have data available yet.")
        print("   Session starts: January 12, 2026")
        
        # Save empty structure
        data["bills"] = []
        data["metadata"]["note"] = "No bills available from API yet"
        
        with open(data_file, 'w') as f:
            json.dump(data, f, indent=2)
    else:
        print(f"\n✅ Successfully fetched {len(bills_list)} bills")
    
    # Create stats file
    stats = {
        "generated": datetime.now().isoformat(),
        "totalBills": len(bills_list),
        "byStatus": {},
        "byCommittee": {},
        "byPriority": {},
        "byTopic": {},
        "biennium": BIENNIUM
    }
    
    for bill in bills_list:
        status = bill.get('status', 'Unknown')
        stats['byStatus'][status] = stats['byStatus'].get(status, 0) + 1
        
        committee = bill.get('committee', 'Unknown')
        stats['byCommittee'][committee] = stats['byCommittee'].get(committee, 0) + 1
        
        priority = bill.get('priority', 'medium')
        stats['byPriority'][priority] = stats['byPriority'].get(priority, 0) + 1
        
        topic = bill.get('topic', 'General Government')
        stats['byTopic'][topic] = stats['byTopic'].get(topic, 0) + 1
    
    stats_file = DATA_DIR / "stats.json"
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2)
    
    # Create sync log
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "status": "success" if len(bills_list) > 0 else "no_data",
        "billsCount": len(bills_list),
        "biennium": BIENNIUM
    }
    
    log_file = DATA_DIR / "sync-log.json"
    logs = []
    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
                existing = json.load(f)
                logs = existing.get('logs', [])
        except:
            pass
    
    logs.insert(0, log_entry)
    logs = logs[:100]
    
    with open(log_file, 'w') as f:
        json.dump({"logs": logs}, f, indent=2)
    
    print("\n" + "=" * 60)
    print(f"📊 Summary:")
    print(f"   - Total bills: {len(bills_list)}")
    print(f"   - Data saved to: {data_file}")
    print(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()

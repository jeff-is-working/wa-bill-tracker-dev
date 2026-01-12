#!/usr/bin/env python3
"""
Washington State Legislature Bill Fetcher
Fetches bill data and updates JSON files for GitHub Pages
"""

import json
import requests
from datetime import datetime, timedelta
import os
from pathlib import Path

# Configuration
BASE_URL = "https://app.leg.wa.gov"
YEAR = 2026
DATA_DIR = Path("data")

def ensure_data_dir():
    """Ensure data directory exists"""
    DATA_DIR.mkdir(exist_ok=True)

def fetch_bills_list():
    """
    Fetch list of bills from WA Legislature
    Note: This is a simplified example. The actual API endpoints would need to be confirmed.
    """
    bills = []
    
    # Example data structure - would be replaced with actual API calls
    # In production, you would need to register for API access at https://app.leg.wa.gov/
    
    try:
        # This would be the actual API call
        # response = requests.get(f"{BASE_URL}/bi/api/bills", params={"year": YEAR})
        # bills_data = response.json()
        
        # For now, we'll maintain the existing data structure
        existing_data = load_existing_data()
        if existing_data:
            bills = existing_data.get('bills', [])
        
        # Add some sample updates to demonstrate functionality
        sample_bills = [
            {
                "id": "SB5872",
                "number": "SB 5872",
                "title": "Early Childhood Education and Assistance Program Account",
                "sponsor": "Sen. Claire Wilson",
                "description": "Establishes account for private funds to support ECEAP, funding up to 10,000 additional school day slots for 10 years",
                "status": "prefiled",
                "committee": "Education",
                "priority": "high",
                "topic": "Education",
                "introducedDate": "2026-01-08",
                "lastUpdated": datetime.now().isoformat(),
                "legUrl": f"{BASE_URL}/billsummary?BillNumber=5872&Year={YEAR}",
                "hearings": [
                    {"date": "2026-01-15", "time": "10:00 AM", "committee": "Education"}
                ]
            },
            {
                "id": "HB2225",
                "number": "HB 2225",
                "title": "Regulating Artificial Intelligence Companion Chatbots",
                "sponsor": "Rep. Lisa Callan",
                "description": "Requires AI chatbot developers to implement protocols for detecting self-harm/suicidal ideation, with protections for minors",
                "status": "prefiled",
                "committee": "Consumer Protection & Business",
                "priority": "high",
                "topic": "Technology",
                "introducedDate": "2026-01-09",
                "lastUpdated": datetime.now().isoformat(),
                "legUrl": f"{BASE_URL}/billsummary?BillNumber=2225&Year={YEAR}",
                "hearings": []
            },
            {
                "id": "HB2090",
                "number": "HB 2090",
                "title": "Advanced Nuclear Energy Integration",
                "sponsor": "Rep. Stephanie Barnard",
                "description": "Integrates advanced nuclear energy into state energy strategy, requires Commerce to develop nuclear framework by Dec 2026",
                "status": "committee",
                "committee": "Environment & Energy",
                "priority": "high",
                "topic": "Energy",
                "introducedDate": "2026-01-07",
                "lastUpdated": datetime.now().isoformat(),
                "legUrl": f"{BASE_URL}/billsummary?BillNumber=2090&Year={YEAR}",
                "hearings": [
                    {"date": "2026-01-18", "time": "1:30 PM", "committee": "Environment & Energy"}
                ]
            },
            {
                "id": "SB6026",
                "number": "SB 6026",
                "title": "Changing Commercial Zoning to Support Housing",
                "sponsor": "Sen. Emily Alvarado",
                "description": "Requires local governments to update land use policies under GMA to allow more housing in commercial zones",
                "status": "introduced",
                "committee": "Housing",
                "priority": "high",
                "topic": "Housing",
                "introducedDate": "2026-01-10",
                "lastUpdated": datetime.now().isoformat(),
                "legUrl": f"{BASE_URL}/billsummary?BillNumber=6026&Year={YEAR}",
                "hearings": []
            },
            {
                "id": "HB1921",
                "number": "HB 1921",
                "title": "Transportation Revenue from Road Usage",
                "sponsor": "Rep. Fey, Ramel, Wylie, Ormsby",
                "description": "Establishing new sources of transportation revenue based on motor vehicle use of public roadways",
                "status": "introduced",
                "committee": "Transportation",
                "priority": "high",
                "topic": "Transportation",
                "introducedDate": "2026-01-06",
                "lastUpdated": datetime.now().isoformat(),
                "legUrl": f"{BASE_URL}/billsummary?BillNumber=1921&Year={YEAR}",
                "hearings": [
                    {"date": "2026-01-20", "time": "3:30 PM", "committee": "Transportation"}
                ]
            },
            {
                "id": "HB2147",
                "number": "HB 2147",
                "title": "School Materials and Supplies Funding Increase",
                "sponsor": "Rep. Mia Gregerson",
                "description": "Increases state funding for school materials/supplies by $100 per FTE student, adjusted annually for inflation",
                "status": "prefiled",
                "committee": "Education",
                "priority": "high",
                "topic": "Education",
                "introducedDate": "2026-01-11",
                "lastUpdated": datetime.now().isoformat(),
                "legUrl": f"{BASE_URL}/billsummary?BillNumber=2147&Year={YEAR}",
                "hearings": []
            },
            {
                "id": "SB5853",
                "number": "SB 5853",
                "title": "Protecting Elected Officials from Political Violence",
                "sponsor": "Sen. Jeff Wilson",
                "description": "Enhanced protections for elected officials from political violence and threats",
                "status": "prefiled",
                "committee": "Law & Justice",
                "priority": "medium",
                "topic": "Public Safety",
                "introducedDate": "2026-01-10",
                "lastUpdated": datetime.now().isoformat(),
                "legUrl": f"{BASE_URL}/billsummary?BillNumber=5853&Year={YEAR}",
                "hearings": []
            }
        ]
        
        # Merge with existing bills (in production, this would be from API)
        existing_ids = {bill['id'] for bill in bills}
        for new_bill in sample_bills:
            if new_bill['id'] not in existing_ids:
                bills.append(new_bill)
            else:
                # Update existing bill
                for i, bill in enumerate(bills):
                    if bill['id'] == new_bill['id']:
                        bills[i] = new_bill
                        break
        
    except Exception as e:
        print(f"Error fetching bills: {e}")
        # Return existing data if fetch fails
        return bills
    
    return bills

def load_existing_data():
    """Load existing bills data if it exists"""
    data_file = DATA_DIR / "bills.json"
    if data_file.exists():
        with open(data_file, 'r') as f:
            return json.load(f)
    return None

def save_bills_data(bills):
    """Save bills data to JSON file"""
    data = {
        "lastSync": datetime.now().isoformat(),
        "sessionYear": YEAR,
        "sessionStart": "2026-01-12",
        "sessionEnd": "2026-03-12",
        "totalBills": len(bills),
        "bills": bills,
        "metadata": {
            "source": "Washington State Legislature",
            "updateFrequency": "daily",
            "dataVersion": "1.0.0"
        }
    }
    
    data_file = DATA_DIR / "bills.json"
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved {len(bills)} bills to {data_file}")
    return data

def create_sync_log(bills_count, status="success"):
    """Create sync log for monitoring"""
    log = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "billsCount": bills_count,
        "nextSync": (datetime.now() + timedelta(days=1)).isoformat()
    }
    
    log_file = DATA_DIR / "sync-log.json"
    
    # Load existing logs
    logs = []
    if log_file.exists():
        with open(log_file, 'r') as f:
            data = json.load(f)
            logs = data.get('logs', [])
    
    # Add new log entry (keep last 30 entries)
    logs.insert(0, log)
    logs = logs[:30]
    
    # Save logs
    with open(log_file, 'w') as f:
        json.dump({"logs": logs}, f, indent=2)
    
    print(f"📝 Sync log updated: {status}")

def create_stats_file(bills):
    """Create statistics file for dashboard"""
    stats = {
        "generated": datetime.now().isoformat(),
        "totalBills": len(bills),
        "byStatus": {},
        "byCommittee": {},
        "byPriority": {},
        "byTopic": {},
        "recentlyUpdated": 0,
        "upcomingHearings": 0
    }
    
    # Calculate statistics
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
        
        # Recently updated (within 24 hours)
        try:
            last_updated = datetime.fromisoformat(bill.get('lastUpdated', ''))
            if (datetime.now() - last_updated).days < 1:
                stats['recentlyUpdated'] += 1
        except:
            pass
        
        # Upcoming hearings (within 7 days)
        for hearing in bill.get('hearings', []):
            try:
                hearing_date = datetime.strptime(hearing['date'], '%Y-%m-%d')
                if 0 <= (hearing_date - datetime.now()).days <= 7:
                    stats['upcomingHearings'] += 1
            except:
                pass
    
    stats_file = DATA_DIR / "stats.json"
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f"📊 Statistics file updated")

def main():
    """Main execution function"""
    print(f"🚀 Starting WA Legislature Bill Fetcher - {datetime.now()}")
    
    # Ensure data directory exists
    ensure_data_dir()
    
    # Fetch bills
    print("📥 Fetching bills data...")
    bills = fetch_bills_list()
    
    if bills:
        # Save bills data
        save_bills_data(bills)
        
        # Create statistics
        create_stats_file(bills)
        
        # Create sync log
        create_sync_log(len(bills), "success")
        
        print(f"✅ Successfully updated {len(bills)} bills")
    else:
        print("❌ No bills data fetched")
        create_sync_log(0, "failed")
    
    print("🏁 Update complete!")

if __name__ == "__main__":
    main()
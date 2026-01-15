#!/usr/bin/env python3
"""
Test script for WA Legislature API integration
Run this to debug and verify bill fetching
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import json
import sys

def test_api_endpoints():
    """Test all API endpoints for connectivity"""
    print("=" * 60)
    print("TESTING API ENDPOINTS")
    print("=" * 60)
    
    endpoints = [
        ("Legislation Service", "https://wslwebservices.leg.wa.gov/LegislationService.asmx"),
        ("Committee Service", "https://wslwebservices.leg.wa.gov/CommitteeService.asmx"),
        ("Committee Meeting Service", "https://wslwebservices.leg.wa.gov/CommitteeMeetingService.asmx"),
    ]
    
    all_success = True
    for name, url in endpoints:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                print(f"[OK] {name}: {url}")
            else:
                print(f"[FAIL] {name}: Status {response.status_code}")
                all_success = False
        except Exception as e:
            print(f"[ERROR] {name}: {e}")
            all_success = False
    
    return all_success

def test_simple_soap_request():
    """Test a simple SOAP request to get sponsors"""
    print("\n" + "=" * 60)
    print("TESTING SIMPLE SOAP REQUEST (GetSponsors)")
    print("=" * 60)
    
    url = "https://wslwebservices.leg.wa.gov/LegislationService.asmx"
    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': 'http://WSLWebServices.leg.wa.gov/GetSponsors'
    }
    
    soap_body = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
               xmlns:xsd="http://www.w3.org/2001/XMLSchema" 
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetSponsors xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>2025-26</biennium>
    </GetSponsors>
  </soap:Body>
</soap:Envelope>"""
    
    try:
        response = requests.post(url, data=soap_body, headers=headers, timeout=30)
        print(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            # Save response for debugging
            with open('test_sponsors_response.xml', 'w', encoding='utf-8') as f:
                f.write(response.text)
            print("Response saved to: test_sponsors_response.xml")
            
            # Try to parse
            root = ET.fromstring(response.content)
            
            # Count sponsor elements
            sponsors = root.findall('.//{http://WSLWebServices.leg.wa.gov/}SponsorInfo')
            if not sponsors:
                sponsors = root.findall('.//SponsorInfo')
            
            print(f"Found {len(sponsors)} sponsors")
            
            if sponsors:
                print("\nSample sponsors:")
                for sponsor in sponsors[:5]:
                    name = sponsor.find('.//Name')
                    if name is None:
                        name = sponsor.find('Name')
                    if name is not None and name.text:
                        print(f"  - {name.text}")
                return True
            else:
                print("No sponsors found in response")
                print("Response preview:", response.text[:500])
        else:
            print(f"Error response: {response.text[:500]}")
            
    except Exception as e:
        print(f"Error: {e}")
    
    return False

def test_get_legislation_by_year():
    """Test fetching legislation for current year"""
    print("\n" + "=" * 60)
    print("TESTING GetLegislationByYear (2026)")
    print("=" * 60)
    
    url = "https://wslwebservices.leg.wa.gov/LegislationService.asmx"
    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': 'http://WSLWebServices.leg.wa.gov/GetLegislationByYear'
    }
    
    soap_body = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
               xmlns:xsd="http://www.w3.org/2001/XMLSchema" 
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetLegislationByYear xmlns="http://WSLWebServices.leg.wa.gov/">
      <year>2026</year>
    </GetLegislationByYear>
  </soap:Body>
</soap:Envelope>"""
    
    try:
        print("Making request...")
        response = requests.post(url, data=soap_body, headers=headers, timeout=60)
        print(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            # Save response
            with open('test_legislation_response.xml', 'w', encoding='utf-8') as f:
                f.write(response.text)
            print("Response saved to: test_legislation_response.xml")
            
            # Parse and analyze
            root = ET.fromstring(response.content)
            
            # Try multiple patterns to find legislation
            patterns = [
                './/{http://WSLWebServices.leg.wa.gov/}LegislationInfo',
                './/LegislationInfo',
                './/{http://WSLWebServices.leg.wa.gov/}ArrayOfLegislationInfo/*',
                './/GetLegislationByYearResult//*',
                './/*[local-name()="LegislationInfo"]'
            ]
            
            bills_found = False
            for pattern in patterns:
                bills = root.findall(pattern)
                if bills:
                    print(f"\nFound {len(bills)} bills using pattern: {pattern}")
                    bills_found = True
                    
                    # Show sample bills
                    print("\nSample bills:")
                    for bill in bills[:5]:
                        # Try to extract bill info
                        bill_num = bill.find('.//BillNumber')
                        if bill_num is None:
                            bill_num = bill.find('BillNumber')
                        
                        title = bill.find('.//ShortDescription')
                        if title is None:
                            title = bill.find('ShortDescription')
                        
                        if bill_num is not None and bill_num.text:
                            bill_text = f"  - Bill {bill_num.text}"
                            if title is not None and title.text:
                                bill_text += f": {title.text[:60]}..."
                            print(bill_text)
                    break
            
            if not bills_found:
                print("\nNo bills found with standard patterns")
                print("Checking raw XML structure...")
                
                # Check if there's any content
                if "LegislationInfo" in response.text:
                    print("LegislationInfo elements exist in response")
                    
                    # Count occurrences
                    count = response.text.count("<LegislationInfo")
                    print(f"Found {count} LegislationInfo elements in raw text")
                    
                    # Try regex extraction
                    import re
                    bills = re.findall(r'<BillNumber>(.*?)</BillNumber>', response.text)
                    if bills:
                        print(f"\nExtracted {len(bills)} bill numbers via regex:")
                        for bill in bills[:10]:
                            print(f"  - {bill}")
                else:
                    print("No LegislationInfo elements in response")
                    print("\nResponse structure preview:")
                    print(response.text[:1000])
            
            return bills_found
            
        else:
            print(f"Error response: {response.text[:500]}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    return False

def test_prefiled_legislation():
    """Test fetching prefiled legislation"""
    print("\n" + "=" * 60)
    print("TESTING GetPrefiledLegislationInfo")
    print("=" * 60)
    
    url = "https://wslwebservices.leg.wa.gov/LegislationService.asmx"
    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': 'http://WSLWebServices.leg.wa.gov/GetPrefiledLegislationInfo'
    }
    
    soap_body = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
               xmlns:xsd="http://www.w3.org/2001/XMLSchema" 
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetPrefiledLegislationInfo xmlns="http://WSLWebServices.leg.wa.gov/">
      <biennium>2025-26</biennium>
    </GetPrefiledLegislationInfo>
  </soap:Body>
</soap:Envelope>"""
    
    try:
        print("Making request...")
        response = requests.post(url, data=soap_body, headers=headers, timeout=60)
        print(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            # Save response
            with open('test_prefiled_response.xml', 'w', encoding='utf-8') as f:
                f.write(response.text)
            print("Response saved to: test_prefiled_response.xml")
            
            # Quick check for content
            if "LegislationInfo" in response.text:
                count = response.text.count("<LegislationInfo")
                print(f"Found {count} LegislationInfo elements")
                
                # Extract some bill numbers
                import re
                bills = re.findall(r'<BillNumber>(.*?)</BillNumber>', response.text)
                if bills:
                    print(f"\nFound {len(bills)} bill numbers")
                    print("Sample bills:", bills[:10])
                    return True
            else:
                print("No LegislationInfo found in response")
                
        else:
            print(f"Error: {response.status_code}")
            
    except Exception as e:
        print(f"Error: {e}")
    
    return False

def analyze_saved_responses():
    """Analyze any saved XML response files"""
    print("\n" + "=" * 60)
    print("ANALYZING SAVED RESPONSES")
    print("=" * 60)
    
    import os
    import glob
    
    xml_files = glob.glob("*.xml")
    
    if not xml_files:
        print("No XML files found in current directory")
        return
    
    for filename in xml_files:
        print(f"\nAnalyzing: {filename}")
        print("-" * 40)
        
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Basic stats
            print(f"File size: {len(content)} bytes")
            
            # Check for legislation elements
            if "LegislationInfo" in content:
                count = content.count("<LegislationInfo")
                print(f"LegislationInfo elements: {count}")
                
                # Extract bill numbers
                import re
                bills = re.findall(r'<BillNumber>(.*?)</BillNumber>', content)
                titles = re.findall(r'<ShortDescription>(.*?)</ShortDescription>', content)
                
                print(f"Bill numbers found: {len(bills)}")
                print(f"Titles found: {len(titles)}")
                
                if bills:
                    print("\nFirst 5 bills:")
                    for i, bill in enumerate(bills[:5]):
                        title = titles[i] if i < len(titles) else "No title"
                        print(f"  {bill}: {title[:60]}...")
            else:
                print("No LegislationInfo found")
                
                # Check what we do have
                if "soap:Fault" in content:
                    print("SOAP Fault detected - there was an error")
                    fault = re.search(r'<faultstring>(.*?)</faultstring>', content)
                    if fault:
                        print(f"Error: {fault.group(1)}")
                        
        except Exception as e:
            print(f"Error analyzing {filename}: {e}")

def main():
    """Run all tests"""
    print("WA LEGISLATURE API TEST SUITE")
    print("=" * 60)
    print(f"Test started: {datetime.now()}")
    print("\n")
    
    results = []
    
    # Test 1: API Connectivity
    result = test_api_endpoints()
    results.append(("API Connectivity", result))
    
    # Test 2: Simple SOAP Request
    result = test_simple_soap_request()
    results.append(("Simple SOAP Request", result))
    
    # Test 3: Get Legislation by Year
    result = test_get_legislation_by_year()
    results.append(("Get Legislation by Year", result))
    
    # Test 4: Get Prefiled Legislation
    result = test_prefiled_legislation()
    results.append(("Get Prefiled Legislation", result))
    
    # Analyze saved responses
    analyze_saved_responses()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, success in results:
        status = "PASSED" if success else "FAILED"
        symbol = "✓" if success else "✗"
        print(f"{symbol} {test_name}: {status}")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed < total:
        print("\nRECOMMENDATIONS:")
        print("1. Check the saved XML files for response structure")
        print("2. Verify the API endpoints are currently available")
        print("3. Check if the biennium/year parameters are correct")
        print("4. Review the SOAP envelope format in the saved request files")
        sys.exit(1)
    else:
        print("\nAll tests passed! The API integration is working correctly.")
        sys.exit(0)

if __name__ == "__main__":
    main()

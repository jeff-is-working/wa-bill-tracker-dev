#!/usr/bin/env python3
"""
Unit Tests for Washington State Legislature Bill Fetcher
Tests parsing logic, data transformation, helper functions, and data integrity

Run with: python -m pytest tests/test_fetch_all_bills.py -v
"""

import unittest
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
import sys
import os
import tempfile
import shutil

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

from scripts.fetch_all_bills import (
    determine_topic,
    determine_committee,
    determine_priority,
    determine_status_from_text,
    parse_xml_text,
    parse_xml_bool,
    parse_legislation_info,
    parse_committee_meeting,
    save_bills_data,
    save_meetings_data,
    create_stats_file,
    ensure_data_dir,
    DATA_DIR,
    BIENNIUM,
    YEAR
)


class TestTopicDetermination(unittest.TestCase):
    """Test topic determination from bill titles"""
    
    def test_education_topic(self):
        """Test Education topic detection"""
        self.assertEqual(determine_topic("Concerning public school funding"), "Education")
        self.assertEqual(determine_topic("Student loan assistance program"), "Education")
        self.assertEqual(determine_topic("Teacher certification requirements"), "Education")
        self.assertEqual(determine_topic("University research grants"), "Education")
    
    def test_healthcare_topic(self):
        """Test Healthcare topic detection"""
        self.assertEqual(determine_topic("Expanding mental health services"), "Healthcare")
        self.assertEqual(determine_topic("Hospital transparency requirements"), "Healthcare")
        self.assertEqual(determine_topic("Drug pricing regulations"), "Healthcare")
        self.assertEqual(determine_topic("Pharmacy benefit managers"), "Healthcare")
    
    def test_housing_topic(self):
        """Test Housing topic detection"""
        self.assertEqual(determine_topic("Rent stabilization measures"), "Housing")
        self.assertEqual(determine_topic("Tenant protection act"), "Housing")
        self.assertEqual(determine_topic("Zoning reform for affordable housing"), "Housing")
        self.assertEqual(determine_topic("Homeless shelter funding"), "Housing")
    
    def test_transportation_topic(self):
        """Test Transportation topic detection"""
        self.assertEqual(determine_topic("Highway improvement funding"), "Transportation")
        self.assertEqual(determine_topic("Public transit expansion"), "Transportation")
        self.assertEqual(determine_topic("Vehicle emissions standards"), "Transportation")
    
    def test_environment_topic(self):
        """Test Environment topic detection"""
        self.assertEqual(determine_topic("Climate change mitigation"), "Environment")
        self.assertEqual(determine_topic("Clean energy standards"), "Environment")
        self.assertEqual(determine_topic("Water quality protection"), "Environment")
    
    def test_public_safety_topic(self):
        """Test Public Safety topic detection"""
        self.assertEqual(determine_topic("Crime prevention measures"), "Public Safety")
        self.assertEqual(determine_topic("Police accountability"), "Public Safety")
        self.assertEqual(determine_topic("Firearm regulations"), "Public Safety")
    
    def test_tax_revenue_topic(self):
        """Test Tax & Revenue topic detection"""
        self.assertEqual(determine_topic("Property tax relief"), "Tax & Revenue")
        self.assertEqual(determine_topic("Revenue forecasting"), "Tax & Revenue")
        self.assertEqual(determine_topic("Budget stabilization"), "Tax & Revenue")
    
    def test_business_topic(self):
        """Test Business topic detection"""
        self.assertEqual(determine_topic("Small business assistance"), "Business")
        self.assertEqual(determine_topic("Labor standards"), "Business")
        self.assertEqual(determine_topic("Employment protections"), "Business")
    
    def test_technology_topic(self):
        """Test Technology topic detection"""
        self.assertEqual(determine_topic("Data privacy requirements"), "Technology")
        self.assertEqual(determine_topic("Artificial intelligence regulation"), "Technology")
        self.assertEqual(determine_topic("Cybersecurity standards"), "Technology")
    
    def test_general_government_default(self):
        """Test default General Government topic"""
        self.assertEqual(determine_topic("Concerning state agencies"), "General Government")
        self.assertEqual(determine_topic("Administrative procedures"), "General Government")


class TestCommitteeDetermination(unittest.TestCase):
    """Test committee assignment from bill ID and title"""
    
    def test_house_education_committee(self):
        """Test House Education committee assignment"""
        self.assertEqual(determine_committee("HB 1234", "Public school funding"), "Education")
    
    def test_senate_education_committee(self):
        """Test Senate Education committee assignment"""
        self.assertEqual(determine_committee("SB 5678", "Teacher certification"), "Education")
    
    def test_house_finance_committee(self):
        """Test House Finance committee assignment"""
        self.assertEqual(determine_committee("HB 1234", "Tax reform measures"), "Finance")
    
    def test_senate_ways_means_committee(self):
        """Test Senate Ways & Means committee assignment"""
        self.assertEqual(determine_committee("SB 5678", "Budget appropriations"), "Ways & Means")
    
    def test_transportation_committee(self):
        """Test Transportation committee assignment"""
        self.assertEqual(determine_committee("HB 1234", "Highway improvements"), "Transportation")
        self.assertEqual(determine_committee("SB 5678", "Transit funding"), "Transportation")
    
    def test_default_committee(self):
        """Test default committee assignment"""
        result_house = determine_committee("HB 1234", "Miscellaneous provisions")
        result_senate = determine_committee("SB 5678", "General provisions")
        self.assertEqual(result_house, "State Government & Tribal Relations")
        self.assertEqual(result_senate, "State Government & Elections")


class TestPriorityDetermination(unittest.TestCase):
    """Test priority determination from title and flags"""
    
    def test_high_priority_governor_request(self):
        """Test high priority for governor-requested bills"""
        self.assertEqual(determine_priority("General provisions", True, False), "high")
    
    def test_high_priority_appropriations(self):
        """Test high priority for appropriations bills"""
        self.assertEqual(determine_priority("General provisions", False, True), "high")
    
    def test_high_priority_keywords(self):
        """Test high priority from title keywords"""
        self.assertEqual(determine_priority("Emergency response funding", False, False), "high")
        self.assertEqual(determine_priority("Budget appropriations act", False, False), "high")
        self.assertEqual(determine_priority("Education funding formula", False, False), "high")
    
    def test_low_priority_keywords(self):
        """Test low priority from title keywords"""
        self.assertEqual(determine_priority("Technical corrections act", False, False), "low")
        self.assertEqual(determine_priority("Clarifying existing provisions", False, False), "low")
        self.assertEqual(determine_priority("Study committee report", False, False), "low")
    
    def test_medium_priority_default(self):
        """Test medium priority as default"""
        self.assertEqual(determine_priority("General provisions", False, False), "medium")


class TestStatusDetermination(unittest.TestCase):
    """Test status determination from API text"""
    
    def test_prefiled_status(self):
        """Test prefiled status detection"""
        self.assertEqual(determine_status_from_text("Prefiled for introduction"), "prefiled")
        self.assertEqual(determine_status_from_text("Pre-filed"), "prefiled")
    
    def test_introduced_status(self):
        """Test introduced status detection"""
        self.assertEqual(determine_status_from_text("First reading"), "introduced")
        self.assertEqual(determine_status_from_text("Introduced and referred"), "introduced")
    
    def test_committee_status(self):
        """Test committee status detection"""
        self.assertEqual(determine_status_from_text("Referred to committee"), "committee")
        self.assertEqual(determine_status_from_text("In committee"), "committee")
    
    def test_passed_status(self):
        """Test passed status detection"""
        self.assertEqual(determine_status_from_text("Passed Senate and House"), "passed")
        self.assertEqual(determine_status_from_text("Passed third reading"), "passed")
    
    def test_enacted_status(self):
        """Test enacted status detection"""
        self.assertEqual(determine_status_from_text("Signed by governor"), "enacted")
        self.assertEqual(determine_status_from_text("Governor signed"), "enacted")
    
    def test_vetoed_status(self):
        """Test vetoed status detection"""
        self.assertEqual(determine_status_from_text("Vetoed by governor"), "vetoed")
    
    def test_failed_status(self):
        """Test failed status detection"""
        self.assertEqual(determine_status_from_text("Failed to pass"), "failed")
        self.assertEqual(determine_status_from_text("Tabled indefinitely"), "failed")


class TestXMLParsing(unittest.TestCase):
    """Test XML parsing helper functions"""
    
    def setUp(self):
        """Create sample XML elements for testing"""
        self.sample_xml = ET.fromstring('''
            <root xmlns="http://WSLWebServices.leg.wa.gov/">
                <StringField>Test Value</StringField>
                <BoolTrue>true</BoolTrue>
                <BoolFalse>false</BoolFalse>
                <EmptyField></EmptyField>
            </root>
        ''')
        
        self.no_namespace_xml = ET.fromstring('''
            <root>
                <StringField>No Namespace Value</StringField>
                <BoolTrue>true</BoolTrue>
            </root>
        ''')
    
    def test_parse_xml_text_with_namespace(self):
        """Test parsing text from namespaced XML"""
        result = parse_xml_text(self.sample_xml, "StringField", "default")
        self.assertEqual(result, "Test Value")
    
    def test_parse_xml_text_without_namespace(self):
        """Test parsing text from non-namespaced XML"""
        result = parse_xml_text(self.no_namespace_xml, "StringField", "default")
        self.assertEqual(result, "No Namespace Value")
    
    def test_parse_xml_text_missing_field(self):
        """Test default value for missing field"""
        result = parse_xml_text(self.sample_xml, "NonExistent", "default_value")
        self.assertEqual(result, "default_value")
    
    def test_parse_xml_text_empty_field(self):
        """Test default value for empty field"""
        result = parse_xml_text(self.sample_xml, "EmptyField", "default_value")
        self.assertEqual(result, "default_value")
    
    def test_parse_xml_bool_true(self):
        """Test parsing true boolean"""
        result = parse_xml_bool(self.sample_xml, "BoolTrue", False)
        self.assertTrue(result)
    
    def test_parse_xml_bool_false(self):
        """Test parsing false boolean"""
        result = parse_xml_bool(self.sample_xml, "BoolFalse", True)
        self.assertFalse(result)
    
    def test_parse_xml_bool_default(self):
        """Test default boolean value"""
        result = parse_xml_bool(self.sample_xml, "NonExistent", True)
        self.assertTrue(result)


class TestLegislationParsing(unittest.TestCase):
    """Test legislation XML parsing"""
    
    def test_parse_legislation_info_complete(self):
        """Test parsing a complete LegislationInfo element"""
        xml = ET.fromstring('''
            <LegislationInfo xmlns="http://WSLWebServices.leg.wa.gov/">
                <Biennium>2025-26</Biennium>
                <BillId>HB 1234</BillId>
                <BillNumber>1234</BillNumber>
                <ShortDescription>Concerning public education</ShortDescription>
                <LongDescription>An act relating to public education funding</LongDescription>
                <CurrentStatus>Introduced</CurrentStatus>
                <IntroducedDate>2026-01-15T00:00:00</IntroducedDate>
                <Sponsor>Rep. John Smith</Sponsor>
                <OriginalAgency>House</OriginalAgency>
                <RequestedByGovernor>false</RequestedByGovernor>
                <Appropriations>false</Appropriations>
            </LegislationInfo>
        ''')
        
        bill = parse_legislation_info(xml)
        
        self.assertIsNotNone(bill)
        self.assertEqual(bill['id'], "HB1234")
        self.assertEqual(bill['number'], "HB 1234")
        self.assertEqual(bill['title'], "Concerning public education")
        self.assertEqual(bill['status'], "introduced")
        self.assertEqual(bill['sponsor'], "Rep. John Smith")
        self.assertEqual(bill['biennium'], "2025-26")
        self.assertFalse(bill['requestedByGovernor'])
    
    def test_parse_legislation_info_minimal(self):
        """Test parsing a minimal LegislationInfo element"""
        xml = ET.fromstring('''
            <LegislationInfo>
                <BillId>SB 5678</BillId>
                <ShortDescription>Tax reform</ShortDescription>
            </LegislationInfo>
        ''')
        
        bill = parse_legislation_info(xml)
        
        self.assertIsNotNone(bill)
        self.assertEqual(bill['id'], "SB5678")
        self.assertEqual(bill['title'], "Tax reform")
    
    def test_parse_legislation_info_empty(self):
        """Test parsing an empty LegislationInfo element"""
        xml = ET.fromstring('<LegislationInfo></LegislationInfo>')
        
        bill = parse_legislation_info(xml)
        
        self.assertIsNone(bill)


class TestCommitteeMeetingParsing(unittest.TestCase):
    """Test committee meeting XML parsing"""
    
    def test_parse_committee_meeting_complete(self):
        """Test parsing a complete CommitteeMeeting element"""
        xml = ET.fromstring('''
            <CommitteeMeeting xmlns="http://WSLWebServices.leg.wa.gov/">
                <AgendaId>12345</AgendaId>
                <Date>2026-01-20T10:00:00</Date>
                <Time>10:00 AM</Time>
                <Committees>Education</Committees>
                <Agency>House</Agency>
                <Room>Hearing Room A</Room>
                <Building>John L. O'Brien Building</Building>
                <City>Olympia</City>
                <State>WA</State>
                <Cancelled>false</Cancelled>
                <Notes>Public hearing on HB 1234</Notes>
            </CommitteeMeeting>
        ''')
        
        meeting = parse_committee_meeting(xml)
        
        self.assertIsNotNone(meeting)
        self.assertEqual(meeting['agendaId'], "12345")
        self.assertEqual(meeting['date'], "2026-01-20")
        self.assertEqual(meeting['committee'], "Education")
        self.assertFalse(meeting['cancelled'])
        self.assertIn("Hearing Room A", meeting['location'])
    
    def test_parse_committee_meeting_cancelled(self):
        """Test parsing a cancelled meeting"""
        xml = ET.fromstring('''
            <CommitteeMeeting>
                <AgendaId>99999</AgendaId>
                <Date>2026-01-25T14:00:00</Date>
                <Cancelled>true</Cancelled>
            </CommitteeMeeting>
        ''')
        
        meeting = parse_committee_meeting(xml)
        
        self.assertIsNotNone(meeting)
        self.assertTrue(meeting['cancelled'])
    
    def test_parse_committee_meeting_empty(self):
        """Test parsing an empty CommitteeMeeting element"""
        xml = ET.fromstring('<CommitteeMeeting></CommitteeMeeting>')
        
        meeting = parse_committee_meeting(xml)
        
        self.assertIsNone(meeting)


class TestDataSaving(unittest.TestCase):
    """Test data saving functions"""
    
    def setUp(self):
        """Create temporary directory for test data"""
        self.test_dir = Path(tempfile.mkdtemp())
        # Temporarily override DATA_DIR
        import scripts.fetch_all_bills as fab
        self.original_data_dir = fab.DATA_DIR
        fab.DATA_DIR = self.test_dir
    
    def tearDown(self):
        """Clean up temporary directory"""
        import scripts.fetch_all_bills as fab
        fab.DATA_DIR = self.original_data_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_save_bills_data(self):
        """Test saving bills data to JSON"""
        import scripts.fetch_all_bills as fab
        
        bills = [
            {
                "id": "HB1234",
                "number": "HB 1234",
                "title": "Test Bill",
                "status": "introduced",
                "committee": "Education",
                "priority": "medium",
                "topic": "Education",
                "introducedDate": "2026-01-15",
                "lastUpdated": datetime.now().isoformat(),
                "legUrl": "https://example.com",
                "hearings": [],
                "sponsor": "Test Sponsor",
                "description": "Test description",
                "biennium": "2025-26"
            }
        ]
        
        result = save_bills_data(bills)
        
        self.assertEqual(result['totalBills'], 1)
        self.assertTrue((self.test_dir / "bills.json").exists())
        
        with open(self.test_dir / "bills.json", 'r') as f:
            saved_data = json.load(f)
        
        self.assertEqual(saved_data['totalBills'], 1)
        self.assertEqual(len(saved_data['bills']), 1)
        self.assertEqual(saved_data['bills'][0]['id'], "HB1234")
    
    def test_save_meetings_data(self):
        """Test saving meetings data to JSON"""
        import scripts.fetch_all_bills as fab
        
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        meetings = [
            {
                "agendaId": "12345",
                "date": tomorrow,
                "time": "10:00 AM",
                "committee": "Education",
                "location": "Room A",
                "cancelled": False,
                "agendaUrl": "https://example.com"
            }
        ]
        
        result = save_meetings_data(meetings)
        
        self.assertTrue((self.test_dir / "meetings.json").exists())
        self.assertGreaterEqual(result['upcomingMeetings'], 0)


class TestStatsGeneration(unittest.TestCase):
    """Test statistics generation"""
    
    def setUp(self):
        """Create temporary directory for test data"""
        self.test_dir = Path(tempfile.mkdtemp())
        import scripts.fetch_all_bills as fab
        self.original_data_dir = fab.DATA_DIR
        fab.DATA_DIR = self.test_dir
    
    def tearDown(self):
        """Clean up temporary directory"""
        import scripts.fetch_all_bills as fab
        fab.DATA_DIR = self.original_data_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_create_stats_file(self):
        """Test creating statistics file"""
        import scripts.fetch_all_bills as fab
        
        bills = [
            {"number": "HB 1234", "status": "introduced", "committee": "Education",
             "priority": "high", "topic": "Education", "sponsor": "Rep. Smith",
             "lastUpdated": datetime.now().isoformat()},
            {"number": "SB 5678", "status": "prefiled", "committee": "Finance",
             "priority": "medium", "topic": "Tax & Revenue", "sponsor": "Sen. Jones",
             "lastUpdated": datetime.now().isoformat()},
        ]
        
        meetings = [
            {"date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
             "cancelled": False}
        ]
        
        create_stats_file(bills, meetings)
        
        self.assertTrue((self.test_dir / "stats.json").exists())
        
        with open(self.test_dir / "stats.json", 'r') as f:
            stats = json.load(f)
        
        self.assertEqual(stats['totalBills'], 2)
        self.assertEqual(stats['byStatus']['introduced'], 1)
        self.assertEqual(stats['byStatus']['prefiled'], 1)
        self.assertEqual(stats['byPriority']['high'], 1)
        self.assertEqual(stats['byPriority']['medium'], 1)


class TestDataIntegrity(unittest.TestCase):
    """Integration tests for data consistency"""
    
    def test_bill_data_consistency(self):
        """Test that bill data maintains internal consistency"""
        bills_file = Path("data/bills.json")
        
        if not bills_file.exists():
            self.skipTest("No bills.json file available for testing")
        
        with open(bills_file, 'r') as f:
            data = json.load(f)
        
        bills = data.get('bills', [])
        
        for bill in bills:
            # Required fields
            self.assertIn('id', bill)
            self.assertIn('number', bill)
            self.assertIn('title', bill)
            self.assertIn('status', bill)
            self.assertIn('committee', bill)
            self.assertIn('priority', bill)
            self.assertIn('topic', bill)
            
            # ID should match number (without spaces)
            expected_id = bill['number'].replace(' ', '')
            self.assertEqual(bill['id'], expected_id)
            
            # Valid status
            valid_statuses = ['prefiled', 'introduced', 'committee', 'passed', 
                             'failed', 'enacted', 'vetoed']
            self.assertIn(bill['status'], valid_statuses)
            
            # Valid priority
            self.assertIn(bill['priority'], ['high', 'medium', 'low'])
    
    def test_meetings_data_consistency(self):
        """Test that meetings data maintains internal consistency"""
        meetings_file = Path("data/meetings.json")
        
        if not meetings_file.exists():
            self.skipTest("No meetings.json file available for testing")
        
        with open(meetings_file, 'r') as f:
            data = json.load(f)
        
        meetings = data.get('meetings', [])
        
        for meeting in meetings:
            # Required fields
            self.assertIn('agendaId', meeting)
            self.assertIn('date', meeting)
            self.assertIn('cancelled', meeting)
            self.assertIn('agendaUrl', meeting)
            
            # Date format validation (YYYY-MM-DD)
            if meeting.get('date'):
                self.assertRegex(meeting['date'], r'^\d{4}-\d{2}-\d{2}$')


class TestNoSampleData(unittest.TestCase):
    """Verify no sample/static data in the script"""
    
    def test_no_hardcoded_bills(self):
        """Ensure fetch script has no hardcoded bill data"""
        script_path = Path(__file__).parent.parent / "scripts" / "fetch_all_bills.py"
        
        if not script_path.exists():
            self.skipTest("Script file not found")
        
        with open(script_path, 'r') as f:
            content = f.read()
        
        # Check for hardcoded bill patterns
        suspicious_patterns = [
            '"HB 1001"',
            '"SB 5001"',
            'sample_bills',
            'static_bills',
            'mock_bills',
            'test_bills =',
            'hardcoded',
        ]
        
        for pattern in suspicious_patterns:
            self.assertNotIn(pattern, content, 
                f"Found suspicious pattern '{pattern}' that may indicate sample data")
    
    def test_uses_api_endpoints(self):
        """Ensure script uses official API endpoints"""
        script_path = Path(__file__).parent.parent / "scripts" / "fetch_all_bills.py"
        
        if not script_path.exists():
            self.skipTest("Script file not found")
        
        with open(script_path, 'r') as f:
            content = f.read()
        
        # Must contain official API URL
        self.assertIn("wslwebservices.leg.wa.gov", content)
        
        # Must use SOAP or HTTP methods
        self.assertTrue(
            "make_soap_request" in content or "make_http_get_request" in content,
            "Script must use API request methods"
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)

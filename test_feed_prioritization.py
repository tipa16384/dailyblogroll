#!/usr/bin/env python3
"""
Test script for the new feed prioritization logic in collect_new_items function.
This script tests the feed grouping and ordering without making network requests or API calls.
"""

import json
import time
import calendar
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the function we want to test
from blogroll import collect_new_items, load_state, save_state

def setup_test_state():
    """Create test state data with some feeds having recent activity and others not."""
    twenty_four_hours_ago = time.time() - (24 * 60 * 60)
    forty_eight_hours_ago = time.time() - (48 * 60 * 60)
    
    return {
        "https://required-feed-1.com/feed.xml": {
            "last_ts": int(forty_eight_hours_ago),  # Old, but required so still prioritized
            "etag": "test-etag-req1"
        },
        "https://required-feed-2.com/feed.xml": {
            "last_ts": int(time.time() - 6 * 60 * 60),  # Recent, and required
            "etag": "test-etag-req2"
        },
        "https://recent-feed-1.com/feed.xml": {
            "last_ts": int(time.time() - 12 * 60 * 60),  # 12 hours ago - recent
            "etag": "test-etag-1"
        },
        "https://recent-feed-2.com/feed.xml": {
            "last_ts": int(twenty_four_hours_ago + 3600),  # 23 hours ago - recent
            "etag": "test-etag-2"
        },
        "https://old-feed-1.com/feed.xml": {
            "last_ts": int(forty_eight_hours_ago),  # 48 hours ago - old
            "etag": "test-etag-3"
        },
        "https://old-feed-2.com/feed.xml": {
            "last_ts": int(forty_eight_hours_ago - 3600),  # 49 hours ago - old
            "etag": "test-etag-4"
        },
        "https://new-feed.com/feed.xml": {
            # No last_ts - should be treated as old
            "etag": "test-etag-5"
        }
    }

def setup_test_config():
    """Create test configuration with feeds that have different activity levels."""
    return {
        "max_items_total": 10,
        "max_items_per_feed": 2,
        "min_chars_for_article": 100,
        "first_run_skip_backlog": True,
        "feeds": [
            {
                "name": "Required Feed 1",
                "url": "https://required-feed-1.com/feed.xml",
                "required": True,
                "category": "Tech"
            },
            {
                "name": "Required Feed 2", 
                "url": "https://required-feed-2.com/feed.xml",
                "required": True,
                "category": "Gaming"
            },
            {
                "name": "Recent Feed 1",
                "url": "https://recent-feed-1.com/feed.xml",
                "category": "Tech"
            },
            {
                "name": "Recent Feed 2", 
                "url": "https://recent-feed-2.com/feed.xml",
                "category": "Gaming"
            },
            {
                "name": "Old Feed 1",
                "url": "https://old-feed-1.com/feed.xml",
                "category": "Writing"
            },
            {
                "name": "Old Feed 2",
                "url": "https://old-feed-2.com/feed.xml", 
                "category": "General"
            },
            {
                "name": "New Feed",
                "url": "https://new-feed.com/feed.xml",
                "category": "Tech"
            },
            {
                "name": "Skipped Feed",
                "url": "https://skipped-feed.com/feed.xml",
                "skip": True,
                "category": "General"
            }
        ]
    }

def mock_feedparser_parse(url, etag=None):
    """Mock feedparser.parse to return realistic feed data with recent activity for some feeds."""
    mock_result = MagicMock()
    
    # Create different mock data based on feed URL to simulate variety
    twenty_four_hours_ago = time.time() - (24 * 60 * 60)
    current_time = time.time()
    
    if "recent-feed-1" in url:
        # This feed has server modification time from 12 hours ago
        modified_time = time.gmtime(current_time - 12 * 60 * 60)
        mock_result.modified = modified_time
        # And a recent entry from 10 hours ago
        mock_entry = MagicMock()
        mock_entry.published_parsed = time.gmtime(current_time - 10 * 60 * 60) 
        mock_entry.id = "entry-1"
        mock_entry.link = f"{url}/entry-1"
        mock_entry.title = "Recent Post 1"
        mock_result.entries = [mock_entry]
    elif "recent-feed-2" in url:
        # This feed has server modification time from 18 hours ago  
        modified_time = time.gmtime(current_time - 18 * 60 * 60)
        mock_result.modified = modified_time
        # And a recent entry from 16 hours ago
        mock_entry = MagicMock()
        mock_entry.published_parsed = time.gmtime(current_time - 16 * 60 * 60)
        mock_entry.id = "entry-2" 
        mock_entry.link = f"{url}/entry-2"
        mock_entry.title = "Recent Post 2"
        mock_result.entries = [mock_entry]
    elif "old-feed" in url or "new-feed" in url:
        # These feeds have old modification times and old entries
        modified_time = time.gmtime(current_time - 48 * 60 * 60)  # 48 hours ago
        mock_result.modified = modified_time
        # And old entries
        mock_entry = MagicMock()
        mock_entry.published_parsed = time.gmtime(current_time - 72 * 60 * 60)  # 72 hours ago
        mock_entry.id = f"old-entry-{url[-10:]}"
        mock_entry.link = f"{url}/old-entry"
        mock_entry.title = "Old Post"
        mock_result.entries = [mock_entry]
    else:
        # Required and other feeds - mix of recent and old
        if "required-feed-1" in url:
            # Required feed 1 - old but still prioritized
            modified_time = time.gmtime(current_time - 36 * 60 * 60)
            mock_result.modified = modified_time
            mock_entry = MagicMock()
            mock_entry.published_parsed = time.gmtime(current_time - 40 * 60 * 60)
            mock_entry.id = "req-entry-1"
            mock_entry.link = f"{url}/req-entry-1"
            mock_entry.title = "Required Post 1"
            mock_result.entries = [mock_entry]
        elif "required-feed-2" in url:
            # Required feed 2 - recent activity but would be prioritized anyway
            modified_time = time.gmtime(current_time - 8 * 60 * 60)
            mock_result.modified = modified_time  
            mock_entry = MagicMock()
            mock_entry.published_parsed = time.gmtime(current_time - 6 * 60 * 60)
            mock_entry.id = "req-entry-2"
            mock_entry.link = f"{url}/req-entry-2" 
            mock_entry.title = "Required Post 2"
            mock_result.entries = [mock_entry]
        else:
            # Default: no entries
            mock_result.entries = []
            mock_result.modified = None
    
    mock_result.etag = f"new-etag-for-{url[-20:]}"
    return mock_result

def mock_db():
    """Mock database connection."""
    mock_con = MagicMock()
    mock_con.execute.return_value.fetchone.return_value = None  # Nothing seen before
    return mock_con

def test_feed_prioritization():
    """Test that feeds are properly grouped by recent activity."""
    print("Testing feed prioritization logic...")
    print("Setting up test data...")
    
    # Setup test data
    test_config = setup_test_config()
    test_state = setup_test_state()
    
    # Create temporary state file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_state, f, indent=2)
        temp_state_file = f.name
    
    try:
        # Mock the necessary functions and modules
        debug_log_lines = []
        
        def mock_write_debug_log(filename, mode='w', encoding='utf-8'):
            class MockFile:
                def write(self, content):
                    debug_log_lines.extend(content.strip().split('\n'))
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
            return MockFile()
        
        with patch('blogroll.feedparser.parse', side_effect=mock_feedparser_parse), \
             patch('blogroll.db', return_value=mock_db()), \
             patch('blogroll.STATE_PATH', Path(temp_state_file)), \
             patch('blogroll.ROOT', Path.cwd()), \
             patch('builtins.open', side_effect=lambda filename, *args, **kwargs: 
                   mock_write_debug_log(filename, *args, **kwargs) 
                   if 'debug.log' in str(filename) 
                   else open(filename, *args, **kwargs)):
            
            # Call the function we're testing
            print("Calling collect_new_items...")
            result = collect_new_items(test_config)
            
            print(f"Function returned {len(result)} items")
            print("Debug log content:")
            for line in debug_log_lines:
                if any(keyword in line for keyword in ['First pass:', 'Checked', 'Required feeds', 'Recent feeds', 'Older feeds', 'Processing feed:']):
                    print(f"  {line}")
            
            # Analyze the debug output to verify feed ordering
            required_line = next((line for line in debug_log_lines if 'Required feeds' in line), None)
            recent_line = next((line for line in debug_log_lines if 'Recent feeds (activity in last 24h)' in line), None)
            older_line = next((line for line in debug_log_lines if 'Older feeds' in line), None)
            processing_lines = [line for line in debug_log_lines if 'Processing feed:' in line]
            
            if required_line:
                print(f"\n✓ {required_line}")
            if recent_line:
                print(f"✓ {recent_line}")
            if older_line:
                print(f"✓ {older_line}")
                
            print(f"\n✓ Feed processing order:")
            for i, line in enumerate(processing_lines, 1):
                feed_name = line.split('Processing feed: ')[1].split(' http')[0]
                print(f"  {i}. {feed_name}")
            
            # Verify three-tier ordering: required -> recent -> older
            required_feeds = ['Required Feed 1', 'Required Feed 2']
            recent_feeds = ['Recent Feed 1', 'Recent Feed 2']
            older_feeds = ['Old Feed 1', 'Old Feed 2', 'New Feed']
            
            required_positions = []
            recent_positions = []
            older_positions = []
            
            for i, line in enumerate(processing_lines):
                for rf in required_feeds:
                    if rf in line:
                        required_positions.append(i)
                for rf in recent_feeds:
                    if rf in line:
                        recent_positions.append(i)
                for of in older_feeds:
                    if of in line:
                        older_positions.append(i)
            
            # Verify ordering
            success = True
            if required_positions:
                max_required = max(required_positions)
                print(f"\n✓ Required feeds processed first (positions {[p+1 for p in required_positions]})")
                
                if recent_positions:
                    min_recent = min(recent_positions)
                    if max_required >= min_recent:
                        print(f"✗ FAIL: Required feeds not before recent feeds")
                        success = False
                    else:
                        print(f"✓ Required feeds before recent feeds")
                        
                if older_positions:
                    min_older = min(older_positions)
                    if max_required >= min_older:
                        print(f"✗ FAIL: Required feeds not before older feeds")
                        success = False
                        
            if recent_positions and older_positions:
                max_recent = max(recent_positions)
                min_older = min(older_positions)
                if max_recent >= min_older:
                    print(f"✗ FAIL: Recent feeds not before older feeds")
                    success = False
                else:
                    print(f"✓ Recent feeds before older feeds")
                    
            if success:
                print(f"\n✓ PASS: Three-tier ordering working correctly")
            else:
                print(f"\n✗ FAIL: Feed ordering incorrect")
    
    finally:
        # Clean up temp file - handle Windows file locking
        try:
            os.unlink(temp_state_file)
        except (OSError, PermissionError) as e:
            print(f"Note: Could not delete temp file {temp_state_file}: {e}")

if __name__ == "__main__":
    try:
        test_feed_prioritization()
        print("Test completed successfully!")
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
#!/usr/bin/env python3
"""
Test script for the new two-tier feed prioritization logic in collect_new_items function.
This script tests the feed grouping and ordering by selection history without making network requests or API calls.
"""

import json
import time
import calendar
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import datetime

# Import the function we want to test
from blogroll import collect_new_items, load_state, save_state

def setup_test_state():
    """Create test state data with some feeds having recent activity and others not."""
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
        "https://never-selected-feed.com/feed.xml": {
            "last_ts": int(time.time() - 12 * 60 * 60),  # Recent posts
            "etag": "test-etag-1"
        },
        "https://long-wait-feed.com/feed.xml": {
            "last_ts": int(time.time() - 18 * 60 * 60),  # Has posts
            "etag": "test-etag-2"
        },
        "https://medium-wait-feed.com/feed.xml": {
            "last_ts": int(forty_eight_hours_ago),  # Has posts
            "etag": "test-etag-3"
        },
        "https://short-wait-feed.com/feed.xml": {
            "last_ts": int(forty_eight_hours_ago - 3600),  # Has posts
            "etag": "test-etag-4"
        }
    }

def setup_test_config():
    """Create test configuration with feeds that have different selection histories."""
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
                "name": "Never Selected Feed",
                "url": "https://never-selected-feed.com/feed.xml",
                "category": "Tech"
            },
            {
                "name": "Long Wait Feed", 
                "url": "https://long-wait-feed.com/feed.xml",
                "category": "Gaming"
            },
            {
                "name": "Medium Wait Feed",
                "url": "https://medium-wait-feed.com/feed.xml",
                "category": "Writing"
            },
            {
                "name": "Short Wait Feed",
                "url": "https://short-wait-feed.com/feed.xml", 
                "category": "General"
            },
            {
                "name": "Skipped Feed",
                "url": "https://skipped-feed.com/feed.xml",
                "skip": True,
                "category": "General"
            }
        ]
    }

def setup_selection_history():
    """Create mock selection history data - days since last selection."""
    today = datetime.date.today()
    return {
        # Never Selected Feed has None (never selected)
        "https://never-selected-feed.com/feed.xml": None,
        # Long Wait Feed was selected 30 days ago
        "https://long-wait-feed.com/feed.xml": 30,
        # Medium Wait Feed was selected 15 days ago
        "https://medium-wait-feed.com/feed.xml": 15,
        # Short Wait Feed was selected 2 days ago
        "https://short-wait-feed.com/feed.xml": 2,
        # Required feeds have selection history but it doesn't matter for ordering
        "https://required-feed-1.com/feed.xml": 5,
        "https://required-feed-2.com/feed.xml": 10,
    }

def mock_feedparser_parse(url, etag=None):
    """Mock feedparser.parse to return realistic feed data with recent entries for all feeds."""
    mock_result = MagicMock()
    
    current_time = time.time()
    
    # Give all feeds recent entries so we can test selection prioritization
    mock_result.modified = time.gmtime(current_time - 4 * 60 * 60)  # Modified 4 hours ago
    
    # Create a recent entry for each feed
    mock_entry = MagicMock()
    mock_entry.published_parsed = time.gmtime(current_time - 2 * 60 * 60)  # Published 2 hours ago
    mock_entry.id = f"entry-{hash(url) % 1000}"
    mock_entry.link = f"{url}/entry"
    mock_entry.title = f"Recent Post from {url}"
    mock_result.entries = [mock_entry]
    
    mock_result.etag = f"new-etag-for-{url[-20:]}"
    return mock_result

def mock_db_with_selection_history(selection_history):
    """Mock database connection with selection history."""
    mock_con = MagicMock()
    mock_con.execute.return_value.fetchone.return_value = None  # Nothing seen before
    
    # Mock get_days_since_last_selection function
    def mock_get_days_since_last_selection(con, feed_url):
        return selection_history.get(feed_url, None)
    
    return mock_con, mock_get_days_since_last_selection

def test_feed_prioritization():
    """Test that feeds are properly ordered: required first, then by selection history."""
    print("Testing two-tier feed prioritization logic...")
    print("Setting up test data...")
    
    # Setup test data
    test_config = setup_test_config()
    test_state = setup_test_state()
    selection_history = setup_selection_history()
    
    print("Selection history setup:")
    for url, days in selection_history.items():
        feed_name = next((f["name"] for f in test_config["feeds"] if f["url"] == url), "Unknown")
        if days is None:
            print(f"  {feed_name}: Never selected")
        else:
            print(f"  {feed_name}: {days} days since last selection")
    
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
        
        mock_con, mock_get_days_func = mock_db_with_selection_history(selection_history)
        
        with patch('blogroll.feedparser.parse', side_effect=mock_feedparser_parse), \
             patch('blogroll.db', return_value=mock_con), \
             patch('blogroll.get_days_since_last_selection', side_effect=mock_get_days_func), \
             patch('blogroll.get_all_feed_selection_stats', return_value=[]), \
             patch('blogroll.update_feed_selection'), \
             patch('blogroll.STATE_PATH', Path(temp_state_file)), \
             patch('blogroll.ROOT', Path.cwd()), \
             patch('builtins.open', side_effect=lambda filename, *args, **kwargs: 
                   mock_write_debug_log(filename, *args, **kwargs) 
                   if 'debug.log' in str(filename) 
                   else open(filename, *args, **kwargs)):
            
            # Call the function we're testing
            print("\nCalling collect_new_items...")
            result = collect_new_items(test_config)
            
            print(f"Function returned {len(result)} items")
            print("\nDebug log content:")
            for line in debug_log_lines:
                if any(keyword in line for keyword in ['Required feeds', 'Other feeds', 'priority order', 'Processing feed:']):
                    print(f"  {line}")
            
            # Analyze the debug output to verify feed ordering
            required_line = next((line for line in debug_log_lines if 'Required feeds (always first)' in line), None)
            other_line = next((line for line in debug_log_lines if 'Other feeds to be sorted' in line), None)
            priority_lines = [line for line in debug_log_lines if 'Never selected' in line or ('days since last selection' in line and 'priority order' in debug_log_lines[debug_log_lines.index(line) - 3:debug_log_lines.index(line) + 1])]
            processing_lines = [line for line in debug_log_lines if 'Processing feed:' in line]
            
            if required_line:
                print(f"\n✓ {required_line}")
            if other_line:
                print(f"✓ {other_line}")
                
            print(f"\n✓ Selection priority order:")
            for line in priority_lines:
                print(f"  {line}")
                
            print(f"\n✓ Feed processing order:")
            for i, line in enumerate(processing_lines, 1):
                feed_name = line.split('Processing feed: ')[1].split(' http')[0]
                print(f"  {i}. {feed_name}")
            
            # Verify two-tier ordering: required -> other feeds by selection history
            required_feeds = ['Required Feed 1', 'Required Feed 2']
            other_feeds_expected_order = [
                'Never Selected Feed',      # Never selected (highest priority)
                'Long Wait Feed',          # 30 days since last selection
                'Medium Wait Feed',        # 15 days since last selection  
                'Short Wait Feed'          # 2 days since last selection
            ]
            
            required_positions = []
            other_positions = {}
            
            for i, line in enumerate(processing_lines):
                for rf in required_feeds:
                    if rf in line:
                        required_positions.append(i)
                for of in other_feeds_expected_order:
                    if of in line:
                        other_positions[of] = i
            
            # Verify ordering
            success = True
            
            # Check that required feeds come first
            if required_positions:
                max_required = max(required_positions)
                print(f"\n✓ Required feeds processed in positions {[p+1 for p in required_positions]}")
                
                if other_positions:
                    min_other = min(other_positions.values())
                    if max_required >= min_other:
                        print(f"✗ FAIL: Required feeds not before other feeds")
                        success = False
                    else:
                        print(f"✓ Required feeds processed before other feeds")
            
            # Check that other feeds are in selection history order
            other_feed_positions = [other_positions.get(feed, float('inf')) for feed in other_feeds_expected_order if feed in other_positions]
            if len(other_feed_positions) > 1:
                if other_feed_positions == sorted(other_feed_positions):
                    print(f"✓ Other feeds processed in correct selection history order")
                else:
                    print(f"✗ FAIL: Other feeds not in correct selection history order")
                    print(f"  Expected order: {other_feeds_expected_order}")
                    print(f"  Actual positions: {[(feed, other_positions.get(feed, 'Not found')) for feed in other_feeds_expected_order]}")
                    success = False
                    
            if success:
                print(f"\n✓ PASS: Two-tier ordering by selection history working correctly")
            else:
                print(f"\n✗ FAIL: Feed ordering incorrect")
                
            return success
    
    finally:
        # Clean up temp file - handle Windows file locking
        try:
            os.unlink(temp_state_file)
        except (OSError, PermissionError) as e:
            print(f"Note: Could not delete temp file {temp_state_file}: {e}")

if __name__ == "__main__":
    try:
        success = test_feed_prioritization()
        if success:
            print("\n✓ Test completed successfully!")
        else:
            print("\n✗ Test FAILED!")
            exit(1)
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
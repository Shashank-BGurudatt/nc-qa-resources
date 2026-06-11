#!/usr/bin/env python3
"""
App Provisioning Stats Analyzer
================================
Author: Manish Gupta
Contact: manish.gupta@nutanix.com

Description:
------------
Analyzes Nutanix app provisioning times from the Nutanix API and generates comprehensive
reports with detailed tables, graphs, and HTML visualizations. The script queries the
Nutanix API to fetch app information, calculates provisioning durations, and creates
visual representations of app start times and provisioning performance.

Logic:
------
1. API Connection:
   - Constructs API URL from hostname (format: https://ncm.services.<host>/api/nutanix/v3/apps/list)
   - Uses Basic Authentication with configurable credentials
   - Queries Nutanix API for app list (POST request)

2. App Filtering:
   - Supports two filtering modes:
     a) File-based: Exact match from CSV file (one app name per line)
     b) Regex-based: Pattern matching from command-line (simple strings auto-converted to regex)
   - Filters apps based on name matching

3. Data Extraction:
   - Extracts from each app entity:
     * App name (status.name)
     * Creation time (status.creation_time) - epoch microseconds
     * Last update time (status.last_update_time) - epoch microseconds
     * State (status.state) - e.g., "running", "error", "provisioning"
     * Blueprint UUID (status.uuid - the app's UUID)
     * Source marketplace name (resources.source_marketplace_name)
   - Calculates provisioning time: (last_update_time - creation_time) / 1,000,000 seconds
   - Validates timestamps and handles missing/invalid data gracefully

4. Time Formatting:
   - Converts epoch microseconds to IST (India Standard Time, UTC+5:30)
   - Formats timestamps as "YYYY-MM-DD HH:MM:SS IST"
   - Formats durations as human-readable (e.g., "2h 15m 30s", "45s", "12m")
   - Handles edge cases (sub-second durations, missing timestamps)

5. Report Generation:
   - CSV Table: Detailed table with all app information
   - HTML Report: Comprehensive report with:
     * Summary information
     * Summary breakdown by state (running, provisioning, error, unknown)
     * Pass % based on running apps only (Running / Total)
     * Provisioning time stats for running apps only (min, max, P95)
     * Detailed table with color-coded state (red for "error")
     * Graph 1: App Provisioning Start Times (interactive with hover tooltips)
     * Graph 2: Provisioning Time by App (horizontal bar chart, sorted)
   - PNG Images: Standalone graph images for reference

6. Graph Generation:
   - Graph 1 (Start Times):
     * Scatter plot: X-axis = start time, Y-axis = app names
     * Interactive version (if plotly available): Hover shows exact start time
     * Static version: PNG image embedded in HTML
     * Helps visualize if apps started simultaneously or over a period
   
   - Graph 2 (Provisioning Times):
     * Horizontal bar chart: X-axis = provisioning time, Y-axis = app names
     * Sorted by provisioning time (shortest to longest)
     * Color-coded: Above average (coral), below average (light blue)
     * Value labels on each bar
     * Helps identify fastest and slowest provisioning apps

7. Runlog Tree Building (Detailed Runbook/Task Execution Logs):
   - For each provisioned application, fetches detailed runbook and task execution logs
   - Two-step API process:
     a) First API Call: Fetches top-level entities
        * Endpoint: POST /api/calm/v3.0/apps/{app_uuid}/app_runlogs/list
        * Filter: application_reference=={app_uuid};(type==action_runlog,type==audit_runlog,...)
        * Returns: action_runlog, platform_sync_runlog entities
        * Extracts: metadata.uuid for each action_runlog
     
     b) Second API Call (for each action_runlog):
        * Endpoint: POST /api/calm/v3.0/apps/{app_uuid}/app_runlogs/list
        * Filter: root_reference=={action_runlog_uuid}
        * Returns: runbook_runlog, task_runlog, policy_runlog entities nested under the action
   
   - Tree Structure Building:
     * Variables:
       - node: Dictionary mapping UUID -> node data (id, type, names, timestamps, parent_uuid, root_uuid)
       - children: defaultdict mapping parent UUID -> list of child UUIDs
       - roots: defaultdict mapping root UUID -> list of root node UUIDs
     
     * Parent-Child Relationship Logic:
       1. action_runlog and platform_sync_runlog are roots (their own root)
       2. If node has parent_uuid that exists in node map → attach as child of parent
          (handles: runbook→runbook, runbook→task relationships)
       3. If node has no parent but root_uuid exists in map:
          - For runbook_runlog → attach as child of root (action_runlog)
          - For task_runlog → attach as child of root (fallback for orphaned tasks)
       4. Otherwise → make it its own root (fallback)
     
     * Tree Building Process:
       - build_json(nid): Recursively builds tree structure
         * Gets all children of node nid from children dictionary
         * Sorts children by creation_time (earliest first) to match UI order
         * Recursively builds each child's subtree
         * Returns node with 'children' array containing nested structure
       
       - Forest Building:
         * Groups nodes by root_action_runlog_uuid
         * Only includes action_runlog/platform_sync_runlog as actual roots
         * Creates forest structure: {root_action_runlog_uuid: uuid, nodes: [root_nodes]}
   
   - Data Extraction from JSON:
     * From metadata:
       - uuid: Node identifier
       - creation_time: Entity creation timestamp (epoch microseconds)
       - last_update_time: Entity last update timestamp (epoch microseconds)
     
     * From status:
       - type: Entity type (action_runlog, runbook_runlog, task_runlog, platform_sync_runlog, policy_runlog)
       - parent_reference.uuid: Immediate parent UUID
       - root_reference.uuid: Root action_runlog UUID
       - state: Execution state (SUCCESS, ERROR, ABORTING, etc.)
       - action_reference.name: Action name (for action_runlog)
       - runbook_reference.name: Runbook name (for runbook_runlog)
       - task_reference.name: Task name (for task_runlog)
       - element_type, element_name, machine_name, task_kind, e_task_type, exit_code: Task details
   
   - Duration Calculation:
     * Each entity has independent duration: (last_update_time - creation_time) / 1,000,000 seconds
     * action_runlog duration ≠ sum of child runbooks (they can run in parallel)
     * Example: Action (26m 2s) vs Runbook (21m 15s) - both are correct, independent durations
   
   - HTML Tree Rendering:
     * format_runlog_tree_html(): Formats tree as HTML table
       - Columns: Type | Name | Created (IST) | Last Updated (IST) | Duration | State
       - format_node_html(n, indent_level): Recursively formats nodes
         * indent_level=0: Action (root)
         * indent_level=1: Runbooks (children of action)
         * indent_level=2: Tasks (children of runbooks) or nested runbooks
         * indent_level=3+: Nested tasks or deeper nesting
       - Indentation: 20px per level (indent_padding = indent_level * 20)
       - Color coding: Green (SUCCESS), Red (ERROR), Orange (other states)
       - Expandable/collapsible rows in HTML table

8. Output Management:
   - Creates directory: "nutanix-calm-blueprint-results"
   - Saves all outputs in the directory:
     * <output>.csv
     * <output>.html (includes expandable runlog tree tables)
     * <output>_start_times.png
     * <output>_provisioning_times.png
     * <output>.log (console output captured during run)
   - Debug output is written to the log file only (not printed to console)

9. Logging & Debug:
   - Console output is duplicated to the log file
   - Debug logs are enabled by default and written only to the log file
   - Use --no-debug to suppress debug logging

Dependencies:
-------------
Required:
  - Python 3.6+
  - json (standard library)
  - ssl (standard library)
  - http.client (standard library)
  - argparse (standard library)
  - re (standard library)
  - csv (standard library)
  - base64 (standard library)
  - html (standard library)
  - io (standard library)
  - datetime (standard library)
  - collections (standard library)
  - pytz (timezone handling)
    Installation: pip install pytz
  - matplotlib (graph generation)
    Installation: pip install matplotlib

Optional:
  - plotly (interactive graphs with hover tooltips)
    Installation: pip install plotly
    Note: If not installed, script falls back to static matplotlib graphs

Usage:
------
  # Using file with app names (exact match)
  python3 update_stats.py --host nconprem-10-122-152-117.ccpnx.com --app-file ./log/app.csv
  
  # Using simple string (will match "lite" anywhere in app name)
  python3 update_stats.py --host nconprem-10-122-152-117.ccpnx.com --app-name lite
  
  # Using regex pattern
  python3 update_stats.py --host nconprem-10-122-152-117.ccpnx.com --app-name "foundation.*|multivm.*"
  
  # Custom authentication
  python3 update_stats.py --host nconprem-10-122-152-117.ccpnx.com --app-name lite --username admin --password Nutanix.123
  
  # Custom output prefix
  python3 update_stats.py --host nconprem-10-122-152-117.ccpnx.com --app-name lite --output ./reports/my_report

Arguments:
----------
  --host (required): Host URL (e.g., nconprem-10-122-152-117.ccpnx.com)
  --app-file: CSV file with app names for exact match (one per line)
  --app-name: String or regex pattern to match app names
  --username: Username for Basic Auth (default: ssp_admin@qa.nutanix.com)
  --password: Password for Basic Auth (default: nutanix/4u)
  --output: Output file prefix (default: 'provisioning_stats')

Output Files:
-------------
All files are saved in 'nutanix-calm-blueprint-results/' directory:
  - <output>.csv: CSV table with app provisioning details
  - <output>.html: HTML report with embedded graphs and table
  - <output>_start_times.png: Graph showing app start times
  - <output>_provisioning_times.png: Graph showing provisioning times

Notes:
------
- All timestamps are displayed in IST (India Standard Time, UTC+5:30)
- State column shows "error" in red/bold for failed provisioning
- Blueprint UUID is the app's UUID (status.uuid), used for fetching runlogs via API
- Graph 1 supports hover tooltips if plotly is installed (shows exact start time)
- Script handles missing/invalid data gracefully with warnings
- TLS certificate verification is disabled by default (uses unverified SSL context)
"""

import json
import ssl
import pytz
import http.client
import argparse
import re
import csv
import base64
import html
import io
import os
import sys
from datetime import datetime, time as dt_time, timezone
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from collections import defaultdict

class Tee:
    """Write output to multiple streams (console + log file)."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()

DEBUG_ENABLED = True
DEBUG_LOG_HANDLE = None

def debug_log(message):
    """Write debug messages only to the log file when enabled."""
    if not DEBUG_ENABLED or DEBUG_LOG_HANDLE is None:
        return
    msg = str(message)
    if not msg.endswith("\n"):
        msg += "\n"
    DEBUG_LOG_HANDLE.write(msg)
    DEBUG_LOG_HANDLE.flush()

# Try to import plotly for interactive graphs with hover
try:
    import plotly.graph_objects as go
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("[INFO] Plotly not available - hover tooltips will not be available. Install with: pip install plotly")

def build_api_url(host_url):
    """Build complete API URL from host."""
    if not host_url.startswith('http'):
        return f"https://ncm.services.{host_url}/api/nutanix/v3/apps/list"
    return f"{host_url}/api/nutanix/v3/apps/list"

def build_app_runlogs_url(host_url, blueprint_uuid):
    """Build app runlogs API URL for a blueprint UUID."""
    if not host_url.startswith('http'):
        base_url = f"https://ncm.services.{host_url}"
    else:
        base_url = host_url
    return f"{base_url}/api/calm/v3.0/apps/{blueprint_uuid}/app_runlogs/list"

def get_app_names_from_file(file_path):
    """Read app names from CSV file."""
    try:
        with open(file_path, 'r') as file:
            reader = csv.reader(file)
            return [row[0] for row in reader if row]
    except FileNotFoundError:
        return []

def create_basic_auth(username, password):
    """Create Basic Auth header value."""
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return encoded

def format_timestamp(epoch_microseconds):
    """Convert epoch microseconds to IST formatted string with timezone indicator.
    
    Args:
        epoch_microseconds: Unix timestamp in microseconds (e.g., 1763580604454895)
    
    Returns:
        Formatted string: "YYYY-MM-DD HH:MM:SS IST"
    """
    if not epoch_microseconds or epoch_microseconds <= 0:
        return "N/A"
    
    try:
        # Convert microseconds to seconds (preserve precision)
        epoch_seconds = epoch_microseconds / 1_000_000.0
        
        # Create UTC datetime from timestamp
        dt_utc = datetime.fromtimestamp(epoch_seconds, tz=pytz.utc)
        
        # Convert to IST (Asia/Kolkata)
        ist = pytz.timezone('Asia/Kolkata')
        dt_ist = dt_utc.astimezone(ist)
        
        # Format with timezone indicator for clarity
        return dt_ist.strftime("%Y-%m-%d %H:%M:%S IST")
    except (ValueError, OSError) as e:
        # Handle invalid timestamps gracefully
        return f"Invalid timestamp ({epoch_microseconds})"

def format_duration(seconds):
    """Format duration in seconds to unambiguous readable format.
    
    Args:
        seconds: Duration in seconds (float or int)
    
    Returns:
        Formatted string: "Xs", "Xm Ys", "Xh Ym", or "Xh Ym Zs"
        Always shows all non-zero components for clarity.
    """
    if seconds is None or seconds < 0:
        return "0s"
    
    seconds = float(seconds)
    
    # Handle very small durations (< 1 second)
    if seconds < 1:
        return f"{seconds:.3f}s"
    
    # Round to nearest second for display
    total_seconds = int(round(seconds))
    
    if total_seconds < 60:
        return f"{total_seconds}s"
    
    # Calculate hours, minutes, and remaining seconds
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    
    # Build format string with all non-zero components
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0:
        parts.append(f"{secs}s")
    
    # If somehow all are zero, return 0s
    if not parts:
        return "0s"
    
    return " ".join(parts)

def get_app_list(conn, headers, get_response_code=False):
    """Query Nutanix API for app list with pagination support.
    
    Fetches all apps by iterating through pages until all results are retrieved.
    The API supports pagination via 'offset' and 'length' parameters.
    
    Args:
        conn: HTTP connection object
        headers: HTTP headers with authentication
        get_response_code: If True, returns (data, status_code) tuple
    
    Returns:
        dict: Combined API response with all entities from all pages
        or tuple: (data, status_code) if get_response_code=True
    """
    all_entities = []
    offset = 0
    length = 250  # Fetch 250 apps per page
    total_matches = None
    page_num = 1
    max_pages = 1000  # Safety limit to prevent infinite loops (250 * 1000 = 250,000 apps max)
    
    print(f"[INFO] Fetching apps from API (pagination enabled)...")
    
    while page_num <= max_pages:
        # Build payload with pagination parameters
        payload = {
            "length": length,
            "offset": offset
        }
        
        # Make API request
        conn.request("POST", "/api/nutanix/v3/apps/list", json.dumps(payload), headers)
        res = conn.getresponse()
        data = res.read()
        status_code = res.status
        
        if status_code != 200:
            error_msg = f"API request failed with status {status_code}"
            if get_response_code:
                return json.loads(data) if data else {}, status_code
            print(f"[ERROR] {error_msg}")
            return json.loads(data) if data else {}
        
        result = json.loads(data)
        
        # Extract entities from this page
        page_entities = result.get("entities", [])
        if not page_entities:
            # No more entities, break the loop
            print(f"[INFO] Page {page_num}: No more entities found")
            break
        
        all_entities.extend(page_entities)
        print(f"[INFO] Page {page_num}: Fetched {len(page_entities)} apps (total so far: {len(all_entities)})")
        
        # Check metadata for pagination info
        metadata = result.get("metadata", {})
        if total_matches is None:
            total_matches = metadata.get("total_matches")
            if total_matches is not None:
                print(f"[INFO] Total apps available: {total_matches}")
        
        # Check if we've fetched all apps
        if total_matches is not None:
            if len(all_entities) >= total_matches:
                print(f"[INFO] Fetched all {len(all_entities)} apps (matched total_matches: {total_matches})")
                break
        
        # If this page returned fewer entities than requested, we've reached the end
        if len(page_entities) < length:
            print(f"[INFO] Last page reached (returned {len(page_entities)} < {length} requested)")
            break
        
        # Move to next page
        offset += length
        page_num += 1
    
    # Check if we hit the safety limit
    if page_num > max_pages:
        print(f"[WARNING] Reached maximum page limit ({max_pages}). Stopping pagination.")
        print(f"[WARNING] Fetched {len(all_entities)} apps, but there may be more available.")
    
    # Build combined response with all entities
    combined_result = {
        "entities": all_entities,
        "metadata": {
            "total_matches": len(all_entities) if total_matches is None else total_matches,
            "length": len(all_entities),
            "offset": 0
        }
    }
    
    print(f"[INFO] Successfully fetched {len(all_entities)} apps across {page_num} page(s)")
    
    if get_response_code:
        return combined_result, status_code
    return combined_result

def get_nested_runlogs(hostname, port, headers, blueprint_uuid, action_runlog_uuid):
    """Fetch nested runbook_runlog and task_runlog entities for a specific action_runlog.
    
    This function makes a second API call to fetch all runbooks and tasks that belong to
    a specific action_runlog. The filter uses root_reference to get all entities that
    have this action_runlog as their root.
    
    Args:
        hostname (str): Nutanix API hostname
        port (int): HTTPS port (usually 9440)
        headers (dict): HTTP headers with authentication
        blueprint_uuid (str): Application UUID (from status.uuid)
        action_runlog_uuid (str): Action runlog UUID (from metadata.uuid of action_runlog entity)
    
    Returns:
        list: List of entity dictionaries containing runbook_runlog and task_runlog entities
    
    API Details:
        - Endpoint: POST /api/calm/v3.0/apps/{blueprint_uuid}/app_runlogs/list
        - Filter: {"filter": "root_reference=={action_runlog_uuid}"}
        - Returns: All entities where root_reference.uuid matches action_runlog_uuid
    """
    try:
        conn = http.client.HTTPSConnection(
            host=hostname,
            port=port,
            context=ssl._create_unverified_context()
        )
        
        # Use exact filter format as specified: root_reference=={uuid}
        filter_payload = {
            "filter": f"root_reference=={action_runlog_uuid}"
        }
        
        api_path = f"/api/calm/v3.0/apps/{blueprint_uuid}/app_runlogs/list"
        conn.request("POST", api_path, json.dumps(filter_payload), headers)
        res = conn.getresponse()
        data = res.read()
        status_code = res.status
        conn.close()
        
        if status_code == 200:
            result = json.loads(data)
            entities = result.get("entities", [])
            if entities:
                entity_types = {}
                for entity in entities:
                    etype = entity.get("status", {}).get("type", "unknown")
                    entity_types[etype] = entity_types.get(etype, 0) + 1
                debug_log(f"[DEBUG] Found {len(entities)} nested runlogs for action_runlog {action_runlog_uuid}, types: {entity_types}")
                return entities
            else:
                debug_log(f"[DEBUG] No nested runlogs found for action_runlog {action_runlog_uuid}")
        else:
            print(f"[WARNING] Failed to fetch nested runlogs for action_runlog {action_runlog_uuid}, status: {status_code}")
        return []
    except Exception as e:
        print(f"[WARNING] Failed to fetch nested runlogs for action_runlog {action_runlog_uuid}: {e}")
        import traceback
        debug_log(f"[DEBUG] Traceback: {traceback.format_exc()}")
        return []

def get_app_runlogs(hostname, port, headers, blueprint_uuid):
    """Fetch app runlogs for a blueprint UUID using POST method.
    
    This function performs a two-step process:
    1. First API Call: Fetches top-level entities (action_runlog, platform_sync_runlog)
    2. Second API Call: For each action_runlog, fetches nested runbook/task runlogs
    
    Args:
        hostname (str): Nutanix API hostname
        port (int): HTTPS port (usually 9440)
        headers (dict): HTTP headers with authentication
        blueprint_uuid (str): Application UUID (from status.uuid, NOT blueprint_reference.uuid)
    
    Returns:
        dict: JSON response containing all entities (top-level + nested), or None on error
        dict: On error, returns dict with 'error' key containing error details:
              {'error': True, 'status_code': int, 'response': str, 'api_path': str, 'exception': str}
    
    Variables:
        - entities: List of entity dictionaries from first API call
        - action_runlog_uuids: List of UUIDs extracted from metadata.uuid of action_runlog entities
        - all_nested_entities: Combined list of all nested runbook/task runlogs from all actions
    
    API Details:
        First Call:
        - Endpoint: POST /api/calm/v3.0/apps/{blueprint_uuid}/app_runlogs/list
        - Filter: {"filter": "application_reference=={blueprint_uuid};(type==action_runlog,...)"}
        - Returns: action_runlog, platform_sync_runlog entities
        
        Second Call (for each action_runlog):
        - Calls get_nested_runlogs() for each action_runlog UUID
        - Merges all nested entities into the main result
    """
    try:
        conn = http.client.HTTPSConnection(
            host=hostname,
            port=port,
            context=ssl._create_unverified_context()
        )
        
        # Use exact format as specified: POST to /api/calm/v3.0/apps/{blueprint_uuid}/app_runlogs/list
        api_path = f"/api/calm/v3.0/apps/{blueprint_uuid}/app_runlogs/list"
        
        # Use exact filter format as specified
        filter_payload = {
            "filter": f"application_reference=={blueprint_uuid};(type==action_runlog,type==audit_runlog,type==ngt_runlog,type==clone_action_runlog,type==platform_sync_runlog,type==patch_runlog)"
        }
        
        conn.request("POST", api_path, json.dumps(filter_payload), headers)
        res = conn.getresponse()
        data = res.read()
        status_code = res.status
        conn.close()
        
        if status_code != 200:
            error_response = data.decode('utf-8', errors='ignore')[:500]  # Limit response size
            print(f"[WARNING] POST request failed with status {status_code} for {blueprint_uuid}")
            return {
                'error': True,
                'status_code': status_code,
                'response': error_response,
                'api_path': api_path,
                'api_method': 'POST',
                'api_payload': json.dumps(filter_payload),
                'exception': None
            }
        
        try:
            result = json.loads(data)
        except json.JSONDecodeError as e:
            error_response = data.decode('utf-8', errors='ignore')[:500]
            print(f"[WARNING] Failed to parse JSON response for {blueprint_uuid}: {e}")
            return {
                'error': True,
                'status_code': status_code,
                'response': error_response,
                'api_path': api_path,
                'api_method': 'POST',
                'api_payload': json.dumps(filter_payload),
                'exception': f'JSONDecodeError: {str(e)}'
            }
        
        entities = result.get("entities", [])
        
        if entities:
            debug_log(f"[DEBUG] Received {len(entities)} top-level entities for {blueprint_uuid}")
            # Log entity types for debugging
            entity_types = {}
            action_runlog_uuids = []
            for entity in entities:
                etype = entity.get("status", {}).get("type", "unknown")
                entity_types[etype] = entity_types.get(etype, 0) + 1
                # Collect action_runlog UUIDs from metadata.uuid (not status fields)
                if etype == "action_runlog":
                    action_uuid = entity.get("metadata", {}).get("uuid")
                    if action_uuid:
                        action_runlog_uuids.append(action_uuid)
                        debug_log(f"[DEBUG] Found action_runlog with UUID: {action_uuid}")
            
            if entity_types:
                debug_log(f"[DEBUG] Entity types: {entity_types}")
            
            # Fetch nested runbook_runlog and task_runlog for each action_runlog
            if action_runlog_uuids:
                debug_log(f"[DEBUG] Fetching nested runlogs for {len(action_runlog_uuids)} action_runlogs...")
                all_nested_entities = []
                for action_uuid in action_runlog_uuids:
                    nested_entities = get_nested_runlogs(hostname, port, headers, blueprint_uuid, action_uuid)
                    all_nested_entities.extend(nested_entities)
                
                if all_nested_entities:
                    debug_log(f"[DEBUG] Found {len(all_nested_entities)} nested runbook/task runlogs")
                    # Add nested entities to the result
                    entities.extend(all_nested_entities)
                    result["entities"] = entities
                    # Update metadata
                    if "metadata" in result:
                        result["metadata"]["total_matches"] = len(entities)
            
            return result
        else:
            print(f"[WARNING] POST returned no entities for {blueprint_uuid}")
            return {
                'error': True,
                'status_code': status_code,
                'response': 'No entities returned',
                'api_path': api_path,
                'api_method': 'POST',
                'api_payload': json.dumps(filter_payload),
                'exception': None
            }
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[WARNING] Failed to fetch runlogs for blueprint {blueprint_uuid}: {e}")
        debug_log(f"[DEBUG] Traceback: {error_trace}")
        api_path = f"/api/calm/v3.0/apps/{blueprint_uuid}/app_runlogs/list"
        return {
            'error': True,
            'status_code': None,
            'response': None,
            'api_path': api_path,
            'api_method': 'POST',
            'api_payload': f'application_reference=={blueprint_uuid};(type==action_runlog,...)',
            'exception': f'{type(e).__name__}: {str(e)}'
        }

def filter_apps_by_regex(apps, search_string):
    """Filter apps by regex pattern on name. Converts simple string to regex."""
    # If it's a simple string (no regex special chars), make it case-insensitive regex
    if not any(char in search_string for char in ['*', '+', '?', '^', '$', '[', ']', '(', ')', '{', '}', '|', '\\']):
        # Simple string - convert to case-insensitive regex that matches anywhere in name
        regex_pattern = f".*{re.escape(search_string)}.*"
    else:
        # User provided actual regex
        regex_pattern = search_string
    
    pattern = re.compile(regex_pattern, re.IGNORECASE)
    return [app for app in apps if pattern.search(app["status"]["name"])]

def filter_apps_by_list(apps, app_names):
    """Filter apps by exact name match from list."""
    app_names_set = set(app_names)
    return [app for app in apps if app["status"]["name"] in app_names_set]

def generate_table(data, output_file):
    """Generate CSV table with provisioning stats."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "App Name",
            "Creation Time (IST)",
            "Last Update Time (IST)",
            "Time to Provision",
            "State",
            "Blueprint UUID",
            "Source Marketplace Name"
        ])
        for row in data:
            writer.writerow(row)
    print(f"[INFO] Table written to: {output_file}")

def generate_html(data, output_file, host_url, custom_avg=None, runlogs_data=None, trend_analysis=None, total_provisioning_info=None, runlog_errors=None):
    """Generate HTML report with table and embedded graphs.
    
    Args:
        data: List of table rows
        output_file: Output HTML file path
        host_url: Host URL
        custom_avg: Custom average threshold
        runlogs_data: Dictionary mapping blueprint_uuid to parsed runlogs tree
        trend_analysis: Dict with runbook/task graph HTML and table HTML
        total_provisioning_info: Dict with total provisioning time info and summary stats across filtered apps
        runlog_errors: List of dicts with error details for failed runlog fetches
    """
    # Generate graphs as base64 images for embedding
    graph_results = generate_graphs(data, None, embed_in_html=True, custom_avg=custom_avg)
    if graph_results:
        start_times_img, provisioning_times_img, start_times_plotly_html = graph_results
    else:
        start_times_img, provisioning_times_img, start_times_plotly_html = None, None, None
    
    if runlogs_data is None:
        runlogs_data = {}
    
    # Extract trend analysis components
    runbook_graph_html = None
    task_graph_html = None
    runbook_table_html = None
    task_table_html = None
    
    if trend_analysis:
        runbook_graph_html = trend_analysis.get('runbook_graph_html')
        task_graph_html = trend_analysis.get('task_graph_html')
        runbook_table_html = trend_analysis.get('runbook_table_html')
        task_table_html = trend_analysis.get('task_table_html')
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>App Provisioning Stats Report</title>
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #e8ecf1 0%, #f5f7fa 100%);
            min-height: 100vh;
            line-height: 1.6;
            color: #333;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background-color: #ffffff;
            padding: 40px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15);
            border-radius: 8px;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 4px solid #7c9bc7;
            padding-bottom: 15px;
            margin-bottom: 30px;
            font-size: 2.2em;
            font-weight: 600;
            letter-spacing: -0.5px;
        }}
        h2 {{
            color: #2c3e50;
            margin-top: 50px;
            padding: 15px 20px;
            background: linear-gradient(135deg, #7c9bc7 0%, #9bb5d3 100%);
            color: white;
            border-radius: 6px;
            font-size: 1.5em;
            font-weight: 500;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .info {{
            background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
            padding: 20px;
            border-left: 5px solid #7c9bc7;
            margin: 25px 0;
            border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 25px 0;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border-radius: 8px;
            overflow: hidden;
        }}
        th {{
            background: linear-gradient(135deg, #7c9bc7 0%, #9bb5d3 100%);
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
            font-size: 0.95em;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}
        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #e8ecf1;
            font-size: 0.9em;
        }}
        tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}
        tr:hover {{
            background-color: #e8f4f8;
            transition: background-color 0.2s ease;
        }}
        .summary {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 25px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .summary h3 {{
            margin-top: 0;
            color: #2c3e50;
            font-weight: 600;
        }}
        .graph-container {{
            margin: 35px 0;
            text-align: center;
            background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        }}
        .graph-container p {{
            color: #555;
            font-size: 0.95em;
            margin: 10px 0;
        }}
        .graph-container strong {{
            color: #2c3e50;
        }}
        .graph-container img {{
            max-width: 100%;
            height: auto;
            border: 2px solid #e8ecf1;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            margin-top: 15px;
        }}
        a {{
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
        }}
        a:hover {{
            color: #764ba2;
            text-decoration: underline;
        }}
        .expandable-row {{
            cursor: pointer;
        }}
        .expand-icon {{
            display: inline-block;
            width: 20px;
            text-align: center;
            font-weight: bold;
            color: #7c9bc7;
            margin-right: 5px;
        }}
        .expand-icon:hover {{
            color: #5a7ba3;
        }}
        .runlog-details {{
            display: none;
            background-color: #f8f9fa;
            padding: 15px;
            border-left: 4px solid #7c9bc7;
            margin: 10px 0;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            overflow-x: auto;
        }}
        .runlog-details.expanded {{
            display: block;
        }}
        .runlog-tree {{
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .runlog-node {{
            margin: 5px 0;
            padding: 3px 0;
        }}
        .runbook-node {{
            color: #2c3e50;
            font-weight: 500;
        }}
        .task-node {{
            color: #555;
        }}
        .runlog-root {{
            font-weight: bold;
            color: #7c9bc7;
            margin: 10px 0;
            padding: 5px 0;
            border-bottom: 2px solid #7c9bc7;
        }}
    </style>
    <script>
        function toggleRunlogDetails(rowId) {{
            var details = document.getElementById('runlog-' + rowId);
            var icon = document.getElementById('icon-' + rowId);
            if (details.classList.contains('expanded')) {{
                details.classList.remove('expanded');
                icon.textContent = '+';
            }} else {{
                details.classList.add('expanded');
                icon.textContent = '−';
            }}
        }}
    </script>
</head>
<body>
    <div class="container">
        <h1>App Provisioning Stats Report</h1>
        
        <div class="info">
            <strong>Generated:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}<br>
            <strong>Host:</strong> {host_url}<br>
            <strong>Total Apps:</strong> {len(data)}<br>
            <strong>Contact:</strong> <a href="mailto:manish.gupta@nutanix.com">manish.gupta@nutanix.com</a>
        </div>
        
        <div class="summary">
            <h3>Summary</h3>
            <p>This report shows provisioning times for {len(data)} apps.</p>
"""
    
    # Add total provisioning time section if available
    if total_provisioning_info:
        html_content += f"""
            <div class="info" style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-left: 5px solid #4caf50; margin-top: 30px;">
                <h3 style="margin-top: 0; color: #2e7d32; font-size: 1.3em;">📊 Total Provisioning Time Across Filtered Apps</h3>
                <p style="font-size: 1.1em; line-height: 1.8;">
                    <strong>Total Filtered Apps Provisioned:</strong> {total_provisioning_info['total_apps']}<br>
                    <strong>Earliest Creation Time (IST):</strong> {total_provisioning_info['min_creation_time_str']}<br>
                    <strong>Latest Last Update Time (IST):</strong> {total_provisioning_info['max_last_update_time_str']}<br>
                    <strong style="color: #1b5e20; font-size: 1.2em;">Total Time to Provision All Filtered Apps:</strong> 
                    <span style="color: #2e7d32; font-size: 1.3em; font-weight: bold;">{total_provisioning_info['total_provisioning_duration_str']}</span>
                </p>
                <p style="font-size: 0.95em; color: #555; margin-top: 10px; font-style: italic;">
                    <em>Note: This calculation is based only on the filtered apps (not all apps in the system).</em><br>
                    <em>Calculation: Max(Last Update Time) - Min(Creation Time) = {total_provisioning_info['total_provisioning_duration_str']}</em>
                </p>
"""
        # Expanded summary: state breakdown, Pass %, and provisioning time stats (running apps only)
        if 'count_error' in total_provisioning_info:
            pi = total_provisioning_info
            count_error = pi.get('count_error', 0)
            count_running = pi.get('count_running', 0)
            count_provisioning = pi.get('count_provisioning', 0)
            count_unknown = pi.get('count_unknown', 0)
            pass_pct = pi.get('pass_pct', 0.0)
            total_apps = pi.get('total_apps', 0)
            min_sec = pi.get('min_provisioning_seconds')
            max_sec = pi.get('max_provisioning_seconds')
            p95_sec = pi.get('p95_provisioning_seconds')
            min_str = format_duration(min_sec) if min_sec is not None else 'N/A'
            max_str = format_duration(max_sec) if max_sec is not None else 'N/A'
            p95_str = format_duration(p95_sec) if p95_sec is not None else 'N/A'
            html_content += f"""
                <h4 style="margin-top: 22px; margin-bottom: 10px; color: #1b5e20;">State breakdown and Pass %</h4>
                <p style="font-size: 1.05em; line-height: 1.9;">
                    1. <strong>Total Filtered Apps Provisioned:</strong> {total_apps}<br>
                    2. <strong>Total Filtered app in error state:</strong> {count_error}<br>
                    3. <strong>Total Filtered app in Running state:</strong> {count_running}<br>
                    4. <strong>Total Filtered app in provisioning state:</strong> {count_provisioning}<br>
                    5. <strong>Total Filtered app in unknown state:</strong> {count_unknown} <span style="font-size: 0.9em; color: #555;">(catchall: state is not error, provisioning, or running)</span><br>
                    <strong>Pass %:</strong> {pass_pct:.1f}% &nbsp; <span style="font-size: 0.95em;">(formula: Running / Total = {count_running} / {total_apps} = {pass_pct:.1f}%)</span>
                </p>
                <p style="font-size: 0.9em; color: #555; margin-top: 8px; font-style: italic;">
                    <em>Note: Pass % counts only apps in Running state as success. Apps in provisioning state and unknown (catchall) state are not considered as pass.</em>
                </p>
                <h4 style="margin-top: 22px; margin-bottom: 10px; color: #1b5e20;">Time to Provision (running apps only)</h4>
                <p style="font-size: 1.05em; line-height: 1.9;">
                    <strong>Minimum provisioning time:</strong> {min_str} &nbsp; <span style="font-size: 0.9em; color: #555;">(only apps that moved to Running state; error and provisioning excluded)</span><br>
                    <strong>Maximum provisioning time:</strong> {max_str}<br>
                    <strong>P95 provisioning time:</strong> {p95_str} &nbsp; <span style="font-size: 0.9em; color: #555;">(95th percentile among successful running apps)</span>
                </p>
                <p style="font-size: 0.9em; color: #555; margin-top: 8px; font-style: italic;">
                    <em>Note: Min, max, and P95 are computed only over apps in Running state. Error and provisioning states are excluded.</em>
                </p>
            </div>
"""
        else:
            html_content += """
            </div>
"""
    
    html_content += """
        
        <h2>Detailed Table</h2>
        <p><strong>Note:</strong> All times are displayed in IST (India Standard Time, UTC+5:30). 
        Time to Provision is calculated as: Last Update Time - Creation Time.
        Click the <strong>+</strong> icon to expand and view runbook/task details for each Blueprint UUID.</p>
        <table>
            <thead>
                <tr>
                    <th style="width: 30px;"></th>
                    <th>App Name</th>
                    <th>Creation Time (IST)</th>
                    <th>Last Update Time (IST)</th>
                    <th>Time to Provision</th>
                    <th>State</th>
                    <th>Blueprint UUID</th>
                    <th>Source Marketplace Name</th>
                </tr>
            </thead>
            <tbody>
"""
    
    for idx, row in enumerate(data):
        # Escape HTML special characters for safety
        # Row structure: [app_name, creation_time_str, update_time_str, duration_str, state, blueprint_uuid, marketplace_name, ...]
        app_name = html.escape(str(row[0]))
        creation_time = html.escape(str(row[1]))
        update_time = html.escape(str(row[2]))
        duration = html.escape(str(row[3]))
        state_raw = str(row[4])
        state = html.escape(state_raw)
        blueprint_uuid = html.escape(str(row[5]))
        marketplace_name = html.escape(str(row[6]))
        
        # Color code state: RED for "error", normal for others
        state_style = 'style="color: red; font-weight: bold;"' if state_raw.lower() == "error" else ''
        state_cell = f'<td {state_style}>{state}</td>' if state_style else f'<td>{state}</td>'
        
        row_id = f"row-{idx}"
        has_runlogs = blueprint_uuid != "N/A" and blueprint_uuid in runlogs_data
        
        # Get runlog tree HTML if available
        runlog_tree_html = ""
        if has_runlogs:
            runlog_tree_html = format_runlog_tree_html(runlogs_data[blueprint_uuid], row_id)
        
        # Build expand icon and onclick attribute (avoid backslashes in f-string expressions)
        if has_runlogs:
            # Build strings separately to avoid backslash issues in f-strings
            row_id_escaped = row_id  # row_id is already safe (no special chars)
            expand_icon = '<span class="expand-icon" id="icon-' + row_id_escaped + '" onclick="toggleRunlogDetails(\'' + row_id_escaped + '\'); event.stopPropagation();">+</span>'
            onclick_attr = 'onclick="toggleRunlogDetails(\'' + row_id_escaped + '\')"'
            row_class = 'expandable-row'
        else:
            expand_icon = '<span style="width: 20px; display: inline-block;"></span>'
            onclick_attr = ''
            row_class = ''
        
        # Build row HTML
        if row_class:
            html_content += f"""
                <tr class="{row_class}" {onclick_attr}>
                    <td>{expand_icon}</td>
                    <td>{app_name}</td>
                    <td>{creation_time}</td>
                    <td>{update_time}</td>
                    <td>{duration}</td>
                    {state_cell}
                    <td>{blueprint_uuid}</td>
                    <td>{marketplace_name}</td>
                </tr>
"""
        else:
            html_content += f"""
                <tr>
                    <td>{expand_icon}</td>
                    <td>{app_name}</td>
                    <td>{creation_time}</td>
                    <td>{update_time}</td>
                    <td>{duration}</td>
                    {state_cell}
                    <td>{blueprint_uuid}</td>
                    <td>{marketplace_name}</td>
                </tr>
"""
        
        if has_runlogs:
            html_content += f"""
                <tr>
                    <td colspan="8">
                        <div class="runlog-details" id="runlog-{row_id}">
                            <h4 style="margin-top: 0; color: #7c9bc7;">Runbook/Task Details for Blueprint: {blueprint_uuid}</h4>
                            {runlog_tree_html}
                        </div>
                    </td>
                </tr>
"""
    
    html_content += """
            </tbody>
        </table>
        
        <h2>Graph 1: App Provisioning Start Times</h2>
        <div class="graph-container">
            <p><strong>Interpretation:</strong> Shows when each app started provisioning. X-axis shows date & time, Y-axis shows app names. Points clustered together indicate apps started around the same time. Spread out points show apps started over a period.</p>
            <p><strong>Hover over data points to see exact start time.</strong></p>
"""
    
    # Use interactive plotly graph if available, otherwise fall back to static image
    if start_times_plotly_html:
        html_content += f'            <div style="margin: 20px 0;">{start_times_plotly_html}</div>\n'
    elif start_times_img:
        html_content += f'            <img src="data:image/png;base64,{start_times_img}" alt="Start Times Graph">\n'
    else:
        html_content += '            <p>No start time data available</p>\n'
    
    html_content += """        </div>
        
        <h2>Graph 2: Provisioning Time by App</h2>
        <div class="graph-container">
            <p><strong>Interpretation:</strong> Horizontal bar chart showing provisioning time for each app (sorted by time, shortest to longest). X-axis shows provisioning time in seconds. Longer bars indicate longer provisioning times. Apps are sorted to easily identify fastest and slowest provisioning.</p>
"""
    
    if provisioning_times_img:
        html_content += f'            <img src="data:image/png;base64,{provisioning_times_img}" alt="Provisioning Times Graph">\n'
    else:
        html_content += '            <p>No provisioning time data available</p>\n'
    
    html_content += """        </div>
"""
    
    # Add trend analysis section if available
    if runbook_graph_html or task_graph_html or runbook_table_html or task_table_html:
        html_content += """        
        <h2>Trend Analysis: Execution Time Across All Apps</h2>
        <div class="info">
            <p><strong>Purpose:</strong> This section shows execution time trends for each runbook and task across all applications.</p>
            <p><strong>How to use:</strong></p>
            <ul style="margin: 10px 0; padding-left: 20px;">
                <li><strong>Interactive Graphs:</strong> Click legend items to show/hide specific runbooks/tasks</li>
                <li><strong>Hover:</strong> See app UUID and exact execution time</li>
                <li><strong>Tables:</strong> Summary statistics (Min, Avg, P95, Max) with app names on hover</li>
                <li><strong>Analysis:</strong> Identify tasks with high variance or consistently slow execution</li>
            </ul>
        </div>
"""
        
        if runbook_table_html:
            html_content += """        
        <h2>Runbook Execution Summary</h2>
        <div class="info">
            <p><strong>Key Metrics:</strong></p>
            <ul style="margin: 10px 0; padding-left: 20px;">
                <li><strong>Min Time:</strong> Fastest execution across all apps. <em>App name shown below the time, hover for full UUID.</em></li>
                <li><strong>Avg Time:</strong> Average execution time across all apps.</li>
                <li><strong>P95 Time:</strong> 95th percentile - 95% of executions complete within this time.</li>
                <li><strong>Max Time:</strong> Slowest execution across all apps. <em>App name shown below the time, hover for full UUID.</em></li>
            </ul>
        </div>
"""
            html_content += runbook_table_html + '\n'
        
        if runbook_graph_html:
            html_content += """        
        <h2>Runbook Execution Time Trends</h2>
        <div class="graph-container">
            <p><strong>How to use:</strong></p>
            <ul style="margin: 10px 0; padding-left: 20px;">
                <li><strong>X-axis:</strong> App names (shortened to 12 chars)</li>
                <li><strong>Y-axis:</strong> Execution time in seconds</li>
                <li><strong>Each line:</strong> One runbook type across all apps</li>
                <li><strong>Click legend:</strong> Show/hide specific runbooks</li>
                <li><strong>Hover on data point:</strong> See full app UUID and exact duration</li>
            </ul>
            <p><strong>Look for:</strong> Flat lines = consistent execution ✅, steep spikes = investigate those apps ⚠️</p>
"""
            html_content += f'            <div style="margin: 20px 0;">{runbook_graph_html}</div>\n'
            html_content += """        </div>
"""
        
        if task_table_html:
            html_content += """        
        <h2>Task Execution Summary</h2>
        <div class="info">
            <p><strong>Key Metrics:</strong></p>
            <ul style="margin: 10px 0; padding-left: 20px;">
                <li><strong>Min Time:</strong> Fastest execution across all apps. <em>App name shown below the time, hover for full UUID.</em></li>
                <li><strong>Avg Time:</strong> Average execution time across all apps.</li>
                <li><strong>P95 Time:</strong> 95th percentile - 95% of executions complete within this time.</li>
                <li><strong>Max Time:</strong> Slowest execution across all apps. <em>App name shown below the time, hover for full UUID.</em></li>
            </ul>
        </div>
"""
            html_content += task_table_html + '\n'
        
        if task_graph_html:
            html_content += """        
        <h2>Task Execution Time Trends</h2>
        <div class="graph-container">
            <p><strong>How to use:</strong></p>
            <ul style="margin: 10px 0; padding-left: 20px;">
                <li><strong>X-axis:</strong> App names (shortened to 12 chars)</li>
                <li><strong>Y-axis:</strong> Execution time in seconds</li>
                <li><strong>Each line:</strong> One task type across all apps</li>
                <li><strong>Click legend:</strong> Show/hide specific tasks</li>
                <li><strong>Hover on data point:</strong> See full app UUID and exact duration</li>
            </ul>
            <p><strong>Look for:</strong> Flat lines = consistent execution ✅, steep spikes = investigate those apps ⚠️, clustering = multiple performance profiles</p>
"""
            html_content += f'            <div style="margin: 20px 0;">{task_graph_html}</div>\n'
            html_content += """        </div>
"""
    
    html_content += """        
        <div class="info" style="margin-top: 40px; text-align: center; font-size: 0.9em; color: #666;">
            <strong>For questions or issues, please contact:</strong> 
            <a href="mailto:manish.gupta@nutanix.com">manish.gupta@nutanix.com</a>
        </div>
    </div>
</body>
</html>
"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"[INFO] HTML report written to: {output_file}")

def generate_graphs(data, output_prefix, embed_in_html=False, custom_avg=None):
    """Generate two graphs: start times and provisioning times.
    
    Args:
        data: List of [app_name, creation_time_str, update_time_str, duration_str, state, blueprint_uuid, marketplace_name, 
                       creation_time_raw, last_update_time_raw, duration_seconds_raw]
        output_prefix: Prefix for output files
        embed_in_html: If True, return base64 encoded images for HTML embedding
        custom_avg: Optional custom average threshold in seconds. If None, calculates average from data.
    
    Returns:
        If embed_in_html=True: tuple of (start_times_img_base64, provisioning_times_img_base64)
        Otherwise: None
    """
    if not data:
        print("[WARNING] No data to plot")
        return (None, None, None) if embed_in_html else None
    
    # Extract data for graphs using raw timestamps and durations (more reliable)
    app_names = []
    start_times = []
    provision_times = []
    
    for row in data:
        # Row structure: [app_name, creation_time_str, update_time_str, duration_str, state, blueprint_uuid, marketplace_name, 
        #                  creation_time_raw, last_update_time_raw, duration_seconds_raw]
        if len(row) < 10:
            debug_log(f"[DEBUG] Row has insufficient data: {len(row)} columns, expected 10")
            continue
        
        app_name = row[0]
        creation_time_raw = row[7]  # Raw timestamp in microseconds
        duration_seconds_raw = row[9]  # Raw duration in seconds
        
        # Convert raw timestamp to datetime object
        try:
            if isinstance(creation_time_raw, (int, float)) and creation_time_raw > 0:
                epoch_seconds = creation_time_raw / 1_000_000.0
                dt = datetime.fromtimestamp(epoch_seconds, tz=pytz.utc)
                # Convert to IST for display consistency
                ist = pytz.timezone('Asia/Kolkata')
                dt_ist = dt.astimezone(ist)
                # Remove timezone info for matplotlib (it handles naive datetimes better)
                dt_naive = dt_ist.replace(tzinfo=None)
            else:
                debug_log(f"[DEBUG] Invalid creation_time_raw for app '{app_name}': {creation_time_raw}")
                continue
        except (ValueError, OSError, TypeError) as e:
            debug_log(f"[DEBUG] Failed to convert timestamp for app '{app_name}': {e}")
            continue
        
        # Validate duration
        if not isinstance(duration_seconds_raw, (int, float)) or duration_seconds_raw <= 0:
            debug_log(f"[DEBUG] Invalid duration for app '{app_name}': {duration_seconds_raw}")
            continue
        
        # All data is valid, append
        app_names.append(app_name)
        start_times.append(dt_naive)
        provision_times.append(float(duration_seconds_raw))
    
    if not start_times:
        print(f"[WARNING] No valid data to plot (processed {len(data)} rows)")
        return (None, None, None) if embed_in_html else None
    
    print(f"[INFO] Generating graphs for {len(app_names)} apps")
    
    # Graph 1: Start times - Simple visualization showing start time distribution
    # Round timestamps to nearest second for display (so apps with same second align vertically)
    # This ensures apps with same creation time (within same second) appear on same vertical line
    from datetime import timedelta
    start_times_rounded = []
    for dt in start_times:
        # Round to nearest second by truncating microseconds
        dt_rounded = dt.replace(microsecond=0)
        start_times_rounded.append(dt_rounded)
    
    plt.figure(figsize=(16, max(8, len(app_names) * 0.5)))
    
    # Simple scatter plot: X-axis = start time, Y-axis = app names
    y_positions = range(len(app_names))
    plt.scatter(start_times_rounded, y_positions, alpha=0.7, s=150, color='steelblue', edgecolors='navy', linewidth=1.5)
    
    plt.yticks(y_positions, app_names)
    plt.xlabel("Start Time (Date & Time IST)", fontsize=12, fontweight='bold')
    plt.ylabel("App Name", fontsize=12, fontweight='bold')
    plt.title("App Provisioning Start Times\n(Shows when each app started - points close together = similar start times)", fontsize=14, fontweight='bold')
    plt.grid(True, alpha=0.3, axis='x', linestyle='--')
    
    # Format X-axis based on time span - use proper date locator
    ax = plt.gca()
    time_span = (max(start_times_rounded) - min(start_times_rounded)).total_seconds()
    
    # Use AutoDateLocator with maxticks to prevent too many ticks, but ensure it works
    locator = mdates.AutoDateLocator(maxticks=10)
    ax.xaxis.set_major_locator(locator)
    
    # Apply date formatting based on time span
    if time_span < 3600:  # Less than 1 hour
        formatter = mdates.DateFormatter('%H:%M:%S')
    elif time_span < 86400:  # Less than 1 day
        formatter = mdates.DateFormatter('%m/%d %H:%M')
    else:  # Multiple days
        formatter = mdates.DateFormatter('%Y-%m-%d %H:%M')
    
    ax.xaxis.set_major_formatter(formatter)
    
    # Fix duplicate X-axis labels by removing duplicates
    # Get current tick positions and labels
    ticks = ax.get_xticks()
    labels = [formatter.format_data(tick) for tick in ticks]
    # Remove duplicate consecutive labels
    unique_labels = []
    unique_ticks = []
    prev_label = None
    for tick, label in zip(ticks, labels):
        if label != prev_label:
            unique_labels.append(label)
            unique_ticks.append(tick)
            prev_label = label
        else:
            unique_labels.append('')  # Empty label for duplicate
            unique_ticks.append(tick)
    
    ax.set_xticks(unique_ticks)
    ax.set_xticklabels(unique_labels, rotation=45, ha='right')
    plt.tight_layout()
    
    # Generate interactive plotly version with hover tooltips (if available)
    # Use rounded timestamps (seconds only, no milliseconds) for consistency
    start_times_plotly_html = None
    if PLOTLY_AVAILABLE and embed_in_html:
        try:
            # Format timestamps for display in hover (using rounded times, seconds only)
            hover_texts = []
            for i, (app_name, start_time) in enumerate(zip(app_names, start_times_rounded)):
                # Format time with seconds precision only (no milliseconds)
                time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
                hover_texts.append(f"<b>{app_name}</b><br>Start Time: {time_str} IST")
            
            # Create interactive scatter plot with hover (using rounded timestamps)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=start_times_rounded,
                y=list(range(len(app_names))),
                mode='markers',
                marker=dict(
                    size=12,
                    color='steelblue',
                    line=dict(width=1.5, color='navy')
                ),
                text=app_names,
                hovertext=hover_texts,
                hoverinfo='text',
                name='App Start Times'
            ))
            
            fig.update_layout(
                title="App Provisioning Start Times<br><sub>Hover over points to see exact start time</sub>",
                xaxis_title="Start Time (Date & Time IST)",
                yaxis_title="App Name",
                yaxis=dict(
                    tickmode='array',
                    tickvals=list(range(len(app_names))),
                    ticktext=app_names
                ),
                hovermode='closest',
                height=max(600, len(app_names) * 40),
                width=1200,
                showlegend=False,
                xaxis=dict(
                    tickangle=-45,
                    tickformat='%Y-%m-%d %H:%M:%S'
                )
            )
            
            # Convert to HTML string
            start_times_plotly_html = fig.to_html(include_plotlyjs='cdn', div_id='start_times_graph')
        except Exception as e:
            print(f"[WARNING] Failed to create interactive graph: {e}")
            start_times_plotly_html = None
    
    if embed_in_html:
        # Save to bytes buffer for HTML embedding
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        start_times_img = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
    else:
        plt.savefig(f"{output_prefix}_start_times.png", dpi=150, bbox_inches='tight')
        start_times_img = None
    plt.close()
    
    if not embed_in_html:
        print(f"[INFO] Graph 1 saved: {output_prefix}_start_times.png")
    
    # Graph 2: Provisioning times - Horizontal bar chart for clear comparison
    if not provision_times:
        print("[WARNING] No provisioning time data to plot")
        if embed_in_html:
            return (start_times_img if 'start_times_img' in locals() else None, None, None)
        return None
    
    plt.figure(figsize=(14, max(8, len(app_names) * 0.4)))
    # Sort by provisioning time for better visualization (ascending)
    # Match app names with their provisioning times
    valid_data = [(app_names[i], provision_times[i]) for i in range(min(len(app_names), len(provision_times))) if i < len(provision_times) and provision_times[i] > 0]
    
    if not valid_data:
        print("[WARNING] No valid provisioning time data to plot")
        if embed_in_html:
            return (start_times_img if 'start_times_img' in locals() else None, None, None)
        return None
    
    sorted_data = sorted(valid_data, key=lambda x: x[1])
    sorted_names, sorted_times = zip(*sorted_data) if sorted_data else ([], [])
    
    # Use horizontal bar chart - much clearer for comparing values
    # Use custom average if provided, otherwise calculate from data
    if custom_avg is not None:
        avg_time = custom_avg
    else:
        avg_time = sum(sorted_times) / len(sorted_times) if sorted_times else 0
    colors = ['coral' if t > avg_time else 'lightblue' for t in sorted_times]
    bars = plt.barh(sorted_names, sorted_times, alpha=0.7, color=colors, edgecolor='darkred', linewidth=1)
    
    # Add value labels on bars - use same format_duration function as table for consistency
    for i, (name, time_val) in enumerate(zip(sorted_names, sorted_times)):
        label = f' {format_duration(time_val)}'
        plt.text(time_val, i, label, va='center', fontsize=9, fontweight='bold')
    
    # Add legend to explain color coding
    from matplotlib.patches import Patch
    avg_time_formatted = format_duration(avg_time)
    
    # Determine if average is user-defined or calculated
    if custom_avg is not None:
        avg_label = f'User-Defined Average: {avg_time_formatted}'
    else:
        avg_label = f'Calculated Average: {avg_time_formatted} (average of all {len(sorted_times)} apps)'
    
    legend_elements = [
        Patch(facecolor='lightblue', alpha=0.7, label=f'≤ Average ({avg_time_formatted})'),
        Patch(facecolor='coral', alpha=0.7, label=f'> Average ({avg_time_formatted})')
    ]
    legend = plt.legend(handles=legend_elements, loc='lower right', fontsize=9, framealpha=0.95)
    
    # Add text annotation explaining the average calculation (positioned below the graph)
    ax = plt.gca()
    plt.figtext(0.5, 0.01, avg_label, ha='center', fontsize=9, style='italic', 
                bbox=dict(boxstyle='round,pad=0.8', facecolor='#f0f0f0', edgecolor='#666', alpha=0.8))
    
    plt.xlabel("Provisioning Time", fontsize=12, fontweight='bold')
    plt.ylabel("App Name", fontsize=12, fontweight='bold')
    plt.title("Provisioning Time by App (Sorted)\n(Longer bars = longer provisioning time)", fontsize=14, fontweight='bold')
    plt.grid(True, alpha=0.3, axis='x', linestyle='--')
    plt.tight_layout(rect=[0, 0.05, 1, 1])  # Make room at bottom for annotation
    
    if embed_in_html:
        # Save to bytes buffer for HTML embedding
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        provisioning_times_img = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
    else:
        plt.savefig(f"{output_prefix}_provisioning_times.png", dpi=150, bbox_inches='tight')
        provisioning_times_img = None
    plt.close()
    
    if not embed_in_html:
        print(f"[INFO] Graph 2 saved: {output_prefix}_provisioning_times.png")
    
    if embed_in_html:
        return (start_times_img, provisioning_times_img, start_times_plotly_html)
    return None

def parse_duration_to_seconds(duration_str):
    """Parse duration string (e.g., '5m 30s', '2h 15m', '730s') to seconds."""
    if not duration_str or duration_str.strip() == '':
        return 0
    
    total_seconds = 0
    duration_str = duration_str.strip()
    
    # Handle hours - match pattern like "2h" or "2h 15m"
    import re
    hour_match = re.search(r'(\d+(?:\.\d+)?)h', duration_str)
    if hour_match:
        total_seconds += float(hour_match.group(1)) * 3600
    
    # Handle minutes - match pattern like "12m" or "12m 20s"
    minute_match = re.search(r'(\d+(?:\.\d+)?)m', duration_str)
    if minute_match:
        total_seconds += float(minute_match.group(1)) * 60
    
    # Handle seconds - match pattern like "30s" or just "730"
    second_match = re.search(r'(\d+(?:\.\d+)?)s', duration_str)
    if second_match:
        total_seconds += float(second_match.group(1))
    elif re.match(r'^\d+(?:\.\d+)?$', duration_str):
        # If it's just a number, assume it's seconds
        total_seconds = float(duration_str)
    
    return total_seconds

def parse_epoch(s):
    """Convert epoch-like int (sec/ms/us/ns) to timezone-aware UTC datetime.
    
    Nutanix API timestamps are typically in microseconds (16 digits).
    Examples: 1764908481636312 (microseconds) = ~2025-12-05
    """
    if s is None:
        return None
    try:
        # Handle both string and int formats
        if isinstance(s, str):
            val = int(s)
        else:
            val = int(s)
    except (ValueError, TypeError):
        return None
    
    # Heuristic by magnitude (ns/us/ms/sec)
    # Timestamps from Nutanix API are typically in microseconds (16 digits)
    # Examples: 1764908481636312 (microseconds) = ~2025-12-05
    if val > 1_000_000_000_000_000:      # nanoseconds (19+ digits)
        sec = val / 1_000_000_000
    elif val > 1_000_000_000_000:        # microseconds (13-18 digits) - MOST COMMON for Nutanix
        sec = val / 1_000_000
    elif val > 1_000_000_000:            # milliseconds (10-12 digits)
        sec = val / 1_000
    else:                                # seconds (< 10 digits)
        sec = val
    
    try:
        dt = datetime.fromtimestamp(sec, tz=timezone.utc)
        # Sanity check: if date is before 2000, likely wrong parsing
        # Try as microseconds if it was parsed as seconds
        if dt.year < 2000 and sec < 1_000_000_000_000:
            # Likely microseconds being parsed as seconds
            sec_micro = val / 1_000_000
            try:
                dt = datetime.fromtimestamp(sec_micro, tz=timezone.utc)
            except:
                pass
        return dt
    except (ValueError, OSError):
        return None

def duration_seconds(start_dt, end_dt):
    """Return duration in seconds (float), or None."""
    if not start_dt or not end_dt:
        return None
    return (end_dt - start_dt).total_seconds()

def parse_runlogs_json(runlogs_data):
    """Parse app runlogs JSON and build hierarchical tree structure.
    
    This function processes the JSON response from the runlogs API and builds a tree
    structure representing the parent-child relationships between actions, runbooks, and tasks.
    
    Args:
        runlogs_data (dict): JSON response from get_app_runlogs() containing 'entities' array
    
    Returns:
        dict: Dictionary with 'forest' key containing list of root trees:
              {'forest': [{'root_action_runlog_uuid': uuid, 'nodes': [root_nodes]}, ...]}
    
    Variables:
        - node: Dictionary mapping UUID -> node data
          * Keys: id, type, action_name, runbook_name, task_name, state, created_iso,
                  updated_iso, duration_seconds, parent_uuid, root_uuid, children
        - children: defaultdict mapping parent UUID -> list of child UUIDs
          * Used to build adjacency list for tree structure
        - roots: defaultdict mapping root UUID -> list of root node UUIDs
          * Groups nodes by their root_action_runlog_uuid
    
    Tree Building Logic:
        1. Extract all entities and build node map:
           - Extract parent_reference.uuid (immediate parent)
           - Extract root_reference.uuid (root action_runlog)
           - Extract timestamps from metadata (creation_time, last_update_time)
           - Extract names from status (action_reference.name, runbook_reference.name, task_reference.name)
           - Calculate duration: (last_update_time - creation_time) / 1,000,000 seconds
        
        2. Build adjacency list (parent-child relationships):
           - action_runlog/platform_sync_runlog → roots (their own root)
           - If parent_uuid exists in node map → attach as child of parent
           - If no parent but root_uuid exists in map:
             * runbook_runlog → attach as child of root (action_runlog)
             * task_runlog → attach as child of root (fallback)
           - Otherwise → make it its own root (fallback)
        
        3. Build JSON tree recursively:
           - build_json(nid): Recursively builds tree starting from node nid
           - Sorts children by creation_time (earliest first) to match UI order
           - Returns node with nested 'children' array
        
        4. Build forest (multiple root trees):
           - Groups by root_action_runlog_uuid
           - Only includes action_runlog/platform_sync_runlog as actual roots
           - Creates forest structure for multiple action runlogs
    
    Example Tree Structure:
        action_runlog (root, indent_level=0)
          └── runbook_runlog (child, indent_level=1)
                └── task_runlog (child, indent_level=2)
                └── runbook_runlog (nested, indent_level=2)
                      └── task_runlog (child, indent_level=3)
    """
    if not runlogs_data or "entities" not in runlogs_data:
        debug_log("[DEBUG] parse_runlogs_json: No entities in runlogs_data")
        return None
    
    entities = runlogs_data.get('entities', [])
    debug_log(f"[DEBUG] parse_runlogs_json: Processing {len(entities)} entities")
    
    if len(entities) == 0:
        debug_log("[DEBUG] parse_runlogs_json: No entities to process")
        return None
    
    # Build node map (keyed by metadata.uuid), record parent & root
    node = {}
    children = defaultdict(list)
    roots = defaultdict(list)
    
    entity_types_found = {}
    for e in entities:
        status = e.get('status', {})
        meta = e.get('metadata', {})
        nid = meta.get('uuid')
        if not nid:
            continue
        
        entity_type = status.get('type', 'unknown')
        entity_types_found[entity_type] = entity_types_found.get(entity_type, 0) + 1
        
        # Extract parent and root references correctly
        # parent_reference.uuid points to the immediate parent (e.g., runbook_runlog -> runbook_runlog, or task_runlog -> runbook_runlog)
        # root_reference.uuid points to the root action_runlog
        parent_ref = status.get('parent_reference') or {}
        root_ref = status.get('root_reference') or {}
        parent_uuid = parent_ref.get('uuid')
        root_uuid = root_ref.get('uuid')
        
        # Debug: log if we find runbook or task runlogs
        if entity_type in ['runbook_runlog', 'task_runlog']:
            debug_log(f"[DEBUG] Found {entity_type}: id={nid}, parent={parent_uuid}, root={root_uuid}, runbook={status.get('runbook_reference', {}).get('name')}, task={status.get('task_reference', {}).get('name')}")
        
        # Extract timestamps from metadata (these are in microseconds as strings or ints)
        # IMPORTANT: Each entity has its own creation_time and last_update_time in metadata
        # Duration is calculated as: last_update_time - creation_time for THAT specific entity
        # This means each entity (action, runbook, task) has its own independent duration
        # 
        # Example: 
        # - action_runlog: created=09:25:22, updated=09:51:23 → duration = 26m 2s (action's own duration)
        # - runbook_runlog: created=09:30:06, updated=09:51:20 → duration = 21m 15s (runbook's own duration)
        # These durations are independent - the runbook started later and finished slightly earlier than the action
        created_raw = meta.get('creation_time')
        updated_raw = meta.get('last_update_time')
        
        # Parse timestamps - handle both string and int formats
        created_dt = parse_epoch(created_raw)
        updated_dt = parse_epoch(updated_raw)
        dur = duration_seconds(created_dt, updated_dt)
        
        # Debug: log duration calculation for verification
        if entity_type == 'action_runlog':
            debug_log(f"[DEBUG] action_runlog {nid}: created={created_raw}, updated={updated_raw}, duration={dur}s ({dur/60:.1f}m)")
        elif entity_type == 'runbook_runlog' and status.get('runbook_reference', {}).get('name'):
            debug_log(f"[DEBUG] runbook_runlog {status.get('runbook_reference', {}).get('name')}: created={created_raw}, updated={updated_raw}, duration={dur}s ({dur/60:.1f}m)")
        
        # Extract runbook reference name (for runbook_runlog type)
        runbook_ref = status.get('runbook_reference') or {}
        runbook_name = runbook_ref.get('name')
        
        # Extract task reference name (for task_runlog type)
        task_ref = status.get('task_reference') or {}
        task_name = task_ref.get('name')
        
        # Extract element reference name (for task_runlog type)
        element_ref = status.get('element_reference') or {}
        element_name = element_ref.get('name')
        
        # Extract action reference for action_runlog type
        action_ref = status.get('action_reference') or {}
        action_name = action_ref.get('name')
        
        # Build node with all extracted information
        node[nid] = {
            'id': nid,
            'type': status.get('type'),  # 'action_runlog', 'runbook_runlog', 'task_runlog', 'policy_runlog', etc.
            'action_name': action_name,  # For action_runlog: name of the action
            'runbook_name': runbook_name,  # For runbook_runlog: name of the runbook
            'task_name': task_name,  # For task_runlog: name of the task
            'element_type': status.get('element_type'),  # e.g., 'ServiceElement', 'SubstrateElement'
            'element_name': element_name,  # Name of the element
            'machine_name': status.get('machine_name'),  # Machine name for tasks
            'task_kind': status.get('task_kind'),  # e.g., 'EXEC', 'DELAY', 'PROVISION_NUTANIX'
            'e_task_type': status.get('e_task_type'),  # e.g., 'EXEC2', 'CALL_WORKFLOW'
            'exit_code': status.get('exit_code'),  # Exit code (can be -1 for success)
            'state': status.get('state'),  # 'SUCCESS', 'ERROR', etc.
            'name': status.get('name'),  # Name field (for platform_sync_runlog)
            'created_raw': created_raw,  # Raw timestamp string
            'updated_raw': updated_raw,  # Raw timestamp string
            'created_iso': created_dt.isoformat() if created_dt else None,  # ISO format UTC
            'updated_iso': updated_dt.isoformat() if updated_dt else None,  # ISO format UTC
            'duration_seconds': dur,  # Duration in seconds (float)
            'parent_uuid': parent_uuid,  # UUID of parent node
            'root_uuid': root_uuid,  # UUID of root action_runlog
        }
    
    debug_log(f"[DEBUG] parse_runlogs_json: Built {len(node)} nodes, entity types: {entity_types_found}")
    
    # Build adjacency list with proper parent-child relationships
    # Strategy:
    # 1. action_runlog and platform_sync_runlog entities are roots (their own root)
    # 2. If a node has a parent_uuid that exists in our node map, attach it as child of that parent
    #    (This handles: runbook->runbook, runbook->task relationships)
    # 3. If a node has no parent in our map but has a root_uuid that exists in our map, 
    #    attach it as child of that root ONLY if it's a direct child (runbook under action)
    # 4. Otherwise, make it its own root (fallback)
    
    for n in node.values():
        p = n['parent_uuid']
        r = n['root_uuid']
        node_type = n.get('type', '')
        nid = n['id']
        
        # action_runlog and platform_sync_runlog entities are always roots (their own root)
        if node_type in ['action_runlog', 'platform_sync_runlog']:
            # These are root nodes - they should be in the roots list
            roots[nid].append(nid)
        # If this node has a parent that exists in our node map, attach it as a child
        # This is the PRIMARY way to build hierarchy (parent->child relationships)
        elif p and p in node:
            # Parent exists in our map - attach as child (this handles nested runbooks and tasks)
            # This ensures proper tree structure: parent -> child
            children[p].append(nid)
            debug_log(f"[DEBUG] Tree: {node_type} {nid[:8]}... attached as child of parent {p[:8]}...")
        # If no parent in map but has a root reference that exists in our map
        # Only attach to root if it's a runbook_runlog (direct child of action)
        # Tasks should NOT be attached directly to root - they must have a parent runbook
        elif r and r in node:
            # Check if this is a runbook that should be directly under the action
            if node_type == 'runbook_runlog':
                # Runbook with no parent in map but root exists - attach to root as child
                children[r].append(nid)
                debug_log(f"[DEBUG] Tree: runbook_runlog {nid[:8]}... attached as child of root {r[:8]}...")
            elif node_type == 'task_runlog':
                # Task with no parent in map - this shouldn't happen, but if it does, attach to root
                # This is a fallback for orphaned tasks
                children[r].append(nid)
                print(f"[WARNING] Tree: task_runlog {nid[:8]}... has no parent, attaching to root {r[:8]}...")
            else:
                # Other types - attach to root
                children[r].append(nid)
        # If root_uuid exists but not in our map, still attach to it (it might be an action_runlog we fetched separately)
        elif r:
            # Root UUID exists but not in our node map - add to roots list
            # This will be handled when building the forest
            roots[r].append(nid)
        # Fallback: no parent or root, make it its own root
        else:
            roots[nid].append(nid)
            print(f"[WARNING] Tree: {node_type} {nid[:8]}... has no parent or root, making it its own root")
    
    def build_json(nid):
        """Recursively build JSON tree structure with proper parent-child relationships."""
        if nid not in node:
            print(f"[WARNING] build_json: Node {nid} not found in node map")
            return None
        
        # Get all children of this node
        child_ids = children.get(nid, [])
        
        # Sort children by creation time to match UI order
        def get_creation_time(cid):
            if cid in node:
                created_iso = node[cid].get('created_iso')
                if created_iso:
                    try:
                        return datetime.fromisoformat(created_iso.replace('Z', '+00:00'))
                    except:
                        return datetime.min
            return datetime.min
        
        # Sort children by creation time (earliest first)
        sorted_child_ids = sorted(child_ids, key=get_creation_time)
        
        # Build the node with its children recursively
        # Only include children that exist in the node map
        valid_children = []
        for cid in sorted_child_ids:
            if cid in node:
                child_node = build_json(cid)
                if child_node is not None:
                    valid_children.append(child_node)
        
        result = {
            **node[nid],
            'children': valid_children
        }
        
        return result
    
    # Build forest (multiple root trees, one per root_action_runlog_uuid)
    # Only include actual root nodes (action_runlog, platform_sync_runlog) as roots
    forest = []
    processed_roots = set()
    
    for root_uuid in sorted(roots.keys()):
        if not root_uuid or root_uuid in processed_roots:
            continue
        
        # Get all nodes that should be roots for this root_uuid
        root_node_ids = sorted(roots[root_uuid])
        
        # Filter to only include actual root nodes (action_runlog, platform_sync_runlog)
        # These are the top-level nodes that start each tree
        actual_root_nodes = []
        for nid in root_node_ids:
            if nid in node:
                n = node[nid]
                node_type = n.get('type', '')
                # Include action_runlog and platform_sync_runlog as roots
                if node_type in ['action_runlog', 'platform_sync_runlog']:
                    actual_root_nodes.append(nid)
                # Also include orphaned nodes (no parent, not a child of anyone)
                elif not n.get('parent_uuid'):
                    # Check if this node is a child of any other node
                    is_child = any(nid in child_list for child_list in children.values())
                    if not is_child:
                        actual_root_nodes.append(nid)
        
        if actual_root_nodes:
            # Build the tree starting from root nodes
            root_nodes = []
            for nid in actual_root_nodes:
                root_node = build_json(nid)
                if root_node is not None:
                    root_nodes.append(root_node)
            
            if root_nodes:
                forest.append({
                    'root_action_runlog_uuid': root_uuid,
                    'nodes': root_nodes
                })
                debug_log(f"[DEBUG] parse_runlogs_json: Added root {root_uuid} with {len(root_nodes)} root nodes, total children: {sum(len(n.get('children', [])) for n in root_nodes)}")
                processed_roots.add(root_uuid)
    
    if not forest:
        debug_log("[DEBUG] parse_runlogs_json: No forest built - checking why...")
        debug_log(f"[DEBUG] Total nodes: {len(node)}, Roots: {list(roots.keys())}, Children: {dict(children)}")
        # If no forest but we have nodes, try to create a forest with all nodes as roots
        if node:
            debug_log("[DEBUG] Creating fallback forest with all nodes as roots")
            for nid, n in node.items():
                if not n.get('parent_uuid') or n.get('parent_uuid') not in node:
                    forest.append({
                        'root_action_runlog_uuid': n.get('root_uuid') or nid,
                        'nodes': [build_json(nid)]
                    })
    
    debug_log(f"[DEBUG] parse_runlogs_json: Returning forest with {len(forest)} root trees")
    return {'forest': forest}

def format_runlog_tree_html(forest_data, row_id):
    """Format runlog tree as HTML table with improved visual hierarchy."""
    if not forest_data or 'forest' not in forest_data:
        debug_log(f"[DEBUG] format_runlog_tree_html: No forest_data for row {row_id}")
        return '<div class="runlog-tree">No runlog data available</div>'
    
    forest = forest_data.get('forest', [])
    if not forest:
        debug_log(f"[DEBUG] format_runlog_tree_html: Empty forest for row {row_id}")
        return '<div class="runlog-tree">No runlog tree data available (empty forest)</div>'
    
    debug_log(f"[DEBUG] format_runlog_tree_html: Formatting {len(forest)} root trees for row {row_id}")
    
    # Start with table structure
    html_parts = ['<div class="runlog-tree">']
    html_parts.append('<table class="runlog-table" style="width: 100%; border-collapse: collapse; margin: 10px 0; font-family: monospace;">')
    html_parts.append('<thead>')
    html_parts.append('<tr style="background-color: #2c3e50; color: white;">')
    html_parts.append('<th style="padding: 10px; text-align: left; border: 2px solid #34495e; font-weight: bold;">Type</th>')
    html_parts.append('<th style="padding: 10px; text-align: left; border: 2px solid #34495e; font-weight: bold;">Name</th>')
    html_parts.append('<th style="padding: 10px; text-align: left; border: 2px solid #34495e; font-weight: bold;">Created (IST)</th>')
    html_parts.append('<th style="padding: 10px; text-align: left; border: 2px solid #34495e; font-weight: bold;">Last Updated (IST)</th>')
    html_parts.append('<th style="padding: 10px; text-align: left; border: 2px solid #34495e; font-weight: bold;">Duration</th>')
    html_parts.append('<th style="padding: 10px; text-align: left; border: 2px solid #34495e; font-weight: bold;">State</th>')
    html_parts.append('</tr>')
    html_parts.append('</thead>')
    html_parts.append('<tbody>')
    
    ist = pytz.timezone('Asia/Kolkata')
    
    def format_node_html(n, indent_level=0, is_last=False, parent_prefix=""):
        """Recursively format a node and its children as table rows with tree structure."""
        rows = []
        
        # Format timestamps to IST
        created_ist = "N/A"
        updated_ist = "N/A"
        duration_str = "N/A"
        
        if n.get('created_iso'):
            try:
                dt_utc = datetime.fromisoformat(n['created_iso'].replace('Z', '+00:00'))
                dt_ist = dt_utc.astimezone(ist)
                created_ist = dt_ist.strftime("%Y-%m-%d %H:%M:%S")
            except:
                created_ist = n.get('created_iso', 'N/A')
        
        if n.get('updated_iso'):
            try:
                dt_utc = datetime.fromisoformat(n['updated_iso'].replace('Z', '+00:00'))
                dt_ist = dt_utc.astimezone(ist)
                updated_ist = dt_ist.strftime("%Y-%m-%d %H:%M:%S")
            except:
                updated_ist = n.get('updated_iso', 'N/A')
        
        if n.get('duration_seconds') is not None:
            duration_str = format_duration(n['duration_seconds'])
        
        node_type = n.get('type', 'unknown')
        state = n.get('state', 'N/A')
        state_color = 'red' if state == 'ERROR' else ('orange' if state != 'SUCCESS' else 'green')
        
        # Build tree connector prefix
        if indent_level == 0:
            tree_prefix = ""
        else:
            # Use tree characters: │ ├── └──
            connector = "└── " if is_last else "├── "
            tree_prefix = parent_prefix + connector
        
        # Calculate indentation (30px per level for better visibility)
        indent_padding = indent_level * 30
        
        # Determine background color based on level and type
        has_children = len(n.get('children', [])) > 0
        
        if indent_level == 0:
            # Root level - darker background
            bg_color = "#d4e6f1"  # Light blue
            name_style = "font-weight: bold; font-size: 1.05em; color: #1a5490;"
        elif indent_level == 1:
            # First level children - medium background
            bg_color = "#e8f4f8"  # Very light blue
            name_style = "font-weight: bold; color: #2c5aa0;"
        elif indent_level == 2:
            # Second level - lighter background
            bg_color = "#f0f8fa"  # Almost white blue
            name_style = "font-weight: 600; color: #3d6ba0;"
        else:
            # Deeper levels - white with subtle border
            bg_color = "#ffffff"
            name_style = "color: #555;"
        
        # Make parent nodes (with children) more prominent
        if has_children:
            name_style += " border-left: 3px solid #7c9bc7; padding-left: 5px;"
        
        # Format based on node type
        if node_type == 'action_runlog':
            action_name = n.get('action_name') or 'N/A'
            rows.append(f'<tr style="background-color: {bg_color}; border-left: 4px solid #2980b9;">')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; padding-left: {indent_padding + 10}px; font-weight: bold; color: #2980b9;">ACTION</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; {name_style}">{tree_prefix}<strong>{html.escape(str(action_name))}</strong> <span style="font-size: 0.85em; color: #7f8c8d;">(id: {n.get("id", "N/A")[:8]}...)</span></td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;">{created_ist}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;">{updated_ist}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; font-weight: bold;">{duration_str}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;"><span style="color: {state_color}; font-weight: bold; font-size: 1.05em;">{state}</span></td>')
            rows.append('</tr>')
        elif node_type == 'platform_sync_runlog':
            sync_name = n.get('name') or 'Platform Sync Updates'
            rows.append(f'<tr style="background-color: {bg_color}; border-left: 4px solid #9b59b6;">')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; padding-left: {indent_padding + 10}px; font-weight: bold; color: #9b59b6;">PLATFORM SYNC</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; {name_style}">{tree_prefix}<strong>{html.escape(str(sync_name))}</strong></td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;">{created_ist}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;">{updated_ist}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; font-weight: bold;">{duration_str}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;"><span style="color: {state_color}; font-weight: bold;">{state}</span></td>')
            rows.append('</tr>')
        elif node_type == 'runbook_runlog':
            runbook_name = n.get('runbook_name') or 'N/A'
            rows.append(f'<tr style="background-color: {bg_color}; border-left: 4px solid #27ae60;">')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; padding-left: {indent_padding + 10}px; font-weight: bold; color: #27ae60;">RUNBOOK</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; {name_style}">{tree_prefix}<strong>{html.escape(str(runbook_name))}</strong></td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;">{created_ist}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;">{updated_ist}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; font-weight: bold;">{duration_str}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;"><span style="color: {state_color}; font-weight: bold;">{state}</span></td>')
            rows.append('</tr>')
        elif node_type == 'task_runlog':
            task_name = n.get('task_name') or 'N/A'
            rows.append(f'<tr style="background-color: {bg_color}; border-left: 4px solid #e67e22;">')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; padding-left: {indent_padding + 10}px; color: #e67e22;">Task</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; {name_style}">{tree_prefix}{html.escape(str(task_name))}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;">{created_ist}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;">{updated_ist}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;">{duration_str}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;"><span style="color: {state_color}; font-weight: bold;">{state}</span></td>')
            rows.append('</tr>')
        else:
            type_display = node_type.replace('_', ' ').title()
            rows.append(f'<tr style="background-color: {bg_color}; border-left: 4px solid #95a5a6;">')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; padding-left: {indent_padding + 10}px; color: #95a5a6;">{type_display}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7; {name_style}">{tree_prefix}{n.get("id", "N/A")}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;">{created_ist}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;">{updated_ist}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;">{duration_str}</td>')
            rows.append(f'<td style="padding: 10px; border: 1px solid #bdc3c7;"><span style="color: {state_color}; font-weight: bold;">{state}</span></td>')
            rows.append('</tr>')
        
        # Add children with increased indent and proper tree connectors
        children = n.get('children', [])
        for idx, child in enumerate(children):
            is_last_child = (idx == len(children) - 1)
            # Update parent prefix for tree connectors
            # If current node is last, children use spaces; otherwise use vertical line
            if indent_level == 0:
                child_parent_prefix = "    " if is_last else "│   "
            else:
                if is_last:
                    # Current node is last, so children use spaces
                    child_parent_prefix = parent_prefix + "    "
                else:
                    # Current node is not last, so children use vertical line
                    child_parent_prefix = parent_prefix + "│   "
            rows.extend(format_node_html(child, indent_level + 1, is_last_child, child_parent_prefix))
        
        return rows
    
    for root_tree in forest_data['forest']:
        root_uuid = root_tree.get('root_action_runlog_uuid', 'unknown')
        nodes = root_tree.get('nodes', [])
        if nodes:
            # Add root header row with better styling
            html_parts.append(f'<tr style="background-color: #34495e; color: white; font-weight: bold;">')
            html_parts.append(f'<td colspan="6" style="padding: 12px; border: 2px solid #2c3e50; font-size: 1.1em;">📋 ROOT action_runlog = {root_uuid}</td>')
            html_parts.append('</tr>')
            # Add child nodes
            for idx, node in enumerate(nodes):
                is_last = (idx == len(nodes) - 1)
                html_parts.extend(format_node_html(node, indent_level=0, is_last=is_last, parent_prefix=""))
    
    html_parts.append('</tbody>')
    html_parts.append('</table>')
    html_parts.append('</div>')
    return ''.join(html_parts)

def analyze_runbook_task_trends(runlogs_data):
    """Analyze execution time trends for runbooks and tasks across all apps.
    
    This function aggregates execution times for each unique runbook and task
    across all applications to identify trends, consistency, and variations.
    Focuses on summary statistics to keep it readable even with 10K+ apps.
    
    Args:
        runlogs_data (dict): Dictionary mapping blueprint_uuid -> parsed runlogs tree data
    
    Returns:
        dict: Dictionary with 'runbooks' and 'tasks' keys, each containing:
              {
                  'name': {
                      'name': Runbook/task name,
                      'count': Number of executions,
                      'app_count': Number of unique apps,
                      'avg_duration': Average time (seconds),
                      'min_duration': Min time (seconds),
                      'max_duration': Max time (seconds),
                      'std_dev': Standard deviation (seconds),
                      'consistency': 'High'/'Medium'/'Low',
                      'cv_percent': Coefficient of variation %
                  }
              }
    """
    import statistics
    
    runbook_stats = {}  # name -> {count, durations, apps}
    task_stats = {}     # name -> {count, durations, apps}
    
    if not runlogs_data:
        return {'runbooks': {}, 'tasks': {}}
    
    # Process all runlogs data
    for blueprint_uuid, tree_data in runlogs_data.items():
        if not tree_data or 'forest' not in tree_data:
            continue
        
        # Traverse all trees and collect runbook/task data
        def collect_node_data(node):
            """Recursively collect runbook and task execution data."""
            node_type = node.get('type', '')
            duration = node.get('duration_seconds')
            
            if node_type == 'runbook_runlog' and duration is not None and duration > 0:
                runbook_name = node.get('runbook_name') or 'Unknown'
                if runbook_name not in runbook_stats:
                    runbook_stats[runbook_name] = {
                        'name': runbook_name,
                        'count': 0,
                        'durations': [],
                        'apps': set()
                    }
                runbook_stats[runbook_name]['count'] += 1
                runbook_stats[runbook_name]['durations'].append(duration)
                runbook_stats[runbook_name]['apps'].add(blueprint_uuid)
            
            elif node_type == 'task_runlog' and duration is not None and duration > 0:
                task_name = node.get('task_name') or 'Unknown'
                if task_name not in task_stats:
                    task_stats[task_name] = {
                        'name': task_name,
                        'count': 0,
                        'durations': [],
                        'apps': set()
                    }
                task_stats[task_name]['count'] += 1
                task_stats[task_name]['durations'].append(duration)
                task_stats[task_name]['apps'].add(blueprint_uuid)
            
            # Recursively process children
            for child in node.get('children', []):
                collect_node_data(child)
        
        # Process all nodes in this tree
        for root_tree in tree_data.get('forest', []):
            for root_node in root_tree.get('nodes', []):
                collect_node_data(root_node)
    
    # Calculate statistics for runbooks
    runbook_results = {}
    for name, data in runbook_stats.items():
        durations = data['durations']
        if durations and len(durations) > 0:
            avg = statistics.mean(durations)
            min_dur = min(durations)
            max_dur = max(durations)
            std_dev = statistics.stdev(durations) if len(durations) > 1 else 0
            
            # Calculate consistency (coefficient of variation)
            if avg > 0:
                cv = (std_dev / avg) * 100
                if cv < 20:
                    consistency = 'High'
                elif cv < 50:
                    consistency = 'Medium'
                else:
                    consistency = 'Low'
            else:
                consistency = 'N/A'
                cv = 0
            
            runbook_results[name] = {
                'name': name,
                'count': data['count'],
                'app_count': len(data['apps']),
                'avg_duration': avg,
                'min_duration': min_dur,
                'max_duration': max_dur,
                'std_dev': std_dev,
                'consistency': consistency,
                'cv_percent': cv
            }
    
    # Calculate statistics for tasks
    task_results = {}
    for name, data in task_stats.items():
        durations = data['durations']
        if durations and len(durations) > 0:
            avg = statistics.mean(durations)
            min_dur = min(durations)
            max_dur = max(durations)
            std_dev = statistics.stdev(durations) if len(durations) > 1 else 0
            
            # Calculate consistency (coefficient of variation)
            if avg > 0:
                cv = (std_dev / avg) * 100
                if cv < 20:
                    consistency = 'High'
                elif cv < 50:
                    consistency = 'Medium'
                else:
                    consistency = 'Low'
            else:
                consistency = 'N/A'
                cv = 0
            
            task_results[name] = {
                'name': name,
                'count': data['count'],
                'app_count': len(data['apps']),
                'avg_duration': avg,
                'min_duration': min_dur,
                'max_duration': max_dur,
                'std_dev': std_dev,
                'consistency': consistency,
                'cv_percent': cv
            }
    
    print(f"[INFO] Trend analysis: Found {len(runbook_results)} unique runbooks, {len(task_results)} unique tasks")
    return {
        'runbooks': runbook_results,
        'tasks': task_results
    }

def normalize_runbook_task_name(name):
    """Normalize runbook/task names by removing UUID suffixes.
    
    Examples:
        SYS_GEN__Runbook_Application_16ec9fea_3b01_495a_86ae_4b7c909d3d1b
        -> SYS_GEN__Runbook_Application
        
        SYS_GEN__Runbook_Package_9f4b1f88_aeea_4046_82ff_7bcc0779251f
        -> SYS_GEN__Runbook_Package
        
        Linux___create___runbook (no UUID) -> Linux___create___runbook
    
    Args:
        name (str): Original runbook/task name
    
    Returns:
        str: Normalized name with UUID removed
    """
    if not name:
        return name
    
    import re
    
    # Pattern 1: Match UUID at the end (underscore separated hex segments)
    # e.g., _16ec9fea_3b01_495a_86ae_4b7c909d3d1b
    uuid_pattern = r'_[0-9a-f]{8}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{12}$'
    normalized = re.sub(uuid_pattern, '', name, flags=re.IGNORECASE)
    
    # Pattern 2: Also handle UUIDs with dashes (less common but possible)
    # e.g., _16ec9fea-3b01-495a-86ae-4b7c909d3d1b
    uuid_pattern2 = r'_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    normalized = re.sub(uuid_pattern2, '', normalized, flags=re.IGNORECASE)
    
    return normalized

def build_trend_tables_and_graphs(runlogs_data):
    """Build interactive trend analysis with execution time across apps for each task/runbook.
    
    Creates:
    1. Interactive Plotly graphs showing execution time trends across apps
    2. Summary tables with min, max, avg, P95 statistics
    
    Note: Runbook/task names are normalized to remove UUID suffixes, so that the same
    logical runbook type (e.g., SYS_GEN__Runbook_Application) is aggregated across all apps.
    
    Args:
        runlogs_data (dict): Dictionary mapping blueprint_uuid -> parsed runlogs tree data
    
    Returns:
        dict: {
            'runbook_graph_html': str (Plotly HTML),
            'task_graph_html': str (Plotly HTML),
            'runbook_table_html': str (HTML table),
            'task_table_html': str (HTML table)
        }
    """
    import statistics
    
    # Collect execution data: {normalized_name: [(app_name, duration), ...]}
    runbook_executions = defaultdict(list)  # runbook_name -> [(app_uuid, duration), ...]
    task_executions = defaultdict(list)      # task_name -> [(app_uuid, duration), ...]
    
    if not runlogs_data:
        return {
            'runbook_graph_html': None,
            'task_graph_html': None,
            'runbook_table_html': None,
            'task_table_html': None
        }
    
    # Collect all execution data
    apps_with_runbook_executions = set()
    apps_with_task_executions = set()
    apps_with_no_runbook_executions = []
    apps_with_no_task_executions = []
    
    for app_uuid, tree_data in runlogs_data.items():
        if not tree_data or 'forest' not in tree_data:
            apps_with_no_runbook_executions.append(app_uuid)
            apps_with_no_task_executions.append(app_uuid)
            continue
        
        has_runbook = False
        has_task = False
        
        def collect_executions(node, app_uuid):
            """Recursively collect execution data with normalized names."""
            nonlocal has_runbook, has_task
            node_type = node.get('type', '')
            duration = node.get('duration_seconds')
            
            if node_type == 'runbook_runlog' and duration is not None and duration > 0:
                has_runbook = True
                runbook_name = node.get('runbook_name') or 'Unknown'
                # Normalize the runbook name to remove UUID suffixes
                normalized_name = normalize_runbook_task_name(runbook_name)
                runbook_executions[normalized_name].append((app_uuid, duration))
            
            elif node_type == 'task_runlog' and duration is not None and duration > 0:
                has_task = True
                task_name = node.get('task_name') or 'Unknown'
                # Normalize the task name to remove UUID suffixes
                normalized_name = normalize_runbook_task_name(task_name)
                task_executions[normalized_name].append((app_uuid, duration))
            
            # Recursively process children
            for child in node.get('children', []):
                collect_executions(child, app_uuid)
        
        # Process all nodes in this app's tree
        for root_tree in tree_data.get('forest', []):
            for root_node in root_tree.get('nodes', []):
                collect_executions(root_node, app_uuid)
        
        # Track which apps contributed executions
        if has_runbook:
            apps_with_runbook_executions.add(app_uuid)
        else:
            apps_with_no_runbook_executions.append(app_uuid)
        
        if has_task:
            apps_with_task_executions.add(app_uuid)
        else:
            apps_with_no_task_executions.append(app_uuid)
    
    # Debug logging for missing apps
    if apps_with_no_runbook_executions:
        debug_log(f"[DEBUG] Apps with no runbook executions ({len(apps_with_no_runbook_executions)}): {apps_with_no_runbook_executions[:5]}{'...' if len(apps_with_no_runbook_executions) > 5 else ''}")
    if apps_with_no_task_executions:
        debug_log(f"[DEBUG] Apps with no task executions ({len(apps_with_no_task_executions)}): {apps_with_no_task_executions[:5]}{'...' if len(apps_with_no_task_executions) > 5 else ''}")
    
    debug_log(f"[DEBUG] Apps contributing runbook executions: {len(apps_with_runbook_executions)}")
    debug_log(f"[DEBUG] Apps contributing task executions: {len(apps_with_task_executions)}")
    
    print(f"[INFO] Collected execution data (after normalization):")
    print(f"       - {len(runbook_executions)} unique runbook types")
    print(f"       - {len(task_executions)} unique task types")
    
    # Show example normalizations
    if runbook_executions:
        sample_runbooks = list(runbook_executions.keys())[:3]
        print(f"       - Sample runbooks: {', '.join(sample_runbooks)}")
    if task_executions:
        sample_tasks = list(task_executions.keys())[:3]
        print(f"       - Sample tasks: {', '.join(sample_tasks)}")
    
    # Generate interactive Plotly graphs if available
    runbook_graph_html = None
    task_graph_html = None
    
    if PLOTLY_AVAILABLE:
        # Generate Runbook Trend Graph
        if runbook_executions:
            try:
                fig = go.Figure()
                
                # Add a trace for each runbook
                for runbook_name, executions in sorted(runbook_executions.items()):
                    # Sort by app_uuid for consistent x-axis
                    executions_sorted = sorted(executions, key=lambda x: x[0])
                    durations = [e[1] for e in executions_sorted]
                    
                    # X-axis labels: shortened app names
                    app_names_short = [e[0][:12] + '...' for e in executions_sorted]
                    
                    # Create hover text with full app UUID and formatted duration
                    hover_texts = []
                    for app_uuid, duration in executions_sorted:
                        hover_texts.append(
                            f"<b>{runbook_name}</b><br>" +
                            f"<b>App:</b> {app_uuid}<br>" +
                            f"<b>Duration:</b> {format_duration(duration)}"
                        )
                    
                    fig.add_trace(go.Scatter(
                        x=app_names_short,  # Use app names instead of indices
                        y=durations,
                        mode='lines+markers',
                        name=runbook_name[:50],  # Truncate long names
                        hovertext=hover_texts,
                        hoverinfo='text',
                        visible=True  # All visible by default
                    ))
                
                fig.update_layout(
                    title="Runbook Execution Time Trends Across All Apps<br><sub>Click legend items to show/hide specific runbooks</sub>",
                    xaxis_title="App Name (hover for full UUID)",
                    yaxis_title="Execution Time (seconds)",
                    xaxis=dict(
                        tickangle=-45,  # Angle labels for readability
                        tickmode='auto',
                        nticks=20  # Limit number of ticks for readability
                    ),
                    hovermode='closest',
                    height=600,
                    showlegend=True,
                    legend=dict(
                        title="Runbooks (click to show/hide)",
                        orientation="v",
                        yanchor="top",
                        y=1,
                        xanchor="left",
                        x=1.02
                    ),
                    margin=dict(b=100)  # Extra margin for angled labels
                )
                
                runbook_graph_html = fig.to_html(include_plotlyjs='cdn', div_id='runbook_trends_graph')
                print("[INFO] Generated interactive runbook trends graph")
            except Exception as e:
                print(f"[WARNING] Failed to generate runbook trends graph: {e}")
        
        # Generate Task Trend Graph
        if task_executions:
            try:
                fig = go.Figure()
                
                # Add a trace for each task
                for task_name, executions in sorted(task_executions.items()):
                    # Sort by app_uuid for consistent x-axis
                    executions_sorted = sorted(executions, key=lambda x: x[0])
                    durations = [e[1] for e in executions_sorted]
                    
                    # X-axis labels: shortened app names
                    app_names_short = [e[0][:12] + '...' for e in executions_sorted]
                    
                    # Create hover text with full app UUID
                    hover_texts = []
                    for app_uuid, duration in executions_sorted:
                        hover_texts.append(
                            f"<b>{task_name}</b><br>" +
                            f"<b>App:</b> {app_uuid}<br>" +
                            f"<b>Duration:</b> {format_duration(duration)}"
                        )
                    
                    fig.add_trace(go.Scatter(
                        x=app_names_short,  # Use app names instead of indices
                        y=durations,
                        mode='lines+markers',
                        name=task_name[:50],  # Truncate long names
                        hovertext=hover_texts,
                        hoverinfo='text',
                        visible=True
                    ))
                
                fig.update_layout(
                    title="Task Execution Time Trends Across All Apps<br><sub>Click legend items to show/hide specific tasks</sub>",
                    xaxis_title="App Name (hover for full UUID)",
                    yaxis_title="Execution Time (seconds)",
                    xaxis=dict(
                        tickangle=-45,  # Angle labels for readability
                        tickmode='auto',
                        nticks=20  # Limit number of ticks for readability
                    ),
                    hovermode='closest',
                    height=600,
                    showlegend=True,
                    legend=dict(
                        title="Tasks (click to show/hide)",
                        orientation="v",
                        yanchor="top",
                        y=1,
                        xanchor="left",
                        x=1.02
                    ),
                    margin=dict(b=100)  # Extra margin for angled labels
                )
                
                task_graph_html = fig.to_html(include_plotlyjs='cdn', div_id='task_trends_graph')
                print("[INFO] Generated interactive task trends graph")
            except Exception as e:
                print(f"[WARNING] Failed to generate task trends graph: {e}")
    else:
        print("[WARNING] Plotly not available - interactive trend graphs will not be generated")
    
    # Generate summary tables
    runbook_table_html = None
    task_table_html = None
    
    # Calculate statistics and build runbook table
    if runbook_executions:
        runbook_stats = []
        for runbook_name, executions in sorted(runbook_executions.items()):
            durations = [e[1] for e in executions]
            app_uuids = [e[0] for e in executions]
            
            if durations:
                min_dur = min(durations)
                max_dur = max(durations)
                avg_dur = statistics.mean(durations)
                # Calculate 95th percentile
                sorted_durs = sorted(durations)
                p95_index = int(len(sorted_durs) * 0.95)
                p95_dur = sorted_durs[p95_index] if p95_index < len(sorted_durs) else sorted_durs[-1]
                
                # Get app UUIDs for min and max (full UUID for hover, shortened for display)
                min_app_full = app_uuids[durations.index(min_dur)]
                max_app_full = app_uuids[durations.index(max_dur)]
                min_app_short = min_app_full[:12] + '...' if len(min_app_full) > 15 else min_app_full
                max_app_short = max_app_full[:12] + '...' if len(max_app_full) > 15 else max_app_full
                
                # Build app list for all apps
                app_list_str = ', '.join([a[:12] + '...' for a in app_uuids[:10]])
                if len(app_uuids) > 10:
                    app_list_str += f' ... and {len(app_uuids) - 10} more'
                
                runbook_stats.append({
                    'name': runbook_name,
                    'count': len(durations),
                    'min': min_dur,
                    'min_app': min_app_short,
                    'min_app_full': min_app_full,
                    'max': max_dur,
                    'max_app': max_app_short,
                    'max_app_full': max_app_full,
                    'avg': avg_dur,
                    'p95': p95_dur,
                    'app_list': app_list_str,
                    'app_uuids': app_uuids  # Keep full list for graph
                })
        
        # Build HTML table with improved tree-style formatting
        if runbook_stats:
            table_html = '<table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 0.9em; box-shadow: 0 4px 12px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden;">'
            table_html += '<thead><tr style="background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%); color: white;">'
            table_html += '<th style="padding: 14px 12px; text-align: left; border: 2px solid #1e8449; font-weight: bold; font-size: 0.95em; letter-spacing: 0.5px;">📋 Runbook Name</th>'
            table_html += '<th style="padding: 14px 12px; text-align: center; border: 2px solid #1e8449; font-weight: bold; font-size: 0.95em;">Executions</th>'
            table_html += '<th style="padding: 14px 12px; text-align: right; border: 2px solid #1e8449; font-weight: bold; font-size: 0.95em;">Min Time<br><span style="font-size: 0.8em; font-weight: normal; opacity: 0.9;">(app)</span></th>'
            table_html += '<th style="padding: 14px 12px; text-align: right; border: 2px solid #1e8449; font-weight: bold; font-size: 0.95em;">Avg Time</th>'
            table_html += '<th style="padding: 14px 12px; text-align: right; border: 2px solid #1e8449; font-weight: bold; font-size: 0.95em;">P95 Time</th>'
            table_html += '<th style="padding: 14px 12px; text-align: right; border: 2px solid #1e8449; font-weight: bold; font-size: 0.95em;">Max Time<br><span style="font-size: 0.8em; font-weight: normal; opacity: 0.9;">(app)</span></th>'
            table_html += '</tr></thead><tbody>'
            
            for idx, stat in enumerate(runbook_stats):
                # Alternating row colors with tree-style left border
                if idx % 2 == 0:
                    bg_color = '#f0f8f5'  # Very light green
                    border_color = '#27ae60'
                else:
                    bg_color = '#ffffff'
                    border_color = '#2ecc71'
                
                # Print full UUIDs directly (no tooltip)
                min_app_full_escaped = html.escape(stat["min_app_full"])
                max_app_full_escaped = html.escape(stat["max_app_full"])
                
                table_html += f'<tr style="background-color: {bg_color}; border-left: 4px solid {border_color}; transition: background-color 0.2s ease;">'
                table_html += f'<td style="padding: 12px; border: 1px solid #bdc3c7; font-family: monospace; font-size: 0.9em;">'
                table_html += f'<strong style="color: #27ae60; font-weight: 600;">{html.escape(stat["name"])}</strong>'
                table_html += '</td>'
                table_html += f'<td style="padding: 12px; text-align: center; border: 1px solid #bdc3c7; font-weight: 600; color: #2c3e50;">{stat["count"]}</td>'
                # Min time with full UUID displayed
                table_html += f'<td style="padding: 12px; text-align: right; border: 1px solid #bdc3c7;">'
                table_html += f'<strong style="color: #27ae60; font-size: 1.05em;">{format_duration(stat["min"])}</strong><br>'
                table_html += f'<span style="font-size: 0.65em; color: #7f8c8d; font-family: monospace; word-break: break-all;">{min_app_full_escaped}</span>'
                table_html += '</td>'
                # Avg and P95 (no app names)
                table_html += f'<td style="padding: 12px; text-align: right; border: 1px solid #bdc3c7;"><strong style="color: #2c3e50;">{format_duration(stat["avg"])}</strong></td>'
                table_html += f'<td style="padding: 12px; text-align: right; border: 1px solid #bdc3c7;"><strong style="color: #2c3e50;">{format_duration(stat["p95"])}</strong></td>'
                # Max time with full UUID displayed
                table_html += f'<td style="padding: 12px; text-align: right; border: 1px solid #bdc3c7;">'
                table_html += f'<strong style="color: #e74c3c; font-size: 1.05em;">{format_duration(stat["max"])}</strong><br>'
                table_html += f'<span style="font-size: 0.65em; color: #7f8c8d; font-family: monospace; word-break: break-all;">{max_app_full_escaped}</span>'
                table_html += '</td>'
                table_html += '</tr>'
            
            table_html += '</tbody></table>'
            runbook_table_html = table_html
    
    # Calculate statistics and build task table
    if task_executions:
        task_stats = []
        for task_name, executions in sorted(task_executions.items()):
            durations = [e[1] for e in executions]
            app_uuids = [e[0] for e in executions]
            
            if durations:
                min_dur = min(durations)
                max_dur = max(durations)
                avg_dur = statistics.mean(durations)
                sorted_durs = sorted(durations)
                p95_index = int(len(sorted_durs) * 0.95)
                p95_dur = sorted_durs[p95_index] if p95_index < len(sorted_durs) else sorted_durs[-1]
                
                # Get app UUIDs for min and max
                min_app_full = app_uuids[durations.index(min_dur)]
                max_app_full = app_uuids[durations.index(max_dur)]
                min_app_short = min_app_full[:12] + '...' if len(min_app_full) > 15 else min_app_full
                max_app_short = max_app_full[:12] + '...' if len(max_app_full) > 15 else max_app_full
                
                app_list_str = ', '.join([a[:12] + '...' for a in app_uuids[:10]])
                if len(app_uuids) > 10:
                    app_list_str += f' ... and {len(app_uuids) - 10} more'
                
                task_stats.append({
                    'name': task_name,
                    'count': len(durations),
                    'min': min_dur,
                    'min_app': min_app_short,
                    'min_app_full': min_app_full,
                    'max': max_dur,
                    'max_app': max_app_short,
                    'max_app_full': max_app_full,
                    'avg': avg_dur,
                    'p95': p95_dur,
                    'app_list': app_list_str,
                    'app_uuids': app_uuids
                })
        
        # Build HTML table with improved tree-style formatting
        if task_stats:
            table_html = '<table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 0.9em; box-shadow: 0 4px 12px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden;">'
            table_html += '<thead><tr style="background: linear-gradient(135deg, #e67e22 0%, #f39c12 100%); color: white;">'
            table_html += '<th style="padding: 14px 12px; text-align: left; border: 2px solid #d35400; font-weight: bold; font-size: 0.95em; letter-spacing: 0.5px;">⚙️ Task Name</th>'
            table_html += '<th style="padding: 14px 12px; text-align: center; border: 2px solid #d35400; font-weight: bold; font-size: 0.95em;">Executions</th>'
            table_html += '<th style="padding: 14px 12px; text-align: right; border: 2px solid #d35400; font-weight: bold; font-size: 0.95em;">Min Time<br><span style="font-size: 0.8em; font-weight: normal; opacity: 0.9;">(app)</span></th>'
            table_html += '<th style="padding: 14px 12px; text-align: right; border: 2px solid #d35400; font-weight: bold; font-size: 0.95em;">Avg Time</th>'
            table_html += '<th style="padding: 14px 12px; text-align: right; border: 2px solid #d35400; font-weight: bold; font-size: 0.95em;">P95 Time</th>'
            table_html += '<th style="padding: 14px 12px; text-align: right; border: 2px solid #d35400; font-weight: bold; font-size: 0.95em;">Max Time<br><span style="font-size: 0.8em; font-weight: normal; opacity: 0.9;">(app)</span></th>'
            table_html += '</tr></thead><tbody>'
            
            for idx, stat in enumerate(task_stats):
                # Alternating row colors with tree-style left border
                if idx % 2 == 0:
                    bg_color = '#fef5e7'  # Very light orange
                    border_color = '#e67e22'
                else:
                    bg_color = '#ffffff'
                    border_color = '#f39c12'
                
                # Print full UUIDs directly (no tooltip)
                min_app_full_escaped = html.escape(stat["min_app_full"])
                max_app_full_escaped = html.escape(stat["max_app_full"])
                
                table_html += f'<tr style="background-color: {bg_color}; border-left: 4px solid {border_color}; transition: background-color 0.2s ease;">'
                table_html += f'<td style="padding: 12px; border: 1px solid #bdc3c7; font-family: monospace; font-size: 0.9em;">'
                table_html += f'<strong style="color: #e67e22; font-weight: 600;">{html.escape(stat["name"])}</strong>'
                table_html += '</td>'
                table_html += f'<td style="padding: 12px; text-align: center; border: 1px solid #bdc3c7; font-weight: 600; color: #2c3e50;">{stat["count"]}</td>'
                # Min time with full UUID displayed
                table_html += f'<td style="padding: 12px; text-align: right; border: 1px solid #bdc3c7;">'
                table_html += f'<strong style="color: #27ae60; font-size: 1.05em;">{format_duration(stat["min"])}</strong><br>'
                table_html += f'<span style="font-size: 0.65em; color: #7f8c8d; font-family: monospace; word-break: break-all;">{min_app_full_escaped}</span>'
                table_html += '</td>'
                # Avg and P95 (no app names)
                table_html += f'<td style="padding: 12px; text-align: right; border: 1px solid #bdc3c7;"><strong style="color: #2c3e50;">{format_duration(stat["avg"])}</strong></td>'
                table_html += f'<td style="padding: 12px; text-align: right; border: 1px solid #bdc3c7;"><strong style="color: #2c3e50;">{format_duration(stat["p95"])}</strong></td>'
                # Max time with full UUID displayed
                table_html += f'<td style="padding: 12px; text-align: right; border: 1px solid #bdc3c7;">'
                table_html += f'<strong style="color: #e74c3c; font-size: 1.05em;">{format_duration(stat["max"])}</strong><br>'
                table_html += f'<span style="font-size: 0.65em; color: #7f8c8d; font-family: monospace; word-break: break-all;">{max_app_full_escaped}</span>'
                table_html += '</td>'
                table_html += '</tr>'
            
            table_html += '</tbody></table>'
            task_table_html = table_html
    
    return {
        'runbook_graph_html': runbook_graph_html,
        'task_graph_html': task_graph_html,
        'runbook_table_html': runbook_table_html,
        'task_table_html': task_table_html
    }

def generate_trend_graphs(trend_data, graph_prefix):
    """Legacy function - now handled by build_trend_tables_and_graphs.
    Kept for backward compatibility.
    """
    # This function is no longer used but kept to avoid breaking changes
    return (None, None)

def analyze_runbook_task_trends(runlogs_data):
    """Legacy function - now handled by build_trend_tables_and_graphs.
    Kept for backward compatibility.
    """
    # This function is no longer used but kept to avoid breaking changes
    return {'runbooks': {}, 'tasks': {}}

def main():
    parser = argparse.ArgumentParser(
        description="Analyze Nutanix app provisioning times",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using file with app names
  python3 update_stats.py --host nconprem-10-122-152-117.ccpnx.com --app-file ./log/app.csv
  
  # Using simple string (will match "lite" anywhere in app name)
  python3 update_stats.py --host nconprem-10-122-152-117.ccpnx.com --app-name lite
  
  # Using regex pattern
  python3 update_stats.py --host nconprem-10-122-152-117.ccpnx.com --app-name "foundation.*|multivm.*"
  
  # Custom auth
  python3 update_stats.py --host nconprem-10-122-152-117.ccpnx.com --app-name lite --username admin --password Nutanix.123
  
  # Custom output directory
  python3 update_stats.py --host nconprem-10-122-152-117.ccpnx.com --app-name lite --output ./reports/my_report
  
  # Custom average threshold for color coding (e.g., 22m 30s)
  python3 update_stats.py --host nconprem-10-122-152-117.ccpnx.com --app-name lite --avg-threshold "22m 30s"
  
  # Disable debug logs
  python3 update_stats.py --host nconprem-10-122-152-117.ccpnx.com --app-name lite --no-debug

Output files (directory: nutanix-calm-blueprint-results):
  - <output>.csv - CSV table
  - <output>.html - HTML report
  - <output>_start_times.png - Graph showing start times
  - <output>_provisioning_times.png - Graph showing provisioning times
  - <output>.log - Console output log
  - Debug logs are written to the log file only
        """
    )
    parser.add_argument("--host", required=True, help="Host URL (e.g., nconprem-10-122-152-117.ccpnx.com)")
    parser.add_argument("--app-file", help="CSV file with app names for exact match (one per line)")
    parser.add_argument("--app-name", help="String or regex pattern to match app names (e.g., 'lite' or 'foundation.*')")
    parser.add_argument("--username", default="ssp_admin@qa.nutanix.com", help="Username for Basic Auth (default: ssp_admin@qa.nutanix.com)")
    parser.add_argument("--password", default="nutanix/4u", help="Password for Basic Auth (default: nutanix/4u)")
    parser.add_argument("--output", default="provisioning_stats", help="Output file prefix (default: 'provisioning_stats')")
    parser.add_argument("--avg-threshold", help="Custom average threshold for color coding (e.g., '22m 30s', '1350s', '1h 5m'). If not specified, calculates average from data.")
    debug_group = parser.add_mutually_exclusive_group()
    debug_group.add_argument("--debug", dest="debug", action="store_true", help="Enable debug logs (default: enabled, written to log file)")
    debug_group.add_argument("--no-debug", dest="debug", action="store_false", help="Disable debug logs")
    parser.set_defaults(debug=True)
    args = parser.parse_args()
    
    # Validate that either app-file or app-name is provided
    if not args.app_file and not args.app_name:
        print("[ERROR] Either --app-file or --app-name must be provided")
        return
    
    # Prepare output directory and logging (before heavy processing)
    output_dir = "nutanix-calm-blueprint-results"
    os.makedirs(output_dir, exist_ok=True)
    print(f"[INFO] Created output directory: {output_dir}")
    log_file = os.path.join(output_dir, f"{args.output}.log")
    log_handle = None
    global DEBUG_ENABLED, DEBUG_LOG_HANDLE
    DEBUG_ENABLED = args.debug
    try:
        log_handle = open(log_file, 'w', encoding='utf-8')
        sys.stdout = Tee(sys.stdout, log_handle)
        sys.stderr = Tee(sys.stderr, log_handle)
        DEBUG_LOG_HANDLE = log_handle
        print(f"[INFO] Logging console output to: {log_file}")
        if DEBUG_ENABLED:
            print("[INFO] Debug logs enabled (written to log file only)")
        else:
            print("[INFO] Debug logs disabled")
    except Exception as e:
        print(f"[WARNING] Unable to create log file at {log_file}: {e}")

    # Build API URL
    api_url = build_api_url(args.host)
    # Extract host and path
    from urllib.parse import urlparse
    parsed = urlparse(api_url)
    hostname = parsed.hostname
    port = parsed.port or 443
    
    # Setup connection
    conn = http.client.HTTPSConnection(
        host=hostname,
        port=port,
        context=ssl._create_unverified_context()
    )
    
    # Create Basic Auth header
    auth_token = create_basic_auth(args.username, args.password)
    headers = {
        'Content-Type': "application/json",
        'Authorization': f"Basic {auth_token}"
    }
    
    # Get app list
    print(f"[INFO] Querying Nutanix API: {api_url}")
    try:
        app_list = get_app_list(conn, headers)
    except Exception as e:
        print(f"[ERROR] Failed to query API: {e}")
        return
    
    if "entities" not in app_list:
        print(f"[ERROR] API query failed or no entities found: {app_list.get('message', 'Unknown error')}")
        return
    
    entities = app_list["entities"]
    print(f"[INFO] Found {len(entities)} apps in API response")
    
    # Filter apps
    if args.app_file:
        app_names = get_app_names_from_file(args.app_file)
        filtered_apps = filter_apps_by_list(entities, app_names)
        print(f"[INFO] Filtered to {len(filtered_apps)} apps from file: {args.app_file}")
    else:
        filtered_apps = filter_apps_by_regex(entities, args.app_name)
        print(f"[INFO] Filtered to {len(filtered_apps)} apps matching pattern: {args.app_name}")
    
    # Check if any apps were found
    if not filtered_apps:
        print("\n[INFO] No matching apps found.")
        if args.app_file:
            print(f"      Searched for apps from file: {args.app_file}")
            print(f"      Total apps in API response: {len(entities)}")
        else:
            print(f"      Pattern: {args.app_name}")
            print(f"      Total apps in API response: {len(entities)}")
        return
    
    # Process apps
    table_data = []
    for app in filtered_apps:
        status = app.get("status", {})
        resources = status.get("resources", {})
        
        app_name = status.get("name", "N/A")
        app_uuid = status.get("uuid", "N/A")  # This is the app's UUID
        creation_time = status.get("creation_time")
        last_update_time = status.get("last_update_time")
        
        # Blueprint UUID is the app's UUID (status.uuid), not from blueprint_reference
        # This UUID is used for the API call: /api/calm/v3.0/apps/{app_uuid}/app_runlogs/list
        blueprint_uuid = app_uuid
        
        # Get source marketplace name
        source_marketplace_name = resources.get("source_marketplace_name", "N/A")
        
        # Get state from status (not protection_status.state)
        app_state = status.get("state", "N/A")
        
        # Validate timestamps
        if not creation_time or not last_update_time:
            print(f"[WARNING] Skipping {app_name}: missing timestamps")
            continue
        
        # Ensure timestamps are integers (handle string timestamps if any)
        try:
            creation_time = int(creation_time)
            last_update_time = int(last_update_time)
        except (ValueError, TypeError):
            print(f"[WARNING] Skipping {app_name}: invalid timestamp format")
            continue
        
        # Validate timestamp ranges (reasonable Unix timestamp range)
        # Timestamps should be in microseconds (e.g., 1763580604454895)
        # This corresponds to dates roughly between 2000 and 2100
        min_valid = 946684800000000  # 2000-01-01 in microseconds
        max_valid = 4102444800000000  # 2100-01-01 in microseconds
        
        if not (min_valid <= creation_time <= max_valid) or not (min_valid <= last_update_time <= max_valid):
            print(f"[WARNING] Skipping {app_name}: timestamp out of valid range")
            continue
        
        # Calculate provisioning time (difference in microseconds, then convert to seconds)
        if last_update_time < creation_time:
            print(f"[WARNING] Skipping {app_name}: last_update_time ({last_update_time}) < creation_time ({creation_time})")
            continue
        
        # Calculate provisioning time (difference in microseconds, then convert to seconds)
        diff_microseconds = last_update_time - creation_time
        diff_seconds = diff_microseconds / 1_000_000.0
        
        # Format timestamps with timezone indicator
        creation_time_str = format_timestamp(creation_time)
        last_update_time_str = format_timestamp(last_update_time)
        duration_str = format_duration(diff_seconds)
        
        table_data.append([
            app_name,
            creation_time_str,
            last_update_time_str,
            duration_str,
            app_state,
            blueprint_uuid,
            source_marketplace_name,
            # Store raw data for graphs (timestamps in microseconds, duration in seconds)
            creation_time,  # raw timestamp
            last_update_time,  # raw timestamp
            diff_seconds  # raw duration in seconds
        ])
    
    print(f"[INFO] Processed {len(table_data)} apps")
    
    # Calculate total provisioning time across filtered apps only
    # Find min creation time and max last update time from the filtered apps
    total_provisioning_info = None
    if table_data:
        # Extract raw timestamps from table_data (which contains only filtered apps)
        # Row structure: [app_name, creation_time_str, update_time_str, duration_str, state, blueprint_uuid, marketplace_name,
        #                  creation_time_raw (index 7), last_update_time_raw (index 8), duration_seconds_raw (index 9)]
        creation_times = []
        last_update_times = []
        for row in table_data:
            if len(row) >= 9:
                creation_time_raw = row[7]  # Raw timestamp in microseconds
                last_update_time_raw = row[8]  # Raw timestamp in microseconds
                if creation_time_raw and last_update_time_raw:
                    creation_times.append(creation_time_raw)
                    last_update_times.append(last_update_time_raw)
        
        if creation_times and last_update_times:
            min_creation_time = min(creation_times)
            max_last_update_time = max(last_update_times)
            total_provisioning_seconds = (max_last_update_time - min_creation_time) / 1_000_000.0
            
            # Format timestamps for display
            min_creation_time_str = format_timestamp(min_creation_time)
            max_last_update_time_str = format_timestamp(max_last_update_time)
            total_provisioning_duration_str = format_duration(total_provisioning_seconds)
            
            total_provisioning_info = {
                'min_creation_time': min_creation_time,
                'max_last_update_time': max_last_update_time,
                'min_creation_time_str': min_creation_time_str,
                'max_last_update_time_str': max_last_update_time_str,
                'total_provisioning_seconds': total_provisioning_seconds,
                'total_provisioning_duration_str': total_provisioning_duration_str,
                'total_apps': len(table_data)
            }
            
            # State breakdown and running-app provisioning stats (for expanded summary)
            count_error = 0
            count_running = 0
            count_provisioning = 0
            count_unknown = 0
            running_durations = []
            for row in table_data:
                if len(row) < 10:
                    continue
                state_lower = str(row[4]).strip().lower()
                dur_raw = row[9]
                if state_lower == 'error':
                    count_error += 1
                elif state_lower == 'running':
                    count_running += 1
                    if dur_raw is not None and (isinstance(dur_raw, (int, float)) and dur_raw >= 0):
                        running_durations.append(float(dur_raw))
                elif state_lower == 'provisioning':
                    count_provisioning += 1
                else:
                    count_unknown += 1
            total_apps_summary = len(table_data)
            pass_pct = (count_running / total_apps_summary * 100.0) if total_apps_summary else 0.0
            total_provisioning_info['count_error'] = count_error
            total_provisioning_info['count_running'] = count_running
            total_provisioning_info['count_provisioning'] = count_provisioning
            total_provisioning_info['count_unknown'] = count_unknown
            total_provisioning_info['pass_pct'] = pass_pct
            if running_durations:
                total_provisioning_info['min_provisioning_seconds'] = min(running_durations)
                total_provisioning_info['max_provisioning_seconds'] = max(running_durations)
                sorted_d = sorted(running_durations)
                p95_idx = min(len(sorted_d) - 1, max(0, int(0.95 * len(sorted_d))))
                total_provisioning_info['p95_provisioning_seconds'] = sorted_d[p95_idx]
            else:
                total_provisioning_info['min_provisioning_seconds'] = None
                total_provisioning_info['max_provisioning_seconds'] = None
                total_provisioning_info['p95_provisioning_seconds'] = None
            
            print(f"[INFO] Total provisioning time calculation (for {len(table_data)} filtered apps):")
            print(f"       Min Creation Time (IST): {min_creation_time_str}")
            print(f"       Max Last Update Time (IST): {max_last_update_time_str}")
            print(f"       Total Time to Provision All Filtered Apps: {total_provisioning_duration_str}")
    
    # Fetch runlogs for each blueprint UUID
    print("\n[INFO] Fetching runlogs for each Blueprint UUID...")
    runlogs_data = {}
    runlog_errors = []  # Track detailed error information
    unique_blueprint_uuids = set()
    for row in table_data:
        blueprint_uuid = row[5]  # Blueprint UUID is at index 5
        if blueprint_uuid != "N/A" and blueprint_uuid:
            unique_blueprint_uuids.add(blueprint_uuid)
    
    print(f"[INFO] Found {len(unique_blueprint_uuids)} unique Blueprint UUIDs to fetch runlogs for")
    
    for blueprint_uuid in unique_blueprint_uuids:
        print(f"[INFO] Fetching runlogs for Blueprint UUID: {blueprint_uuid}")
        runlogs_json = get_app_runlogs(hostname, port, headers, blueprint_uuid)
        
        # Check if it's an error response
        if runlogs_json and isinstance(runlogs_json, dict) and runlogs_json.get('error'):
            error_info = {
                'blueprint_uuid': blueprint_uuid,
                'status_code': runlogs_json.get('status_code'),
                'response': runlogs_json.get('response'),
                'api_path': runlogs_json.get('api_path'),
                'api_method': runlogs_json.get('api_method'),
                'api_payload': runlogs_json.get('api_payload'),
                'exception': runlogs_json.get('exception')
            }
            runlog_errors.append(error_info)
            print(f"[ERROR] Failed to fetch runlogs for {blueprint_uuid}:")
            print(f"        API: {runlogs_json.get('api_method')} {runlogs_json.get('api_path')}")
            print(f"        Status: {runlogs_json.get('status_code')}")
            print(f"        Payload: {runlogs_json.get('api_payload')}")
            print(f"        Response: {runlogs_json.get('response')[:200] if runlogs_json.get('response') else 'None'}")
            if runlogs_json.get('exception'):
                print(f"        Exception: {runlogs_json.get('exception')}")
            continue
        
        if runlogs_json:
            # Check if we have entities
            entities_count = len(runlogs_json.get('entities', []))
            print(f"[INFO] Received {entities_count} runlog entities for Blueprint UUID: {blueprint_uuid}")
            
            # Log entity types for debugging
            if entities_count > 0:
                entity_types = {}
                for entity in runlogs_json.get('entities', []):
                    etype = entity.get("status", {}).get("type", "unknown")
                    entity_types[etype] = entity_types.get(etype, 0) + 1
                debug_log(f"[DEBUG] Entity types received: {entity_types}")
            
            parsed_runlogs = parse_runlogs_json(runlogs_json)
            if parsed_runlogs and parsed_runlogs.get('forest'):
                forest_count = len(parsed_runlogs.get('forest', []))
                total_nodes = sum(len(tree.get('nodes', [])) for tree in parsed_runlogs.get('forest', []))
                print(f"[INFO] Successfully parsed runlogs for Blueprint UUID: {blueprint_uuid} (forest: {forest_count} roots, {total_nodes} total nodes)")
                runlogs_data[blueprint_uuid] = parsed_runlogs
            else:
                error_info = {
                    'blueprint_uuid': blueprint_uuid,
                    'status_code': 200,
                    'response': f'Parsed but no forest (entities: {entities_count})',
                    'api_path': f'/api/calm/v3.0/apps/{blueprint_uuid}/app_runlogs/list',
                    'api_method': 'POST',
                    'api_payload': f'application_reference=={blueprint_uuid};(type==action_runlog,...)',
                    'exception': 'No forest in parsed runlogs'
                }
                runlog_errors.append(error_info)
                print(f"[WARNING] Failed to parse runlogs for Blueprint UUID: {blueprint_uuid} (entities count: {entities_count}, parsed: {parsed_runlogs is not None})")
        else:
            error_info = {
                'blueprint_uuid': blueprint_uuid,
                'status_code': None,
                'response': 'No data returned',
                'api_path': f'/api/calm/v3.0/apps/{blueprint_uuid}/app_runlogs/list',
                'api_method': 'POST',
                'api_payload': f'application_reference=={blueprint_uuid};(type==action_runlog,...)',
                'exception': 'Function returned None'
            }
            runlog_errors.append(error_info)
            print(f"[WARNING] No runlogs data returned for Blueprint UUID: {blueprint_uuid}")
    
    print(f"[INFO] Successfully fetched runlogs for {len(runlogs_data)} Blueprint UUIDs")
    
    # Check for apps missing runlogs data
    apps_with_runlogs = set(runlogs_data.keys())
    apps_missing_runlogs = unique_blueprint_uuids - apps_with_runlogs
    if apps_missing_runlogs:
        print(f"[WARNING] {len(apps_missing_runlogs)} apps have no runlogs data:")
        for uuid in list(apps_missing_runlogs)[:5]:
            print(f"       - {uuid}")
        if len(apps_missing_runlogs) > 5:
            print(f"       ... and {len(apps_missing_runlogs) - 5} more")
    
    # Print detailed summary of runlog errors for debugging
    if runlog_errors:
        print(f"\n{'='*80}")
        print(f"[ERROR SUMMARY] {len(runlog_errors)} apps failed to fetch runlog data")
        print(f"{'='*80}")
        for idx, error in enumerate(runlog_errors, 1):
            print(f"\n[{idx}] Blueprint UUID: {error['blueprint_uuid']}")
            print(f"    API Method: {error.get('api_method', 'N/A')}")
            print(f"    API Path: {error.get('api_path', 'N/A')}")
            print(f"    Status Code: {error.get('status_code', 'N/A')}")
            print(f"    API Payload: {error.get('api_payload', 'N/A')}")
            if error.get('response'):
                response_str = str(error['response'])
                if len(response_str) > 500:
                    print(f"    Response (first 500 chars): {response_str[:500]}...")
                else:
                    print(f"    Response: {response_str}")
            if error.get('exception'):
                print(f"    Exception: {error.get('exception')}")
            print(f"    {'-'*76}")
        print(f"\n{'='*80}")
        debug_log(f"[DEBUG INFO] To debug, use the API details above to make direct API calls")
        print(f"{'='*80}\n")
    
    # Build trend analysis: interactive graphs and summary tables
    print("\n[INFO] Building interactive trend analysis for runbooks and tasks across all apps...")
    trend_analysis = build_trend_tables_and_graphs(runlogs_data)
    
    # Parse custom average threshold if provided
    custom_avg_seconds = None
    if args.avg_threshold:
        custom_avg_seconds = parse_duration_to_seconds(args.avg_threshold)
        print(f"[INFO] Using custom average threshold: {args.avg_threshold} ({format_duration(custom_avg_seconds)})")
    else:
        print("[INFO] Average threshold will be calculated from data")
    
    # Generate output files in the directory
    csv_file = os.path.join(output_dir, f"{args.output}.csv")
    html_file = os.path.join(output_dir, f"{args.output}.html")
    graph_prefix = os.path.join(output_dir, args.output)
    
    generate_table(table_data, csv_file)
    generate_html(table_data, html_file, args.host, custom_avg=custom_avg_seconds, runlogs_data=runlogs_data, trend_analysis=trend_analysis, total_provisioning_info=total_provisioning_info, runlog_errors=runlog_errors)
    # Also generate standalone PNG files for reference
    generate_graphs(table_data, graph_prefix, embed_in_html=False, custom_avg=custom_avg_seconds)
    
    print(f"\n[SUCCESS] Analysis complete. Output files in '{output_dir}/':")
    print(f"  - {args.output}.csv")
    print(f"  - {args.output}.html (includes embedded graphs and interactive trend analysis)")
    print(f"  - {args.output}_start_times.png")
    print(f"  - {args.output}_provisioning_times.png")
    print(f"[INFO] HTML report location: {html_file}")
    if os.path.exists(log_file):
        print(f"[INFO] Console log saved at: {log_file}")
    
    # Show trend analysis summary
    if trend_analysis:
        has_runbook = trend_analysis.get('runbook_graph_html') is not None
        has_task = trend_analysis.get('task_graph_html') is not None
        if has_runbook or has_task:
            print("\n[INFO] Interactive trend analysis included in HTML report:")
            if has_runbook:
                print("  ✓ Runbook execution trends (interactive graph + summary table)")
            if has_task:
                print("  ✓ Task execution trends (interactive graph + summary table)")
            print("  → Click legend items in graphs to show/hide specific runbooks/tasks")
            print("  → Hover over data points to see app UUID and execution time")

if __name__ == "__main__":
    main()

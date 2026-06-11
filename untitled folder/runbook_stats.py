#!/usr/bin/env python3
"""
NCM Runbook Execution Statistics Analyzer
==========================================
Author: Manish Gupta
Contact: manish.gupta@nutanix.com

Description:
------------
Analyzes Nutanix Calm Manager (NCM) runbook execution logs and generates comprehensive
statistical reports with visualizations. This tool fetches runbook execution data (runlogs)
from the NCM API, processes execution metrics, and produces detailed HTML reports with
interactive tables and performance graphs.

Key Features:
-------------
- Fetches runbook execution logs from NCM API with pagination support
- Extracts execution metrics: task names, states, users, projects, endpoints, timings
- Calculates performance statistics: min, max, average, and P95 execution times
- Generates clickable task hierarchy showing runbook workflows and task relationships
- Creates visual reports: scatter plots, bar charts, and trend analysis graphs
- Supports filtering by task name (regex) and execution state
- Exports data to CSV and comprehensive HTML reports

API Endpoint:
-------------
  POST https://ncm.services.nconprem-<IP>.ccpnx.com/api/calm/v3.0/runbooks/runlogs/list

Data Model:
-----------
Each runlog entity represents a runbook execution with the following key fields:

  Identification:
    - metadata.uuid: Unique runlog identifier
    - status.action_reference.name: Task/action name
    - status.action_reference.kind: Action type (app_action)
  
  Execution Details:
    - status.state: Execution state (SUCCESS, FAILURE, RUNNING, etc.)
    - metadata.creation_time: Start timestamp (epoch microseconds)
    - metadata.last_update_time: End timestamp (epoch microseconds)
    - Execution Time: Calculated as (end_time - start_time) / 1,000,000 seconds
  
  Context:
    - status.userdata_reference.name: User who executed the runbook
    - metadata.project_reference.name: Project context
    - metadata.owner_reference: Owner information
  
  Runbook Structure:
    - status.runbook_json.resources.runbook: Runbook definition
    - status.runbook_json.resources.runbook.task_definition_list: Task hierarchy
    - status.runbook_json.resources.default_target_reference: Target endpoint

Hierarchical Tree Structure:
-----------------------------
The script builds a tree view for each runlog execution:

  Runlog: <uuid>
  ├── Action: <action_name>
  ├── State: <state>
  ├── User: <user_name>
  ├── Project: <project_name>
  ├── Endpoint: <endpoint_name>
  ├── Start: <start_time>
  ├── End: <end_time>
  └── Workflow: <workflow_name>
       ├── DAG: <dag_task_name>
       ├── VM_POWERON: <power_on_task>
       ├── VM_POWEROFF: <power_off_task>
       └── EXEC: <script_task>

Report Components:
------------------
1. Summary Statistics:
   - Total executions count
   - Breakdown by state (SUCCESS, FAILURE, RUNNING, etc.)
   - Success rate percentage
   - Execution time metrics (min, max, avg, P95) for successful runs

2. Detailed Data Table:
   - Sortable table with all runlog executions
   - Color-coded states: green (SUCCESS), red (FAILURE), orange (RUNNING)
   - Clickable task names that show full hierarchy tree in popup
   - Fields: Task, State, User, Project, Endpoint, Start Time, End Time, Duration

3. Visual Graphs:
   - Start Times Scatter Plot: Shows when runbooks were executed over time
   - Execution Times Bar Chart: Horizontal bars sorted by duration
   - P95 Trend Line Chart: Performance trends over time per task name

Time Handling:
--------------
- All timestamps from API are in epoch microseconds (e.g., 1780987602394611)
- Converted to IST timezone (Asia/Kolkata, UTC+5:30) for display
- Duration formatting: "2h 15m 30s", "45m 12s", "23s", etc.

Filtering:
----------
- Task Name Filter: Regex pattern matching on action names
- State Filter: Exact match on execution states (SUCCESS, FAILURE, etc.)
- Filters can be combined for precise data selection

Usage Examples:
---------------
  # Basic usage with hostname
  python3 runbook_stats.py --host nconprem-10-122-152-117.ccpnx.com

  # Using short IP format
  python3 runbook_stats.py --host 10-122-152-117

  # Filter by task name pattern
  python3 runbook_stats.py --host 10-122-152-117 --task-name "vmpower.*"

  # Filter successful executions only
  python3 runbook_stats.py --host 10-122-152-117 --state SUCCESS

  # Custom output name
  python3 runbook_stats.py --host 10-122-152-117 --output weekly_report

  # Custom credentials
  python3 runbook_stats.py --host 10-122-152-117 --username admin --password pass123

Arguments:
----------
  --host (required)   : NCM hostname or IP (e.g., nconprem-10-122-152-117.ccpnx.com or 10-122-152-117)
  --username          : Basic Auth username (default: ssp_admin@qa.nutanix.com)
  --password          : Basic Auth password (default: nutanix/4u)
  --output            : Output file prefix (default: runbook_stats)
  --task-name         : Filter by task name using regex pattern
  --state             : Filter by execution state (SUCCESS, FAILURE, RUNNING, etc.)
  --debug/--no-debug  : Enable/disable debug logging (default: enabled)

Output Files:
-------------
All files saved in 'nutanix-calm-runbook-results/' directory:
  - <output>.csv              : CSV export of all runlog data
  - <output>.html             : Comprehensive HTML report with graphs and interactive table
  - <output>_start_times.png  : Scatter plot of execution start times
  - <output>_execution_times.png : Bar chart of execution durations
  - <output>_p95_trend.png    : Line chart showing P95 performance trend
  - <output>.log              : Console output and debug logs

Technical Notes:
----------------
- Pagination: Fetches runlogs in batches of 500 until all data is retrieved
- Authentication: Uses HTTP Basic Auth with Base64 encoding
- SSL: TLS certificate verification disabled for internal/test environments
- Timezone: All times displayed in IST (India Standard Time, UTC+5:30)
- Plotly: Optional dependency for interactive HTML graphs with hover tooltips
- Error Handling: Gracefully handles missing data, invalid timestamps, API errors
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
from datetime import datetime, timezone
from urllib.parse import urlparse
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from collections import defaultdict
import numpy as np

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

# Try to import plotly for interactive graphs
try:
    import plotly.graph_objects as go
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("[INFO] Plotly not available - hover tooltips will not be available. Install with: pip install plotly")

def build_api_url(host_identifier):
    """Build complete NCM API URL from host identifier.
    
    Constructs the full API endpoint URL for the runbooks/runlogs/list endpoint.
    Supports multiple input formats: full hostname, hostname with prefix, or just IP.
    
    Args:
        host_identifier: Can be one of:
                        - Full URL: https://ncm.services.nconprem-10-122-152-117.ccpnx.com
                        - Full hostname: ncm.services.nconprem-10-122-152-117.ccpnx.com
                        - Hostname with prefix: nconprem-10-122-152-117.ccpnx.com
                        - IP format only: 10-122-152-117
    
    Returns:
        Full HTTPS URL for NCM runbooks runlogs list API endpoint
    
    Examples:
        build_api_url("10-122-152-117")
        -> "https://ncm.services.nconprem-10-122-152-117.ccpnx.com/api/calm/v3.0/runbooks/runlogs/list"
        
        build_api_url("nconprem-10-122-152-117.ccpnx.com")
        -> "https://ncm.services.nconprem-10-122-152-117.ccpnx.com/api/calm/v3.0/runbooks/runlogs/list"
    """
    # Strip trailing slashes
    host_identifier = host_identifier.rstrip('/')
    
    # If it starts with http/https, extract the hostname
    if host_identifier.startswith('http://') or host_identifier.startswith('https://'):
        from urllib.parse import urlparse
        parsed = urlparse(host_identifier)
        host_identifier = parsed.hostname
    
    # Check if it's just an IP format (contains only digits and hyphens)
    if re.match(r'^[\d\-]+$', host_identifier):
        # Just IP format, construct full hostname
        hostname = f"ncm.services.nconprem-{host_identifier}.ccpnx.com"
    elif host_identifier.startswith('nconprem-'):
        # Has nconprem prefix but might be missing ncm.services prefix
        if not host_identifier.startswith('ncm.services.'):
            hostname = f"ncm.services.{host_identifier}"
        else:
            hostname = host_identifier
    else:
        # Assume it's a complete hostname
        hostname = host_identifier
    
    return f"https://{hostname}/api/calm/v3.0/runbooks/runlogs/list"

def create_basic_auth(username, password):
    """Create Basic Auth header value."""
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return encoded

def format_timestamp(epoch_microseconds):
    """Convert epoch microseconds to IST formatted string.
    
    Args:
        epoch_microseconds: Unix timestamp in microseconds
    
    Returns:
        Formatted string: "YYYY-MM-DD HH:MM:SS IST"
    """
    if not epoch_microseconds or epoch_microseconds <= 0:
        return "N/A"
    
    try:
        # Convert microseconds to seconds
        epoch_seconds = epoch_microseconds / 1_000_000.0
        
        # Create UTC datetime from timestamp
        dt_utc = datetime.fromtimestamp(epoch_seconds, tz=pytz.utc)
        
        # Convert to IST (Asia/Kolkata)
        ist = pytz.timezone('Asia/Kolkata')
        dt_ist = dt_utc.astimezone(ist)
        
        return dt_ist.strftime("%Y-%m-%d %H:%M:%S IST")
    except (ValueError, OSError) as e:
        return f"Invalid timestamp ({epoch_microseconds})"

def format_duration(seconds):
    """Format duration in seconds to readable format.
    
    Args:
        seconds: Duration in seconds (float or int)
    
    Returns:
        Formatted string: "Xs", "Xm Ys", "Xh Ym", or "Xh Ym Zs"
    """
    if seconds is None or seconds < 0:
        return "0s"
    
    seconds = float(seconds)
    
    # Handle very small durations (< 1 second)
    if seconds < 1:
        return f"{seconds:.3f}s"
    
    # Round to nearest second
    total_seconds = int(round(seconds))
    
    if total_seconds < 60:
        return f"{total_seconds}s"
    
    # Calculate hours, minutes, and remaining seconds
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    
    # Build format string
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0:
        parts.append(f"{secs}s")
    
    if not parts:
        return "0s"
    
    return " ".join(parts)

def get_runlog_list(conn, headers):
    """Query NCM API for runbook execution logs with pagination support.
    
    Fetches all runlog entities by iterating through pages until all results
    are retrieved. The API supports pagination via 'offset' and 'length' parameters.
    
    Args:
        conn: HTTP connection object (HTTPSConnection)
        headers: HTTP headers dictionary with authentication
    
    Returns:
        Dictionary with 'entities' list and 'metadata' dict containing total_matches
    """
    all_entities = []
    offset = 0
    length = 250  # API maximum is 250 per page
    total_matches = None
    
    while True:
        payload = {
            "kind": "runbook_runlog",
            "offset": offset,
            "length": length
        }
        
        try:
            conn.request("POST", "/api/calm/v3.0/runbooks/runlogs/list", 
                        body=json.dumps(payload), headers=headers)
            response = conn.getresponse()
            data = response.read().decode('utf-8')
            
            if response.status != 200:
                print(f"[ERROR] NCM API request failed with HTTP status {response.status}")
                print(f"[ERROR] Response: {data}")
                return {"entities": []}
            
            result = json.loads(data)
            entities = result.get("entities", [])
            all_entities.extend(entities)
            
            if total_matches is None:
                total_matches = result.get("metadata", {}).get("total_matches", 0)
                print(f"[INFO] Total runbook execution logs to fetch: {total_matches}")
            
            print(f"[INFO] Fetched {len(all_entities)} / {total_matches} runlogs...")
            
            # Check if we've fetched all entities
            if len(all_entities) >= total_matches:
                break
            
            offset += length
            
        except Exception as e:
            print(f"[ERROR] Exception during NCM API request: {e}")
            break
    
    print(f"[INFO] Successfully fetched {len(all_entities)} runbook execution logs")
    return {"entities": all_entities, "metadata": {"total_matches": len(all_entities)}}

def build_tree_structure_html(runlog):
    """Build HTML-formatted hierarchical tree structure for a runlog entity.
    
    Creates a detailed tree representation using HTML styling instead of ASCII characters.
    
    Args:
        runlog: Single runlog entity from NCM API
    
    Returns:
        HTML string representing the detailed tree structure
    """
    # Extract key information from runlog
    status = runlog.get("status", {})
    metadata = runlog.get("metadata", {})
    
    # Basic identification
    runlog_uuid = metadata.get("uuid", "N/A")
    runlog_name = metadata.get("name", "")
    runlog_type = status.get("type", "N/A")
    state = status.get("state", "UNKNOWN")
    
    # Timestamps (convert strings to integers)
    creation_time = metadata.get("creation_time", 0)
    last_update_time = metadata.get("last_update_time", 0)
    
    # Convert to integers if they're strings
    if isinstance(creation_time, str):
        try:
            creation_time = int(creation_time)
        except (ValueError, TypeError):
            creation_time = 0
    
    if isinstance(last_update_time, str):
        try:
            last_update_time = int(last_update_time)
        except (ValueError, TypeError):
            last_update_time = 0
    
    creation_time_fmt = format_timestamp(creation_time)
    last_update_time_fmt = format_timestamp(last_update_time)
    
    # Duration
    duration_seconds = 0
    if creation_time > 0 and last_update_time > 0:
        duration_seconds = (last_update_time - creation_time) / 1_000_000.0
    duration_fmt = format_duration(duration_seconds)
    
    # Archived status
    is_archived = status.get("is_runlog_archived", False)
    
    # Build HTML tree structure
    html = '<div class="tree-container" style="font-family: monospace; line-height: 1.8;">'
    html += '<div class="tree-section"><strong style="color: #2c3e50;">Runlog</strong></div>'
    
    # Execution section
    html += '<div class="tree-section" style="margin-left: 20px;"><strong style="color: #7c9bc7;">▸ Execution</strong></div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Name: <span style="color: #2c3e50; font-weight: 600;">{runlog_name if runlog_name else "N/A"}</span></div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">UUID: <span style="color: #666;">{runlog_uuid}</span></div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Type: {runlog_type}</div>'
    
    # State with color coding
    state_color = '#27ae60' if state == 'SUCCESS' else ('#e74c3c' if state == 'FAILURE' else '#f39c12')
    html += f'<div class="tree-item" style="margin-left: 40px;">State: <span style="color: {state_color}; font-weight: bold;">{state}</span></div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Duration: <span style="font-weight: 600;">{duration_fmt}</span></div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Start Time: {creation_time_fmt}</div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">End Time: {last_update_time_fmt}</div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Archived: {"Yes" if is_archived else "No"}</div>'
    
    # Mode and concurrency
    runlog_meta = status.get("runlog_meta_state", {})
    if runlog_meta:
        html += f'<div class="tree-item" style="margin-left: 40px;">Mode: {runlog_meta.get("mode", "N/A")}</div>'
        html += f'<div class="tree-item" style="margin-left: 40px;">Concurrency Group: {runlog_meta.get("concurrency_group", "N/A")}</div>'
    else:
        html += f'<div class="tree-item" style="margin-left: 40px;">Mode: N/A</div>'
        html += f'<div class="tree-item" style="margin-left: 40px;">Concurrency Group: N/A</div>'
    
    # Action section
    action_ref = status.get("action_reference", {})
    action_name = action_ref.get("name", "N/A")
    action_uuid = action_ref.get("uuid", "N/A")
    action_kind = action_ref.get("kind", "N/A")
    
    html += '<div class="tree-section" style="margin-left: 20px; margin-top: 10px;"><strong style="color: #7c9bc7;">▸ Action</strong></div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Name: <span style="font-weight: 600;">{action_name}</span></div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">UUID: <span style="color: #666;">{action_uuid}</span></div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Operation Type: {action_kind}</div>'
    
    # Ownership section
    user_ref = status.get("userdata_reference", {})
    user_name = user_ref.get("name", "N/A")
    
    owner_ref = metadata.get("owner_reference", {})
    owner_name = owner_ref.get("name", "N/A")
    
    project_ref = metadata.get("project_reference", {})
    project_name = project_ref.get("name", "N/A")
    
    invoker = status.get("invoker", {})
    invoker_kind = invoker.get("kind", "N/A")
    invoker_name = invoker.get("name", "N/A") if invoker.get("name") else invoker_kind
    
    html += '<div class="tree-section" style="margin-left: 20px; margin-top: 10px;"><strong style="color: #7c9bc7;">▸ Ownership</strong></div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">User: {user_name}</div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Owner: {owner_name}</div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Project: {project_name}</div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Invoker: {invoker_name}</div>'
    
    # Target section
    runbook_json = status.get("runbook_json", {})
    endpoint_name = "N/A"
    endpoint_uuid = "N/A"
    
    if runbook_json:
        resources = runbook_json.get("resources", {})
        target_ref = resources.get("default_target_reference", {})
        endpoint_name = target_ref.get("name", "N/A")
        endpoint_uuid = target_ref.get("uuid", "N/A")
    
    html += '<div class="tree-section" style="margin-left: 20px; margin-top: 10px;"><strong style="color: #7c9bc7;">▸ Target</strong></div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Endpoint Name: {endpoint_name}</div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Endpoint UUID: <span style="color: #666;">{endpoint_uuid}</span></div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Environment: N/A</div>'
    
    # Workflow section
    if runbook_json:
        resources = runbook_json.get("resources", {})
        runbook = resources.get("runbook", {})
        
        workflow_name = runbook.get("name", "N/A")
        workflow_uuid = runbook.get("uuid", "N/A")
        main_task_ref = runbook.get("main_task_local_reference", {})
        main_task_uuid = main_task_ref.get("uuid", "N/A")
        
        task_list = runbook.get("task_definition_list", [])
        task_count = len(task_list)
        
        html += '<div class="tree-section" style="margin-left: 20px; margin-top: 10px;"><strong style="color: #7c9bc7;">▸ Workflow</strong></div>'
        html += f'<div class="tree-item" style="margin-left: 40px;">Name: {workflow_name}</div>'
        html += f'<div class="tree-item" style="margin-left: 40px;">UUID: <span style="color: #666;">{workflow_uuid}</span></div>'
        html += f'<div class="tree-item" style="margin-left: 40px;">Main Task: {main_task_uuid}</div>'
        html += f'<div class="tree-item" style="margin-left: 40px;">Task Count: {task_count}</div>'
        
        if task_list:
            html += '<div class="tree-item" style="margin-left: 40px; margin-top: 5px;"><strong>Tasks:</strong></div>'
            for i, task in enumerate(task_list):
                task_type = task.get("type", "UNKNOWN")
                task_name = task.get("name", "unnamed")
                html += f'<div class="tree-item" style="margin-left: 60px;">• {task_type}: <span style="font-weight: 600;">{task_name}</span></div>'
    
    # Runtime Analysis section
    html += '<div class="tree-section" style="margin-left: 20px; margin-top: 10px;"><strong style="color: #7c9bc7;">▸ Runtime Analysis</strong></div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Queue Delay: N/A</div>'
    
    reason_list = status.get("reason_list", [])
    retry_count = len([r for r in reason_list if r.get("type") == "RETRY"])
    html += f'<div class="tree-item" style="margin-left: 40px;">Retry Count: {retry_count}</div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Timeout Detected: No</div>'
    html += f'<div class="tree-item" style="margin-left: 40px;">Failure Category: N/A</div>'
    
    # Failure Details section
    html += '<div class="tree-section" style="margin-left: 20px; margin-top: 10px;"><strong style="color: #7c9bc7;">▸ Failure Details</strong></div>'
    if state != "SUCCESS" and reason_list:
        for reason in reason_list:
            reason_message = reason.get("message", "Unknown error")
            html += f'<div class="tree-item" style="margin-left: 40px; color: #e74c3c;">• {reason_message}</div>'
    else:
        html += '<div class="tree-item" style="margin-left: 40px; color: #27ae60;">No failures detected - Clean execution</div>'
    
    html += '</div>'
    return html

def build_tree_structure(runlog):
    """Build comprehensive hierarchical tree structure for a runlog entity.
    
    Creates a detailed tree representation showing execution details, action info,
    ownership, target endpoint, workflow structure, and failure analysis.
    
    Args:
        runlog: Single runlog entity from NCM API
    
    Returns:
        Multi-line string representing the detailed tree structure
    """
    lines = []
    
    # Extract key information from runlog
    status = runlog.get("status", {})
    metadata = runlog.get("metadata", {})
    
    # Basic identification
    runlog_uuid = metadata.get("uuid", "N/A")
    runlog_name = metadata.get("name", "")
    runlog_type = status.get("type", "N/A")
    state = status.get("state", "UNKNOWN")
    
    # Timestamps (convert strings to integers)
    creation_time = metadata.get("creation_time", 0)
    last_update_time = metadata.get("last_update_time", 0)
    
    # Convert to integers if they're strings
    if isinstance(creation_time, str):
        try:
            creation_time = int(creation_time)
        except (ValueError, TypeError):
            creation_time = 0
    
    if isinstance(last_update_time, str):
        try:
            last_update_time = int(last_update_time)
        except (ValueError, TypeError):
            last_update_time = 0
    
    creation_time_fmt = format_timestamp(creation_time)
    last_update_time_fmt = format_timestamp(last_update_time)
    
    # Duration
    duration_seconds = 0
    if creation_time > 0 and last_update_time > 0:
        duration_seconds = (last_update_time - creation_time) / 1_000_000.0
    duration_fmt = format_duration(duration_seconds)
    
    # Archived status
    is_archived = status.get("is_runlog_archived", False)
    
    # Build tree header - Runlog section
    lines.append("Runlog")
    lines.append("├── Execution")
    lines.append(f"│    ├── Name: {runlog_name if runlog_name else 'N/A'}")
    lines.append(f"│    ├── UUID: {runlog_uuid}")
    lines.append(f"│    ├── Type: {runlog_type}")
    lines.append(f"│    ├── State: {state}")
    lines.append(f"│    ├── Duration: {duration_fmt}")
    lines.append(f"│    ├── Start Time: {creation_time_fmt}")
    lines.append(f"│    ├── End Time: {last_update_time_fmt}")
    lines.append(f"│    ├── Archived: {'Yes' if is_archived else 'No'}")
    
    # Mode and concurrency (if available in runlog_meta_state)
    runlog_meta = status.get("runlog_meta_state", {})
    if runlog_meta:
        lines.append(f"│    ├── Mode: {runlog_meta.get('mode', 'N/A')}")
        lines.append(f"│    └── Concurrency Group: {runlog_meta.get('concurrency_group', 'N/A')}")
    else:
        lines.append("│    ├── Mode: N/A")
        lines.append("│    └── Concurrency Group: N/A")
    lines.append("│")
    
    # Action section
    action_ref = status.get("action_reference", {})
    action_name = action_ref.get("name", "N/A")
    action_uuid = action_ref.get("uuid", "N/A")
    action_kind = action_ref.get("kind", "N/A")
    
    lines.append("├── Action")
    lines.append(f"│    ├── Name: {action_name}")
    lines.append(f"│    ├── UUID: {action_uuid}")
    lines.append(f"│    └── Operation Type: {action_kind}")
    lines.append("│")
    
    # Ownership section
    user_ref = status.get("userdata_reference", {})
    user_name = user_ref.get("name", "N/A")
    
    owner_ref = metadata.get("owner_reference", {})
    owner_name = owner_ref.get("name", "N/A")
    
    project_ref = metadata.get("project_reference", {})
    project_name = project_ref.get("name", "N/A")
    
    invoker = status.get("invoker", {})
    invoker_kind = invoker.get("kind", "N/A")
    invoker_name = invoker.get("name", "N/A") if invoker.get("name") else invoker_kind
    
    lines.append("├── Ownership")
    lines.append(f"│    ├── User: {user_name}")
    lines.append(f"│    ├── Owner: {owner_name}")
    lines.append(f"│    ├── Project: {project_name}")
    lines.append(f"│    └── Invoker: {invoker_name}")
    lines.append("│")
    
    # Target section
    runbook_json = status.get("runbook_json", {})
    endpoint_name = "N/A"
    endpoint_uuid = "N/A"
    
    if runbook_json:
        resources = runbook_json.get("resources", {})
        target_ref = resources.get("default_target_reference", {})
        endpoint_name = target_ref.get("name", "N/A")
        endpoint_uuid = target_ref.get("uuid", "N/A")
    
    lines.append("├── Target")
    lines.append(f"│    ├── Endpoint Name: {endpoint_name}")
    lines.append(f"│    ├── Endpoint UUID: {endpoint_uuid}")
    lines.append(f"│    └── Environment: N/A")
    lines.append("│")
    
    # Workflow section
    if runbook_json:
        resources = runbook_json.get("resources", {})
        runbook = resources.get("runbook", {})
        
        workflow_name = runbook.get("name", "N/A")
        workflow_uuid = runbook.get("uuid", "N/A")
        main_task_ref = runbook.get("main_task_local_reference", {})
        main_task_uuid = main_task_ref.get("uuid", "N/A")
        
        task_list = runbook.get("task_definition_list", [])
        task_count = len(task_list)
        
        lines.append("├── Workflow")
        lines.append(f"│    ├── Name: {workflow_name}")
        lines.append(f"│    ├── UUID: {workflow_uuid}")
        lines.append(f"│    ├── Main Task: {main_task_uuid}")
        lines.append(f"│    ├── Task Count: {task_count}")
        
        if task_list:
            lines.append("│    └── Tasks")
            for i, task in enumerate(task_list):
                task_type = task.get("type", "UNKNOWN")
                task_name = task.get("name", "unnamed")
                is_last = (i == len(task_list) - 1)
                prefix = "│         └──" if is_last else "│         ├──"
                lines.append(f"{prefix} {task_type}: {task_name}")
        else:
            lines.append("│    └── Tasks: None")
    else:
        lines.append("├── Workflow")
        lines.append("│    └── No workflow data available")
    
    lines.append("│")
    
    # Runtime Analysis section
    # Note: These fields may not be available in the current API response
    # but keeping structure for future enhancement
    lines.append("├── Runtime Analysis")
    lines.append("│    ├── Queue Delay: N/A")
    lines.append("│    ├── Retry Count: 0")
    lines.append("│    ├── Timeout Detected: No")
    lines.append("│    └── Failure Category: N/A")
    lines.append("│")
    
    # Failure Details section
    reason_list = status.get("reason_list", [])
    is_critical = status.get("critical", False)
    
    lines.append("└── Failure Details")
    if reason_list:
        lines.append(f"     ├── Critical: {'Yes' if is_critical else 'No'}")
        lines.append("     ├── Reason List:")
        for i, reason in enumerate(reason_list):
            is_last = (i == len(reason_list) - 1)
            prefix = "     │    └──" if is_last else "     │    ├──"
            lines.append(f"{prefix} {reason}")
        lines.append("     └── Error Messages: See reason list above")
    else:
        lines.append("     ├── No failures detected")
        lines.append("     └── Status: Clean execution")
    
    return "\n".join(lines)

def extract_runlog_data(runlog):
    """Extract relevant data from a single runlog entity.
    
    Parses a runlog entity from the NCM API response and extracts all relevant fields
    including task information, execution state, timestamps, user/project context,
    and builds the hierarchical tree structure.
    
    Args:
        runlog: Single runlog entity from NCM API response
    
    Returns:
        Dictionary with extracted and formatted runlog data
    """
    status = runlog.get("status", {})
    metadata = runlog.get("metadata", {})
    
    # Extract identification fields
    runlog_uuid = metadata.get("uuid", "N/A")
    runlog_name = metadata.get("name", "")  # This is the display name for filtering
    task_name = status.get("action_reference", {}).get("name", "N/A")
    state = status.get("state", "UNKNOWN")
    
    # Extract context fields
    user_name = status.get("userdata_reference", {}).get("name", "N/A")
    project_name = metadata.get("project_reference", {}).get("name", "N/A")
    
    # Extract endpoint from runbook JSON
    endpoint_name = "N/A"
    runbook_json = status.get("runbook_json", {})
    if runbook_json:
        resources = runbook_json.get("resources", {})
        target_ref = resources.get("default_target_reference", {})
        endpoint_name = target_ref.get("name", "N/A")
    
    # Extract timestamp fields (epoch microseconds as strings from API)
    creation_time = metadata.get("creation_time", 0)
    last_update_time = metadata.get("last_update_time", 0)
    
    # Convert to integers if they're strings
    if isinstance(creation_time, str):
        try:
            creation_time = int(creation_time)
        except (ValueError, TypeError):
            creation_time = 0
    
    if isinstance(last_update_time, str):
        try:
            last_update_time = int(last_update_time)
        except (ValueError, TypeError):
            last_update_time = 0
    
    # Calculate execution duration in seconds
    execution_seconds = 0
    if creation_time > 0 and last_update_time > 0:
        execution_seconds = (last_update_time - creation_time) / 1_000_000.0
    
    # Build hierarchical tree structure
    tree_structure = build_tree_structure_html(runlog)
    
    return {
        "runlog_uuid": runlog_uuid,
        "runlog_name": runlog_name,  # metadata.name for filtering
        "task_name": task_name,
        "state": state,
        "user": user_name,
        "project": project_name,
        "endpoint": endpoint_name,
        "start_time": creation_time,
        "end_time": last_update_time,
        "execution_seconds": execution_seconds,
        "start_time_formatted": format_timestamp(creation_time),
        "end_time_formatted": format_timestamp(last_update_time),
        "execution_duration": format_duration(execution_seconds),
        "tree_structure": tree_structure
    }

def filter_runlogs(runlogs_data, name_filter=None, state_filter=None):
    """Filter runbook execution logs based on criteria.
    
    Applies optional filters for runlog name (regex pattern on metadata.name) 
    and execution state. Filters can be used independently or combined.
    
    Args:
        runlogs_data: List of runlog data dictionaries
        name_filter: Regex pattern to match runlog names from metadata.name (case-insensitive)
        state_filter: Exact state to match (e.g., "SUCCESS", "FAILURE")
    
    Returns:
        Filtered list of runlog data dictionaries
    """
    filtered = runlogs_data
    
    # Apply name filter using regex on metadata.name
    if name_filter:
        try:
            pattern = re.compile(name_filter, re.IGNORECASE)
            filtered = [r for r in filtered if pattern.search(r["runlog_name"]) or pattern.search(r["task_name"])]
            print(f"[INFO] Name filter applied ('{name_filter}'): {len(filtered)} runlogs match")
        except re.error as e:
            print(f"[WARNING] Invalid regex pattern '{name_filter}': {e}")
    
    # Apply state filter (exact match, case-insensitive)
    if state_filter:
        filtered = [r for r in filtered if r["state"].upper() == state_filter.upper()]
        print(f"[INFO] State filter applied ('{state_filter}'): {len(filtered)} runlogs match")
    
    return filtered

def calculate_statistics(runlogs_data):
    """Calculate execution time statistics from runbook execution data.
    
    Computes min, max, average, and P95 execution times for successful runbook
    executions. Only considers executions with SUCCESS state and valid execution times.
    
    Args:
        runlogs_data: List of runlog data dictionaries
    
    Returns:
        Dictionary with keys: min, max, avg, p95, count (all times in seconds)
    """
    # Filter for successful executions with valid execution times
    successful = [r for r in runlogs_data if r["state"] == "SUCCESS" and r["execution_seconds"] > 0]
    
    if not successful:
        return {
            "min": 0,
            "max": 0,
            "avg": 0,
            "p95": 0,
            "count": 0
        }
    
    times = [r["execution_seconds"] for r in successful]
    times.sort()
    
    # Calculate P95 index
    p95_index = int(len(times) * 0.95)
    if p95_index >= len(times):
        p95_index = len(times) - 1
    
    return {
        "min": min(times),
        "max": max(times),
        "avg": sum(times) / len(times),
        "p95": times[p95_index],
        "count": len(successful)
    }

def calculate_total_execution_summary(runlogs_data):
    """Calculate total execution time summary across all filtered runlogs.
    
    Calculates the total time span from earliest start to latest end time,
    and provides state breakdown with pass percentage.
    
    Args:
        runlogs_data: List of runlog data dictionaries
    
    Returns:
        Dictionary with total_count, state_counts, earliest_start, latest_end,
        total_span_seconds, and pass_percentage
    """
    if not runlogs_data:
        return {
            "total_count": 0,
            "state_counts": {},
            "earliest_start": 0,
            "latest_end": 0,
            "total_span_seconds": 0,
            "pass_percentage": 0.0
        }
    
    # Count by state
    state_counts = defaultdict(int)
    for runlog in runlogs_data:
        state_counts[runlog["state"]] += 1
    
    # Find earliest and latest times
    valid_times = [(r["start_time"], r["end_time"]) for r in runlogs_data 
                   if r["start_time"] > 0 and r["end_time"] > 0]
    
    if not valid_times:
        return {
            "total_count": len(runlogs_data),
            "state_counts": dict(state_counts),
            "earliest_start": 0,
            "latest_end": 0,
            "total_span_seconds": 0,
            "pass_percentage": 0.0
        }
    
    earliest_start = min(t[0] for t in valid_times)
    latest_end = max(t[1] for t in valid_times)
    total_span_seconds = (latest_end - earliest_start) / 1_000_000.0
    
    # Calculate pass percentage (SUCCESS / Total)
    success_count = state_counts.get("SUCCESS", 0)
    total_count = len(runlogs_data)
    pass_percentage = (success_count / total_count * 100) if total_count > 0 else 0.0
    
    return {
        "total_count": total_count,
        "state_counts": dict(state_counts),
        "earliest_start": earliest_start,
        "latest_end": latest_end,
        "total_span_seconds": total_span_seconds,
        "pass_percentage": pass_percentage
    }

def calculate_p95_trend_by_task(runlogs_data):
    """Calculate P95 execution time trend over time for each task name.
    
    Groups runbook executions by task name, then divides each task's executions into
    time windows. Calculates P95 for each window to show performance trends.
    
    Args:
        runlogs_data: List of runlog data dictionaries
    
    Returns:
        Dictionary mapping task names to list of (timestamp, p95_value) tuples
    """
    # Group runlogs by task name (only successful executions)
    by_task = defaultdict(list)
    for runlog in runlogs_data:
        if runlog["state"] == "SUCCESS" and runlog["execution_seconds"] > 0:
            by_task[runlog["task_name"]].append(runlog)
    
    # Calculate P95 trend for each task
    trend_data = {}
    
    for task_name, runlogs in by_task.items():
        # Sort by start time chronologically
        runlogs.sort(key=lambda x: x["start_time"])
        
        # Group into time windows (every 10 executions per window)
        window_size = 10
        p95_points = []
        
        for i in range(0, len(runlogs), window_size):
            window = runlogs[i:i+window_size]
            times = [r["execution_seconds"] for r in window]
            times.sort()
            
            # Calculate P95 for this window
            p95_index = int(len(times) * 0.95)
            if p95_index >= len(times):
                p95_index = len(times) - 1
            
            p95_value = times[p95_index]
            
            # Use middle timestamp of window as the time point
            mid_index = len(window) // 2
            timestamp = window[mid_index]["start_time"]
            
            p95_points.append((timestamp, p95_value))
        
        if p95_points:
            trend_data[task_name] = p95_points
    
    return trend_data

def generate_csv_report(runlogs_data, output_path):
    """Generate CSV report from runbook execution data.
    
    Exports all runlog data to a CSV file with columns for key runbook execution metrics.
    
    Args:
        runlogs_data: List of runlog data dictionaries
        output_path: Path to output CSV file
    """
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                "Runbook Name", "Start Time (IST)", "End Time (IST)", 
                "Total Execution Time", "State", "Runlog UUID", "Task Name"
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for runlog in runlogs_data:
                writer.writerow({
                    "Runbook Name": runlog.get("runlog_name", "N/A"),
                    "Start Time (IST)": runlog["start_time_formatted"],
                    "End Time (IST)": runlog["end_time_formatted"],
                    "Total Execution Time": runlog["execution_duration"],
                    "State": runlog["state"],
                    "Runlog UUID": runlog["runlog_uuid"],
                    "Task Name": runlog["task_name"]
                })
        
        print(f"[INFO] CSV report saved to: {output_path}")
    except Exception as e:
        print(f"[ERROR] Failed to generate CSV report: {e}")

def generate_start_times_graph(runlogs_data, output_path):
    """Generate scatter plot showing runbook execution start times.
    
    Creates a scatter plot with execution start times on X-axis and unique runbook names on Y-axis.
    Uses the actual runbook names (metadata.name) that are being filtered.
    
    Args:
        runlogs_data: List of runlog data dictionaries
        output_path: Path to output PNG file
    """
    if not runlogs_data:
        print("[WARNING] No data available to generate start times graph")
        return
    
    try:
        # Get unique runbook names (use runlog_name which is metadata.name) and create mapping to Y positions
        unique_runbooks = sorted(set(r.get("runlog_name", r["task_name"]) for r in runlogs_data))
        runbook_to_y = {name: i for i, name in enumerate(unique_runbooks)}
        
        # Convert timestamps to datetime objects (IST timezone)
        start_times = []
        y_positions = []
        
        for runlog in runlogs_data:
            if runlog["start_time"] > 0:
                dt = datetime.fromtimestamp(runlog["start_time"] / 1_000_000.0, tz=pytz.timezone('Asia/Kolkata'))
                start_times.append(dt)
                runbook_name = runlog.get("runlog_name", runlog["task_name"])
                y_positions.append(runbook_to_y[runbook_name])
        
        if not start_times:
            print("[WARNING] No valid start times found for graph generation")
            return
        
        # Calculate time span
        earliest_start = min(start_times)
        latest_start = max(start_times)
        time_span_seconds = (latest_start - earliest_start).total_seconds()
        time_span_formatted = format_duration(time_span_seconds)
        
        # Create scatter plot with enough height for all unique runbook names
        fig, ax = plt.subplots(figsize=(18, max(10, len(unique_runbooks) * 0.5)))
        
        # Plot scatter points
        ax.scatter(start_times, y_positions, alpha=0.7, s=150, color='steelblue', edgecolors='navy', linewidth=1.5)
        
        # Set Y-axis to show unique runbook names
        ax.set_yticks(range(len(unique_runbooks)))
        ax.set_yticklabels(unique_runbooks, fontsize=9)
        
        # Format X-axis with detailed time labels (seconds granularity)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S', tz=pytz.timezone('Asia/Kolkata')))
        
        # Set X-axis locator for better granularity based on time span
        if time_span_seconds < 60:  # Less than 1 minute
            ax.xaxis.set_major_locator(mdates.SecondLocator(interval=5))
        elif time_span_seconds < 300:  # Less than 5 minutes
            ax.xaxis.set_major_locator(mdates.SecondLocator(interval=10))
        elif time_span_seconds < 600:  # Less than 10 minutes
            ax.xaxis.set_major_locator(mdates.SecondLocator(interval=30))
        else:
            ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
        
        plt.xticks(rotation=45, ha='right')
        
        # Add vertical lines for first and last execution
        ax.axvline(x=earliest_start, color='green', linestyle='--', alpha=0.5, linewidth=2, label=f'First Start: {earliest_start.strftime("%H:%M:%S")}')
        ax.axvline(x=latest_start, color='red', linestyle='--', alpha=0.5, linewidth=2, label=f'Last Start: {latest_start.strftime("%H:%M:%S")}')
        
        # Labels and title with time span information
        ax.set_xlabel("Execution Start Time (HH:MM:SS IST)", fontsize=12, fontweight='bold')
        ax.set_ylabel("Runbook Name", fontsize=12, fontweight='bold')
        title = f"Runbook Execution Start Times\n"
        title += f"Time Span: {time_span_formatted} (First to Last Start) | Total Runbooks: {len(unique_runbooks)}"
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.grid(True, alpha=0.3, linestyle='--', axis='x')
        ax.legend(loc='upper right', fontsize=10)
        
        # Add padding to Y-axis
        ax.set_ylim(-0.5, len(unique_runbooks) - 0.5)
        
        # Add text annotation showing time span details
        textstr = f'Time to start all runbooks: {time_span_formatted}\nTotal unique runbooks: {len(unique_runbooks)}'
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
        ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=11,
                verticalalignment='top', bbox=props)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        
        print(f"[INFO] Start times graph saved to: {output_path}")
    except Exception as e:
        print(f"[ERROR] Failed to generate start times graph: {e}")

def generate_execution_times_graph(runlogs_data, output_path):
    """Generate horizontal bar chart showing runbook execution durations.
    
    Creates a sorted bar chart with unique runbook names on Y-axis and execution times on X-axis.
    Uses the actual runbook names (metadata.name) that are being filtered.
    Each unique runbook name is shown, color-coded based on average.
    
    Args:
        runlogs_data: List of runlog data dictionaries
        output_path: Path to output PNG file
    """
    # Filter for successful executions only
    successful = [r for r in runlogs_data if r["state"] == "SUCCESS" and r["execution_seconds"] > 0]
    
    if not successful:
        print("[WARNING] No successful runbook executions found for execution times graph")
        return
    
    try:
        # Group by unique runbook name (use runlog_name which is metadata.name) and calculate average for each
        runbook_times = {}
        for r in successful:
            runbook_name = r.get("runlog_name", r["task_name"])
            if runbook_name not in runbook_times:
                runbook_times[runbook_name] = []
            runbook_times[runbook_name].append(r["execution_seconds"])
        
        # Calculate average for each runbook
        runbook_averages = {name: sum(times)/len(times) for name, times in runbook_times.items()}
        
        # Sort by average execution time
        sorted_runbooks = sorted(runbook_averages.items(), key=lambda x: x[1])
        runbook_names = [t[0] for t in sorted_runbooks]
        avg_times = [t[1] for t in sorted_runbooks]
        
        # Calculate overall average for color coding
        overall_avg = sum(avg_times) / len(avg_times)
        
        # Color code bars: coral for above average, light blue for below average
        colors = ['#e74c3c' if t > overall_avg else '#3498db' for t in avg_times]
        
        # Create horizontal bar chart with enough height for all runbooks
        fig, ax = plt.subplots(figsize=(14, max(8, len(runbook_names) * 0.5)))
        
        bars = ax.barh(runbook_names, avg_times, color=colors, edgecolor='#2c3e50', linewidth=0.8)
        
        # Add value labels on bars
        for bar, time in zip(bars, avg_times):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2, 
                   f' {format_duration(time)}',
                   ha='left', va='center', fontsize=9, fontweight='bold')
        
        # Labels and title
        ax.set_xlabel("Average Execution Time (seconds)", fontsize=12, fontweight='bold')
        ax.set_ylabel("Runbook Name", fontsize=12, fontweight='bold')
        ax.set_title(f"Runbook Execution Times (Overall Avg: {format_duration(overall_avg)})", 
                    fontsize=14, fontweight='bold', pad=15)
        ax.grid(True, alpha=0.3, axis='x', linestyle='--')
        
        # Adjust layout
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        
        print(f"[INFO] Execution times graph saved to: {output_path}")
    except Exception as e:
        print(f"[ERROR] Failed to generate execution times graph: {e}")


def generate_html_report(runlogs_data, stats, total_summary, trend_data, output_path, 
                        start_times_png, exec_times_png):
    """Generate comprehensive HTML report with interactive elements.
    
    Creates an HTML report with summary statistics, detailed data table with
    expandable rows showing tree structures, and embedded graphs.
    
    Args:
        runlogs_data: List of runlog data dictionaries
        stats: Statistics dictionary from calculate_statistics
        total_summary: Total execution summary from calculate_total_execution_summary
        trend_data: Trend data (not used currently, kept for compatibility)
        output_path: Path to output HTML file
        start_times_png: Path to start times graph PNG file
        exec_times_png: Path to execution times graph PNG file
    """
    try:
        # Extract summary data
        total_count = total_summary["total_count"]
        state_counts = total_summary["state_counts"]
        success_count = state_counts.get("SUCCESS", 0)
        failure_count = state_counts.get("FAILURE", 0)
        running_count = state_counts.get("RUNNING", 0)
        provisioning_count = state_counts.get("PROVISIONING", 0)
        
        # Calculate unknown count (catchall)
        known_count = success_count + failure_count + running_count + provisioning_count
        unknown_count = total_count - known_count
        
        pass_percentage = total_summary["pass_percentage"]
        
        # Format total execution time summary
        earliest_start_fmt = format_timestamp(total_summary["earliest_start"])
        latest_end_fmt = format_timestamp(total_summary["latest_end"])
        total_span_fmt = format_duration(total_summary["total_span_seconds"])
        
        # Build HTML content
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>NCM Runbook Execution Statistics Report</title>
    <style>
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
        h3 {{
            color: #666;
            margin-top: 20px;
        }}
        .summary {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 25px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .summary-box {{
            background-color: #e8f5e9;
            padding: 15px;
            border-radius: 5px;
            margin: 15px 0;
            border-left: 4px solid #7c9bc7;
        }}
        .summary-box p {{
            margin: 8px 0;
            font-size: 14px;
        }}
        .summary-box strong {{
            color: #2e7d32;
        }}
        .note {{
            background-color: #fff3cd;
            padding: 10px 15px;
            border-radius: 5px;
            margin: 10px 0;
            border-left: 4px solid #ffc107;
            font-size: 13px;
            color: #856404;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}
        .summary-item {{
            background-color: white;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #7c9bc7;
        }}
        .summary-item strong {{
            display: block;
            color: #666;
            font-size: 12px;
            margin-bottom: 5px;
        }}
        .summary-item span {{
            display: block;
            font-size: 20px;
            font-weight: bold;
            color: #333;
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
        .state-success {{
            color: #27ae60;
            font-weight: bold;
        }}
        .state-failure {{
            color: #e74c3c;
            font-weight: bold;
        }}
        .state-running {{
            color: #f39c12;
            font-weight: bold;
        }}
        .graph-container {{
            margin: 30px 0;
            text-align: center;
        }}
        .graph-container img {{
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
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
            line-height: 1.8;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            color: #2c3e50;
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
                icon.textContent = '\u2212';
            }}
        }}
    </script>
</head>
<body>
    <div class="container">
        <h1>NCM Runbook Execution Statistics Report</h1>
        
        <!-- Total Execution Time Summary -->
        <div class="summary">
            <h2>Total Execution Time Across Filtered Runbook Logs</h2>
            <div class="summary-box">
                <p><strong>Total Filtered Runbook Logs:</strong> {total_count}</p>
                <p><strong>Earliest Start Time (IST):</strong> {earliest_start_fmt}</p>
                <p><strong>Latest End Time (IST):</strong> {latest_end_fmt}</p>
                <p><strong>Total Time to Complete All Filtered Runbook Logs:</strong> {total_span_fmt}</p>
            </div>
            <div class="note">
                <strong>Note:</strong> This calculation is based only on the filtered runbook logs (not all runlogs in the system).<br>
                <strong>Calculation:</strong> Max(Last Update Time) - Min(Creation Time) = {total_span_fmt}
            </div>
        </div>
        
        <!-- State Breakdown and Pass % -->
        <div class="summary">
            <h2>State Breakdown and Pass %</h2>
            <div class="summary-box">
                <p><strong>1. Total Filtered Runbook Logs:</strong> {total_count}</p>
                <p><strong>2. Total Filtered runbook logs in FAILURE state:</strong> {failure_count}</p>
                <p><strong>3. Total Filtered runbook logs in SUCCESS state:</strong> {success_count}</p>
                <p><strong>4. Total Filtered runbook logs in RUNNING state:</strong> {running_count}</p>
                <p><strong>5. Total Filtered runbook logs in PROVISIONING state:</strong> {provisioning_count}</p>
                <p><strong>6. Total Filtered runbook logs in UNKNOWN state:</strong> {unknown_count} (catchall: state is not FAILURE, SUCCESS, RUNNING, or PROVISIONING)</p>
                <p style="font-size: 16px; margin-top: 10px;"><strong>Pass %:</strong> <span style="color: #2e7d32; font-size: 18px;">{pass_percentage:.1f}%</span>   (formula: SUCCESS / Total = {success_count} / {total_count})</p>
            </div>
            <div class="note">
                <strong>Note:</strong> Pass % counts only runbook logs in SUCCESS state as pass. Runbook logs in PROVISIONING and UNKNOWN states are not considered as pass.
            </div>
        </div>
        
        <!-- Execution Time Statistics -->
        <div class="summary">
            <h2>Execution Time Statistics (Successful Executions Only)</h2>
            <div class="summary-grid">
                <div class="summary-item">
                    <strong>Successful Executions</strong>
                    <span class="state-success">{stats['count']}</span>
                </div>
                <div class="summary-item">
                    <strong>Min Execution Time</strong>
                    <span>{format_duration(stats['min'])}</span>
                </div>
                <div class="summary-item">
                    <strong>Max Execution Time</strong>
                    <span>{format_duration(stats['max'])}</span>
                </div>
                <div class="summary-item">
                    <strong>Avg Execution Time</strong>
                    <span>{format_duration(stats['avg'])}</span>
                </div>
                <div class="summary-item">
                    <strong>P95 Execution Time</strong>
                    <span>{format_duration(stats['p95'])}</span>
                </div>
            </div>
            <div class="note">
                <strong>Note:</strong> Only runbook logs that moved to SUCCESS state are included. FAILURE and PROVISIONING states are excluded.
            </div>
        </div>
        
        <!-- State Distribution Table -->
        <div class="summary">
            <h3>Detailed State Distribution</h3>
            <table style="width: auto;">
                <tr>
                    <th>State</th>
                    <th>Count</th>
                    <th>Percentage</th>
                </tr>
"""
        
        for state, count in sorted(state_counts.items()):
            percentage = (count / total_count * 100) if total_count > 0 else 0
            state_class = ""
            if state == "SUCCESS":
                state_class = "state-success"
            elif state == "FAILURE":
                state_class = "state-failure"
            elif state == "RUNNING":
                state_class = "state-running"
            
            html_content += f"""                <tr>
                    <td class="{state_class}">{html.escape(state)}</td>
                    <td>{count}</td>
                    <td>{percentage:.1f}%</td>
                </tr>
"""
        
        html_content += """            </table>
        </div>
        
        <h2>Detailed Runbook Execution Data</h2>
        <p style="color: #666; font-size: 14px;"><strong>Note:</strong> All times are displayed in IST (India Standard Time, UTC+5:30). Click the <strong>+</strong> icon to expand and view runbook execution details.</p>
        <table>
            <thead>
            <tr>
                <th style="width: 30px;"></th>
                <th>Runbook Name</th>
                <th>Start Time (IST)</th>
                <th>End Time (IST)</th>
                <th>Total Execution Time</th>
                <th>State</th>
                <th>Runlog UUID</th>
                <th>Task Name</th>
            </tr>
            </thead>
            <tbody>
"""
        
        for idx, runlog in enumerate(runlogs_data):
            state_class = ""
            if runlog["state"] == "SUCCESS":
                state_class = "state-success"
            elif runlog["state"] == "FAILURE":
                state_class = "state-failure"
            elif runlog["state"] == "RUNNING":
                state_class = "state-running"
            
            # Prepare data for row
            runbook_name = runlog.get("runlog_name", runlog["task_name"])
            row_id = f"row-{idx}"
            
            # Build row with expand icon
            html_content += f"""
                <tr class="expandable-row" onclick="toggleRunlogDetails('{row_id}')">
                    <td><span class="expand-icon" id="icon-{row_id}" onclick="toggleRunlogDetails('{row_id}'); event.stopPropagation();">+</span></td>
                    <td>{html.escape(runbook_name if runbook_name else "N/A")}</td>
                    <td>{html.escape(runlog["start_time_formatted"])}</td>
                    <td>{html.escape(runlog["end_time_formatted"])}</td>
                    <td>{html.escape(runlog["execution_duration"])}</td>
                    <td class="{state_class}">{html.escape(runlog["state"])}</td>
                    <td style="font-family: monospace; font-size: 11px;">{html.escape(runlog["runlog_uuid"])}</td>
                    <td>{html.escape(runlog["task_name"])}</td>
                </tr>
                <tr>
                    <td colspan="8">
                        <div class="runlog-details" id="runlog-{row_id}">
                            <h4 style="margin-top: 0; color: #7c9bc7;">Runbook Execution Details: {html.escape(runbook_name if runbook_name else runlog["task_name"])}</h4>
                            <div class="runlog-tree">{runlog['tree_structure']}</div>
                        </div>
                    </td>
                </tr>
"""
        
        html_content += """            </tbody>
        </table>
"""
        
        # Add graph sections
        if os.path.exists(start_times_png):
            html_content += f"""        <div class="graph-container">
            <h2>Runbook Execution Start Times</h2>
            <p style="color: #666; font-size: 14px;">Scatter plot showing when runbook executions were initiated</p>
            <img src="{os.path.basename(start_times_png)}" alt="Start Times Graph">
        </div>
"""
        
        if os.path.exists(exec_times_png):
            html_content += f"""        <div class="graph-container">
            <h2>Runbook Execution Durations</h2>
            <p style="color: #666; font-size: 14px;">Bar chart comparing execution times (coral = above average, blue = below average)</p>
            <img src="{os.path.basename(exec_times_png)}" alt="Execution Times Graph">
        </div>
"""
        
        html_content += """    </div>
</body>
</html>
"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"[INFO] HTML report saved to: {output_path}")
    except Exception as e:
        print(f"[ERROR] Failed to generate HTML report: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="Analyze Nutanix Calm Manager runbook execution statistics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with full NCM hostname
  python3 runbook_stats.py --host nconprem-10-122-152-117.ccpnx.com
  
  # Using short IP format (will construct full hostname)
  python3 runbook_stats.py --host 10-122-152-117
  
  # Filter by runlog name pattern (regex on metadata.name)
  python3 runbook_stats.py --host 10-122-152-117 --name "vmpower.*"
  
  # Filter successful executions only
  python3 runbook_stats.py --host 10-122-152-117 --state SUCCESS
  
  # Custom output directory and name
  python3 runbook_stats.py --host 10-122-152-117 --output weekly_runbook_report
  
  # Custom credentials for authentication
  python3 runbook_stats.py --host 10-122-152-117 --username admin --password Nutanix.123
  
  # Disable debug logging
  python3 runbook_stats.py --host 10-122-152-117 --no-debug

Output files (saved in directory: nutanix-calm-runbook-results/):
  - <output>.csv              : CSV export of runlog data
  - <output>.html             : Interactive HTML report with graphs
  - <output>_start_times.png  : Execution start times scatter plot
  - <output>_execution_times.png : Execution duration bar chart
  - <output>_p95_trend.png    : P95 performance trend line chart
  - <output>.log              : Console output and debug logs
        """
    )
    parser.add_argument("--host", required=True, 
                       help="NCM hostname or IP (e.g., nconprem-10-122-152-117.ccpnx.com or 10-122-152-117)")
    parser.add_argument("--username", default="ssp_admin@qa.nutanix.com", 
                       help="Username for Basic Auth (default: ssp_admin@qa.nutanix.com)")
    parser.add_argument("--password", default="nutanix/4u", 
                       help="Password for Basic Auth (default: nutanix/4u)")
    parser.add_argument("--output", default="runbook_stats", 
                       help="Output file prefix (default: runbook_stats)")
    parser.add_argument("--name", 
                       help="Filter by runlog name using regex pattern (e.g., 'vmpower.*')")
    parser.add_argument("--state", 
                       help="Filter by execution state (e.g., SUCCESS, FAILURE, RUNNING)")
    debug_group = parser.add_mutually_exclusive_group()
    debug_group.add_argument("--debug", dest="debug", action="store_true", 
                            help="Enable debug logs (default: enabled)")
    debug_group.add_argument("--no-debug", dest="debug", action="store_false", 
                            help="Disable debug logs")
    parser.set_defaults(debug=True)
    args = parser.parse_args()
    
    # Setup output directory
    output_dir = "nutanix-calm-runbook-results"
    os.makedirs(output_dir, exist_ok=True)
    print(f"[INFO] Created output directory: {output_dir}")
    
    # Setup logging
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
            print("[INFO] Debug logs enabled")
        else:
            print("[INFO] Debug logs disabled")
    except Exception as e:
        print(f"[WARNING] Unable to create log file: {e}")
    
    # Build API URL
    api_url = build_api_url(args.host)
    print(f"[INFO] Using API URL: {api_url}")
    
    # Parse URL for connection
    parsed = urlparse(api_url)
    hostname = parsed.hostname
    port = parsed.port or 443
    
    # Setup HTTPS connection
    conn = http.client.HTTPSConnection(
        host=hostname,
        port=port,
        context=ssl._create_unverified_context()
    )
    
    # Create auth headers
    auth_token = create_basic_auth(args.username, args.password)
    headers = {
        'Content-Type': "application/json",
        'Authorization': f"Basic {auth_token}"
    }
    
    # Fetch runlog list from NCM API
    print(f"[INFO] Querying NCM API for runbook execution logs...")
    try:
        response_data = get_runlog_list(conn, headers)
        entities = response_data.get("entities", [])
        
        if not entities:
            print("[ERROR] No runbook execution logs found")
            return
        
        print(f"[INFO] Processing {len(entities)} runbook execution logs...")
        
        # Extract data from each runlog entity
        runlogs_data = []
        for entity in entities:
            try:
                data = extract_runlog_data(entity)
                runlogs_data.append(data)
            except Exception as e:
                debug_log(f"[WARNING] Failed to extract data from runlog entity: {e}")
        
        print(f"[INFO] Successfully processed {len(runlogs_data)} runbook executions")
        
        # Apply filters if specified
        filtered_data = filter_runlogs(runlogs_data, args.name, args.state)
        
        if not filtered_data:
            print("[ERROR] No runbook executions match the specified filters")
            return
        
        # Calculate execution statistics
        stats = calculate_statistics(filtered_data)
        print(f"[INFO] Calculated statistics for {stats['count']} successful runbook executions")
        
        # Calculate total execution time summary
        total_summary = calculate_total_execution_summary(filtered_data)
        print(f"[INFO] Calculated total execution summary across {total_summary['total_count']} filtered runlogs")
        
        # Calculate P95 trend over time per task
        trend_data = calculate_p95_trend_by_task(filtered_data)
        print(f"[INFO] Calculated P95 performance trend for {len(trend_data)} unique tasks")
        
        # Generate all report files
        # Include filter in filename if provided
        output_name = args.output
        if args.name:
            # Sanitize filter name for filename
            filter_safe = re.sub(r'[^\w\-]', '_', args.name)[:50]
            output_name = f"{args.output}_filter_{filter_safe}"
        
        csv_path = os.path.join(output_dir, f"{output_name}.csv")
        html_path = os.path.join(output_dir, f"{output_name}.html")
        start_times_png = os.path.join(output_dir, f"{output_name}_start_times.png")
        exec_times_png = os.path.join(output_dir, f"{output_name}_execution_times.png")
        
        print("[INFO] Generating reports and visualizations...")
        generate_csv_report(filtered_data, csv_path)
        generate_start_times_graph(filtered_data, start_times_png)
        generate_execution_times_graph(filtered_data, exec_times_png)
        generate_html_report(filtered_data, stats, total_summary, trend_data, html_path, 
                           start_times_png, exec_times_png)
        
        print(f"\n[INFO] Reports generated in: {output_dir}")
        print(f"[INFO] HTML Report: {html_path}")
        print(f"[INFO] CSV Report: {csv_path}")
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch or process runbook execution logs: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
        if log_handle:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            log_handle.close()

if __name__ == "__main__":
    main()

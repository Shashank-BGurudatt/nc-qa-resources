#!/usr/bin/env python3
"""
Parallel Calm Marketplace Item Launch Script

Launches multiple Calm marketplace items (blueprints) in parallel. Handles all the
interactive prompts automatically by pressing ENTER, so you can run large batches
without having to sit there and respond to prompts.

What it does:
    - Launches apps in parallel using threads
    - Automatically handles prompts (just presses ENTER for everything)
    - Creates unique app names with a batch ID so you can find them later
    - Finds and uses the calm-dsl virtual environment if it's available
    - Shows debug output with timestamps so you know what's happening
    - Handles errors and timeouts gracefully
    - Can launch 1000+ apps by limiting how many run at once
    - Three different modes depending on what you need
    - Saves a separate log file for each calm launch command (helps with debugging)
    - Cleans up failed submissions automatically so they don't block slots
    - Better timeout handling to avoid getting stuck
    - Polls the API to track app status in real-time (Mode 3 only)

Execution Modes:
    
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ MODE 1: Batch without Sleep (default)                                  │
    │ ─────────────────────────────────────────────────────────────────────── │
    │                                                                         │
    │ Execution Flow:                                                        │
    │                                                                         │
    │   STEP 1: Submit Batch 1                                              │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Submit parallel_users apps simultaneously                 │     │
    │   │ - Start threads for all apps in batch                       │     │
    │   │ - Example: Submit apps 1-10 (if parallel_users=10)          │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 2: Wait for Batch 1 to Complete                                │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Wait for all threads in batch to finish                   │     │
    │   │ - Thread.join() for each app                                │     │
    │   │ - No delay after completion                                 │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 3: Submit Batch 2 (immediately)                                 │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Submit next parallel_users apps                           │     │
    │   │ - Start threads immediately (no sleep)                      │     │
    │   │ - Example: Submit apps 11-20                                 │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 4: Repeat until all apps submitted                             │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Continue batches 3, 4, 5... until count reached          │     │
    │   │ - Each batch waits for previous batch to complete           │     │
    │   │ - No sleep between batches                                  │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                                                                         │
    │ Timeline Example (count=100, parallel_users=10):                     │
    │   Time 0s:   Submit batch 1 (apps 1-10)                                │
    │   Time 30s:  Batch 1 complete → Submit batch 2 (apps 11-20)            │
    │   Time 60s:  Batch 2 complete → Submit batch 3 (apps 21-30)          │
    │   ... continues until all 100 apps submitted                           │
    │                                                                         │
    │ Use Case: Fast submission when you don't need delays                   │
    │ Example: --count 100 --parallel_users 10                               │
    └─────────────────────────────────────────────────────────────────────────┘
    
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ MODE 2: Batch with Sleep                                                │
    │ ─────────────────────────────────────────────────────────────────────── │
    │                                                                         │
    │ Execution Flow:                                                        │
    │                                                                         │
    │   STEP 1: Submit Batch 1                                              │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Submit parallel_users apps simultaneously                 │     │
    │   │ - Start threads for all apps in batch                       │     │
    │   │ - Example: Submit apps 1-10 (if parallel_users=10)          │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 2: Wait for Batch 1 to Complete                                │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Wait for all threads in batch to finish                   │     │
    │   │ - Thread.join() for each app                                │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 3: Sleep (batch_delay seconds)                                 │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Wait batch_delay seconds before next batch                │     │
    │   │ - Example: Sleep 5 seconds (if --batch_delay 5)            │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 4: Submit Batch 2                                               │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Submit next parallel_users apps                           │     │
    │   │ - Start threads for batch 2                                  │     │
    │   │ - Example: Submit apps 11-20                                 │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 5: Repeat until all apps submitted                             │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Continue batches 3, 4, 5... until count reached          │     │
    │   │ - Each batch: wait → sleep → submit next                    │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                                                                         │
    │ Timeline Example (count=100, parallel_users=10, batch_delay=5):        │
    │   Time 0s:   Submit batch 1 (apps 1-10)                                │
    │   Time 30s:  Batch 1 complete → Sleep 5s                              │
    │   Time 35s:  Submit batch 2 (apps 11-20)                               │
    │   Time 65s:  Batch 2 complete → Sleep 5s                              │
    │   Time 70s:  Submit batch 3 (apps 21-30)                               │
    │   ... continues with 5s sleep between each batch                       │
    │                                                                         │
    │ Use Case: Space out batch submissions to reduce system load            │
    │ Example: --count 100 --parallel_users 10 --batch_delay 5                │
    └─────────────────────────────────────────────────────────────────────────┘
    
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ MODE 3: Scheduling (Active Queue Management)                            │
    │ ─────────────────────────────────────────────────────────────────────── │
    │                                                                         │
    │ Execution Flow:                                                        │
    │                                                                         │
    │   STEP 1: Initial Submission                                           │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Submit up to parallel_users apps immediately             │     │
    │   │ - Move from pending_apps → active_queue                    │     │
    │   │ - Start threads for each app                                │     │
    │   │ - Example: Submit apps 1-10 (if parallel_users=10)          │     │
    │   │   active_queue = 10, pending = 90, complete = 0             │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 2: Wait for API (10 seconds)                                    │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Allow apps to appear in API after submission              │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 3: Main Polling Loop (every 30 seconds)                          │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ 3a. Query API for all tracked apps                            │     │
    │   │     - Get status of apps in active_queue                    │     │
    │   │     - Get status of apps in complete_queue (for cache)       │     │
    │   │                                                              │     │
    │   │ 3b. Check Active Queue Apps                                   │     │
    │   │     FOR each app in active_queue:                            │     │
    │   │       IF app found in API:                                   │     │
    │   │         IF state == "running" OR state == "error":          │     │
    │   │           → Move app to complete_queue                       │     │
    │   │           → Remove from active_queue (free slot)            │     │
    │   │           → Log: "✓ app_name moved to RUNNING" or           │     │
    │   │                  "✗ app_name moved to ERROR"                │     │
    │   │         ELSE IF state == "provisioning":                    │     │
    │   │           → Keep in active_queue (still provisioning)       │     │
    │   │       ELSE:                                                  │     │
    │   │         → Keep in active_queue (not in API yet)            │     │
    │   │                                                              │     │
    │   │     NOTE: Both "running" and "error" states free slots     │     │
    │   │           immediately, allowing new submissions             │     │
    │   │                                                              │     │
    │   │ 3c. Calculate Free Slots                                      │     │
    │   │     free_slots = parallel_users - len(active_queue)          │     │
    │   │                                                              │     │
    │   │ 3d. Submit New Apps (if slots available)                     │     │
    │   │     IF free_slots > 0 AND pending_apps not empty:          │     │
    │   │       apps_to_submit = min(free_slots, len(pending_apps))  │     │
    │   │       FOR each app to submit:                                │     │
    │   │         → Start thread for automate_calm_launch()          │     │
    │   │         → Add to active_queue IMMEDIATELY (before thread    │     │
    │   │           completes) - reserves slot                       │     │
    │   │         → Wait for thread.join() to complete                │     │
    │   │         → Check results[app_name][0] for success           │     │
    │   │         → IF submission failed:                             │     │
    │   │             → Remove from active_queue immediately          │     │
    │   │             → Move to complete_queue with error state       │     │
    │   │             → Free slot for next submission                 │     │
    │   │         → IF submission succeeded:                          │     │
    │   │             → Keep in active_queue (will be tracked      │     │
    │   │               by API polling)                               │     │
    │   │                                                              │     │
    │   │ 3e. Print Status                                              │     │
    │   │     "Active: X, Complete: Y, Pending: Z"                    │     │
    │   │                                                              │     │
    │   │ 3f. Check Completion                                          │     │
    │   │     IF len(complete_queue) >= count:                        │     │
    │   │       → Break loop (all apps reached running)              │     │
    │   │                                                              │     │
    │   │ 3g. Wait 30 seconds before next poll                         │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 4: Cleanup                                                      │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Wait for all submission threads to complete               │     │
    │   │ - Calculate provisioning time from app statuses            │     │
    │   │ - Return results and app_statuses                           │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                                                                         │
    │ Timeline Example (count=100, parallel_users=10):                     │
    │   Time 0s:   Submit apps 1-10 → active=10, pending=90, complete=0   │
    │   Time 10s:  Wait for API (initial delay)                             │
    │   Time 10s:  Poll #1 - Apps 1-3: running → complete=3, active=7       │
    │             Submit apps 11-13 → active=10, pending=87                  │
    │   Time 40s:  Poll #2 - Apps 4-6: running → complete=6, active=7       │
    │             Submit apps 14-16 → active=10, pending=84                  │
    │   Time 70s:  Poll #3 - Apps 7-9: running → complete=9, active=7       │
    │             Submit apps 17-19 → active=10, pending=81                 │
    │   ... continues until all 100 apps reach "running" state               │
    │                                                                         │
    │ Key Features:                                                          │
    │   - Maintains exactly parallel_users apps in active queue            │
    │   - Only submits new apps when slots free up                          │
    │   - State-based tracking (waits for "running" or "error" state)      │
    │   - Immediate slot recovery on submission failures                    │
    │   - Prevents system overload                                           │
    │   - Uses Nutanix API for status polling (not CLI)                     │
    │   - Uses CLI command (calm launch) for job submission                 │
    │                                                                         │
    │ Use Case: Maintain constant concurrency during provisioning           │
    │ Example: --count 100 --parallel_users 10 --scheduling --host example.com│
    └─────────────────────────────────────────────────────────────────────────┘

Log Files:
    The script creates two types of log files:
    
    1. Console Logs (Main Script Output):
       - If --log_file NOT specified:
         * Creates: parallel_calm_launch_YYYYMMDD-HHMMSS-{uuid}.log in current directory
         * Example: parallel_calm_launch_20251230-143022-a1b2c3d4.log
       - If --log_file specified:
         * Uses: The path you provided
         * Example: --log_file /path/to/my.log creates /path/to/my.log
    
    2. Calm Launch Logs (Command Output):
       - If --log_file NOT specified:
         * Directory: {CWD}/calm-launch-logs/
         * Files: calm-app-launch-console-YYYYMMDD-HHMMSS-{app_name}.log
       - If --log_file specified:
         * Directory: {log_file_directory}/calm-launch-logs/
         * Files: calm-app-launch-console-YYYYMMDD-HHMMSS-{app_name}.log
         * Example: If --log_file /path/to/logs/script.log, logs go to /path/to/logs/calm-launch-logs/
    
    All log files are preserved after execution for debugging.

Scalability:
    - Supports launching 1000+ apps with configurable parallel_users parameter
    - Default parallel_users=50 prevents resource exhaustion
    - Semaphore-based concurrency control limits simultaneous launches
    - Handles up to 100 prompts per launch (safety limit to prevent infinite loops)
    - Thread-safe result collection for parallel execution

Error Handling & Logging:
    - Automatic failure detection during command execution and prompt handling
    - Failed submissions immediately removed from active_queue (prevents slot leaks)
    - Two types of log files created:
      * Console logs: Main script output (stdout/stderr)
        - Default: parallel_calm_launch_YYYYMMDD-HHMMSS-{uuid}.log in current directory
        - Custom: Use --log_file to specify path
      * Calm launch logs: Individual log files for each calm launch command
        - Default: calm-launch-logs/ directory in current directory
        - Custom: calm-launch-logs/ subdirectory next to --log_file if specified
        - Format: calm-app-launch-console-YYYYMMDD-HHMMSS-{app_name}.log
        - Preserved for debugging (not deleted)
    - Enhanced timeout handling:
      * Per-prompt timeout: 5 minutes (300 seconds)
      * Overall command timeout: 10 minutes (600 seconds)
      * Activity tracking: detects if no prompt activity for 5+ minutes
      * Safety limit: maximum 100 prompts to prevent infinite loops
    - Multiple failure detection methods:
      * Exit code checking (non-zero = failure)
      * ERROR message pattern matching in output
      * Failure state detection in API responses
      * Output analysis: extracts error details from command output
    - Failed apps tracked in complete_queue with error state
    - Detailed error logging with exit codes and error messages

How it works - API vs CLI:
    The script uses two different things:
    
    1. CLI Command (calm launch) - For submitting jobs:
       - Uses pexpect to handle the interactive prompts
       - Runs the command locally: "calm launch marketplace item ..."
       - Automatically presses ENTER for all prompts
       - Returns 0 if it worked, non-zero if it failed
       - This is a command-line tool, not an API
    
    2. Nutanix API (POST /api/nutanix/v3/apps/list) - For checking status:
       - HTTP POST to Nutanix Prism Central
       - Only used in Mode 3 (scheduling) to check app statuses
       - Called every 30 seconds
       - Endpoint: https://ncm.services.{host}/api/nutanix/v3/apps/list
       - Uses Basic Auth (username:password)
       - Returns JSON with app statuses (running, error, provisioning, etc.)
       - Only used for checking status, not for submitting jobs
    
    Why use both?
    - CLI handles all the prompt stuff automatically
    - API is faster for checking status of lots of apps
    - Can check up to 250 apps in one API call
    - Get status updates without having to parse CLI output

How the active queue works:
    In scheduling mode, we keep track of apps that are being provisioned:
    
    1. Finding free slots:
       - Check the API every 30 seconds
       - Look at apps in active_queue to see their state
       - If state is "running" OR "error", move it to complete_queue
       - Free slots = parallel_users - how many apps are in active_queue
    
    2. What happens in order:
       a. Check the API to get app statuses
       b. Update active_queue (remove apps that are done) - this frees slots right away
       c. Figure out free_slots = parallel_users - len(active_queue)
       d. Submit new jobs (start threads)
       e. Add to active_queue right away (before thread finishes) - reserves the slot
       f. Wait for thread to finish (thread.join())
       g. Check results[app_name][0] to see if it worked
       h. If it failed, remove from active_queue right away (free the slot)
       i. If it worked, keep it in active_queue (API polling will track it)
    
    3. What happens when a submission fails:
       - App gets added to active_queue when the thread starts (around line 1065)
       - After thread.join(), we check the results dictionary
       - If results[app_name][0] is False:
         * Remove it from active_queue right away
         * Move it to complete_queue with error state
         * Log the error (exit code, error message)
         * Free the slot so we can submit the next one
       - This stops "slot leaks" where failed submissions block slots forever
    
    4. Where to look in the code:
       - Line 1018-1044: run_scheduling_mode() - the main polling loop
       - Line 1044-1046: Remove apps from active_queue (frees slots)
       - Line 1064-1065: Add to active_queue before thread finishes
       - Line 1072-1090: Check results and remove failed submissions
       - Line 345-442: query_app_status() - the API polling function
       - Line 445-808: automate_calm_launch() - runs the CLI command

Usage Examples:
    # Mode 1: Batch without sleep
    python3 parallel_calm_launch.py --count 100 --item Foundation-Lite \\
        --base_app_name automation --project projectbk --version 4.0.0
    
    # Mode 2: Batch with sleep
    python3 parallel_calm_launch.py --count 100 --item Foundation-Lite \\
        --base_app_name automation --project projectbk --version 4.0.0 --batch_delay 5
    
    # Mode 3: Scheduling mode
    python3 parallel_calm_launch.py --count 100 --item Foundation-Lite \\
        --base_app_name automation --project projectbk --version 4.0.0 \\
        --scheduling --host nconprem-10-122-152-117.ccpnx.com --parallel_users 10

Requirements:
    - pexpect module (auto-installed or available in calm-dsl venv)
    - calm CLI tool (in calm-dsl venv or system PATH)
    - Access to Calm marketplace and project

Author: Manish Gupta
Date: 2025
"""

import sys
import os
import re
import argparse
from argparse import ArgumentDefaultsHelpFormatter
import threading
import time
import uuid
import json
import base64
import http.client
import ssl
from datetime import datetime
from urllib.parse import urlparse

# Global log file handle for file logging
_log_file = None
_log_lock = threading.Lock()


class TeeOutput:
    """Class to duplicate output to both console and file."""
    def __init__(self, file_handle):
        self.file = file_handle
        self.stdout = sys.stdout
        self.stderr = sys.stderr
    
    def write(self, text):
        self.stdout.write(text)
        if self.file:
            try:
                self.file.write(text)
                self.file.flush()
            except:
                pass
    
    def flush(self):
        self.stdout.flush()
        if self.file:
            try:
                self.file.flush()
            except:
                pass


def setup_file_logging(log_file_path):
    """Setup file logging by redirecting stdout/stderr to both console and file."""
    global _log_file
    try:
        # Create directory if it doesn't exist
        log_dir = os.path.dirname(log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        _log_file = open(log_file_path, 'w', encoding='utf-8')
        # Redirect stdout and stderr to TeeOutput (writes to both console and file)
        sys.stdout = TeeOutput(_log_file)
        sys.stderr = TeeOutput(_log_file)
        return True
    except Exception as e:
        print(f"[WARNING] Failed to setup file logging: {e}")
        return False

# Try to import pytz for timezone conversion (optional, will handle gracefully if not available)
try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

# ============================================================================
# Auto-detect Python Environment
# ============================================================================
# If pexpect is not available in the current Python environment, automatically
# switch to the calm-dsl virtual environment's Python which should have pexpect
# installed. This allows the script to work without manual environment setup.
# ============================================================================
try:
    import pexpect
except ImportError:
    # Try to find calm-dsl venv Python from environment variable
    # If CALM_DSL_DIR is set, use it; otherwise try to auto-detect from current directory
    CALM_DSL_DIR = os.environ.get('CALM_DSL_DIR', None)
    
    # If not set, try to find calm-dsl in current directory or parent directories
    if not CALM_DSL_DIR:
        current_dir = os.getcwd()
        # Check current directory and parent for calm-dsl
        for check_dir in [current_dir, os.path.dirname(current_dir)]:
            if os.path.exists(os.path.join(check_dir, 'venv', 'bin', 'python')):
                CALM_DSL_DIR = check_dir
                break
    
    if CALM_DSL_DIR:
        venv_python = os.path.join(CALM_DSL_DIR, 'venv', 'bin', 'python')
    else:
        venv_python = None
    
    if venv_python and os.path.exists(venv_python):
        # Restart script with venv Python that has pexpect
        # Use __file__ to get the full path to the script
        script_path = os.path.abspath(__file__)
        print(f"pexpect not found in current Python, switching to: {venv_python}")
        print(f"Restarting script: {script_path}")
        print("Restarting script with venv Python...")
        try:
            os.execv(venv_python, [venv_python, script_path] + sys.argv[1:])
        except Exception as e:
            print(f"Error: Failed to restart with venv Python: {e}")
            print("Please install pexpect in current environment: pip install pexpect")
            sys.exit(1)
    else:
        # Neither pexpect nor venv found - exit with helpful error message
        print("Error: pexpect module not found and calm-dsl venv not found.")
        print(f"Please install pexpect: pip install pexpect")
        print(f"Or set CALM_DSL_DIR environment variable to point to your calm-dsl directory")
        sys.exit(1)


# ============================================================================
# API Functions for Scheduling Mode
# ============================================================================

def build_api_url(host_url):
    """
    Build complete API URL from host.
    
    Args:
        host_url (str): Host URL (e.g., "nconprem-10-122-152-117.ccpnx.com")
    
    Returns:
        str: Complete API URL
    """
    if not host_url.startswith('http'):
        return f"https://ncm.services.{host_url}/api/nutanix/v3/apps/list"
    return f"{host_url}/api/nutanix/v3/apps/list"


def create_basic_auth(username, password):
    """
    Create Basic Auth header value.
    
    Args:
        username (str): Username for Basic Auth
        password (str): Password for Basic Auth
    
    Returns:
        str: Base64 encoded Basic Auth header value
    """
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return encoded


def query_app_status(host, username, password, app_names=None, timeout=180, max_retries=1):
    """
    Queries the Nutanix API to get app statuses.
    
    This uses the Nutanix API (not the CLI) to check app statuses. It calls
    POST /api/nutanix/v3/apps/list at https://ncm.services.{host}/api/nutanix/v3/apps/list
    with Basic Auth. We only use this for checking status, not for submitting jobs.
    
    Args:
        host (str): Host URL like "nconprem-10-122-152-117.ccpnx.com"
        username (str): Username for Basic Auth
        password (str): Password for Basic Auth
        app_names (list, optional): List of app names to filter. If None, gets all apps
        timeout (int): How long to wait for API response in seconds (default: 180)
        max_retries (int): How many times to retry (default: 1, since we'll retry on next poll anyway)
    
    Returns:
        dict: Dictionary mapping app_name to {
            'uuid': str - app uuid,
            'state': str - "running", "error", "provisioning", etc,
            'creation_time': int - timestamp in microseconds,
            'last_update_time': int - timestamp in microseconds
        }
        Returns empty dict if it fails. We'll try again on the next poll.
    
    Notes:
        - Called every 30 seconds in scheduling mode
        - Used to see when apps get to "running" or "error" state
        - Both "running" and "error" free up slots in the active queue
        - If it times out, we log it but keep going (next poll will retry)
    """
    api_url = build_api_url(host)
    parsed = urlparse(api_url)
    hostname = parsed.hostname
    port = parsed.port or 443
    
    auth_token = create_basic_auth(username, password)
    headers = {
        'Content-Type': "application/json",
        'Authorization': f"Basic {auth_token}"
    }
    
    payload = {"length": 250}
    
    # Single attempt with longer timeout - next poll iteration will retry anyway
    try:
        # Create connection with timeout
        conn = http.client.HTTPSConnection(
            host=hostname,
            port=port,
            timeout=timeout,
            context=ssl._create_unverified_context()
        )
        
        # Make request with timeout
        conn.request("POST", "/api/nutanix/v3/apps/list", json.dumps(payload), headers)
        res = conn.getresponse()
        data = res.read()
        conn.close()
        
        if res.status != 200:
            print(f"[WARNING] API query failed with status {res.status}")
            return {}
        
        # Parse response
        app_list = json.loads(data)
        if "entities" not in app_list:
            print(f"[WARNING] API response missing 'entities' key")
            return {}
        
        entities = app_list["entities"]
        result = {}
        
        for app in entities:
            status = app.get("status", {})
            app_name = status.get("name", "")
            
            # Filter by app_names if provided
            if app_names and app_name not in app_names:
                continue
            
            app_uuid = status.get("uuid", "")
            app_state = status.get("state", "N/A")
            creation_time = status.get("creation_time")
            last_update_time = status.get("last_update_time")
            
            if app_name and app_uuid:
                result[app_name] = {
                    'uuid': app_uuid,
                    'state': app_state,
                    'creation_time': creation_time,
                    'last_update_time': last_update_time
                }
        
        # Success - return result
        return result
        
    except (TimeoutError, OSError) as e:
        # API response timeout - log clearly and continue (next poll will retry)
        num_apps = len(app_names) if app_names else "all"
        print(f"[WARNING] API request sent but no response received in {timeout} seconds (querying {num_apps} apps)")
        print(f"[WARNING] Will retry in next poll iteration")
        return {}
    except Exception as e:
        # Other errors
        num_apps = len(app_names) if app_names else "all"
        print(f"[ERROR] Unexpected error querying API for {num_apps} apps: {e}")
        return {}


def automate_calm_launch(item_name, app_name, project, version, environment=None, calm_dsl_dir=None, results=None, semaphore=None, calm_launch_log_dir=None, mode_tag=None):
    """
    Runs a single calm launch command and handles all the prompts automatically.
    
    This runs the 'calm launch marketplace item' command and automatically presses
    ENTER for every prompt that comes up. It also handles timeouts and delays.
    
    Note: This uses the CLI command (not an API) to submit jobs. It runs
    "calm launch marketplace item ..." using pexpect, handles prompts by sending
    ENTER, and returns 0 if it worked or a non-zero exit code if it failed.
    
    Args:
        item_name (str): The blueprint name like "Foundation-Lite"
        app_name (str): Unique name for this app instance
        project (str): Project name where the app will be launched
        version (str): Version like "4.0.0"
        environment (str, optional): Environment name
        calm_dsl_dir (str, optional): Path to calm-dsl directory. If given, switches to that
                                     directory and uses the venv there if it exists
        results (dict, optional): Dictionary to store results. Stores (success, exit_code, error_message)
                                 for each app_name
        semaphore (threading.Semaphore, optional): Used to limit how many can run at once. Grabs it at the start
                                                   and releases it when done
        calm_launch_log_dir (str, optional): Where to save log files. Creates a file like
                                            calm-app-launch-console-20251230-155510-app-name.log
    
    Returns:
        None: Results go into the results dictionary if you provided one.
    
    What it does:
        - Changes to calm_dsl_dir if provided
        - Runs the calm command in a subprocess
        - Prints debug messages
        - Saves results in the results dict
        - Creates a log file if calm_launch_log_dir is set
    
    How it handles errors:
        - Checks exit code (0 = good, anything else = bad)
        - Looks for ERROR messages in the output
        - Checks for failure states in API responses
        - Saves error details in results
        - Keeps the log file so you can debug later
    
    Timeout handling:
        - Waits up to 5 minutes per prompt
        - Overall command can take up to 10 minutes
        - Stops after 100 prompts (safety check to avoid infinite loops)
        - If nothing happens for 5 minutes, tries sending ENTER
        - Checks if the process is still alive
    
    Example:
        results = {}
        semaphore = threading.Semaphore(50)
        automate_calm_launch(
            item_name="Foundation-Lite",
            app_name="my-app-1",
            project="projectbk",
            version="4.0.0",
            calm_dsl_dir="/path/to/calm-dsl",
            results=results,
            semaphore=semaphore,
            calm_launch_log_dir="/path/to/logs/calm-launch-logs"
        )
        # Check results['my-app-1'] for (success, exit_code, error_message)
    """
    # Acquire semaphore if provided (for concurrency limiting)
    # This ensures we don't exceed parallel_users limit
    if semaphore:
        semaphore.acquire()
    
    try:
        # Store original directory to restore later
        original_cwd = os.getcwd()
        debug_output = []
        
        def debug(msg):
            """
            Helper function to print debug messages with timestamp, mode tag, and app name.
            """
            timestamp = datetime.now().strftime("%H:%M:%S")
            # Include mode tag if provided, otherwise just timestamp and app name
            if mode_tag:
                debug_msg = f"[{timestamp}] [{mode_tag}] [{app_name}] {msg}"
            else:
                debug_msg = f"[{timestamp}] [{app_name}] {msg}"
            debug_output.append(debug_msg)
            print(debug_msg)

        # Log computed APP_INDEX once at launch start for traceability.
        computed_app_index = extract_app_index(app_name)
        debug(f"Computed APP_INDEX for this launch: {computed_app_index}")
        
        # Determine the calm command to use
        calm_cmd = "calm"
        env = os.environ.copy()
        
        if calm_dsl_dir:
            try:
                debug(f"Changing directory to: {calm_dsl_dir}")
                os.chdir(calm_dsl_dir)
                
                # Check if venv exists and use it
                venv_path = os.path.join(calm_dsl_dir, "venv")
                if os.path.exists(venv_path):
                    # First try to use venv's calm executable directly
                    venv_calm = os.path.join(venv_path, "bin", "calm")
                    if os.path.exists(venv_calm):
                        calm_cmd = venv_calm
                        debug(f"Using venv calm executable: {venv_calm}")
                    else:
                        # Try Windows path
                        venv_calm = os.path.join(venv_path, "Scripts", "calm.exe")
                        if os.path.exists(venv_calm):
                            calm_cmd = venv_calm
                            debug(f"Using venv calm executable (Windows): {venv_calm}")
                        else:
                            # Fall back to python -m calm
                            venv_python = os.path.join(venv_path, "bin", "python")
                            if os.path.exists(venv_python):
                                calm_cmd = f"{venv_python} -m calm"
                                debug(f"Using venv Python: {venv_python}")
                            else:
                                debug("WARNING: venv found but calm/python not found, using system calm")
                    # Set VIRTUAL_ENV for proper environment
                    env['VIRTUAL_ENV'] = venv_path
                    # Add venv bin to PATH (so calm can find its dependencies)
                    venv_bin = os.path.join(venv_path, "bin")
                    if os.path.exists(venv_bin):
                        env['PATH'] = venv_bin + os.pathsep + env.get('PATH', '')
                else:
                    debug("No venv found, using system calm command")
                    
            except Exception as e:
                error_msg = f"Failed to change directory: {e}"
                debug(f"ERROR: {error_msg}")
                if results is not None:
                    results[app_name] = (False, 1, error_msg)
                # Release semaphore before early return
                if semaphore:
                    semaphore.release()
                return
        
        # Build command exactly matching the sample format
        # Format: calm launch marketplace item {item_name} --app_name {app_name} --project {project} --version {version} [--environment {environment}]
        # Note: item_name is used exactly as provided (e.g., "Foundation-Lite")
        cmd = f"{calm_cmd} -v launch marketplace item {item_name} --app_name {app_name} --project {project} --version {version}"
        if environment:
            cmd += f" --environment {environment}"
        debug(f"Item name (BP): {item_name}")
        debug(f"Executing command: {cmd}")
        
        # Spawn the process with a reasonable timeout and environment
        # Use logfile to capture all output for error parsing
        import tempfile
        
        # Create separate log file for calm launch command output if calm_launch_log_dir is provided
        if calm_launch_log_dir:
            # Create directory if it doesn't exist
            os.makedirs(calm_launch_log_dir, exist_ok=True)
            # Create log file with timestamp: calm-app-launch-console-YYYYMMDD-HHMMSS-{app_name}.log
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            logfile_path = os.path.join(calm_launch_log_dir, f"calm-app-launch-console-{timestamp}-{app_name}.log")
            logfile_handle = open(logfile_path, 'w', encoding='utf-8')
            debug(f"Calm launch command output will be logged to: {os.path.abspath(logfile_path)}")
        else:
            # Use temp file if no log directory provided
            logfile_obj = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.log')
            logfile_path = logfile_obj.name
            logfile_obj.close()
            logfile_handle = open(logfile_path, 'w', encoding='utf-8')
        
        # Write initial information to log file (command, timestamp, etc.)
        log_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logfile_handle.write(f"[{log_timestamp}] Starting calm launch command\n")
        logfile_handle.write(f"[{log_timestamp}] App Name: {app_name}\n")
        logfile_handle.write(f"[{log_timestamp}] Item Name: {item_name}\n")
        logfile_handle.write(f"[{log_timestamp}] Project: {project}\n")
        logfile_handle.write(f"[{log_timestamp}] Version: {version}\n")
        if environment:
            logfile_handle.write(f"[{log_timestamp}] Environment: {environment}\n")
        logfile_handle.write(f"[{log_timestamp}] Command: {cmd}\n")
        logfile_handle.write(f"[{log_timestamp}] {'='*80}\n")
        logfile_handle.write(f"[{log_timestamp}] Command output starts below:\n")
        logfile_handle.write(f"[{log_timestamp}] {'='*80}\n")
        logfile_handle.flush()
        
        # Spawn process with timeout: 10 minutes overall, 5 minutes per prompt
        child = pexpect.spawn(cmd, encoding='utf-8', timeout=600, env=env, logfile=logfile_handle)
        
        # Capture all output for error parsing
        all_output = []
        
        # Patterns to match prompts
        prompt_pattern = re.compile(r"Value for '.*?' in app_profile\.AHV\.variable.*?:")
        choose_pattern = re.compile(r"Choose from given choices:")
        
        # Patterns to match errors and failures
        error_pattern = re.compile(r"\[ERROR\].*?Failed to launch blueprint")
        failure_state_pattern = re.compile(r"'state':\s*['\"]failure['\"]")
        message_list_pattern = re.compile(r"'message_list':\s*\[(.*?)\]", re.DOTALL)
        
        # Handle prompts until process completes
        # Each prompt requires pressing ENTER to accept the default value
        debug("Waiting for prompts...")
        
        # Track prompt handling for better error reporting
        prompt_count = 0
        max_prompts = 100  # Safety limit to prevent infinite loops
        last_prompt_time = time.time()
        prompt_timeout = 300  # 5 minutes per prompt
        
        while True:
            try:
                # Check if we've been waiting too long without any activity
                current_time = time.time()
                if current_time - last_prompt_time > prompt_timeout:
                    debug(f"WARNING: No prompt activity for {prompt_timeout} seconds, checking process status...")
                    if not child.isalive():
                        debug("Process is not alive, breaking...")
                        break
                    # Try sending ENTER in case we're stuck
                    try:
                        child.sendline('')
                        time.sleep(0.5)
                        last_prompt_time = time.time()
                    except:
                        pass
                
                # Wait for prompt with timeout - handles delays gracefully
                index = child.expect([
                    prompt_pattern,
                    choose_pattern,
                    pexpect.EOF,
                    pexpect.TIMEOUT
                ], timeout=prompt_timeout)  # 5 minute timeout per prompt
                
                last_prompt_time = time.time()  # Update last activity time
                
                # Capture output before processing
                if child.before:
                    all_output.append(child.before)
                if hasattr(child, 'after') and child.after:
                    all_output.append(child.after)
                
                if index == 0:  # Found a "Value for..." prompt
                    prompt_count += 1
                    if prompt_count > max_prompts:
                        error_msg = f"Exceeded maximum prompt count ({max_prompts}), possible infinite loop"
                        debug(f"ERROR: {error_msg}")
                        if results is not None:
                            results[app_name] = (False, 1, error_msg)
                        child.close()
                        logfile_handle.close()
                        if calm_dsl_dir:
                            os.chdir(original_cwd)
                        return
                    prompt_text = child.after if isinstance(child.after, str) else str(child.after)
                    app_index_value = extract_app_index(app_name)
                    try:
                        if "APP_INDEX" in prompt_text:
                            prompt_snippet = " ".join(prompt_text.split())[:160]
                            debug(f"APP_INDEX prompt snippet: {prompt_snippet}")
                            debug(f"Found prompt #{prompt_count} for APP_INDEX, sending value: {app_index_value}")
                            child.sendline(app_index_value)
                        else:
                            debug(f"Found prompt #{prompt_count}, sending ENTER...")
                            child.sendline('')  # Send ENTER for non-APP_INDEX prompts
                        # Small delay to ensure prompt is processed
                        time.sleep(0.1)
                    except Exception as e:
                        error_msg = f"Failed to send ENTER to prompt: {e}"
                        debug(f"ERROR: {error_msg}")
                        if results is not None:
                            results[app_name] = (False, 1, error_msg)
                        child.close()
                        logfile_handle.close()
                        if calm_dsl_dir:
                            os.chdir(original_cwd)
                        return
                    
                elif index == 1:  # "Choose from given choices:"
                    debug("Found 'Choose from given choices:', waiting for actual prompt...")
                    continue
                    
                elif index == 2:  # EOF - process completed
                    debug("Process completed (EOF)")
                    # Capture remaining output
                    if child.before:
                        all_output.append(child.before)
                    break
                    
                elif index == 3:  # TIMEOUT
                    debug(f"Timeout waiting for prompt (timeout={prompt_timeout}s), checking if process is still alive...")
                    if not child.isalive():
                        debug("Process is not alive, breaking...")
                        # Capture remaining output
                        if child.before:
                            all_output.append(child.before)
                        break
                    # If still alive, try sending ENTER and continue waiting
                    debug("Process still alive, sending ENTER and continuing...")
                    try:
                        child.sendline('')
                        time.sleep(0.5)
                    except Exception as e:
                        debug(f"WARNING: Failed to send ENTER after timeout: {e}")
                    continue
                    
            except pexpect.EOF:
                debug("Received EOF, process ended")
                break
            except pexpect.TIMEOUT:
                debug(f"Pexpect TIMEOUT exception (timeout={prompt_timeout}s), checking process status...")
                if not child.isalive():
                    debug("Process is not alive, breaking...")
                    break
                # Try sending ENTER in case we're stuck
                try:
                    debug("Process still alive, sending ENTER and continuing...")
                    child.sendline('')
                    time.sleep(0.5)
                    last_prompt_time = time.time()
                except Exception as e:
                    debug(f"WARNING: Failed to send ENTER after timeout: {e}")
                continue
            except pexpect.ExceptionPexpect as e:
                error_msg = f"Pexpect error during prompt handling: {e}"
                debug(f"ERROR: {error_msg}")
                # Capture any available output before breaking
                try:
                    if child.before:
                        all_output.append(child.before)
                except:
                    pass
                if results is not None:
                    results[app_name] = (False, 1, error_msg)
                child.close()
                logfile_handle.close()
                if calm_dsl_dir:
                    os.chdir(original_cwd)
                return
            except Exception as e:
                error_msg = f"Unexpected error in expect loop: {e}"
                debug(f"ERROR: {error_msg}")
                # Try to recover by sending ENTER
                try:
                    child.sendline('')
                    time.sleep(0.5)
                    last_prompt_time = time.time()
                except:
                    pass
                # If process is dead, break
                if not child.isalive():
                    debug("Process is not alive, breaking...")
                    break
                # If process is still alive, continue (might be recoverable)
                debug("Process still alive, continuing...")
                continue
        
        # Wait a bit for process to fully terminate
        if child.isalive():
            debug("Waiting for process to terminate...")
            child.wait()
        
        # Capture any remaining output
        try:
            # Try to read any remaining output
            remaining = child.read()
            if remaining:
                all_output.append(remaining)
        except:
            pass
        
        # Write final information to log file before closing
        end_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        exit_status = child.exitstatus if child.exitstatus is not None else "unknown"
        logfile_handle.write(f"\n[{end_timestamp}] {'='*80}\n")
        logfile_handle.write(f"[{end_timestamp}] Command execution completed\n")
        logfile_handle.write(f"[{end_timestamp}] Exit code: {exit_status}\n")
        logfile_handle.write(f"[{end_timestamp}] {'='*80}\n")
        logfile_handle.flush()
        
        # Close logfile handle before reading
        logfile_handle.close()
        child.close()
        
        # Read the logfile to get all output
        try:
            with open(logfile_path, 'r', encoding='utf-8') as f:
                full_output = f.read()
            # Only delete temp file if it's not in calm_launch_log_dir (user wants to keep those)
            if not calm_launch_log_dir:
                os.unlink(logfile_path)  # Clean up temp file
            else:
                debug(f"Calm launch log file preserved at: {os.path.abspath(logfile_path)}")
        except Exception as e:
            debug(f"Warning: Could not read logfile: {e}")
            # Fallback to collected output
            full_output = ''.join(all_output)
        
        if calm_dsl_dir:
            os.chdir(original_cwd)
        
        # Parse for errors and failure reasons
        error_message = None
        launch_success = True
        
        # Check for ERROR messages
        if error_pattern.search(full_output):
            launch_success = False
            debug("ERROR message detected in output")
        
        # Check for failure state in API response
        if failure_state_pattern.search(full_output):
            launch_success = False
            debug("Failure state detected in API response")
            
            # Extract error messages from message_list - more robust parsing
            # Look for the message_list section in the status dictionary
            message_list_section = None
            # Try to find the message_list array
            message_list_match = re.search(r"'message_list':\s*\[(.*?)\]", full_output, re.DOTALL)
            if message_list_match:
                message_list_section = message_list_match.group(1)
            
            # Extract individual error messages with their details
            error_details = []
            
            # Pattern to match each error object in message_list
            # Format: {'message': '...', 'reason': '...', 'details': {...}}
            error_obj_pattern = re.compile(r"\{[^}]*'message':\s*['\"]([^'\"]+)['\"][^}]*'reason':\s*['\"]([^'\"]+)['\"][^}]*\}", re.DOTALL)
            
            if message_list_section:
                # Find all error objects in the message_list
                for match in error_obj_pattern.finditer(message_list_section):
                    msg = match.group(1)
                    reason = match.group(2)
                    error_details.append(f"{msg} (reason: {reason})")
            
            # Fallback: if we didn't find structured errors, try simple extraction
            if not error_details:
                message_matches = re.findall(r"'message':\s*['\"]([^'\"]+)['\"]", full_output)
                reason_matches = re.findall(r"'reason':\s*['\"]([^'\"]+)['\"]", full_output)
                
                if message_matches:
                    for i, msg in enumerate(message_matches):
                        reason = reason_matches[i] if i < len(reason_matches) else "UNKNOWN"
                        error_details.append(f"{msg} (reason: {reason})")
            
            if error_details:
                # Combine first few errors, limit total length
                error_message = "; ".join(error_details[:3])  # Limit to first 3 errors
                if len(error_details) > 3:
                    error_message += f" ... and {len(error_details) - 3} more"
                
                # Truncate if too long
                if len(error_message) > 200:
                    error_message = error_message[:197] + "..."
            else:
                # No structured errors found, but failure state detected
                error_message = "Launch failed (check API response for details)"
        
        exit_status = child.exitstatus if child.exitstatus is not None else 1
        
        # Launch is successful only if exit code is 0 AND no error messages found
        success = (exit_status == 0) and launch_success
        
        if not success and error_message:
            debug(f"Launch failed: {error_message}")
            if calm_launch_log_dir:
                debug(f"Check calm launch log for details: {os.path.abspath(logfile_path)}")
        elif not success:
            debug(f"Launch failed (exit code: {exit_status})")
            if calm_launch_log_dir:
                debug(f"Check calm launch log for details: {os.path.abspath(logfile_path)}")
            # Try to extract more error info from output
            if full_output:
                # Look for common error patterns
                if "ERROR" in full_output or "error" in full_output.lower():
                    # Extract last few lines that might contain error
                    lines = full_output.split('\n')
                    error_lines = [line for line in lines[-20:] if 'error' in line.lower() or 'ERROR' in line or 'failed' in line.lower()]
                    if error_lines:
                        debug(f"Recent error lines from output: {'; '.join(error_lines[:3])}")
        else:
            debug(f"Launch successful")
        
        debug(f"Process finished with exit code: {exit_status} (Success: {success})")
        
        if results is not None:
            # Store: (success, exit_code, error_message)
            results[app_name] = (success, exit_status, error_message)
    
    except pexpect.ExceptionPexpect as e:
        error_msg = f"Pexpect error: {e}"
        if 'debug' in locals():
            debug(f"ERROR: {error_msg}")
        else:
            print(f"[{app_name}] ERROR: {error_msg}")
        if calm_dsl_dir and 'original_cwd' in locals():
            os.chdir(original_cwd)
        if results is not None:
            results[app_name] = (False, 1, error_msg)
    except KeyboardInterrupt:
        if 'debug' in locals():
            debug("Interrupted by user")
        else:
            print(f"[{app_name}] Interrupted by user")
        if calm_dsl_dir and 'original_cwd' in locals():
            os.chdir(original_cwd)
        if results is not None:
            results[app_name] = (False, 1, "Interrupted by user")
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        if 'debug' in locals():
            debug(f"ERROR: {error_msg}")
        else:
            print(f"[{app_name}] ERROR: {error_msg}")
        if calm_dsl_dir and 'original_cwd' in locals():
            os.chdir(original_cwd)
        if results is not None:
            results[app_name] = (False, 1, error_msg)
    finally:
        # Always release semaphore to allow next thread to proceed
        # This ensures we don't deadlock even if an error occurs
        if semaphore:
            semaphore.release()


def generate_unique_app_name(base_name, index, batch_id, mode_short=None):
    """
    Generate a unique app name with a constant batch ID and mode identifier for easy filtering.
    
    Args:
        base_name (str): Base app name (e.g., "test2-demo2-gmanish-cred-without-i")
        index (int): Index number
        batch_id (str): Constant unique string shared by all apps in the batch
        mode_short (str, optional): Short mode identifier (e.g., "sch", "batch", "batch-slp")
    
    Returns:
        str: Unique app name string: {base_name}-{mode}-{batch_id}-{index} (if mode provided)
             or {base_name}-{batch_id}-{index} (if mode not provided, for backward compatibility)
    """
    if mode_short:
        return f"{base_name}-{mode_short}-{batch_id}-{index}"
    else:
        return f"{base_name}-{batch_id}-{index}"


def extract_app_index(app_name):
    """
    Extract trailing numeric index from generated app name.

    Expected patterns:
      - {base_name}-{batch_id}-{index}
      - {base_name}-{mode}-{batch_id}-{index}
    """
    match = re.search(r"-(\d+)$", app_name)
    return match.group(1) if match else "1"


def calculate_provisioning_time(app_statuses):
    """
    Calculate total provisioning time from app statuses.
    
    Args:
        app_statuses (dict): Dictionary mapping app_name -> {
            'creation_time': int (epoch microseconds),
            'last_update_time': int (epoch microseconds)
        }
    
    Returns:
        tuple: (min_creation_time (int or None), max_last_update_time (int or None), duration_seconds (float or None))
               Returns (None, None, None) if no valid timestamps found
    """
    if not app_statuses:
        return None, None, None
    
    creation_times = []
    last_update_times = []
    
    for app_name, status in app_statuses.items():
        creation_time = status.get('creation_time')
        last_update_time = status.get('last_update_time')
        
        if creation_time and last_update_time:
            try:
                creation_times.append(int(creation_time))
                last_update_times.append(int(last_update_time))
            except (ValueError, TypeError):
                continue
    
    if not creation_times or not last_update_times:
        return None, None, None
    
    min_creation = min(creation_times)
    max_last_update = max(last_update_times)
    
    # Calculate duration in seconds (timestamps are in microseconds)
    duration_seconds = (max_last_update - min_creation) / 1_000_000.0
    
    return min_creation, max_last_update, duration_seconds


def format_timestamp_ist(epoch_microseconds):
    """
    Convert epoch microseconds to IST formatted string.
    
    Args:
        epoch_microseconds (int): Epoch timestamp in microseconds
    
    Returns:
        str: Formatted timestamp string in IST timezone
    """
    try:
        if not PYTZ_AVAILABLE:
            # Fallback: just convert to UTC and add IST label (not accurate but better than nothing)
            epoch_seconds = epoch_microseconds / 1_000_000.0
            dt = datetime.fromtimestamp(epoch_seconds)
            return dt.strftime("%Y-%m-%d %H:%M:%S") + " IST (approx)"
        
        epoch_seconds = epoch_microseconds / 1_000_000.0
        dt_utc = datetime.fromtimestamp(epoch_seconds, tz=pytz.utc)
        ist = pytz.timezone('Asia/Kolkata')
        dt_ist = dt_utc.astimezone(ist)
        return dt_ist.strftime("%Y-%m-%d %H:%M:%S IST")
    except Exception:
        return "N/A"


def format_duration(seconds):
    """
    Format duration in seconds to readable format.
    
    Args:
        seconds (float or None): Duration in seconds
    
    Returns:
        str: Human-readable duration string (e.g., "1h 30m 45s")
    """
    if seconds is None or seconds < 0:
        return "0s"
    
    seconds = float(seconds)
    total_seconds = int(round(seconds))
    
    if total_seconds < 60:
        return f"{total_seconds}s"
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0:
        parts.append(f"{secs}s")
    
    return " ".join(parts) if parts else "0s"


def run_scheduling_mode(args, app_names, batch_id, calm_launch_log_dir=None, mode_tag="SCH"):
    """
    Runs scheduling mode - keeps a queue of apps being provisioned and submits
    new ones as slots free up.
    
    This is Mode 3 (Scheduling Mode). Here's what it does:
    1. Keeps track of apps that are being provisioned (up to parallel_users at a time)
    2. Checks the Nutanix API every 30 seconds to see app statuses
    3. When apps reach "running" or "error" state, frees up those slots
    4. Immediately submits new apps to fill the free slots
    5. If a submission fails, removes it from the queue right away so it doesn't block
    
    Data structures we use:
        - active_queue (dict): Apps currently being provisioned (these are using up slots)
        - complete_queue (dict): Apps that finished (either running or error state)
        - pending_apps (list): Apps we haven't submitted yet
    
    How we manage the queue:
        - When we start a thread, we add the app to active_queue right away
        - After the thread finishes, we check if it succeeded
        - If it failed: remove from active_queue immediately (frees the slot)
        - If it succeeded: keep it in active_queue (API polling will track it)
        - API polling sees when apps get to "running" or "error" state
        - Both of those states free up slots right away
    
    Args:
        args: Parsed command line arguments
        app_names (list): List of app names to launch
        batch_id (str): Batch ID for this run
        calm_launch_log_dir (str, optional): Where to save calm launch command logs
    
    Returns:
        tuple: (results_dict, app_statuses_dict)
            - results_dict (dict): Maps app_name to (success: bool, exit_code: int, error_message: str)
            - app_statuses_dict (dict): Maps app_name to {'uuid': str, 'state': str, ...}
    
    How it works:
        1. Submit initial batch (up to parallel_users apps)
        2. Wait for threads to finish (check if any failed)
        3. Wait 10 seconds for apps to show up in the API
        4. Main loop (every 30 seconds):
           a. Query API to get app statuses
           b. Check apps in active_queue, move to complete_queue if done
           c. Figure out how many free slots we have
           d. Submit new apps to fill those slots
           e. Wait for threads, check for failures, remove failed ones
           f. Keep going until all apps are done
    """
    print("=" * 80)
    print("MODE 3: SCHEDULING (ACTIVE QUEUE MANAGEMENT) - ENABLED")
    print("=" * 80)
    print(f"Concurrency (active queue size): {args.parallel_users}")
    print(f"Total apps to launch: {args.count}")
    print(f"Polling interval: 30 seconds")
    print(f"Host: {args.host}")
    print()
    print("Behavior:")
    print("  - Maintains active queue of apps being provisioned")
    print("  - Polls API every 30 seconds to check app status")
    print("  - When apps reach 'running' or 'error' state, slots are freed immediately")
    print("  - New apps are submitted immediately to fill free slots")
    print("  - Only 'provisioning' state keeps apps in active queue")
    print("=" * 80)
    print()
    
    results = {}
    active_queue = {}  # app_name -> {'submitted': bool, 'thread_completed': bool}
    complete_queue = {}  # app_name -> {'uuid': str, 'state': str, 'creation_time': int, 'last_update_time': int}
    pending_apps = list(app_names)  # Apps not yet submitted
    app_status_cache = {}  # Cache of app statuses from API
    pending_apps_lock = threading.Lock()  # Lock to protect pending_apps from race conditions
    
    start_time = time.time()
    
    # Submit initial batch up to concurrency limit
    print(f"[SCHEDULING] Submitting initial batch (up to {args.parallel_users} apps)...")
    with pending_apps_lock:
        initial_batch = min(args.parallel_users, len(pending_apps))
    initial_threads = []
    for i in range(initial_batch):
        with pending_apps_lock:
            if not pending_apps:
                break  # No more apps to submit
            app_name = pending_apps.pop(0)
        thread = threading.Thread(
            target=automate_calm_launch,
            args=(args.item, app_name, args.project, args.version, args.environment, args.calm_dsl_dir, results, None, calm_launch_log_dir, mode_tag)
        )
        thread.start()
        active_queue[app_name] = {'submitted': True, 'thread_completed': False}
        initial_threads.append((app_name, thread))
        print(f"[SCHEDULING] Started submission thread for: {app_name}")
    
    print(f"[SCHEDULING] Initial batch threads started. Active queue: {len(active_queue)} apps")
    print()
    
    # Wait for initial batch threads to finish (all prompts handled, jobs submitted)
    # After each thread finishes, we check the results to see if the submission failed.
    # If it failed, we remove it from active_queue right away to free up the slot.
    # This stops failed submissions from blocking slots forever.
    print("[SCHEDULING] Waiting for initial batch submission threads to complete...")
    print("[SCHEDULING] (This ensures all prompts are handled and jobs are fully submitted before polling)")
    for app_name, thread in initial_threads:
        thread.join()
        # Check if the submission worked - if it failed, remove it from active_queue
        # This fixes the slot leak problem: we catch failed submissions right away
        # and remove them from the queue so the slot is free for the next one.
        if app_name in results and len(results[app_name]) >= 1:
            success = results[app_name][0]
            if not success:
                # Submission failed - remove from active_queue immediately to free the slot
                # This prevents the slot from being blocked by a failed submission
                if app_name in active_queue:
                    del active_queue[app_name]
                    exit_code = results[app_name][1] if len(results[app_name]) > 1 else "unknown"
                    error_msg = results[app_name][2] if len(results[app_name]) > 2 else "unknown error"
                    print(f"[SCHEDULING] ✗ Submission FAILED for: {app_name} (exit code: {exit_code}) - removed from active queue")
                    print(f"[SCHEDULING]   Error: {error_msg}")
                    # Move to complete_queue with error state so it's tracked in final stats
                    complete_queue[app_name] = {'uuid': 'N/A', 'state': 'error', 'creation_time': None, 'last_update_time': None}
                continue
        
        # Submission succeeded - keep in active_queue (will be tracked by API polling)
        if app_name in active_queue:
            active_queue[app_name]['thread_completed'] = True
            print(f"[SCHEDULING] ✓ Submission completed for: {app_name} (prompts handled, job submitted)")
        else:
            print(f"[SCHEDULING] ⚠ Warning: {app_name} not in active_queue (may have been removed due to failure)")
    print("[SCHEDULING] All initial submissions completed. Starting API polling...")
    print()
    
    # Wait a bit before first poll to allow apps to appear in API
    print("[SCHEDULING] Waiting 10 seconds before first poll (to allow apps to appear in API)...")
    time.sleep(10)
    print()
    
    # Main polling loop - polls every 30 seconds
    # Flow:
    # 1. Poll API every 30 seconds to check app statuses
    # 2. If ANY apps (1 or all concurrent) moved to "running" or "error":
    #    - Immediately free those slots
    #    - Calculate available free slots
    #    - IMMEDIATELY fire that many calm launch commands
    #    - Wait for prompt sequences to complete (thread.join())
    #    - Polling does NOT interfere with prompt handling (we wait for completion)
    # 3. Continue polling until all apps reach terminal state
    poll_count = 0
    while len(complete_queue) < args.count:
        poll_count += 1
        print(f"[SCHEDULING] Poll #{poll_count} - Checking app statuses...")
        
        # Query API for all app names we're tracking
        all_tracked_apps = list(active_queue.keys()) + list(complete_queue.keys())
        if all_tracked_apps:
            app_statuses = query_app_status(args.host, args.username, args.password, all_tracked_apps, timeout=180, max_retries=1)
            if app_statuses:
                app_status_cache.update(app_statuses)
            else:
                # API query failed or timed out - log warning but continue with cached data
                print(f"[SCHEDULING] WARNING: API query failed/timed out, using cached data for {len(app_status_cache)} apps")
                # Use cached data if available
                app_statuses = {k: v for k, v in app_status_cache.items() if k in all_tracked_apps}
            
            # Check active queue apps and immediately free slots when apps reach terminal states
            apps_to_move = []
            slots_freed_count = 0
            
            for app_name in list(active_queue.keys()):
                if app_name in app_statuses:
                    status = app_statuses[app_name]
                    state = status.get('state', '').lower()
                    
                    # Move to complete queue if state is "running" OR "error"
                    # Both states free up slots IMMEDIATELY (running = success, error = failed, need to submit next app)
                    if state == 'running':
                        apps_to_move.append(app_name)
                        complete_queue[app_name] = status
                        uuid_short = status.get('uuid', 'N/A')
                        if len(uuid_short) > 8:
                            uuid_short = uuid_short[:8] + "..."
                        print(f"[SCHEDULING] ✓ {app_name} moved to RUNNING state (UUID: {uuid_short}) - slot freed immediately")
                        slots_freed_count += 1
                    elif state == 'error':
                        apps_to_move.append(app_name)
                        complete_queue[app_name] = status
                        uuid_short = status.get('uuid', 'N/A')
                        if len(uuid_short) > 8:
                            uuid_short = uuid_short[:8] + "..."
                        print(f"[SCHEDULING] ✗ {app_name} moved to ERROR state (UUID: {uuid_short}) - slot freed immediately")
                        slots_freed_count += 1
                    # Keep in active queue only if state is "provisioning" or similar provisioning states
                    # Other states like "running" or "error" free up slots
                else:
                    # App not found in API yet - still being submitted or not yet created
                    # Keep in active queue (assuming it's in provisioning state)
                    pass
            
            # IMMEDIATELY remove from active queue to free up slots
            for app_name in apps_to_move:
                del active_queue[app_name]
            
            # IMMEDIATELY calculate free slots and submit new apps (no delay)
            if slots_freed_count > 0:
                free_slots = args.parallel_users - len(active_queue)
                print(f"[SCHEDULING] {slots_freed_count} slot(s) freed. Free slots available: {free_slots}")
                
                if free_slots > 0:
                    # Thread-safe check and pop from pending_apps
                    with pending_apps_lock:
                        if not pending_apps:
                            apps_to_submit = 0
                        else:
                            apps_to_submit = min(free_slots, len(pending_apps))
                    
                    if apps_to_submit > 0:
                        print(f"[SCHEDULING] IMMEDIATELY submitting {apps_to_submit} new app(s) to fill free slots...")
                        
                        new_threads = []
                        for i in range(apps_to_submit):
                            with pending_apps_lock:
                                if not pending_apps:
                                    break  # No more apps to submit
                                app_name = pending_apps.pop(0)
                            thread = threading.Thread(
                                target=automate_calm_launch,
                                args=(args.item, app_name, args.project, args.version, args.environment, args.calm_dsl_dir, results, None, calm_launch_log_dir)
                            )
                            thread.start()
                            active_queue[app_name] = {'submitted': True, 'thread_completed': False}
                            new_threads.append((app_name, thread))
                            print(f"[SCHEDULING] → Started submission thread for: {app_name}")
                        
                        # Wait for the new threads to finish (all prompts handled, job submitted)
                        # After each thread finishes, we check if the submission failed.
                        # If it failed, we remove it from active_queue right away to free the slot.
                        # Same logic as the initial batch - stops slot leaks.
                        if new_threads:
                            print(f"[SCHEDULING] Waiting for {len(new_threads)} new submission(s) to complete...")
                            print(f"[SCHEDULING] (Ensuring all prompts are handled before next poll)")
                            for app_name, thread in new_threads:
                                thread.join()
                                # Check if the submission worked - if it failed, remove it from active_queue
                                # We check right after the thread finishes, so failed submissions don't
                                # sit there blocking slots while we wait for API polling to notice.
                                if app_name in results and len(results[app_name]) >= 1:
                                    success = results[app_name][0]
                                    if not success:
                                        # Submission failed - remove it from active_queue right away to free the slot
                                        # We don't wait for API polling to notice the failure.
                                        # The slot gets freed right away, so we can submit the next one in this same poll cycle.
                                        if app_name in active_queue:
                                            del active_queue[app_name]
                                            exit_code = results[app_name][1] if len(results[app_name]) > 1 else "unknown"
                                            error_msg = results[app_name][2] if len(results[app_name]) > 2 else "unknown error"
                                            print(f"[SCHEDULING] ✗ Submission FAILED for: {app_name} (exit code: {exit_code}) - removed from active queue")
                                            print(f"[SCHEDULING]   Error: {error_msg}")
                                            # Move to complete_queue with error state so we count it in the final stats
                                            complete_queue[app_name] = {'uuid': 'N/A', 'state': 'error', 'creation_time': None, 'last_update_time': None}
                                        continue
                                
                                # Submission succeeded - keep in active_queue (will be tracked by API polling)
                                if app_name in active_queue:
                                    active_queue[app_name]['thread_completed'] = True
                                    print(f"[SCHEDULING] ✓ Submission completed for: {app_name} (prompts handled, job submitted)")
                                else:
                                    print(f"[SCHEDULING] ⚠ Warning: {app_name} not in active_queue (may have been removed due to failure)")
                            print(f"[SCHEDULING] All new submissions completed. Apps should appear in API shortly.")
                elif free_slots > 0:
                    with pending_apps_lock:
                        if not pending_apps:
                            print(f"[SCHEDULING] {free_slots} free slot(s) available but no pending apps to submit")
                else:
                    with pending_apps_lock:
                        if pending_apps:
                            print(f"[SCHEDULING] No free slots available (active queue full: {len(active_queue)}/{args.parallel_users})")
            else:
                # No slots freed in this poll - check if we still have free slots from previous polls
                free_slots = args.parallel_users - len(active_queue)
                if free_slots > 0:
                    # Thread-safe check and pop from pending_apps
                    with pending_apps_lock:
                        if not pending_apps:
                            apps_to_submit = 0
                        else:
                            apps_to_submit = min(free_slots, len(pending_apps))
                    
                    if apps_to_submit > 0:
                        print(f"[SCHEDULING] {free_slots} free slot(s) available from previous polls, submitting {apps_to_submit} new app(s)...")
                        
                        new_threads = []
                        for i in range(apps_to_submit):
                            with pending_apps_lock:
                                if not pending_apps:
                                    break  # No more apps to submit
                                app_name = pending_apps.pop(0)
                            thread = threading.Thread(
                                target=automate_calm_launch,
                                args=(args.item, app_name, args.project, args.version, args.environment, args.calm_dsl_dir, results, None, calm_launch_log_dir)
                            )
                            thread.start()
                            active_queue[app_name] = {'submitted': True, 'thread_completed': False}
                            new_threads.append((app_name, thread))
                            print(f"[SCHEDULING] → Started submission thread for: {app_name}")
                        
                        # Wait for newly submitted threads to complete
                        if new_threads:
                            print(f"[SCHEDULING] Waiting for {len(new_threads)} new submission(s) to complete...")
                            for app_name, thread in new_threads:
                                thread.join()
                                # Check if submission was successful - remove from active_queue if it failed
                                if app_name in results and len(results[app_name]) >= 1:
                                    success = results[app_name][0]
                                    if not success:
                                        # Submission failed - remove from active_queue immediately to free the slot
                                        if app_name in active_queue:
                                            del active_queue[app_name]
                                            exit_code = results[app_name][1] if len(results[app_name]) > 1 else "unknown"
                                            error_msg = results[app_name][2] if len(results[app_name]) > 2 else "unknown error"
                                            print(f"[SCHEDULING] ✗ Submission FAILED for: {app_name} (exit code: {exit_code}) - removed from active queue")
                                            print(f"[SCHEDULING]   Error: {error_msg}")
                                            # Move to complete_queue with error state
                                            complete_queue[app_name] = {'uuid': 'N/A', 'state': 'error', 'creation_time': None, 'last_update_time': None}
                                        continue
                                
                                # Submission succeeded - keep in active_queue
                                if app_name in active_queue:
                                    active_queue[app_name]['thread_completed'] = True
                                    print(f"[SCHEDULING] ✓ Submission completed for: {app_name} (prompts handled, job submitted)")
                                else:
                                    print(f"[SCHEDULING] ⚠ Warning: {app_name} not in active_queue (may have been removed due to failure)")
                            print(f"[SCHEDULING] All new submissions completed.")
        
        # Print status
        with pending_apps_lock:
            pending_count = len(pending_apps)
        print(f"[SCHEDULING] Status - Active: {len(active_queue)}, Complete: {len(complete_queue)}, Pending: {pending_count}")
        
        # Check if we're done (all apps submitted and all reached terminal state: running or error)
        if len(complete_queue) >= args.count:
            running_count = sum(1 for app_name in complete_queue.keys() 
                             if app_name in app_status_cache and 
                             app_status_cache[app_name].get('state', '').lower() == 'running')
            error_count = sum(1 for app_name in complete_queue.keys() 
                            if app_name in app_status_cache and 
                            app_status_cache[app_name].get('state', '').lower() == 'error')
            print(f"[SCHEDULING] All {args.count} apps have reached terminal state!")
            print(f"[SCHEDULING]   - Running: {running_count}")
            print(f"[SCHEDULING]   - Error: {error_count}")
            break
        
        # Also check if we've submitted all apps but some are still in active queue
        # (waiting for them to reach running state)
        with pending_apps_lock:
            pending_count = len(pending_apps)
        if pending_count == 0 and len(active_queue) == 0:
            # All submitted but none in active queue - this shouldn't happen, but handle it
            print(f"[SCHEDULING] All apps submitted, but only {len(complete_queue)}/{args.count} reached RUNNING state")
            # Continue polling to see if remaining apps appear
        
        # Wait 30 seconds before next poll (polling interval)
        # Note: This ensures we check every 30 seconds if any apps moved to running/error
        # When apps move to terminal states, we immediately submit new apps and wait for
        # their prompt sequences to complete. The 30-second wait happens AFTER all submissions
        # are complete, so polling never interferes with prompt handling.
        if len(complete_queue) < args.count:
            print(f"[SCHEDULING] Waiting 30 seconds before next poll...")
            time.sleep(30)
        print()
    
    # All threads should have completed by now (we wait for them after each submission)
    # But check if any are still in active_queue (shouldn't happen, but handle gracefully)
    incomplete_apps = [app_name for app_name, entry in active_queue.items() if not entry.get('thread_completed', False)]
    if incomplete_apps:
        print(f"[SCHEDULING] Warning: {len(incomplete_apps)} apps still in active queue but threads should be complete.")
        print(f"[SCHEDULING] This may indicate apps that were submitted but never appeared in API.")
    else:
        print("[SCHEDULING] All submission threads completed successfully.")
    
    elapsed_time = time.time() - start_time
    
    # Calculate provisioning time from app statuses
    all_app_statuses = {}
    for app_name in app_names:
        if app_name in app_status_cache:
            all_app_statuses[app_name] = app_status_cache[app_name]
        elif app_name in complete_queue:
            all_app_statuses[app_name] = complete_queue[app_name]
    
    min_creation, max_last_update, duration_seconds = calculate_provisioning_time(all_app_statuses)
    
    # Calculate final statistics
    running_apps = []
    error_apps = []
    other_state_apps = []
    unknown_state_apps = []
    
    for app_name in app_names:
        if app_name in all_app_statuses:
            status = all_app_statuses[app_name]
            state = status.get('state', '').lower()
            if state == 'running':
                running_apps.append(app_name)
            elif state == 'error':
                error_apps.append(app_name)
            elif state:
                other_state_apps.append((app_name, state))
            else:
                unknown_state_apps.append(app_name)
        else:
            unknown_state_apps.append(app_name)
    
    print()
    print("=" * 80)
    print("SCHEDULING MODE - FINAL SUMMARY")
    print("=" * 80)
    print(f"Total apps to launch: {args.count}")
    print(f"Total elapsed time: {elapsed_time:.1f} seconds")
    print()
    print("APP STATE SUMMARY:")
    print("-" * 80)
    print(f"✓ Apps moved to RUNNING state: {len(running_apps)}")
    print(f"✗ Apps moved to ERROR state:   {len(error_apps)}")
    if other_state_apps:
        print(f"⚠ Apps in other states:        {len(other_state_apps)}")
        for app_name, state in other_state_apps[:5]:  # Show first 5
            print(f"     - {app_name}: {state}")
        if len(other_state_apps) > 5:
            print(f"     ... and {len(other_state_apps) - 5} more")
    if unknown_state_apps:
        print(f"? Apps with unknown state:     {len(unknown_state_apps)}")
        for app_name in unknown_state_apps[:5]:  # Show first 5
            print(f"     - {app_name}")
        if len(unknown_state_apps) > 5:
            print(f"     ... and {len(unknown_state_apps) - 5} more")
    print("-" * 80)
    print(f"Total completed (running + error): {len(running_apps) + len(error_apps)}/{args.count}")
    print()
    
    # Show provisioning time if available
    if min_creation and max_last_update and duration_seconds:
        creation_time_str = format_timestamp_ist(min_creation)
        last_update_str = format_timestamp_ist(max_last_update)
        duration_str = format_duration(duration_seconds)
        print("PROVISIONING TIME ANALYSIS:")
        print("-" * 80)
        print(f"Earliest creation time (IST): {creation_time_str}")
        print(f"Latest update time (IST):     {last_update_str}")
        print(f"Total provisioning time:      {duration_str} ({duration_seconds:.1f} seconds)")
        print("-" * 80)
        print()
    
    # Show detailed breakdown if there are errors
    if error_apps:
        print("APPS THAT REACHED ERROR STATE:")
        print("-" * 80)
        for app_name in error_apps[:10]:  # Show first 10
            if app_name in all_app_statuses:
                status = all_app_statuses[app_name]
                uuid_short = status.get('uuid', 'N/A')
                if len(uuid_short) > 8:
                    uuid_short = uuid_short[:8] + "..."
                print(f"  ✗ {app_name} (UUID: {uuid_short})")
            else:
                print(f"  ✗ {app_name}")
        if len(error_apps) > 10:
            print(f"  ... and {len(error_apps) - 10} more error apps")
        print("-" * 80)
        print()
    
    print("=" * 80)
    print()
    
    return results, all_app_statuses


def main():
    parser = argparse.ArgumentParser(
        description='Launch multiple Calm marketplace items in parallel with auto-ENTER responses',
        formatter_class=ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument('--count', type=int, default=10,
                       help='Number of parallel apps to launch')
    parser.add_argument('--item',
                       help='Marketplace item name (e.g., Foundation-Lite). REQUIRED: This argument must be provided.')
    parser.add_argument('--base_app_name',
                       help='Base application name (will be appended with index and unique suffix). REQUIRED: This argument must be provided.')
    parser.add_argument('--project',
                       help='Project name. REQUIRED: This argument must be provided.')
    parser.add_argument('--version',
                       help='Version (e.g., 4.0.0). REQUIRED: This argument must be provided.')
    parser.add_argument('--environment',
                       help='Environment name (optional)')
    parser.add_argument('--calm_dsl_dir',
                       default=os.environ.get('CALM_DSL_DIR', None),
                       help='Path to calm-dsl directory (default: from CALM_DSL_DIR env var, or auto-detect from current directory). '
                            'If venv exists in this directory, it will be used automatically.')
    parser.add_argument('--parallel_users', type=int, default=50,
                       help='Number of parallel users/launches (default: 50). '
                            'Mode 1 & 2: Controls batch size (apps launched simultaneously per batch). '
                            'Mode 3: Controls active queue size (concurrency limit for apps being provisioned). '
                            'Use this to limit resource usage for large-scale launches (e.g., 1000+ apps).')
    parser.add_argument('--batch_delay', type=float, default=0.0,
                       help='Delay in seconds between batches (default: 0). '
                            'Mode 1: Set to 0 (default) - batches submitted back-to-back without sleep. '
                            'Mode 2: Set > 0 - wait N seconds between batches. '
                            'Mode 3: Not used (scheduling mode uses API polling instead). '
                            'Example: --batch_delay 5 waits 5 seconds between batches.')
    parser.add_argument('--scheduling', action='store_true',
                       help='Enable Mode 3 (Scheduling Mode). '
                            'In this mode, parallel_users becomes the active queue size (concurrency limit). '
                            'Maintains an active queue of apps being provisioned and only submits new launches '
                            'when slots are available (apps reach "running" state). '
                            'Polls API every 30 seconds to check app status. '
                            'Requires --host, --username, --password. '
                            'Modes: 1=No sleep (batch_delay=0), 2=With sleep (batch_delay>0), 3=Scheduling (--scheduling)')
    parser.add_argument('--host',
                       help='Host URL for API polling (e.g., nconprem-10-122-152-117.ccpnx.com). Required for scheduling mode.')
    parser.add_argument('--username', default='ssp_admin@qa.nutanix.com',
                       help='Username for API Basic Auth (default: ssp_admin@qa.nutanix.com). Required for scheduling mode.')
    parser.add_argument('--password', default='nutanix/4u',
                       help='Password for API Basic Auth (default: nutanix/4u). Required for scheduling mode.')
    parser.add_argument('--log_file',
                       help='Path to log file for console output (optional). '
                            'If not specified, auto-creates parallel_calm_launch_YYYYMMDD-HHMMSS-{uuid}.log in current directory. '
                            'All console output (stdout/stderr) will be duplicated to this file. '
                            'Calm launch command logs (prompt interactions) will be saved in calm-launch-logs/ subdirectory. '
                            'If --log_file specified, calm-launch-logs/ will be created next to your log file. '
                            'If not specified, calm-launch-logs/ will be created in current directory.')
    
    args = parser.parse_args()
    
    # Check if required arguments are provided, show help if not
    missing_args = []
    if not args.item:
        missing_args.append('--item')
    if not args.base_app_name:
        missing_args.append('--base_app_name')
    if not args.project:
        missing_args.append('--project')
    if not args.version:
        missing_args.append('--version')
    
    if missing_args:
        parser.print_help()
        print()
        print(f"ERROR: Required argument(s) missing: {', '.join(missing_args)}")
        print("Example: python3 parallel_calm_launch.py --item Foundation-Lite --base_app_name test --project projectbk --version 1.0.0 --count 10")
        sys.exit(1)
    
    if args.count < 1:
        print("Error: --count must be at least 1")
        sys.exit(1)
    
    # Validate scheduling mode requirements
    if args.scheduling:
        if not args.host:
            print("Error: --host is required when --scheduling is enabled")
            sys.exit(1)
    
    # Validate calm-dsl directory
    if args.calm_dsl_dir and not os.path.exists(args.calm_dsl_dir):
        print(f"Error: Calm-DSL directory not found: {args.calm_dsl_dir}")
        sys.exit(1)
    
    # Check for venv
    venv_status = "Not found"
    if args.calm_dsl_dir:
        venv_path = os.path.join(args.calm_dsl_dir, "venv")
        if os.path.exists(venv_path):
            venv_python = os.path.join(venv_path, "bin", "python")
            if os.path.exists(venv_python) or os.path.exists(os.path.join(venv_path, "Scripts", "python.exe")):
                venv_status = "Found (will be used)"
            else:
                venv_status = "Found but incomplete"
    
    # Determine execution mode
    if args.scheduling:
        mode = "Mode 3: Scheduling (Active Queue Management)"
        mode_desc = f"Concurrency={args.parallel_users}, Polls API every 30s"
        mode_key = "SCHEDULING"
        mode_short = "sch"  # Short identifier for app names and log files
    elif args.batch_delay > 0:
        mode = "Mode 2: Batch with Sleep"
        mode_desc = f"Batch size={args.parallel_users}, Sleep={args.batch_delay}s between batches"
        mode_key = "BATCH_WITH_SLEEP"
        mode_short = "batch-slp"  # Short identifier for app names and log files
    else:
        mode = "Mode 1: Batch without Sleep"
        mode_desc = f"Batch size={args.parallel_users}, No sleep between batches"
        mode_key = "BATCH_NO_SLEEP"
        mode_short = "batch"  # Short identifier for app names and log files
    
    # Print prominent mode banner at the very start
    print()
    print("=" * 80)
    print(" " * 20 + "EXECUTION MODE SELECTED" + " " * 20)
    print("=" * 80)
    print(f"  >>> {mode} <<<")
    print(f"  {mode_desc}")
    print("=" * 80)
    print()
    
    # Generate a constant batch ID for easy filtering/searching
    # Format: timestamp + short UUID (e.g., "20251124081234-a1b2c3d4")
    batch_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + str(uuid.uuid4())[:8]
    
    # Setup console log file (main script output)
    # If user specified --log_file, use that. Otherwise, create unique filename in current directory.
    if args.log_file:
        # User specified a log file path - use it
        log_file_path = args.log_file
    else:
        # No log file specified - create unique filename in current working directory
        # Format: parallel_calm_launch_{mode_short}_YYYYMMDD-HHMMSS-{short_uuid}.log
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]
        log_file_path = f"parallel_calm_launch_{mode_short}_{timestamp}-{short_uuid}.log"
    
    # Setup file logging - redirects all stdout/stderr to both console and file
    if setup_file_logging(log_file_path):
        # This print will go to both console and file (since stdout is redirected)
        print(f"[INFO] All console output is being logged to: {os.path.abspath(log_file_path)}")
        print()
    
    # Setup calm launch log directory (for prompt/command output logs)
    # These are separate log files for each calm launch command
    if args.log_file:
        # User specified log_file - derive directory from that path
        # Create calm-launch-logs subdirectory in the same directory as the log file
        log_dir = os.path.dirname(os.path.abspath(args.log_file))
        if not log_dir:
            # If log_file is just a filename (no path), use current directory
            log_dir = os.getcwd()
        calm_launch_log_dir = os.path.join(log_dir, "calm-launch-logs")
    else:
        # No log_file specified - create calm-launch-logs directory in current working directory
        calm_launch_log_dir = os.path.join(os.getcwd(), "calm-launch-logs")
    
    # Generate unique app names with the same batch ID and mode identifier
    app_names = [
        generate_unique_app_name(args.base_app_name, i+1, batch_id, mode_short)
        for i in range(args.count)
    ]
    
    print("=" * 80)
    print("PARALLEL CALM LAUNCH CONFIGURATION")
    print("=" * 80)
    print(f"Execution Mode: {mode}")
    print(f"  {mode_desc}")
    print()
    print(f"Number of apps: {args.count}")
    print(f"Marketplace item: {args.item}")
    print(f"Base app name: {args.base_app_name}")
    print(f"Project: {args.project}")
    print(f"Version: {args.version}")
    if args.environment:
        print(f"Environment: {args.environment}")
    print(f"Calm-DSL directory: {args.calm_dsl_dir}")
    print(f"Virtual environment: {venv_status}")
    print(f"Parallel users/concurrency: {args.parallel_users}")
    if not args.scheduling:
        print(f"Sleep between batches: {args.batch_delay}s")
    print(f"Batch ID (for filtering): {batch_id}")
    if args.scheduling:
        print(f"Host: {args.host}")
    print()
    print("Generated app names:")
    for i, app_name in enumerate(app_names, 1):
        print(f"  {i}. {app_name}")
    print()
    print("Sample command format:")
    sample_cmd = f"calm -v launch marketplace item {args.item} --app_name {app_names[0]} --project {args.project} --version {args.version}"
    if args.environment:
        sample_cmd += f" --environment {args.environment}"
    print(f"  {sample_cmd}")
    print("=" * 80)
    print()
    
    # Choose mode: scheduling or regular batch mode
    if args.scheduling:
        # Mode 3: Scheduling mode - maintain active queue and poll API
        print("=" * 80)
        print("STARTING MODE 3: SCHEDULING (ACTIVE QUEUE MANAGEMENT)")
        print("=" * 80)
        print()
        results, app_statuses = run_scheduling_mode(args, app_names, batch_id, calm_launch_log_dir, mode_tag="SCH")
        elapsed_time = 0  # Elapsed time is calculated inside run_scheduling_mode
    else:
        # Mode 1 or 2: Regular batch mode - process parallel_users at a time, wait for batch to complete, then next batch
        if args.batch_delay > 0:
            print("=" * 80)
            print("STARTING MODE 2: BATCH WITH SLEEP")
            print("=" * 80)
            print()
        else:
            print("=" * 80)
            print("STARTING MODE 1: BATCH WITHOUT SLEEP")
            print("=" * 80)
            print()
        
        if args.count > args.parallel_users:
            num_batches = (args.count + args.parallel_users - 1) // args.parallel_users  # Ceiling division
            print(f"Note: {args.count} apps will be launched in {num_batches} batches of up to {args.parallel_users} parallel users")
            if args.batch_delay > 0:
                print(f"      Sleep {args.batch_delay}s between batches")
        else:
            print(f"Note: All {args.count} apps will launch in parallel (count < parallel_users, single batch)")
        print()
        
        results = {}
        start_time = time.time()
        
        # Determine mode tag for batch mode
        batch_mode_tag = "BATCH-SLP" if args.batch_delay > 0 else "BATCH"
        
        # Process apps in batches - all users in a batch submit commands simultaneously
        for batch_start in range(0, len(app_names), args.parallel_users):
            batch_end = min(batch_start + args.parallel_users, len(app_names))
            batch = app_names[batch_start:batch_end]
            batch_num = (batch_start // args.parallel_users) + 1
            
            if args.count > args.parallel_users:
                print(f"[MAIN] Starting batch {batch_num}: {len(batch)} apps (apps {batch_start+1}-{batch_end} of {len(app_names)})")
            else:
                print(f"[MAIN] Starting {len(batch)} apps in parallel")
            
            # Start all threads in this batch
            threads = []
            for app_name in batch:
                thread = threading.Thread(
                    target=automate_calm_launch,
                    args=(args.item, app_name, args.project, args.version, args.environment, args.calm_dsl_dir, results, None, calm_launch_log_dir, batch_mode_tag)
                )
                thread.start()
                threads.append(thread)
                print(f"[MAIN] Started thread for: {app_name}")
            
            # Wait for all threads in this batch to complete
            print(f"[MAIN] Waiting for batch {batch_num} to complete...")
            for i, thread in enumerate(threads, 1):
                thread.join()
                print(f"[MAIN] Batch {batch_num} - Thread {i}/{len(threads)} completed")
            
            print(f"[MAIN] Batch {batch_num} completed")
            
            # Sleep before starting next batch (if not the last batch)
            if batch_end < len(app_names) and args.batch_delay > 0:
                print(f"[MAIN] Sleeping {args.batch_delay}s before next batch...")
                time.sleep(args.batch_delay)
            print()
        
        elapsed_time = time.time() - start_time
        
        # For regular mode, try to get app statuses if host is provided (optional)
        app_statuses = {}
        if args.host:
            print()
            print("[MAIN] Fetching app statuses for timing calculation...")
            app_statuses = query_app_status(args.host, args.username, args.password, app_names)
            print(f"[MAIN] Retrieved statuses for {len(app_statuses)} apps")
            print()
    
    # Print results
    print()
    print("=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)
    
    # Handle both old format (success, exit_code) and new format (success, exit_code, error_message)
    successful = 0
    failed = 0
    failed_with_errors = []
    
    for app_name, result in sorted(results.items()):
        if len(result) == 3:
            success, exit_code, error_message = result
        else:
            # Backward compatibility with old format
            success, exit_code = result
            error_message = None
        
        if success:
            successful += 1
            status = "✓ SUCCESS"
            error_info = ""
        else:
            failed += 1
            status = "✗ FAILED"
            if error_message:
                error_info = f" | Error: {error_message[:100]}"  # Limit error message length
                failed_with_errors.append((app_name, error_message))
            else:
                error_info = ""
        
        print(f"{status:12} | Exit: {str(exit_code):3} | {app_name}{error_info}")
    
    print("=" * 80)
    print(f"Summary: {successful} successful, {failed} failed")
    
    # Show detailed error messages for failed launches
    if failed_with_errors:
        print()
        print("FAILED LAUNCHES WITH ERROR DETAILS:")
        print("-" * 80)
        for app_name, error_msg in failed_with_errors:
            print(f"  {app_name}:")
            print(f"    {error_msg}")
        print("-" * 80)
    
    print(f"Total script execution time: {elapsed_time:.1f} seconds")
    print("=" * 80)
    
    # Calculate and display provisioning time if we have app statuses
    if app_statuses:
        print()
        print("=" * 80)
        print("PROVISIONING TIME ANALYSIS")
        print("=" * 80)
        min_creation, max_last_update, duration_seconds = calculate_provisioning_time(app_statuses)
        
        if min_creation and max_last_update and duration_seconds:
            creation_time_str = format_timestamp_ist(min_creation)
            last_update_str = format_timestamp_ist(max_last_update)
            duration_str = format_duration(duration_seconds)
            
            print(f"Earliest creation time (IST): {creation_time_str}")
            print(f"Latest update time (IST): {last_update_str}")
            print(f"Total provisioning time for all {args.count} apps: {duration_str} ({duration_seconds:.1f} seconds)")
            print()
            print(f"This represents the time from the first app creation to the last app update.")
        else:
            print("Could not calculate provisioning time (missing timestamp data)")
        print("=" * 80)
    elif args.host and not args.scheduling:
        print()
        print("NOTE: To see provisioning time analysis, ensure --host is provided and API is accessible.")
    
    if failed > 0:
        print()
        print("NOTE: Check debug output above for details on failed launches.")
        if failed_with_errors:
            print(f"NOTE: {len(failed_with_errors)} failed launches have specific error messages listed above.")
    
    # Restore stdout/stderr and close log file
    global _log_file
    log_file_path_used = None
    if args.log_file:
        log_file_path_used = args.log_file
    elif _log_file:
        try:
            log_file_path_used = _log_file.name
        except:
            pass
    
    if _log_file:
        try:
            # Restore original stdout/stderr
            if isinstance(sys.stdout, TeeOutput):
                sys.stdout = sys.stdout.stdout
            if isinstance(sys.stderr, TeeOutput):
                sys.stderr = sys.stderr.stderr
            
            _log_file.close()
            if log_file_path_used:
                print()
                print("=" * 80)
                print(f"All output has been logged to: {os.path.abspath(log_file_path_used)}")
                print("=" * 80)
        except:
            pass
    
    sys.exit(1 if failed > 0 else 0)


if __name__ == '__main__':
    main()


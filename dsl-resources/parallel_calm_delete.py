#!/usr/bin/env python3
"""
Parallel Calm App Deletion Script

This script fetches all Calm apps, filters them by a regex pattern, and deletes
matching apps in parallel using three execution modes.

What it does:
    - Fetches apps using 'calm get apps' command (supports JSON and table formats)
    - Filters apps by string pattern (converted to regex internally)
    - Deletes apps in parallel using threads
    - Handles >250 apps by iteratively fetching and deleting until exhausted
    - Automatically skips apps already in "deleting" state (already being deleted)
    - Includes ALL other states for deletion (error, running, provisioning, unknown, etc.)
    - Verifies deletions by checking if app still exists
    - Retries failed deletions with exponential backoff
    - Three different execution modes depending on what you need
    - Comprehensive logging to both console and file
    - Virtual environment auto-detection
    - Shows comprehensive help when run without required arguments

EXECUTION MODES:

    ┌─────────────────────────────────────────────────────────────────────────┐
    │ MODE 1: Active Queue Management (--mode queue, DEFAULT)                │
    │ ─────────────────────────────────────────────────────────────────────── │
    │                                                                         │
    │ Execution Flow:                                                        │
    │                                                                         │
    │   STEP 1: Initial Submission                                           │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Submit up to parallel_users deletion commands immediately │     │
    │   │ - Move apps from pending_apps → active_queue               │     │
    │   │ - Start threads for each deletion command                   │     │
    │   │ - Example: Submit apps 1-10 (if parallel_users=10)          │     │
    │   │   active_queue = 10, pending = 90, complete = 0             │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 2: Wait for Commands to be Submitted (5 seconds)                │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Wait for all initial deletion command threads to complete│     │
    │   │ - This ensures all deletion commands are submitted          │     │
    │   │ - Allows system to start processing deletions              │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 3: Main Polling Loop (every poll_interval seconds)              │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ 3a. Check Active Queue Apps                                   │     │
    │   │     FOR each app in active_queue:                            │     │
    │   │       - Use 'calm get apps -n <app_name>' to check status   │     │
    │   │       IF "No application found" in output:                   │     │
    │   │         → App deleted successfully                           │     │
    │   │         → Move app to complete_queue                         │     │
    │   │         → Free slot immediately                               │     │
    │   │         → Log: "✓ app_name deleted - slot freed"            │     │
    │   │       ELSE (app found in any state):                         │     │
    │   │         → Keep in active_queue (still deleting)              │     │
    │   │         → Log: "⏳ app_name still deleting"                  │     │
    │   │                                                              │     │
    │   │ 3b. Calculate Free Slots                                      │     │
    │   │     free_slots = parallel_users - len(active_queue)          │     │
    │   │                                                              │     │
    │   │ 3c. Submit New Deletions (fill free slots immediately)        │     │
    │   │     IF free_slots > 0 AND pending_apps not empty:            │     │
    │   │       apps_to_submit = min(free_slots, len(pending_apps))  │     │
    │   │       FOR each app to submit:                                │     │
    │   │         → Start deletion thread                              │     │
    │   │         → Move from pending_apps → active_queue            │     │
    │   │         → Wait for deletion command to be submitted           │     │
    │   │     This keeps active queue full (up to concurrency limit)   │     │
    │   │     As soon as ANY slot is freed, it's immediately filled    │     │
    │   │                                                              │     │
    │   │ 3d. Print Status                                              │     │
    │   │     "Active: X, Complete: Y, Pending: Z"                    │     │
    │   │                                                              │     │
    │   │ 3e. Check Completion                                          │     │
    │   │     IF len(complete_queue) >= total_count:                  │     │
    │   │       → Break loop (all apps deleted)                        │     │
    │   │                                                              │     │
    │   │ 3f. Wait poll_interval seconds before next poll              │     │
    │   │     (default: 15 seconds)                                    │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 4: Handle >250 Apps (Iterative Fetching)                        │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - After current batch completes, re-fetch apps              │     │
    │   │ - If more matching apps found, repeat deletion process      │     │
    │   │ - Continues until no matching apps found                    │     │
    │   │ - Final verification: Re-fetch to confirm all deleted       │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                                                                         │
    │ Timeline Example (300 apps, parallel_users=10, poll_interval=15):      │
    │   Iteration 1:                                                         │
    │     Time 0s:   Submit apps 1-10 → active=10, pending=240, complete=0  │
    │     Time 5s:   Wait for commands to be submitted                       │
    │     Time 20s:  Poll #1 - Apps 1-3: deleted → complete=3, active=7   │
    │                Submit apps 11-13 → active=10, pending=237              │
    │     Time 35s:  Poll #2 - Apps 4-6: deleted → complete=6, active=7     │
    │                Submit apps 14-16 → active=10, pending=234              │
    │     ... continues until 250 apps deleted                               │
    │   Iteration 2:                                                         │
    │     Re-fetch apps → 50 more matching apps found                       │
    │     Repeat deletion process for remaining 50 apps                     │
    │   Iteration 3:                                                         │
    │     Re-fetch apps → 0 matching apps found → Exit                      │
    │                                                                         │
    │ Key Features:                                                          │
    │   - Dynamic slot management: Fills free slots immediately              │
    │   - Polling-based: Checks deletion status every poll_interval seconds │
    │   - Handles >250 apps: Re-fetches and re-deletes until exhausted       │
    │   - Filters "deleting" state: Excludes apps already being deleted     │
    │   - Includes ALL other states: error, running, provisioning, etc.     │
    │   - Optimal throughput: Keeps active queue full                        │
    │                                                                         │
    │ Use Case: Optimal throughput with dynamic slot management              │
    │ Example: --app-name-pattern "test" --mode queue --parallel_users 10    │
    │          (DEFAULT MODE: Used when --mode is not specified)              │
    └─────────────────────────────────────────────────────────────────────────┘
    
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ MODE 2: Batch without Sleep (--mode batch)                             │
    │ ─────────────────────────────────────────────────────────────────────── │
    │                                                                         │
    │ Execution Flow:                                                        │
    │                                                                         │
    │   STEP 1: Submit Batch 1                                              │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Submit parallel_users deletion commands simultaneously   │     │
    │   │ - Start threads for all apps in batch                       │     │
    │   │ - Example: Submit apps 1-10 (if parallel_users=10)          │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 2: Wait for Batch 1 to Complete                                │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Wait for all threads in batch to finish                   │     │
    │   │ - Thread.join() for each app                                │     │
    │   │ - Verify deletions (if --no_verify not set)                  │     │
    │   │ - No delay after completion                                 │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 3: Submit Batch 2 (immediately)                                 │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Submit next parallel_users deletions                      │     │
    │   │ - Start threads immediately (no sleep)                      │     │
    │   │ - Example: Submit apps 11-20                                 │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 4: Repeat until all apps deleted                               │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Continue batches 3, 4, 5... until all deleted            │     │
    │   │ - Each batch waits for previous batch to complete           │     │
    │   │ - No sleep between batches                                  │     │
    │   │ - Handles >250 apps by re-fetching and re-deleting          │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                                                                         │
    │ Timeline Example (100 apps, parallel_users=10):                         │
    │   Time 0s:   Submit batch 1 (apps 1-10)                                 │
    │   Time 30s:  Batch 1 complete → Submit batch 2 (apps 11-20)            │
    │   Time 60s:  Batch 2 complete → Submit batch 3 (apps 21-30)          │
    │   ... continues until all 100 apps deleted                             │
    │                                                                         │
    │ Use Case: Fast deletion when you don't need delays                      │
    │ Example: --app-name-pattern "test" --mode batch --parallel_users 10   │
    └─────────────────────────────────────────────────────────────────────────┘
    
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ MODE 3: Batch with Sleep (--mode batch_sleep)                           │
    │ ─────────────────────────────────────────────────────────────────────── │
    │                                                                         │
    │ Execution Flow:                                                        │
    │                                                                         │
    │   STEP 1: Submit Batch 1                                              │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Submit parallel_users deletion commands simultaneously   │     │
    │   │ - Start threads for all apps in batch                       │     │
    │   │ - Example: Submit apps 1-10 (if parallel_users=10)          │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 2: Wait for Batch 1 to Complete                                │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Wait for all threads in batch to finish                   │     │
    │   │ - Thread.join() for each app                                │     │
    │   │ - Verify deletions (if --no_verify not set)                  │     │
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
    │   │ - Submit next parallel_users deletions                      │     │
    │   │ - Start threads for batch 2                                  │     │
    │   │ - Example: Submit apps 11-20                                 │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                        ↓                                               │
    │   STEP 5: Repeat until all apps deleted                               │
    │   ┌─────────────────────────────────────────────────────────────┐     │
    │   │ - Continue batches 3, 4, 5... until all deleted            │     │
    │   │ - Each batch: wait → sleep → submit next                    │     │
    │   │ - Handles >250 apps by re-fetching and re-deleting          │     │
    │   └─────────────────────────────────────────────────────────────┘     │
    │                                                                         │
    │ Timeline Example (100 apps, parallel_users=10, batch_delay=5):        │
    │   Time 0s:   Submit batch 1 (apps 1-10)                                 │
    │   Time 30s:  Batch 1 complete → Sleep 5s                              │
    │   Time 35s:  Submit batch 2 (apps 11-20)                               │
    │   Time 65s:  Batch 2 complete → Sleep 5s                              │
    │   Time 70s:  Submit batch 3 (apps 21-30)                               │
    │   ... continues with 5s sleep between each batch                       │
    │                                                                         │
    │ Use Case: Rate limiting to avoid overwhelming the system                │
    │ Example: --app-name-pattern "old-apps" --mode batch_sleep --batch_delay 5│
    └─────────────────────────────────────────────────────────────────────────┘

USAGE EXAMPLES:

    Basic usage (queue mode, default):
    python3 parallel_calm_delete.py --app-name-pattern "automation-gmanish" --project projectbk
        # Uses: queue mode, concurrency=10, poll_interval=15, skip_missing=enabled

    Minimal usage (all defaults):
        python3 parallel_calm_delete.py --app-name-pattern "demo"
        # Uses: queue mode, concurrency=10, poll_interval=15, skip_missing=enabled

    Queue mode with custom concurrency:
        python3 parallel_calm_delete.py --app-name-pattern "test" --mode queue --parallel_users 20 --poll_interval 10

    Batch mode (explicit):
        python3 parallel_calm_delete.py --app-name-pattern "test" --mode batch --parallel_users 10

    Batch with sleep:
        python3 parallel_calm_delete.py --app-name-pattern "old-apps" --mode batch_sleep --batch_delay 3

    Dry run (preview what would be deleted):
        python3 parallel_calm_delete.py --app-name-pattern "test" --dry_run

    Disable skip already-deleted apps:
        python3 parallel_calm_delete.py --app-name-pattern "test" --no_skip_missing

    Show help (when no arguments provided):
        python3 parallel_calm_delete.py

How it works - Deletion Process:
    The script uses a multi-step process to safely and efficiently delete apps:
    
    1. Fetching Apps:
       - Uses 'calm get apps' command to fetch all apps
       - Supports both JSON and table output formats (auto-detects)
       - Respects Calm API limit of 250 apps per query
       - Returns dictionary mapping app_name -> state
       - Location: fetch_apps() function (line ~418)
    
    2. Filtering Apps:
       - Converts string pattern to regex (matches if string appears anywhere in app name)
       - Excludes apps in "deleting" state (already being deleted, will complete automatically)
       - Includes ALL other states: error, running, provisioning, unknown, etc.
       - Why: Apps in "deleting" state are already being deleted, sending another delete
             command is unnecessary and may cause errors
       - Location: filter_apps_by_pattern() function (line ~650)
    
    3. Iterative Fetching for >250 Apps:
       - Calm API has a hard limit of 250 apps per query
       - Script handles this by repeatedly fetching and deleting until no matching apps remain
       - Process:
         a. Fetch up to 250 apps matching pattern
         b. Delete all matching apps (using selected mode)
         c. Re-fetch apps to check if more matching apps exist
         d. If more found, repeat deletion process
         e. Continue until no matching apps found
         f. Final verification: Re-fetch one more time to confirm all deleted
       - Why: Ensures all apps are deleted even if there are 1000+ matching apps
       - Location: main() function, while True loop (line ~1708)
    
    4. Deletion Execution (varies by mode):
       - Queue Mode: Maintains active queue, polls for completion, fills slots dynamically
       - Batch Mode: Processes in batches, waits for each batch to complete
       - Batch Sleep Mode: Same as batch but with delay between batches
       - All modes use threading for parallel execution
       - Location: run_queue_mode(), run_batch_mode(), run_batch_sleep_mode() functions
    
    5. Deletion Verification:
       - After deletion command completes, verifies app is actually deleted
       - Uses 'calm get apps -n <app_name>' to check if app still exists
       - If "No application found" in output → deletion successful
       - If app found in any state → deletion may still be in progress or failed
       - Why: Deletion command may return success but app might still exist (e.g., in "deleting" state)
       - Location: check_app_exists() function (line ~700), verify_deletion() in delete_app() (line ~800)
    
    6. Retry Logic:
       - Failed deletions are retried with exponential backoff
       - Default: 2 retries per app (configurable via --max_retries)
       - Backoff: 1s, 2s, 4s, etc. (doubles each retry)
       - Why: Network issues, temporary API errors, or race conditions may cause failures
       - Location: delete_app() function, retry loop (line ~780)

How the queue mode works:
    In queue mode, we maintain an active queue of apps being deleted:
    
    1. Initial Submission:
       - Submit up to parallel_users deletion commands immediately
       - Move apps from pending_apps → active_queue
       - Start threads for each deletion command
       - Wait for all threads to complete (ensures commands are submitted)
       - Location: run_queue_mode(), initial batch submission (line ~1350)
    
    2. Polling Loop (every poll_interval seconds):
       - Check each app in active_queue using 'calm get apps -n <app_name>'
       - If "No application found" → app deleted successfully
         * Move app to complete_queue
         * Remove from active_queue (free slot immediately)
       - If app found in any state → still deleting
         * Keep in active_queue (continue polling)
       - Location: run_queue_mode(), main polling loop (line ~1370)
    
    3. Filling Free Slots:
       - Calculate free_slots = parallel_users - len(active_queue)
       - If free_slots > 0 AND pending_apps not empty:
         * Submit new deletion commands to fill free slots
         * Start threads for each new deletion
         * Move from pending_apps → active_queue
         * Wait for threads to complete
       - Why: Keeps active queue full (up to concurrency limit) for optimal throughput
       - Location: run_queue_mode(), slot filling logic (line ~1400)
    
    4. Completion Check:
       - Break loop when: len(complete_queue) >= total_count
       - Also break if: len(pending_apps) == 0 AND len(active_queue) == 0
       - Why: Handles edge cases where apps might be stuck or untracked
       - Location: run_queue_mode(), completion check (line ~1450)
    
    5. Data Structures:
       - active_queue (dict): Apps currently being deleted (using slots)
       - complete_queue (dict): Apps that finished deleting (slots freed)
       - pending_apps (list): Apps not yet submitted for deletion
       - Location: run_queue_mode(), data structure initialization (line ~1320)

How the filtering works:
    The script filters apps based on two criteria:
    
    1. Pattern Matching:
       - User provides string pattern (e.g., "test")
       - Script converts to regex: re.escape(pattern) → matches if string appears anywhere
       - Case-insensitive matching
       - Example: Pattern "demo" matches "my-demo-app", "DemoApp", "app-demo-123"
       - Location: filter_apps_by_pattern(), regex compilation (line ~660)
    
    2. State Filtering:
       - ALWAYS excludes apps in "deleting" state
         * These apps are already being deleted
         * Sending another delete command is unnecessary
         * May cause errors or confusion
       - INCLUDES all other states:
         * "error" → App failed, needs deletion
         * "running" → App is running, can be deleted
         * "provisioning" → App is provisioning, can be deleted
         * "unknown" → Unknown state, attempt deletion
         * Any other state → Attempt deletion
       - Why: Only "deleting" state means deletion is already in progress
       - Location: filter_apps_by_pattern(), state checking logic (line ~670)

How deletion verification works:
    After sending a deletion command, the script verifies the app was actually deleted:
    
    1. Verification Method:
       - Runs: 'calm get apps -n <app_name>'
       - Checks output for "No application found" message
       - If found → app deleted successfully
       - If app details returned → app still exists (may be in "deleting" state)
    
    2. When Verification Happens:
       - Queue Mode: During polling loop, checks apps in active_queue
       - Batch Modes: After deletion command completes, before marking as success
       - Can be disabled with --no_verify flag
    
    3. Why Verification is Important:
       - Deletion command may return success but app might still exist
       - App might be in "deleting" state (deletion in progress)
       - Network issues or API delays may cause false positives
       - Verification ensures we only mark apps as deleted when they're actually gone
    
    4. Location:
       - check_app_exists() function (line ~921)
       - verify_deletion parameter in delete_app() function (line ~1082)
       - run_queue_mode() polling logic (line ~1657)
    
    5. COMPLETE SCRIPT EXECUTION FLOW:
       ┌─────────────────────────────────────────────────────────────┐
       │  COMPLETE SCRIPT EXECUTION FLOW                              │
       └─────────────────────────────────────────────────────────────┘
       
       STEP 1: INITIAL SETUP
          └─> Parse arguments, setup logging, get calm command
              └─> Validate inputs (pattern required, limit <= 250, etc.)
       
       STEP 2: ITERATION LOOP (handles >250 apps)
          └─> while True:  # Continue until no matching apps found
              │
              ├─> 2a. FETCH APPS (Iteration N)
              │   └─> calm get apps --out json --limit 250
              │       │
              │       ├─> Parse JSON: Extract entities[].status.name and entities[].status.state
              │       ├─> Extract total_matches from metadata.total_matches
              │       └─> Return: (apps_dict, total_matches, error_message)
              │
              ├─> 2b. FILTER APPS
              │   └─> Filter by pattern (regex match on app name)
              │       │
              │       ├─> EXCLUDE: Apps with state="deleting" (already being deleted)
              │       └─> INCLUDE: All other states (error, running, provisioning, unknown, etc.)
              │
              ├─> 2c. CHECK IF MATCHING APPS FOUND
              │   └─> If no matching apps:
              │       ├─> Iteration 0 → Exit (no apps to delete)
              │       └─> Iteration >0 → Break loop (all deleted, proceed to final verification)
              │
              ├─> 2d. OPTIONAL: SKIP MISSING APPS (if --skip_missing enabled, batch modes only)
              │   └─> For each matching app:
              │       ├─> check_app_exists(app_name)
              │       ├─> If False → Skip (already deleted)
              │       └─> If True → Keep for deletion
              │
              ├─> 2e. USER CONFIRMATION (only on iteration 0)
              │   └─> Prompt: "Delete N apps? (yes/no)"
              │
              ├─> 2f. EXECUTE DELETION (based on selected mode)
              │   │
              │   ├─> [BATCH MODE]
              │   │   └─> Submit batches of parallel_users apps
              │   │       └─> Wait for batch to complete → Next batch
              │   │
              │   ├─> [BATCH_SLEEP MODE]
              │   │   └─> Submit batches of parallel_users apps
              │   │       └─> Wait for batch → Sleep batch_delay seconds → Next batch
              │   │
              │   └─> [QUEUE MODE] (DEFAULT)
              │       └─> See STEP 3 below for detailed queue mode flow
              │
              └─> 2g. CHECK FOR MORE APPS
                  └─> If iteration completed → Continue to next iteration (re-fetch)
                      └─> If no more apps found → Break loop → Proceed to final verification
       
       STEP 3: QUEUE MODE DELETION FLOW (DEFAULT MODE)
          ┌─────────────────────────────────────────────────────────────┐
          │  QUEUE MODE: Active Queue Management with Polling          │
          └─────────────────────────────────────────────────────────────┘
          
          3a. INITIAL SUBMISSION
              └─> Submit up to parallel_users deletion commands immediately
                  └─> Start threads for each deletion command
                      └─> Move apps from pending_apps → active_queue
                      └─> Log: "[QUEUE] → Started deletion thread for: <app_name>"
                      └─> Log: "[14:46:28] [<app_name>] Executing delete command (attempt 1/3)..."
          
          3b. WAIT FOR COMMANDS TO BE SUBMITTED (5 seconds)
              └─> Wait for all initial deletion command threads to complete
                  └─> This ensures deletion commands are submitted before polling starts
          
          3c. MAIN POLLING LOOP (every poll_interval seconds, default: 15)
              └─> while len(complete_queue) < len(matching_apps):
                  │
                  ├─> 3c.1. CHECK FOR FAILED DELETIONS
                  │   └─> For each app in active_queue:
                  │       ├─> Check results dictionary
                  │       ├─> If deletion failed (e.g., 422 error):
                  │       │   └─> Log: "[QUEUE] ✗ <app_name> deletion failed: <error> - slot freed"
                  │       │   └─> Move to complete_queue → Free slot immediately
                  │       │   └─> Continue to next app (skip existence check)
                  │       └─> If deletion succeeded or still in progress:
                  │           └─> Proceed to existence check
                  │
                  ├─> 3c.2. CHECK APP EXISTENCE (for apps with successful deletion commands)
                  │   └─> For each app in active_queue (not yet checked):
                  │       ├─> Run: calm get apps -n <app_name>
                  │       │
                  │       ├─> If "No application found !!!" in output:
                  │       │   └─> App deleted successfully!
                  │       │   └─> Log: "[QUEUE] ✓ <app_name> deleted successfully - slot freed immediately"
                  │       │   └─> Move to complete_queue → Free slot
                  │       │
                  │       └─> If app found in output (any state: running, error, deleting):
                  │           └─> App still exists (may be in "deleting" state)
                  │           └─> Log: "[QUEUE] ⏳ <app_name> deletion command completed but app still exists (may be in 'deleting' state)"
                  │           └─> Keep in active_queue → Check again in next poll
                  │           └─> NOTE: "deletion command completed" means the delete command
                  │               was submitted successfully, but app hasn't been fully deleted yet
                  │
                  ├─> 3c.3. FILL FREE SLOTS
                  │   └─> Calculate: free_slots = parallel_users - len(active_queue)
                  │       └─> If free_slots > 0 AND pending_apps not empty:
                  │           ├─> Submit min(free_slots, len(pending_apps)) new deletions
                  │           ├─> Log: "[QUEUE] → Started deletion thread for: <app_name>"
                  │           └─> Move apps from pending_apps → active_queue
                  │
                  ├─> 3c.4. PRINT STATUS
                  │   └─> Log: "[QUEUE] Status - Active: X, Complete: Y, Pending: Z"
                  │
                  ├─> 3c.5. CHECK COMPLETION
                  │   └─> If len(complete_queue) >= len(matching_apps):
                  │       └─> All apps processed → Break polling loop
                  │
                  └─> 3c.6. WAIT BEFORE NEXT POLL
                      └─> Sleep poll_interval seconds (default: 15)
       
       STEP 4: FINAL VERIFICATION
          └─> After all iterations complete:
              ├─> Re-fetch apps one final time
              ├─> Filter by pattern
              └─> If no matching apps found:
                  └─> ✓ Verification passed: All deletions successful!
       
       LOG MESSAGE EXPLANATIONS:
       
       "[QUEUE] → Started deletion thread for: <app_name>"
          → We are about to fire the delete command (thread started)
       
       "[14:46:28] [<app_name>] Executing delete command (attempt 1/3)..."
          → Delete command is being executed (first attempt out of max_retries+1)
       
       "[QUEUE] ⏳ <app_name> deletion command completed but app still exists (may be in 'deleting' state)"
          → Delete command was submitted successfully (exit code 0)
          → BUT when we checked if app exists, it still exists
          → This means app is likely in "deleting" state (deletion in progress)
          → We will keep checking in next poll until app is fully deleted
          → NO ACTION NEEDED: This is normal - deletion is asynchronous
       
       "[QUEUE] ✓ <app_name> deleted successfully - slot freed immediately"
          → We checked if app exists using 'calm get apps -n <app_name>'
          → Got "No application found !!!" response
          → App is confirmed deleted
          → Slot is freed so we can submit next deletion
       
       "[QUEUE] ✗ <app_name> deletion failed: <error> (code: 422, category: INVALID_REQUEST) - slot freed"
          → Delete command failed (e.g., 422 error - app in provisioning state)
          → Slot is freed immediately (no need to keep polling)
          → Error is logged for reporting
       
       Key Points:
       - Asynchronous deletion: Calm deletion is asynchronous, app may be in "deleting" state
       - State progression: running/error/provisioning → deleting → deleted (not found)
       - Verification command: Uses 'calm get apps -n <app_name>' which returns app if exists
         in any state, or "No application found !!!" only when completely deleted
       - Error handling: 422 errors (e.g., app in provisioning) are detected and slots freed
       - Safety: On exceptions/timeouts, check_app_exists() returns False to avoid false positives
       - Queue mode keeps polling until all apps are confirmed deleted or failed

Error Handling & Logging:
    - Automatic retry with exponential backoff for failed deletions
    - Error categorization: NOT_FOUND, IN_USE, PERMISSION, TIMEOUT, NETWORK, UNKNOWN
    - Comprehensive logging to both console and file
    - Log file auto-generated with timestamp if not specified
    - Failed deletions tracked and reported in final summary
    - Detailed error messages extracted from command output
    - Location: delete_app() function, error parsing (line ~850)

COMMAND-LINE ARGUMENTS:

    Required:
        --app-name-pattern PATTERN    String pattern to match app names (converted to regex)
                                     If not provided, script shows help and exits

    Optional:
        --project PROJECT             Project name (optional, for filtering apps)
        --calm_dsl_dir PATH           Path to calm-dsl directory (default: from CALM_DSL_DIR env var)
        --mode {batch|batch_sleep|queue}
                                     Execution mode (default: queue)
                                     - queue: Active queue management with polling (DEFAULT)
                                     - batch: Sequential batches without sleep
                                     - batch_sleep: Sequential batches with delay
        --parallel_users N            Number of parallel deletions/concurrency (default: 10)
                                     Applies to all modes
        --batch_delay SECONDS         Delay in seconds between batches for batch_sleep mode (default: 0)
        --poll_interval SECONDS       Polling interval in seconds for queue mode (default: 15)
        --limit N                     Maximum number of apps to fetch (default: 250, max: 250)
        --max_retries N               Maximum retry attempts per app (default: 2)
        --no_verify                   Skip verification that app was deleted (default: verify)
        --skip_missing                Skip apps that are already deleted (default: enabled)
        --no_skip_missing             Do not skip apps that are already deleted
        --dry_run                     Show what would be deleted without actually deleting

DEFAULTS SUMMARY:
    - Mode: queue (active queue management with polling)
    - Concurrency: 10 parallel deletions
    - Poll interval: 15 seconds (for queue mode)
    - Skip missing: Enabled (apps already deleted are skipped)
    - Max retries: 2 attempts per app
    - Limit: 250 apps per fetch

RETURN CODES:
    0: All deletions successful
    1: One or more deletions failed

Author: Manish Gupta
Date: 2025
"""

import sys
import os
import re
import argparse
import threading
import time
import subprocess
from datetime import datetime

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

# Auto-detect Python from calm-dsl venv if pexpect is not available
try:
    import pexpect
except ImportError:
    # Try to find calm-dsl venv Python
    CALM_DSL_DIR = os.environ.get('CALM_DSL_DIR', '/Users/manish.gupta/Documents/GitHub/calm-dsl')
    venv_python = os.path.join(CALM_DSL_DIR, 'venv', 'bin', 'python')
    
    if os.path.exists(venv_python):
        print(f"pexpect not found in current Python, switching to: {venv_python}")
        print("Restarting script with venv Python...")
        os.execv(venv_python, [venv_python] + sys.argv)
    else:
        print("Error: pexpect module not found and calm-dsl venv not found.")
        print(f"Please install pexpect: pip install pexpect")
        print(f"Or set CALM_DSL_DIR environment variable to point to your calm-dsl directory")
        sys.exit(1)


def get_calm_command_and_env(calm_dsl_dir=None):
    """
    Determine the calm command and environment to use based on calm-dsl directory and venv.
    
    This function auto-detects the best way to invoke the calm command:
    1. If calm-dsl directory is provided and has a venv, use venv's calm executable
    2. Try Unix path first (bin/calm), then Windows path (Scripts/calm.exe)
    3. Fall back to python -m calm if executable not found
    4. Sets up environment variables (VIRTUAL_ENV, PATH) for proper dependency resolution
    
    Logic matches parallel_calm_launch.py for consistency.
    
    Args:
        calm_dsl_dir (str, optional): Path to calm-dsl directory
    
    Returns:
        tuple: (calm_cmd, env_dict) where:
            - calm_cmd: Full path to calm command or "calm" if using system command
            - env_dict: Environment dictionary with VIRTUAL_ENV and PATH configured
    """
    # Default: use system calm command
    calm_cmd = "calm"
    env = os.environ.copy()
    
    # If calm-dsl directory provided, try to use its venv
    if calm_dsl_dir and os.path.exists(calm_dsl_dir):
        venv_path = os.path.join(calm_dsl_dir, "venv")
        if os.path.exists(venv_path):
            # Strategy 1: Try to use venv's calm executable directly (Unix/Mac)
            venv_calm = os.path.join(venv_path, "bin", "calm")
            if os.path.exists(venv_calm):
                calm_cmd = venv_calm
            else:
                # Strategy 2: Try Windows path
                venv_calm = os.path.join(venv_path, "Scripts", "calm.exe")
                if os.path.exists(venv_calm):
                    calm_cmd = venv_calm
                else:
                    # Strategy 3: Fall back to python -m calm (works if calm is installed as module)
                    venv_python = os.path.join(venv_path, "bin", "python")
                    if os.path.exists(venv_python):
                        calm_cmd = f"{venv_python} -m calm"
            
            # Configure environment for venv
            # Set VIRTUAL_ENV so Python knows which venv is active
            env['VIRTUAL_ENV'] = venv_path
            # Add venv bin to PATH so calm can find its dependencies (e.g., other Python packages)
            venv_bin = os.path.join(venv_path, "bin")
            if os.path.exists(venv_bin):
                env['PATH'] = venv_bin + os.pathsep + env.get('PATH', '')
    
    return calm_cmd, env


def fetch_apps(calm_cmd, env=None, calm_dsl_dir=None, project=None, limit=None):
    """
    Fetch apps using 'calm get apps --out json --limit 250' command.
    
    This function uses a single command to fetch apps in JSON format:
    - Command: calm get apps --out json --limit 250
    - JSON output is easier to parse programmatically
    - Handles timeouts and errors gracefully
    - Uses --limit flag to fetch apps in batches (default: 250, Calm API maximum)
    - Extracts total_matches from metadata to calculate expected iterations
    
    The function changes to calm-dsl directory before running commands to ensure
    proper context and configuration.
    
    IMPORTANT: This function fetches up to 'limit' apps per call. The main script
    handles >250 apps by iteratively calling this function until no matching apps remain.
    
    Execution Flow:
        1. Run: calm get apps --out json --limit 250
        2. Parse JSON output to extract app names and states
        3. Extract total_matches from metadata
        4. Return apps_dict, total_matches, and error_message (if any)
        5. Main script will call this again after deletion to check for more apps
    
    Args:
        calm_cmd (str): Calm command to use (full path or "calm")
        env (dict, optional): Environment variables dictionary
        calm_dsl_dir (str, optional): Path to calm-dsl directory (for context)
        project (str, optional): Project name (currently not used in command, reserved for future)
        limit (int, optional): Maximum number of apps to fetch (default: 250, max: 250)
    
    Returns:
        tuple: (apps_dict, total_matches, error_message)
            - apps_dict (dict): Dictionary mapping app_name -> state (e.g., {'app1': 'running', 'app2': 'deleting'})
              Empty dict if fetch fails or no apps found
            - total_matches (int or None): Total number of apps from metadata.total_matches, None if not available
            - error_message (str or None): Error message if command failed, None if successful
    
    Note:
        Calm API has a hard limit of 250 apps per query. The main script iteratively
        calls this function until no matching apps remain.
    """
    original_cwd = os.getcwd()
    
    # Calm API has a maximum limit of 250 apps per query
    # Enforce this limit to avoid API errors
    if limit is None:
        limit = 250
    
    # Ensure limit doesn't exceed API maximum
    if limit > 250:
        limit = 250
    
    # Use single command: calm get apps --out json --limit 250
    # JSON output is preferred as it's structured and easier to parse programmatically
    # The script handles >250 apps by iteratively fetching and deleting until exhausted
    cmd = f"{calm_cmd} get apps --out json --limit {limit}"
    
    try:
        if calm_dsl_dir:
            os.chdir(calm_dsl_dir)
        
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
                timeout=120,  # Increased timeout for large result sets
            env=env
        )
        
        if calm_dsl_dir:
            os.chdir(original_cwd)
        
        # If command failed, capture error and return it
        if result.returncode != 0:
            # Build comprehensive error message
            error_msg = f"Command failed with exit code {result.returncode}"
            if result.stderr:
                error_msg += f"\nstderr: {result.stderr[:1000]}"  # First 1000 chars of stderr
            if result.stdout:
                error_msg += f"\nstdout: {result.stdout[:1000]}"  # First 1000 chars of stdout
            print(f"[ERROR] Command '{cmd}' failed (exit code: {result.returncode})")
            if result.stderr:
                print(f"  Error details: {result.stderr[:1000]}")
            return {}, None, error_msg
            
        # Combine stdout and stderr (warnings go to stderr but output is in stdout)
        full_output = result.stdout
        if result.stderr:
            # Warnings in stderr are usually fine, but log them
            if 'WARNING' in result.stderr:
                print(f"Note: {result.stderr.strip()}")
        
        # Parse JSON output (we always use --out json, so output should always be JSON)
        # Always use JSON parser since we're requesting JSON format
        apps_dict, total_matches = parse_apps_from_json(full_output)
        
        if apps_dict:
            print(f"Successfully fetched {len(apps_dict)} apps using command: {cmd}")
            if total_matches is not None:
                print(f"Total apps available: {total_matches} (fetched {len(apps_dict)} in this batch)")
            return apps_dict, total_matches, None  # Return apps_dict, total_matches, and no error
        else:
            # Check if output looks like JSON (safety check)
            if full_output.strip() and not (full_output.strip().startswith('[') or full_output.strip().startswith('{')):
                # Output doesn't look like JSON - might be an error message
                error_msg = f"Unexpected output format from command. Expected JSON but got: {full_output[:500]}"
                print(f"[ERROR] {error_msg}")
                return {}, None, error_msg
            else:
                # Parsing succeeded but no apps found - return empty dict (no error)
                # total_matches may have been extracted from metadata even if no apps found
                print(f"Successfully fetched 0 apps (no apps found)")
                return {}, total_matches, None
    
    except subprocess.TimeoutExpired:
        error_msg = f"Timeout while fetching apps with command: {cmd}"
        print(f"[ERROR] {error_msg}")
        return {}, None, error_msg
    except Exception as e:
        error_msg = f"Exception while executing command '{cmd}': {str(e)}"
        print(f"[ERROR] {error_msg}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()[:500]}")
        return {}, None, error_msg
        

def parse_apps_from_json(json_output):
    """
    Parse app names and states from JSON output.
    
    Expected JSON structure from 'calm get apps --out json':
    {
        "api_version": "3.0",
        "metadata": {...},
        "entities": [
            {
                "status": {
                    "name": "app-name",
                    "state": "running",
                    ...
                },
                "metadata": {...},
                ...
            },
            ...
        ]
    }
    
    Args:
        json_output (str): JSON output from calm get apps --out json
    
    Returns:
        dict: Dictionary mapping app_name -> state (e.g., {'app1': 'running', 'app2': 'deleting'})
    """
    try:
        import json
        data = json.loads(json_output)
        
        apps_dict = {}
        total_matches = None
        
        # Extract total_matches from metadata (if available)
        if isinstance(data, dict) and 'metadata' in data:
            metadata = data['metadata']
            if isinstance(metadata, dict) and 'total_matches' in metadata:
                try:
                    total_matches = int(metadata['total_matches'])
                except (ValueError, TypeError):
                    pass  # Keep total_matches as None if conversion fails
        
        # Expected structure: dict with "entities" key containing array of app objects
        if isinstance(data, dict) and 'entities' in data:
            entities = data['entities']
            if isinstance(entities, list):
                for entity in entities:
                    if isinstance(entity, dict):
                        # Extract app name and state from status object
                        # Structure: entity["status"]["name"] and entity["status"]["state"]
                        status = entity.get('status', {})
                        if isinstance(status, dict):
                            app_name = status.get('name')
                            app_state = status.get('state', '').lower() if status.get('state') else 'unknown'
                            
                            if app_name:
                                apps_dict[app_name] = app_state
                        else:
                            # Fallback: try metadata.name if status structure is different
                            metadata = entity.get('metadata', {})
                            if isinstance(metadata, dict):
                                app_name = metadata.get('name')
                                if app_name:
                                    apps_dict[app_name] = 'unknown'
        
        return apps_dict, total_matches
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse JSON output: {e}")
        print(f"[ERROR] JSON output preview (first 500 chars): {json_output[:500]}")
        return {}, None
    except Exception as e:
        print(f"[ERROR] Error processing JSON: {e}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()[:500]}")
        return {}, None


def parse_apps_from_output(full_output):
    """
    Parse app names and states from calm get apps table output.
    Handles table format with columns: NAME, SOURCE BLUEPRINT, STATE, etc.
    
    Args:
        full_output (str): Full output from calm get apps command
    
    Returns:
        dict: Dictionary mapping app_name -> state (e.g., {'app1': 'running', 'app2': 'deleting'})
    """
    apps_dict = {}
    lines = full_output.split('\n')
    
    # Find the table header row (contains NAME and STATE)
    header_found = False
    header_index = -1
    name_col_index = -1
    state_col_index = -1
    
    for i, line in enumerate(lines):
        if '|' in line and 'NAME' in line.upper():
            header_found = True
            header_index = i
            # Parse header to find column indices
            header_parts = [p.strip().upper() for p in line.split('|')]
            # Find NAME and STATE column indices
            for idx, part in enumerate(header_parts):
                if 'NAME' in part and name_col_index == -1:
                    name_col_index = idx
                if 'STATE' in part and state_col_index == -1:
                    state_col_index = idx
            break
    
    if not header_found:
        print("Warning: Could not find table header in output")
        print("Output preview (first 1000 chars):")
        print(full_output[:1000])
        return {}
    
    if name_col_index == -1:
        print("Warning: Could not find NAME column in table header")
        return {}
    
    # Start parsing from line after header
    # Skip the separator line that comes after the header (format: +----+----+)
    start_line = header_index + 1
    # If next line is a separator (starts with +), skip it
    if start_line < len(lines) and lines[start_line].strip().startswith('+'):
        start_line += 1
    
    # Parse data rows - continue until we hit the end of the table
    # Don't stop early - parse all rows until we find the table end marker
    for j in range(start_line, len(lines)):
        data_line = lines[j]
        
        # Stop at the end of table (line with dashes and plus signs)
        # But be more careful - only stop if it looks like a table separator
        if data_line.strip().startswith('+') and '--' in data_line:
            # Check if this is actually the end of the table
            # If there are more lines with | after this, it might be a separator in the middle
            found_more_data = False
            for k in range(j + 1, min(j + 5, len(lines))):  # Check next few lines
                if lines[k].strip() and '|' in lines[k]:
                    found_more_data = True
                    break
            if not found_more_data:
                break
        
        # Skip empty lines
        if not data_line.strip():
            continue
        
        # Parse table row
        if '|' in data_line:
            parts = [p.strip() for p in data_line.split('|')]
            # parts[0] is empty (before first |), parts[1] is first column
            if len(parts) > name_col_index and parts[name_col_index]:
                app_name = parts[name_col_index].strip()
                if app_name and app_name.upper() != 'NAME':  # Skip header if it appears again
                    # Extract state if STATE column exists
                    app_state = 'unknown'
                    if state_col_index != -1 and len(parts) > state_col_index and parts[state_col_index]:
                        app_state = parts[state_col_index].strip().lower()
                    apps_dict[app_name] = app_state
    
    return apps_dict


def filter_apps_by_pattern(apps_dict, pattern_string, exclude_deleting=True):
    """
    Filter apps by string pattern and state.
    
    The pattern string is converted to a regex that matches if the string
    appears anywhere in the app name.
    
    IMPORTANT: Include ALL states EXCEPT "deleting" state.
    Apps in "deleting" state are ALWAYS excluded (already being deleted, will complete automatically).
    All other states (error, running, provisioning, unknown, etc.) are INCLUDED for deletion.
    
    Args:
        apps_dict (dict): Dictionary mapping app_name -> state
        pattern_string (str): String pattern to match (will be converted to regex)
        exclude_deleting (bool): If True, exclude apps with state="deleting" (default: True)
                                 This is always enforced - "deleting" state is never included
    
    Returns:
        list: Filtered app names matching the pattern AND NOT in "deleting" state
              - Includes: ALL states except "deleting" (error, running, provisioning, unknown, etc.)
              - Excludes: ONLY "deleting" state
    """
    try:
        # Escape special regex characters and create a pattern that matches
        # if the string appears anywhere in the app name
        escaped_pattern = re.escape(pattern_string)
        regex = re.compile(escaped_pattern, re.IGNORECASE)
        
        matching_apps = []
        excluded_deleting_count = 0
        
        for app_name, app_state in apps_dict.items():
            # Check if app name matches pattern
            if regex.search(app_name):
                # Normalize state for comparison (case-insensitive)
                state_lower = app_state.lower() if app_state else ''
                
                # ALWAYS exclude apps in "deleting" state (already being deleted)
                if 'deleting' in state_lower:
                    excluded_deleting_count += 1
                    continue
                
                # Include apps in ALL other states (error, running, provisioning, unknown, etc.)
                # Only "deleting" state is excluded
                matching_apps.append(app_name)
        
        # Print summary of exclusions
        if excluded_deleting_count > 0:
            print(f"Excluded {excluded_deleting_count} app(s) that are already in 'deleting' state")
        
        return matching_apps
    except Exception as e:
        print(f"Error filtering apps: {e}")
        return []


def check_app_exists(calm_cmd, app_name, calm_dsl_dir=None, env=None):
    """
    Check if an app exists by querying Calm API.
    
    This function is used for two purposes:
    1. Pre-deletion check: Skip apps that are already deleted (if --skip_missing is used)
    2. Post-deletion verification: Confirm app was actually deleted (in queue mode polling)
    
    Logic:
        - Uses 'calm get apps -n <app_name>' command (note: plural "apps" with -n flag)
        - If command succeeds AND output contains app (not "No application found"):
          → app exists (may be in any state: running, error, deleting, etc.)
        - If command succeeds BUT output contains "No application found":
          → app doesn't exist (deleted or never existed)
        - If command fails (exit code != 0): assume app doesn't exist
        - On exception: assumes app doesn't exist (safer for deletion - avoids false positives)
    
    Note:
        Apps in "error", "running", "deleting" states all return success and show the app.
        Only when app is completely deleted does it return "No application found !!!"
        This is important for queue mode, which needs to distinguish between:
        - App exists (any state: error, running, deleting) -> keep in active queue
        - App doesn't exist ("No application found") -> free slot (deletion successful)
    
    Args:
        calm_cmd (str): Calm command to use
        app_name (str): Name of app to check
        calm_dsl_dir (str, optional): Path to calm-dsl directory (for context)
        env (dict, optional): Environment variables
    
    Returns:
        bool: True if app exists (found in output), False if app doesn't exist ("No application found")
    """
    original_cwd = os.getcwd()
    try:
        # Change to calm-dsl directory for proper context
        if calm_dsl_dir:
            os.chdir(calm_dsl_dir)
        
        # Query app status using 'calm get apps -n <app_name>'
        # This command returns the app if it exists (any state), or "No application found !!!" if deleted
        cmd = f"{calm_cmd} get apps -n {app_name}"
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout for app status check
            env=env
        )
        
        if calm_dsl_dir:
            os.chdir(original_cwd)
        
        # Check if command succeeded
        if result.returncode == 0:
            # Command succeeded - check output to see if app was found
            # If "No application found" in output → app doesn't exist (deleted)
            # If app name appears in table or output → app exists (any state)
            output_lower = result.stdout.lower() + result.stderr.lower()
            
            if 'no application found' in output_lower:
                # App doesn't exist (deleted)
                return False
            else:
                # App exists (found in output, may be in any state: error, running, deleting, etc.)
                # Check if app name appears in output as additional verification
                if app_name.lower() in output_lower:
                    return True
                # If output doesn't contain app name but also doesn't say "no application found",
                # assume it exists (command succeeded, might be in table format)
                return True
        else:
            # Command failed - assume app doesn't exist
            return False
    except Exception:
        # On any exception (timeout, network error, etc.), assume app doesn't exist
        # This is safer for deletion verification - avoids false positives
        # In worst case, we might skip a deletion that should happen, but that's better
        # than thinking an app is deleted when it's not
        if calm_dsl_dir:
            os.chdir(original_cwd)
        return False


def parse_deletion_error(stderr, stdout):
    """
    Parse deletion error output to extract meaningful error messages and categorize them.
    
    This function analyzes error output from calm delete commands to:
    1. Extract human-readable error messages
    2. Categorize errors for appropriate retry behavior
    
    Error Categories and Retry Behavior:
        - NOT_FOUND: App doesn't exist (may already be deleted) -> Don't retry
        - INVALID_REQUEST: Unable to delete (e.g., app in provisioning state, code 422) -> Don't retry
        - PERMISSION: Permission denied -> Don't retry (won't succeed on retry)
        - IN_USE: App has dependencies -> Don't retry
        - TIMEOUT: Operation timed out -> Retry (may succeed on retry)
        - NETWORK: Network/connection error -> Retry (transient error)
        - UNKNOWN: Other errors -> Retry (may be transient)
    
    Args:
        stderr (str): Standard error output from calm command
        stdout (str): Standard output from calm command (sometimes errors appear here)
    
    Returns:
        tuple: (error_message, error_category) where:
            - error_message: Human-readable error description
            - error_category: One of 'NOT_FOUND', 'INVALID_REQUEST', 'IN_USE', 'PERMISSION', 'TIMEOUT', 'NETWORK', 'UNKNOWN'
    """
    # Combine stderr and stdout for comprehensive error detection
    # Some calm commands may output errors to stdout instead of stderr
    combined = (stderr + " " + stdout).lower()
    
    # Pattern matching for common error types
    # Order matters: check specific errors before generic ones
    
    # NOT_FOUND: App doesn't exist (may already be deleted)
    # This is actually a success case for deletion - app is already gone
    if 'not found' in combined or 'does not exist' in combined or 'no such' in combined:
        return ("App not found (may already be deleted)", "NOT_FOUND")
    
    # INVALID_REQUEST (422): Unable to delete app (e.g., app in provisioning state)
    # Common error: "Unable to run normal delete action on Application" with code 422
    # This happens when app is in a state that doesn't allow deletion (e.g., provisioning)
    # Don't retry - app state needs to change first
    elif '422' in combined or 'invalid_request' in combined or 'unable to run normal delete action' in combined:
        # Try to extract the actual error message from JSON error response
        error_msg = "Unable to delete app (invalid request - app may be in provisioning or other non-deletable state)"
        # Check if there's a JSON error structure in stdout
        if stdout and ('"message"' in stdout or '"error"' in stdout):
            try:
                import json
                # Try to parse JSON error response
                if '{' in stdout:
                    json_start = stdout.find('{')
                    json_end = stdout.rfind('}') + 1
                    if json_end > json_start:
                        error_json = json.loads(stdout[json_start:json_end])
                        if 'error' in error_json and 'message_list' in error_json['error']:
                            messages = error_json['error']['message_list']
                            if messages and len(messages) > 0 and 'message' in messages[0]:
                                error_msg = messages[0]['message']
            except:
                pass  # Fall back to default message
        return (error_msg, "INVALID_REQUEST")
    
    # IN_USE: App has dependencies or is in use
    # Usually requires manual intervention
    elif 'in use' in combined or 'dependency' in combined or 'referenced' in combined:
        return ("App is in use or has dependencies", "IN_USE")
    
    # PERMISSION: Access denied
    # Won't succeed on retry - user doesn't have permission
    elif 'permission' in combined or 'forbidden' in combined or 'unauthorized' in combined:
        return ("Permission denied", "PERMISSION")
    
    # TIMEOUT: Operation took too long
    # May succeed on retry if system was temporarily slow
    elif 'timeout' in combined or 'timed out' in combined:
        return ("Operation timed out", "TIMEOUT")
    
    # NETWORK: Connection/network issues
    # Transient error - likely to succeed on retry
    elif 'connection' in combined or 'network' in combined or 'unreachable' in combined:
        return ("Network error", "NETWORK")
    
    else:
        # UNKNOWN: Other errors
        # Extract first meaningful error line from output
        # Try stderr first (standard error output), then stdout
        error_lines = stderr.split('\n') if stderr else []
        if not error_lines:
            error_lines = stdout.split('\n') if stdout else []
        
        error_msg = "Unknown error"
        for line in error_lines:
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith('#'):
                error_msg = line[:200]  # Limit length to avoid overly long messages
                break
        
        return (error_msg, "UNKNOWN")


def delete_app(calm_cmd, app_name, calm_dsl_dir=None, env=None, results=None, 
               max_retries=2, verify_deletion=True):
    """
    Delete a single app using 'calm delete app' command with retry logic and verification.
    
    This is the core deletion function that implements:
    1. Pre-deletion check (optional): Skip if app already deleted
    2. Retry logic with exponential backoff: Retries failed deletions up to max_retries times
    3. Post-deletion verification (optional): Confirms app was actually deleted
    4. Error categorization: Determines which errors should trigger retries
    
    Execution Flow:
        Step 1: Pre-check (if verify_deletion=True)
            - Check if app exists
            - If not exists, mark as ALREADY_DELETED and return success
        
        Step 2: Build delete command
            - Base: "calm delete app <app_name>"
        
        Step 3: Retry loop (up to max_retries + 1 attempts)
            - Execute delete command
            - On success: proceed to verification (if enabled)
            - On failure: categorize error and decide if retry is appropriate
            - Exponential backoff: wait 2^attempt seconds before retry
        
        Step 4: Verification (if verify_deletion=True)
            - Wait 2 seconds for deletion to propagate
            - Check if app still exists
            - If not exists: SUCCESS
            - If exists: VERIFICATION_FAILED (command succeeded but app still exists)
    
    Retry Behavior:
        - NOT_FOUND, PERMISSION errors: Don't retry (won't succeed)
        - TIMEOUT, NETWORK, UNKNOWN errors: Retry with exponential backoff
        - Max retries: max_retries (default: 2, so 3 total attempts)
    
    Args:
        calm_cmd (str): Calm command to use (full path or "calm")
        app_name (str): Name of app to delete
        calm_dsl_dir (str, optional): Path to calm-dsl directory (for context)
        env (dict, optional): Environment variables dictionary
        results (dict, optional): Dictionary to store results (thread-safe, can be shared)
            Format: {app_name: (success, exit_code, stdout, stderr, category)}
        max_retries (int): Maximum number of retry attempts (default: 2, so 3 total attempts)
        verify_deletion (bool): Whether to verify app was deleted after command succeeds
            - True: Check app existence after deletion (used in batch modes)
            - False: Skip verification (used in queue mode, which polls separately)
    
    Returns:
        None (results stored in results dictionary if provided)
    
    Note:
        This function is designed to be thread-safe and can be called from multiple threads
        concurrently. The results dictionary is the shared state.
    """
    original_cwd = os.getcwd()
    
    # Debug logging function with timestamp for better traceability
    def debug(msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{app_name}] {msg}")
    
    # STEP 1: Pre-deletion check (optional)
    # Skip deletion if app already doesn't exist
    # This is useful when --skip_missing is used or when retrying after a failed deletion
    if verify_deletion:
        debug("Checking if app exists...")
        if not check_app_exists(calm_cmd, app_name, calm_dsl_dir, env):
            debug("App does not exist (may already be deleted)")
            if results is not None:
                results[app_name] = (True, 0, "App already deleted", "", "ALREADY_DELETED")
            return
    
    # STEP 2: Build delete command
    # Base command: "calm delete app <app_name>"
    delete_cmd = f"{calm_cmd} delete app {app_name}"
    
    # Track state across retry attempts
    last_error = None
    last_exit_code = None
    last_stdout = ""
    last_stderr = ""
    
    # STEP 3: Retry loop with exponential backoff
    # Total attempts = max_retries + 1 (initial attempt + retries)
    # Example: max_retries=2 means 3 total attempts (attempt 0, 1, 2)
    for attempt in range(max_retries + 1):
        try:
            if calm_dsl_dir:
                os.chdir(calm_dsl_dir)
            
            # Exponential backoff: wait before retry (not before first attempt)
            # Delay = 2^attempt seconds: attempt 1 -> 2s, attempt 2 -> 4s, etc.
            if attempt > 0:
                delay = 2 ** attempt
                debug(f"Retry attempt {attempt + 1}/{max_retries + 1} after {delay}s delay...")
                time.sleep(delay)
            
            debug(f"Executing delete command (attempt {attempt + 1}/{max_retries + 1})...")
            
            # Execute deletion command with timeout
            # Timeout: 5 minutes (300 seconds) - deletion can take time for large apps
            result = subprocess.run(
                delete_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout per attempt
                env=env
            )
            
            if calm_dsl_dir:
                os.chdir(original_cwd)
            
            # Store result for potential retry or final reporting
            last_exit_code = result.returncode
            last_stdout = result.stdout
            last_stderr = result.stderr
            
            # STEP 4: Check if deletion command succeeded
            if result.returncode == 0:
                debug("Delete command completed successfully")
                
                # STEP 5: Post-deletion verification (if enabled)
                # Verify that app was actually deleted by checking if it still exists
                # This catches cases where command succeeds but deletion hasn't completed yet
                if verify_deletion:
                    debug("Verifying app deletion...")
                    # Brief wait for deletion to propagate through Calm API
                    # This is necessary because deletion is asynchronous - command may return
                    # success before the app is actually removed from the system
                    time.sleep(2)
                    
                    # Check if app still exists
                    if not check_app_exists(calm_cmd, app_name, calm_dsl_dir, env):
                        # App doesn't exist - deletion successful!
                        debug("✓ App successfully deleted and verified")
                        if results is not None:
                            results[app_name] = (True, 0, result.stdout, result.stderr, "SUCCESS")
                        return
                    else:
                        # App still exists - command succeeded but deletion not complete
                        # This can happen if deletion is in progress (state: "deleting")
                        # In batch mode, we treat this as success but log warning
                        # In queue mode, polling will detect when deletion completes
                        debug("⚠ Delete command succeeded but app still exists")
                        if results is not None:
                            results[app_name] = (True, 0, result.stdout, result.stderr, "VERIFICATION_FAILED")
                        return
                else:
                    # Verification disabled (used in queue mode)
                    # Queue mode handles verification via polling, so we skip it here
                    debug("✓ App deletion completed (verification skipped)")
                    if results is not None:
                        results[app_name] = (True, 0, result.stdout, result.stderr, "SUCCESS")
                    return
            
            # STEP 6: Command failed - parse and categorize error
            error_msg, error_category = parse_deletion_error(result.stderr, result.stdout)
            last_error = error_msg
            
            # STEP 7: Decide if retry is appropriate
            # Some errors won't succeed on retry (e.g., permission denied, invalid request)
            # Don't waste time retrying these
            if error_category in ['NOT_FOUND', 'PERMISSION', 'INVALID_REQUEST', 'IN_USE']:
                debug(f"✗ Deletion failed: {error_msg} (not retrying - {error_category})")
                if results is not None:
                    results[app_name] = (False, result.returncode, result.stdout, result.stderr, error_category)
                return
            
            # For other errors, continue to retry if attempts remain
            if attempt < max_retries:
                debug(f"✗ Deletion failed: {error_msg} (will retry)")
            else:
                debug(f"✗ Deletion failed after {max_retries + 1} attempts: {error_msg}")
        
        except subprocess.TimeoutExpired:
            debug(f"Timeout while deleting app (attempt {attempt + 1}/{max_retries + 1})")
            if calm_dsl_dir:
                os.chdir(original_cwd)
            
            last_error = "Timeout"
            last_exit_code = 1
            
            if attempt < max_retries:
                continue  # Retry on timeout
            else:
                if results is not None:
                    results[app_name] = (False, 1, "", "Timeout after all retries", "TIMEOUT")
                return
        
        except Exception as e:
            debug(f"Exception during deletion: {e}")
            if calm_dsl_dir:
                os.chdir(original_cwd)
            
            last_error = str(e)
            last_exit_code = 1
            
            if attempt < max_retries:
                continue  # Retry on exception
            else:
                if results is not None:
                    results[app_name] = (False, 1, "", str(e), "EXCEPTION")
                return
    
    # All retries exhausted
    error_msg, error_category = parse_deletion_error(last_stderr, last_stdout)
    if last_error:
        error_msg = last_error
    
    debug(f"✗ Deletion failed after all retries: {error_msg}")
    if results is not None:
        results[app_name] = (False, last_exit_code or 1, last_stdout, last_stderr, error_category)


def run_batch_mode(args, matching_apps, calm_cmd, env):
    """
    Mode 1: Batch without sleep - submit batches immediately one after another.
    
    EXECUTION FLOW:
        For each batch of parallel_users apps:
            1. Start deletion threads for all apps in batch (parallel)
            2. Wait for all threads in batch to complete (thread.join())
            3. Immediately start next batch (no delay)
        
        Example with 25 apps, parallel_users=10:
            - Batch 1: Apps 1-10  (submit, wait, done)
            - Batch 2: Apps 11-20 (submit immediately, wait, done)
            - Batch 3: Apps 21-25 (submit immediately, wait, done)
    
    CHARACTERISTICS:
        - Simple and straightforward
        - Fast execution (no delays)
        - All apps in a batch must complete before next batch starts
        - Good for: Fast deletion when system can handle load
    
    Args:
        args: Parsed command line arguments (must have parallel_users attribute)
        matching_apps: List of app names to delete
        calm_cmd: Calm command to use (full path or "calm")
        env: Environment variables dictionary
    
    Returns:
        dict: Results dictionary mapping app_name -> (success, exit_code, stdout, stderr, category)
    """
    print("=" * 80)
    print("MODE 1: BATCH WITHOUT SLEEP")
    print("=" * 80)
    print(f"Concurrency (batch size): {args.parallel_users}")
    print(f"Total apps to delete: {len(matching_apps)}")
    print("Behavior: Submit batches immediately, wait for completion, then submit next batch")
    print("=" * 80)
    print()
    
    results = {}
    start_time = time.time()
    
    for batch_start in range(0, len(matching_apps), args.parallel_users):
        batch_end = min(batch_start + args.parallel_users, len(matching_apps))
        batch = matching_apps[batch_start:batch_end]
        batch_num = (batch_start // args.parallel_users) + 1
        
        if len(matching_apps) > args.parallel_users:
            print(f"[BATCH] Starting batch {batch_num}: {len(batch)} apps (apps {batch_start+1}-{batch_end} of {len(matching_apps)})")
        else:
            print(f"[BATCH] Starting {len(batch)} deletions in parallel")
        
        # Start all threads in this batch
        threads = []
        for app_name in batch:
            thread = threading.Thread(
                target=delete_app,
                args=(calm_cmd, app_name, args.calm_dsl_dir, env, results, 
                      args.max_retries, not args.no_verify)
            )
            thread.start()
            threads.append(thread)
            print(f"[BATCH] Started deletion for: {app_name}")
        
        # Wait for all threads in this batch to complete
        print(f"[BATCH] Waiting for batch {batch_num} to complete...")
        for i, thread in enumerate(threads, 1):
            thread.join()
            print(f"[BATCH] Batch {batch_num} - Thread {i}/{len(threads)} completed")
        
        print(f"[BATCH] Batch {batch_num} completed")
        print()
    
    elapsed_time = time.time() - start_time
    print(f"[BATCH] All batches completed in {elapsed_time:.1f} seconds")
    return results


def run_batch_sleep_mode(args, matching_apps, calm_cmd, env):
    """
    Mode 2: Batch with sleep - submit batches with configurable delay between them.
    
    EXECUTION FLOW:
        For each batch of parallel_users apps:
            1. Start deletion threads for all apps in batch (parallel)
            2. Wait for all threads in batch to complete (thread.join())
            3. Sleep for batch_delay seconds (if not last batch)
            4. Start next batch
        
        Example with 25 apps, parallel_users=10, batch_delay=5:
            - Batch 1: Apps 1-10  (submit, wait, done)
            - Sleep: 5 seconds
            - Batch 2: Apps 11-20 (submit, wait, done)
            - Sleep: 5 seconds
            - Batch 3: Apps 21-25 (submit, wait, done)
    
    CHARACTERISTICS:
        - Rate limiting between batches
        - Prevents overwhelming the system
        - All apps in a batch must complete before next batch starts
        - Good for: Controlled deletion with rate limiting
    
    Args:
        args: Parsed command line arguments (must have parallel_users, batch_delay attributes)
        matching_apps: List of app names to delete
        calm_cmd: Calm command to use (full path or "calm")
        env: Environment variables dictionary
    
    Returns:
        dict: Results dictionary mapping app_name -> (success, exit_code, stdout, stderr, category)
    """
    print("=" * 80)
    print("MODE 2: BATCH WITH SLEEP")
    print("=" * 80)
    print(f"Concurrency (batch size): {args.parallel_users}")
    print(f"Sleep between batches: {args.batch_delay}s")
    print(f"Total apps to delete: {len(matching_apps)}")
    print("Behavior: Submit batch, wait for completion, sleep, then submit next batch")
    print("=" * 80)
    print()
    
    results = {}
    start_time = time.time()
    
    for batch_start in range(0, len(matching_apps), args.parallel_users):
        batch_end = min(batch_start + args.parallel_users, len(matching_apps))
        batch = matching_apps[batch_start:batch_end]
        batch_num = (batch_start // args.parallel_users) + 1
        
        if len(matching_apps) > args.parallel_users:
            print(f"[BATCH_SLEEP] Starting batch {batch_num}: {len(batch)} apps (apps {batch_start+1}-{batch_end} of {len(matching_apps)})")
        else:
            print(f"[BATCH_SLEEP] Starting {len(batch)} deletions in parallel")
        
        # Start all threads in this batch
        threads = []
        for app_name in batch:
            thread = threading.Thread(
                target=delete_app,
                args=(calm_cmd, app_name, args.calm_dsl_dir, env, results, 
                      args.max_retries, not args.no_verify)
            )
            thread.start()
            threads.append(thread)
            print(f"[BATCH_SLEEP] Started deletion for: {app_name}")
        
        # Wait for all threads in this batch to complete
        print(f"[BATCH_SLEEP] Waiting for batch {batch_num} to complete...")
        for i, thread in enumerate(threads, 1):
            thread.join()
            print(f"[BATCH_SLEEP] Batch {batch_num} - Thread {i}/{len(threads)} completed")
        
        print(f"[BATCH_SLEEP] Batch {batch_num} completed")
        
        # Sleep before starting next batch (if not the last batch)
        if batch_end < len(matching_apps) and args.batch_delay > 0:
            print(f"[BATCH_SLEEP] Sleeping {args.batch_delay}s before next batch...")
            time.sleep(args.batch_delay)
        print()
    
    elapsed_time = time.time() - start_time
    print(f"[BATCH_SLEEP] All batches completed in {elapsed_time:.1f} seconds")
    return results


def run_queue_mode(args, matching_apps, calm_cmd, env):
    """
    Mode 1: Active queue management with polling (DEFAULT).
    
    This mode maintains an active queue of deletions and uses polling to detect when
    deletions complete, immediately freeing slots and submitting new deletions.
    
    EXECUTION FLOW:
    
        STEP 1: Initial Submission
            - Submit up to parallel_users deletion commands immediately
            - Move apps from pending_apps → active_queue
            - Start threads for each deletion command
            - Example: Submit apps 1-10 (if parallel_users=10)
            - State: active_queue=10, pending=90, complete=0
        
        STEP 2: Wait for Commands to be Submitted (5 seconds)
            - Wait for all initial deletion command threads to complete
            - This ensures all deletion commands are submitted before polling starts
            - Allows system to start processing deletions
        
        STEP 3: Main Polling Loop (every poll_interval seconds, default: 15)
            
            3a. Check Active Queue Apps
                - For each app in active_queue:
                  - Use 'calm get apps -n <app_name>' to check if app exists
                  - If "No application found" in output:
                    → App deleted successfully
                    → Move app to complete_queue
                    → Free slot immediately
                    → Log: "✓ app_name deleted - slot freed"
                  - If app found (any state: error, running, deleting):
                    → Keep in active_queue (still deleting)
                    → Log: "⏳ app_name still deleting"
            
            3b. Calculate Free Slots
                - free_slots = parallel_users - len(active_queue)
                - This tells us how many new deletions we can submit
            
            3c. Submit New Deletions (fill free slots immediately)
                - If free_slots > 0 AND pending_apps not empty:
                  - Submit min(free_slots, len(pending_apps)) new deletions immediately
                  - Move apps from pending_apps → active_queue
                  - Wait for deletion command threads to complete
                - This keeps active queue full (up to concurrency limit) for optimal throughput
                - As soon as ANY slot is freed, it's immediately filled with next pending app
            
            3d. Print Status
                - "Active: X, Complete: Y, Pending: Z"
            
            3e. Check Completion
                - If len(complete_queue) >= len(matching_apps):
                  - All apps deleted → break loop
            
            3f. Wait Before Next Poll
                - Sleep poll_interval seconds (default: 15) before next iteration
    
    CHARACTERISTICS:
        - Dynamic slot management: Fills free slots immediately as deletions complete
        - Polling-based: Uses polling every poll_interval seconds to detect when deletions complete
        - Controlled concurrency: Maintains up to parallel_users concurrent deletions
        - Optimal throughput: Keeps active queue full (up to concurrency limit) for maximum efficiency
        - Handles >250 apps: Main loop re-fetches and re-deletes until no matching apps found
        - Good for: Large-scale deletions with optimal resource utilization
    
    QUEUE STATES:
        - pending_apps: Apps not yet submitted for deletion
        - active_queue: Apps with deletion commands submitted (being processed)
        - complete_queue: Apps confirmed deleted (not found in API via 'calm get apps -n')
    
    POLLING LOGIC:
        - Uses 'calm get apps -n <app_name>' to check if app exists
        - If app found in output (any state: error, running, deleting): app exists → keep in active_queue
        - If "No application found !!!" in output: app doesn't exist (deleted) → move to complete_queue, free slot
        - Apps in "error" and "running" states are included for deletion (only "deleting" is excluded)
    
    Args:
        args: Parsed command line arguments (must have parallel_users, poll_interval attributes)
        matching_apps: List of app names to delete
        calm_cmd: Calm command to use (full path or "calm")
        env: Environment variables dictionary
    
    Returns:
        tuple: (results, failed_apps) where:
            - results (dict): Results dictionary mapping app_name -> (success, exit_code, stdout, stderr, category)
            - failed_apps (set): Set of app names that failed to delete (e.g., 422 errors) and should be excluded from future iterations
    
    Note:
        Verification is disabled in delete_app() for queue mode (verify_deletion=False)
        because polling handles verification separately. This allows deletion commands
        to return immediately without waiting for verification.
        
        This function is called from main() which handles iterative fetching for >250 apps.
        The main loop re-fetches apps after each batch completes and calls this function
        again if more matching apps are found.
        
        Failed apps (e.g., 422 INVALID_REQUEST errors) are tracked separately and returned
        so they can be excluded from future iterations to prevent infinite loops.
    """
    print("=" * 80)
    print("MODE 3: ACTIVE QUEUE MANAGEMENT (POLLING)")
    print("=" * 80)
    print(f"Concurrency (active queue size): {args.parallel_users}")
    print(f"Total apps to delete: {len(matching_apps)}")
    print(f"Polling interval: {args.poll_interval} seconds")
    print()
    print("Behavior:")
    print("  - Maintains active queue of apps being deleted")
    print("  - Polls every {} seconds to check if apps are deleted".format(args.poll_interval))
    print("  - When apps are deleted (not found), slots are freed immediately")
    print("  - New deletions are submitted immediately to fill free slots")
    print("=" * 80)
    print()
    
    # Initialize queue data structures
    results = {}  # Shared results dictionary (thread-safe)
    active_queue = {}  # app_name -> {'thread': Thread, 'submitted': bool, 'thread_completed': bool}
    complete_queue = set()  # Set of app names that are confirmed deleted (not found in API)
    failed_apps = set()  # Set of app names that failed to delete (e.g., 422 errors) - exclude from future iterations
    pending_apps = list(matching_apps)  # Apps not yet submitted for deletion
    
    start_time = time.time()
    
    # STEP 1: Submit initial batch up to concurrency limit
    # Fill the active queue immediately to start processing
    print(f"[QUEUE] Submitting initial batch (up to {args.parallel_users} apps)...")
    initial_batch = min(args.parallel_users, len(pending_apps))
    initial_threads = []
    
    for i in range(initial_batch):
        app_name = pending_apps.pop(0)
        # Start deletion thread (verification disabled - polling handles it)
        thread = threading.Thread(
            target=delete_app,
            args=(calm_cmd, app_name, args.calm_dsl_dir, env, results, 
                  args.max_retries, False)  # verify_deletion=False for queue mode
        )
        thread.start()
        # Track thread in active queue
        active_queue[app_name] = {'thread': thread, 'submitted': True, 'thread_completed': False}
        initial_threads.append((app_name, thread))
        print(f"[QUEUE] Started deletion thread for: {app_name}")
    
    print(f"[QUEUE] Initial batch threads started. Active queue: {len(active_queue)} apps")
    print()
    
    # STEP 2: Wait for initial batch submission threads to complete
    # This ensures all deletion commands are fully submitted before we start polling
    # Important: We wait for threads to complete, not for deletions to finish
    # The deletion commands are asynchronous - they return immediately after submission
    print("[QUEUE] Waiting for initial batch deletion commands to be submitted...")
    for app_name, thread in initial_threads:
        thread.join()  # Wait for deletion command to be submitted
        active_queue[app_name]['thread_completed'] = True
        print(f"[QUEUE] ✓ Deletion command submitted for: {app_name}")
    print("[QUEUE] All initial deletion commands submitted. Starting polling...")
    print()
    
    # STEP 3: Wait before first poll
    # Give the system time to start processing deletions before we check status
    # This prevents false negatives (checking too early, before deletion starts)
    print(f"[QUEUE] Waiting 5 seconds before first poll (to allow deletions to start processing)...")
    time.sleep(5)
    print()
    
    # STEP 4: Main polling loop
    # Continue polling until all apps are confirmed deleted (in complete_queue)
    poll_count = 0
    # Main polling loop: Continue until all apps are deleted
    # Loop condition: Keep polling while complete_queue < matching_apps
    # Additional exit condition: If no pending AND no active apps, we're done (handled inside loop)
    while len(complete_queue) < len(matching_apps):
        poll_count += 1
        print(f"[QUEUE] Poll #{poll_count} - Checking app deletion status...")
        
        # 4a. Check Active Queue Apps
        # For each app in active queue, check if it still exists in Calm
        # If app doesn't exist → deletion successful → free slot immediately
        apps_to_move = []
        slots_freed_count = 0
        
        for app_name in list(active_queue.keys()):
            # First, check if deletion command failed (check results dictionary)
            # This handles cases where deletion command failed (e.g., 422 error) but app still exists
            thread_info = active_queue[app_name]
            thread_completed = thread_info.get('thread_completed', False)
            
            # Check if deletion command failed (if thread completed and result is in results dict)
            if thread_completed and app_name in results:
                success, exit_code, stdout, stderr, category = results[app_name]
                if not success:
                    # Deletion command failed - free slot and report error
                    # This handles 422 errors and other failures where app still exists but deletion failed
                    apps_to_move.append(app_name)
                    failed_apps.add(app_name)  # Track failed app - exclude from future iterations
                    # NOTE: Do NOT add to complete_queue - failed apps should not count as "deleted"
                    # They will be excluded from future iterations to prevent infinite loops
                    
                    # Extract error message for reporting
                    error_msg = f"Deletion failed with {category}"
                    if category == "INVALID_REQUEST":
                        # Try to extract detailed error message
                        if stdout and ('"message"' in stdout or '"error"' in stdout):
                            try:
                                import json
                                if '{' in stdout:
                                    json_start = stdout.find('{')
                                    json_end = stdout.rfind('}') + 1
                                    if json_end > json_start:
                                        error_json = json.loads(stdout[json_start:json_end])
                                        if 'error' in error_json and 'message_list' in error_json['error']:
                                            messages = error_json['error']['message_list']
                                            if messages and len(messages) > 0 and 'message' in messages[0]:
                                                error_msg = messages[0]['message']
                            except:
                                pass
                    
                    print(f"[QUEUE] ✗ {app_name} deletion failed: {error_msg} (code: {exit_code}, category: {category}) - slot freed")
                    print(f"[QUEUE]   → App will be excluded from future iterations to prevent infinite loop")
                    slots_freed_count += 1
                    continue  # Skip existence check - we already know it failed
            
            # Query Calm API to check if app exists
            # Returns True if app exists (any state), False if app doesn't exist (deleted)
            exists = check_app_exists(calm_cmd, app_name, args.calm_dsl_dir, env)
            
            if not exists:
                # App not found = successfully deleted!
                # Move to complete queue and free up the slot
                apps_to_move.append(app_name)
                complete_queue.add(app_name)
                print(f"[QUEUE] ✓ {app_name} deleted successfully - slot freed immediately")
                slots_freed_count += 1
            else:
                # App still exists - deletion in progress
                # Keep in active queue and check again in next poll
                if thread_info['thread'].is_alive():
                    # Thread still running (deletion command may still be executing)
                    print(f"[QUEUE] ⏳ {app_name} still deleting (thread active)")
                else:
                    # Thread completed but app still exists
                    # This means deletion command was submitted, but app is in "deleting" state
                    # Calm deletion is asynchronous - app may show as "deleting" for a while
                    # Note: If deletion failed, we would have caught it above in the results check
                    print(f"[QUEUE] ⏳ {app_name} deletion command completed but app still exists (may be in 'deleting' state)")
        
        # 4b. Remove deleted apps from active queue to free slots
        # This immediately makes slots available for new deletions
        for app_name in apps_to_move:
            del active_queue[app_name]
        
        # 4c. Calculate free slots
        # Free slots = concurrency limit - current active queue size
        free_slots = args.parallel_users - len(active_queue)
        
        # 4d. Submit new deletions if slots available
        # Strategy: Fill free slots immediately as they become available
        # This keeps the active queue full (up to concurrency limit) for optimal throughput
        if slots_freed_count > 0:
            print(f"[QUEUE] {slots_freed_count} slot(s) freed. Free slots available: {free_slots}")
        
        if free_slots > 0 and pending_apps:
            # Fill available free slots immediately
            # Submit as many new deletions as we have free slots (or remaining pending apps)
            apps_to_submit = min(free_slots, len(pending_apps))
            print(f"[QUEUE] Submitting {apps_to_submit} new deletion(s) to fill free slots...")
            
            new_threads = []
            for i in range(apps_to_submit):
                app_name = pending_apps.pop(0)
                # Start deletion thread (verification disabled - polling handles it)
                thread = threading.Thread(
                    target=delete_app,
                    args=(calm_cmd, app_name, args.calm_dsl_dir, env, results, 
                          args.max_retries, False)  # verify_deletion=False for queue mode
                )
                thread.start()
                # Track in active queue
                active_queue[app_name] = {'thread': thread, 'submitted': True, 'thread_completed': False}
                new_threads.append((app_name, thread))
                print(f"[QUEUE] → Started deletion thread for: {app_name}")
            
            # Wait for newly submitted threads to complete (deletion commands submitted)
            # This ensures deletion commands are fully submitted before next poll
            print(f"[QUEUE] Waiting for {len(new_threads)} deletion command(s) to be submitted...")
            for app_name, thread in new_threads:
                thread.join()  # Wait for deletion command to be submitted
                active_queue[app_name]['thread_completed'] = True
                print(f"[QUEUE] ✓ Deletion command submitted for: {app_name}")
            print(f"[QUEUE] All new deletion commands submitted.")
        elif free_slots > 0 and not pending_apps:
            print(f"[QUEUE] {free_slots} free slot(s) available but no pending apps to delete")
        elif not free_slots and pending_apps:
            print(f"[QUEUE] No free slots available (active queue full: {len(active_queue)}/{args.parallel_users}, {len(pending_apps)} pending)")
        
        # 4e. Print status summary
        # Shows current state: how many apps are active, complete, and pending
        print(f"[QUEUE] Status - Active: {len(active_queue)}, Complete: {len(complete_queue)}, Pending: {len(pending_apps)}")
        
        # 4f. Check completion condition
        # All apps processed: either deleted (in complete_queue) or failed (in failed_apps)
        # Only count successfully deleted apps, not failed ones
        successfully_deleted = len(complete_queue)
        total_processed = successfully_deleted + len(failed_apps)
        
        if total_processed >= len(matching_apps):
            if len(failed_apps) > 0:
                print(f"[QUEUE] All {len(matching_apps)} apps processed: {successfully_deleted} deleted, {len(failed_apps)} failed")
            else:
                print(f"[QUEUE] All {len(matching_apps)} apps have been deleted!")
            break
        
        # Additional check: If no pending apps and no active apps, we're done
        # This handles edge cases where all apps are processed
        if len(pending_apps) == 0 and len(active_queue) == 0:
            if total_processed >= len(matching_apps):
                if len(failed_apps) > 0:
                    print(f"[QUEUE] All {len(matching_apps)} apps processed: {successfully_deleted} deleted, {len(failed_apps)} failed")
                else:
                    print(f"[QUEUE] All {len(matching_apps)} apps have been deleted!")
            else:
                print(f"[QUEUE] No pending or active apps, but only {total_processed}/{len(matching_apps)} processed.")
                print(f"[QUEUE] This may indicate some apps were not tracked. Exiting queue mode.")
            break
        
        # Debug: Show why loop is continuing (if no pending apps but still active)
        if len(pending_apps) == 0 and len(active_queue) > 0:
            remaining_active = list(active_queue.keys())
            print(f"[QUEUE] Continuing to poll {len(active_queue)} app(s) until deleted: {', '.join(remaining_active[:3])}{'...' if len(remaining_active) > 3 else ''}")
        
        # 4g. Wait before next poll
        # Polling interval controls how often we check for completed deletions
        # Shorter interval = faster slot reuse but more API calls
        # Longer interval = fewer API calls but slower slot reuse
        if len(complete_queue) < len(matching_apps):
            print(f"[QUEUE] Waiting {args.poll_interval} seconds before next poll...")
            time.sleep(args.poll_interval)
        print()
    
    # Cleanup: Wait for any remaining threads to complete
    # This handles edge cases where threads are still running when loop exits
    remaining_threads = [info['thread'] for info in active_queue.values() if info['thread'].is_alive()]
    if remaining_threads:
        print(f"[QUEUE] Waiting for {len(remaining_threads)} remaining deletion thread(s) to complete...")
        for thread in remaining_threads:
            thread.join()
    
    elapsed_time = time.time() - start_time
    print(f"[QUEUE] All deletions completed in {elapsed_time:.1f} seconds")
    if len(failed_apps) > 0:
        print(f"[QUEUE] Note: {len(failed_apps)} app(s) failed to delete and will be excluded from future iterations:")
        for app_name in sorted(failed_apps):
            if app_name in results:
                success, exit_code, stdout, stderr, category = results[app_name]
                print(f"[QUEUE]   - {app_name} (category: {category})")
    return results, failed_apps


def main():
    """
    Main entry point for parallel Calm app deletion script.
    
    EXECUTION FLOW:
        1. Parse command-line arguments
        2. Validate arguments (limit, calm-dsl directory, etc.)
        3. Get calm command and environment (auto-detect venv)
        4. Fetch all apps from Calm API
        5. Filter apps by pattern (regex matching)
        6. Optional: Skip already-deleted apps (if --skip_missing)
        7. Confirm deletion with user (unless --dry_run)
        8. Route to appropriate execution mode:
           - Mode 1 (batch): run_batch_mode()
           - Mode 2 (batch_sleep): run_batch_sleep_mode()
           - Mode 3 (queue): run_queue_mode()
        9. Print final results summary
    
    Returns:
        None (exits with code 0 on success, 1 on failure)
    """
    parser = argparse.ArgumentParser(
        description='Delete Calm apps matching a regex pattern in parallel batches',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

    Basic usage (queue mode, default):
        python3 parallel_calm_delete.py --app-name-pattern "automation-gmanish" --project projectbk
        # Uses: queue mode, concurrency=10, poll_interval=15, skip_missing=enabled

    Minimal usage (all defaults):
        python3 parallel_calm_delete.py --app-name-pattern "demo"
        # Uses: queue mode, concurrency=10, poll_interval=15, skip_missing=enabled

    Queue mode with custom concurrency:
        python3 parallel_calm_delete.py --app-name-pattern "test" --mode queue --parallel_users 20 --poll_interval 10

    Batch mode (explicit):
        python3 parallel_calm_delete.py --app-name-pattern "test" --mode batch --parallel_users 10

    Batch with sleep:
        python3 parallel_calm_delete.py --app-name-pattern "old-apps" --mode batch_sleep --batch_delay 3

    Dry run (preview what would be deleted):
        python3 parallel_calm_delete.py --app-name-pattern "test" --dry_run

    Disable skip already-deleted apps:
        python3 parallel_calm_delete.py --app-name-pattern "test" --no_skip_missing

    Custom log file:
        python3 parallel_calm_delete.py --app-name-pattern "test" --log_file /path/to/my_log.log

    Show help (when no arguments provided):
        python3 parallel_calm_delete.py

KEY FEATURES:
    - Handles >250 apps by iteratively fetching and deleting until exhausted
    - Automatically skips apps in "deleting" state (already being deleted)
    - Includes ALL other states for deletion (error, running, provisioning, etc.)
    - Verifies deletions by checking if app still exists
    - Retries failed deletions with exponential backoff
    - Comprehensive logging to both console and file
    - Three execution modes: queue (default), batch, batch_sleep

For more information, see the script documentation or contact Manish.Gupta@nutanix.com
        """
    )
    
    parser.add_argument('--app-name-pattern',
                       help='String pattern to match app names (e.g., "automation-gmanish"). '
                            'Script will convert to regex to match if string appears anywhere in app name. '
                            'REQUIRED: This argument must be provided.')
    parser.add_argument('--project',
                       help='Project name (optional, for filtering apps)')
    parser.add_argument('--calm_dsl_dir',
                       default=os.environ.get('CALM_DSL_DIR', '/Users/manish.gupta/Documents/GitHub/calm-dsl'),
                       help='Path to calm-dsl directory')
    parser.add_argument('--parallel_users', type=int, default=10,
                       help='Number of parallel deletions per batch (default: 10)')
    parser.add_argument('--batch_delay', type=float, default=0.0,
                       help='Delay in seconds between batches (default: 0)')
    parser.add_argument('--limit', type=int, default=250,
                       help='Maximum number of apps to fetch (default: 250, max: 250). '
                            'NOTE: Currently NOT USED - --limit flag is broken in calm CLI. '
                            'Script fetches all apps without limit flag as workaround. '
                            'The script handles >250 apps by iteratively fetching and deleting until exhausted.')
    parser.add_argument('--dry_run', action='store_true',
                       help='Show what would be deleted without actually deleting')
    parser.add_argument('--max_retries', type=int, default=2,
                       help='Maximum number of retry attempts per app (default: 2)')
    parser.add_argument('--no_verify', action='store_true',
                       help='Skip verification that app was actually deleted (default: verify)')
    # Skip missing is enabled by default
    parser.add_argument('--no_skip_missing', action='store_false', dest='skip_missing',
                       default=True,
                       help='Do not skip apps that are already deleted (default: skip_missing is enabled)')
    parser.add_argument('--skip_missing', action='store_true',
                       help='Skip apps that are already deleted (default: enabled)')
    parser.add_argument('--mode', type=str, choices=['batch', 'batch_sleep', 'queue'], default='queue',
                       help='Execution mode: "queue" (active queue management with polling, default), '
                            '"batch" (no sleep), or "batch_sleep" (sleep between batches)')
    parser.add_argument('--poll_interval', type=int, default=15,
                       help='Polling interval in seconds for queue mode (default: 15)')
    parser.add_argument('--log_file',
                       help='Path to log file for all console output (default: auto-generated with date/time). '
                            'All console output will be duplicated to this file.')
    
    args = parser.parse_args()
    
    # Check if required argument is provided, show help if not
    if not args.app_name_pattern:
        parser.print_help()
        print()
        print("ERROR: --app-name-pattern is required.")
        print("Example: python3 parallel_calm_delete.py --app-name-pattern 'demo'")
        sys.exit(1)
    
    # Validate limit (Calm API maximum is 250)
    if args.limit > 250:
        print(f"Warning: Limit {args.limit} exceeds maximum of 250. Setting to 250.")
        args.limit = 250
    elif args.limit < 1:
        print(f"Error: Limit must be at least 1. Got: {args.limit}")
        sys.exit(1)
    
    # Validate calm-dsl directory
    if args.calm_dsl_dir and not os.path.exists(args.calm_dsl_dir):
        print(f"Error: Calm-DSL directory not found: {args.calm_dsl_dir}")
        sys.exit(1)
    
    # Setup file logging - generate default log file name if not provided
    if args.log_file:
        log_file_path = args.log_file
    else:
        # Auto-generate log file name with date/time: parallel_calm_delete_YYYYMMDD-HHMMSS.log
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_file_path = f"parallel_calm_delete_{timestamp}.log"
    
    # Setup file logging - redirects all stdout/stderr to both console and file
    if setup_file_logging(log_file_path):
        # This print will go to both console and file (since stdout is redirected)
        print(f"[INFO] All console output is being logged to: {os.path.abspath(log_file_path)}")
        print()
    
    script_start_time = time.time()  # Track total script execution time
    
    # Get calm command and environment (matches launch script logic)
    calm_cmd, env = get_calm_command_and_env(args.calm_dsl_dir)
    
    print("=" * 80)
    print("PARALLEL CALM APP DELETION")
    print("=" * 80)
    print(f"App name pattern: {args.app_name_pattern}")
    print(f"Project: {args.project or 'All projects'}")
    print(f"Calm-DSL directory: {args.calm_dsl_dir}")
    print(f"Execution mode: {args.mode}")
    print(f"Parallel users (concurrency): {args.parallel_users}")
    if args.mode == 'batch_sleep':
        print(f"Sleep between batches: {args.batch_delay}s")
    elif args.mode == 'queue':
        print(f"Polling interval: {args.poll_interval}s")
    print(f"Fetch limit: {args.limit}")
    print(f"Max retries per app: {args.max_retries}")
    print(f"Verify deletion: {not args.no_verify}")
    print(f"Skip already deleted: {args.skip_missing}")
    print(f"Dry run: {args.dry_run}")
    print("=" * 80)
    print()
    
    # Main deletion loop: Continue fetching and deleting until no more matching apps found
    # This handles cases where there are more than 250 apps (API limit)
    # Iteration 0: Fetch first 250 apps, delete them
    # Iteration 1: Fetch next 250 apps (if any), delete them
    # Continue until no matching apps found
    all_results = {}
    all_failed_apps = set()  # Track failed apps across all iterations to prevent infinite loops
    iteration = -1  # Start at -1 so first iteration is 0
    
    while True:
        iteration += 1
        print("=" * 80)
        print(f"ITERATION {iteration}: Fetching and deleting apps (limit: {args.limit})")
        print("=" * 80)
        print()
        
        # Fetch apps (returns tuple: apps_dict, total_matches, error_message)
        print("Fetching apps...")
        apps_dict, total_matches, fetch_error = fetch_apps(calm_cmd, env, args.calm_dsl_dir, args.project, args.limit)
        
        # Check if fetch command failed
        if fetch_error:
            print(f"[ERROR] Failed to fetch apps: {fetch_error}")
            print("[ERROR] This indicates the 'calm get apps' command failed with an error.")
            print("[ERROR] Please check the error details above and fix the issue before retrying.")
            sys.exit(1)
        
        # Display total matches and calculate expected iterations (only on first iteration)
        if iteration == 0 and total_matches is not None:
            import math
            max_per_iteration = args.limit or 250
            expected_iterations = math.ceil(total_matches / max_per_iteration) if total_matches > 0 else 0
            print(f"Total apps available: {total_matches}")
            if expected_iterations > 1:
                print(f"Expected iterations: {expected_iterations} (fetching {max_per_iteration} apps per iteration, max 250 per API call)")
            print(f"Found {len(apps_dict)} apps in this batch")
        else:
            print(f"Found {len(apps_dict)} apps in this batch")
        print()
        
        # Filter by pattern and state
        # IMPORTANT: Include ALL states EXCEPT "deleting" state
        # Apps in "deleting" state are ALWAYS excluded (already being deleted, will complete automatically)
        # All other states (error, running, provisioning, unknown, etc.) are INCLUDED for deletion
        matching_apps = filter_apps_by_pattern(apps_dict, args.app_name_pattern, exclude_deleting=True)
        
        # Exclude failed apps from previous iterations to prevent infinite loops
        # Failed apps (e.g., 422 INVALID_REQUEST errors) are tracked and excluded
        if iteration > 0 and len(all_failed_apps) > 0:
            original_count = len(matching_apps)
            matching_apps = [app for app in matching_apps if app not in all_failed_apps]
            excluded_count = original_count - len(matching_apps)
            if excluded_count > 0:
                print(f"Excluded {excluded_count} app(s) that failed in previous iterations (to prevent infinite loop)")
        
        print(f"Apps matching pattern '{args.app_name_pattern}' (excluding 'deleting' state, all other states included): {len(matching_apps)}")
        
        if not matching_apps:
            if iteration == 0:
                print("No apps match the pattern. Exiting.")
                sys.exit(0)
            else:
                print("No more matching apps found. All deletions complete!")
                break
        
        print()
        print("Matching apps to delete:")
        for i, app_name in enumerate(matching_apps, 1):
            state = apps_dict.get(app_name, 'unknown')
            print(f"  {i}. {app_name} (state: {state})")
        print()
        
        if args.dry_run:
            print("DRY RUN: Would delete the above apps. Exiting without deletion.")
            sys.exit(0)
        
        # Check for already-deleted apps if skip_missing is enabled
        # Note: For queue mode, we skip this pre-check because:
        # 1. Queue mode polls to detect completion, so it handles missing apps naturally
        # 2. Apps in "error" state might not be queryable but still need deletion
        # 3. The deletion command itself will handle apps that don't exist
        if args.skip_missing and args.mode != 'queue':
            print()
            print("Checking which apps already exist...")
            existing_apps = []
            missing_apps = []
            
            for app_name in matching_apps:
                if check_app_exists(calm_cmd, app_name, args.calm_dsl_dir, env):
                    existing_apps.append(app_name)
                else:
                    missing_apps.append(app_name)
            
            print(f"Found {len(existing_apps)} apps that exist (will be deleted)")
            if missing_apps:
                print(f"Found {len(missing_apps)} apps that don't exist (will be skipped)")
                if len(missing_apps) <= 20:  # Only show list if not too many
                    print("Skipped apps:")
                    for app_name in missing_apps:
                        print(f"  - {app_name}")
                else:
                    print(f"  (showing first 10 of {len(missing_apps)} skipped apps)")
                    for app_name in missing_apps[:10]:
                        print(f"  - {app_name}")
                    print(f"  ... and {len(missing_apps) - 10} more")
            
            matching_apps = existing_apps  # Only delete apps that exist
            
            if not matching_apps:
                print("No apps to delete in this iteration (all are already deleted).")
                print("Continuing to check for more apps...")
                print()
                # Skip to next iteration - no need to proceed with deletion
                # We'll break out of the skip_missing check and continue the while loop
                pass
            else:
                print()
        elif args.skip_missing and args.mode == 'queue':
            # For queue mode, skip the pre-check but inform user
            print()
            print("Note: --skip_missing is enabled but skipped for queue mode.")
            print("Queue mode will handle missing apps during polling.")
            print()
        
        # Skip deletion if no matching apps (from skip_missing check above)
        if not matching_apps:
            # Continue to next iteration of while loop
            continue
        
        # Confirm deletion (only on first iteration)
        if iteration == 0:
            response = input(f"Delete {len(matching_apps)} apps? (yes/no): ")
            if response.lower() != 'yes':
                print("Cancelled.")
                sys.exit(0)
            print()
        
        print(f"Starting parallel deletions for iteration {iteration}...")
        
        # Route to appropriate execution mode
        if args.mode == 'batch':
            iteration_results = run_batch_mode(args, matching_apps, calm_cmd, env)
            iteration_failed_apps = set()  # Batch modes don't track failed apps separately
        elif args.mode == 'batch_sleep':
            iteration_results = run_batch_sleep_mode(args, matching_apps, calm_cmd, env)
            iteration_failed_apps = set()  # Batch modes don't track failed apps separately
        else:  # queue mode (default)
            iteration_results, iteration_failed_apps = run_queue_mode(args, matching_apps, calm_cmd, env)
        
        # Merge results from this iteration
        all_results.update(iteration_results)
        
        # Track failed apps across iterations to exclude them from future fetches
        # This prevents infinite loops when apps fail to delete (e.g., 422 errors)
        if iteration == 0:
            all_failed_apps = set(iteration_failed_apps)
        else:
            all_failed_apps.update(iteration_failed_apps)
        
        # Report failed apps if any
        if len(iteration_failed_apps) > 0:
            print(f"[ITERATION {iteration}] {len(iteration_failed_apps)} app(s) failed to delete and will be excluded from future iterations")
        
        print()
        print(f"Iteration {iteration} completed. Checking for more apps...")
        print()
        
        # Brief pause before next fetch to allow deletions to propagate
        if len(matching_apps) > 0:
            print("Waiting 5 seconds before next fetch (to allow deletions to propagate)...")
            time.sleep(5)
            print()
    
    # Final verification: Re-fetch one more time to ensure no matching apps remain
    print("=" * 80)
    print("FINAL VERIFICATION")
    print("=" * 80)
    print()
    print("Re-fetching apps to verify all matching apps are deleted...")
    final_apps_dict, final_total_matches, final_fetch_error = fetch_apps(calm_cmd, env, args.calm_dsl_dir, args.project, args.limit)
    
    # Check if final fetch failed
    if final_fetch_error:
        print(f"[WARNING] Final verification fetch failed: {final_fetch_error}")
        print("[WARNING] Cannot verify if all apps are deleted. Please check manually.")
    else:
        final_matching = filter_apps_by_pattern(final_apps_dict, args.app_name_pattern, exclude_deleting=True)
        
        if not final_matching:
            print("✓ Verification passed: No matching apps found. All deletions successful!")
        else:
            print(f"⚠ Warning: {len(final_matching)} matching app(s) still found after deletion:")
            for app_name in final_matching:
                state = final_apps_dict.get(app_name, 'unknown')
                print(f"  - {app_name} (state: {state})")
            print("These apps may be in 'deleting' state and will be cleaned up automatically.")
        print()
    
    # Use all_results for final summary
    results = all_results
    
    # Print results
    print()
    print("=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)
    
    # Handle both old format (4-tuple) and new format (5-tuple) for backward compatibility
    successful = 0
    failed = 0
    skipped = 0
    verification_failed = 0
    
    for app_name, result_tuple in sorted(results.items()):
        # Handle both old and new result formats
        if len(result_tuple) == 5:
            success, exit_code, stdout, stderr, category = result_tuple
        else:
            # Old format: (success, exit_code, stdout, stderr)
            success, exit_code, stdout, stderr = result_tuple
            category = "UNKNOWN"
        
        if success:
            if category == "ALREADY_DELETED":
                status = "⊘ SKIPPED"
                skipped += 1
            elif category == "VERIFICATION_FAILED":
                status = "⚠ VERIFY_FAIL"
                verification_failed += 1
                successful += 1  # Command succeeded but verification failed
            else:
                status = "✓ SUCCESS"
                successful += 1
        else:
            status = "✗ FAILED"
            failed += 1
        
        # Show category if available and meaningful
        category_display = f" [{category}]" if category and category != "SUCCESS" and category != "UNKNOWN" else ""
        print(f"{status:15} | Exit: {exit_code:3} | {app_name}{category_display}")
    
    print("=" * 80)
    print(f"Summary: {successful} successful, {failed} failed", end="")
    if skipped > 0:
        print(f", {skipped} skipped (already deleted)", end="")
    if verification_failed > 0:
        print(f", {verification_failed} verification failed", end="")
    print()
    print("=" * 80)
    
    # Calculate total script execution time
    script_end_time = time.time()
    total_script_time = script_end_time - script_start_time
    total_script_minutes = int(total_script_time // 60)  # Integer minutes
    total_script_seconds = int(total_script_time % 60)  # Remaining seconds
    
    # Count total apps deleted (successful deletions, excluding skipped)
    total_apps_deleted = successful  # This includes successful deletions across all iterations
    
    # Print final summary with total time
    print()
    print("=" * 80)
    print("SCRIPT EXECUTION SUMMARY")
    print("=" * 80)
    if total_script_minutes >= 1:
        print(f"{total_apps_deleted} app(s) deleted - cumulative across all iterations")
        print(f"Completed in {total_script_minutes} min {total_script_seconds} sec - script time")
    else:
        print(f"{total_apps_deleted} app(s) deleted - cumulative across all iterations")
        print(f"Completed in {total_script_seconds} sec - script time")
    print("=" * 80)
    print()
    
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


import { test, expect } from '@playwright/test';
import { PerformanceTracker } from './helpers/performance-tracker.js';
import fs from 'fs';
import path from 'path';

/**
 * Self Service App Launch from Store - Performance Test
 * 
 * PRODUCTION-READY for 1000+ users
 * 
 * IMPORTANT CONCEPTS:
 * 
 * 1. WAITING vs PAGE LOAD TIME:
 *    - We WAIT for pages to load BEFORE capturing metrics
 *    - The TIME IT TAKES to load is recorded as "totalLoadTime" by Performance API
 *    - Different users will have different load times (parallel execution, network variance)
 *    - Performance tracker captures this variance automatically
 * 
 * 2. SCRIPT RESPONSIBILITY:
 *    - Script ensures page is READY before perf.stop()
 *    - Script handles all UI interactions and waits
 *    - Script is NOT agnostic - it knows about the app flow
 * 
 * 3. PERFORMANCE TRACKER RESPONSIBILITY:
 *    - Tracker captures metrics when stop() is called
 *    - Tracker is agnostic to your app - works with ANY app
 *    - Tracker handles retries, validation, error recovery
 * 
 * Version: 2.0 (Production Scale)
 */

// ═══════════════════════════════════════════════════════════════════════════
// TIMEOUT CONFIGURATION (ADJUST THESE FOR YOUR ENVIRONMENT)
// ═══════════════════════════════════════════════════════════════════════════

const TIMEOUTS = {
    // ──────────────────────────────────────────────────────────────────────────
    // UI INTERACTION TIMEOUTS (How long to wait for elements/actions)
    // ──────────────────────────────────────────────────────────────────────────

    /**
     * ACTION: Timeout for clicking, filling, selecting elements
     * Use: await button.click({ timeout: TIMEOUTS.ACTION })
     * Recommendation: 20s is safe for high load, 10s for light load
     */
    ACTION: 180000, // 3 minutes

    /**
     * NAVIGATION: Timeout for page navigation to complete
     * Use: await page.goto(url, { timeout: TIMEOUTS.NAVIGATION })
     * Recommendation: 20s for slow networks, 10s for fast
     */
    NAVIGATION: 90000, // 1 minute 30 seconds

    /**
     * WAIT: Generic wait for elements to appear
     * Use: await element.waitFor({ state: 'visible', timeout: TIMEOUTS.WAIT })
     * Recommendation: 10s for most cases
     */
    WAIT: 90000, // 1 minute 30 seconds

    // ──────────────────────────────────────────────────────────────────────────
    // PAGE LOAD TIMEOUTS (How long to wait for browser load events)
    // ──────────────────────────────────────────────────────────────────────────

    /**
     * LOAD_STATE: Timeout for waitForLoadState('load')
     * This is CRITICAL for performance tracking!
     * Use: await page.waitForLoadState('load', { timeout: TIMEOUTS.LOAD_STATE })
     * 
     * WHY THIS MATTERS:
     * - Performance API only has complete data AFTER load event fires
     * - If page takes > this timeout, metrics will be incomplete
     * - Increase this for slow environments or high parallel load
     * 
     * Recommendation:
     * - 1-10 users: 15000 (15s)
     * - 100 users: 20000 (20s)
     * - 1000 users: 25000 (25s)
     */
    LOAD_STATE: 15000, // 15 seconds (adjust for scale!)

    /**
     * NETWORK_IDLE: Timeout for waitForLoadState('networkidle')
     * Waits until no network activity for 500ms
     * Use: await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NETWORK_IDLE })
     * 
     * NOTE: This is OPTIONAL and not required for performance tracking
     * Performance tracker only needs 'load' state, not 'networkidle'
     */
    NETWORK_IDLE: 20000, // 20 seconds

    // ──────────────────────────────────────────────────────────────────────────
    // APP-SPECIFIC TIMEOUTS (Your self-service app specific waits)
    // ──────────────────────────────────────────────────────────────────────────

    /**
     * DYNAMIC_VAR: Total timeout for dynamic variables to load
     * Your app has "Fetching values..." that can take minutes
     */
    DYNAMIC_VAR: 210000, // 3.5 minutes

    /**
     * DYNAMIC_VAR_CHECK_INTERVAL: How often to check if variables loaded
     */
    DYNAMIC_VAR_CHECK_INTERVAL: 30000, // 30 seconds

    /**
     * DYNAMIC_VAR_MAX_ITERATIONS: Max number of checks
     */
    DYNAMIC_VAR_MAX_ITERATIONS: 7, // 7 checks × 30s = 3.5 minutes

    // ──────────────────────────────────────────────────────────────────────────
    // SMALL WAITS (For UI stabilization)
    // ──────────────────────────────────────────────────────────────────────────

    SHORT_WAIT: 500,   // 0.5s - Brief pause for UI updates
    MEDIUM_WAIT: 1000, // 1s - Modal animations, dropdown opens
    LONG_WAIT: 2000,   // 2s - Page transitions, heavy renders


    STATUS_WAIT: 180000 // 3 minutes - Waiting for long-running operations (e.g. deployment)
};

// ═══════════════════════════════════════════════════════════════════════════
// APP CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════

const APP_CONFIG = {
    runbookName: 'vmpoweroff',
    excutionName: 'rb-poweroff-50-user',
    taskName: 'Task 1',
    operationType: 'VM Power Off',
    endpointPrefix: 'bg-pc2-150users-ep',
    scriptType: 'null', // Only relevant if operationType is 'Execute'
};

// ═══════════════════════════════════════════════════════════════════════════
// TEST USERS (Add more for scale testing)
// ═══════════════════════════════════════════════════════════════════════════

const users = [
    // {username: 'solution_user1@qa.nutanix.com', password: 'nutanix/4u'},
    // {username: 'solution_user2@qa.nutanix.com', password: 'nutanix/4u'},
    // {username: 'solution_user3@qa.nutanix.com', password: 'nutanix/4u'},
    // {username: 'solution_user4@qa.nutanix.com', password: 'nutanix/4u'},
    // {username: 'solution_user5@qa.nutanix.com', password: 'nutanix/4u'},
    // {username: 'solution_user6@qa.nutanix.com', password: 'nutanix/4u'},
    // {username: 'solution_user7@qa.nutanix.com', password: 'nutanix/4u'},
    // {username: 'solution_user8@qa.nutanix.com', password: 'nutanix/4u'},
    // {username: 'solution_user9@qa.nutanix.com', password: 'nutanix/4u'},
    // {username: 'solution_user10@qa.nutanix.com', password: 'nutanix/4u'}
    {username: 'solution_user11@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user12@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user13@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user14@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user15@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user16@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user17@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user18@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user19@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user20@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user21@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user22@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user23@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user24@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user25@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user26@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user27@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user28@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user29@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user30@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user31@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user32@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user33@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user34@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user35@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user36@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user37@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user38@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user39@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user40@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user41@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user42@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user43@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user44@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user45@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user46@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user47@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user48@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user49@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user50@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user51@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user52@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user53@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user54@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user55@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user56@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user57@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user58@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user59@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user60@qa.nutanix.com', password: 'nutanix/4u'}
/**    {username: 'solution_user61@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user62@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user63@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user64@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user65@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user66@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user67@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user68@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user69@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user70@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user71@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user72@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user73@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user74@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user75@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user76@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user77@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user78@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user79@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user80@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user81@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user82@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user83@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user84@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user85@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user86@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user87@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user88@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user89@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user90@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user91@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user92@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user93@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user94@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user95@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user96@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user97@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user98@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user99@qa.nutanix.com', password: 'nutanix/4u'},
    {username: 'solution_user100@qa.nutanix.com', password: 'nutanix/4u'} **/

    // Add more users for parallel execution:
    // { username: 'solution_user2@qa.nutanix.com', password: 'nutanix/4u' },
    // { username: 'solution_user3@qa.nutanix.com', password: 'nutanix/4u' },
    // ... up to 1000 users
];

// ═══════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * ╔════════════════════════════════════════════════════════════════════════════╗
 * ║                           CLASS: UserLogger                                ║
 * ║                      Per-User Test Execution Logging                       ║
 * ╚════════════════════════════════════════════════════════════════════════════╝
 * 
 * PURPOSE:
 *   Individual log file for each test user execution with timestamps and
 *   severity tracking. Data flows automatically to master aggregated log.
 * 
 * OUTPUT FILES:
 *   📄 Location: test-results/[Test-Name]/[User X].log
 *   📄 Format:  [timestamp] [LEVEL] message
 *   📄 Example: [2026-06-08T15:19:36.000Z] [INFO] ✓ Login successful
 * 
 * KEY FEATURES:
 *   ✓ Per-user isolation (each user in separate log file)
 *   ✓ Automatic sync to master.log (real-time aggregation)
 *   ✓ Dual output (file + console simultaneously)
 *   ✓ 5 severity levels: INFO | ERROR | WARN | DEBUG | STEP
 *   ✓ ISO 8601 timestamps for precise timing analysis
 * 
 * USAGE EXAMPLES:
 *   logger.info('✓ Login successful')
 *   logger.error('✗ Failed to click button')
 *   logger.warn('⚠ Element took longer to appear')
 *   logger.debug('Debug info for troubleshooting')
 *   logger.step('Enter username')  // → visual marker
 * 
 * ARCHITECTURE:
 *   UserLogger → individual log file
 *   UserLogger → MasterLogger.log() (sync)
 *   UserLogger → console.log() (display)
 */
class UserLogger {
    constructor(outputDir, userLabel, masterLogger = null) {
        this.outputDir = outputDir;
        this.userLabel = userLabel;
        this.masterLogger = masterLogger; // Reference to master logger for syncing
        this.logFile = path.join(outputDir, `${userLabel.replace(/[\[\]]/g, '')}.log`);
        
        // Ensure output directory exists before creating log file (fixes ENOENT error)
        // REASON: Playwright sometimes creates test folders lazily
        if (!fs.existsSync(outputDir)) {
            fs.mkdirSync(outputDir, { recursive: true });
        }
        
        // Create initial log file with header containing test metadata
        // This makes it easy to identify which user and when the test started
        const header = `\n${'='.repeat(80)}\nTest Log: ${new Date().toISOString()}\nUser: ${userLabel}\n${'='.repeat(80)}\n`;
        fs.writeFileSync(this.logFile, header);
    }

    /**
     * ┌──────────────────────────────────────────────────────────────────────┐
     * │ Internal Core Write Function                                         │
     * │ ───────────────────────────────────────────────────────────────────--│
     * │ Handles all log writes to user log AND master log (if available)     │
     * │ This is the single point where all logging decisions are made        │
     * └──────────────────────────────────────────────────────────────────────┘
     * 
     * @param {string} level   - Log level (INFO | ERROR | WARN | DEBUG | STEP)
     * @param {string} message - Message content to log
     * 
     * FLOW:
     *   1. Generate timestamp (ISO 8601)
     *   2. Format message: [timestamp] [level] message
     *   3. Append to user's individual log file
     *   4. IF masterLogger exists → sync entry to master.log
     *   5. Print to console for real-time visibility
     */
    _write(level, message) {
        const timestamp = new Date().toISOString();
        const logMessage = `[${timestamp}] [${level}] ${message}\n`;
        
        // ① Write to individual user log file
        fs.appendFileSync(this.logFile, logMessage);
        
        // ② Sync to master log if available (for aggregated cross-user view)
        if (this.masterLogger) {
            this.masterLogger.log(this.userLabel, level, message);
        }
        
        // ③ Also print to console for real-time visibility during test execution
        console.log(logMessage.trim());
    }

    /**
     * 📍 Log Level: INFO
     * Used for: General progress, successful operations, confirmations
     * Example: logger.info('✓ Dashboard loaded')
     */
    info(message) {
        this._write('INFO', message);
    }

    /**
     * ❌ Log Level: ERROR
     * Used for: Failures, exceptions, blocked operations
     * Example: logger.error('✗ Failed to login')
     */
    error(message) {
        this._write('ERROR', message);
    }

    /**
     * ⚠️  Log Level: WARN
     * Used for: Warnings, degraded states, unexpected but recoverable issues
     * Example: logger.warn('⚠ Modal still present')
     */
    warn(message) {
        this._write('WARN', message);
    }

    /**
     * 🔍 Log Level: DEBUG
     * Used for: Diagnostic info, verbose details for troubleshooting
     * Example: logger.debug('Frame URL: ' + url)
     */
    debug(message) {
        this._write('DEBUG', message);
    }

    /**
     * ➡️  Log Level: STEP
     * Used for: Test step markers, workflow progression indicators
     * Appearance: Displays with arrow (→) for easy visual scanning
     * Example: logger.step('Navigate to login page')
     * 
     * SPECIAL FEATURE: Step markers are primary navigation points in logs
     */
    step(stepName) {
        this._write('STEP', `→ ${stepName}`);
    }
}

/**
 * ╔════════════════════════════════════════════════════════════════════════════╗
 * ║                          CLASS: MasterLogger                               ║
 * ║                     Aggregated Cross-User Test Logging                     ║
 * ╚════════════════════════════════════════════════════════════════════════════╝
 * 
 * PURPOSE:
 *   Single aggregated log file containing entries from ALL users.
 *   Synchronized in real-time as each UserLogger writes entries.
 *   Ideal for cross-user analysis and timeline-based debugging.
 * 
 * OUTPUT FILES:
 *   📊 Location: test-results/master.log
 *   📊 Format:  [timestamp] [User X] [LEVEL] message
 *   📊 Scope:   All 18+ steps × All users in one file
 * 
 * DATA FLOW:
 *   User 1 Test          User 2 Test          User N Test
 *        ↓                    ↓                    ↓
 *   UserLogger 1       UserLogger 2       UserLogger N
 *        ↓                    ↓                    ↓
 *        └────────────────────┼────────────────────┘
 *                             ↓
 *                       MasterLogger
 *                             ↓
 *                     📊 master.log
 * 
 * KEY FEATURES:
 *   ✓ Single point of aggregation (no file conflicts)
 *   ✓ Real-time synchronization (entries sync as written)
 *   ✓ User context preserved (each entry tagged with user)
 *   ✓ Chronological ordering (timestamps for sequencing)
 *   ✓ Complete coverage (captures all 18+ steps for all users)
 * 
 * USE CASES:
 *   • Comparing user execution timelines
 *   • Finding patterns across users
 *   • Debugging parallel execution issues
 *   • Performance analysis per user
 *   • Cross-user error correlation
 */

class MasterLogger {
  /**
   * @param {string} testResultsDir - Directory where master.log will be created (e.g., "test-results")
   *
   * Behavior:
   *  - Ensures the directory exists.
   *  - If a previous master.log exists, deletes it to guarantee a fresh file for this run.
   *  - Writes a clear header to the new master.log (truncates/creates file).
   *
   * Notes:
   *  - Deleting the file first (fs.unlinkSync) guarantees no leftover content remains.
   *  - We use synchronous filesystem calls to keep ordering deterministic during test runs.
   *  - If your test runner spawns multiple Node processes that each construct MasterLogger,
   *    they will race to create/overwrite master.log. For multi-process runs prefer:
   *      • instantiate MasterLogger only once in a single orchestrator process, or
   *      • write per-worker master files (e.g., master.<worker>.log) and merge them after the run.
   */
  constructor(testResultsDir) {
    this.testResultsDir = testResultsDir;
    this.logFile = path.join(testResultsDir, 'master.log');

    // Ensure the parent directory exists. Playwright/CI may not create it automatically.
    if (!fs.existsSync(testResultsDir)) {
      fs.mkdirSync(testResultsDir, { recursive: true });
    }

    // If a previous master.log exists, remove it so the new run starts with a clean file.
    // This avoids cases where writeFileSync with 'w' might not be sufficient due to
    // cross-process races or leftover file metadata in some environments.
    try {
      if (fs.existsSync(this.logFile)) {
        fs.unlinkSync(this.logFile);
      }
    } catch (err) {
      // Best-effort: log to console but continue (we still attempt to write the header).
      // Do not throw here because logging should not block test execution.
      console.warn(`MasterLogger: failed to remove existing master.log: ${err.message}`);
    }

    // Write a clear header to the new master.log. Using writeFileSync creates the file.
    // We intentionally do not use append here because we want a fresh file.
    const header = [
      ''.padStart(100, '='),
      'MASTER TEST LOG',
      `Test Run: ${new Date().toISOString()}`,
      ''.padStart(100, '='),
      ''
    ].join('\n');

    // Create the file and write the header (synchronous for determinism).
    fs.writeFileSync(this.logFile, header, { flag: 'w' });
  }

  /**
   * Append a single log entry to master.log.
   * Keep each entry to a single line to improve atomicity on POSIX filesystems.
   */
  log(userLabel, level, message) {
    const timestamp = new Date().toISOString();
    const entry = `[${timestamp}] ${userLabel} [${level}] ${message}\n`;
    fs.appendFileSync(this.logFile, entry);
  }

  info(userLabel, message) { this.log(userLabel, 'INFO', message); }
  error(userLabel, message) { this.log(userLabel, 'ERROR', message); }
  warn(userLabel, message) { this.log(userLabel, 'WARN', message); }
  step(userLabel, stepName) { this.log(userLabel, 'STEP', `→ ${stepName}`); }
}

/**
 * Helper: Dismiss modal inside iframe robustly
 * Returns: true if dismissed or not present, false if failed
 */
async function dismissIframeModal(page, iframeSelector, options = {}) {
    const {
        appearTimeout = 8000,
        clickTimeout = 5000,
        hiddenTimeout = 10000,
        diagDir = null,
        userLabel = 'user'
    } = options;

    try {
        const iframeLocator = page.frameLocator(iframeSelector);
        await iframeLocator.locator('body').waitFor({
            state: 'visible',
            timeout: Math.min(appearTimeout, 3000)
        }).catch(() => { });

        const modalRoot = iframeLocator.locator('div[role="dialog"], .welcome-modal, .modal, [data-test="welcome-modal"]');
        await modalRoot.waitFor({ state: 'visible', timeout: appearTimeout }).catch(() => { });

        const closeButtonCandidates = [
            iframeLocator.getByRole('button', { name: /close|×|Close/i }),
            iframeLocator.locator('button.close, button[aria-label="Close"], .modal-close, .close-button'),
            iframeLocator.locator('[data-test="modal-close"], [data-test="close-button"]')
        ];

        for (let attempt = 1; attempt <= 3; attempt++) {
            let clicked = false;
            for (const candidate of closeButtonCandidates) {
                if (await candidate.isVisible({ timeout: 1000 }).catch(() => false)) {
                    try {
                        const canClick = await candidate.click({ trial: true }).then(() => true).catch(() => false);
                        if (canClick) {
                            await candidate.click({ timeout: clickTimeout });
                            await modalRoot.waitFor({ state: 'hidden', timeout: hiddenTimeout }).catch(() => { });
                            await page.locator('.modal-backdrop, .overlay, .loading-overlay').waitFor({
                                state: 'hidden',
                                timeout: 5000
                            }).catch(() => { });
                            clicked = true;
                            break;
                        }
                    } catch (e) {
                        // Swallow, try next candidate
                    }
                }
            }

            if (clicked) return true;
            await page.waitForTimeout(500 * attempt);
        }

        const modalVisible = await page.frameLocator(iframeSelector)
            .locator('div[role="dialog"], .welcome-modal, .modal')
            .isVisible()
            .catch(() => false);

        if (!modalVisible) return true;

        // Save diagnostics on failure
        if (diagDir) {
            try {
                const ts = Date.now();
                const safeLabel = String(userLabel).replace(/[\[\]]/g, '');
                const screenshotPath = path.join(diagDir, `modal-dismiss-failure-${safeLabel}-${ts}.png`);
                await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => { });
                const htmlPath = path.join(diagDir, `modal-dismiss-failure-${safeLabel}-${ts}.html`);
                fs.writeFileSync(htmlPath, await page.content());
                console.log(`Modal dismissal diagnostics saved: ${screenshotPath}, ${htmlPath}`);
            } catch (diagErr) {
                console.warn('Failed to write modal diagnostics:', diagErr.message);
            }
        }

        return false;
    } catch (err) {
        return false;
    }
}


/**
 * HELPER: Wait for element and record timing
 * Use this to track UI responsiveness (how long until button is clickable, input is fillable, etc.)
 * 
 * Example:
 *   await trackAndClick(page.locator('#submit'), 'Submit button', perf);
 */
async function trackAndClick(locator, description, perf, options = {}) {
    const timeout = options.timeout || TIMEOUTS.ACTION;
    const waitStart = Date.now();

    try {
        await locator.click({ timeout, ...options });
        const waitTime = Date.now() - waitStart;
        perf.recordElementWait('click', description, waitTime, false);
    } catch (error) {
        const waitTime = Date.now() - waitStart;
        perf.recordElementWait('click', description, waitTime, waitTime >= timeout);
        throw error;
    }
}

async function trackAndFill(locator, description, value, perf, options = {}) {
    const timeout = options.timeout || TIMEOUTS.ACTION;
    const waitStart = Date.now();

    try {
        await locator.fill(value, { timeout, ...options });
        const waitTime = Date.now() - waitStart;
        perf.recordElementWait('fill', description, waitTime, false);
    } catch (error) {
        const waitTime = Date.now() - waitStart;
        perf.recordElementWait('fill', description, waitTime, waitTime >= timeout);
        throw error;
    }
}

/**
 * CRITICAL HELPER: Wait for page load before capturing performance metrics
 * 
 * This ensures the browser's Performance API has complete data.
 * Call this BEFORE perf.stop() in every step that loads/navigates a page.
 * 
 * @param {Page} page - Playwright page object
 * @param {string} stepName - Name of step for logging
 * @param {PerformanceTracker} perf - Performance tracker instance (unused, kept for compatibility)
 * @param {object} options - Optional { timeout, frameName }
 */
async function ensurePageLoaded(page, stepName, perf, options = {}) {
    const timeout = options.timeout || TIMEOUTS.LOAD_STATE;
    const frameName = options.frameName;

    try {
        // Get target (page or frame)
        let target = page;
        if (frameName) {
            const frame = page.frame({ name: frameName });
            if (frame) {
                target = frame;
            } else {
                console.warn(`⚠️ Frame "${frameName}" not found for ${stepName}, using main page`);
            }
        }

        // CRITICAL: Wait for load event (Performance API needs this!)
        await target.waitForLoadState('load', { timeout }).catch(err => {
            console.warn(`⚠️ ${stepName} - Load timeout: ${err.message}`);
        });

        // Optional: Wait for network idle (smoother, but not required for perf tracking)
        await target.waitForLoadState('networkidle', {
            timeout: TIMEOUTS.NETWORK_IDLE
        }).catch(() => {
            // Network idle timeout is acceptable
        });

    } catch (error) {
        console.error(`❌ ensurePageLoaded failed for ${stepName}: ${error.message}`);
        // Don't throw - let performance tracker handle it
    }
}

// ╔════════════════════════════════════════════════════════════════════════════╗
// ║                           TEST SUITE SETUP                                 ║
// ║                  Self Service - App Launch Performance Test                ║
// ╚════════════════════════════════════════════════════════════════════════════╝
//
// ╭─ LOGGING ARCHITECTURE ──────────────────────────────────────────────────────╮
// │                                                                             │
// │  LEVEL 1: Individual User Logs                                             │
// │  ├─ File: test-results/[Test-Name]/[User X].log                           │
// │  ├─ Scope: Single user execution with all 18+ steps                        │
// │  └─ Purpose: Detailed per-user timeline and troubleshooting               │
// │                                                                             │
// │  LEVEL 2: Master Aggregated Log                                            │
// │  ├─ File: test-results/master.log                                         │
// │  ├─ Scope: All users × all 18+ steps in chronological order              │
// │  └─ Purpose: Cross-user analysis, pattern detection, timeline view        │
// │                                                                             │
// │  SYNCHRONIZATION:                                                          │
// │  ├─ UserLogger._write() → User's individual log file                      │
// │  ├─ UserLogger._write() → MasterLogger.log() [automatic sync]             │
// │  ├─ MasterLogger.log() → master.log                                        │
// │  └─ Result: Real-time dual-log synchronization                            │
// │                                                                             │
// ╰─────────────────────────────────────────────────────────────────────────────╯
// 
// ╭─ DATA FLOW ─────────────────────────────────────────────────────────────────╮
// │                                                                             │
// │   Parallel Test Execution (Multiple Users)                                 │
// │                                                                             │
// │   User 1              User 2              User 3        ...      User N    │
// │     │                  │                   │                      │        │
// │     ├─→ Step 1         ├─→ Step 1        ├─→ Step 1   ...      ├─→ Step 1 │
// │     ├─→ Step 2         ├─→ Step 2        ├─→ Step 2   ...      ├─→ Step 2 │
// │     └─→ ...            └─→ ...           └─→ ...      ...      └─→ ...    │
// │     │                  │                   │                      │        │
// │     UserLogger         UserLogger          UserLogger  ...      UserLogger │
// │     │                  │                   │                      │        │
// │     └──────────────────┼───────────────────┼──────────────────────┘        │
// │                        ↓                                                   │
// │                  MasterLogger (Single)                                     │
// │                        ↓                                                   │
// │                  master.log (Aggregated)                                   │
// │                                                                             │
// ╰─────────────────────────────────────────────────────────────────────────────╯
// 
// ╭─ KEY DESIGN PRINCIPLES ────────────────────────────────────────────────────╮
// │                                                                             │
// │  ✓ Single Responsibility   - Each logger has one job                       │
// │  ✓ Real-Time Sync          - Master updated instantly                      │
// │  ✓ No Data Loss            - All entries captured                          │
// │  ✓ User Context Preserved  - Each entry labeled with user                  │
// │  ✓ Chronological Ordering  - ISO timestamps for sequencing                 │
// │  ✓ Easy Debugging          - Separate view + aggregated view               │
// │  ✓ Scalable               - Works with 1 to 1000+ users                   │
// │                                                                             │
// ╰─────────────────────────────────────────────────────────────────────────────╯

test.describe('Self Service - App Launch from Store Performance Test', () => {
    // Master logger instance - shared across all user tests
    // Created once on first user execution and reused for all subsequent users
    // This ensures all users write to the same aggregated master.log file
    let masterLogger = null;
    
    const userMetrics = {};
    for (let i = 0; i < users.length; i++) {
        test(`User ${i + 1}: App Deployment Test`, async ({ page }, testInfo) => {
            test.setTimeout(600_000); // 10 minutes total test timeout

            const USERNAME = users[i].username;
            const PASSWORD = users[i].password;
            const userLabel = `[User ${i + 1}]`;
            const USERINDEX = USERNAME.replace("solution_user", "").split("@")[0];
            const ENDPOINTNAME = `${APP_CONFIG.endpointPrefix}${USERINDEX}`;
            console.log(USERINDEX);

            // ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
            // ┃ STEP 0: Initialize Master Logger (First User Only)              ┃
            // ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
            // ┃ Purpose: Create shared aggregation point for all users          ┃
            // ┃ Timing:  Once only, on first user test execution               ┃
            // ┃ Result:  All users → MasterLogger → master.log                 ┃
            // ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

            if (!masterLogger) {
                const testResultsDir = path.dirname(testInfo.outputDir);
                masterLogger = new MasterLogger(testResultsDir);
                console.log(`📋 Master logger created at: ${path.join(testResultsDir, 'master.log')}`);
            }

            const timestamp = Date.now();
            const uniqueAppName = `${APP_CONFIG.appNamePrefix}-user${i + 1}-${timestamp}`;

            // ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
            // ┃ STEP 1: Initialize User Logger                                  ┃
            // ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
            // ┃                                                                 ┃
            // ┃ DUAL-LOG ARCHITECTURE:                                          ┃
            // ┃                                                                 ┃
            // ┃ 📄 Individual Log                 📊 Master Log                 ┃
            // ┃ ├─ File: [User X].log            ├─ File: master.log           ┃
            // ┃ ├─ Scope: Single user            ├─ Scope: All users           ┃
            // ┃ ├─ Location: User's folder       ├─ Location: test-results/    ┃
            // ┃ └─ Purpose: Detailed view        └─ Purpose: Aggregated view   ┃
            // ┃                                                                 ┃
            // ┃ SYNCHRONIZATION FLOW:                                           ┃
            // ┃ UserLogger entry → User's log file + MasterLogger.log()        ┃
            // ┃                                                                 ┃
            // ┃ PARAMETERS:                                                     ┃
            // ┃ • outputDir    : User's test result directory                  ┃
            // ┃ • userLabel    : [User X] identifier for tagging               ┃
            // ┃ • masterLogger : Reference for real-time sync                  ┃
            // ┃                                                                 ┃
            // ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

            const logger = new UserLogger(testInfo.outputDir, userLabel, masterLogger);
            logger.info(`Starting test for user: ${USERNAME}`);
            logger.info(`Output directory: ${testInfo.outputDir}`);

            // ═══════════════════════════════════════════════════════════════════════
            // INITIALIZE PERFORMANCE TRACKER
            // ═══════════════════════════════════════════════════════════════════════

            const perf = new PerformanceTracker(page, testInfo, userLabel, {
                debugMode: true, // Set to false for 100+ users to reduce log noise
                maxRetries: 3,
                retryDelayMs: 1500,
                loadStateTimeout: TIMEOUTS.LOAD_STATE, // Use script timeout
                frameDetectionTimeout: 10000,
                slowRequestThreshold: 2000,
            });

            // ═══════════════════════════════════════════════════════════════════════
            // STEP: LOGIN
            // ═══════════════════════════════════════════════════════════════════════

            await test.step(`${userLabel} Login`, async () => {

                // ─────────────────────────────────────────────────────────────────────
                // Step 01: Navigate to login page
                // ─────────────────────────────────────────────────────────────────────
                perf.start('Step 01 - Navigate to login page');
                logger.step('Navigate to login page');
                try {
                    await page.goto('https://iam.nconprem-10-122-152-117.ccpnx.com/ui/iam/login?', {
                        timeout: TIMEOUTS.NAVIGATION
                    });

                    // CRITICAL: Wait for page to load before capturing metrics
                    await ensurePageLoaded(page, 'Step 01', perf);
                    logger.info('✓ Login page loaded successfully');

                } catch (error) {
                    logger.error(`✗ Login navigation failed: ${error.message}`);
                    await perf.captureFailure('Step 01 - Navigate to login');
                    throw error;
                } finally {
                    await perf.stop(); // Performance tracker captures metrics here
                }

                // ─────────────────────────────────────────────────────────────────────
                // Step 02: Enter username
                // ─────────────────────────────────────────────────────────────────────
                perf.start('Step 02 - Enter username');
                logger.step(`Enter username: ${USERNAME}`);
                try {
                    // TRACK: Record how long it takes for input to become fillable
                    await trackAndFill(
                        page.locator('[data-test="loginInputUsername"]'),
                        'Username input field',
                        USERNAME,
                        perf,
                        { timeout: TIMEOUTS.ACTION }
                    );
                    logger.info('✓ Username entered');
                    // No page load here, just form fill
                } catch (error) {
                    logger.error(`✗ Failed to enter username: ${error.message}`);
                    await perf.captureFailure('Step 02 - Enter username');
                    throw error;
                } finally {
                    await perf.stop();
                }

                // ─────────────────────────────────────────────────────────────────────
                // Step 03: Enter password
                // ─────────────────────────────────────────────────────────────────────
                perf.start('Step 03 - Enter password');
                logger.step('Enter password');
                try {
                    await trackAndFill(
                        page.locator('[data-test="loginInputPassword"]'),
                        'Password input field',
                        PASSWORD,
                        perf,
                        { timeout: TIMEOUTS.ACTION }
                    );
                    logger.info('✓ Password entered');
                    // No page load here, just form fill
                } catch (error) {
                    logger.error(`✗ Failed to enter password: ${error.message}`);
                    await perf.captureFailure('Step 03 - Enter password');
                    throw error;
                } finally {
                    await perf.stop();
                }

                // ─────────────────────────────────────────────────────────────────────
                // Step 04: Submit and wait for dashboard
                // ─────────────────────────────────────────────────────────────────────
                perf.start('Step 04 - Submit and wait for dashboard page');
                logger.step('Submit login form');
                try {
                    // TRACK: Record button click responsiveness
                    await trackAndClick(
                        page.locator('[data-test="loginButtonSubmit"]'),
                        'Login submit button',
                        perf,
                        { timeout: TIMEOUTS.ACTION }
                    );

                    // CRITICAL: Wait for new page to load
                    await ensurePageLoaded(page, 'Step 04', perf);
                    logger.info('✓ Dashboard loaded after login');

                } catch (error) {
                    logger.error(`✗ Failed to submit login: ${error.message}`);
                    await perf.captureFailure('Step 04 - Submit');
                    throw error;
                } finally {
                    await perf.stop();
                }
            });

            // ═══════════════════════════════════════════════════════════════════════
            // STEP: DISMISS TOUR
            // ═══════════════════════════════════════════════════════════════════════

            await test.step(`${userLabel} Dismiss tour`, async () => {
                perf.start('Step 05 - Dismiss tour if present');
                logger.step('Dismiss tour if present');
                try {
                    const skipTour = page.getByRole('button', { name: /skip tour/i });

                    await Promise.race([
                        skipTour.waitFor({ state: 'visible', timeout: TIMEOUTS.WAIT }),
                        page.waitForTimeout(1500)
                    ]).catch(() => null);

                    const canClick = await skipTour.click({ trial: true })
                        .then(() => true)
                        .catch(() => false);

                    if (canClick) {
                        await trackAndClick(
                            skipTour,
                            'Skip tour button',
                            perf,
                            { timeout: TIMEOUTS.ACTION }
                        );
                        await page.waitForTimeout(TIMEOUTS.SHORT_WAIT);
                        logger.info('✓ Tour dismissed');
                    } else {
                        logger.info('ℹ Tour not present');
                    }

                    // Wait for any navigation to settle
                    await page.waitForLoadState('networkidle', {
                        timeout: TIMEOUTS.NETWORK_IDLE
                    }).catch(() => { });

                } catch (error) {
                    logger.error(`✗ Failed to dismiss tour: ${error.message}`);
                    await perf.captureFailure('Step 05 - Dismiss tour');
                    throw error;
                } finally {
                    await perf.stop();
                }
            });

            // ═══════════════════════════════════════════════════════════════════════
            // STEP: NAVIGATE TO SELF SERVICE
            // ═══════════════════════════════════════════════════════════════════════

            await test.step(`${userLabel} Navigate to Self Service`, async () => {

                // ─────────────────────────────────────────────────────────────────────
                // Step 06: Click Global Overview and Self Service
                // ─────────────────────────────────────────────────────────────────────
                perf.start('Step 06 - Click on Global Overview and select Self Service');
                logger.step('Navigate to Self Service');
                try {
                    await trackAndClick(
                        page.getByLabel('App - Global Overview selected').getByText('Global Overview'),
                        'Global Overview menu',
                        perf,
                        { timeout: TIMEOUTS.ACTION }
                    );

                    await trackAndClick(
                        page.getByLabel('Cloud Manager - Self Service'),
                        'Self Service menu item',
                        perf,
                        { timeout: TIMEOUTS.ACTION }
                    );

                    // CRITICAL: Wait for iframe to load
                    // This step loads a new iframe, must wait for it
                    await page.waitForLoadState('networkidle', {
                        timeout: TIMEOUTS.NETWORK_IDLE
                    }).catch(() => { });

                    // Wait for iframe to be present
                    await page.locator('iframe[name="ch-nc_self_service"]').waitFor({
                        state: 'attached',
                        timeout: TIMEOUTS.WAIT
                    });
                    logger.info('✓ Self Service iframe loaded');

                } catch (error) {
                    logger.error(`✗ Failed to navigate to Self Service: ${error.message}`);
                    await perf.captureFailure('Step 06 - Navigate to Self Service');
                    throw error;
                } finally {
                    await perf.stop();
                }

                // ─────────────────────────────────────────────────────────────────────
                // Step 07: Dismiss Welcome Modal in iframe
                // ─────────────────────────────────────────────────────────────────────
                perf.start('Step 07 - Dismiss Welcome Modal inside iframe', {
                    frameName: 'ch-nc_self_service'
                });
                logger.step('Dismiss welcome modal');
                try {
                    const selfServiceIframe = page.locator('iframe[name="ch-nc_self_service"]');
                    await expect(selfServiceIframe).toBeVisible({
                        timeout: TIMEOUTS.NAVIGATION
                    });

                    const diagDir = testInfo?.outputDir ? path.dirname(testInfo.outputDir) : process.cwd();
                    const dismissed = await dismissIframeModal(page, 'iframe[name="ch-nc_self_service"]', {
                        appearTimeout: 8000,
                        clickTimeout: 5000,
                        hiddenTimeout: 10000,
                        diagDir,
                        userLabel
                    });

                    if (!dismissed) {
                        logger.warn('Welcome modal may still be present');
                    } else {
                        logger.info('✓ Welcome modal dismissed');
                    }

                    // Wait for frame content to be visible
                    const selfServiceFrame = selfServiceIframe.contentFrame();
                    if (selfServiceFrame) {
                        const welcomeText = selfServiceFrame.getByText('Welcome to Self Service');
                        const deployText = selfServiceFrame.getByText('Deploy and manage');

                        await Promise.race([
                            welcomeText.waitFor({ state: 'visible', timeout: TIMEOUTS.WAIT }),
                            deployText.waitFor({ state: 'visible', timeout: TIMEOUTS.WAIT }),
                        ]).catch(() => {
                            logger.debug('Welcome message not found');
                        });
                    }

                    // CRITICAL: Ensure iframe is loaded
                    await ensurePageLoaded(page, 'Step 07', perf, {
                        frameName: 'ch-nc_self_service'
                    });

                } catch (error) {
                    logger.error(`✗ Failed to dismiss modal: ${error.message}`);
                    await perf.captureFailure('Step 07 - Dismiss modal');
                    throw error;
                } finally {
                    await perf.stop();
                }
            });

            // ═══════════════════════════════════════════════════════════════════════
            // STEP: DISMISS WELCOME MODAL (Legacy step)
            // ═══════════════════════════════════════════════════════════════════════

            await test.step(`${userLabel} Dismiss Welcome Modal`, async () => {
                perf.start('Step 08 - Dismiss Welcome Modal (legacy)', {
                    frameName: 'ch-nc_self_service'
                });
                logger.step('Dismiss welcome modal (legacy)');
                try {
                    const diagDir = testInfo?.outputDir ? path.dirname(testInfo.outputDir) : process.cwd();
                    await dismissIframeModal(page, 'iframe[name="ch-nc_self_service"]', {
                        appearTimeout: 8000,
                        clickTimeout: 5000,
                        hiddenTimeout: 10000,
                        diagDir,
                        userLabel
                    });
                    logger.info('✓ Welcome modal dismissed (legacy)');
                } catch (error) {
                    logger.error(`✗ Failed to dismiss legacy modal: ${error.message}`);
                    await perf.captureFailure('Step 08 - Dismiss modal');
                    throw error;
                } finally {
                    await perf.stop();
                }
            });

            // ═══════════════════════════════════════════════════════════════════════
            // STEP: NAVIGATE TO RUNBOOKS
            // ═══════════════════════════════════════════════════════════════════════

            await test.step(`${userLabel} Navigate to Runbooks`, async () => {
                perf.start('Step 09 - Click on Runbooks in Self Service', { frameName: 'ch-nc_self_service' });
                logger.step('Navigate to Runbooks');
                try {
                    const selfServiceFrame = page.frame({ name: 'ch-nc_self_service' });

                    await trackAndClick(
                        selfServiceFrame.getByRole('link', { name: 'Runbooks', exact: true }),
                        'Runbooks link',
                        perf,
                        { timeout: TIMEOUTS.ACTION }
                    );

                    const runbooksHeader = selfServiceFrame.locator('h1:has-text("Runbooks")');
                    await runbooksHeader.waitFor({ state: 'visible', timeout: TIMEOUTS.WAIT });

                    // CRITICAL: Wait for runbooks page to load
                    await ensurePageLoaded(page, 'Step 09 - Navigate to Runbooks', perf, {
                        frameName: 'ch-nc_self_service'
                    });

                    logger.info('✓ Runbooks page loaded');
                    // Optional: log URL for debugging
                    console.log('Runbooks frame URL:', selfServiceFrame.url());
                } catch (error) {
                    logger.error(`✗ Failed to navigate to Runbooks: ${error.message}`);
                    await perf.captureFailure('Step 09 - Navigate to Runbooks');
                    throw error;
                } finally {
                    await perf.stop();
                }
            });

            // ═══════════════════════════════════════════════════════════════════════
            // STEP: SEARCH FOR RUNBOOK
            // ═══════════════════════════════════════════════════════════════════════

            await test.step(`${userLabel} Search for Runbook`, async () => {
                perf.start('Step 10 - Search for Runbook in Store', {
                    frameName: 'ch-nc_self_service'
                });
                logger.step(`Search for runbook: ${APP_CONFIG.runbookName}`);
                try {
                    const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
                    const searchBox = selfServiceFrame.getByPlaceholder('Type here to apply filters');

                    const searchTerm = APP_CONFIG.runbookName;
                    await searchBox.fill(searchTerm, { timeout: TIMEOUTS.ACTION });
                    await searchBox.press('Enter');

                    // CRITICAL: Wait for any loading to complete after search
                    await ensurePageLoaded(page, 'Step 10', perf, {
                        frameName: 'ch-nc_self_service'
                    });

                    logger.info(`✓ Search for runbook "${searchTerm}" completed`);

                } catch (error) {
                    logger.error(`✗ Failed to search for runbook: ${error.message}`);
                    await perf.captureFailure('Step 10 - Search for Runbook');
                    throw error;
                } finally {
                    await perf.stop();
                }
            });

            // ═══════════════════════════════════════════════════════════════════════
            // STEP: SELECT RUNBOOK
            // ═══════════════════════════════════════════════════════════════════════

            await test.step(`${userLabel} Select Runbook`, async () => {
                perf.start('Step 11 - Select Runbook from search results', {
                    frameName: 'ch-nc_self_service'
                });
                logger.step(`Select runbook: ${APP_CONFIG.runbookName}`);
                try {
                    const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
                    const runbookLink = selfServiceFrame.getByRole('link', { name: APP_CONFIG.runbookName, exact: true });

                    await runbookLink.waitFor({ state: 'visible', timeout: TIMEOUTS.WAIT });
                    await runbookLink.click({ timeout: TIMEOUTS.ACTION });

                    // CRITICAL: Wait for runbook details page to load
                    await ensurePageLoaded(page, 'Step 11', perf, {
                        frameName: 'ch-nc_self_service'
                    });

                    logger.info(`✓ Selected runbook "${APP_CONFIG.runbookName}" successfully`);

                } catch (error) {
                    logger.error(`✗ Failed to select runbook: ${error.message}`);
                    await perf.captureFailure('Step 11 - Select Runbook');
                    throw error;
                } finally {
                    await perf.stop();
                }
            });

            // ═══════════════════════════════════════════════════════════════════════
            // STEP: CLICK ON TASK
            // ═══════════════════════════════════════════════════════════════════════

            await test.step(`${userLabel} Click on Task`, async () => {
                perf.start('Step 12 - Click on Task', {
                    frameName: 'ch-nc_self_service'
                });
                logger.step(`Click on task: ${APP_CONFIG.taskName}`);
                try {
                    const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
                    const taskNode = selfServiceFrame.locator(
                        `g.taskNode:has(text:has-text("${APP_CONFIG.taskName}"))`
                    );
                    await taskNode.click({ timeout: TIMEOUTS.ACTION });

                    // CRITICAL: Wait for task details page to load
                    await ensurePageLoaded(page, 'Step 12 - Click on Task', perf, {
                        frameName: 'ch-nc_self_service'
                    });

                    logger.info(`✓ Clicked on task "${APP_CONFIG.taskName}" successfully`);

                } catch (error) {
                    logger.error(`✗ Failed to click on task: ${error.message}`);
                    await perf.captureFailure('Step 12 - Click on Task');
                    throw error;
                } finally {
                    await perf.stop();
                }
            });

            // ═══════════════════════════════════════════════════════════════════════
            // STEP: SELECT OPERATION
            // ═══════════════════════════════════════════════════════════════════════      

            await test.step(`${userLabel} Select Operation`, async () => {
                perf.start('Step 13 - Select Operation', {
                    frameName: 'ch-nc_self_service'
                });
                logger.step(`Select operation: ${APP_CONFIG.operationType}`);
                try {
                    const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
                    const operationTypeDropdown = selfServiceFrame.locator("[id='task-type-selector']");

                    await expect(operationTypeDropdown).toBeVisible({ timeout: TIMEOUTS.WAIT });
                    await operationTypeDropdown.click({ timeout: TIMEOUTS.ACTION });

                    const operationOption = selfServiceFrame.locator(`//*[text()='${APP_CONFIG.operationType}']/parent::*[@role='option']`);
                    await expect(operationOption).toBeVisible({ timeout: TIMEOUTS.WAIT });
                    await operationOption.click({ timeout: TIMEOUTS.ACTION });

                    // CRITICAL: Wait for any loading to complete after selecting operation
                    await ensurePageLoaded(page, 'Step 13 - Select Operation', perf, {
                        frameName: 'ch-nc_self_service'
                    });

                    logger.info(`✓ Selected operation "${APP_CONFIG.operationType}" successfully`);

                } catch (error) {
                    logger.error(`✗ Failed to select operation: ${error.message}`);
                    await perf.captureFailure('Step 13 - Select Operation');
                    throw error;
                } finally {
                    await perf.stop();
                }
            });

            console.log(`user${USERINDEX} successfully completed the above steps`)

            // ══════════════════════════════════════════════════════════════════════
            // STEP: SELECT SCRIPT TYPE AND ENTER SCRIPT (Only for Execute)
            // ══════════════════════════════════════════════════════════════════════

            if (APP_CONFIG.operationType === 'Execute') {
                await test.step(`${userLabel} Select Script Type`, async () => {
                    perf.start('Step 13b - Select Script Type', {
                        frameName: 'ch-nc_self_service'
                    });
                    logger.step(`Select script type: ${APP_CONFIG.scriptType}`);
                    try {
                        const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
                        const scriptTypeDropdown = selfServiceFrame.locator("[id='script-type']");

                        await expect(scriptTypeDropdown).toBeVisible({ timeout: TIMEOUTS.WAIT });
                        await expect(scriptTypeDropdown).toBeEnabled({ timeout: TIMEOUTS.WAIT });
                        await scriptTypeDropdown.click({ timeout: TIMEOUTS.ACTION });

                        const scriptTypeOption = selfServiceFrame.locator("//*[@class='label-wrapper' and text()='Shell']")
                        await expect(scriptTypeDropdown).toBeVisible({ timeout: TIMEOUTS.WAIT });
                        await scriptTypeDropdown.click({ timeout: TIMEOUTS.ACTION });

                    // CRITICAL: Wait for any loading to complete after selecting endpoint
                    await ensurePageLoaded(page, 'Step 13b - Select Endpoint', perf, {
                        frameName: 'ch-nc_self_service'
                    });

                    } catch (error) {
                        logger.error(`✗ Failed to select script type: ${error.message}`);
                        await perf.captureFailure('Step 13b - Select Script Type');
                        throw error;
                    } finally {
                        await perf.stop();
                    }
                });
            }

            // ═══════════════════════════════════════════════════════════════════════
            // STEP: SAVE RUNBOOK
            // ═══════════════════════════════════════════════════════════════════════
            await test.step(`${userLabel} Save Runbook`, async () => {
            perf.start('Step 14 - Save Runbook', { frameName: 'ch-nc_self_service' });
            logger.step('Save runbook configuration');
            try {
                const selfServiceFrame = page.frame({ name: 'ch-nc_self_service' });
                const saveButton = selfServiceFrame.getByRole('button', { name: 'Save' });

                await expect(saveButton).toBeVisible({ timeout: TIMEOUTS.WAIT });
                await expect(saveButton).toBeEnabled({ timeout: TIMEOUTS.WAIT });
                await saveButton.click({ timeout: TIMEOUTS.ACTION });

                await ensurePageLoaded(page, 'Step 15 - Save Runbook', perf, { frameName: 'ch-nc_self_service' });

                const successMessage = selfServiceFrame.locator("//*[@role='alert' and text()='Runbook saved!']");
                const clickHereLink = selfServiceFrame.getByRole('link', { name: 'Click here' });

                // 🔎 Dynamic wait until either success or link appears
                await expect.poll(async () => {
                if (await successMessage.isVisible().catch(() => false)) return 'success';
                if (await clickHereLink.isVisible().catch(() => false)) return 'link';
                return null;
                }, { timeout: TIMEOUTS.NAVIGATION }).toBeTruthy();

                // ✅ Handle whichever appeared
                if (await successMessage.isVisible().catch(() => false)) {
                logger.info('✓ Runbook saved successfully');
                } else {
                logger.info('ℹ Clicking "Click here" link');
                await clickHereLink.click({ timeout: TIMEOUTS.ACTION });
                }

                // ✅ Ensure Execute button is enabled
                const executeButton = selfServiceFrame.getByRole('button', { name: 'Execute' });
                await expect(executeButton).toBeEnabled({ timeout: TIMEOUTS.NAVIGATION });

                logger.info('✓ Execute button is enabled');
            } catch (error) {
                logger.error(`✗ Failed to save runbook: ${error.message}`);
                await perf.captureFailure('Step 14 - Save Runbook');
                throw error;
            } finally {
                await perf.stop();
            }
            });

            // ═══════════════════════════════════════════════════════════════════════
            // STEP: CLICK EXECUTE
            // ═══════════════════════════════════════════════════════════════════════
            await test.step(`${userLabel} Execute Runbook`, async () => {
                perf.start('Step 15 - Click Execute', {
                    frameName: 'ch-nc_self_service'
                });
                logger.step('Click execute button');
                try {
                    const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
                    const executeButton = selfServiceFrame.getByRole('button', { name: 'Execute' });

                    await expect(executeButton).toBeVisible({ timeout: TIMEOUTS.WAIT });
                    await expect(executeButton).toBeEnabled({ timeout: TIMEOUTS.WAIT });
                    await executeButton.click({ timeout: TIMEOUTS.ACTION });

                    // CRITICAL: Wait for any loading to complete after executing
                    await ensurePageLoaded(page, 'Step 16 - Click Execute', perf, {
                        frameName: 'ch-nc_self_service'
                    });

                    logger.info('✓ Execute button clicked successfully');

                } catch (error) {
                    logger.error(`✗ Failed to click execute button: ${error.message}`);
                    await perf.captureFailure('Step 15 - Click Execute');
                    throw error;
                } finally {
                    await perf.stop();
                }
            }); 

            // =══════════════════════════════════════════════════════════════════════
            // STEP: SELECT ENDPOINT, ENTER NAME & EXECUTE
            // ═══════════════════════════════════════════════════════════════════════
            await test.step(`${userLabel} Handle Execute Modal`, async () => {
                perf.start('Step 16 - Select endpoint and execute', {
                    frameName: 'ch-nc_self_service'
                });
                logger.step(`Selecting the endpoint`);
                try {
                    // Get the frame reference (always await contentFrame)
                    const selfServiceFrame = await page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
                    if (!selfServiceFrame) throw new Error('Self Service frame not available');

                    // Locate the modal heading
                    const modalHeading = selfServiceFrame.locator(`//*[text()='Execute ${APP_CONFIG.runbookName}']`);
                    await expect(modalHeading).toBeVisible({ timeout: TIMEOUTS.WAIT });

                    // Locate the endpoint dropdown input
                    const endpointDropdown = selfServiceFrame.locator(
                    `//*[text()='Execute ${APP_CONFIG.runbookName}']/ancestor::*[@data-animation='pop-in']//*[@id='endpoint-picker']`
                    );
                    await expect(endpointDropdown).toBeVisible({ timeout: TIMEOUTS.WAIT });

                    // Step 1: Clear any existing text in the dropdown
                    await endpointDropdown.fill('');

                    // Step 2: Type the desired endpoint name
                    await endpointDropdown.fill(ENDPOINTNAME);

                    // Step 3: Wait for the matching option to appear and click it
                    const endpointOption = selfServiceFrame.locator(`//*[text()='${ENDPOINTNAME}']/ancestor::*[@role='option']`);
                    await expect(endpointOption).toBeVisible({ timeout: TIMEOUTS.WAIT });
                    await expect(endpointOption).toBeEnabled({ timeout: TIMEOUTS.WAIT });
                    await endpointOption.click({ timeout: TIMEOUTS.ACTION });

                    // Step 4: Enter execution name
                    const executionNameInput = selfServiceFrame.locator("[id='execution_name']");
                    await expect(executionNameInput).toBeVisible({ timeout:TIMEOUTS.NAVIGATION });
                    await executionNameInput.fill(`${APP_CONFIG.excutionName}${USERINDEX}`, {timeout: TIMEOUTS.ACTION});

                    // Finally, click the Execute button
                    const executeButton = selfServiceFrame.locator("[aria-label='Execute']");
                    await expect(executeButton).toBeVisible({ timeout: TIMEOUTS.WAIT });
                    await expect(executeButton).toBeEnabled({ timeout: TIMEOUTS.WAIT });
                    await executeButton.click({ timeout: TIMEOUTS.ACTION });

                    // CRITICAL: Wait for any loading to complete after confirming execution
                    await ensurePageLoaded(page, 'Step 16 - Select endpoint and execute', perf, {
                        frameName: 'ch-nc_self_service'
                    });

                    logger.info('✓ Selected endpoint and execution started successfully');

                } catch (error) {
                    logger.error(`✗ Failed to execute : ${error.message}`);
                    await perf.captureFailure('Step 16 - Select endpoint and execute');
                    throw error;
                } finally {
                    await perf.stop();
                }
            });

            // =══════════════════════════════════════════════════════════════════════
            // STEP: VERIFY EXECUTION & RETURN EXECUTION TIME
            // ═══════════════════════════════════════════════════════════════════════
            await test.step(`${userLabel} Verify Execution`, async () => {
                perf.start('Step 17 - Verify Execution Is Successful', {
                    frameName: 'ch-nc_self_service'
                });
                logger.step('Verify execution completion');
                try {
                    const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
                    const executionStatus = selfServiceFrame.locator(
                    "//*[text()='Status']/parent::*//div[text()='SUCCESS']"
                    );

                    // Wait until the SUCCESS element is visible
                    await expect(executionStatus).toBeVisible({ timeout: TIMEOUTS.STATUS_WAIT });

                    logger.info('✓ Execution verified - Status SUCCESS');

                } catch (error) {
                    logger.error(`✗ Failed to execute: ${error.message}`);
                    await perf.captureFailure('Step 17 - Verify Execution Is Successful');
                    throw error;
                } finally {
                    await perf.stop();
                }
            });

            // ═══════════════════════════════════════════════════════════════════════
            // STEP: PERFORMANCE SUMMARY
            // ═══════════════════════════════════════════════════════════════════════

            await test.step(`${userLabel} Performance Summary`, async () => {
                perf.start('Step 18 - Performance Summary');
                logger.step('Generate performance summary');
                try {
                    await perf.printSummary({ includeBrowserMetrics: true });
                    await perf.exportToJSON(`${userLabel.replace(/[\[\]]/g, '')}-metrics.json`);
                    logger.info('✓ Performance summary generated and exported');
                    logger.info(`Log file saved to: ${testInfo.outputDir}`);
                } catch (error) {
                    logger.error(`✗ Failed to generate summary: ${error.message}`);
                    await perf.captureFailure('Step 18 - Summary');
                    throw error;
                } finally {
                    await perf.stop();
                }
            });

            // Test completed successfully
            logger.info('✓ All steps completed successfully!');
            logger.info(`Total test execution time: ${Date.now() - timestamp}ms`);
        });
    }
    // End of user loop
    const metricsDir = path.join('test-results', 'execution-metrics');
    if (!fs.existsSync(metricsDir)) fs.mkdirSync(metricsDir, { recursive: true });

    const metricsFile = path.join(metricsDir, 'user-execution.json');
    fs.writeFileSync(metricsFile, JSON.stringify(Object.values(userMetrics), null, 2));

});

// ╔════════════════════════════════════════════════════════════════════════════╗
// ║                        TEST CLEANUP & AGGREGATION                         ║
// ║                  After All Tests Complete (All Users Done)                ║
// ╚════════════════════════════════════════════════════════════════════════════╝
//
// ╭─ EXECUTION TIMING ─────────────────────────────────────────────────────────╮
// │ • Triggered: After ALL test executions complete                            │
// │ • Scope: Global (once per test suite run)                                  │
// │ • Duration: After all users have finished                                  │
// ╰─────────────────────────────────────────────────────────────────────────────╯
//
// ╭─ RESPONSIBILITIES ─────────────────────────────────────────────────────────╮
// │                                                                             │
// │ 1️⃣  AGGREGATE METRICS                                                      │
// │    ├─ Read individual [User X]-metrics.json files                         │
// │    ├─ Collect performance data from all users                             │
// │    └─ Write consolidated all-users-metrics.json                           │
// │                                                                             │
// │ 2️⃣  FINALIZE LOGS                                                          │
// │    ├─ Check master.log exists                                             │
// │    ├─ Append completion footer with timestamp                             │
// │    └─ Mark end of test run for analysis                                   │
// │                                                                             │
// │ 3️⃣  OUTPUT SUMMARY                                                         │
// │    ├─ Print confirmation messages                                         │
// │    ├─ Show total users processed                                          │
// │    └─ Display file locations for review                                   │
// │                                                                             │
// ╰─────────────────────────────────────────────────────────────────────────────╯
//
// ╭─ OUTPUT FILES CREATED ─────────────────────────────────────────────────────╮
// │                                                                            │
// │ 📊 test-results/all-users-metrics.json                                     │
// │    └─ Aggregated performance metrics from all users                        │
// │       Structure: { testRunTime, totalUsers, users: [...] }                 │
// │                                                                            │
// │ 📋 test-results/master.log (FINALIZED)                                     │
// │    └─ Master log with completion footer appended                           │
// │       Markers: Header + entries + footer = complete document               │
// │                                                                            │
// ╰─────────────────────────────────────────────────────────────────────────────╯

test.afterAll(async ({ }, testInfo) => {
    try {
        const testResultsDir = path.dirname(testInfo.outputDir);
        const allUsers = [];

        // ┌──────────────────────────────────────────────────────────────────┐
        // │ PHASE 1: Collect Performance Metrics from All Users              │
        // └──────────────────────────────────────────────────────────────────┘

        // Discover all user test subdirectories (each user has their own folder)
        // Format: [Test-Name-User-X-...chromium]
        const subdirs = fs.readdirSync(testResultsDir, { withFileTypes: true })
            .filter(dirent => dirent.isDirectory())
            .map(dirent => dirent.name);

        // Read metrics JSON files from each user's folder
        // Collects: performance timings, execution data, browser metrics
        for (const subdir of subdirs) {
            const subdirPath = path.join(testResultsDir, subdir);
            try {
                const files = fs.readdirSync(subdirPath)
                    .filter(f => f.endsWith('-metrics.json') && f !== 'all-users-metrics.json');
                for (const file of files) {
                    const content = fs.readFileSync(path.join(subdirPath, file), 'utf8');
                    const userData = JSON.parse(content);
                    allUsers.push(userData);
                }
            } catch (e) {
                // Skip directories without JSON files (non-test output dirs)
            }
        }

        // Create aggregated metrics file if data exists
        if (allUsers.length > 0) {
            const cumulative = {
                testRunTime: new Date().toISOString(),
                totalUsers: allUsers.length,
                users: allUsers,
            };

            const outputPath = path.join(testResultsDir, 'all-users-metrics.json');
            fs.writeFileSync(outputPath, JSON.stringify(cumulative, null, 2));
            console.log(`\n📊 Cumulative metrics: ${outputPath} (${allUsers.length} users)`);
        }

        // Finalize master log with footer timestamp
        // This marks the end of the test run for easy identification
        const masterLogPath = path.join(testResultsDir, 'master.log');
        if (fs.existsSync(masterLogPath)) {
            const footer = `\n${'='.repeat(100)}\nTest Completed: ${new Date().toISOString()}\n${'='.repeat(100)}\n`;
            fs.appendFileSync(masterLogPath, footer);
            console.log(`\n📋 Master log finalized: ${masterLogPath}`);
        }
    } catch (e) {
        console.log('Note: Could not finalize test results:', e.message);
    }
});

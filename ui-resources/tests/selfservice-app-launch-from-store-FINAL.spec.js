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
  ACTION: 20000, // 20 seconds
  
  /**
   * NAVIGATION: Timeout for page navigation to complete
   * Use: await page.goto(url, { timeout: TIMEOUTS.NAVIGATION })
   * Recommendation: 20s for slow networks, 10s for fast
   */
  NAVIGATION: 20000, // 20 seconds
  
  /**
   * WAIT: Generic wait for elements to appear
   * Use: await element.waitFor({ state: 'visible', timeout: TIMEOUTS.WAIT })
   * Recommendation: 10s for most cases
   */
  WAIT: 10000, // 10 seconds
  
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
};

// ═══════════════════════════════════════════════════════════════════════════
// APP CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════

const APP_CONFIG = {
  appName: 'Foundation-Lite-One',
  appVersion: '1.0.0',
  appNamePrefix: 'bg-user20-vm-test-01'
};

// ═══════════════════════════════════════════════════════════════════════════
// TEST USERS (Add more for scale testing)
// ═══════════════════════════════════════════════════════════════════════════

const users = [
  {username: 'solution_user1@qa.nutanix.com', password: 'nutanix/4u'},
  {username: 'solution_user2@qa.nutanix.com', password: 'nutanix/4u'},
  {username: 'solution_user3@qa.nutanix.com', password: 'nutanix/4u'},
  {username: 'solution_user4@qa.nutanix.com', password: 'nutanix/4u'},
  {username: 'solution_user5@qa.nutanix.com', password: 'nutanix/4u'},
  {username: 'solution_user6@qa.nutanix.com', password: 'nutanix/4u'},
  {username: 'solution_user7@qa.nutanix.com', password: 'nutanix/4u'},
  {username: 'solution_user8@qa.nutanix.com', password: 'nutanix/4u'},
  {username: 'solution_user9@qa.nutanix.com', password: 'nutanix/4u'}
       
  // Add more users for parallel execution:
  // { username: 'solution_user2@qa.nutanix.com', password: 'nutanix/4u' },
  // { username: 'solution_user3@qa.nutanix.com', password: 'nutanix/4u' },
  // ... up to 1000 users
];

// ═══════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════

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
    }).catch(() => {});

    const modalRoot = iframeLocator.locator('div[role="dialog"], .welcome-modal, .modal, [data-test="welcome-modal"]');
    await modalRoot.waitFor({ state: 'visible', timeout: appearTimeout }).catch(() => {});

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
              await modalRoot.waitFor({ state: 'hidden', timeout: hiddenTimeout }).catch(() => {});
              await page.locator('.modal-backdrop, .overlay, .loading-overlay').waitFor({ 
                state: 'hidden', 
                timeout: 5000 
              }).catch(() => {});
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
        await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
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

// ═══════════════════════════════════════════════════════════════════════════
// TEST SUITE
// ═══════════════════════════════════════════════════════════════════════════

test.describe('Self Service - App Launch from Store Performance Test', () => {
  for (let i = 0; i < users.length; i++) {
    test(`User ${i + 1}: App Deployment Test`, async ({ page }, testInfo) => {
      test.setTimeout(600_000); // 10 minutes total test timeout

      const USERNAME = users[i].username;
      const PASSWORD = users[i].password;
      const userLabel = `[User ${i + 1}]`;

      const timestamp = Date.now();
      const uniqueAppName = `${APP_CONFIG.appNamePrefix}-user${i + 1}-${timestamp}`;

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
        try {
          await page.goto('https://iam.nconprem-10-122-152-117.ccpnx.com/ui/iam/login?', {
            timeout: TIMEOUTS.NAVIGATION
          });
          
          // CRITICAL: Wait for page to load before capturing metrics
          await ensurePageLoaded(page, 'Step 01', perf);
          
        } catch (error) {
          await perf.captureFailure('Step 01 - Navigate to login');
          throw error;
        } finally {
          await perf.stop(); // Performance tracker captures metrics here
        }

        // ─────────────────────────────────────────────────────────────────────
        // Step 02: Enter username
        // ─────────────────────────────────────────────────────────────────────
        perf.start('Step 02 - Enter username');
        try {
          // TRACK: Record how long it takes for input to become fillable
          await trackAndFill(
            page.locator('[data-test="loginInputUsername"]'),
            'Username input field',
            USERNAME,
            perf,
            { timeout: TIMEOUTS.ACTION }
          );
          // No page load here, just form fill
        } catch (error) {
          await perf.captureFailure('Step 02 - Enter username');
          throw error;
        } finally {
          await perf.stop();
        }

        // ─────────────────────────────────────────────────────────────────────
        // Step 03: Enter password
        // ─────────────────────────────────────────────────────────────────────
        perf.start('Step 03 - Enter password');
        try {
          await trackAndFill(
            page.locator('[data-test="loginInputPassword"]'),
            'Password input field',
            PASSWORD,
            perf,
            { timeout: TIMEOUTS.ACTION }
          );
          // No page load here, just form fill
        } catch (error) {
          await perf.captureFailure('Step 03 - Enter password');
          throw error;
        } finally {
          await perf.stop();
        }

        // ─────────────────────────────────────────────────────────────────────
        // Step 04: Submit and wait for dashboard
        // ─────────────────────────────────────────────────────────────────────
        perf.start('Step 04 - Submit and wait for dashboard page');
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
          
        } catch (error) {
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
          }

          // Wait for any navigation to settle
          await page.waitForLoadState('networkidle', { 
            timeout: TIMEOUTS.NETWORK_IDLE 
          }).catch(() => {});
          
        } catch (error) {
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
          }).catch(() => {});
          
          // Wait for iframe to be present
          await page.locator('iframe[name="ch-nc_self_service"]').waitFor({
            state: 'attached',
            timeout: TIMEOUTS.WAIT
          });
          
        } catch (error) {
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
            console.warn(`${userLabel} ⚠️ Welcome modal may still be present`);
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
              console.log(`${userLabel} ⚠️ Welcome message not found`);
            });
          }

          // CRITICAL: Ensure iframe is loaded
          await ensurePageLoaded(page, 'Step 07', perf, { 
            frameName: 'ch-nc_self_service' 
          });
          
        } catch (error) {
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
        try {
          const diagDir = testInfo?.outputDir ? path.dirname(testInfo.outputDir) : process.cwd();
          await dismissIframeModal(page, 'iframe[name="ch-nc_self_service"]', {
            appearTimeout: 8000,
            clickTimeout: 5000,
            hiddenTimeout: 10000,
            diagDir,
            userLabel
          });
        } catch (error) {
          await perf.captureFailure('Step 08 - Dismiss modal');
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // ═══════════════════════════════════════════════════════════════════════
      // STEP: NAVIGATE TO STORE
      // ═══════════════════════════════════════════════════════════════════════
      
      await test.step(`${userLabel} Navigate to Store`, async () => {
        perf.start('Step 09 - Click on Store in Self Service', { 
          frameName: 'ch-nc_self_service' 
        });
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          await trackAndClick(
            selfServiceFrame.getByRole('link', { name: 'Store', exact: true }),
            'Store link',
            perf,
            { timeout: TIMEOUTS.ACTION }
          );
          
          // CRITICAL: Store page loads, wait for it
          await ensurePageLoaded(page, 'Step 09', perf, { 
            frameName: 'ch-nc_self_service' 
          });
          
        } catch (error) {
          await perf.captureFailure('Step 09 - Navigate to Store');
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // ═══════════════════════════════════════════════════════════════════════
      // STEP: SEARCH FOR APP
      // ═══════════════════════════════════════════════════════════════════════
      
      await test.step(`${userLabel} Search for App`, async () => {
        perf.start('Step 10 - Search for App in Store', { 
          frameName: 'ch-nc_self_service' 
        });
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          const searchBox = selfServiceFrame.getByRole('textbox', { name: 'Search Store' });
          
          await trackAndClick(
            searchBox,
            'Search box',
            perf,
            { timeout: TIMEOUTS.ACTION }
          );
          
          await trackAndFill(
            searchBox,
            'Search box input',
            APP_CONFIG.appName,
            perf,
            { timeout: TIMEOUTS.ACTION }
          );
          
          await trackAndClick(
            selfServiceFrame.getByTitle(APP_CONFIG.appName),
            'App title in search results',
            perf,
            { timeout: TIMEOUTS.ACTION }
          );
          
          // App details page loads
          await page.waitForTimeout(TIMEOUTS.MEDIUM_WAIT);
          
        } catch (error) {
          await perf.captureFailure('Step 10 - Search for App');
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // ═══════════════════════════════════════════════════════════════════════
      // STEP: GET APP
      // ═══════════════════════════════════════════════════════════════════════
      
      await test.step(`${userLabel} Get App`, async () => {
        perf.start('Step 11 - Click Get button', { 
          frameName: 'ch-nc_self_service' 
        });
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          await trackAndClick(
            selfServiceFrame.getByRole('button', { name: `Get ${APP_CONFIG.appName}` }),
            'Get button',
            perf,
            { timeout: TIMEOUTS.ACTION }
          );
          
          // Deployment form loads
          await page.waitForTimeout(TIMEOUTS.LONG_WAIT);
          
        } catch (error) {
          await perf.captureFailure('Step 11 - Click Get button');
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // ═══════════════════════════════════════════════════════════════════════
      // STEP: SELECT VERSION
      // ═══════════════════════════════════════════════════════════════════════
      
      await test.step(`${userLabel} Select Version`, async () => {
        let versionDropdown;
        
        // Step 12a: Wait for dropdown to render
        perf.start('Step 12a - Wait for Version dropdown', { 
          frameName: 'ch-nc_self_service' 
        });
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          versionDropdown = selfServiceFrame.getByRole('combobox', { name: 'Version' });
          
          await expect(versionDropdown).toBeVisible({ timeout: TIMEOUTS.ACTION });
          await expect(versionDropdown).toBeEnabled({ timeout: TIMEOUTS.ACTION });
        } catch (error) {
          await perf.captureFailure('Step 12a - Dropdown render');
          throw error;
        } finally {
          await perf.stop();
        }

        // Step 12b: Select version
        perf.start('Step 12b - Select App Version', { 
          frameName: 'ch-nc_self_service' 
        });
        try {
          await trackAndClick(
            versionDropdown,
            'Version dropdown',
            perf,
            { timeout: TIMEOUTS.ACTION }
          );
          await page.waitForTimeout(TIMEOUTS.SHORT_WAIT);
          
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          const versionOption = selfServiceFrame.getByText(APP_CONFIG.appVersion, { exact: true });
          await trackAndClick(
            versionOption,
            'Version option in dropdown',
            perf,
            { timeout: TIMEOUTS.ACTION }
          );
        } catch (error) {
          await perf.captureFailure('Step 12b - Select version');
          throw error;
        } finally {
          await perf.stop();
        }

        // Step 12c: Click Deploy
        perf.start('Step 12c - Click Deploy Button', { 
          frameName: 'ch-nc_self_service' 
        });
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          const deployButton = selfServiceFrame.locator("[title='Deploy App']");
          
          await expect(deployButton).toBeEnabled({ timeout: TIMEOUTS.ACTION });
          await trackAndClick(
            deployButton,
            'Deploy button',
            perf,
            { timeout: TIMEOUTS.ACTION }
          );
          
          // Deployment form loads
          await page.waitForTimeout(TIMEOUTS.LONG_WAIT);
        } catch (error) {
          await perf.captureFailure('Step 12c - Click deploy');
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // ═══════════════════════════════════════════════════════════════════════
      // STEP: FILL FORM AND WAIT FOR VARIABLES
      // ═══════════════════════════════════════════════════════════════════════
      
      await test.step(`${userLabel} Fill Form and Wait for Variables`, async () => {
        
        // Step 13: Fill Application Name
        perf.start('Step 13 - Fill Application Name', { 
          frameName: 'ch-nc_self_service' 
        });
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          console.log(`${userLabel} 📝 Filling Application Name: ${uniqueAppName}`);
          await trackAndFill(
            selfServiceFrame.getByRole('textbox', { name: 'Enter Application Name' }),
            'Application name input',
            uniqueAppName,
            perf,
            { timeout: TIMEOUTS.ACTION }
          );
        } catch (error) {
          await perf.captureFailure('Step 13 - Fill name');
          throw error;
        } finally {
          await perf.stop();
        }

        // Step 14: Click Service Configurations
        perf.start('Step 14 - Click Service Configurations', { 
          frameName: 'ch-nc_self_service' 
        });
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          console.log(`${userLabel} ⏳ Clicking Service Configurations tab...`);
          await trackAndClick(
            selfServiceFrame.getByText('Service Configurations'),
            'Service Configurations tab',
            perf,
            { timeout: TIMEOUTS.ACTION }
          );
          await page.waitForTimeout(TIMEOUTS.LONG_WAIT);
        } catch (error) {
          await perf.captureFailure('Step 14 - Click config');
          throw error;
        } finally {
          await perf.stop();
        }

        // Step 15: Scroll and wait for variables (LONG RUNNING)
        perf.start('Step 15 - Scroll and Wait for Variables', { 
          frameName: 'ch-nc_self_service' 
        });
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          await selfServiceFrame.locator('body').hover();

          const maxScrollSteps = 7;
          const scrollAmount = 300;
          let foundLoadingVariables = false;
          let consecutiveBlankScrolls = 0;

          for (let scrollStep = 1; scrollStep <= maxScrollSteps; scrollStep++) {
            console.log(`${userLabel} 📜 Scroll ${scrollStep}/${maxScrollSteps}`);
            await page.mouse.wheel(0, scrollAmount);
            await page.waitForTimeout(20000);

            let stillFetching = await page.evaluate((frameSelector) => {
              const iframe = document.querySelector(frameSelector);
              if (!iframe?.contentDocument) return false;
              return iframe.contentDocument.body.innerText.includes('Fetching values');
            }, 'iframe[name="ch-nc_self_service"]');

            if (!stillFetching) {
              console.log(`${userLabel} ✅ No loading at scroll ${scrollStep}`);
              consecutiveBlankScrolls++;

              if (!foundLoadingVariables && scrollStep >= 7) {
                console.log(`${userLabel} ✅ Ready (no variables found)`);
                break;
              }

              if (foundLoadingVariables && consecutiveBlankScrolls >= 3) {
                console.log(`${userLabel} ✅ Ready (all loaded)`);
                break;
              }

              continue;
            }

            console.log(`${userLabel} ⏳ Found "Fetching..." at scroll ${scrollStep}`);
            foundLoadingVariables = true;
            consecutiveBlankScrolls = 0;

            for (let iter = 1; iter <= TIMEOUTS.DYNAMIC_VAR_MAX_ITERATIONS; iter++) {
              console.log(`${userLabel} 🔍 Check ${iter}/${TIMEOUTS.DYNAMIC_VAR_MAX_ITERATIONS}`);
              await page.waitForTimeout(TIMEOUTS.DYNAMIC_VAR_CHECK_INTERVAL);

              stillFetching = await page.evaluate((frameSelector) => {
                const iframe = document.querySelector(frameSelector);
                if (!iframe?.contentDocument) return false;
                return iframe.contentDocument.body.innerText.includes('Fetching values');
              }, 'iframe[name="ch-nc_self_service"]');

              if (!stillFetching) {
                console.log(`${userLabel} ✅ Loaded after ${iter * 30}s`);
                break;
              }

              if (iter === TIMEOUTS.DYNAMIC_VAR_MAX_ITERATIONS) {
                throw new Error(`Variables timeout at scroll ${scrollStep}`);
              }
            }
          }

          console.log(`${userLabel} ✅ All variables loaded`);
        } catch (error) {
          await perf.captureFailure('Step 15 - Variables');
          throw error;
        } finally {
          await perf.stop();
        }
      });

       // -----------------------
       // MISSING STEPS: DEPLOY + VERIFY
       // -----------------------
 
       // Step 16: Click Deploy Button to start deployment
       perf.start('Step 16 - Click on Deploy Button to start deployment');
       try {
         const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
         if (!selfServiceFrame) {
           throw new Error('Self service frame not available for deploy click');
         }
 
         // Try semantic role first, fallback to title attribute
         let deployButton = null;
         try {
           deployButton = selfServiceFrame.getByRole('button', { name: 'Click to deploy blueprint' });
           await expect(deployButton).toBeVisible({ timeout: 2000 }).catch(() => { deployButton = null; });
         } catch {
           deployButton = null;
         }
         if (!deployButton) {
           deployButton = selfServiceFrame.locator("[title='Deploy App']");
         }
 
         await expect(deployButton).toBeVisible({ timeout: TIMEOUTS.ACTION });
         await expect(deployButton).toBeEnabled({ timeout: TIMEOUTS.ACTION });
         await deployButton.click({ timeout: TIMEOUTS.ACTION });
 
         // brief stabilization and ensure any frame navigation completes
         await page.waitForTimeout(TIMEOUTS.SHORT_WAIT);
         await ensurePageLoaded(page, 'Step 16', perf, { frameName: 'ch-nc_self_service' });
       } catch (error) {
         await perf.captureFailure('Step 16 - Click Deploy');
         throw error;
       } finally {
         await perf.stop();
       }
 
       // Step 17: Verify Deployment pop up is displayed
       perf.start('Step 17 - Verify Deployment pop up is displayed');
       try {
         const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
         if (!selfServiceFrame) {
           throw new Error('Self service frame not available for deployment verification');
         }
 
         const deployingText = selfServiceFrame.getByText('Deploying App');
         const deploymentInProgress = selfServiceFrame.getByText('Deployment in progress');
 
         await Promise.race([
           deployingText.waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION }),
           deploymentInProgress.waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION }),
         ]);
       } catch (error) {
         await perf.captureFailure('Step 17 - Verify Deployment popup');
         throw error;
       } finally {
         await perf.stop();
       }
 
       // Step 18: Wait for "View in Applications" button to be enabled
       perf.start('Step 18 - Wait for "View in Applications" button to be enabled');
       try {
         const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
         if (!selfServiceFrame) {
           throw new Error('Self service frame not available for view button check');
         }
 
         const viewAppsButton = selfServiceFrame.getByRole('button', { name: 'View in Applications' });
         await viewAppsButton.waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION });
         await expect(viewAppsButton).toBeEnabled({ timeout: TIMEOUTS.NAVIGATION });
         // Optionally click it later; here we only measure readiness
       } catch (error) {
         await perf.captureFailure('Step 18 - View in Applications button');
         throw error;
       } finally {
         await perf.stop();
       }     

      // ═══════════════════════════════════════════════════════════════════════
      // STEP: PERFORMANCE SUMMARY
      // ═══════════════════════════════════════════════════════════════════════
      
      await test.step(`${userLabel} Performance Summary`, async () => {
        perf.start('Step 19 - Performance Summary');
        try {
          await perf.printSummary({ includeBrowserMetrics: true });
          await perf.exportToJSON(`${userLabel.replace(/[\[\]]/g, '')}-metrics.json`);
        } catch (error) {
          await perf.captureFailure('Step 19 - Summary');
          throw error;
        } finally {
          await perf.stop();
        }
      });
    });
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// AFTER ALL: MERGE RESULTS
// ═══════════════════════════════════════════════════════════════════════════

test.afterAll(async ({}, testInfo) => {
  try {
    const testResultsDir = path.dirname(testInfo.outputDir);
    const allUsers = [];

    const subdirs = fs.readdirSync(testResultsDir, { withFileTypes: true })
      .filter(dirent => dirent.isDirectory())
      .map(dirent => dirent.name);

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
        // Skip directories without JSON files
      }
    }

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
  } catch (e) {
    console.log('Note: Could not create cumulative JSON:', e.message);
  }
});

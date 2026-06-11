import { test, expect } from '@playwright/test';
import { PerformanceTracker } from './helpers/performance-tracker.js';

/**
 * Self Service UI Rendering Performance Test
 * 
 * Tests the performance of Self Service UI with comprehensive metrics:
 * - UI Responsiveness (Web Vitals) per page
 * - API Performance with detailed breakdown (P90/P95 percentiles)
 * - Page load times for critical views
 * - Multi-user parallel execution support
 * 
 * Focus: Ensure pages load successfully (not content verification)
 * Uses the generic PerformanceTracker helper for reusable, maintainable code.
 * 
 * ═══════════════════════════════════════════════════════════════════
 * 📊 VIEWING RESULTS (For Large-Scale Testing)
 * ═══════════════════════════════════════════════════════════════════
 * 
 * 1. Run tests (generates JSON files automatically):
 *    npx playwright test tests/selfservice-ui-rendering.spec.js --workers=50
 * 
 * 2. Open the HTML viewer:
 *    open tests/helpers/report-viewer.html
 * 
 * 3. Load JSON files:
 *    - Click "Load JSON Files"
 *    - Navigate to test-results folder
 *    - Select all *-metrics.json files
 *    - Explore interactive reports!
 * 
 * See: tests/helpers/README-REPORT-VIEWER.md for full documentation
 */

// Global timeout configuration (in milliseconds)
const TIMEOUTS = {
  ACTION: 5000,        // 5 seconds for clicks, fills, etc.
  NAVIGATION: 10000,   // 10 seconds for page navigation
  WAIT: 3000,          // 3 seconds for element waits
};

const users = [
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
  { username: 'manish.gupta@qa.nutanix.com', password: 'Nutanix.123' },
];

test.describe('Self Service - UI Rendering Performance Test', () => {
  for (let i = 0; i < users.length; i++) {
    test(`User ${i + 1}: Performance Test`, async ({ page }, testInfo) => {
      test.setTimeout(180_000); // 3 minutes for Self Service navigation

      const USERNAME = users[i].username;
      const PASSWORD = users[i].password;
      const userLabel = `[User ${i + 1}]`;

      // Initialize GENERIC performance tracker
      const perf = new PerformanceTracker(page, testInfo, userLabel, {
        slowRequestThreshold: 2000, // ms
      });

      // STEP 1: Login
      await test.step(`${userLabel} Login`, async () => {
        perf.setPage('Login');
        const endTiming = perf.startTiming('Login');
        
        try {
          // Use EXACT same approach as working AIOps test
          await page.goto('https://iam.nconprem-10-122-152-117.ccpnx.com/ui/iam/login?');
          await page.locator('[data-test="loginInputUsername"]').fill(USERNAME);
          await page.locator('[data-test="loginInputPassword"]').fill(PASSWORD);
          await page.locator('[data-test="loginButtonSubmit"]').click();
          await page.waitForLoadState('domcontentloaded');
          await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
          
          // Capture UI responsiveness for Login page
          await perf.captureWebVitalsForCurrentPage();
          
          endTiming();
        } catch (error) {
          await perf.captureFailure('Login');
          throw error;
        }
      });

      // STEP 2: Dismiss tour
      await test.step(`${userLabel} Dismiss tour`, async () => {
        perf.setPage('Global Overview');
        const skipTour = page.getByRole('button', { name: /skip tour/i });
        if (await skipTour.isVisible({ timeout: TIMEOUTS.WAIT }).catch(() => false)) {
          await skipTour.click({ timeout: TIMEOUTS.ACTION });
        }
        
        // Capture UI responsiveness for Global Overview page
        await perf.captureWebVitalsForCurrentPage();
      });

      // STEP 3: Navigate to Self Service
      await test.step(`${userLabel} Navigate to Self Service`, async () => {
        perf.setPage('Self Service Navigation');
        const endTiming = perf.startTiming('Self Service Navigation');
        
        try {
          // Click Global Overview to open app switcher
          await page.getByLabel('App - Global Overview selected').getByText('Global Overview').click({ timeout: TIMEOUTS.ACTION });
          
          // Click on Cloud Manager - Self Service
          await page.getByLabel('Cloud Manager - Self Service').click({ timeout: TIMEOUTS.ACTION });
          
          // Wait for Self Service iframe to load
          const selfServiceIframe = page.locator('iframe[name="ch-nc_self_service"]');
          await expect(selfServiceIframe).toBeVisible({ timeout: TIMEOUTS.NAVIGATION });
          
          const selfServiceFrame = selfServiceIframe.contentFrame();
          
          // Wait for Self Service content to load - check for welcome message or main content
          const welcomeText = selfServiceFrame.getByText('Welcome to Self Service');
          const deployText = selfServiceFrame.getByText('Deploy and manage');
          
          await Promise.race([
            welcomeText.waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION }),
            deployText.waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION }),
          ]).catch(() => {
            console.log(`${userLabel} ⚠️  Welcome message not found, continuing...`);
          });
          
          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
          
          // Capture UI responsiveness for Self Service Navigation
          await perf.captureWebVitalsForCurrentPage();
          
          endTiming();
        } catch (error) {
          await perf.captureFailure('Self-Service-Navigation');
          throw error;
        }
      });

      // STEP 4: Dismiss Welcome Modal (if present)
      await test.step(`${userLabel} Dismiss Welcome Modal`, async () => {
        perf.setPage('Self Service Home');
        const endTiming = perf.startTiming('Self Service Home');
        
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          
          // Close welcome modal if present
          const closeButton = selfServiceFrame.getByRole('button', { name: '×' });
          if (await closeButton.isVisible({ timeout: TIMEOUTS.WAIT }).catch(() => false)) {
            await closeButton.click({ timeout: TIMEOUTS.ACTION });
            await page.waitForTimeout(500);
          }
          
          // Capture UI responsiveness for Self Service Home
          await perf.captureWebVitalsForCurrentPage('ch-nc_self_service');
          
          endTiming();
        } catch (error) {
          await perf.captureFailure('Self-Service-Home');
          throw error;
        }
      });

      // STEP 5: Navigate to Applications
      await test.step(`${userLabel} Applications Page`, async () => {
        perf.setPage('Applications');
        const endTiming = perf.startTiming('Applications');
        
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          
          // Click Applications link
          await selfServiceFrame.getByRole('link', { name: 'Applications' }).click({ timeout: TIMEOUTS.ACTION });
          await page.waitForTimeout(1000);
          
          // Wait for Applications page to load - check for Apps button or content
          await selfServiceFrame.getByRole('button', { name: /Apps \d+/ }).waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION });
          
          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
          
          // Capture UI responsiveness for Applications page
          await perf.captureWebVitalsForCurrentPage('ch-nc_self_service');
          
          endTiming();
        } catch (error) {
          await perf.captureFailure('Applications-Page');
          throw error;
        }
      });

      // STEP 6: Switch to Table View
      await test.step(`${userLabel} Apps Table View`, async () => {
        perf.setPage('Apps Table');
        const endTiming = perf.startTiming('Apps Table');
        
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          
          // Click second tab (table view)
          await selfServiceFrame.getByRole('tablist').getByRole('tab').nth(1).click({ timeout: TIMEOUTS.ACTION });
          await page.waitForTimeout(2000);
          
          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
          
          // Capture UI responsiveness for Apps Table view
          await perf.captureWebVitalsForCurrentPage('ch-nc_self_service');
          
          endTiming();
        } catch (error) {
          await perf.captureFailure('Apps-Table-View');
          throw error;
        }
      });

      // STEP 8: Navigate to Store
      await test.step(`${userLabel} Store Page`, async () => {
        perf.setPage('Store');
        const endTiming = perf.startTiming('Store');
        
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          
          // Click Store link
          await selfServiceFrame.getByRole('link', { name: 'Store', exact: true }).click({ timeout: TIMEOUTS.ACTION });
          await page.waitForTimeout(2000);
          
          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
          
          // Capture UI responsiveness for Store page
          await perf.captureWebVitalsForCurrentPage('ch-nc_self_service');
          
          endTiming();
        } catch (error) {
          await perf.captureFailure('Store-Page');
          throw error;
        }
      });

      // STEP 9: Switch to Store List View
      await test.step(`${userLabel} Store List View`, async () => {
        perf.setPage('Store List');
        const endTiming = perf.startTiming('Store List');
        
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          
          // Click second tab (list view) - same as Applications table view
          await selfServiceFrame.getByRole('tablist').getByRole('tab').nth(1).click({ timeout: TIMEOUTS.ACTION });
          await page.waitForTimeout(2000);
          
          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
          
          // Capture UI responsiveness for Store List view
          await perf.captureWebVitalsForCurrentPage('ch-nc_self_service');
          
          endTiming();
        } catch (error) {
          await perf.captureFailure('Store-List-View');
          throw error;
        }
      });

      // STEP 10: Navigate to Blueprints
      await test.step(`${userLabel} Blueprints Page`, async () => {
        perf.setPage('Blueprints');
        const endTiming = perf.startTiming('Blueprints');
        
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          
          // Click Blueprints link
          await selfServiceFrame.getByRole('link', { name: 'Blueprints' }).click({ timeout: TIMEOUTS.ACTION });
          await page.waitForTimeout(1000);
          
          // Wait for Blueprints page to load - check for heading
          await selfServiceFrame.getByRole('heading', { name: 'Blueprints', exact: true }).waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION });
          
          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
          
          // Capture UI responsiveness for Blueprints page
          await perf.captureWebVitalsForCurrentPage('ch-nc_self_service');
          
          endTiming();
        } catch (error) {
          await perf.captureFailure('Blueprints-Page');
          throw error;
        }
      });

      // STEP 11: Print performance summary
      await test.step(`${userLabel} Performance Summary`, async () => {
        await perf.printSummary({
          includeBrowserMetrics: true,
        });
      });
    });
  }
});

// After all tests complete, merge all user JSONs into one cumulative file
test.afterAll(async ({}, testInfo) => {
  const fs = require('fs');
  const path = require('path');
  const { PerformanceTracker } = await import('./helpers/performance-tracker.js');
  
  try {
    // Get the parent test-results directory (not the individual test directory)
    const testResultsDir = path.dirname(testInfo.outputDir);
    
    // Find all subdirectories with JSON files
    const allJsonFiles = [];
    const subdirs = fs.readdirSync(testResultsDir, { withFileTypes: true })
      .filter(dirent => dirent.isDirectory())
      .map(dirent => dirent.name);
    
    // Collect all user JSON files from all test directories
    const allUsers = [];
    for (const subdir of subdirs) {
      const subdirPath = path.join(testResultsDir, subdir);
      try {
        const files = fs.readdirSync(subdirPath).filter(f => f.endsWith('-metrics.json') && f !== 'all-users-metrics.json');
        for (const file of files) {
          try {
            const content = fs.readFileSync(path.join(subdirPath, file), 'utf8');
            const userData = JSON.parse(content);
            if (userData && typeof userData === 'object' && userData.pages && typeof userData.pages === 'object') {
              allUsers.push(userData);
            }
          } catch (parseErr) {
            console.warn('Skipping invalid or corrupt JSON:', file, parseErr.message);
          }
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
      console.log(`\n📊 Cumulative metrics exported to: test-results/all-users-metrics.json (${allUsers.length} users)`);
    }
  } catch (e) {
    console.log('Note: Could not create cumulative JSON:', e.message);
  }
});

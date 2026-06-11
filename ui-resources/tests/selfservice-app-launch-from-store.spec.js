import { test, expect } from '@playwright/test';
import { PerformanceTracker } from './helpers/performance-tracker.js';
import fs from 'fs';
import path from 'path';

/**
 * Self Service App Launch from Store - Performance Test
 *
 * Tests the complete app deployment workflow from Store:
 * - Navigate to Store
 * - Search and select app (Foundation-Lite-One)
 * - Fill deployment form with dynamic variables
 * - Deploy app and verify deployment status
 * - Track performance metrics throughout
 *
 * NOTE: This version ensures every perf.start() has a single matching await perf.stop()
 * and that perf.start() is called before any blocking wait you want measured.
 */

// Global timeout configuration (in milliseconds)
const TIMEOUTS = {
  ACTION: 20000,
  NAVIGATION: 20000,
  WAIT: 10000,
  DYNAMIC_VAR: 210000,
  DYNAMIC_VAR_CHECK_INTERVAL: 30000,
  DYNAMIC_VAR_MAX_ITERATIONS: 7,
  SHORT_WAIT: 500,
  MEDIUM_WAIT: 1000,
  LONG_WAIT: 2000,
};

const APP_CONFIG = {
  appName: 'Foundation-Lite-One',
  appVersion: '1.0.0',
  appNamePrefix: 'bg-user20-vm-003',
};

const users = [
  { username: 'solution_user1@qa.nutanix.com', password: 'nutanix/4u' }
];

/**
 * Helper: attempt to dismiss a modal inside an iframe robustly.
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
    await iframeLocator.locator('body').waitFor({ state: 'visible', timeout: Math.min(appearTimeout, 3000) }).catch(() => {});

    const modalRoot = iframeLocator.locator('div[role="dialog"], .welcome-modal, .modal, [data-test="welcome-modal"]');
    await modalRoot.waitFor({ state: 'visible', timeout: appearTimeout }).catch(() => { /* modal may not appear */ });

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
              await page.locator('.modal-backdrop, .overlay, .loading-overlay').waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {});
              clicked = true;
              break;
            }
          } catch (e) {
            // swallow and try next candidate
          }
        }
      }

      if (clicked) return true;

      // short backoff between attempts (small, bounded)
      await page.waitForTimeout(500 * attempt);
    }

    const modalVisible = await page.frameLocator(iframeSelector).locator('div[role="dialog"], .welcome-modal, .modal, [data-test="welcome-modal"]').isVisible().catch(() => false);
    if (!modalVisible) return true;

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
    if (options.diagDir) {
      try {
        const ts = Date.now();
        const safeLabel = String(options.userLabel || 'user').replace(/[\[\]]/g, '');
        const screenshotPath = path.join(options.diagDir, `modal-dismiss-exception-${safeLabel}-${ts}.png`);
        await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
        const htmlPath = path.join(options.diagDir, `modal-dismiss-exception-${safeLabel}-${ts}.html`);
        fs.writeFileSync(htmlPath, await page.content());
        console.log(`Modal dismissal exception diagnostics saved: ${screenshotPath}, ${htmlPath}`);
      } catch (diagErr) {
        console.warn('Failed to write modal exception diagnostics:', diagErr.message);
      }
    }
    return false;
  }
}

test.describe('Self Service - App Launch from Store Performance Test', () => {
  for (let i = 0; i < users.length; i++) {
    test(`User ${i + 1}: App Deployment Test`, async ({ page }, testInfo) => {
      test.setTimeout(600_000);

      const USERNAME = users[i].username;
      const PASSWORD = users[i].password;
      const userLabel = `[User ${i + 1}]`;

      const timestamp = Date.now();
      const uniqueAppName = `${APP_CONFIG.appNamePrefix}-user${i + 1}-${timestamp}`;

      const perf = new PerformanceTracker(page, testInfo, userLabel, {
        slowRequestThreshold: 2000,
        apiPatterns: ['/api/', '/v1/', '/v2/', '/v3/'],
      });

      // Login
      await test.step(`${userLabel} Login`, async () => {
        perf.start('Step 01 - Navigate to login page');
        try {
          await page.goto('https://iam.nconprem-10-122-152-117.ccpnx.com/ui/iam/login?');
        } catch (error) {
          await perf.captureFailure('Login - navigate');
          throw error;
        } finally {
          await perf.stop();
        }

        perf.start('Step 02 - Enter username');
        try {
          await page.locator('[data-test="loginInputUsername"]').fill(USERNAME);
        } catch (error) {
          await perf.captureFailure('Login - enter username');
          throw error;
        } finally {
          await perf.stop();
        }

        perf.start('Step 03 - Enter password');
        try {
          await page.locator('[data-test="loginInputPassword"]').fill(PASSWORD);
        } catch (error) {
          await perf.captureFailure('Login - enter password');
          throw error;
        } finally {
          await perf.stop();
        }

        perf.start('Step 04 - Submit and wait for dashboard page');
        try {
          await page.locator('[data-test="loginButtonSubmit"]').click();
          await page.waitForLoadState('domcontentloaded');
          await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
        } catch (error) {
          await perf.captureFailure('Login - submit');
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // Dismiss tour (Global Overview)
      await test.step(`${userLabel} Dismiss tour`, async () => {
        const skipTour = page.getByRole('button', { name: /skip tour/i });

        perf.start('Step 05 - Dismiss tour if present');
        try {
          await Promise.race([
            skipTour.waitFor({ state: 'visible', timeout: TIMEOUTS.WAIT }),
            page.waitForTimeout(1500)
          ]).catch(() => null);

          const canClick = await skipTour.click({ trial: true }).then(() => true).catch(() => false);

          if (canClick) {
            await skipTour.click({ timeout: TIMEOUTS.ACTION });
            await page.waitForTimeout(800);
          }

          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
        } catch (error) {
          await perf.captureFailure('Dismiss tour');
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // Navigate to Self Service
      await test.step(`${userLabel} Navigate to Self Service`, async () => {
        perf.start('Step 06 - Click on Global Overview and select Self Service');
        try {
          await page.getByLabel('App - Global Overview selected').getByText('Global Overview').click({ timeout: TIMEOUTS.ACTION });
          await page.getByLabel('Cloud Manager - Self Service').click({ timeout: TIMEOUTS.ACTION });
          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
        } catch (error) {
          await perf.captureFailure('Navigate to Self Service');
          throw error;
        } finally {
          await perf.stop();
        }

        // Dismiss welcome modal inside iframe if present
        perf.start('Step 07 - Dismiss Welcome Modal inside iframe if present');
        try {
          const selfServiceIframe = page.locator('iframe[name="ch-nc_self_service"]');
          await expect(selfServiceIframe).toBeVisible({ timeout: TIMEOUTS.NAVIGATION });
          const diagDir = testInfo && testInfo.outputDir ? path.dirname(testInfo.outputDir) : process.cwd();
          const dismissed = await dismissIframeModal(page, 'iframe[name="ch-nc_self_service"]', {
            appearTimeout: 8000,
            clickTimeout: 5000,
            hiddenTimeout: 10000,
            diagDir,
            userLabel
          });

          if (!dismissed) {
            console.warn(`${userLabel} ⚠️ Welcome modal dismissal may have failed or modal still present`);
          }

          const selfServiceFrame = selfServiceIframe.contentFrame();
          const welcomeText = selfServiceFrame ? selfServiceFrame.getByText('Welcome to Self Service') : null;
          const deployText = selfServiceFrame ? selfServiceFrame.getByText('Deploy and manage') : null;

          await Promise.race([
            welcomeText ? welcomeText.waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION }) : Promise.resolve(),
            deployText ? deployText.waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION }) : Promise.resolve(),
          ]).catch(() => {
            console.log(`${userLabel} ⚠️  Welcome message not found, continuing...`);
          });

          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
        } catch (error) {
          await perf.captureFailure('Self-Service-Navigation - open iframe and wait for content');
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // Dismiss Welcome Modal (legacy wrapper)
      await test.step(`${userLabel} Dismiss Welcome Modal`, async () => {
        perf.start('Step 08 - Dismiss Welcome Modal (legacy step, uses helper)');
        try {
          const diagDir = testInfo && testInfo.outputDir ? path.dirname(testInfo.outputDir) : process.cwd();
          const dismissed = await dismissIframeModal(page, 'iframe[name="ch-nc_self_service"]', {
            appearTimeout: 8000,
            clickTimeout: 5000,
            hiddenTimeout: 10000,
            diagDir,
            userLabel
          });

          if (!dismissed) {
            console.warn(`${userLabel} ⚠️ Welcome modal dismissal may have failed or modal still present`);
          }
        } catch (error) {
          await perf.captureFailure('Self-Service-Home - modal dismissal and stabilization');
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // Navigate to Store
      await test.step(`${userLabel} Navigate to Store`, async () => {
        perf.start('Step 09 - Click on Store in Self Service');
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          await selfServiceFrame.getByRole('link', { name: 'Store', exact: true }).click({ timeout: TIMEOUTS.ACTION });
          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
        } catch (error) {
          await perf.captureFailure('Store-Navigation - click and load store page');
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // Search for App
      await test.step(`${userLabel} Search for App`, async () => {
        perf.start('Step 10 - Search for App in Store');
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          const searchBox = selfServiceFrame.getByRole('textbox', { name: 'Search Store' });
          await searchBox.click({ timeout: TIMEOUTS.ACTION });
          await searchBox.fill(APP_CONFIG.appName);
          await selfServiceFrame.getByTitle(APP_CONFIG.appName).click({ timeout: TIMEOUTS.ACTION });
        } catch (error) {
          await perf.captureFailure(`Store-Search - search for ${APP_CONFIG.appName}`);
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // Get App (Start Deployment)
      await test.step(`${userLabel} Get App`, async () => {
        perf.start('Step 11 - Click Get button to start deployment');
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          await selfServiceFrame.getByRole('button', { name: `Get ${APP_CONFIG.appName}` }).click({ timeout: TIMEOUTS.ACTION });
        } catch (error) {
          await perf.captureFailure('App-Details - open app details and start deployment');
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // Select Version and Deploy (split into render vs interaction)
      await test.step(`${userLabel} Select Version`, async () => {
        // 12a: Wait for dropdown to appear (render latency)
        perf.start('Step 12a - Wait for Version dropdown to appear');
        let versionDropdown;
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          versionDropdown = selfServiceFrame.getByRole('combobox', { name: 'Version' });
          await expect(versionDropdown).toBeVisible({ timeout: TIMEOUTS.ACTION });
          await expect(versionDropdown).toBeEnabled({ timeout: TIMEOUTS.ACTION });
        } catch (error) {
          await perf.captureFailure('Select-Version - dropdown render');
          throw error;
        } finally {
          await perf.stop();
        }

        // 12b: Interaction - open dropdown and select version
        perf.start('Step 12b - Select App Version');
        try {
          await versionDropdown.click({ timeout: TIMEOUTS.ACTION });
          await page.waitForTimeout(500); // brief wait for options to render
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          const versionOption = selfServiceFrame.getByText(APP_CONFIG.appVersion, { exact: true });
          await versionOption.click({ timeout: TIMEOUTS.ACTION });
        } catch (error) {
          await perf.captureFailure('Select-Version - choose version and click');
          throw error;
        } finally {
          await perf.stop();
        }

        // 12c: Click Deploy (if present)
        perf.start('Step 12c - Click Deploy Button');
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          const deployButton = selfServiceFrame.locator("[title='Deploy App']");
          await expect(deployButton).toBeEnabled({ timeout: TIMEOUTS.ACTION });
          await deployButton.click({ timeout: TIMEOUTS.ACTION });
        } catch (error) {
          await perf.captureFailure('Select-Version - click deploy');
          throw error;
        } finally {
          await perf.stop();
        }
      });

      // Fill Application Name, Scroll, and Wait for Profile Variables
      await test.step(`${userLabel} Fill Form and Wait for Profile Variables`, async () => {
        // 13: Fill Application Name
        perf.start('Step 13 - Fill Application Name');
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          console.log(`${userLabel} 📝 Filling Application Name: ${uniqueAppName}`);
          await selfServiceFrame.getByRole('textbox', { name: 'Enter Application Name' }).fill(uniqueAppName);
        } catch (error) {
          await perf.captureFailure('Fill Application Name');
          throw error;
        } finally {
          await perf.stop();
        }

        // 14: Click Service Configurations tab
        perf.start('Step 14 - Click on Service Configurations tab');
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          console.log(`${userLabel} ⏳ Clicking Service Configurations tab to load Profile Variables section...`);
          await selfServiceFrame.getByText('Service Configurations').click({ timeout: TIMEOUTS.ACTION });
          await page.waitForTimeout(TIMEOUTS.LONG_WAIT);
        } catch (error) {
          await perf.captureFailure('Click Service Configurations');
          throw error;
        } finally {
          await perf.stop();
        }

        // 15: Scroll and wait for profile variables (long-running)
        perf.start('Step 15 - Scroll and Wait for Profile Variables');
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          await selfServiceFrame.locator('body').hover();

          const maxScrollSteps = 7;
          const scrollAmount = 300;
          let foundLoadingVariables = false;
          let consecutiveBlankScrolls = 0;
          const maxBlankScrolls = 3;
          const maxScrollsIfNeverFound = 7;

          for (let scrollStep = 1; scrollStep <= maxScrollSteps; scrollStep++) {
            console.log(`${userLabel} 📜 Scroll step ${scrollStep}/${maxScrollSteps} (${scrollStep * scrollAmount}px)`);
            await page.mouse.wheel(0, scrollAmount);
            await page.waitForTimeout(20000);

            let stillFetching = await page.evaluate((frameSelector) => {
              const iframe = document.querySelector(frameSelector);
              if (!iframe || !iframe.contentDocument) return false;
              const allText = iframe.contentDocument.body.innerText || '';
              return allText.includes('Fetching values');
            }, 'iframe[name="ch-nc_self_service"]');

            if (!stillFetching) {
              console.log(`${userLabel} ✅ No loading variables at scroll ${scrollStep}`);
              consecutiveBlankScrolls++;

              if (!foundLoadingVariables && scrollStep >= maxScrollsIfNeverFound) {
                console.log(`${userLabel} ✅ No loading variables found after ${scrollStep} scrolls - ready to deploy`);
                break;
              }

              if (foundLoadingVariables && consecutiveBlankScrolls >= maxBlankScrolls) {
                console.log(`${userLabel} ✅ No more loading variables after ${maxBlankScrolls} blank scrolls - ready to deploy`);
                break;
              }

              continue;
            }

            // Found loading variables
            console.log(`${userLabel} ⏳ Found "Fetching values..." at scroll ${scrollStep} - waiting for completion (check every 30s, up to 3.5 min)...`);
            foundLoadingVariables = true;
            consecutiveBlankScrolls = 0;

            for (let iteration = 1; iteration <= TIMEOUTS.DYNAMIC_VAR_MAX_ITERATIONS; iteration++) {
              console.log(`${userLabel} 🔍 [Scroll ${scrollStep}] Validation ${iteration}/${TIMEOUTS.DYNAMIC_VAR_MAX_ITERATIONS}...`);
              await page.waitForTimeout(TIMEOUTS.DYNAMIC_VAR_CHECK_INTERVAL);

              stillFetching = await page.evaluate((frameSelector) => {
                const iframe = document.querySelector(frameSelector);
                if (!iframe || !iframe.contentDocument) return false;
                const allText = iframe.contentDocument.body.innerText || '';
                return allText.includes('Fetching values');
              }, 'iframe[name="ch-nc_self_service"]');

              if (!stillFetching) {
                console.log(`${userLabel} ✅ Variables at scroll ${scrollStep} loaded (after ${iteration * 30}s) - moving to next scroll`);
                break;
              }

              if (iteration === TIMEOUTS.DYNAMIC_VAR_MAX_ITERATIONS) {
                // ensure we close the step before throwing
                await perf.stop();
                throw new Error(`Variables at scroll step ${scrollStep} did not populate within 3.5 minutes`);
              }

              console.log(`${userLabel} ⏳ Still fetching at scroll ${scrollStep}... waiting another 30s`);
            }
          }
          
        } catch (error) {
          await perf.captureFailure('Scroll and Wait for Profile Variables');
          throw error;
        } finally {
          // Only stop if not already stopped by the timeout branch above
          try { await perf.stop(); } catch (e) { /* ignore double-stop if already stopped */ }
        }
     
 
        
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





        console.log(`${userLabel} ✅ All Profile Variables loaded - ready to deploy`);
      });

      // Performance Summary and export
      await test.step(`${userLabel} Performance Summary`, async () => {
        perf.start('Step 19 - Performance Summary');
        try {
          await perf.printSummary({
            includeBrowserMetrics: true,
          });

          await perf.exportToJSON(`${userLabel.replace(/[\[\]]/g, '')}-metrics.json`);
        } catch (error) {
          await perf.captureFailure('Performance-Summary - collect and export metrics');
          throw error;
        } finally {
          await perf.stop();
        }
      });
    });
  }
});

// Merge all user JSONs into cumulative file after all tests complete
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
        const files = fs.readdirSync(subdirPath).filter(f => f.endsWith('-metrics.json') && f !== 'all-users-metrics.json');
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
      console.log(`\n📊 Cumulative metrics exported to: ${outputPath} (${allUsers.length} users)`);
    }
  } catch (e) {
    console.log('Note: Could not create cumulative JSON:', e.message);
  }
});

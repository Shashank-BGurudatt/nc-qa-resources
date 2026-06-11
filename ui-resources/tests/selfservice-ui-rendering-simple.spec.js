import { test, expect } from '@playwright/test';
import { PerformanceTracker } from './helpers/performance-tracker.js';

/**
 * Self Service UI – performance test (simplified API)
 *
 * Uses only:
 *   perf.start(stepName)
 *   await perf.stop()
 *   await perf.finishUser()
 *   PerformanceTracker.generateReport(testInfo)
 */

const TIMEOUTS = {
  ACTION: 10000,
  NAVIGATION: 15000,
  WAIT: 10000,
};

const SELF_SERVICE_FRAME = 'ch-nc_self_service';

const users = [
  { username: 'solution_user1@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user2@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user3@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user4@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user5@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user6@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user7@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user8@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user9@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user10@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user11@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user12@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user13@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user14@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user15@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user16@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user17@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user18@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user19@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user20@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user21@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user22@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user23@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user24@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user25@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user26@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user27@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user28@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user29@qa.nutanix.com', password: 'nutanix/4u' },
  { username: 'solution_user30@qa.nutanix.com', password: 'nutanix/4u' }
];

test.describe('Self Service - Performance (simple start/stop)', () => {
  for (let i = 0; i < users.length; i++) {
    test(`User ${i + 1}: Performance Test`, async ({ page }, testInfo) => {
      test.setTimeout(180_000);

      const USERNAME = users[i].username;
      const PASSWORD = users[i].password;
      const userLabel = `[User ${i + 1}]`;
      const perf = new PerformanceTracker(page, testInfo, userLabel, { slowRequestThreshold: 2000 });

      // —— Login ——
      await test.step(`${userLabel} Login`, async () => {
        perf.start('Login');
        try {
          await page.goto('https://iam.nconprem-10-122-152-117.ccpnx.com/ui/iam/login?');
          await page.locator('[data-test="loginInputUsername"]').fill(USERNAME);
          await page.locator('[data-test="loginInputPassword"]').fill(PASSWORD);
          await page.locator('[data-test="loginButtonSubmit"]').click();
          await page.waitForLoadState('domcontentloaded');
          await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
          await perf.stop();
        } catch (error) {
          await perf.captureFailure('Login');
          throw error;
        }
      });

      // —— Dismiss tour (Global Overview) ——
      await test.step(`${userLabel} Dismiss tour`, async () => {
        perf.start('Global Overview');

        const skipTour = page.getByRole('button', { name: /skip tour/i });

        try {
          await Promise.race([
            skipTour.waitFor({ state: 'visible', timeout: TIMEOUTS.WAIT }),
            page.waitForTimeout(1500)
          ]).catch(() => null);

          const canClick = await skipTour.click({ trial: true })
            .then(() => true)
            .catch(() => false);

          if (canClick) {
            await skipTour.click({ timeout: TIMEOUTS.ACTION });
            await page.waitForTimeout(800);
          }

          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
        } finally {
          await perf.stop();
        }
      });

      // —— Navigate to Self Service ——
      await test.step(`${userLabel} Navigate to Self Service`, async () => {
        perf.start('Self Service Navigation');
        try {
          await page.getByLabel('App - Global Overview selected')
            .getByText('Global Overview')
            .click({ timeout: TIMEOUTS.ACTION });

          await page.getByLabel('Cloud Manager - Self Service')
            .click({ timeout: TIMEOUTS.ACTION });

          const selfServiceIframe = page.locator('iframe[name="ch-nc_self_service"]');
          await expect(selfServiceIframe).toBeVisible({ timeout: TIMEOUTS.NAVIGATION });

          const selfServiceFrame = selfServiceIframe.contentFrame();
          const welcomeText = selfServiceFrame.getByText('Welcome to Self Service');
          const deployText = selfServiceFrame.getByText('Deploy and manage');

          await Promise.race([
            welcomeText.waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION }),
            deployText.waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION }),
          ]).catch(() => {});

          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
          await perf.stop();
        } catch (error) {
          await perf.captureFailure('Self-Service-Navigation');
          throw error;
        }
      });

      // —— Dismiss Welcome Modal (Self Service Home) ——
      await test.step(`${userLabel} Dismiss Welcome Modal`, async () => {
        perf.start('Self Service Home', { frameName: SELF_SERVICE_FRAME });

        try {
          const iframeLocator = page.frameLocator('iframe[name="ch-nc_self_service"]');

          await iframeLocator.locator('body')
            .waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION })
            .catch(() => {});

          const closeButton = iframeLocator.getByRole('button', { name: '×' });

          await Promise.race([
            closeButton.waitFor({ state: 'visible', timeout: TIMEOUTS.WAIT }),
            page.waitForTimeout(1500)
          ]).catch(() => null);

          const canClick = await closeButton.click({ trial: true })
            .then(() => true)
            .catch(() => false);

          if (canClick) {
            await closeButton.click({ timeout: TIMEOUTS.ACTION });
            await page.waitForTimeout(500);
          }

          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
          await perf.stop();

        } catch (error) {
          await perf.captureFailure('Self-Service-Home');
          throw error;
        }
      });

      // —— Store ——
      await test.step(`${userLabel} Store Page`, async () => {
        perf.start('Store', { frameName: SELF_SERVICE_FRAME });
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          await selfServiceFrame.getByRole('link', { name: 'Store', exact: true }).click({ timeout: TIMEOUTS.ACTION });
          await page.waitForTimeout(2000);
          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
          await perf.stop();
        } catch (error) {
          await perf.captureFailure('Store-Page');
          throw error;
        }
      });

      // —— Store List ——
      await test.step(`${userLabel} Store List View`, async () => {
        perf.start('Store List', { frameName: SELF_SERVICE_FRAME });
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          await selfServiceFrame.getByRole('tablist').getByRole('tab').nth(1).click({ timeout: TIMEOUTS.ACTION });
          await page.waitForTimeout(2000);
          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
          await perf.stop();
        } catch (error) {
          await perf.captureFailure('Store-List-View');
          throw error;
        }
      });

      // —— Blueprints ——
      await test.step(`${userLabel} Blueprints Page`, async () => {
        perf.start('Blueprints', { frameName: SELF_SERVICE_FRAME });
        try {
          const selfServiceFrame = page.locator('iframe[name="ch-nc_self_service"]').contentFrame();
          await selfServiceFrame.getByRole('link', { name: 'Blueprints' }).click({ timeout: TIMEOUTS.ACTION });
          await page.waitForTimeout(1000);
          await selfServiceFrame.getByRole('heading', { name: 'Blueprints', exact: true }).waitFor({ state: 'visible', timeout: TIMEOUTS.NAVIGATION });
          await page.waitForLoadState('networkidle', { timeout: TIMEOUTS.NAVIGATION }).catch(() => {});
          await page.waitForTimeout(1500);
          await perf.stop();
        } catch (error) {
          await perf.captureFailure('Blueprints-Page');
          throw error;
        }
      });

      await perf.finishUser();
    });
  }
});

test.afterAll(async ({}, testInfo) => {
  PerformanceTracker.generateReport(testInfo);
});

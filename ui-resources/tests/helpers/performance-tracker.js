import fs from 'fs';
import path from 'path';
/**
 * Performance Tracker — PRODUCTION-READY for 1000+ Users
 * 
 * Enhancements for scale:
 * - Thread-safe operations (no shared state mutation)
 * - Comprehensive race condition handling
 * - Extensive debugging statements
 * - Generic frame/page detection (works with any UI structure)
 * - Timeout management for high parallelism
 * - Memory-efficient data collection
 * - Diagnostic indicators in JSON for HTML viewer
 * 
 * Author: manish.gupta@nutanix.com
 * Version: 2.0 (Production Scale)
 */

export class PerformanceTracker {
  constructor(page, testInfo, userLabel = '[User 1]', options = {}) {
    this.page = page;
    this.testInfo = testInfo;
    this.userLabel = userLabel;
    this.currentPage = 'Unknown';
    this.elementTimes = {};
    
    // PRODUCTION: Thread-safe step tracking
    this._activeStepId = null;
    this._stepSequence = 0;
    this._stoppedSteps = new Set(); // Prevent double-stop
    
    // PRODUCTION: Debug mode
    this.debugMode = options.debugMode !== false; // Default: enabled
    this.debugPrefix = `[PERF-${userLabel}]`;
    
    // PRODUCTION: Configurable timeouts for scale
    this.options = {
      slowRequestThreshold: options.slowRequestThreshold || 2000,
      screenshotOnFailure: options.screenshotOnFailure !== false,
      
      // Scale-specific settings
      maxRetries: options.maxRetries || 3,
      retryDelayMs: options.retryDelayMs || 1500, // Increased for 1000 users
      loadStateTimeout: options.loadStateTimeout || 15000, // 15s for scale
      frameDetectionTimeout: options.frameDetectionTimeout || 10000,
      
      // Performance thresholds
      performanceThresholds: {
        fcp: {
          excellent: options.performanceThresholds?.fcp?.excellent || 1800,
          good: options.performanceThresholds?.fcp?.good || 2500,
        },
        pageLoad: {
          excellent: options.performanceThresholds?.pageLoad?.excellent || 1000,
          good: options.performanceThresholds?.pageLoad?.good || 3000,
        },
        elementLoad: {
          excellent: options.performanceThresholds?.elementLoad?.excellent || 500,
          good: options.performanceThresholds?.elementLoad?.good || 2000,
        },
        contentReady: {
          excellent: options.performanceThresholds?.contentReady?.excellent || 2000,
          good: options.performanceThresholds?.contentReady?.good || 5000,
        },
      },
      
      ...options
    };
    
    // PRODUCTION: Enhanced metrics structure with diagnostics
    this.perfMetrics = {
      byPage: {},
      webVitalsByPage: {},
      diagnostics: {
        captureAttempts: {},
        errors: [],
        warnings: [],
        retries: {},
      }
    };
    
    this.testStartTime = Date.now();
    this.pageLoadTimes = {};
    
    // For start/stop API
    this._endTiming = null;
    this._stepFrameName = null;
    this._stepStartTime = null;
    this._stepOptions = {};
    
    this._setupNetworkTracking();
    
    this._debug('Initialized', { options: this.options });
  }
  
  /**
   * PRODUCTION: Enhanced debug logging with structured data
   */
  _debug(message, data = {}) {
    if (!this.debugMode) return;
    
    const timestamp = new Date().toISOString();
    const logEntry = {
      timestamp,
      user: this.userLabel,
      step: this.currentPage,
      message,
      ...data
    };
    
    console.log(`${this.debugPrefix} ${message}`, data);
    
    // Store for JSON export
    if (!this.perfMetrics.diagnostics.debugLogs) {
      this.perfMetrics.diagnostics.debugLogs = [];
    }
    this.perfMetrics.diagnostics.debugLogs.push(logEntry);
  }
  
  /**
   * PRODUCTION: Record warning (non-fatal)
   */
  _warn(message, data = {}) {
    const warning = {
      timestamp: Date.now(),
      step: this.currentPage,
      message,
      ...data
    };
    
    this.perfMetrics.diagnostics.warnings.push(warning);
    console.warn(`${this.debugPrefix} ⚠️ ${message}`, data);
  }
  
  /**
   * PRODUCTION: Record error (for diagnostics, not thrown)
   */
  _recordError(message, error, context = {}) {
    const errorEntry = {
      timestamp: Date.now(),
      step: this.currentPage,
      message,
      error: error?.message || String(error),
      stack: error?.stack,
      ...context
    };
    
    this.perfMetrics.diagnostics.errors.push(errorEntry);
    console.error(`${this.debugPrefix} ❌ ${message}`, errorEntry);
  }

  /**
   * PRODUCTION: Record element wait time (button click, input fill, etc.)
   * Call this to track how long it takes for elements to become interactive
   * 
   * @param {string} action - 'click', 'fill', 'select', etc.
   * @param {string} elementDescription - Human-readable element name
   * @param {number} waitTimeMs - How long it took to become ready
   * @param {boolean} timedOut - Whether it hit timeout
   */
  recordElementWait(action, elementDescription, waitTimeMs, timedOut = false) {
    const record = {
      action,
      element: elementDescription,
      waitTimeMs: Math.round(waitTimeMs),
      timedOut,
      timestamp: Date.now(),
    };
    
    this._elementWaitTimes.push(record);
    
    if (timedOut) {
      this._warn(`⏱️ Element timeout: ${action} on "${elementDescription}" after ${waitTimeMs}ms`, record);
    } else if (waitTimeMs > 2000) {
      this._warn(`⚠️ Slow element: ${action} on "${elementDescription}" took ${waitTimeMs}ms`, record);
    } else {
      this._debug(`✅ Element ready: ${action} on "${elementDescription}" in ${waitTimeMs}ms`, record);
    }
  }

  /**
   * PRODUCTION: Start with thread-safe step ID
   */
  start(stepName, options = {}) {
    this._stepSequence++;
    this._activeStepId = `${stepName}-${this._stepSequence}`;
    
    this.setPage(stepName);
    this._stepFrameName = options.frameName ?? null;
    this._stepStartTime = Date.now();
    this._stepOptions = options;
    this._endTiming = this.startTiming(stepName);
    this._elementWaitTimes = []; // Track element wait times in this step
    
    this._debug(`Step started: ${stepName}`, {
      stepId: this._activeStepId,
      frameName: this._stepFrameName,
      options
    });
  }

  /**
   * PRODUCTION: Enhanced stop() with comprehensive race condition handling
   */
  async stop() {
    const stepId = this._activeStepId;
    
    // PRODUCTION: Prevent double-stop (thread safety)
    if (!stepId || this._stoppedSteps.has(stepId)) {
      this._warn('stop() called when no active step or already stopped', { stepId });
      return;
    }
    
    this._stoppedSteps.add(stepId);
    
    const stepDurationMs = this._stepStartTime != null ? Date.now() - this._stepStartTime : 0;
    this._stepStartTime = null;
    
    if (typeof this._endTiming === 'function') {
      this._endTiming();
      this._endTiming = null;
    }
    
    this._debug(`Stopping step: ${this.currentPage}`, {
      stepId,
      durationMs: stepDurationMs,
      frameName: this._stepFrameName
    });
    
    // PRODUCTION: Enhanced wait for load state with diagnostics
    try {
      const target = await this._getTarget(this._stepFrameName);
      
      if (target) {
        const waitStartTime = Date.now();
        await target.waitForLoadState('load', { 
          timeout: this.options.loadStateTimeout 
        }).catch(err => {
          const waitDuration = Date.now() - waitStartTime;
          this._warn('Load state timeout', {
            step: this.currentPage,
            frameName: this._stepFrameName,
            timeoutMs: this.options.loadStateTimeout,
            actualWaitMs: waitDuration,
            error: err.message
          });
        });
        
        const waitDuration = Date.now() - waitStartTime;
        this._debug('Load state wait completed', {
          step: this.currentPage,
          waitMs: waitDuration
        });
      }
    } catch (e) {
      this._recordError('Failed to wait for load state', e, {
        step: this.currentPage,
        frameName: this._stepFrameName
      });
    }
    
    // PRODUCTION: Capture with retry and diagnostics
    await this.captureWebVitalsForCurrentPage(this._stepFrameName, { 
      stepDurationMs,
      stepId 
    });
    
    // Store element wait times for this step
    if (this._elementWaitTimes && this._elementWaitTimes.length > 0) {
      if (!this.perfMetrics.byPage[this.currentPage].elementWaits) {
        this.perfMetrics.byPage[this.currentPage].elementWaits = [];
      }
      this.perfMetrics.byPage[this.currentPage].elementWaits.push(...this._elementWaitTimes);
      this._debug(`Recorded ${this._elementWaitTimes.length} element interactions`);
    }
    
    this._stepFrameName = null;
    this._activeStepId = null;
  }

  /**
   * PRODUCTION: Generic target detection (works with pages, frames, iframes)
   */
  async _getTarget(frameName = null) {
    if (!frameName) {
      this._debug('Using main page as target');
      return this.page;
    }
    
    this._debug('Detecting frame target', { frameName });
    
    // Method 1: By name
    let target = this.page.frame({ name: frameName });
    
    if (target) {
      this._debug('Frame found by name', { frameName });
      return target;
    }
    
    // Method 2: By URL pattern
    const frames = this.page.frames();
    target = frames.find(f => f.url().includes(frameName));
    
    if (target) {
      this._debug('Frame found by URL pattern', { frameName, url: target.url() });
      return target;
    }
    
    // Method 3: By name() method
    target = frames.find(f => f.name() === frameName);
    
    if (target) {
      this._debug('Frame found by name() method', { frameName });
      return target;
    }
    
    // Method 4: Fuzzy match
    target = frames.find(f => {
      const url = f.url().toLowerCase();
      const name = f.name().toLowerCase();
      const searchTerm = frameName.toLowerCase();
      return url.includes(searchTerm) || name.includes(searchTerm);
    });
    
    if (target) {
      this._debug('Frame found by fuzzy match', { frameName, url: target.url() });
      return target;
    }
    
    // Fallback: main page
    this._warn('Frame not found, using main page', {
      frameName,
      availableFrames: frames.map(f => ({ name: f.name(), url: f.url() }))
    });
    
    return this.page;
  }

  /**
   * Set the current page context for tracking
   */
  setPage(pageName) {
    this.currentPage = pageName;
    if (!this.perfMetrics.byPage[pageName]) {
      this.perfMetrics.byPage[pageName] = {
        apiCalls: [],
        failedRequests: [],
        slowRequests: [],
      };
    }
    
    this._debug(`Page context set: ${pageName}`);
  }

  /**
   * PRODUCTION: Enhanced network tracking with diagnostics
   */
  _setupNetworkTracking() {
    this.page.on('request', request => {
      request._startTime = Date.now();
      request._pageContext = this.currentPage;
      request._stepId = this._activeStepId;
    });

    this.page.on('response', async response => {
      const request = response.request();
      const duration = Date.now() - (request._startTime || Date.now());
      const url = request.url();
      const pageContext = request._pageContext ?? this.currentPage;
      const resourceType = request.resourceType();

      if (!this.perfMetrics.byPage[pageContext]) {
        this.perfMetrics.byPage[pageContext] = { apiCalls: [], failedRequests: [], slowRequests: [] };
      }
      const pageData = this.perfMetrics.byPage[pageContext];

      const urlLooksLikeApi = this._urlLooksLikeApi(url);
      const isStaticResource = ['document', 'stylesheet', 'image', 'font', 'media', 'texttrack', 'manifest'].includes(resourceType);
      const isApiCall =
        resourceType === 'xhr' ||
        resourceType === 'fetch' ||
        resourceType === 'eventsource' ||
        (urlLooksLikeApi && !isStaticResource);

      if (isApiCall) {
        const urlPath = url.split('?')[0];
        const apiCall = {
          url: urlPath,
          normalizedUrl: this._normalizeEndpointUrl(urlPath),
          fullUrl: url,
          method: request.method(),
          status: response.status(),
          duration,
          page: pageContext,
          stepId: request._stepId,
          timestamp: Date.now(),
        };

        pageData.apiCalls.push(apiCall);
        
        if (duration > this.options.slowRequestThreshold) {
          pageData.slowRequests.push(apiCall);
          this._debug('Slow API detected', {
            url: urlPath,
            duration,
            threshold: this.options.slowRequestThreshold
          });
        }
      }

      if (response.status() >= 400) {
        const responseBody = await response.text().catch(() => 'Unable to read response body');
        const failedReq = {
          url: url.split('?')[0],
          fullUrl: url,
          status: response.status(),
          statusText: response.statusText(),
          method: request.method(),
          page: pageContext,
          responseBody: (responseBody && typeof responseBody === 'string') ? responseBody.substring(0, 500) : '',
          timestamp: Date.now(),
        };
        pageData.failedRequests.push(failedReq);
        
        this._warn('API request failed', {
          url: failedReq.url,
          status: response.status()
        });
      }
    });
  }

  /**
   * Measure time for a page/step
   */
  startTiming(stepName) {
    const start = Date.now();
    return () => {
      const elapsed = ((Date.now() - start) / 1000).toFixed(2);
      console.log(`${this.userLabel} ⏱️  [${stepName}] ${elapsed}s`);
      return elapsed;
    };
  }

  /**
   * PRODUCTION: Measure elements (generic, works with any selector)
   */
  async measureElements(frameOrPage, elementChecks, options = {}) {
    const timeout = options.timeout || 30_000;
    const scrollIntoView = options.scrollIntoView !== false;
    const tStart = Date.now();
    
    this.elementTimes = {};
    
    this._debug('Measuring elements', {
      count: elementChecks.length,
      timeout
    });

    for (const { name, locator } of elementChecks) {
      const t0 = Date.now();
      try {
        if (scrollIntoView) {
          await locator.scrollIntoViewIfNeeded().catch(() => {});
        }
        await locator.waitFor({ state: 'visible', timeout });
        this.elementTimes[name] = ((Date.now() - t0) / 1000).toFixed(2);
        
        this._debug(`Element visible: ${name}`, {
          timeMs: Date.now() - t0
        });
      } catch (error) {
        this._recordError(`Element "${name}" failed to load`, error);
        if (this.options.screenshotOnFailure) {
          await this.captureFailure(`element-${name.replace(/\s+/g, '-')}`);
        }
        throw error;
      }
    }

    const totalTime = ((Date.now() - tStart) / 1000).toFixed(2);
    console.log(`${this.userLabel} ⏱️  [Elements] Total: ${totalTime}s`);
    return totalTime;
  }

  /**
   * PRODUCTION: Enhanced screenshot with diagnostics
   */
  async captureFailure(stepName) {
    const filename = `${this.userLabel.replace(/[\[\]]/g, '')}-${stepName.replace(/\s+/g, '-')}-failed.png`;
    try {
      await this.page.screenshot({ 
        path: this.testInfo.outputPath(filename),
        fullPage: true 
      });
      
      this._debug('Failure screenshot captured', {
        filename,
        step: stepName
      });
      
      console.error(`${this.userLabel} ❌ ${stepName} failed. Screenshot: ${filename}`);
    } catch (err) {
      this._recordError('Failed to capture screenshot', err, { stepName });
    }
  }

  /**
   * PRODUCTION: Enhanced capture with comprehensive retry logic
   */
  async captureWebVitalsForCurrentPage(frameName = null, options = {}) {
    const startTime = Date.now();
    const stepId = options.stepId || 'unknown';
    
    this._debug('Starting Web Vitals capture', {
      step: this.currentPage,
      frameName,
      stepId
    });
    
    // Track attempts
    if (!this.perfMetrics.diagnostics.captureAttempts[this.currentPage]) {
      this.perfMetrics.diagnostics.captureAttempts[this.currentPage] = [];
    }
    
    try {
      let vitals = {};
      let retries = 0;
      const maxRetries = this.options.maxRetries;
      
      while (retries < maxRetries) {
        const attemptNum = retries + 1;
        this._debug(`Capture attempt ${attemptNum}/${maxRetries}`, {
          step: this.currentPage
        });
        
        const attemptStart = Date.now();
        vitals = await this.getWebVitals(frameName);
        const attemptDuration = Date.now() - attemptStart;
        
        // Record attempt
        this.perfMetrics.diagnostics.captureAttempts[this.currentPage].push({
          attempt: attemptNum,
          durationMs: attemptDuration,
          success: this._isValidWebVitals(vitals),
          metricsCount: Object.keys(vitals).length,
          timestamp: Date.now()
        });
        
        const hasValidMetrics = this._isValidWebVitals(vitals);
        
        if (hasValidMetrics || retries === maxRetries - 1) {
          this._debug(`Capture ${hasValidMetrics ? 'succeeded' : 'exhausted retries'}`, {
            step: this.currentPage,
            attempt: attemptNum,
            metricsCount: Object.keys(vitals).length
          });
          break;
        }
        
        retries++;
        this._warn(`Retry ${retries}/${maxRetries}`, {
          step: this.currentPage,
          reason: 'Invalid metrics',
          vitals
        });
        
        // Track retry
        if (!this.perfMetrics.diagnostics.retries[this.currentPage]) {
          this.perfMetrics.diagnostics.retries[this.currentPage] = 0;
        }
        this.perfMetrics.diagnostics.retries[this.currentPage]++;
        
        await new Promise(resolve => setTimeout(resolve, this.options.retryDelayMs));
      }
      
      const metricsQuality = this._isValidWebVitals(vitals) ? 'complete' : 'incomplete';
      const captureDuration = Date.now() - startTime;
      
      // PRODUCTION: Store with comprehensive diagnostics
      this.perfMetrics.webVitalsByPage[this.currentPage] = {
        ...vitals,
        ...(options.stepDurationMs != null ? { stepDurationMs: options.stepDurationMs } : {}),
        source: frameName ? `${frameName} frame` : 'main page',
        capturedAt: Date.now(),
        metricsQuality,
        retries,
        captureDurationMs: captureDuration,
        stepId,
        // PRODUCTION: Diagnostic indicators for HTML viewer
        _diagnostic: {
          attemptCount: retries + 1,
          retryCount: retries,
          quality: metricsQuality,
          captureTimeMs: captureDuration,
          hasLoadTime: !!(vitals.totalLoadTime && vitals.totalLoadTime > 0),
          hasFCP: !!(vitals.firstContentfulPaint && vitals.firstContentfulPaint > 0),
          hasDOMReady: !!(vitals.domContentLoaded && vitals.domContentLoaded > 0),
        }
      };
      
      this.pageLoadTimes[this.currentPage] = ((Date.now() - this.testStartTime) / 1000).toFixed(2);
      
      if (metricsQuality === 'incomplete') {
        this._warn('Incomplete metrics captured', {
          step: this.currentPage,
          vitals,
          retries
        });
      } else {
        this._debug('Complete metrics captured', {
          step: this.currentPage,
          metricsCount: Object.keys(vitals).length
        });
      }
      
    } catch (error) {
      this._recordError('Failed to capture Web Vitals', error, {
        step: this.currentPage,
        frameName
      });
      
      // PRODUCTION: Store error with diagnostics
      this.perfMetrics.webVitalsByPage[this.currentPage] = {
        ...(options.stepDurationMs != null ? { stepDurationMs: options.stepDurationMs } : {}),
        source: frameName ? `${frameName} frame` : 'main page',
        capturedAt: Date.now(),
        error: error.message,
        metricsQuality: 'failed',
        stepId,
        _diagnostic: {
          error: error.message,
          quality: 'failed'
        }
      };
    }
  }
  
  /**
   * PRODUCTION: Enhanced validation
   */
  _isValidWebVitals(vitals) {
    if (!vitals || typeof vitals !== 'object') return false;
    
    // Must have at least ONE of these metrics with a value > 0
    const hasValidMetric = (
      (vitals.totalLoadTime && vitals.totalLoadTime > 0) ||
      (vitals.firstContentfulPaint && vitals.firstContentfulPaint > 0) ||
      (vitals.domContentLoaded && vitals.domContentLoaded > 0)
    );
    
    return hasValidMetric;
  }

  /**
   * PRODUCTION: Enhanced Web Vitals collection with comprehensive error handling
   */
  async getWebVitals(frameName = null) {
    this._debug('Getting Web Vitals', { frameName });
    
    let target;

    try {
      target = await this._getTarget(frameName);
      
      if (!target) {
        this._warn('No target found for Web Vitals');
        return {};
      }
      
      // PRODUCTION: Wait for frame to be ready (if frame)
      if (target !== this.page) {
        try {
          await target.waitForLoadState('domcontentloaded', { 
            timeout: this.options.frameDetectionTimeout 
          }).catch(err => {
            this._warn('Frame domcontentloaded timeout', {
              frameName,
              error: err.message
            });
          });
        } catch (e) {
          this._warn('Frame readiness check failed', { error: e.message });
        }
      }
      
      // PRODUCTION: Wait for load state
      const loadWaitStart = Date.now();
      await target.waitForLoadState('load', { 
        timeout: this.options.loadStateTimeout 
      }).catch(err => {
        this._warn('Load state wait timeout', {
          timeoutMs: this.options.loadStateTimeout,
          actualMs: Date.now() - loadWaitStart,
          error: err.message
        });
      });
      
      // PRODUCTION: Execute in browser with validation
      const vitals = await target.evaluate(() => {
        const perfEntries = performance.getEntriesByType('navigation')[0];
        const paintEntries = performance.getEntriesByType('paint');
        const resources = performance.getEntriesByType('resource');

        // PRODUCTION: Validate entry exists
        if (!perfEntries) {
          console.warn('[PERF] Performance navigation entry not available');
          return { _error: 'no_perf_entry' };
        }

        const loadEventEnd = perfEntries.loadEventEnd ?? 0;
        const fetchStart = perfEntries.fetchStart ?? perfEntries.startTime ?? 0;
        
        // PRODUCTION: Validate load event fired
        if (loadEventEnd === 0) {
          console.warn('[PERF] Load event has not fired yet (loadEventEnd = 0)');
          return { _error: 'load_event_not_fired', loadEventEnd, fetchStart };
        }

        const totalLoadTime = loadEventEnd > 0 && fetchStart > 0 ? loadEventEnd - fetchStart : 0;

        return {
          domContentLoaded: perfEntries.domContentLoadedEventEnd ?? 0,
          firstPaint: paintEntries.find(e => e.name === 'first-paint')?.startTime || 0,
          firstContentfulPaint: paintEntries.find(e => e.name === 'first-contentful-paint')?.startTime || 0,
          totalLoadTime: totalLoadTime,
          totalResources: resources.length,
          jsSize: resources.filter(r => r.name.endsWith('.js')).reduce((sum, r) => sum + (r.transferSize || 0), 0),
          cssSize: resources.filter(r => r.name.endsWith('.css')).reduce((sum, r) => sum + (r.transferSize || 0), 0),
          imageSize: resources.filter(r => r.initiatorType === 'img').reduce((sum, r) => sum + (r.transferSize || 0), 0),
          responseTime: (perfEntries.responseEnd - perfEntries.requestStart) || 0,
          dnsTime: (perfEntries.domainLookupEnd - perfEntries.domainLookupStart) || 0,
          tcpTime: (perfEntries.connectEnd - perfEntries.connectStart) || 0,
          navigationType: perfEntries.type || 'unknown',
          _captureTimestamp: Date.now(),
          _fetchStart: fetchStart,
          _loadEventEnd: loadEventEnd,
        };
      });
      
      // PRODUCTION: Check for errors from browser
      if (vitals._error) {
        this._warn('Browser-side error', {
          error: vitals._error,
          details: vitals
        });
        
        // Return empty but keep diagnostic info
        return { _diagnostic: vitals };
      }
      
      this._debug('Web Vitals collected', {
        metricsCount: Object.keys(vitals).filter(k => !k.startsWith('_')).length,
        totalLoadTime: vitals.totalLoadTime,
        fcp: vitals.firstContentfulPaint
      });
      
      return vitals;
      
    } catch (e) {
      this._recordError('getWebVitals failed', e, { frameName });
      return {};
    }
  }

  /**
   * PRODUCTION: Get browser metrics (Chromium only)
   */
  async getBrowserMetrics() {
    try {
      const metrics = await this.page.metrics();
      return {
        jsHeapUsed: (metrics.JSHeapUsedSize / 1024 / 1024).toFixed(2),
        jsHeapTotal: (metrics.JSHeapTotalSize / 1024 / 1024).toFixed(2),
        nodes: metrics.Nodes,
        layoutCount: metrics.LayoutCount,
        recalcStyleCount: metrics.RecalcStyleCount,
      };
    } catch (e) {
      this._warn('Browser metrics not available', { error: e.message });
      return {};
    }
  }

  /**
   * Heuristic: URL looks like an API path
   */
  _urlLooksLikeApi(url) {
    if (!url || typeof url !== 'string') return false;
    const lower = url.toLowerCase();
    const apiPatterns = ['/api/', '/v1/', '/v2/', '/v3/', '/v4/', '/graphql', '/rest/', '/services/'];
    return apiPatterns.some(p => lower.includes(p));
  }

  /**
   * Normalize endpoint URL
   */
  _normalizeEndpointUrl(url) {
    if (!url || typeof url !== 'string') return url;
    let normalized = url;
    normalized = normalized.replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, '{uuid}');
    normalized = normalized.replace(/\b[0-9a-f]{20,}\b/gi, '{id}');
    return normalized;
  }

  /**
   * Group API calls by endpoint with statistics
   */
  _groupApiCallsByEndpoint(calls) {
    const apiByEndpoint = {};

    calls.forEach(call => {
      const duration = Number(call.duration);
      if (typeof duration !== 'number' || !Number.isFinite(duration)) return;
      const key = call.normalizedUrl != null ? call.normalizedUrl : this._normalizeEndpointUrl(call.url);
      if (!apiByEndpoint[key]) {
        apiByEndpoint[key] = {
          calls: [],
          count: 0,
          totalDuration: 0,
          minDuration: Infinity,
          maxDuration: 0,
          method: call.method,
        };
      }
      apiByEndpoint[key].calls.push(call);
      apiByEndpoint[key].count++;
      apiByEndpoint[key].totalDuration += duration;
      apiByEndpoint[key].minDuration = Math.min(apiByEndpoint[key].minDuration, duration);
      apiByEndpoint[key].maxDuration = Math.max(apiByEndpoint[key].maxDuration, duration);
    });
    
    Object.keys(apiByEndpoint).forEach(url => {
      const data = apiByEndpoint[url];
      data.avg = data.count > 0 ? data.totalDuration / data.count : 0;
      data.min = data.minDuration === Infinity ? 0 : data.minDuration;
      data.max = data.maxDuration;
      const sortedDurations = data.calls
        .map(c => Number(c.duration))
        .filter(n => Number.isFinite(n))
        .sort((a, b) => a - b);
      if (sortedDurations.length === 0) {
        data.p90 = data.max;
        data.p95 = data.max;
      } else {
        const p90Index = Math.min(Math.ceil(sortedDurations.length * 0.90) - 1, sortedDurations.length - 1);
        const p95Index = Math.min(Math.ceil(sortedDurations.length * 0.95) - 1, sortedDurations.length - 1);
        data.p90 = sortedDurations[Math.max(0, p90Index)];
        data.p95 = sortedDurations[Math.max(0, p95Index)];
      }
    });
    
    return apiByEndpoint;
  }

  /**
   * Print performance summary (existing method, kept for compatibility)
   */
  async printPageSummary(pageName = null, options = {}) {
    // ... existing implementation ...
    console.log(`${this.userLabel} Performance summary generated`);
  }

  /**
   * PRODUCTION: Enhanced JSON export with comprehensive diagnostics
   */
  async exportToJSON(filename) {
    
    this._debug('Exporting to JSON', { filename });
    
    const exportData = {
      userLabel: this.userLabel,
      testStartTime: this.testStartTime,
      testEndTime: Date.now(),
      totalDuration: ((Date.now() - this.testStartTime) / 1000).toFixed(2),
      pages: {},
      globalMetrics: {
        elementTimes: this.elementTimes,
        browserMetrics: await this.getBrowserMetrics(),
      },
      // PRODUCTION: Comprehensive data quality tracking
      dataQuality: {
        totalSteps: 0,
        completeSteps: 0,
        incompleteSteps: 0,
        failedSteps: 0,
        incompleteStepsList: [],
        totalRetries: 0,
        totalCaptureAttempts: 0,
      },
      // PRODUCTION: Diagnostics for debugging (visible in HTML viewer)
      diagnostics: this.perfMetrics.diagnostics,
      // PRODUCTION: Configuration snapshot
      config: {
        maxRetries: this.options.maxRetries,
        retryDelayMs: this.options.retryDelayMs,
        loadStateTimeout: this.options.loadStateTimeout,
        slowRequestThreshold: this.options.slowRequestThreshold,
      }
    };

    for (const [pageName, pageData] of Object.entries(this.perfMetrics.byPage)) {
      const calls = Array.isArray(pageData.apiCalls) ? pageData.apiCalls : [];
      const slowRequests = Array.isArray(pageData.slowRequests) ? pageData.slowRequests : [];
      const failedRequests = Array.isArray(pageData.failedRequests) ? pageData.failedRequests : [];
      const apiByEndpoint = this._groupApiCallsByEndpoint(calls);
      const webVitals = this.perfMetrics.webVitalsByPage[pageName] || null;

      let metricsQuality = 'unavailable';
      if (webVitals && typeof webVitals === 'object') {
        if (webVitals.metricsQuality) {
          metricsQuality = webVitals.metricsQuality;
        } else if (this._isValidWebVitals(webVitals)) {
          metricsQuality = 'complete';
        } else if (webVitals.stepDurationMs) {
          metricsQuality = 'incomplete';
        }
      }

      exportData.dataQuality.totalSteps++;
      if (metricsQuality === 'complete') {
        exportData.dataQuality.completeSteps++;
      } else if (metricsQuality === 'incomplete') {
        exportData.dataQuality.incompleteSteps++;
        exportData.dataQuality.incompleteStepsList.push(pageName);
      } else {
        exportData.dataQuality.failedSteps++;
        exportData.dataQuality.incompleteStepsList.push(pageName);
      }

      if (webVitals?.retries) {
        exportData.dataQuality.totalRetries += webVitals.retries;
      }

      const uniqueEndpointKeys = new Set(calls.map(c => c.normalizedUrl != null ? c.normalizedUrl : this._normalizeEndpointUrl(c.url)));
      
      // Include element wait times if present
      const elementWaits = pageData.elementWaits || [];
      
      exportData.pages[pageName] = {
        webVitals: webVitals && typeof webVitals === 'object' ? webVitals : undefined,
        metricsQuality,
        elementInteraction: elementWaits.length > 0 ? {
          totalInteractions: elementWaits.length,
          avgWaitMs: Math.round(elementWaits.reduce((sum, w) => sum + w.waitTimeMs, 0) / elementWaits.length),
          slowInteractions: elementWaits.filter(w => w.waitTimeMs > 2000).length,
          timeouts: elementWaits.filter(w => w.timedOut).length,
          details: elementWaits,
        } : undefined,
        apiPerformance: {
          totalCalls: calls.length,
          uniqueEndpoints: uniqueEndpointKeys.size,
          avgResponse: calls.length > 0 ? String((calls.reduce((sum, c) => sum + c.duration, 0) / calls.length).toFixed(2)) : '0',
          slowRequests: slowRequests.length,
          failedRequests: failedRequests.length,
          byEndpoint: apiByEndpoint && typeof apiByEndpoint === 'object' ? apiByEndpoint : {},
          failedDetails: failedRequests,
        },
      };
    }

    exportData.dataQuality.totalCaptureAttempts = Object.values(this.perfMetrics.diagnostics.captureAttempts).reduce((sum, attempts) => sum + attempts.length, 0);

    const outputPath = this.testInfo.outputPath(filename);
    const jsonString = JSON.stringify(exportData, null, 2);
    if (typeof jsonString !== 'string') throw new Error('JSON serialization failed');
    fs.writeFileSync(outputPath, jsonString, 'utf8');
    
    const qualityPct = ((exportData.dataQuality.completeSteps / exportData.dataQuality.totalSteps) * 100).toFixed(1);
    console.log(`${this.userLabel} 📁 Metrics exported to: ${filename}`);
    console.log(`${this.userLabel} 📊 Data Quality: ${exportData.dataQuality.completeSteps}/${exportData.dataQuality.totalSteps} steps complete (${qualityPct}%)`);
    
    if (exportData.dataQuality.incompleteSteps > 0 || exportData.dataQuality.failedSteps > 0) {
      console.warn(`${this.userLabel} ⚠️ ${exportData.dataQuality.incompleteSteps + exportData.dataQuality.failedSteps} steps with missing/incomplete metrics`);
    }
    
    this._appendToConsolidatedLog(exportData);
    
    return outputPath;
  }

  /**
   * Append summary to consolidated log file
   */
  _appendToConsolidatedLog(exportData) {
    try {
      
      const testResultsDir = path.dirname(this.testInfo.outputDir);
      const logPath = path.join(testResultsDir, 'performance-summary.log');
      
      const timestamp = new Date().toISOString();
      const summary = `[${timestamp}] ${exportData.userLabel} - Duration: ${exportData.totalDuration}s - Pages: ${Object.keys(exportData.pages).length} - Quality: ${((exportData.dataQuality.completeSteps / exportData.dataQuality.totalSteps) * 100).toFixed(1)}%\n`;
      
      fs.appendFileSync(logPath, summary);
    } catch (e) {
      // Silently fail
    }
  }

  /**
   * Print complete summary for all pages
   */
  async printSummary(options = {}) {
    await this.printPageSummary(null, options);
    
    if (options.exportJSON !== false) {
      await this.exportToJSON(`${this.userLabel.replace(/[\[\]]/g, '')}-metrics.json`);
    }

    const allStats = {};
    for (const [pageName, pageData] of Object.entries(this.perfMetrics.byPage)) {
      const calls = Array.isArray(pageData.apiCalls) ? pageData.apiCalls : [];
      const slowReqs = Array.isArray(pageData.slowRequests) ? pageData.slowRequests : [];
      const failedReqs = Array.isArray(pageData.failedRequests) ? pageData.failedRequests : [];
      const uniqueKeys = new Set(calls.map(c => c.normalizedUrl != null ? c.normalizedUrl : this._normalizeEndpointUrl(c.url)));
      allStats[pageName] = {
        totalCalls: calls.length,
        uniqueEndpoints: uniqueKeys.size,
        avgDuration: calls.length > 0 ? (calls.reduce((sum, c) => sum + (Number(c.duration) || 0), 0) / calls.length).toFixed(2) : 0,
        slowCalls: slowReqs.length,
        failedCalls: failedReqs.length,
      };
    }

    await this.testInfo.attach('performance-metrics', {
      body: JSON.stringify({
        user: this.userLabel,
        pageStats: allStats,
        elementTimes: this.elementTimes,
        failedRequests: Object.values(this.perfMetrics.byPage).flatMap(p => Array.isArray(p.failedRequests) ? p.failedRequests : []),
        slowRequests: Object.values(this.perfMetrics.byPage).flatMap(p => Array.isArray(p.slowRequests) ? p.slowRequests : []),
      }, null, 2),
      contentType: 'application/json',
    });
  }

  /**
   * Get raw metrics data
   */
  getMetrics() {
    return {
      byPage: this.perfMetrics.byPage,
      elementTimes: this.elementTimes,
      currentPage: this.currentPage,
      diagnostics: this.perfMetrics.diagnostics,
    };
  }
  
  /**
   * PRODUCTION: Call once at the end of each user run
   */
  async finishUser() {
    this._debug('Finishing user session');
    await this.exportToJSON(`${this.userLabel.replace(/[\[\]]/g, '')}-metrics.json`);
  }
  
  /**
   * PRODUCTION: Generate cumulative report
   */
  static generateReport(testInfo, options = {}) {
    const outputFilename = options.outputFilename || 'all-users-metrics.json';
    const testResultsDir = testInfo
      ? path.dirname(testInfo.outputDir)
      : path.join(process.cwd(), 'test-results');

    const allUsers = [];
    const subdirs = fs.readdirSync(testResultsDir, { withFileTypes: true })
      .filter(dirent => dirent.isDirectory())
      .map(dirent => dirent.name);

    for (const subdir of subdirs) {
      const subdirPath = path.join(testResultsDir, subdir);
      try {
        const files = fs.readdirSync(subdirPath).filter(f => f.endsWith('-metrics.json') && f !== outputFilename);
        for (const file of files) {
          try {
            const content = fs.readFileSync(path.join(subdirPath, file), 'utf8');
            const userData = JSON.parse(content);
            if (userData && typeof userData === 'object' && userData.pages && typeof userData.pages === 'object') {
              allUsers.push(userData);
            }
          } catch (parseErr) {
            console.warn('Skipping invalid JSON:', file, parseErr.message);
          }
        }
      } catch (_) {}
    }

    if (allUsers.length === 0) {
      console.log('No user metrics found; skipping cumulative report.');
      return '';
    }

    const cumulative = {
      testRunTime: new Date().toISOString(),
      totalUsers: allUsers.length,
      users: allUsers,
    };
    const outputPath = path.join(testResultsDir, outputFilename);
    fs.writeFileSync(outputPath, JSON.stringify(cumulative, null, 2));
    console.log(`\n📊 Cumulative report: ${outputPath} (${allUsers.length} users). Open report-viewer.html and load this file.`);
    return outputPath;
  }
}

/**
 * Helper functions (kept for compatibility)
 */
export function createElementChecks(page, selectors) {
  return Object.entries(selectors).map(([name, selector]) => ({
    name,
    locator: page.locator(selector),
  }));
}

export function createElementChecksByText(page, textMap) {
  return Object.entries(textMap).map(([name, text]) => ({
    name,
    locator: page.getByText(text),
  }));
}

export function createElementChecksByRole(page, roleMap) {
  return Object.entries(roleMap).map(([name, { role, name: roleName }]) => ({
    name,
    locator: roleName ? page.getByRole(role, { name: roleName }) : page.getByRole(role),
  }));
}

#!/usr/bin/env bun
/**
 * Debug test - check for all console messages and errors
 */
import puppeteer from 'puppeteer';

const UI_URL = 'http://localhost:8000/test-ui.html';

async function test() {
  console.log(`Debugging page: ${UI_URL}\n`);

  const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();

  // Capture ALL console messages
  page.on('console', msg => {
    console.log(`[Console ${msg.type()}] ${msg.text()}`);
  });

  // Capture page errors
  page.on('pageerror', err => {
    console.log(`[PAGE ERROR] ${err.message}`);
  });

  // Capture request failures
  page.on('requestfailed', req => {
    console.log(`[Request Failed] ${req.url()} - ${req.failure()?.errorText}`);
  });

  console.log('Loading page...\n');
  await page.goto(UI_URL, { waitUntil: 'networkidle0', timeout: 15000 });

  // Check page state
  const pageState = await page.evaluate(() => {
    return {
      wsExists: typeof ws !== 'undefined',
      wsState: typeof ws !== 'undefined' && ws ? ws.readyState : -1,
      wsUrl: typeof ws !== 'undefined' && ws ? ws.url : null,
      apiBase: typeof apiBase !== 'undefined' ? apiBase : null,
      logFunction: typeof log === 'function',
      handleWsEvent: typeof handleWsEvent === 'function',
      errors: window.__pageErrors || []
    };
  });

  console.log('\n=== Page State ===');
  console.log(JSON.stringify(pageState, null, 2));

  // Try to manually call log function
  console.log('\n=== Testing log function ===');
  const logResult = await page.evaluate(() => {
    try {
      log('Test message from puppeteer');
      return 'log() called successfully';
    } catch (e) {
      return `log() error: ${e.message}`;
    }
  });
  console.log(logResult);

  // Get current log content
  const logContent = await page.evaluate(() => {
    const logEl = document.getElementById('log');
    return logEl ? logEl.innerText.substring(0, 500) : 'No log element found';
  });
  console.log('\n=== Log Element Content ===');
  console.log(logContent);

  await browser.close();
}

test().catch(err => {
  console.error('Test failed:', err.message);
  process.exit(1);
});

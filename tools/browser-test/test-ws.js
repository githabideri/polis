#!/usr/bin/env bun
/**
 * Browser-based WebSocket test for test-ui.html
 * Captures console logs and WebSocket activity
 */
import puppeteer from 'puppeteer';

const UI_URL = process.argv[2] || 'http://localhost:8000/test-ui.html';

async function testWebSocket() {
  console.log(`Testing WebSocket via browser at: ${UI_URL}\n`);

  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox']
  });

  const page = await browser.newPage();

  // Capture console logs from browser
  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    if (type === 'error') {
      console.log(`[Browser ERROR] ${text}`);
    } else if (text.includes('WebSocket') || text.includes('ws:') || text.includes('Event')) {
      console.log(`[Browser] ${text}`);
    }
  });

  // Capture page errors
  page.on('pageerror', err => {
    console.log(`[Page Error] ${err.message}`);
  });

  // Track WebSocket connections at CDP level
  const client = await page.createCDPSession();
  await client.send('Network.enable');

  client.on('Network.webSocketCreated', ({ requestId, url }) => {
    console.log(`[CDP] WebSocket created: ${url}`);
  });

  client.on('Network.webSocketFrameReceived', ({ requestId, response }) => {
    console.log(`[CDP] WS frame received: ${response.payloadData.substring(0, 100)}`);
  });

  client.on('Network.webSocketFrameSent', ({ requestId, response }) => {
    console.log(`[CDP] WS frame sent: ${response.payloadData}`);
  });

  client.on('Network.webSocketClosed', ({ requestId }) => {
    console.log(`[CDP] WebSocket closed`);
  });

  client.on('Network.webSocketFrameError', ({ requestId, errorMessage }) => {
    console.log(`[CDP] WS error: ${errorMessage}`);
  });

  // Navigate to page
  console.log('Loading page...');
  await page.goto(UI_URL, { waitUntil: 'networkidle0', timeout: 10000 });
  console.log('Page loaded, waiting for WebSocket activity...\n');

  // Wait a bit for WebSocket to connect
  await new Promise(r => setTimeout(r, 3000));

  // Check WebSocket state via page JavaScript
  const wsState = await page.evaluate(() => {
    if (typeof ws !== 'undefined' && ws) {
      return {
        readyState: ws.readyState,
        readyStateText: ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'][ws.readyState],
        url: ws.url
      };
    }
    return { error: 'ws variable not found' };
  });

  console.log(`\n[Page WS State] ${JSON.stringify(wsState)}`);

  // Wait longer to see if events come through
  console.log('\nWaiting 5 more seconds for events...');
  await new Promise(r => setTimeout(r, 5000));

  await browser.close();
  console.log('\nTest complete.');
}

testWebSocket().catch(err => {
  console.error('Test failed:', err.message);
  process.exit(1);
});

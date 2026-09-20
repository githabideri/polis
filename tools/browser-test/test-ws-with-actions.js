#!/usr/bin/env bun
/**
 * Browser WebSocket test that also triggers bot actions
 */
import puppeteer from 'puppeteer';
import { spawn } from 'child_process';

const UI_URL = 'http://localhost:8585/polis/ui';

function runCli(args) {
  return new Promise((resolve) => {
    const proc = spawn('python3', ['scripts/poliscli.py', ...args.split(' ')], {
      cwd: '/home/mf/Code/polis-builder/polis-builder-npc'
    });
    let out = '';
    proc.stdout.on('data', d => out += d);
    proc.on('close', () => resolve(out.trim()));
  });
}

async function test() {
  console.log(`Testing WebSocket with bot actions\n`);

  const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();

  // Track WebSocket frames
  const client = await page.createCDPSession();
  await client.send('Network.enable');

  let framesReceived = [];
  client.on('Network.webSocketFrameReceived', ({ response }) => {
    framesReceived.push(response.payloadData);
    console.log(`[WS Received] ${response.payloadData.substring(0, 120)}`);
  });

  client.on('Network.webSocketFrameSent', ({ response }) => {
    console.log(`[WS Sent] ${response.payloadData}`);
  });

  // Load page
  await page.goto(UI_URL, { waitUntil: 'networkidle0', timeout: 10000 });
  console.log('Page loaded, WebSocket connecting...\n');

  // Wait for WebSocket to be ready
  await new Promise(r => setTimeout(r, 2000));

  // Verify WebSocket state
  const wsState = await page.evaluate(() => {
    return typeof ws !== 'undefined' && ws ? ws.readyState : -1;
  });
  console.log(`WebSocket readyState: ${wsState} (1=OPEN)\n`);

  if (wsState !== 1) {
    console.log('WebSocket not open, aborting');
    await browser.close();
    return;
  }

  // Now trigger actions via CLI
  console.log('--- Triggering bot actions via CLI ---\n');

  console.log('1. Spawning bot...');
  await runCli('spawn');
  await new Promise(r => setTimeout(r, 1500));

  console.log('2. Giving item...');
  await runCli('give game:stone-granite 2');
  await new Promise(r => setTimeout(r, 1500));

  console.log('3. Dropping item...');
  await runCli('drop');
  await new Promise(r => setTimeout(r, 1500));

  console.log('4. Despawning...');
  await runCli('despawn');
  await new Promise(r => setTimeout(r, 1500));

  console.log(`\n--- Results ---`);
  console.log(`Total WebSocket frames received: ${framesReceived.length}`);

  if (framesReceived.length === 0) {
    console.log('\nNO EVENTS RECEIVED - There may be a server-side issue with broadcasting');
  } else {
    console.log('\nEvents received:');
    framesReceived.forEach((f, i) => {
      try {
        const event = JSON.parse(f);
        console.log(`  ${i+1}. ${event.type}`);
      } catch {
        console.log(`  ${i+1}. (non-JSON): ${f.substring(0, 50)}`);
      }
    });
  }

  await browser.close();
}

test().catch(err => {
  console.error('Test failed:', err.message);
  process.exit(1);
});

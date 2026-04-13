import { chromium } from 'playwright';
import { PROTOTYPE_NORMALIZE_CSS } from './visual-audit.config.mjs';

const VIEWPORT = { width: 1536, height: 900 };

async function main() {
  const browser = await chromium.launch({ channel: 'chromium' });
  
  // React: check pulse area colors
  const reactCtx = await browser.newContext({ viewport: VIEWPORT });
  const reactPage = await reactCtx.newPage();
  await reactPage.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
  await reactPage.waitForTimeout(300);
  
  const reactPulse = await reactPage.evaluate(() => {
    const slot = document.querySelector('[data-slot="pulse"]');
    const strip = document.querySelector('[data-slot="pulse-strip"]');
    return {
      slotBg: slot ? getComputedStyle(slot).backgroundColor : 'NOT FOUND',
      slotH: slot ? getComputedStyle(slot).height : 'NOT FOUND',
      stripBg: strip ? getComputedStyle(strip).backgroundColor : 'NOT FOUND',
      stripH: strip ? getComputedStyle(strip).height : 'NOT FOUND',
      stripW: strip ? getComputedStyle(strip).width : 'NOT FOUND',
    };
  });
  
  // Prototype: check pulse area colors
  const protoCtx = await browser.newContext({ viewport: VIEWPORT });
  const protoPage = await protoCtx.newPage();
  await protoPage.goto('http://localhost:8888/page-home.html', { waitUntil: 'networkidle' });
  await protoPage.addStyleTag({ content: PROTOTYPE_NORMALIZE_CSS });
  await protoPage.waitForTimeout(300);
  
  const protoPulse = await protoPage.evaluate(() => {
    const shell = document.querySelector('.shell-pulse');
    return {
      shellBg: shell ? getComputedStyle(shell).backgroundColor : 'NOT FOUND',
      shellH: shell ? getComputedStyle(shell).height : 'NOT FOUND',
    };
  });
  
  await browser.close();
  
  console.log('=== Pulse Strip Background Comparison ===\n');
  console.log('Prototype .shell-pulse:');
  console.log(`  bg: ${protoPulse.shellBg}`);
  console.log(`  h:  ${protoPulse.shellH}`);
  console.log('\nReact [data-slot="pulse"] (outer):');
  console.log(`  bg: ${reactPulse.slotBg}`);
  console.log(`  h:  ${reactPulse.slotH}`);
  console.log('\nReact [data-slot="pulse-strip"] (inner):');
  console.log(`  bg: ${reactPulse.stripBg}`);
  console.log(`  h:  ${reactPulse.stripH}`);
  console.log(`  w:  ${reactPulse.stripW}`);
}

main().catch(console.error);

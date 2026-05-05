import { chromium } from 'playwright';
import { PROTOTYPE_NORMALIZE_CSS } from './visual-audit.config.mjs';

const VIEWPORT = { width: 1536, height: 900 };

async function main() {
  const browser = await chromium.launch({ channel: 'chromium' });

  // Get background colors of key elements on both sides
  const protoCtx = await browser.newContext({ viewport: VIEWPORT });
  const protoPage = await protoCtx.newPage();
  await protoPage.goto('http://localhost:8888/page-home.html', { waitUntil: 'networkidle' });
  await protoPage.addStyleTag({ content: PROTOTYPE_NORMALIZE_CSS });
  await protoPage.waitForTimeout(300);

  const protoColors = await protoPage.evaluate(() => {
    const el = (sel) => { const e = document.querySelector(sel); return e ? getComputedStyle(e).backgroundColor : 'NOT FOUND'; };
    return {
      shell: el('.shell-home'),
      main: el('.shell-main'),
      header: el('.shell-header'),
      strip: el('.shell-pulse'),
      sidebar: el('.shell-sidebar'),
      decision: el('.decision-banner'),
      queue: el('.panel-grow'),
      rail: el('.shell-rail'),
    };
  });

  const reactCtx = await browser.newContext({ viewport: VIEWPORT });
  const reactPage = await reactCtx.newPage();
  await reactPage.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
  await reactPage.waitForTimeout(300);

  const reactColors = await reactPage.evaluate(() => {
    const el = (sel) => { const e = document.querySelector(sel); return e ? getComputedStyle(e).backgroundColor : 'NOT FOUND'; };
    return {
      shell: el('#root > div'),
      main: el('[data-slot="main"]'),
      header: el('header'),
      strip: el('[data-slot="pulse"]'),
      sidebar: el('[data-slot="sidebar"]'),
      decision: el('[data-slot="decision-banner"]'),
      queue: el('[data-testid="priority-queue"]'),
      rail: el('nav[aria-label="主导航"]'),
    };
  });

  await browser.close();

  console.log('=== Background Color Comparison ===\n');
  console.log(`${'Element'.padEnd(15)} ${'Prototype'.padEnd(35)} ${'React'.padEnd(35)} ${'Match'.padEnd(6)}`);
  console.log('-'.repeat(95));

  for (const key of Object.keys(protoColors)) {
    const p = protoColors[key];
    const r = reactColors[key];
    const match = p === r ? 'YES' : (p.includes('oklch') && r.includes('oklch') ? '~' : 'NO');
    console.log(`${key.padEnd(15)} ${p.padEnd(35)} ${r.padEnd(35)} ${match}`);
  }
}

main().catch(console.error);

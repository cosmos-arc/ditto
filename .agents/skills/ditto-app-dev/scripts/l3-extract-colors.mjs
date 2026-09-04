import { chromium } from 'playwright';
import { PROTOTYPE_NORMALIZE_CSS } from './visual-audit.config.mjs';

const VIEWPORT = { width: 1536, height: 900 };

async function main() {
  const browser = await chromium.launch({ channel: 'chromium' });

  // Extract CSS variables from both sides
  const protoCtx = await browser.newContext({ viewport: VIEWPORT });
  const protoPage = await protoCtx.newPage();
  await protoPage.goto('http://localhost:8888/page-home.html', { waitUntil: 'networkidle' });
  await protoPage.addStyleTag({ content: PROTOTYPE_NORMALIZE_CSS });

  const protoVars = await protoPage.evaluate(() => {
    const cs = getComputedStyle(document.documentElement);
    const keys = ['--brand-accent', '--color-bg-app', '--surface-frosted', '--surface-card', '--surface-panel', '--border-subtle'];
    const result = {};
    for (const k of keys) {
      result[k] = cs.getPropertyValue(k).trim();
    }
    // Also get body background
    result['body-bg'] = cs.getPropertyValue('background-color').trim();
    return result;
  });

  const reactCtx = await browser.newContext({ viewport: VIEWPORT });
  const reactPage = await reactCtx.newPage();
  await reactPage.goto('http://localhost:5173/', { waitUntil: 'networkidle' });

  const reactVars = await reactPage.evaluate(() => {
    const cs = getComputedStyle(document.documentElement);
    const keys = ['--color-accent', '--color-surface-app', '--color-surface-frosted', '--color-surface-panel-base', '--color-surface-card', '--color-border-subtle', '--color-bg-app'];
    const result = {};
    for (const k of keys) {
      result[k] = cs.getPropertyValue(k).trim();
    }
    result['body-bg'] = cs.getPropertyValue('background-color').trim();
    return result;
  });

  await browser.close();

  console.log('=== CSS Variable Comparison ===\n');
  console.log('Prototype:');
  for (const [k, v] of Object.entries(protoVars)) {
    console.log(`  ${k}: ${v || '(not set)'}`);
  }
  console.log('\nReact:');
  for (const [k, v] of Object.entries(reactVars)) {
    console.log(`  ${k}: ${v || '(not set)'}`);
  }
}

main().catch(console.error);

import { chromium } from 'playwright';
import { PROTOTYPE_NORMALIZE_CSS } from './visual-audit.config.mjs';

const VIEWPORT = { width: 1536, height: 900 };

async function main() {
  const browser = await chromium.launch({ channel: 'chromium' });

  // Sample pixels in header area from both sides
  const protoCtx = await browser.newContext({ viewport: VIEWPORT });
  const protoPage = await protoCtx.newPage();
  await protoPage.goto('http://localhost:8888/page-home.html', { waitUntil: 'networkidle' });
  await protoPage.addStyleTag({ content: PROTOTYPE_NORMALIZE_CSS });
  await protoPage.waitForTimeout(300);

  // Get header inner elements' computed styles
  const protoHeader = await protoPage.evaluate(() => {
    const header = document.querySelector('.shell-header');
    const title = header?.querySelector('.header-title');
    const search = header?.querySelector('.header-search');
    const actions = header?.querySelector('.header-actions');

    const cs = (el) => el ? getComputedStyle(el) : null;

    return {
      headerBg: cs(header)?.backgroundColor,
      headerBorder: cs(header)?.borderBottom,
      headerPadding: cs(header)?.padding,
      headerGap: cs(header)?.gap,
      titleFontSize: cs(title)?.fontSize,
      titleFontWeight: cs(title)?.fontWeight,
      titleFontFamily: cs(title)?.fontFamily?.substring(0, 50),
      searchBg: cs(search)?.backgroundColor,
      searchBorder: cs(search)?.border,
      actions: actions ? Array.from(actions.children).map(c => ({
        text: c.textContent?.substring(0, 20),
        bg: cs(c)?.backgroundColor,
        border: cs(c)?.border,
        fontSize: cs(c)?.fontSize,
      })) : [],
    };
  });

  const reactCtx = await browser.newContext({ viewport: VIEWPORT });
  const reactPage = await reactCtx.newPage();
  await reactPage.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
  await reactPage.waitForTimeout(300);

  const reactHeader = await reactPage.evaluate(() => {
    const header = document.querySelector('header');
    const buttons = header?.querySelectorAll('button');

    const cs = (el) => el ? getComputedStyle(el) : null;

    return {
      headerBg: cs(header)?.backgroundColor,
      headerBorder: cs(header)?.borderBottom,
      headerPadding: cs(header)?.padding,
      headerGap: cs(header)?.gap,
      buttons: buttons ? Array.from(buttons).slice(0, 5).map(c => ({
        text: c.textContent?.substring(0, 20),
        bg: cs(c)?.backgroundColor,
        border: cs(c)?.border,
        fontSize: cs(c)?.fontSize,
      })) : [],
    };
  });

  await browser.close();

  console.log('=== Header Detail Comparison ===\n');
  console.log('Prototype:');
  console.log(`  bg: ${protoHeader.headerBg}`);
  console.log(`  border-bottom: ${protoHeader.headerBorder}`);
  console.log(`  padding: ${protoHeader.headerPadding}`);
  console.log(`  gap: ${protoHeader.headerGap}`);
  console.log(`  title font: ${protoHeader.titleFontSize} ${protoHeader.titleFontWeight} ${protoHeader.titleFontFamily}`);
  if (protoHeader.search) console.log(`  search bg: ${protoHeader.searchBg}`);
  for (const a of protoHeader.actions) console.log(`  action: "${a.text}" bg=${a.bg} border=${a.border}`);

  console.log('\nReact:');
  console.log(`  bg: ${reactHeader.headerBg}`);
  console.log(`  border-bottom: ${reactHeader.headerBorder}`);
  console.log(`  padding: ${reactHeader.headerPadding}`);
  console.log(`  gap: ${reactHeader.headerGap}`);
  for (const b of reactHeader.buttons) console.log(`  button: "${b.text}" bg=${b.bg} border=${b.border}`);
}

main().catch(console.error);

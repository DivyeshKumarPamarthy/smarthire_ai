import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

// Repo-relative, so this works on any clone. Lives under frontend/ because
// that is where Playwright resolves from — it is a docs tool, not app code.
const REPO = path.resolve(import.meta.dirname, '..');
const SRC = path.join(REPO, 'docs', 'PROJECT_REPORT.md');
const OUT = path.join(REPO, 'docs', 'PROJECT_REPORT.pdf');

const md = fs.readFileSync(SRC, 'utf8');

// The markdown is injected as JSON so backticks, $ and quotes survive intact.
const html = `<!doctype html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<style>
  @page { size: A4; margin: 18mm 16mm; }
  body {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 10.5pt; line-height: 1.55; color: #1a1d1a; margin: 0;
  }
  h1 { font-size: 20pt; line-height: 1.2; margin: 0 0 4pt; letter-spacing: -0.01em; }
  h1 + p strong { font-weight: 600; color: #444; }
  h2 {
    font-size: 14pt; margin: 22pt 0 8pt; padding-bottom: 4pt;
    border-bottom: 1.2pt solid #1f4e4a; color: #1f4e4a;
    break-after: avoid; page-break-after: avoid;
  }
  h3 { font-size: 11.5pt; margin: 14pt 0 6pt; color: #244; break-after: avoid; page-break-after: avoid; }
  h4 { font-size: 10.5pt; margin: 11pt 0 4pt; break-after: avoid; }
  p { margin: 0 0 7pt; }
  ul, ol { margin: 0 0 8pt; padding-left: 18pt; }
  li { margin-bottom: 3pt; }
  hr { border: 0; border-top: 0.6pt solid #ccc; margin: 14pt 0; }
  code { font-family: "SF Mono", Menlo, monospace; font-size: 8.8pt; background: #f2f4f1; padding: 1pt 3pt; border-radius: 2pt; }
  strong { font-weight: 600; }

  table {
    border-collapse: collapse; width: 100%; margin: 8pt 0 12pt;
    font-size: 8.6pt; break-inside: avoid; page-break-inside: avoid;
  }
  th, td { border: 0.5pt solid #d0d6cf; padding: 4pt 6pt; text-align: left; vertical-align: top; }
  th { background: #eef2ed; font-weight: 600; }
  td code { font-size: 8pt; }

  .mermaid { text-align: center; margin: 10pt 0 14pt; break-inside: avoid; page-break-inside: avoid; }
  .mermaid svg { max-width: 100%; height: auto; }

  blockquote { margin: 8pt 0; padding-left: 10pt; border-left: 2pt solid #1f4e4a; color: #333; }
  .katex-display { margin: 10pt 0; }
  h2, h3, table, .mermaid { orphans: 3; widows: 3; }
</style></head>
<body><article id="out"></article>

<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
<script>
  const SOURCE = ${JSON.stringify(md)};
  window.__ready = false;
  window.addEventListener('load', async () => {
    // Pull mermaid blocks out before markdown parsing so they are not escaped.
    const blocks = [];
    const prepared = SOURCE.replace(/\`\`\`mermaid\\n([\\s\\S]*?)\`\`\`/g, (_, body) => {
      blocks.push(body);
      return '<div class="mermaid-slot" data-i="' + (blocks.length - 1) + '"></div>';
    });

    document.getElementById('out').innerHTML = marked.parse(prepared);

    document.querySelectorAll('.mermaid-slot').forEach(slot => {
      const d = document.createElement('div');
      d.className = 'mermaid';
      d.textContent = blocks[Number(slot.dataset.i)];
      slot.replaceWith(d);
    });

    mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose' });
    try { await mermaid.run({ querySelector: '.mermaid' }); } catch (e) { window.__mermaidError = String(e); }

    if (window.renderMathInElement) {
      renderMathInElement(document.body, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$',  right: '$',  display: false },
        ],
        throwOnError: false,
      });
    }
    window.__ready = true;
  });
</script></body></html>`;

const tmp = '/tmp/report-render.html';
fs.writeFileSync(tmp, html);

const browser = await chromium.launch();
const page = await browser.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));

await page.goto('file://' + tmp, { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.__ready === true, { timeout: 60000 });

const diag = await page.evaluate(() => ({
  mermaidSvgs: document.querySelectorAll('.mermaid svg').length,
  unrenderedSlots: document.querySelectorAll('.mermaid-slot').length,
  katex: document.querySelectorAll('.katex').length,
  tables: document.querySelectorAll('table').length,
  headings: document.querySelectorAll('h2').length,
  mermaidError: window.__mermaidError || null,
}));

await page.pdf({ path: OUT, format: 'A4', printBackground: true,
  margin: { top: '18mm', bottom: '18mm', left: '16mm', right: '16mm' } });
await browser.close();

console.log('rendered:', JSON.stringify(diag, null, 2));
console.log('page errors:', errs.length ? errs.slice(0,3) : 'none');
console.log('written:', OUT, fs.statSync(OUT).size, 'bytes');

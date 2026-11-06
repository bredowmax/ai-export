// node render.js <page.html> <out_dir> [--root SEL] [--px-per-mm N] [--wait MS]
// Renders an HTML artboard as Illustrator layers: one exact-size vector PDF per layer (shapes, pictures, graphics; no text in any of
// them), the text as blocks for native type (textblocks.js), the graphics' boxes (each <svg> or SVG <img> becomes one group), and
// the fonts the page uses (@font-face rules and the font files it loaded). ai_export.py turns these into a layered .ai.
const { chromium } = require('playwright'); const path = require('path'); const fs = require('fs');
const args = process.argv.slice(2); const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const [page, out] = args; fs.mkdirSync(out, { recursive: true });
const ROOT = opt('--root', null), PXMM = +opt('--px-per-mm', 96 / 25.4), WAIT = +opt('--wait', 800);
const HIDE_TEXT = `(root => { const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); const ns = [];
  while (w.nextNode()) if (w.currentNode.textContent.trim() && !w.currentNode.parentElement.closest('svg')) ns.push(w.currentNode);
  for (const n of ns) { const sp = document.createElement('span'); sp.style.visibility = 'hidden'; n.parentNode.insertBefore(sp, n); sp.appendChild(n); } })`;
const SVGIMG = 'img[src$=".svg"],img[src*=".svg?"],img[src^="data:image/svg"]';
const PASSES = {
  shapes:   `img,svg{visibility:hidden!important}`,
  pictures: `*{visibility:hidden!important} img:not(${SVGIMG}){visibility:visible!important}`,
  graphics: `*{visibility:hidden!important} ${SVGIMG},svg,svg *{visibility:visible!important}`,
};
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 2000, height: 2000 } }); const p = await ctx.newPage();
  const fontFiles = {}, css = []; let nfont = 0;
  p.on('response', async r => { try {
    const t = r.request().resourceType(), u = r.url();
    if (t === 'font' && !u.startsWith('file:') && !(u in fontFiles)) {   // name taken before the await: fonts arrive together
      const f = path.join(out, 'webfont_' + (nfont++) + path.extname(new URL(u).pathname).slice(0, 7)); fontFiles[u] = f; fs.writeFileSync(f, await r.body()); }
    if (t === 'stylesheet') css.push({ url: u, text: await r.text() });
  } catch (e) {} });
  const load = async () => {
    await p.goto('file://' + path.resolve(page), { waitUntil: 'networkidle' }); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(WAIT);
    return p.evaluate(sel => { const r = sel ? document.querySelector(sel) : (document.body.children.length === 1 ? document.body.children[0] : document.body);
      if (!r) return null; r.setAttribute('data-ai-root', ''); const b = r.getBoundingClientRect(); return { w: b.width, h: b.height, x: b.left, y: b.top }; }, ROOT);
  };
  const box = await load(); if (!box) { console.error('root not found'); process.exit(1); }
  if (Math.abs(box.x) > 0.5 || Math.abs(box.y) > 0.5) console.error(`warning: the artboard starts at ${box.x},${box.y} px, not the page's corner`);
  const Wmm = box.w / PXMM, Hmm = box.h / PXMM, scale = 96 / 25.4 / PXMM;
  if (scale < 0.1 || scale > 2) { console.error('--px-per-mm out of range for printing'); process.exit(1); }
  // text, graphics boxes, @font-face rules (same-origin sheets; cross-origin ones come from the responses above)
  const src = fs.readFileSync(path.join(__dirname, 'textblocks.js'), 'utf8');
  const info = await p.evaluate(({ src, PXMM }) => {
    eval(src + ';window.__pt=page_text');
    const root = document.querySelector('[data-ai-root]'), R = root.getBoundingClientRect(), PT = 72 / 25.4 / PXMM;
    const graphics = [...root.querySelectorAll('svg,img')].filter(e => (e.tagName.toLowerCase() === 'svg' && !e.parentElement.closest('svg')) || /\.svg($|\?)|^data:image\/svg/.test(e.getAttribute('src') || ''))
      .map(e => { const r = e.getBoundingClientRect(); return { name: e.getAttribute('aria-label') || e.getAttribute('alt') || e.id || (e.getAttribute('src') || '').split('/').pop().replace(/\.svg.*/, '') || 'Graphic',
        box: [(r.left - R.left) * PT, (r.top - R.top) * PT, r.width * PT, r.height * PT] }; }).filter(g => g.box[2] > 0 && g.box[3] > 0);
    const faces = [];
    for (const sh of document.styleSheets) { let rules; try { rules = sh.cssRules; } catch (e) { continue; }
      for (const r of rules) if (r.type === CSSRule.FONT_FACE_RULE) faces.push({ base: sh.href || location.href, text: r.cssText }); }
    return { text: window.__pt({ root: '[data-ai-root]', pxPerMm: PXMM }), graphics, faces };
  }, { src, PXMM });
  for (const c of css) for (const m of c.text.matchAll(/@font-face\s*\{[^}]*\}/g)) info.faces.push({ base: c.url, text: m[0] });
  fs.writeFileSync(path.join(out, 'page.json'), JSON.stringify({ width_mm: Wmm, height_mm: Hmm, ...info, fontFiles }, null, 1));
  for (const [name, css] of Object.entries(PASSES)) {
    await load();
    await p.evaluate(({ css, HIDE }) => { eval(HIDE)(document.querySelector('[data-ai-root]'));
      const s = document.createElement('style'); s.textContent = css + ';html,body:not([data-ai-root]){background:transparent!important}'; document.head.appendChild(s); }, { css, HIDE: HIDE_TEXT });
    await p.pdf({ path: path.join(out, `layer_${name}.pdf`), width: Wmm + 'mm', height: Hmm + 'mm', scale, printBackground: true, pageRanges: '1' });
  }
  await b.close(); console.log(out, info.text.length, 'text blocks', info.graphics.length, 'graphics');
})();

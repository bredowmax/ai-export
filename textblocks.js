function page_text(opts) {
  const PT = 72 / 25.4 / opts.pxPerMm;   // CSS px -> pt
  const pg = document.querySelector(opts.root);
  const metrics = opts.metrics || {};   // font key -> [ascent, descent] per em (from the font files); default below
  // measure untransformed (transforms don't change layout), then map points through the transformed ancestors ourselves
  const tf = [];
  for (const e of pg.querySelectorAll('*')) {
    const cs = getComputedStyle(e);
    if (cs.transform !== 'none') { tf.push([e, new DOMMatrix(cs.transform), cs.transformOrigin]); e.style.transform = 'none'; }
  }
  const P0 = pg.getBoundingClientRect();
  const origin = new Map();
  for (const [e, m, o] of tf) { const r = e.getBoundingClientRect(); const [ox, oy] = o.split(' ').map(parseFloat); origin.set(e, [r.left - P0.left + ox, r.top - P0.top + oy, m]); }
  const chain = e => { const c = []; for (let a = e; a && a !== pg; a = a.parentElement) if (origin.has(a)) c.push(origin.get(a)); return c; };   // innermost first
  const map = (c, x, y) => { for (const [ox, oy, m] of c) { const dx = x - ox, dy = y - oy; x = ox + m.a * dx + m.c * dy + m.e; y = oy + m.b * dx + m.d * dy + m.f; } return [x, y]; };
  const lin = c => c.reduce((acc, [, , m]) => new DOMMatrix([m.a, m.b, m.c, m.d, 0, 0]).multiply(acc), new DOMMatrix());
  const rel = r => ({ l: r.left - P0.left, t: r.top - P0.top, r: r.right - P0.left, b: r.bottom - P0.top });
  const hex = c => { const m = c.match(/[\d.]+/g).map(Number); return m.length > 3 && m[3] === 0 ? null : '#' + m.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join(''); };
  const inline = e => getComputedStyle(e).display.startsWith('inline');
  const flexrow = e => { const cs = getComputedStyle(e); return cs.display.includes('flex') && !cs.flexDirection.startsWith('column'); };
  const canvas = document.createElement('canvas').getContext('2d');
  const out = [];
  const units = new Set();
  const tw = document.createTreeWalker(pg, NodeFilter.SHOW_TEXT);
  while (tw.nextNode()) {
    const n = tw.currentNode; if (!n.textContent.trim()) continue;
    const pe = n.parentElement; if (getComputedStyle(pe).visibility === 'hidden') continue;
    const isBox = e => e === pg || ['absolute', 'fixed'].includes(getComputedStyle(e).position) || e.hasAttribute('data-text-group');
    if (pe.closest('svg')) continue;   // SVG text stays in its graphic
    let u = pe; while (u !== pg && !isBox(u.parentElement) && !u.hasAttribute('data-text')) u = u.parentElement;
    if (u === pg) u = pe;
    const ab = u.parentElement, acs = getComputedStyle(ab);   // a stack (flex column, e.g. Raw's minerals) is one object
    units.add(acs.display.includes('flex') && acs.flexDirection.startsWith('column') && ab.children.length > 1 ? ab : u);
  }
  // a boxed block (the Nutrition Facts) is never merged with the text beside it: its siblings become objects of their own (Max, 2026-11-06)
  for (const u of [...units]) {
    const kids = [...u.children].filter(e => e.innerText && e.innerText.trim());
    if (kids.length > 1 && kids.some(e => parseFloat(getComputedStyle(e).borderTopWidth) > 0)) { units.delete(u); kids.forEach(e => units.add(e)); }
  }
  for (const u of units) {
    // paragraphs: consecutive text nodes sharing their nearest block container (a flex row counts as one block)
    const paras = []; let cur = null;
    const w = document.createTreeWalker(u, NodeFilter.SHOW_TEXT);
    while (w.nextNode()) {
      const n = w.currentNode; const pe = n.parentElement;
      if (!n.textContent.trim() && !(cur && /\s/.test(n.textContent))) continue;
      const cs = getComputedStyle(pe); if (cs.visibility === 'hidden') continue;
      let blk = pe; while (blk !== u && (inline(blk) || flexrow(blk.parentElement))) blk = blk.parentElement;
      if (!cur || cur.blk !== blk) { cur = { blk, items: [] }; paras.push(cur); }
      let item = pe; while (item !== blk && item.parentElement !== blk) item = item.parentElement;   // flex row: each flex item
      cur.items.push({ n, cs, item: flexrow(blk) && item !== blk ? item : null });
    }
    if (!paras.length) continue;
    const c = chain(u), L = lin(c), sx = Math.hypot(L.a, L.b), sy = Math.hypot(L.c, L.d), rot = Math.atan2(L.b, L.a) * 180 / Math.PI;
    const ucs = getComputedStyle(u), ub = rel(u.getBoundingClientRect());
    const bb = [1e9, 1e9, -1e9, -1e9];
    // characters: [ch, style, line baseline (local px) | null for collapsible space]; lines keyed by their baseline
    const chars = []; const lineBox = new Map(); let first0 = null;   // baseline -> [left, right, size]
    const rg = document.createRange();
    paras.forEach((p, pi) => {
      if (pi) chars.push(['\n', null, null]);
      let prevItem = null, prevRight = null;
      for (const { n, cs, item } of p.items) {
        const size = parseFloat(cs.fontSize), ls = cs.letterSpacing === 'normal' ? 0 : parseFloat(cs.letterSpacing);
        const fill = hex(cs.color); if (!fill) continue;
        const font = { family: cs.fontFamily.split(',')[0].replace(/['"]/g, '').trim(), weight: +cs.fontWeight, style: cs.fontStyle,
                       stretch: cs.fontStretch, fvs: cs.fontVariationSettings, opsz: cs.fontOpticalSizing === 'auto' ? size : null };
        const s = { font: JSON.stringify(font), size: size * PT * sy, tracking: Math.round(ls / size * 1000), fill, hScale: sx / sy * 100 };
        // the baseline's offset below a glyph's box top for this font and size: a zero-size inline-block sits on the baseline
        let asc = null;
        { const m = document.createElement('span'); m.style.cssText = 'display:inline-block;width:0;height:0;margin:0;padding:0;border:0';
          n.parentNode.insertBefore(m, n); const mb = m.getBoundingClientRect().bottom; rg.setStart(n, 0); rg.setEnd(n, Math.min(1, n.length));
          const fr = [...rg.getClientRects()][0]; m.remove();
          if (fr && mb >= fr.top && mb <= fr.bottom) asc = mb - fr.top; }
        const txt = n.textContent; let firstRect = null, lastRight = null;
        for (let i = 0; i < txt.length; i++) {
          let ch = txt[i]; if (cs.textTransform === 'uppercase') ch = ch.toUpperCase();
          if (/[ \t\n\r]/.test(ch)) { chars.push([' ', s, null]); continue; }
          rg.setStart(n, i); rg.setEnd(n, i + 1); const r = [...rg.getClientRects()].map(rel)[0];
          if (!r) continue;
          const base = r.t + (asc ?? (r.b - r.t) * 0.78); if (!first0) first0 = { asc: asc ?? (r.b - r.t) * 0.78 }; const key = Math.round(base * 4) / 4;
          let k = [...lineBox.keys()].find(q => Math.abs(q - key) < size * 0.3); if (k === undefined) { k = key; lineBox.set(k, [r.l, r.r, size]); }
          const lb = lineBox.get(k); lb[0] = Math.min(lb[0], r.l); lb[1] = Math.max(lb[1], r.r); lb[2] = Math.max(lb[2], size);
          for (const [X_, Y_] of [[r.l, r.t], [r.r, r.t], [r.l, r.b], [r.r, r.b]]) { const [X, Y] = map(c, X_, Y_); bb[0] = Math.min(bb[0], X * PT); bb[1] = Math.min(bb[1], Y * PT); bb[2] = Math.max(bb[2], X * PT); bb[3] = Math.max(bb[3], Y * PT); }
          if (item && prevItem && item !== prevItem && !firstRect) {   // gap between flex items -> one space tracked to the measured gap
            canvas.font = `${size}px "${cs.fontFamily.replace(/['"]/g, '')}"`; const sp = canvas.measureText(' ').width;
            while (chars.length && chars[chars.length - 1][0] === ' ') chars.pop();
            chars.push([' ', { ...s, tracking: Math.round((r.l - prevRight - sp) / size * 1000) }, k, true]);
          }
          if (!firstRect) firstRect = r; lastRight = r.r;
          chars.push([ch, s, k]);
        }
        if (item) { prevItem = item; prevRight = lastRight ?? prevRight; }
      }
    });
    // collapse spaces as the browser does: none at a paragraph's start or end, never two in a row; a space takes the previous line
    const C = []; let line = null;
    for (const ch of chars) {
      if (ch[0] === '\n') { while (C.length && C[C.length - 1][0] === ' ' && !C[C.length - 1][3]) C.pop(); C.push(ch); continue; }
      if (ch[0] === ' ' && !ch[3]) { const pv = C[C.length - 1]; if (!pv || pv[0] === '\n' || pv[0] === ' ') continue; C.push([' ', ch[1], line]); continue; }
      line = ch[2]; C.push(ch);
    }
    while (C.length && (C[C.length - 1][0] === ' ' || C[C.length - 1][0] === '\n')) C.pop();
    if (!C.some(ch => ch[1])) continue;
    for (let i = 0; i < C.length; i++) if (!C[i][1]) C[i][1] = (C.slice(i + 1).find(q => q[1]) || C.slice(0, i).reverse().find(q => q[1]))[1];
    // leading per line: baseline to the line before (Illustrator takes a line's leading from its characters)
    const bases = [...lineBox.keys()].sort((a, b) => a - b);
    const lead = new Map(bases.map((b, i) => [b, ((i ? b - bases[i - 1] : lineBox.get(b)[2] * 1.2)) * PT * sy]));
    // runs: same style and same leading
    const runs = []; let lastLine = bases[0];
    for (const [ch, s, k] of C) {
      if (k != null) lastLine = k;
      const ld = ch === '\n' ? null : lead.get(lastLine);
      const R = runs[runs.length - 1];
      if (R && (ch === '\n' || (R.s === s && R.leading === ld) || R.text.endsWith('\n'))) {
        if (ch !== '\n' && R.text.endsWith('\n')) { runs.push({ text: ch, s, leading: ld }); continue; }
        R.text += ch; continue;
      }
      runs.push({ text: ch, s, leading: ld });
    }
    // alignment from the lines' own positions inside the box
    // the frame: the content boxes of the blocks the text wraps in (all paragraphs'), so lines break where the browser broke them
    let cl = 1e9, cr = -1e9;
    for (const { blk } of paras) { const fcs = getComputedStyle(blk), fr = rel(blk.getBoundingClientRect());
      cl = Math.min(cl, fr.l + parseFloat(fcs.paddingLeft) + parseFloat(fcs.borderLeftWidth)); cr = Math.max(cr, fr.r - parseFloat(fcs.paddingRight) - parseFloat(fcs.borderRightWidth)); }
    const Ls = bases.map(b => lineBox.get(b));
    let align = 'left';
    if (Ls.length > 1) {
      if (Ls.every(([l]) => Math.abs(l - cl) < 1.5)) align = 'left';
      else if (Ls.every(([l, r]) => Math.abs((l + r) / 2 - (cl + cr) / 2) < 2)) align = 'center';
      else if (Ls.every(([, r]) => Math.abs(r - cr) < 1.5)) align = 'right';
    } else align = ['center', 'right'].includes(ucs.textAlign) ? ucs.textAlign
               : (getComputedStyle(u.parentElement).justifyContent === 'center' || ucs.justifyContent === 'center') ? 'center' : 'left';
    let clip = null; for (let a = u.parentElement; a && a !== pg; a = a.parentElement) if (getComputedStyle(a).overflow === 'hidden' && !chain(a).length) { const r = rel(a.getBoundingClientRect()); clip = [r.l * PT, r.t * PT, (r.r - r.l) * PT, (r.b - r.t) * PT]; break; }
    const b0 = bases[0], [l0, r0, s0] = lineBox.get(b0);
    const o = { text: runs.map(r => r.text).join(''), runs, rotation: rot, justify: align, clip, lines: bases.length, bbox: bb };
    if (bases.length === 1) {
      const [x, y] = map(c, align === 'center' ? (l0 + r0) / 2 : align === 'right' ? r0 : l0, b0); o.kind = 'point'; o.x = x * PT; o.y = y * PT;
    } else {
      const top = b0 - first0.asc;   // Illustrator's first baseline (Ascent): the frame's top plus the first line's ascent
      const [x, y] = map(c, cl, top); o.kind = 'area'; o.x = x * PT; o.y = y * PT;
      o.width = (cr - cl) * PT * sx + 0.2; o.height = (bases[bases.length - 1] - top + s0) * PT * sy;
    }
    out.push(o);
  }
  for (const [e] of tf) e.style.transform = '';
  return out;
}
if (typeof module !== 'undefined') module.exports = { page_text };

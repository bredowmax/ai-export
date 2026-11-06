#!/usr/bin/env python3
"""ai-export: layered Adobe Illustrator (.ai) files from HTML artwork or a PDF, with VectorCraft (open source).

    ai-export page.html out.ai [--root SEL] [--px-per-mm N] [--wait MS] [--layer "Name=page.html[,hidden][,locked][,noprint][,below]"]...
    ai-export art.pdf out.ai

HTML: the artboard is --root (default: the body's only child, else the body), its size in CSS px divided by --px-per-mm
(default 96/25.4, CSS's own). The .ai gets these layers, bottom to top:
    Shapes     backgrounds, boxes, rules, gradients
    Pictures   raster images
    Graphics   SVG art; each <svg> or SVG <img> is one named group (a logo is never loose letters)
    Type       live text: one text object per block that belongs together (a paragraph block with its siblings, a box's
               contents, a flex row as one line), runs with their font, size, tracking, color and per-line leading;
               several lines are area type (reflows), one line point type. A boxed block (border) stays its own object.
    + extra whole-page layers (--layer), e.g. a dieline (noprint, locked) or a white underlayer (hidden, below).
Group text by hand with data-text (that element is one object) or data-text-group (each child is one object).
Fonts: every face the text uses goes next to the .ai in <out>_fonts/, one file per family (.ttc); variable fonts are cut
into static instances named weight / width / optical size. Install them before opening the .ai.
PDF: converted as it is (its optional-content layers become layers, its text live type).
Illustrator asks once to update the legacy text (the file is a version 7 .ai, the format that keeps layers and live type):
choose Update, then Save. Raster images are flattened onto what is under them in the .ai; <out>_layered.pdf keeps them
transparent.
"""
import argparse, glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VC = os.environ.get('VECTORCRAFT') or shutil.which('vectorcraft-cli') or os.path.join(HERE, 'bin', 'vectorcraft-cli')


def vc(*args):
    r = subprocess.run([VC, *args], capture_output=True, text=True)
    if r.returncode: sys.exit(f'vectorcraft failed: {(r.stderr or r.stdout)[-1500:]}')
    return [json.loads(l) for l in r.stdout.splitlines() if l.startswith('{')]


# ---------- fonts ----------
WEIGHTS = {100: 'Thin', 200: 'ExtraLight', 300: 'Light', 400: 'Regular', 500: 'Medium', 600: 'SemiBold', 700: 'Bold', 800: 'ExtraBold', 900: 'Black'}


def parse_faces(faces):
    out = []
    for f in faces:
        t = f['text']
        fam = re.search(r'font-family:\s*["\']?([^;"\']+)', t)
        if not fam: continue
        w = re.search(r'font-weight:\s*([\d ]+|bold|normal)', t); st = re.search(r'font-style:\s*(\w+)', t)
        ur = re.search(r'unicode-range:\s*([^;}]+)', t)   # web fonts come split by script: keep the subset that has Latin
        if ur and not any(int(a, 16) <= 0x41 <= int(b or a, 16) for a, b in re.findall(r'U\+([0-9A-Fa-f]+)(?:-([0-9A-Fa-f]+))?', ur.group(1))): continue
        ws = (w.group(1).strip() if w else '400').replace('bold', '700').replace('normal', '400').split()
        for u in re.findall(r'url\(["\']?([^)"\']+)["\']?\)', t):
            out.append(dict(family=fam.group(1).strip(), wmin=int(ws[0]), wmax=int(ws[-1]), style=st.group(1) if st else 'normal',
                            url=urllib.parse.urljoin(f['base'], u)))
    return out


def fetch(url, captured, tmp):
    if url in captured and os.path.exists(captured[url]): return captured[url]
    if url.startswith('file://'): return urllib.parse.unquote(urllib.parse.urlparse(url).path)
    if url.startswith('data:'): return None
    p = os.path.join(tmp, hashlib.md5(url.encode()).hexdigest()[:12] + os.path.splitext(urllib.parse.urlparse(url).path)[1])
    if not os.path.exists(p): urllib.request.urlretrieve(url, p)
    return p


def fc_match(family, weight, italic):
    fw = {100: 0, 200: 40, 300: 50, 400: 80, 500: 100, 600: 180, 700: 200, 800: 205, 900: 210}[min(900, max(100, round(weight / 100) * 100))]
    r = subprocess.run(['fc-match', '-f', '%{file}', f'{family}:weight={fw}' + (':slant=100' if italic else '')], capture_output=True, text=True)
    return r.stdout.strip() or None


def names(ft):
    n = ft['name']; g = lambda *ids: next((n.getDebugName(i) for i in ids if n.getDebugName(i)), None)
    return g(16, 1), g(17, 2)


def resolve_fonts(keys, faces, captured, tmp):
    """{font key: (family, style, TTFont)}: the face each text run uses, variable fonts cut to the run's instance."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    out, cache = {}, {}
    for key in keys:
        k = json.loads(key); italic = k['style'] in ('italic', 'oblique')
        cands = [f for f in faces if f['family'].lower() == k['family'].lower()]
        path = None
        if cands:
            best = min(cands, key=lambda f: (('italic' if italic else 'normal') != f['style'], 0 if f['wmin'] <= k['weight'] <= f['wmax'] else min(abs(k['weight'] - f['wmin']), abs(k['weight'] - f['wmax']))))
            path = fetch(best['url'], captured, tmp)
        if not path: path = fc_match(k['family'], k['weight'], italic)
        if not path: sys.exit(f"font not found: {k['family']} {k['weight']}")
        ft = TTFont(path, fontNumber=0); fam, sty = names(ft)
        if 'fvar' in ft:
            axes = {a.axisTag: a for a in ft['fvar'].axes}; loc = {}
            if 'wght' in axes: loc['wght'] = k['weight']
            m = re.match(r'([\d.]+)%', k['stretch'] or '')
            if 'wdth' in axes and m: loc['wdth'] = float(m.group(1))
            if 'opsz' in axes and k['opsz']: loc['opsz'] = k['opsz']
            for tag, v in re.findall(r'"(\w{4})"\s+([\d.]+)', k['fvs'] or ''): loc[tag] = float(v)
            if 'ital' in axes: loc['ital'] = 1 if italic else 0
            loc = {t: max(axes[t].minValue, min(axes[t].maxValue, v)) for t, v in loc.items() if t in axes}
            for t, a in axes.items(): loc.setdefault(t, a.defaultValue)
            only_w = set(axes) <= {'wght', 'ital'}
            w = round(loc.get('wght', 400))
            sty = (WEIGHTS.get(w, str(w)) + (' Italic' if italic else '')) if only_w else ' '.join(
                f"{t.upper() if t != 'wght' else ''}{round(v)}".replace('WDTH', 'W').replace('OPSZ', 'O') for t, v in sorted(loc.items(), key=lambda x: x[0] != 'wght'))
            ck = (path, tuple(sorted(loc.items())))
            if ck not in cache:
                inst = instantiateVariableFont(TTFont(path, fontNumber=0), loc); inst.flavor = None
                cache[ck] = inst
            ft = cache[ck]
        out[key] = (fam, sty, ft)
    return out


def write_fonts(resolved, out_dir):
    """One file per family (.ttc when it has several faces), names set so each face is family + style; installed for VectorCraft."""
    from fontTools.ttLib import TTCollection
    os.makedirs(out_dir, exist_ok=True)
    fams = {}
    for fam, sty, ft in resolved.values():
        fams.setdefault(fam, {})[sty] = ft
    files = []
    for fam, faces in fams.items():
        fts = []
        for sty, ft in faces.items():
            ps = re.sub(r'[^A-Za-z0-9-]', '', f"{fam.replace(' ', '')}-{sty.replace(' ', '')}")[:63]
            n = ft['name']; n.names = [x for x in n.names if x.nameID not in (1, 2, 3, 4, 6, 16, 17, 25)]
            for nid, s in ((1, f'{fam} {sty}'), (2, 'Regular'), (3, ps + ';ai-export'), (4, f'{fam} {sty}'), (6, ps), (16, fam), (17, sty)):
                n.setName(s, nid, 3, 1, 0x409); n.setName(s, nid, 1, 0, 0)
            ft.flavor = None; fts.append(ft)
        base = os.path.join(out_dir, re.sub(r'[^A-Za-z0-9]+', '', fam) or 'Font')
        if len(fts) == 1: fts[0].save(base + '.ttf'); files.append(base + '.ttf')
        else:
            c = TTCollection(); c.fonts = fts; c.save(base + '.ttc'); files.append(base + '.ttc')
    inst = os.path.expanduser('~/.local/share/fonts/ai-export')
    os.makedirs(inst, exist_ok=True)
    for f in files: shutil.copy(f, inst)
    subprocess.run(['fc-cache', '-f', inst], capture_output=True)
    return files


# ---------- layers ----------
def merge(layers, out, W, H):
    """layers: [(pdf, name, visible, locked, prints)] bottom to top (an extra page prints without its page background) -> one PDF with optional content groups."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject, NameObject, RectangleObject, TextStringObject
    w = PdfWriter(); page = w.add_blank_page(W, H)
    xobjs, props, ocgs, content, off, locked = DictionaryObject(), DictionaryObject(), [], [], [], []
    for i, (f, name, visible, lock, prints) in enumerate(layers):
        lp = PdfReader(f).pages[0]; top = float(lp.mediabox.top)
        form = DecodedStreamObject(); c = lp.get_contents(); form.set_data(c.get_data() if c is not None else b'')
        form.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Form'),
                     NameObject('/BBox'): RectangleObject([0, top - H, W, top]),
                     NameObject('/Matrix'): ArrayObject([FloatObject(v) for v in (1, 0, 0, 1, 0, H - top)]),
                     NameObject('/Resources'): lp['/Resources'].get_object().clone(w) if '/Resources' in lp else DictionaryObject()})
        ocg = DictionaryObject({NameObject('/Type'): NameObject('/OCG'), NameObject('/Name'): TextStringObject(name)})
        if not prints:
            ocg[NameObject('/Usage')] = DictionaryObject({NameObject('/Print'): DictionaryObject({NameObject('/PrintState'): NameObject('/OFF')})})
        o = w._add_object(ocg); ocgs.append(o)
        if not visible: off.append(o)
        if lock: locked.append(o)
        xobjs[NameObject(f'/L{i}')] = w._add_object(form); props[NameObject(f'/OC{i}')] = o
        content.append(f'/OC /OC{i} BDC q /L{i} Do Q EMC')
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'): xobjs, NameObject('/Properties'): props})
    cs = DecodedStreamObject(); cs.set_data('\n'.join(content).encode()); page[NameObject('/Contents')] = w._add_object(cs)
    d = DictionaryObject({NameObject('/Order'): ArrayObject(list(reversed(ocgs))), NameObject('/OFF'): ArrayObject(off), NameObject('/Locked'): ArrayObject(locked)})
    w._root_object[NameObject('/OCProperties')] = DictionaryObject({NameObject('/OCGs'): ArrayObject(ocgs), NameObject('/D'): d})
    w._root_object[NameObject('/PageMode')] = NameObject('/UseOC')
    w.write(out)


def print_page(html, pdf, Wmm, Hmm, pxmm, wait):
    js = (f"const {{chromium}}=require('playwright');(async()=>{{const b=await chromium.launch();const p=await b.newPage();"
          f"await p.goto('file://'+{json.dumps(os.path.abspath(html))},{{waitUntil:'networkidle'}});await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout({wait});await p.addStyleTag({{content:'html,body{{background:transparent!important}}'}});"
          f"await p.pdf({{path:{json.dumps(pdf)},width:'{Wmm}mm',height:'{Hmm}mm',scale:{96 / 25.4 / pxmm},printBackground:true,pageRanges:'1'}});await b.close()}})()")
    subprocess.run(['node', '-e', js], check=True, cwd=HERE)


def overlap(a, b):
    bx0, by0, bx1, by1 = b[0], b[1], b[0] + b[2], b[1] + b[3]
    if a[2] <= bx0 or a[0] >= bx1 or a[3] <= by0 or a[1] >= by1: return 'out'
    if a[0] >= bx0 - .2 and a[2] <= bx1 + .2 and a[1] >= by0 - .2 and a[3] <= by1 + .2: return 'in'
    return 'part'


def html_to_ai(a):
    stem = os.path.splitext(a.out)[0]; tmp = tempfile.mkdtemp(prefix='aiexport_')
    cmd = ['node', os.path.join(HERE, 'render.js'), os.path.abspath(a.input), tmp, '--px-per-mm', str(a.px_per_mm), '--wait', str(a.wait)]
    if a.root: cmd += ['--root', a.root]
    subprocess.run(cmd, check=True, cwd=HERE, stdout=subprocess.DEVNULL)
    pg = json.load(open(os.path.join(tmp, 'page.json')))
    W, H = pg['width_mm'] / 25.4 * 72, pg['height_mm'] / 25.4 * 72
    # fonts first: the text is set in the files written next to the .ai
    keys = sorted({r['s']['font'] for o in pg['text'] for r in o['runs']})
    resolved = resolve_fonts(keys, parse_faces(pg['faces']), pg['fontFiles'], tmp)
    fonts = write_fonts(resolved, stem + '_fonts') if resolved else []
    # layers
    below, above = [], []
    for spec in a.layer or []:
        name, rest = spec.split('=', 1); parts = rest.split(','); f = os.path.join(tmp, f'extra_{len(below) + len(above)}.pdf')
        print_page(parts[0], f, pg['width_mm'], pg['height_mm'], a.px_per_mm, a.wait)
        L = (f, name, 'hidden' not in parts, 'locked' in parts, 'noprint' not in parts)
        (below if 'below' in parts else above).append(L)
    base = [(os.path.join(tmp, f'layer_{n}.pdf'), N, True, False, True) for n, N in (('shapes', 'Shapes'), ('pictures', 'Pictures'), ('graphics', 'Graphics'))]
    merge(below + base + above, stem + '_layered.pdf', W, H)
    doc = os.path.join(tmp, 'base.vectorcraft'); vc('convert', stem + '_layered.pdf', doc)
    ins = next(r for r in vc('run', '--in', doc, '--cmd', 'document.inspect', '--params', json.dumps({'depth': 1})) if r.get('command') == 'document.inspect')
    L = {x['name']: x for x in ins['result']['layers']}
    steps = []
    def cmd(c, **p): steps.append({'command': c, 'params': p}); return len(steps) - 1
    # graphics: everything inside one <svg> / SVG <img> box becomes one named group
    gl = L.get('Graphics', {}).get('children', [])
    for g in pg['graphics']:
        x, y, w, h = g['box']; box = [x - .6, y - .6, w + 1.2, h + 1.2]
        ids = [c['id'] for c in gl if overlap([c['bounds']['x'], c['bounds']['y'], c['bounds']['x'] + c['bounds']['width'], c['bounds']['y'] + c['bounds']['height']], box) == 'in']
        if len(ids) > 1: gi = cmd('object.group', ids=ids); cmd('object.setProps', id=f'${gi}.id', name=g['name']); gl = [c for c in gl if c['id'] not in ids]
        elif ids: cmd('object.setProps', id=ids[0], name=g['name'])
    # Type, right above Graphics
    cmd('layer.setCurrent', id=L['Graphics']['id']); t0 = cmd('layer.new', name='Type'); cmd('layer.setCurrent', id=f'${t0}.id')
    for o in pg['text']:
        where = overlap(o['bbox'], o['clip']) if o.get('clip') else 'in'
        if where == 'out': continue
        r0 = o['runs'][0]['s']; fam, sty, _ = resolved[r0['font']]
        p = dict(x=round(o['x'], 3), y=round(o['y'], 3), text=o['text'], size=round(r0['size'], 3), font=fam, style=sty, color=r0['fill'], justify=o['justify'])
        if o['rotation']: p['rotation'] = round(o['rotation'], 3)
        if o['kind'] == 'area': p['area'] = {'width': round(o['width'], 3), 'height': round(o['height'], 3), 'fit': 'none'}
        tid = f"${cmd('text.create', **p)}.id"; pos = 0
        for r in o['runs']:
            n = len(r['text'].encode('utf-8')); s = r['s']; fam, sty, _ = resolved[s['font']]
            if n and r['text'].strip('\n'):
                cmd('text.setRangeStyle', id=tid, start=pos, end=pos + n, font=fam, style=sty, size=round(s['size'], 3), tracking=s['tracking'],
                    hScale=round(s['hScale'], 2), fill=s['fill'], **({'leading': round(r['leading'], 3)} if r.get('leading') else {}))
            pos += n
        if where == 'part':
            x, y, w, h = o['clip']; rc = cmd('shape.rectangle', x=x, y=y, width=w, height=h); cmd('object.clippingMask.make', ids=[f'${rc}.id', tid])
    cmd('select.none')
    json.dump(steps, open(os.path.join(tmp, 'steps.json'), 'w'))
    built = os.path.join(tmp, 'built.vectorcraft')
    res = vc('run', '--in', doc, '--commands', os.path.join(tmp, 'steps.json'), '--export', built)
    warn = sorted({r['result']['warning'] for r in res if isinstance(r.get('result'), dict) and r['result'].get('warning')})
    for x in warn: print('warning:', x, file=sys.stderr)
    vc('convert', built, a.out, '--ai-version', '7')
    n_text = sum(1 for s in steps if s['command'] == 'text.create')
    print(f"{a.out}: {len(below) + len(base) + len(above) + 1} layers, {n_text} text objects, {len(pg['graphics'])} graphics; "
          f"fonts in {stem + '_fonts' if fonts else '(none)'}; same layers as PDF: {stem}_layered.pdf")
    if not a.keep: shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input'); ap.add_argument('out')
    ap.add_argument('--root'); ap.add_argument('--px-per-mm', type=float, default=96 / 25.4); ap.add_argument('--wait', type=int, default=800)
    ap.add_argument('--layer', action='append', help='extra whole-page layer: "Name=page.html[,hidden][,locked][,noprint][,below]"')
    ap.add_argument('--keep', action='store_true', help='keep the working folder')
    a = ap.parse_args(); a.out = os.path.abspath(a.out)
    a.layer = [s.split('=', 1)[0] + '=' + os.path.abspath(s.split('=', 1)[1].split(',')[0]) + ''.join(',' + x for x in s.split('=', 1)[1].split(',')[1:]) for s in (a.layer or [])]
    if not (VC and os.path.exists(VC)): sys.exit('vectorcraft-cli not found: run install.sh or set VECTORCRAFT')
    if a.input.lower().endswith('.pdf'):
        vc('convert', a.input, a.out, '--ai-version', '7'); print(a.out)
    else:
        html_to_ai(a)


if __name__ == '__main__':
    main()

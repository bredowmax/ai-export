# ai-export

Layered Adobe Illustrator (`.ai`) files from HTML artwork or a PDF, without Illustrator. Built for packaging and print art that is
designed in code and then handed to a designer who works in Illustrator.

```
ai-export page.html out.ai [--root SEL] [--px-per-mm N] [--layer "Dieline=dieline.html,locked,noprint"]
ai-export art.pdf out.ai
```

What a designer gets from an HTML page:

| Layer | What is on it |
| --- | --- |
| Shapes | backgrounds, boxes, rules, gradients |
| Pictures | raster images |
| Graphics | SVG art; each `<svg>` or SVG `<img>` is one group, so a logo never comes apart into letters |
| Type | live text, one text object per block that belongs together, with its fonts, sizes, tracking, colors and line spacing; several lines are area type that reflows |
| extra | whole pages added with `--layer` (a dieline, a white underlayer), each hidden, locked or non-printing as asked; `below` puts one under the art |

Next to the `.ai`: `<out>_fonts/` (every face the text uses, one file per family; variable fonts are cut into static instances named
weight / width / optical size, e.g. `800 W76 O96`) and `<out>_layered.pdf` (the same layers as PDF layers, images kept transparent).

Text grouping: a block's paragraphs stay one object; a boxed block (one with a border) is its own object; a flex row is one line
whose gaps are kept as tracked spaces; a vertical flex stack is one object. Override with `data-text` (this element is one object)
or `data-text-group` (each child is one object).

The artboard is `--root` (default: the body's only child, else the body), at `--px-per-mm` CSS px per millimeter (default 96/25.4).
Text placed in a clipped region that only partly shows is clipped the same way in the `.ai`.

## Opening in Illustrator

1. Install the fonts in `<out>_fonts/`.
2. Open the `.ai`. Illustrator says the file has legacy text: choose **Update**, then **Save**. The type becomes normal text and the
   message does not come back. (The file is a version 7 `.ai`, the format that carries layers and live type; the newer
   PDF-based `.ai` from VectorCraft writes type as outlines.)
3. Raster images in the `.ai` are flattened onto what is under them; use `<out>_layered.pdf` where transparency matters.
4. The document is RGB: switch to CMYK and assign spot inks as the print spec says.

## Install (Linux x86_64)

```
curl -fsSL https://raw.githubusercontent.com/bredowmax/ai-export/main/install.sh | bash
```

Installs to `/opt/ai-export` with `ai-export` and `vectorcraft-cli` on the PATH. Needs Python 3 and Node with Playwright and Chromium
(`require('playwright')`); installs `fonttools`, `brotli` and `pypdf` if missing.

## Not Adobe

This project is not affiliated with or endorsed by Adobe. Adobe and Illustrator are trademarks of Adobe Inc., named here only to say
which application opens the files. It contains no Adobe software or code.

## VectorCraft

`bin/vectorcraft-cli.xz` is the command-line tool of [VectorCraft](https://github.com/storytold/vectorcraft) (open source,
Apache-2.0 or MIT, see `bin/VECTORCRAFT-LICENSE-*`), built for Linux x86_64 from commit
`36ef34dfdd8dfd1abc19fd209678860a00583558` (2026-11-06) with `cargo build --release -p vectorcraft-cli`, stripped and xz-compressed.
To rebuild: clone that repository, run the same command (about 13 minutes), `strip`, `xz -9`, replace the file.

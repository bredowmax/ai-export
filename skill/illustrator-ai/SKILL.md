---
name: illustrator-ai
description: Make layered Adobe Illustrator (.ai) files, with live editable type and named layers, from HTML artwork or a PDF. Use when someone wants an .ai file, artwork "editable in Illustrator", or layered print or packaging files for a designer.
---

# Layered Illustrator files

`ai-export` (github.com/bredowmax/ai-export) writes a real `.ai` that Illustrator opens with named layers, live type and grouped
graphics. In cloud sessions it is installed by the environment's setup script; check with `command -v ai-export`. If it is
missing, install it (Linux x86_64, seconds):

    curl -fsSL https://raw.githubusercontent.com/bredowmax/ai-export/main/install.sh | bash

## Make the art as HTML, then export

    ai-export page.html out.ai --root .artboard --px-per-mm 20 [--layer "Dieline=dieline.html,locked,noprint"]

- Lay the artboard out at an exact size (an element with a fixed width and height in px; give `--px-per-mm` so it maps to
  millimeters). Place blocks absolutely; each absolutely placed box's content becomes text objects.
- Text that belongs together goes in one element (paragraphs as block children): it becomes ONE text object with consistent
  spacing. Boxed text (with a border) stays its own object. Mark exceptions with `data-text` (one object) or `data-text-group`
  (each child one object).
- Logos, icons and barcodes as SVG (`<img src="x.svg">` or inline `<svg>`): each becomes one group, never loose letters or bars.
- Fonts via `@font-face` (local files or web fonts). Every face used is written to `out_fonts/`, one file per family; variable
  fonts are cut into named static instances. Never squeeze small type with negative tracking to make it fit.
- Extra whole-page layers (dieline, white underlayer, finish map): `--layer "Name=page.html[,hidden][,locked][,noprint][,below]"`.

A PDF converts as it is: `ai-export art.pdf out.ai` (its PDF layers become layers).

## Check before handing over

Render the result and compare it with the HTML: `vectorcraft-cli convert out.ai out.png --ppi 300`, and a Playwright
screenshot of the page. Look for: line breaks matching, no font substitution (`vectorcraft-cli info out.ai`: every font
`exact`), text objects grouped as intended (`vectorcraft-cli run --in out.ai --cmd document.inspect --params '{"depth":2}'`).

## Tell the recipient

Install the fonts in `out_fonts/` first. Illustrator asks once to update legacy text: choose Update, then Save. Raster images
are flattened in the .ai (`out_layered.pdf` keeps them transparent). Set the document to CMYK for print.

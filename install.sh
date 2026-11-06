#!/bin/bash
# Installs ai-export and VectorCraft's CLI (Linux x86_64): /opt/ai-export, with `ai-export` and `vectorcraft-cli` on the PATH.
# From a checkout: bash install.sh. Anywhere: curl -fsSL https://raw.githubusercontent.com/bredowmax/ai-export/main/install.sh | bash
set -e
REPO="${AI_EXPORT_REPO:-bredowmax/ai-export}"; DEST="${AI_EXPORT_DIR:-/opt/ai-export}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" 2>/dev/null && pwd)"
if [ ! -f "$SRC/ai_export.py" ]; then
  SRC="$(mktemp -d)"; curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/main" | tar -xz -C "$SRC" --strip-components=1
fi
mkdir -p "$DEST/bin"
cp "$SRC"/ai_export.py "$SRC"/render.js "$SRC"/textblocks.js "$SRC"/README.md "$DEST/" 2>/dev/null || true
cp "$SRC"/bin/VECTORCRAFT-LICENSE-* "$DEST/bin/"
xz -dc "$SRC/bin/vectorcraft-cli.xz" > "$DEST/bin/vectorcraft-cli"; chmod +x "$DEST/bin/vectorcraft-cli"
ln -sf "$DEST/bin/vectorcraft-cli" /usr/local/bin/vectorcraft-cli
printf '#!/bin/sh\nexec python3 %s/ai_export.py "$@"\n' "$DEST" > /usr/local/bin/ai-export; chmod +x /usr/local/bin/ai-export
python3 -c "import fontTools, pypdf, brotli" 2>/dev/null || pip install -q --break-system-packages fonttools brotli pypdf
echo "ai-export installed: $(vectorcraft-cli 2>&1 | head -1)"

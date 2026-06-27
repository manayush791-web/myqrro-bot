#!/usr/bin/env bash
# Download OFL-licensed Google Fonts used by the poster renderer.
# Called automatically during Docker build (see Dockerfile).
set -e

DIR="$(dirname "$0")/../fonts"
mkdir -p "$DIR"

BASE="https://github.com/google/fonts/raw/main/ofl"

FAIL=0

dl() {
  local url="$1" dest="$2"
  if [ ! -f "$dest" ]; then
    echo "⬇  $(basename "$dest")"
    if ! curl -fsSL "$url" -o "$dest"; then
      echo "⚠  Failed to download $(basename "$dest") from $url"
      FAIL=1
    fi
  else
    echo "✓  $(basename "$dest") already exists"
  fi
}

# Poppins fonts (these are stable)
dl "$BASE/poppins/Poppins-Regular.ttf"   "$DIR/Poppins-Regular.ttf"
dl "$BASE/poppins/Poppins-SemiBold.ttf"  "$DIR/Poppins-SemiBold.ttf"
dl "$BASE/poppins/Poppins-Bold.ttf"      "$DIR/Poppins-Bold.ttf"

# Inter fonts — try multiple known paths since Google Fonts reorganises files
dl_inter() {
  local weight="$1" dest="$2"
  for path in \
    "inter/static/Inter_18pt-${weight}.ttf" \
    "inter/static/Inter-${weight}.ttf" \
    "inter/Inter-${weight}.ttf" \
    "inter/Inter_18pt-${weight}.ttf"; do
    if curl -fsSL "$BASE/$path" -o "$dest" 2>/dev/null; then
      echo "⬇  $(basename "$dest")  ← $path"
      return 0
    fi
  done
  echo "⚠  Could not download Inter ${weight} from any known path"
  FAIL=1
  return 1
}

dl_inter "Regular"  "$DIR/Inter-Regular.ttf"
dl_inter "SemiBold" "$DIR/Inter-SemiBold.ttf"

if [ "$FAIL" -ne 0 ]; then
  echo "⚠  Some fonts failed to download — build continues but rendering may use fallback fonts"
fi

echo "✅  Font setup complete."

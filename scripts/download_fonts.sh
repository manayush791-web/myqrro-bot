#!/usr/bin/env bash
# Download OFL-licensed Google Fonts used by the poster renderer.
# Called automatically during Docker build (see Dockerfile).
set -e

DIR="$(dirname "$0")/../fonts"
mkdir -p "$DIR"

BASE="https://github.com/google/fonts/raw/main/ofl"

dl() {
  local url="$1" dest="$2"
  if [ ! -f "$dest" ]; then
    echo "⬇  $(basename $dest)"
    curl -fsSL "$url" -o "$dest"
  else
    echo "✓  $(basename $dest) already exists"
  fi
}

dl "$BASE/poppins/Poppins-Regular.ttf"   "$DIR/Poppins-Regular.ttf"
dl "$BASE/poppins/Poppins-SemiBold.ttf"  "$DIR/Poppins-SemiBold.ttf"
dl "$BASE/poppins/Poppins-Bold.ttf"      "$DIR/Poppins-Bold.ttf"
dl "$BASE/inter/static/Inter_18pt-Regular.ttf"       "$DIR/Inter-Regular.ttf"
dl "$BASE/inter/static/Inter_18pt-SemiBold.ttf"      "$DIR/Inter-SemiBold.ttf"

echo "✅  All fonts ready."

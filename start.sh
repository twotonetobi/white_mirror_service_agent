#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

detect_platform() {
    case "$(uname -s)" in
        Darwin*)  echo "macos" ;;
        Linux*)   echo "linux" ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *)        echo "unknown" ;;
    esac
}

PLATFORM=$(detect_platform)
VENV_DIR="venv-$PLATFORM"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       White Mirror Service Agent - Cross-Platform Start      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Platform:    $PLATFORM"
echo "  Virtual Env: $VENV_DIR"
echo ""

if [ ! -d "$VENV_DIR" ]; then
    echo "⚠️  Virtual environment not found: $VENV_DIR"
    echo "   Run ./setup.sh first to create it."
    echo ""
    read -p "Create it now? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ./setup.sh
    else
        exit 1
    fi
fi

echo "🚀 Starting Service Agent..."
echo ""

source "$VENV_DIR/bin/activate"

export WM_AGENT_PLATFORM="$PLATFORM"

OPEN_BROWSER=${OPEN_BROWSER:-true}

if [ "$OPEN_BROWSER" = "true" ]; then
    (
        sleep 3
        PORT=${WM_AGENT_PORT:-9100}
        URL="http://localhost:$PORT/ui"
        
        case "$PLATFORM" in
            macos)  open "$URL" 2>/dev/null || true ;;
            linux)  xdg-open "$URL" 2>/dev/null || sensible-browser "$URL" 2>/dev/null || true ;;
        esac
        
        echo ""
        echo "🌐 Browser opened: $URL"
    ) &
fi

python main.py "$@"

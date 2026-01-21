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
PYTHON_CMD="${PYTHON_CMD:-python3}"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       White Mirror Service Agent - Setup                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Platform:    $PLATFORM"
echo "  Python:      $PYTHON_CMD"
echo "  Virtual Env: $VENV_DIR"
echo ""

if ! command -v $PYTHON_CMD &> /dev/null; then
    echo "❌ Python not found: $PYTHON_CMD"
    echo "   Please install Python 3.10+ and try again."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
echo "  Python Ver:  $PYTHON_VERSION"
echo ""

if [ -d "$VENV_DIR" ]; then
    echo "⚠️  Virtual environment already exists: $VENV_DIR"
    read -p "Recreate it? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🗑️  Removing existing venv..."
        rm -rf "$VENV_DIR"
    else
        echo "✅ Using existing venv"
        source "$VENV_DIR/bin/activate"
        pip install -q --upgrade pip
        pip install -q -r requirements.txt
        echo "✅ Dependencies updated"
        exit 0
    fi
fi

echo "📦 Creating virtual environment..."
$PYTHON_CMD -m venv "$VENV_DIR"

echo "🔧 Activating..."
source "$VENV_DIR/bin/activate"

echo "📥 Upgrading pip..."
pip install -q --upgrade pip

echo "📥 Installing dependencies..."
pip install -q -r requirements.txt

if [ "$PLATFORM" = "linux" ]; then
    echo "📥 Installing NVIDIA GPU support (pynvml)..."
    pip install -q pynvml || echo "   (pynvml install failed - OK if no NVIDIA GPU)"
fi

CONFIG_FILE="config-$PLATFORM.yaml"
if [ ! -f "$CONFIG_FILE" ] && [ -f "config.yaml.example" ]; then
    echo "📝 Creating platform config: $CONFIG_FILE"
    cp config.yaml.example "$CONFIG_FILE"
    
    HOSTNAME=$(hostname | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
    if [ "$PLATFORM" = "macos" ]; then
        sed -i '' "s/machine_id:.*/machine_id: \"$HOSTNAME-mac\"/" "$CONFIG_FILE" 2>/dev/null || true
        sed -i '' "s/machine_name:.*/machine_name: \"Mac Workstation\"/" "$CONFIG_FILE" 2>/dev/null || true
    elif [ "$PLATFORM" = "linux" ]; then
        sed -i "s/machine_id:.*/machine_id: \"$HOSTNAME-linux\"/" "$CONFIG_FILE" 2>/dev/null || true
        sed -i "s/machine_name:.*/machine_name: \"Linux Server\"/" "$CONFIG_FILE" 2>/dev/null || true
    fi
fi

chmod +x start.sh 2>/dev/null || true

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    ✅ Setup Complete!                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  To start the Service Agent:"
echo ""
echo "    ./start.sh"
echo ""
echo "  The UI will automatically open in your browser at:"
echo "    http://localhost:9100/ui"
echo ""

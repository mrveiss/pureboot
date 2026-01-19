#!/bin/bash
# PureBoot Setup Script
# Installs dependencies and prepares the development environment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "  PureBoot Development Setup"
echo "========================================"
echo ""

cd "$PROJECT_ROOT"

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "Error: Python $REQUIRED_VERSION or higher is required (found $PYTHON_VERSION)"
    exit 1
fi
echo "  Python $PYTHON_VERSION - OK"
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    echo "  Virtual environment created"
else
    echo "Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip --quiet
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install -e ".[dev]" --quiet
echo "  Dependencies installed"
echo ""

# Create necessary directories
echo "Creating directory structure..."
mkdir -p tftp/bios tftp/uefi assets docker/ipxe-builder
touch tftp/bios/.gitkeep tftp/uefi/.gitkeep 2>/dev/null || true
echo "  Directories created"
echo ""

# Verify installation
echo "Verifying installation..."
python3 -c "from src.config import settings; print(f'  Settings loaded - Server port: {settings.port}')"
echo ""

echo "========================================"
echo "  Setup Complete!"
echo "========================================"
echo ""
echo "To activate the virtual environment:"
echo "  source .venv/bin/activate"
echo ""
echo "To run the server:"
echo "  python -m src.main"
echo ""
echo "To run tests:"
echo "  pytest"
echo ""

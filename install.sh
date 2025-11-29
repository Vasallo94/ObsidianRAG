#!/bin/bash

# ============================================================
# ObsidianRAG - Installation Script
# ============================================================
# Run with: chmod +x install.sh && ./install.sh

set -e  # Exit on errors

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║              🧠 ObsidianRAG - Installation               ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ============================================================
# 1. Check system requirements
# ============================================================
echo -e "${YELLOW}[1/5] Checking system requirements...${NC}"

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    echo -e "  ${GREEN}✓${NC} Python $PYTHON_VERSION found"
else
    echo -e "  ${RED}✗ Python 3 not found${NC}"
    echo "    Install Python 3.11+ from https://python.org"
    exit 1
fi

# Check Python version (3.11+)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    echo -e "  ${RED}✗ Python 3.11+ required, you have $PYTHON_VERSION${NC}"
    exit 1
fi

# Check Ollama
if command -v ollama &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Ollama found"
else
    echo -e "  ${YELLOW}⚠ Ollama not found${NC}"
    echo -e "    Installing Ollama..."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install ollama
        else
            echo "    Download Ollama from: https://ollama.ai"
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        curl -fsSL https://ollama.com/install.sh | sh
    else
        echo "    Download Ollama from: https://ollama.ai"
        exit 1
    fi
fi

# ============================================================
# 2. Install UV (package manager)
# ============================================================
echo -e "${YELLOW}[2/5] Configuring package manager...${NC}"

if command -v uv &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} UV already installed"
else
    echo "  Installing UV..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    echo -e "  ${GREEN}✓${NC} UV installed"
fi

# ============================================================
# 3. Install Python dependencies
# ============================================================
echo -e "${YELLOW}[3/5] Installing Python dependencies...${NC}"

uv sync
echo -e "  ${GREEN}✓${NC} Dependencies installed"

# ============================================================
# 4. Configure .env file
# ============================================================
echo -e "${YELLOW}[4/5] Configuring environment...${NC}"

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "  ${GREEN}✓${NC} .env file created from .env.example"
        echo -e "  ${YELLOW}⚠ IMPORTANT: Edit .env and configure OBSIDIAN_PATH${NC}"
    else
        # Create minimal .env
        cat > .env << 'EOF'
# Path to your Obsidian vault (REQUIRED)
OBSIDIAN_PATH=/path/to/your/vault

# LLM model (any Ollama model)
LLM_MODEL=gemma3
EOF
        echo -e "  ${GREEN}✓${NC} .env file created"
        echo -e "  ${YELLOW}⚠ IMPORTANT: Edit .env and configure OBSIDIAN_PATH${NC}"
    fi
else
    echo -e "  ${GREEN}✓${NC} .env file already exists"
fi

# ============================================================
# 5. Download Ollama model
# ============================================================
echo -e "${YELLOW}[5/5] Configuring Ollama...${NC}"

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags &> /dev/null; then
    echo "  Starting Ollama..."
    ollama serve &> /dev/null &
    sleep 3
fi

# Get model from .env or use default
LLM_MODEL=$(grep -E "^LLM_MODEL=" .env 2>/dev/null | cut -d'=' -f2 || echo "gemma3")
LLM_MODEL=${LLM_MODEL:-gemma3}

# Check if model is already downloaded
if ollama list 2>/dev/null | grep -q "$LLM_MODEL"; then
    echo -e "  ${GREEN}✓${NC} Model $LLM_MODEL already downloaded"
else
    echo "  Downloading model $LLM_MODEL (this may take a while)..."
    ollama pull "$LLM_MODEL"
    echo -e "  ${GREEN}✓${NC} Model $LLM_MODEL downloaded"
fi

# ============================================================
# Completion
# ============================================================
echo ""
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║              ✅ Installation Complete                    ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo ""
echo "  1. Edit the .env file and configure your Obsidian vault:"
echo -e "     ${YELLOW}nano .env${NC}"
echo ""
echo "  2. Start the server:"
echo -e "     ${YELLOW}uv run main.py${NC}"
echo ""
echo "  3. Open the web interface (in another terminal):"
echo -e "     ${YELLOW}uv run streamlit run streamlit_app.py${NC}"
echo ""
echo "  4. Open your browser at: http://localhost:8501"
echo ""
echo -e "${GREEN}Ready to use! 🚀${NC}"

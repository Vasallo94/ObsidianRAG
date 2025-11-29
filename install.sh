#!/bin/bash

# ============================================================
# ObsidianRAG - Script de Instalación
# ============================================================
# Ejecutar con: chmod +x install.sh && ./install.sh

set -e  # Salir si hay errores

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║              🧠 ObsidianRAG - Instalación                 ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ============================================================
# 1. Verificar requisitos del sistema
# ============================================================
echo -e "${YELLOW}[1/5] Verificando requisitos del sistema...${NC}"

# Verificar Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    echo -e "  ${GREEN}✓${NC} Python $PYTHON_VERSION encontrado"
else
    echo -e "  ${RED}✗ Python 3 no encontrado${NC}"
    echo "    Instala Python 3.11+ desde https://python.org"
    exit 1
fi

# Verificar versión de Python (3.11+)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    echo -e "  ${RED}✗ Se requiere Python 3.11+, tienes $PYTHON_VERSION${NC}"
    exit 1
fi

# Verificar Ollama
if command -v ollama &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Ollama encontrado"
else
    echo -e "  ${YELLOW}⚠ Ollama no encontrado${NC}"
    echo -e "    Instalando Ollama..."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install ollama
        else
            echo "    Descarga Ollama desde: https://ollama.ai"
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        curl -fsSL https://ollama.com/install.sh | sh
    else
        echo "    Descarga Ollama desde: https://ollama.ai"
        exit 1
    fi
fi

# ============================================================
# 2. Instalar UV (gestor de paquetes)
# ============================================================
echo -e "${YELLOW}[2/5] Configurando gestor de paquetes...${NC}"

if command -v uv &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} UV ya instalado"
else
    echo "  Instalando UV..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    echo -e "  ${GREEN}✓${NC} UV instalado"
fi

# ============================================================
# 3. Instalar dependencias Python
# ============================================================
echo -e "${YELLOW}[3/5] Instalando dependencias Python...${NC}"

uv sync
echo -e "  ${GREEN}✓${NC} Dependencias instaladas"

# ============================================================
# 4. Configurar archivo .env
# ============================================================
echo -e "${YELLOW}[4/5] Configurando entorno...${NC}"

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "  ${GREEN}✓${NC} Archivo .env creado desde .env.example"
        echo -e "  ${YELLOW}⚠ IMPORTANTE: Edita .env y configura OBSIDIAN_PATH${NC}"
    else
        # Crear .env mínimo
        cat > .env << 'EOF'
# Ruta a tu vault de Obsidian (OBLIGATORIO)
OBSIDIAN_PATH=/ruta/a/tu/vault

# Modelo LLM (cualquier modelo de Ollama)
LLM_MODEL=gemma3
EOF
        echo -e "  ${GREEN}✓${NC} Archivo .env creado"
        echo -e "  ${YELLOW}⚠ IMPORTANTE: Edita .env y configura OBSIDIAN_PATH${NC}"
    fi
else
    echo -e "  ${GREEN}✓${NC} Archivo .env ya existe"
fi

# ============================================================
# 5. Descargar modelo de Ollama
# ============================================================
echo -e "${YELLOW}[5/5] Configurando Ollama...${NC}"

# Verificar si Ollama está corriendo
if ! curl -s http://localhost:11434/api/tags &> /dev/null; then
    echo "  Iniciando Ollama..."
    ollama serve &> /dev/null &
    sleep 3
fi

# Obtener modelo del .env o usar default
LLM_MODEL=$(grep -E "^LLM_MODEL=" .env 2>/dev/null | cut -d'=' -f2 || echo "gemma3")
LLM_MODEL=${LLM_MODEL:-gemma3}

# Verificar si el modelo ya está descargado
if ollama list 2>/dev/null | grep -q "$LLM_MODEL"; then
    echo -e "  ${GREEN}✓${NC} Modelo $LLM_MODEL ya descargado"
else
    echo "  Descargando modelo $LLM_MODEL (esto puede tardar)..."
    ollama pull "$LLM_MODEL"
    echo -e "  ${GREEN}✓${NC} Modelo $LLM_MODEL descargado"
fi

# ============================================================
# Finalización
# ============================================================
echo ""
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║              ✅ Instalación Completada                    ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "${BLUE}Próximos pasos:${NC}"
echo ""
echo "  1. Edita el archivo .env y configura tu vault de Obsidian:"
echo -e "     ${YELLOW}nano .env${NC}"
echo ""
echo "  2. Inicia el servidor:"
echo -e "     ${YELLOW}uv run cerebro.py${NC}"
echo ""
echo "  3. Abre la interfaz web (en otra terminal):"
echo -e "     ${YELLOW}uv run streamlit run app.py${NC}"
echo ""
echo "  4. Abre tu navegador en: http://localhost:8501"
echo ""
echo -e "${GREEN}¡Listo para usar! 🚀${NC}"

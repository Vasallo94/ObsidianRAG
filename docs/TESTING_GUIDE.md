# Testing Guide - ObsidianRAG Plugin v1.0.0

## ✅ Current Status

**Version**: 1.0.0  
**Build**: Completed (47KB main.js)  
**Commit**: Pushed to `v3-plugin`

---

## 🧪 Testing on Windows

### Prerequisites

1. **Windows 10/11**
2. **Obsidian installed**: [Download here](https://obsidian.md/download)
3. **Python 3.11+**: [python.org](https://www.python.org/downloads/)
4. **Ollama**: [ollama.com/download](https://ollama.com/download)

### Installation Steps

#### 1. Install Backend

```powershell
# Open PowerShell as normal user (not admin)

# Verify Python
python --version  # Should be 3.11+

# Install backend
pip install obsidianrag

# Verify installation
pip show obsidianrag
```

#### 2. Install and Configure Ollama

```powershell
# Download LLM model
ollama pull gemma3

# Verify Ollama is running
# Should open automatically after installation
# Verify with:
curl http://localhost:11434/api/tags
```

#### 3. Install Plugin Manually

```powershell
# Navigate to your Obsidian vault
cd "C:\Users\YourUser\Documents\MyVault"

# Create plugin directory
mkdir -p .obsidian\plugins\obsidianrag

# Copy release files
# (Download from GitHub release: main.js, manifest.json, styles.css)
# And copy to .obsidian\plugins\obsidianrag\
```

#### 4. Enable Plugin in Obsidian

1. Open Obsidian
2. Settings → Community Plugins → Browse
3. Find "ObsidianRAG" in the local list
4. Enable

### Tests to Run on Windows

#### ✅ Test 1: Server Auto-start

1. **Close Obsidian completely**
2. **Open Obsidian**
3. **Verify**: 
   - Ribbon icon 🧠 appears
   - Click on the icon
   - Status should show "● Online" (may take 5-10 seconds)

**If it fails**:
- Open PowerShell: `obsidianrag serve --vault "C:\path\to\vault"`
- Check for errors

#### ✅ Test 2: Ask a Question

1. **Click on 🧠 or Command Palette → "ObsidianRAG: Open Chat"**
2. **Type**: "What notes do I have about testing?"
3. **Verify**:
   - Status changes to "Retrieving..."
   - Answer appears (may take 10-30s the first time)
   - Sources are shown with 🟢/🟡/🟠 indicators
   - Note links are clickable

**If it fails**:
- Settings → ObsidianRAG → Check Status
- Verify port 8000 is not occupied

#### ✅ Test 3: Source Links Work

1. **Ask a question**
2. **Click on a source (linked note)**
3. **Verify**: The corresponding note opens

#### ✅ Test 4: Settings UI

1. **Settings → ObsidianRAG**
2. **Verify**:
   - Model dropdown shows installed models (gemma3)
   - Server Status shows "Online"
   - Vault stats show number of notes
3. **Change model**: Select another model (if you have several)
4. **Stop Server** → **Start Server**
5. **Verify**: Server restarts correctly

#### ✅ Test 5: Edge Cases

**Occupied port**:
```powershell
# In PowerShell, start a server on port 8000
python -m http.server 8000
```
- Open Obsidian
- Settings → ObsidianRAG → Server Port → change to `8001`
- Stop → Start Server
- Verify it works on the new port

**Ollama not running**:
- Close Ollama (Task Manager → end process)
- Try to ask a question
- Verify: Clear error message about Ollama

---

## 🐧 Testing on Linux

### Prerequisites

1. **Ubuntu 22.04+ / Debian / Fedora / Arch**
2. **Obsidian AppImage**: [Download here](https://obsidian.md/download)
3. **Python 3.11+**
4. **Ollama**

### Installation Steps

#### 1. Install Backend

```bash
# Verify Python
python3 --version  # Should be 3.11+

# Install backend
pip3 install obsidianrag
# or with user flag if you don't have permissions
pip3 install --user obsidianrag

# Add to PATH if needed
export PATH="$HOME/.local/bin:$PATH"

# Verify
obsidianrag --help
```

#### 2. Install Ollama

```bash
# Quick installation
curl -fsSL https://ollama.com/install.sh | sh

# Start service
sudo systemctl start ollama
# or manually
ollama serve

# Download model
ollama pull gemma3
```

#### 3. Install Plugin

```bash
# Navigate to vault
cd ~/Documents/ObsidianVault  # or wherever your vault is

# Create directory
mkdir -p .obsidian/plugins/obsidianrag

# Download release files from GitHub
cd .obsidian/plugins/obsidianrag
wget https://github.com/Vasallo94/ObsidianRAG/releases/download/v1.0.0/main.js
wget https://github.com/Vasallo94/ObsidianRAG/releases/download/v1.0.0/manifest.json
wget https://github.com/Vasallo94/ObsidianRAG/releases/download/v1.0.0/styles.css
```

#### 4. Give Permissions to Obsidian AppImage

```bash
chmod +x Obsidian-*.AppImage
./Obsidian-*.AppImage
```

### Tests to Run on Linux

Same tests as Windows, but with Linux-specific commands:

#### ✅ Test 1: Check Port

```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill process if needed
lsof -ti:8000 | xargs kill -9
```

#### ✅ Test 2: Check Ollama Service

```bash
# Check Ollama status
systemctl status ollama

# If not running
sudo systemctl start ollama
# or
ollama serve
```

#### ✅ Test 3: Manual Server Start

```bash
# If auto-start fails, start manually
obsidianrag serve --vault ~/Documents/ObsidianVault --port 8000

# Check logs for errors
```

---

## 🍎 Testing on macOS

### Prerequisites

1. **macOS 12+ (Monterey or later)**
2. **Obsidian**: [Download here](https://obsidian.md/download)
3. **Python 3.11+**: via Homebrew or python.org
4. **Ollama**: [ollama.ai](https://ollama.ai)

### Installation Steps

#### 1. Install Backend

```bash
# Using pip
pip3 install obsidianrag

# Or using pipx (recommended)
brew install pipx
pipx install obsidianrag
```

#### 2. Install Ollama

1. Download from [ollama.ai](https://ollama.ai)
2. Open Ollama.app
3. Pull a model:
   ```bash
   ollama pull gemma3
   ```

#### 3. Install Plugin

```bash
# Navigate to vault
cd ~/Documents/ObsidianVault

# Create plugin directory
mkdir -p .obsidian/plugins/obsidianrag

# Copy files from release
# Or symlink for development:
ln -s /path/to/ObsidianRAG/plugin .obsidian/plugins/obsidianrag
```

### macOS-Specific Tests

#### ✅ Test 1: Gatekeeper / Security

- First time opening may require allowing the app in System Preferences → Security

#### ✅ Test 2: Port Conflicts

```bash
# Check port usage
lsof -i :8000

# Kill if needed
lsof -ti:8000 | xargs kill -9
```

---

## 📋 Test Checklist

### Core Functionality

| Test | Windows | Linux | macOS |
|------|---------|-------|-------|
| Plugin loads | ⬜ | ⬜ | ✅ |
| Server auto-starts | ⬜ | ⬜ | ✅ |
| Ask question works | ⬜ | ⬜ | ✅ |
| Streaming works | ⬜ | ⬜ | ✅ |
| Source links work | ⬜ | ⬜ | ✅ |
| Settings UI works | ⬜ | ⬜ | ✅ |
| Model dropdown loads from Ollama | ⬜ | ⬜ | ✅ |
| Stop server works | ⬜ | ⬜ | ✅ |
| Start server works | ⬜ | ⬜ | ✅ |
| Reindex works | ⬜ | ⬜ | ✅ |

### Edge Cases

| Test | Windows | Linux | macOS |
|------|---------|-------|-------|
| Ollama not running | ⬜ | ⬜ | ✅ |
| Port occupied | ⬜ | ⬜ | ✅ |
| Large vault (>500 notes) | ⬜ | ⬜ | ⬜ |
| Empty vault | ⬜ | ⬜ | ⬜ |
| Server crash recovery | ⬜ | ⬜ | ✅ |

---

## 🐛 Reporting Issues

When reporting issues, please include:

1. **OS and version** (e.g., Windows 11, Ubuntu 22.04, macOS 14)
2. **Obsidian version**
3. **Plugin version**
4. **Python version** (`python --version`)
5. **Ollama version** (`ollama --version`)
6. **Error messages** from:
   - Obsidian Developer Console (Cmd+Option+I / Ctrl+Shift+I)
   - Terminal where server is running
7. **Steps to reproduce**

Open an issue at: https://github.com/Vasallo94/ObsidianRAG/issues

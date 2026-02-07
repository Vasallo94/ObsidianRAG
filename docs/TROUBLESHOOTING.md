# Troubleshooting Guide

Common issues and solutions for ObsidianRAG.

---

## 🔴 Server Issues

### Server shows "Offline" in plugin

**Symptoms**:
- Status indicator shows ● Offline
- No response when asking questions

**Solutions**:

1. **Check backend is installed**:
   ```bash
   pip show obsidianrag
   ```

   If not installed:
   ```bash
   pip install obsidianrag
   # or
   pipx install obsidianrag
   ```

2. **Start server manually**:
   ```bash
   obsidianrag serve --vault /path/to/vault
   ```

3. **Check port conflicts**:
   - Default port is 8000
   - Check if another app is using it:
     ```bash
     # macOS/Linux
     lsof -i :8000

     # Windows
     netstat -ano | findstr :8000
     ```
   - Change port in Settings → ObsidianRAG → Server Port

4. **Verify server is running**:
   ```bash
   curl http://localhost:8000/health
   ```

   Should return:
   ```json
   {"status": "ok", "model": "gemma3", ...}
   ```

---

## 🤖 Ollama Issues

### "Ollama is not running" error

**Symptoms**:
- Error: `Ollama is not running at http://localhost:11434`
- Server fails to start

**Solutions**:

1. **Start Ollama**:
   ```bash
   ollama serve
   ```

2. **macOS - Ollama running as app**:
   - Open Ollama.app from Applications
   - Check menu bar for Ollama icon

3. **Verify Ollama is accessible**:
   ```bash
   curl http://localhost:11434/api/tags
   ```

   Should list available models.

4. **Check Ollama URL**:
   - Default: `http://localhost:11434`
   - If using custom setup, set environment variable:
     ```bash
     export OLLAMA_BASE_URL=http://your-custom-url:port
     ```

### "Model not found" error

**Symptoms**:
- Error: `model 'gemma3' not found`
- Error: `pull model manifest: file does not exist`

**Solutions**:

1. **Download the model**:
   ```bash
   ollama pull gemma3
   ```

2. **List available models**:
   ```bash
   ollama list
   ```

3. **Change model in settings**:
   - Settings → ObsidianRAG → LLM Model
   - Select a model you have downloaded

4. **Popular model downloads**:
   ```bash
   ollama pull gemma3      # 5GB, balanced
   ollama pull qwen2.5     # 4.4GB, great for Spanish
   ollama pull llama3.2    # 2GB, smaller/faster
   ollama pull mistral     # 4GB, alternative
   ```

---

## 📊 Database Issues

### "Collection does not exist" error

**Symptoms**:
- Error: `Collection 'obsidianrag' does not exist`
- Plugin shows no answers

**Solutions**:

1. **Delete and rebuild database**:
   ```bash
   # Stop server first
   obsidianrag serve --vault /path/to/vault --rebuild
   ```

2. **Or manually delete**:
   ```bash
   rm -rf /path/to/vault/.obsidianrag/db/
   # Then restart server
   ```

3. **Check vault path**:
   - Make sure vault path is correct
   - Should point to folder containing `.md` files

### First indexing is very slow

**This is normal**.

First run downloads and indexes:
1. **HuggingFace models** (~500MB):
   - Embeddings: `paraphrase-multilingual-mpnet-base-v2`
   - Reranker: `BAAI/bge-reranker-v2-m3`

2. **All vault notes** (can take 1-5 minutes depending on vault size)

Subsequent runs are fast (incremental indexing).

**Tips**:
- Watch progress in terminal
- Large vaults (>500 notes) may take 5-10 minutes first time
- Models are cached, only downloaded once

### "No documents found" / Empty results

**Symptoms**:
- All queries return "No documents found"
- Stats show 0 notes

**Solutions**:

1. **Verify vault path**:
   ```bash
   ls /path/to/vault/*.md
   ```
   Make sure `.md` files exist.

2. **Check vault permissions**:
   ```bash
   # macOS/Linux
   ls -la /path/to/vault
   ```
   Ensure read permissions.

3. **Force reindex**:
   - In Obsidian: Command Palette → "ObsidianRAG: Rebuild Database"
   - Or via API:
     ```bash
     curl -X POST http://localhost:8000/rebuild_db
     ```

---

## 🌍 Language & Response Issues

### Responses in wrong language

**Symptoms**:
- Ask in English, get Spanish answers
- Ask in Spanish, get English answers

**Why this happens**:
- Agent responds in **dominant language** between:
  1. Your question's language
  2. Your notes' language
- If 80% of your notes are Spanish, answers will be Spanish

**Solutions**:

1. **Use a better multilingual model**:
   ```bash
   ollama pull qwen2.5  # Excellent for Spanish/English
   ```
   Then: Settings → ObsidianRAG → LLM Model → `qwen2.5`

2. **Write notes in desired language**:
   - More English notes = English responses
   - More Spanish notes = Spanish responses

3. **Ask in dominant language**:
   - If notes are mostly Spanish, ask in Spanish
   - If notes are mostly English, ask in English

### Responses are too generic / don't cite notes

**Symptoms**:
- Answers don't reference specific notes
- Generic LLM knowledge instead of your notes

**Solutions**:

1. **Check retrieval is working**:
   - Look at "Sources" in chat
   - Should show 🟢/🟡/🟠 indicators
   - If no sources → database issue (see above)

2. **Adjust retrieval settings** (advanced):
   ```bash
   obsidianrag serve --vault /path/to/vault \
     --retrieval-k 15  # Retrieve more documents
   ```

3. **Improve note quality**:
   - Use descriptive titles
   - Add `[[wikilinks]]` between related notes
   - GraphRAG will follow links for better context

---

## 🚀 Performance Issues

### Server is slow to respond

**Symptoms**:
- 10+ seconds to get an answer
- Plugin freezes

**Solutions**:

1. **Use smaller/faster model**:
   ```bash
   ollama pull llama3.2  # 2GB, much faster
   ```

2. **Check system resources**:
   ```bash
   # macOS/Linux
   top

   # Look for high CPU/RAM usage
   ```

3. **Reduce retrieval complexity** (advanced):
   - Edit `~/.config/obsidianrag/config.toml`:
     ```toml
     use_reranker = false      # Skip reranking (faster)
     retrieval_k = 8           # Fewer documents
     ```

4. **Use GPU acceleration** (if available):
   - Ollama automatically uses GPU if available
   - Check: `ollama list` should show GPU info

### High RAM usage

**Symptoms**:
- System slows down
- RAM usage >8GB

**Solutions**:

1. **Use smaller model**:
   ```bash
   ollama pull llama3.2  # Uses ~2GB RAM instead of 5GB
   ```

2. **Close other apps**

3. **Disable auto-start**:
   - Settings → ObsidianRAG → Auto-start Server → OFF
   - Start server only when needed

---

## 🔗 Plugin-Specific Issues

### Plugin doesn't appear in Community Plugins

**Solutions**:

1. **Check Obsidian version**:
   - Requires Obsidian 1.5.0+
   - Help → About → Version

2. **Disable Safe Mode**:
   - Settings → Community Plugins → Turn off Safe Mode

3. **Refresh plugin list**:
   - Settings → Community Plugins → Reload

### Source links don't work

**Symptoms**:
- Clicking source note does nothing
- Error: "File not found"

**Why this happens**:
- Note was moved/renamed after indexing
- Note is in different vault

**Solutions**:

1. **Rebuild database**:
   - Command Palette → "ObsidianRAG: Rebuild Database"

2. **Check source path**:
   - Hover over link to see full path
   - Verify file exists in vault

3. **Fallback search**:
   - Plugin tries to find by basename if full path fails
   - Should still work even if file moved

---

## 🛠️ Advanced Debugging

### Enable debug logs

**Backend**:
```bash
export LOG_LEVEL=DEBUG
obsidianrag serve --vault /path/to/vault
```

**Plugin**:
- Open Developer Console: `Cmd+Opt+I` (Mac) / `Ctrl+Shift+I` (Windows)
- Filter by "ObsidianRAG"

### Check API manually

```bash
# Health check
curl http://localhost:8000/health

# Ask question
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"text": "test question"}'

# Get stats
curl http://localhost:8000/stats
```

### Check ChromaDB

```python
import chromadb

client = chromadb.PersistentClient(path="/path/to/vault/.obsidianrag/db")
collection = client.get_collection("obsidianrag")
print(f"Total documents: {collection.count()}")
```

---

## 🆘 Still Having Issues?

1. **Check GitHub Issues**: [github.com/Vasallo94/ObsidianRAG/issues](https://github.com/Vasallo94/ObsidianRAG/issues)
2. **Create new issue** with:
   - Full error message
   - Steps to reproduce
   - System info (OS, Python version, Ollama version)
   - Obsidian version
3. **Discord/Forum**: Check Obsidian forums for community support

---

## 📋 Diagnostic Checklist

Before reporting an issue, verify:

- [ ] Python 3.11+ installed (`python --version`)
- [ ] Backend installed (`pip show obsidianrag`)
- [ ] Ollama installed (`ollama --version`)
- [ ] Ollama running (`curl http://localhost:11434`)
- [ ] Model downloaded (`ollama list`)
- [ ] Server running (`curl http://localhost:8000/health`)
- [ ] Vault path correct (contains `.md` files)
- [ ] Database created (`.obsidianrag/db/` folder exists in vault)
- [ ] Plugin enabled (Settings → Community Plugins)

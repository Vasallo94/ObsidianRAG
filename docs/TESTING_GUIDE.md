# Guía de Testing - ObsidianRAG Plugin v1.0.0

## ✅ Estado Actual

**Version**: 1.0.0  
**Build**: Completado (47KB main.js)  
**Commit**: Pusheado a `v3-plugin`

---

## 🧪 Testing en Windows

### Prerequisitos

1. **Windows 10/11**
2. **Obsidian instalado**: [Descargar aquí](https://obsidian.md/download)
3. **Python 3.11+**: [python.org](https://www.python.org/downloads/)
4. **Ollama**: [ollama.com/download](https://ollama.com/download)

### Pasos de Instalación

#### 1. Instalar Backend

```powershell
# Abrir PowerShell como usuario normal (no admin)

# Verificar Python
python --version  # Debe ser 3.11+

# Instalar backend
pip install obsidianrag

# Verificar instalación
pip show obsidianrag
```

#### 2. Instalar y Configurar Ollama

```powershell
# Descargar modelo LLM
ollama pull gemma3

# Verificar que Ollama está corriendo
# Debe abrirse automáticamente tras instalación
# Verificar con:
curl http://localhost:11434/api/tags
```

#### 3. Instalar Plugin Manualmente

```powershell
# Navegar a tu vault de Obsidian
cd "C:\Users\TuUsuario\Documents\MiVault"

# Crear directorio del plugin
mkdir -p .obsidian\plugins\obsidianrag

# Copiar archivos del release
# (Descargar de GitHub release: main.js, manifest.json, styles.css)
# Y copiarlos a .obsidian\plugins\obsidianrag\
```

#### 4. Activar Plugin en Obsidian

1. Abrir Obsidian
2. Settings → Community Plugins → Browse
3. Buscar "ObsidianRAG" en la lista local
4. Enable

### Tests a Realizar en Windows

#### ✅ Test 1: Auto-start del servidor

1. **Cerrar Obsidian completamente**
2. **Abrir Obsidian**
3. **Verificar**: 
   - Ribbon icon 🧠 aparece
   - Click en el icon
   - Status debería mostrar "● Online" (puede tardar 5-10 segundos)

**Si falla**:
- Abrir PowerShell: `obsidianrag serve --vault "C:\path\to\vault"`
- Verificar errores

#### ✅ Test 2: Hacer una pregunta

1. **Click en 🧠 o Command Palette → "ObsidianRAG: Open Chat"**
2. **Escribir**: "What notes do I have about testing?"
3. **Verificar**:
   - Status cambia a "Retrieving..."
   - Respuesta aparece (puede tardar 10-30s la primera vez)
   - Fuentes se muestran con 🟢/🟡/🟠 indicators
   - Links a notas son clickeables

**Si falla**:
- Settings → ObsidianRAG → Check Status
- Verificar puerto 8000 no esté ocupado

#### ✅ Test 3: Source links funcionan

1. **Hacer una pregunta**
2. **Click en una fuente (nota linkada)**
3. **Verificar**: Se abre la nota correspondiente

#### ✅ Test 4: Settings UI

1. **Settings → ObsidianRAG**
2. **Verificar**:
   - Dropdown de modelos muestra modelos instalados (gemma3)
   - Server Status muestra "Online"
   - Vault stats muestran número de notas
3. **Cambiar modelo**: Seleccionar otro modelo (si tienes varios)
4. **Stop Server** → **Start Server**
5. **Verificar**: Server reinicia correctamente

#### ✅ Test 5: Edge Cases

**Puerto ocupado**:
```powershell
# En PowerShell, iniciar servidor en puerto 8000
python -m http.server 8000
```
- Abrir Obsidian
- Settings → ObsidianRAG → Server Port → cambiar a `8001`
- Stop → Start Server
- Verificar funciona en nuevo puerto

**Ollama no corriendo**:
- Cerrar Ollama (Task Manager → cerrar proceso)
- Intentar hacer pregunta
- Verificar: Error message claro sobre Ollama

---

## 🐧 Testing en Linux

### Prerequisitos

1. **Ubuntu 22.04+ / Debian / Fedora / Arch**
2. **Obsidian AppImage**: [Descargar aquí](https://obsidian.md/download)
3. **Python 3.11+**
4. **Ollama**

### Pasos de Instalación

#### 1. Instalar Backend

```bash
# Verificar Python
python3 --version  # Debe ser 3.11+

# Instalar backend
pip3 install obsidianrag
# o con user flag si no tienes permisos
pip3 install --user obsidianrag

# Agregar a PATH si es necesario
export PATH="$HOME/.local/bin:$PATH"

# Verificar
obsidianrag --help
```

#### 2. Instalar Ollama

```bash
# Instalación rápida
curl -fsSL https://ollama.com/install.sh | sh

# Iniciar servicio
sudo systemctl start ollama
# o manualmente
ollama serve

# Descargar modelo
ollama pull gemma3
```

#### 3. Instalar Plugin

```bash
# Navegar a vault
cd ~/Documents/ObsidianVault  # o donde esté tu vault

# Crear directorio
mkdir -p .obsidian/plugins/obsidianrag

# Descargar release files desde GitHub
cd .obsidian/plugins/obsidianrag
wget https://github.com/Vasallo94/ObsidianRAG/releases/download/v1.0.0/main.js
wget https://github.com/Vasallo94/ObsidianRAG/releases/download/v1.0.0/manifest.json
wget https://github.com/Vasallo94/ObsidianRAG/releases/download/v1.0.0/styles.css
```

#### 4. Dar Permisos a Obsidian AppImage

```bash
chmod +x Obsidian-*.AppImage
./Obsidian-*.AppImage
```

### Tests en Linux (Mismos que Windows)

Los tests son idénticos a Windows. Verificar:

1. ✅ Auto-start
2. ✅ Query funcionando
3. ✅ Source links
4. ✅ Settings UI
5. ✅ Edge cases

### Tests Adicionales Linux-Específicos

#### ✅ Test 6: Permisos

```bash
# Verificar backend tiene permisos de ejecución
which obsidianrag
ls -la $(which obsidianrag)
```

#### ✅ Test 7: Systemd (si Ollama se instaló como servicio)

```bash
# Verificar Ollama service
sudo systemctl status ollama

# Si no está corriendo
sudo systemctl start ollama
```

---

## 📊 Checklist Completo de Testing

### Windows

- [ ] Python 3.11+ instalado y en PATH
- [ ] `pip install obsidianrag` funciona
- [ ] Ollama descargado e instalado
- [ ] `ollama pull gemma3` exitoso
- [ ] Plugin copiado a `.obsidian/plugins/obsidianrag/`
- [ ] Plugin habilitado en Settings
- [ ] Auto-start funciona
- [ ] Query básica retorna respuesta
- [ ] Source links clickeables
- [ ] Settings UI funciona
- [ ] Cambio de modelo funciona
- [ ] Restart server funciona
- [ ] Error handling correcto (Ollama offline)

### Linux

- [ ] Python 3.11+ instalado
- [ ] `pip3 install obsidianrag` funciona
- [ ] `obsidianrag` en PATH
- [ ] Ollama instalado (curl script)
- [ ] Ollama service corriendo o `ollama serve` manual
- [ ] `ollama pull gemma3` exitoso
- [ ] Plugin descargado a `.obsidian/plugins/obsidianrag/`
- [ ] Obsidian AppImage tiene permisos de ejecución
- [ ] Plugin habilitado en Settings
- [ ] Auto-start funciona
- [ ] Query básica retorna respuesta
- [ ] Source links clickeables
- [ ] Settings UI funciona
- [ ] Cambio de modelo funciona
- [ ] Restart server funciona
- [ ] Error handling correcto

---

## 🐛 Problemas Comunes y Soluciones

### Windows

**"python no encontrado"**:
```powershell
# Instalar desde python.org
# Marcar "Add to PATH" durante instalación
```

**"pip no es un comando reconocido"**:
```powershell
python -m pip install obsidianrag
```

**"Port 8000 already in use"**:
- Settings → ObsidianRAG → Server Port → 8001

### Linux

**"command not found: obsidianrag"**:
```bash
export PATH="$HOME/.local/bin:$PATH"
# Agregar a ~/.bashrc o ~/.zshrc para permanencia
```

**"Permission denied"**:
```bash
# Usar --user
pip3 install --user obsidianrag
```

**Ollama no inicia**:
```bash
# Ver logs
sudo journalctl -u ollama -f

# Iniciar manualmente
ollama serve
```

---

## 📝 Reportar Resultados

Para cada OS, reportar:

1. **Python version**: `python --version`
2. **Obsidian version**: Help → About
3. **Ollama version**: `ollama --version`
4. **Backend version**: `pip show obsidianrag`
5. **Tests passed**: Lista de ✅/❌
6. **Errores encontrados**: Screenshots/logs

---

## 🚀 Próximos Pasos Tras Testing

Si todo funciona:
1. ✅ Marcar tests como completos
2. ✅ Crear GitHub Release v1.0.0
3. ✅ PR a `obsidianmd/obsidian-releases`
4. ⏳ Esperar review (1-2 semanas)
5. 🎉 Plugin disponible en Community Plugins

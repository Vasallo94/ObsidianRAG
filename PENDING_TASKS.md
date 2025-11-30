# 🎯 Tareas Pendientes para Release v3.0

## ✅ Estado General
**Progreso**: ~95% completado

## 📋 Lo que queda

### 1. Screenshots/GIFs del Plugin (Opcional pero recomendado)
**Prioridad**: Media  
**Estimado**: 30 minutos

- [ ] Capturar pantalla del Chat View con una conversación
- [ ] Capturar la Settings Tab
- [ ] Capturar el Setup Modal
- [ ] GIF mostrando el streaming en acción (opcional)
- [ ] Añadir a `docs/images/` y referenciar en README

**Herramientas sugeridas**:
- macOS: Cmd+Shift+5 para screenshots
- [Kap](https://getkap.co/) o QuickTime para GIFs

### 2. Publicación en GitHub (Manual)
**Prioridad**: Alta (crítico para release)  
**Estimado**: 15 minutos

#### Pasos:
1. **Build del plugin**:
   ```bash
   cd plugin
   npm run build
   ```

2. **Crear tag y release**:
   ```bash
   git tag plugin-v1.0.0
   git push origin plugin-v1.0.0
   ```
   
3. El workflow automático creará el release con `main.js`, `manifest.json`, `styles.css`

4. **Verificar**: Ir a GitHub Releases y confirmar que se creó

### 3. Publicación en Obsidian Community Plugins (Manual)
**Prioridad**: Alta (para distribución)  
**Estimado**: 1-2 horas + tiempo de review

#### Pasos:
1. **Fork del repo oficial**:
   - Ir a https://github.com/obsidianmd/obsidian-releases
   - Click "Fork"

2. **Agregar entrada**:
   - Editar `community-plugins.json`
   - Añadir al final (mantener orden alfabético):
   ```json
   {
       "id": "obsidianrag",
       "name": "ObsidianRAG",
       "author": "Enrique Vasallo",
       "description": "Ask questions about your Obsidian notes using local AI (RAG) with Ollama",
       "repo": "Vasallo94/ObsidianRAG"
   }
   ```

3. **Crear PR**:
   - Commit: `Add ObsidianRAG plugin`
   - Crear Pull Request al repo original
   - Esperar review (puede tomar 1-7 días)

4. **Responder feedback** si los revisores tienen preguntas

### 4. Testing en Windows/Linux (Opcional)
**Prioridad**: Baja (nice to have)  
**Estimado**: Variable

- [ ] Conseguir acceso a Windows
- [ ] Conseguir acceso a Linux
- [ ] Probar instalación y funcionamiento básico

## 🚀 Qué NO hace falta
- ❌ Backend en PyPI - **Ya publicado** (v3.0.1)
- ❌ Tests - **Todos pasando** (32 tests plugin, 79 tests backend)
- ❌ Workflows CI/CD - **Ya creados** (test-backend.yml, release-backend.yml, release-plugin.yml)
- ❌ Documentación - **Completa** (README, Installation, Usage, Architecture, Troubleshooting, Contributing)

## 📦 Próximos pasos sugeridos
1. Opcional: Capturar screenshots (30 min)
2. **CRÍTICO**: Build + Tag + Release en GitHub (15 min)
3. **CRÍTICO**: PR a obsidian-releases (1 hora)
4. Esperar aprobación
5. 🎉 Celebrar!

---

**Resumen**: El proyecto está técnicamente completo. Solo faltan tareas manuales de publicación.

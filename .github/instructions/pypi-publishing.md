# PyPI Publishing Guide

> Guía para publicar el paquete `obsidianrag` en PyPI y TestPyPI

## Configuración Inicial (Solo una vez)

### 1. Crear cuentas
- [PyPI](https://pypi.org/account/register/) - Producción
- [TestPyPI](https://test.pypi.org/account/register/) - Pruebas

### 2. Configurar Trusted Publishers

En lugar de usar tokens, usamos **Trusted Publishers** (OpenID Connect), que es más seguro.

#### En TestPyPI
1. Ve a: https://test.pypi.org/manage/account/publishing/
2. Rellena:
   - **Nombre de proyecto**: `obsidianrag`
   - **Propietario**: `Vasallo94`
   - **Repositorio**: `ObsidianRAG`
   - **Workflow**: `release-backend.yml`
   - **Environment**: `testpypi`
3. Clic en "Añadir"

#### En PyPI (Producción)
1. Ve a: https://pypi.org/manage/account/publishing/
2. Rellena igual pero:
   - **Environment**: `pypi`
3. Clic en "Añadir"

### 3. Crear Environments en GitHub

1. Ve a: https://github.com/Vasallo94/ObsidianRAG/settings/environments
2. Crea dos environments:
   - `testpypi` (para pruebas)
   - `pypi` (para producción)

## Publicar a TestPyPI (Pruebas)

### Opción A: Manual desde GitHub
1. Ve a: https://github.com/Vasallo94/ObsidianRAG/actions/workflows/release-backend.yml
2. Clic en **"Run workflow"**
3. Selecciona `testpypi`
4. Clic en **"Run workflow"**

### Opción B: Con GitHub CLI
```bash
gh workflow run release-backend.yml -f publish_to=testpypi
```

### Verificar publicación
```bash
# Instalar desde TestPyPI
pip install -i https://test.pypi.org/simple/ obsidianrag

# O con uv
uv pip install -i https://test.pypi.org/simple/ obsidianrag
```

## Publicar a PyPI (Producción)

### Opción A: Automático con tags (Recomendado)
```bash
# 1. Actualizar versión en backend/obsidianrag/__init__.py
# 2. Commit
git add -A
git commit -m "chore: release v3.0.0"

# 3. Crear tag
git tag v3.0.0

# 4. Push con tag
git push origin v3-plugin --tags
```

El workflow se ejecutará automáticamente y:
1. Ejecuta tests
2. Construye el paquete
3. Publica a PyPI
4. Crea GitHub Release

### Opción B: Manual desde GitHub
1. Ve a Actions → Release Backend to PyPI
2. Run workflow → selecciona `pypi`

### Verificar publicación
```bash
pip install obsidianrag
# o
uv add obsidianrag
```

## Estructura del Workflow

```yaml
# .github/workflows/release-backend.yml
Triggers:
  - push tags v*  → PyPI automático
  - workflow_dispatch → Manual (TestPyPI o PyPI)

Jobs:
  1. build       → Tests + Build
  2. publish     → Upload a PyPI/TestPyPI
  3. release     → GitHub Release (solo con tags)
```

## Versionado

Usamos [Semantic Versioning](https://semver.org/):
- `MAJOR.MINOR.PATCH` (ej: `3.0.0`)
- **MAJOR**: Cambios incompatibles
- **MINOR**: Nuevas funcionalidades compatibles
- **PATCH**: Correcciones de bugs

### Actualizar versión
```python
# backend/obsidianrag/__init__.py
__version__ = "3.0.1"  # Cambiar aquí
```

## Troubleshooting

### Error: "Project not found"
- Verifica que el Trusted Publisher está configurado correctamente
- El nombre del proyecto debe coincidir exactamente

### Error: "Environment not found"
- Crea el environment en GitHub Settings → Environments

### Error: "Permission denied"
- Verifica `id-token: write` en el workflow
- El environment debe existir y coincidir

## Links útiles
- [PyPI - obsidianrag](https://pypi.org/project/obsidianrag/) *(después de publicar)*
- [TestPyPI - obsidianrag](https://test.pypi.org/project/obsidianrag/)
- [Trusted Publishers Docs](https://docs.pypi.org/trusted-publishers/)
- [GitHub Environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)

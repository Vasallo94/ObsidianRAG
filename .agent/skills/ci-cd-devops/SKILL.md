---
name: ci-cd-devops
description: >
  Usa esta skill para gestionar workflows de GitHub Actions, releases,
  publicación en PyPI y versionado semántico.
tools: ['read', 'edit', 'run_command']
---

# CI/CD & DevOps

## Cuándo usar esta skill
- Cuando modifiques workflows de GitHub Actions (`.github/workflows`).
- Cuando prepares una nueva versión (release) del software.
- Cuando necesites publicar el paquete en PyPI.

## Cómo usar esta skill

### 1. GitHub Actions
- `test-backend.yml`: Ejecuta tests y linter en cada push.
- `release.yml`: Publica a PyPI y crea release en GitHub cuando hay un tag `v*`.

### 2. Proceso de Release
1.  **Actualizar Versiones**:
    - `backend/obsidianrag/__init__.py`
    - `plugin/manifest.json` y `package.json`
2.  **CHANGELOG.md**: Documentar cambios.
3.  **Git Tag**:
    ```bash
    git commit -m "chore: release v3.0.1"
    git tag v3.0.1
    git push origin main --tags
    ```

### 3. Publicación en PyPI
Usamos **Trusted Publishers**. No se necesitan tokens manuales en local si usas el workflow.
Para publicar manualmente desde local:
```bash
uv build
uv publish
```
(Requiere configuración de token local si no se usa CI/CD).

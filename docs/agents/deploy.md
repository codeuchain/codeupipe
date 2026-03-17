# codeupipe Deploy — Agent Reference

> `curl https://codeuchain.github.io/codeupipe/agents/deploy.txt`

---

## Overview

codeupipe deploys pipelines to cloud platforms via `cup deploy`. Each platform has an adapter that generates the right config files. The manifest (`cup.toml`) declares what to deploy.

---

## Manifest — cup.toml

```toml
[project]
name = "my-pipeline"
version = "0.1.0"
python = "3.11"

[pipeline]
config = "pipeline.toml"    # or pipeline.json

[connectors.postgres]
package = "codeupipe-postgres"
env = ["DATABASE_URL"]

[deploy.docker]
port = 8000

[deploy.render]
plan = "free"
region = "oregon"
```

---

## Targets

| Target | Adapter | What It Generates |
|--------|---------|-------------------|
| `docker` | `DockerAdapter` | Dockerfile + docker-compose.yml |
| `render` | `RenderAdapter` | render.yaml (free tier, no CC) |
| `vercel` | `VercelAdapter` | vercel.json + serverless functions |
| `netlify` | `NetlifyAdapter` | netlify.toml + functions |
| `fly` | `FlyAdapter` | fly.toml (edge deployment) |
| `railway` | `RailwayAdapter` | railway.json |
| `cloudrun` | `CloudRunAdapter` | Google Cloud Run config |
| `koyeb` | `KoyebAdapter` | Koyeb free-tier |
| `apprunner` | `AppRunnerAdapter` | AWS App Runner |
| `oracle` | `OracleAdapter` | Oracle Cloud Always Free VM |
| `azure` | `AzureContainerAppsAdapter` | Azure Container Apps |
| `huggingface` | `HuggingFaceAdapter` | Hugging Face Spaces |

---

## CLI Commands

```bash
cup deploy docker cup.toml     # generate Docker artifacts
cup deploy render cup.toml     # Render.com (free, no CC)
cup deploy vercel cup.toml     # Vercel serverless
cup deploy netlify cup.toml    # Netlify serverless
cup init                       # scaffold new project with cup.toml
cup recipe list                # list deployment recipes
cup recipe apply <name>        # apply a recipe
cup ci                         # generate CI/CD config
```

---

## Recipes

Recipes are pre-configured deployment blueprints:

```bash
cup recipe list
# → docker-dev, render-free, vercel-serverless, netlify-functions, ...

cup recipe apply render-free
# → generates cup.toml + render.yaml for zero-cost deploy
```

---

## Programmatic API

```python
from codeupipe.deploy import (
    DeployTarget, DeployAdapter,
    DockerAdapter, VercelAdapter, NetlifyAdapter, RenderAdapter,
    find_adapters, load_manifest, init_project,
    list_recipes, resolve_recipe,
)

# Load manifest
manifest = load_manifest("cup.toml")

# Generate artifacts
adapter = RenderAdapter()
adapter.prepare(manifest)
adapter.deploy(manifest)

# Discover available adapters
adapters = find_adapters()  # auto-discovers all installed adapters
```

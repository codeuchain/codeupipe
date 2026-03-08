"""
AzureContainerAppsAdapter: Deploy adapter for Azure Container Apps.

Generates az CLI deploy script for Azure Container Apps:
- Serverless containers with scale-to-zero
- 180K vCPU-seconds/month free
- Built-in Dapr, KEDA, and Envoy
- Integrates with Azure services (Key Vault, Managed Identity)

Zero external dependencies — pure string template generation.

Usage:
    cup deploy azure-container-apps cup.toml
    cup deploy azure-container-apps cup.toml --dry-run
"""

import json
from pathlib import Path
from typing import List

from .adapter import DeployAdapter, DeployTarget

__all__ = ["AzureContainerAppsAdapter"]


class AzureContainerAppsAdapter(DeployAdapter):
    """Generates az CLI deploy script for Azure Container Apps."""

    def target(self) -> DeployTarget:
        return DeployTarget(
            name="azure-container-apps",
            description="Azure Container Apps — serverless containers, scale-to-zero, 180K vCPU-s/mo free",
            requires=["az"],
        )

    def validate(self, pipeline_config: dict, **options) -> List[str]:
        issues = []
        has_pipeline = "pipeline" in pipeline_config
        has_frontend = "frontend" in pipeline_config
        if not has_pipeline and not has_frontend:
            issues.append("Config needs 'pipeline' and/or 'frontend' section")
        if has_pipeline and "steps" not in pipeline_config.get("pipeline", {}):
            issues.append("Config 'pipeline' missing 'steps'")
        return issues

    def generate(self, pipeline_config: dict, output_dir: Path, **options) -> List[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        generated: List[Path] = []

        project_name = pipeline_config.get("project", {}).get("name", "my-app")
        port = options.get("port", 8080)
        python_version = options.get("python_version", "3.12")
        resource_group = options.get("resource_group", "cup-rg")
        location = options.get("location", "eastus")

        # 1. deploy.sh — az CLI commands
        deploy_path = output_dir / "deploy.sh"
        deploy_path.write_text(
            self._render_deploy_script(project_name, resource_group, location, port)
        )
        deploy_path.chmod(0o755)
        generated.append(deploy_path)

        # 2. Dockerfile
        dockerfile_path = output_dir / "Dockerfile"
        dockerfile_path.write_text(self._render_dockerfile(port, python_version))
        generated.append(dockerfile_path)

        # 3. Pipeline config
        config_path = output_dir / "pipeline.json"
        config_path.write_text(json.dumps(pipeline_config, indent=2))
        generated.append(config_path)

        # 4. Entrypoint
        entrypoint_path = output_dir / "entrypoint.py"
        entrypoint_path.write_text(self._render_entrypoint(port))
        generated.append(entrypoint_path)

        # 5. Requirements
        reqs_path = output_dir / "requirements.txt"
        reqs_path.write_text(self._render_requirements(pipeline_config))
        generated.append(reqs_path)

        return generated

    def deploy(self, output_dir: Path, *, dry_run: bool = False, **options) -> str:
        resource_group = options.get("resource_group", "cup-rg")
        location = options.get("location", "eastus")

        if dry_run:
            return (
                f"[dry-run] Would deploy {output_dir} to Azure Container Apps\n"
                f"Resource Group: {resource_group}\n"
                f"Location: {location}\n"
                f"Steps:\n"
                f"  1. az containerapp up\n"
                f"  2. Free tier — 180K vCPU-seconds/month"
            )

        return (
            f"Azure Container Apps artifacts generated in {output_dir}/\n"
            f"\n"
            f"Deploy steps:\n"
            f"  1. cd {output_dir}\n"
            f"  2. chmod +x deploy.sh\n"
            f"  3. ./deploy.sh\n"
            f"\n"
            f"Or one-liner:\n"
            f"  az containerapp up --source . --resource-group {resource_group} "
            f"--location {location}\n"
            f"\n"
            f"Free tier: 180K vCPU-seconds, 360K GiB-seconds, 2M requests/month."
        )

    # ── Internal ────────────────────────────────────────────────

    @staticmethod
    def _render_deploy_script(
        project_name: str,
        resource_group: str,
        location: str,
        port: int,
    ) -> str:
        return (
            "#!/usr/bin/env bash\n"
            "# Auto-generated Azure Container Apps deploy script by cup deploy\n"
            "set -euo pipefail\n"
            "\n"
            f'RG="{resource_group}"\n'
            f'APP="{project_name}"\n'
            f'LOCATION="{location}"\n'
            f'PORT="{port}"\n'
            "\n"
            'echo "Deploying to Azure Container Apps..."\n'
            "\n"
            "# Create resource group (if needed)\n"
            'az group create --name $RG --location $LOCATION 2>/dev/null || true\n'
            "\n"
            "# Deploy from source (builds in Azure)\n"
            "az containerapp up \\\n"
            "  --name $APP \\\n"
            "  --resource-group $RG \\\n"
            "  --location $LOCATION \\\n"
            "  --source . \\\n"
            "  --ingress external \\\n"
            "  --target-port $PORT\n"
            "\n"
            'echo "Deployment complete!"\n'
            'echo "App URL:"\n'
            "az containerapp show \\\n"
            "  --name $APP \\\n"
            "  --resource-group $RG \\\n"
            "  --query 'properties.configuration.ingress.fqdn' \\\n"
            "  --output tsv\n"
        )

    @staticmethod
    def _render_dockerfile(port: int, python_version: str) -> str:
        return (
            f"FROM python:{python_version}-slim\n"
            "\n"
            "WORKDIR /app\n"
            "\n"
            "COPY requirements.txt .\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n"
            "\n"
            "COPY . .\n"
            "\n"
            f"EXPOSE {port}\n"
            'CMD ["python", "entrypoint.py"]\n'
        )

    @staticmethod
    def _render_entrypoint(port: int) -> str:
        return (
            '"""Auto-generated pipeline entrypoint by cup deploy (Azure Container Apps)."""\n'
            "import asyncio\n"
            "import json\n"
            "import os\n"
            "from http.server import HTTPServer, BaseHTTPRequestHandler\n"
            "from pathlib import Path\n"
            "\n"
            "from codeupipe import Pipeline, Payload\n"
            "from codeupipe.registry import default_registry\n"
            "\n"
            "\n"
            'CONFIG_PATH = Path(__file__).parent / "pipeline.json"\n'
            "\n"
            "\n"
            "def _load_pipeline():\n"
            '    return Pipeline.from_config(str(CONFIG_PATH), registry=default_registry)\n'
            "\n"
            "\n"
            "def main():\n"
            "    pipeline = _load_pipeline()\n"
            f"    port = int(os.environ.get('PORT', {port}))\n"
            "\n"
            "    class Handler(BaseHTTPRequestHandler):\n"
            "        def do_POST(self):\n"
            "            length = int(self.headers.get('Content-Length', 0))\n"
            "            body = self.rfile.read(length) if length else b'{}'\n"
            "            data = json.loads(body)\n"
            "            result = asyncio.run(pipeline.run(Payload(data)))\n"
            "            response = json.dumps(result.to_dict()).encode()\n"
            "            self.send_response(200)\n"
            "            self.send_header('Content-Type', 'application/json')\n"
            "            self.send_header('Content-Length', str(len(response)))\n"
            "            self.end_headers()\n"
            "            self.wfile.write(response)\n"
            "\n"
            "        def do_GET(self):\n"
            "            self.send_response(200)\n"
            "            self.send_header('Content-Type', 'application/json')\n"
            '            body = b\'{"status": "ok"}\'\n'
            "            self.send_header('Content-Length', str(len(body)))\n"
            "            self.end_headers()\n"
            "            self.wfile.write(body)\n"
            "\n"
            '    server = HTTPServer(("0.0.0.0", port), Handler)\n'
            '    print(f"Pipeline server listening on 0.0.0.0:{port}")\n'
            "    server.serve_forever()\n"
            "\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    main()\n"
        )

    @staticmethod
    def _render_requirements(pipeline_config: dict) -> str:
        lines = ["codeupipe"]
        deps = pipeline_config.get("dependencies", {})
        for pkg in deps:
            if isinstance(deps[pkg], str):
                lines.append(f"{pkg}{deps[pkg]}")
            else:
                lines.append(pkg)
        return "\n".join(lines) + "\n"

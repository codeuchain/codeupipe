"""
RenderAdapter: Deploy adapter for Render (https://render.com).

Generates render.yaml blueprint for free-tier deployment:
- Web service (free plan) from Dockerfile
- PostgreSQL database (free plan) when postgres connector declared
- Environment variable wiring between services

Zero external dependencies — pure string template generation.

Usage:
    cup deploy render cup.toml
    cup deploy render cup.toml --dry-run
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .adapter import DeployAdapter, DeployTarget

__all__ = ["RenderAdapter"]


class RenderAdapter(DeployAdapter):
    """Generates Render blueprint (render.yaml) for free-tier cloud deploy."""

    def target(self) -> DeployTarget:
        return DeployTarget(
            name="render",
            description="Render — free-tier web service + Postgres, visible from any browser",
            requires=[],
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
        connectors = pipeline_config.get("connectors", {})
        port = options.get("port", 8000)
        python_version = options.get("python_version", "3.12")

        # 1. render.yaml blueprint
        blueprint = self._render_blueprint(
            project_name, port, connectors, pipeline_config
        )
        blueprint_path = output_dir / "render.yaml"
        blueprint_path.write_text(blueprint)
        generated.append(blueprint_path)

        # 2. Dockerfile (Render builds from it)
        dockerfile_path = output_dir / "Dockerfile"
        dockerfile_path.write_text(
            self._render_dockerfile(port, python_version)
        )
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
        if dry_run:
            return (
                f"[dry-run] Would deploy {output_dir} to Render\n"
                f"Blueprint: {output_dir}/render.yaml\n"
                f"Steps:\n"
                f"  1. Push render.yaml to your GitHub repo\n"
                f"  2. Go to https://dashboard.render.com/select-repo?type=blueprint\n"
                f"  3. Select your repo → Render deploys automatically\n"
                f"  4. Free plan — no credit card required"
            )

        blueprint_path = output_dir / "render.yaml"
        if not blueprint_path.exists():
            return (
                f"No render.yaml found in {output_dir}/\n"
                f"Run: cup deploy render cup.toml --output-dir {output_dir}"
            )

        return (
            f"Render artifacts generated in {output_dir}/\n"
            f"\n"
            f"Deploy steps:\n"
            f"  1. Copy these files to your project root\n"
            f"  2. Push to GitHub\n"
            f"  3. Go to: https://dashboard.render.com/select-repo?type=blueprint\n"
            f"  4. Select your repo and click 'Apply'\n"
            f"  5. Render provisions your services (web + database) automatically\n"
            f"\n"
            f"Free tier — no credit card required.\n"
            f"Your app will be live at: https://<your-service>.onrender.com"
        )

    # ── Internal ────────────────────────────────────────────────

    @staticmethod
    def _render_blueprint(
        project_name: str,
        port: int,
        connectors: dict,
        pipeline_config: dict,
    ) -> str:
        """Render render.yaml blueprint."""
        lines = [
            "# Auto-generated Render Blueprint by cup deploy",
            "# Docs: https://docs.render.com/blueprint-spec",
            "",
        ]

        # Databases section — declared first so services can reference them
        postgres_connectors = {
            cname: cblock
            for cname, cblock in connectors.items()
            if cblock.get("provider") == "postgres"
        }

        if postgres_connectors:
            lines.append("databases:")
            for cname, cblock in postgres_connectors.items():
                db_name = f"{project_name}-{cname}"
                lines.extend([
                    f"  - name: {db_name}",
                    f"    plan: free",
                    f"    databaseName: {project_name.replace('-', '_')}",
                    f"    user: {project_name.replace('-', '_')}",
                    "",
                ])

        # Services section
        lines.append("services:")
        lines.extend([
            f"  - type: web",
            f"    name: {project_name}",
            f"    plan: free",
            f"    runtime: docker",
            f"    dockerfilePath: ./Dockerfile",
        ])

        # Env vars
        env_vars: List[Dict[str, Any]] = []

        # Wire postgres DATABASE_URL from Render's managed database
        for cname, cblock in postgres_connectors.items():
            conn_env = cblock.get("connection_string_env", "DATABASE_URL")
            db_name = f"{project_name}-{cname}"
            env_vars.append({
                "key": conn_env,
                "fromDatabase": {"name": db_name, "property": "connectionString"},
            })

        # Other connector env vars — user sets in Render dashboard
        for cname, cblock in connectors.items():
            if cblock.get("provider") == "postgres":
                continue
            for key, val in cblock.items():
                if key == "provider":
                    continue
                if key.endswith("_env"):
                    env_vars.append({
                        "key": val,
                        "sync": False,
                    })

        # Port
        env_vars.append({"key": "PORT", "value": str(port)})

        if env_vars:
            lines.append("    envVars:")
            for ev in env_vars:
                lines.append(f"      - key: {ev['key']}")
                if "fromDatabase" in ev:
                    db_ref = ev["fromDatabase"]
                    lines.append(f"        fromDatabase:")
                    lines.append(f"          name: {db_ref['name']}")
                    lines.append(f"          property: {db_ref['property']}")
                elif "value" in ev:
                    lines.append(f"        value: \"{ev['value']}\"")
                elif ev.get("sync") is False:
                    lines.append(f"        sync: false  # Set in Render dashboard")

        lines.append("")
        return "\n".join(lines) + "\n"

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
            '"""Auto-generated pipeline entrypoint by cup deploy (Render)."""\n'
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
            "            self.send_header('Access-Control-Allow-Origin', '*')\n"
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
            "        def do_OPTIONS(self):\n"
            "            self.send_response(204)\n"
            "            self.send_header('Access-Control-Allow-Origin', '*')\n"
            "            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')\n"
            "            self.send_header('Access-Control-Allow-Headers', 'Content-Type')\n"
            "            self.end_headers()\n"
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

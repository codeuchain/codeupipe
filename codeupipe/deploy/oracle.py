"""
OracleAdapter: Deploy adapter for Oracle Cloud Always Free (https://cloud.oracle.com).

Generates docker-compose.yml + deploy.sh for Oracle Cloud deployment:
- 4 ARM Ampere cores + 24 GB RAM (Always Free)
- Docker Compose on a persistent VM
- SSH-based deployment script
- Ideal for long-running services and databases

Zero external dependencies — pure string template generation.

Usage:
    cup deploy oracle cup.toml
    cup deploy oracle cup.toml --dry-run
"""

import json
from pathlib import Path
from typing import List

from .adapter import DeployAdapter, DeployTarget

__all__ = ["OracleAdapter"]


class OracleAdapter(DeployAdapter):
    """Generates docker-compose.yml + deploy.sh for Oracle Cloud Always Free VM."""

    def target(self) -> DeployTarget:
        return DeployTarget(
            name="oracle",
            description="Oracle Cloud Always Free — 4 ARM cores, 24 GB RAM, persistent VM",
            requires=["ssh", "docker"],
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

        # 1. docker-compose.yml
        compose_path = output_dir / "docker-compose.yml"
        compose_path.write_text(
            self._render_compose(project_name, port, pipeline_config)
        )
        generated.append(compose_path)

        # 2. deploy.sh
        deploy_path = output_dir / "deploy.sh"
        deploy_path.write_text(
            self._render_deploy_script(project_name)
        )
        deploy_path.chmod(0o755)
        generated.append(deploy_path)

        # 3. Dockerfile
        dockerfile_path = output_dir / "Dockerfile"
        dockerfile_path.write_text(self._render_dockerfile(port, python_version))
        generated.append(dockerfile_path)

        # 4. Pipeline config
        config_path = output_dir / "pipeline.json"
        config_path.write_text(json.dumps(pipeline_config, indent=2))
        generated.append(config_path)

        # 5. Entrypoint
        entrypoint_path = output_dir / "entrypoint.py"
        entrypoint_path.write_text(self._render_entrypoint(port))
        generated.append(entrypoint_path)

        # 6. Requirements
        reqs_path = output_dir / "requirements.txt"
        reqs_path.write_text(self._render_requirements(pipeline_config))
        generated.append(reqs_path)

        return generated

    def deploy(self, output_dir: Path, *, dry_run: bool = False, **options) -> str:
        ssh_host = options.get("ssh_host", "YOUR_VM_IP")

        if dry_run:
            return (
                f"[dry-run] Would deploy {output_dir} to Oracle Cloud VM\n"
                f"Host: {ssh_host}\n"
                f"Config: {output_dir}/docker-compose.yml\n"
                f"Steps:\n"
                f"  1. scp files to VM\n"
                f"  2. docker compose up -d\n"
                f"  3. Always Free — 4 ARM cores, 24 GB RAM"
            )

        return (
            f"Oracle Cloud artifacts generated in {output_dir}/\n"
            f"\n"
            f"Deploy steps:\n"
            f"  1. cd {output_dir}\n"
            f"  2. Edit deploy.sh — set SSH_HOST to your VM IP\n"
            f"  3. chmod +x deploy.sh && ./deploy.sh\n"
            f"\n"
            f"Prerequisites:\n"
            f"  - Oracle Cloud Always Free VM provisioned (ARM A1.Flex)\n"
            f"  - SSH key configured\n"
            f"  - Docker + Docker Compose installed on VM\n"
            f"\n"
            f"Always Free tier: 4 ARM Ampere cores, 24 GB RAM, 200 GB storage."
        )

    # ── Internal ────────────────────────────────────────────────

    @staticmethod
    def _render_compose(
        project_name: str,
        port: int,
        pipeline_config: dict,
    ) -> str:
        connectors = pipeline_config.get("connectors", {})
        has_postgres = any(
            c.get("provider") == "postgres" for c in connectors.values()
        )

        lines = [
            "# Auto-generated Docker Compose for Oracle Cloud by cup deploy",
            "version: '3.8'",
            "",
            "services:",
            f"  {project_name}:",
            "    build: .",
            "    ports:",
            f'      - "{port}:{port}"',
            "    restart: unless-stopped",
        ]

        env_lines = []
        for name, connector in connectors.items():
            if connector.get("provider") == "postgres" and has_postgres:
                env_lines.append(
                    f"      DATABASE_URL: postgres://cup:cup@postgres:5432/{project_name}"
                )
            else:
                for key in connector.get("env", {}):
                    env_lines.append(f'      {key}: ""')

        if env_lines:
            lines.append("    environment:")
            lines.extend(env_lines)

        if has_postgres:
            lines.append(f"    depends_on:")
            lines.append(f"      - postgres")
            lines.extend([
                "",
                "  postgres:",
                "    image: postgres:16-alpine",
                "    volumes:",
                "      - pgdata:/var/lib/postgresql/data",
                "    environment:",
                "      POSTGRES_USER: cup",
                "      POSTGRES_PASSWORD: cup",
                f"      POSTGRES_DB: {project_name}",
                "    restart: unless-stopped",
            ])

        if has_postgres:
            lines.extend([
                "",
                "volumes:",
                "  pgdata:",
            ])

        lines.append("")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _render_deploy_script(project_name: str) -> str:
        return (
            "#!/usr/bin/env bash\n"
            "# Auto-generated Oracle Cloud deploy script by cup deploy\n"
            "# Edit SSH_HOST and SSH_KEY before running.\n"
            "set -euo pipefail\n"
            "\n"
            'SSH_HOST="${SSH_HOST:-YOUR_VM_IP}"\n'
            'SSH_USER="${SSH_USER:-opc}"\n'
            'SSH_KEY="${SSH_KEY:-~/.ssh/id_rsa}"\n'
            f'APP_DIR="/home/$SSH_USER/{project_name}"\n'
            "\n"
            'echo "Deploying to Oracle Cloud VM at $SSH_HOST..."\n'
            "\n"
            "# Create app directory on VM\n"
            'ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "mkdir -p $APP_DIR"\n'
            "\n"
            "# Copy files\n"
            'scp -i "$SSH_KEY" \\\n'
            "  docker-compose.yml Dockerfile entrypoint.py \\\n"
            "  pipeline.json requirements.txt \\\n"
            '  "$SSH_USER@$SSH_HOST:$APP_DIR/"\n'
            "\n"
            "# Build and start\n"
            'ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" "\\\n'
            "  cd $APP_DIR && \\\n"
            "  docker compose pull && \\\n"
            "  docker compose build && \\\n"
            '  docker compose up -d"\n'
            "\n"
            'echo "Deployment complete! Service running at http://$SSH_HOST:8080"\n'
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
            '"""Auto-generated pipeline entrypoint by cup deploy (Oracle Cloud)."""\n'
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

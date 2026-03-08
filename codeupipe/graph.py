"""
codeupipe.graph — Pipeline visualization as Mermaid diagrams.

Reads a pipeline config (.json) and generates a Mermaid flowchart
showing the data flow through filters, taps, and parallel groups.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = ["pipeline_to_mermaid", "render_graph"]


def pipeline_to_mermaid(config: Dict[str, Any]) -> str:
    """Convert a pipeline config dict to a Mermaid flowchart string.

    Args:
        config: Parsed pipeline config with 'pipeline.steps' list.

    Returns:
        Mermaid diagram string.
    """
    pipeline = config.get("pipeline", config)
    name = pipeline.get("name", "pipeline")
    steps = pipeline.get("steps", [])

    lines = [
        f"graph TD",
        f"    START([\"Input\"]) --> {_node_id(0, steps)}",
    ]

    for i, step in enumerate(steps):
        step_name = step.get("name", f"step_{i}")
        step_type = step.get("type", "filter")
        node_id = _node_id(i, steps)

        # Shape by type
        if step_type == "tap":
            lines.append(f"    {node_id}[/\"{step_name}\"/]")
        elif step_type == "parallel":
            lines.append(f"    {node_id}{{{{\"⫘ {step_name}\"}}}}")
        elif step_type == "valve":
            lines.append(f"    {node_id}{{{{\"{step_name}\"}}}}") 
        else:
            lines.append(f"    {node_id}[\"{step_name}\"]")

        # Edge to next
        if i < len(steps) - 1:
            next_id = _node_id(i + 1, steps)
            lines.append(f"    {node_id} --> {next_id}")
        else:
            lines.append(f"    {node_id} --> END([\"Output\"])")

    # Style classes
    lines.extend([
        "",
        "    classDef filter fill:#2196F3,color:#fff,stroke:#1565C0",
        "    classDef tap fill:#FF9800,color:#fff,stroke:#E65100",
        "    classDef valve fill:#9C27B0,color:#fff,stroke:#6A1B9A",
        "    classDef parallel fill:#4CAF50,color:#fff,stroke:#2E7D32",
    ])

    # Apply styles
    for i, step in enumerate(steps):
        step_type = step.get("type", "filter")
        node_id = _node_id(i, steps)
        if step_type in ("filter", "tap", "valve", "parallel"):
            lines.append(f"    class {node_id} {step_type}")

    return "\n".join(lines)


def render_graph(config_path: str) -> str:
    """Load a pipeline config file and return its Mermaid diagram."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    text = path.read_text()
    config = json.loads(text)
    return pipeline_to_mermaid(config)


def _node_id(index: int, steps: list) -> str:
    """Generate a safe Mermaid node ID from a step index."""
    if index < len(steps):
        name = steps[index].get("name", f"step_{index}")
        # Sanitize for Mermaid IDs
        safe = name.replace(" ", "_").replace("-", "_").replace("$", "").replace("{", "").replace("}", "")
        return f"S{index}_{safe}"
    return f"S{index}"

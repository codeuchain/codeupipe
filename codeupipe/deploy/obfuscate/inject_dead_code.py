"""InjectDeadCode — insert syntactically valid non-functional code into extracted blocks."""

import random
from typing import Any, Dict, List

from codeupipe import Payload


# ── Dead code snippet templates ─────────────────────────
# These are syntactically valid JS that have no side effects.
# Used to bloat source and confuse reverse engineering.

_DEAD_VAR_TEMPLATES = [
    "var _cup{n} = {val};",
    "var _h{n} = '{sval}';",
    "var _d{n} = [{val}, {val2}];",
    "var _m{n} = {{{key}: {val}}};",
]

_DEAD_IF_TEMPLATES = [
    "if (typeof _cup{n} === 'undefined') {{ var _cup{n} = {val}; }}",
    "if (false) {{ var _x{n} = {val}; }}",
    "if (void 0) {{ console.debug(_cup{n}); }}",
]

_DEAD_FUNC_TEMPLATES = [
    "function _fn{n}() {{ return {val}; }}",
    "function _gn{n}(a) {{ return a + {val}; }}",
    "var _ln{n} = function() {{ return '{sval}'; }};",
]

# Density → number of snippets per block
_DENSITY_MAP = {
    "low": 2,
    "medium": 5,
    "high": 12,
}

_STRING_POOL = [
    "init", "process", "handle", "validate", "transform",
    "parse", "resolve", "compute", "execute", "dispatch",
    "render", "compile", "optimize", "serialize", "normalize",
]


def _generate_snippet(rng: random.Random, idx: int) -> str:
    """Generate a single dead code snippet."""
    val = rng.randint(0, 99999)
    val2 = rng.randint(0, 99999)
    sval = rng.choice(_STRING_POOL)
    key = rng.choice(_STRING_POOL)

    category = rng.choice(["var", "if", "func"])
    if category == "var":
        template = rng.choice(_DEAD_VAR_TEMPLATES)
    elif category == "if":
        template = rng.choice(_DEAD_IF_TEMPLATES)
    else:
        template = rng.choice(_DEAD_FUNC_TEMPLATES)

    return template.format(n=idx, val=val, val2=val2, sval=sval, key=key)


class InjectDeadCode:
    """Insert syntactically valid but non-functional code into extracted blocks.

    Controlled by ``config.dead_code``:
        - ``enabled`` (bool): Whether to inject.
        - ``density`` (str): "low", "medium", or "high".
        - ``seed`` (int|None): RNG seed for reproducibility.

    Reads:
        - ``code_blocks`` — list of block dicts with ``code`` field.
        - ``config`` — dict with ``dead_code`` sub-dict.

    Writes:
        - ``code_blocks`` — updated blocks with injected dead code.
        - ``dead_code_stats`` — dict with injection counts.
    """

    def call(self, payload: Payload) -> Payload:
        blocks = payload.get("code_blocks") or []
        config = payload.get("config") or {}
        dc_config = config.get("dead_code") or {}

        enabled = dc_config.get("enabled", False)

        if not enabled or not blocks:
            stats = {"total": len(blocks), "injected": 0, "snippets_added": 0}
            return (
                payload
                .insert("code_blocks", list(blocks))
                .insert("dead_code_stats", stats)
            )

        density = dc_config.get("density", "medium")
        seed = dc_config.get("seed")
        snippets_per_block = _DENSITY_MAP.get(density, _DENSITY_MAP["medium"])

        rng = random.Random(seed)

        results: List[dict] = []
        total_snippets = 0

        for block in blocks:
            entry = dict(block)
            original_code = block.get("code", "")

            # Generate dead code snippets
            snippets = []
            for i in range(snippets_per_block):
                snippet_idx = total_snippets + i
                snippets.append(_generate_snippet(rng, snippet_idx))

            total_snippets += len(snippets)

            # Interleave: dead code before original, some after
            split_point = len(snippets) // 2
            before = "\n".join(snippets[:split_point])
            after = "\n".join(snippets[split_point:])

            injected = f"{before}\n{original_code}\n{after}"
            entry["code"] = injected
            results.append(entry)

        stats = {
            "total": len(blocks),
            "injected": len(results),
            "snippets_added": total_snippets,
        }

        return (
            payload
            .insert("code_blocks", results)
            .insert("dead_code_stats", stats)
        )

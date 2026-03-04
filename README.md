# codeupipe

Python pipeline framework — composable State-Link-Chain pattern.

Forked from [codeuchain](https://github.com/codeuchain/codeuchain) (Python implementation only).

## Install

```bash
pip install -e .
```

## Quick Start

```python
from codeuchain import State, Link, Chain

# Define links
class CleanInput(Link):
    async def call(self, ctx):
        ctx = ctx.insert("text", ctx.get("text").strip())
        return ctx

class Validate(Link):
    async def call(self, ctx):
        if not ctx.get("text"):
            raise ValueError("Empty input")
        return ctx

# Build and run a chain
chain = Chain()
chain.add_link(CleanInput(name="clean"))
chain.add_link(Validate(name="validate"))

import asyncio
result = asyncio.run(chain.execute(State({"text": "  hello  "})))
print(result.get("text"))  # "hello"
```

## Test

```bash
pytest
```

## License

Apache 2.0

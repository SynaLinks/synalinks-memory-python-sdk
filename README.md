# Synalinks Memory Python SDK

**Synalinks Memory** is the knowledge and context layer for AI agents. It lets your agents always have the right context at the right time. Unlike retrieval systems that compound LLM errors at every step, Synalinks uses **logical rules** to derive knowledge from your raw data. Every claim can be traced back to evidence, from raw data to insight, no more lies or hallucinations.

This SDK provides a Python client to interact with the Synalinks Memory API, so your agents can store, query, and reason over their knowledge base programmatically.

## Installation

```bash
pip install synalinks-memory
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add synalinks-memory
```

## Quick Start

Set your API key as an environment variable:

```bash
export SYNALINKS_API_KEY="synalinks_..."
```

Then query your data:

```python
from synalinks_memory import SynalinksMemory

with SynalinksMemory() as client:
    # List all available tables, concepts, and rules
    predicates = client.list()
    for table in predicates.tables:
        print(f"{table.name}: {table.description}")

    # Fetch rows from a table
    result = client.execute("Users", limit=10)
    for row in result.rows:
        print(row)

    # Search with keywords (fuzzy matching)
    result = client.search("Users", "alice")
    for row in result.rows:
        print(row)

    # Upload a CSV or Parquet file
    upload = client.upload("data/sales.csv", name="Sales", description="Monthly sales data")
    print(f"Uploaded {upload.predicate} ({upload.row_count} rows)")

    # Export data as a file (CSV, Parquet, or JSON)
    client.execute("Users", format="csv", output="users.csv")
    client.execute("Users", format="parquet", output="users.parquet")

    # Ask the agent a question
    answer = client.ask("What were the top 5 products by revenue last month?")
    print(answer)
```

You can also pass the key directly:

```python
client = SynalinksMemory(api_key="synalinks_...")
```

### Error Handling

```python
from synalinks_memory import (
    SynalinksMemory,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
)

with SynalinksMemory() as client:
    try:
        result = client.execute("MyTable")
    except AuthenticationError:
        print("Invalid API key")
    except NotFoundError as e:
        print(f"Not found: {e.message}")
    except RateLimitError as e:
        print(f"Rate limited, retry after {e.retry_after}s")
```

## API Reference

### `SynalinksMemory(api_key=None, base_url=None, timeout=30.0)`

| Parameter | Description |
|-----------|-------------|
| `api_key` | Your API key. If omitted, reads from `SYNALINKS_API_KEY` env var. |
| `base_url` | Override the API endpoint (defaults to `https://app.synalinks.com/api`). |
| `timeout` | Request timeout in seconds. |

### Methods

| Method | Description |
|--------|-------------|
| `list()` | List all tables, concepts, and rules |
| `execute(predicate, *, limit=100, offset=0, format=None, output=None)` | Fetch rows (or export as json/csv/parquet file when *format* is set) |
| `search(predicate, keywords, *, limit=100, offset=0)` | Search rows by keywords (fuzzy matching) |
| `upload(file_path, *, name=None, description=None, overwrite=False)` | Upload a CSV or Parquet file as a new table |
| `ask(question)` | Ask the agent a question, returns the answer string |
| `close()` | Close the HTTP client (not needed with `with` statement) |

## License

Apache 2.0

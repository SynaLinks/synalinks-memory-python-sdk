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

A **Synalinks API key** is required to authenticate with your knowledge base.

When you create a knowledge base on [app.synalinks.com](https://app.synalinks.com), a **default API key** is generated automatically with read/write access and no predicate restrictions — you can use it right away.

To create a key with granular access, go to **Profile icon** (in the header) > **API Keys** > **Create API Key**.

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

    # Insert a row
    client.insert("Users", {"name": "Alice", "email": "alice@example.com"})

    # Update rows matching a filter
    result = client.update("Users", filter={"name": "Alice"}, values={"email": "alice@new.com"})
    print(f"Updated {result.updated_count} row(s)")

    # Export data as a file (CSV, Parquet, or JSON)
    client.execute("Users", format="csv", output="users.csv")
    client.execute("Users", format="parquet", output="users.parquet")

    # Chat with the agent (multi-turn)
    answer = client.chat("What were the top 5 products by revenue last month?")
    print(answer)

    # Follow-up question (uses conversation context automatically)
    answer = client.chat("Show me just the top 3")
    print(answer)

    # Reset conversation history
    client.clear()
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
| `insert(predicate, row)` | Insert a single row into a table |
| `update(predicate, filter, values)` | Update rows matching a filter with new values |
| `chat(question)` | Chat with the agent (multi-turn), returns the answer string |
| `clear()` | Reset conversation history for a fresh chat |
| `close()` | Close the HTTP client (not needed with `with` statement) |

## License

Licensed under Apache 2.0. See the [LICENSE](LICENSE) file for full details.
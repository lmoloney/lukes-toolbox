# Event Hub Reader

CLI tool for reading events from Azure Event Hubs. Supports streaming new events, reading historical data, and tailing recent messages — with text or JSON output.

## Setup

```bash
cd eventhubs

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure your connection string
cp .env.example .env
# Edit .env with your Event Hub connection string
```

The connection string must include an `EntityPath` segment:

```
Endpoint=sb://<namespace>.servicebus.windows.net/;SharedAccessKeyName=<key-name>;SharedAccessKey=<key>;EntityPath=<eventhub-name>
```

## Usage

```bash
source .venv/bin/activate
python read_eventhub.py [options]
```

### Read modes

| Flag | Behaviour |
|------|-----------|
| `--latest` | Wait for new events only (default) |
| `--beginning` | Read all events from the start of retention |
| `--tail N` | Read the last N events per partition, then keep listening |

These are mutually exclusive — pick one.

### Filtering and limits

| Flag | Description |
|------|-------------|
| `--partition ID` | Read from a single partition instead of all |
| `--max-events N` | Stop after receiving N events |
| `--timeout SECS` | Stop after N seconds |
| `--consumer-group GROUP` | Consumer group to use (default: `$Default`) |

### Output

| Flag | Description |
|------|-------------|
| `--output text` | Human-readable format with timestamps and metadata (default) |
| `--output json` | One JSON object per line (NDJSON), suitable for piping to `jq` |

### Connection

| Flag | Description |
|------|-------------|
| `--connection-string STRING` | Pass connection string directly (overrides `.env` / env var) |

The tool resolves the connection string in this order:

1. `--connection-string` flag
2. `EVENTHUB_CONNECTION_STRING` environment variable
3. `.env` file in the script's directory

## Examples

```bash
# Stream new events as they arrive
python read_eventhub.py

# Read all retained events, stop after 30 seconds
python read_eventhub.py --beginning --timeout 30

# Tail the last 100 events per partition
python read_eventhub.py --tail 100

# Read 10 events from partition 2 as JSON
python read_eventhub.py --partition 2 --max-events 10 --output json

# Pipe JSON output to jq for filtering
python read_eventhub.py --beginning --output json | jq 'select(.body.level == "error")'

# Use a specific consumer group
python read_eventhub.py --consumer-group my-group --latest

# Pass connection string inline (no .env needed)
python read_eventhub.py --connection-string "Endpoint=sb://..." --beginning --timeout 10
```

## Output formats

### Text (default)

```
[2026-03-23 17:30:01.234] partition=0 seq=42 offset=1024
{
  "temperature": 22.5,
  "sensor": "room-3"
}
```

### JSON (`--output json`)

```json
{"partition":"0","sequence":42,"offset":"1024","enqueued_time":"2026-03-23T17:30:01.234000+00:00","body":{"temperature":22.5,"sensor":"room-3"}}
```

## Stopping

- **Ctrl+C** — graceful shutdown at any time
- **`--timeout`** — automatic shutdown after N seconds
- **`--max-events`** — automatic shutdown after N events

## Requirements

- Python 3.9+
- `azure-eventhub` ≥ 5.11
- `python-dotenv` ≥ 1.0

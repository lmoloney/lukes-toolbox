#!/usr/bin/env python3
"""Read events from Azure Event Hub with flexible CLI options.

Usage:
    # Wait for new events (default)
    python read_eventhub.py

    # Read all historical events
    python read_eventhub.py --beginning

    # Read last 50 events per partition, then keep listening
    python read_eventhub.py --tail 50

    # Read from a specific partition, stop after 10 events, output JSON
    python read_eventhub.py --partition 0 --max-events 10 --output json

    # Run for 30 seconds then stop
    python read_eventhub.py --beginning --timeout 30
"""

import argparse
import json
import os
import sys
import threading
from pathlib import Path

from azure.eventhub import EventHubConsumerClient
from dotenv import load_dotenv


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read events from Azure Event Hub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--latest", action="store_true", default=True,
        help="Wait for new events only (default)",
    )
    mode.add_argument(
        "--beginning", action="store_true",
        help="Read all events from the start of retention",
    )
    mode.add_argument(
        "--tail", type=int, metavar="N",
        help="Read last N events per partition, then keep listening",
    )

    parser.add_argument(
        "--consumer-group", default="$Default",
        help="Consumer group (default: $Default)",
    )
    parser.add_argument(
        "--partition", metavar="ID",
        help="Read from a specific partition ID only",
    )
    parser.add_argument(
        "--timeout", type=int, default=0, metavar="SECS",
        help="Stop after N seconds (0 = run until Ctrl+C)",
    )
    parser.add_argument(
        "--max-events", type=int, default=0, metavar="N",
        help="Stop after N total events (0 = unlimited)",
    )
    parser.add_argument(
        "--output", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--connection-string",
        help="Event Hub connection string (overrides EVENTHUB_CONNECTION_STRING env var)",
    )

    return parser.parse_args()


def format_event_text(event, partition_id):
    """Format an event as human-readable text."""
    ts = event.enqueued_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if event.enqueued_time else "?"
    body = event.body_as_str()

    # Pretty-print JSON bodies
    try:
        body = json.dumps(json.loads(body), indent=2)
    except (json.JSONDecodeError, TypeError):
        pass

    header = f"[{ts}] partition={partition_id} seq={event.sequence_number} offset={event.offset}"

    if event.properties:
        props = _decode_props(event.properties)
        header += f" props={json.dumps(props)}"

    return f"{header}\n{body}\n"


def format_event_json(event, partition_id):
    """Format an event as a single JSON line."""
    body = event.body_as_str()
    try:
        body = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        pass

    record = {
        "partition": partition_id,
        "sequence": event.sequence_number,
        "offset": str(event.offset),
        "enqueued_time": event.enqueued_time.isoformat() if event.enqueued_time else None,
        "body": body,
    }
    if event.properties:
        record["properties"] = _decode_props(event.properties)
    if event.system_properties:
        record["system_properties"] = _decode_props(event.system_properties)

    return json.dumps(record)


def _decode_props(props):
    """Decode byte keys/values in property dicts."""
    return {
        (k.decode() if isinstance(k, bytes) else str(k)): (v.decode() if isinstance(v, bytes) else v)
        for k, v in props.items()
    }


def resolve_starting_position(args, client):
    """Determine starting position based on CLI flags."""
    if args.beginning:
        return "-1"

    if args.tail and args.tail > 0:
        positions = {}
        partition_ids = [args.partition] if args.partition else client.get_partition_ids()
        for pid in partition_ids:
            props = client.get_partition_properties(pid)
            last_seq = props["last_enqueued_sequence_number"]
            # Start N events before the end; -1 means beginning of stream
            positions[pid] = max(-1, last_seq - args.tail)
        return positions

    return "@latest"


def main():
    # Load .env from the script's own directory
    load_dotenv(Path(__file__).parent / ".env")
    args = parse_args()

    conn_str = args.connection_string or os.environ.get("EVENTHUB_CONNECTION_STRING")
    if not conn_str:
        print("Error: No connection string provided.", file=sys.stderr)
        print("Set EVENTHUB_CONNECTION_STRING or use --connection-string.", file=sys.stderr)
        sys.exit(1)

    client = EventHubConsumerClient.from_connection_string(
        conn_str,
        consumer_group=args.consumer_group,
    )

    formatter = format_event_json if args.output == "json" else format_event_text
    event_count = 0
    lock = threading.Lock()

    def on_event(partition_context, event):
        nonlocal event_count
        if event is None:
            return

        output = formatter(event, partition_context.partition_id)

        with lock:
            event_count += 1
            print(output, flush=True)

            if args.max_events and event_count >= args.max_events:
                print(f"--- Reached {args.max_events} events, stopping ---", file=sys.stderr)
                client.close()

    def on_error(partition_context, error):
        if isinstance(error, KeyboardInterrupt):
            return
        pid = partition_context.partition_id if partition_context else "?"
        print(f"Error on partition {pid}: {error}", file=sys.stderr)

    with client:
        starting_position = resolve_starting_position(args, client)

        # Print session info
        partition_ids = client.get_partition_ids()
        eh_name = client.eventhub_name
        target = args.partition if args.partition else f"all {len(partition_ids)} partitions"
        mode = "beginning" if args.beginning else f"tail {args.tail}" if args.tail else "latest"
        print(f"--- Reading {eh_name} | {target} | mode={mode} | Ctrl+C to stop ---", file=sys.stderr)

        if args.timeout:
            timer = threading.Timer(args.timeout, lambda: (
                print(f"\n--- Timeout after {args.timeout}s, stopping ---", file=sys.stderr),
                client.close(),
            ))
            timer.daemon = True
            timer.start()

        try:
            client.receive(
                on_event=on_event,
                on_error=on_error,
                starting_position=starting_position,
                partition_id=args.partition,
            )
        except KeyboardInterrupt:
            pass

    print(f"--- Done. {event_count} events received ---", file=sys.stderr)


if __name__ == "__main__":
    main()

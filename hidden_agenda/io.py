"""Shared JSONL storage helpers."""
import json
from pathlib import Path

def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]

def write_rows(path, rows):
    with Path(path).open('x') as stream:
        for row in rows:
            stream.write(json.dumps(row) + '\n')

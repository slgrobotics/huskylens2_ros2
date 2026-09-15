#!/usr/bin/env python3

import base64
import json
import queue
import sys
import time
import statistics
import threading
from pathlib import Path
from urllib.parse import urljoin
import requests

"""
This is a modified version of mcp_capure.py that benchmarks the latency of MCP calls to self.get_recognition_result.

How to run (you need to select an algorithm from the HuskyLens 2 menu first):

# Benchmark MCP calls to self.get_recognition_result
python3 mcp_benchmark.py  --benchmark 2 10

# Check the active algorithm ID
python3 mcp_benchmark.py self.manage_applications.current_application '{}'

# Retrieve the image to "/tmp/huskylens-capture..." (replace 2 if the first command reports another ID)
python3 mcp_benchmark.py self.get_recognition_result '{"algorithm":2}'

"""


base = 'http://huskylens.local:3000/sse'
events = queue.Queue()

def read_events():
    try:
        with requests.get(base, stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            kind, data = '', []
            for line in response.iter_lines(chunk_size=1, decode_unicode=True):
                if not line:
                    if data:
                        events.put((kind, '\n'.join(data)))
                        kind, data = '', []
                elif line.startswith('event:'):
                    kind = line[6:].strip()
                elif line.startswith('data:'):
                    data.append(line[5:].strip())
    except Exception as exc:
        events.put(('error', str(exc)))

threading.Thread(target=read_events, daemon=True).start()
kind, endpoint = events.get(timeout=15)
if kind != 'endpoint':
    raise RuntimeError((kind, endpoint))
endpoint = urljoin(base, endpoint)

def send(method, params, ident=None):
    payload = dict(
        jsonrpc='2.0',
        method=method,
        params=params
    )

    if ident is not None:
        payload['id'] = ident

    r = requests.post(
        endpoint,
        json=payload,
        timeout=15
    )
    r.raise_for_status()

    if ident is None:
        return

    while True:
        kind, raw = events.get(timeout=45)

        if kind == 'error':
            raise RuntimeError(raw)

        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue

        # The SSE stream may contain data that isn't
        # a JSON-RPC response object.
        if not isinstance(value, dict):
            continue

        if value.get('id') != ident:
            continue

        if 'error' in value:
            raise RuntimeError(value['error'])

        return value['result']
    
send('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'camera-capture', 'version': '1.0'}}, 1)
send('notifications/initialized', {})

def benchmark(algorithm, count=100):
    latencies = []

    print(f"Benchmarking self.get_recognition_result")
    print(f"Algorithm: {algorithm}")
    print(f"Requests:  {count}")
    print()

    start_total = time.perf_counter()

    for i in range(count):
        start = time.perf_counter()

        result = send(
            'tools/call',
            {
                'name': 'self.get_recognition_result',
                'arguments': {'algorithm': algorithm}
            },
            i + 100
        )

        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

        print(
            f"{i + 1:4d}: "
            f"{elapsed * 1000:7.1f} ms   "
            f"{1.0 / elapsed:5.2f} calls/s"
        )

    total = time.perf_counter() - start_total

    print()
    print("Results")
    print("-------")
    print(f"Total time:       {total:.3f} s")
    print(f"Requests:         {count}")
    print(f"Average rate:     {count / total:.2f} calls/s")
    print(f"Average latency:  {statistics.mean(latencies) * 1000:.1f} ms")
    print(f"Median latency:   {statistics.median(latencies) * 1000:.1f} ms")
    print(f"Minimum latency:  {min(latencies) * 1000:.1f} ms")
    print(f"Maximum latency:  {max(latencies) * 1000:.1f} ms")


if len(sys.argv) == 1:
    print(json.dumps(send('tools/list', {}, 2), indent=2))

elif sys.argv[1] == '--benchmark':
    algorithm = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 100

    benchmark(algorithm, count)

else:
    result = send(
        'tools/call',
        {
            'name': sys.argv[1],
            'arguments': json.loads(sys.argv[2])
        },
        2
    )

    for i, item in enumerate(result.get('content', [])):
        if item.get('type') == 'image':
            ext = 'png' if item.get('mimeType') == 'image/png' else 'jpg'
            path = Path(f'/tmp/huskylens-capture-{i}.{ext}')
            path.write_bytes(base64.b64decode(item['data']))
            print(f'Image saved: {path}')
        else:
            print(json.dumps(item))


import base64
import json
import queue
import sys
import threading
from pathlib import Path
from urllib.parse import urljoin
import requests

"""
This is a simple caller for the HuskyLens 2 MCP Server.
It uses very standard Python libraries (requests, json, base64) to avoid installing additional dependencies.
It connects to the server, initializes the session, and sends a request to retrieve the recognition result (including the image).

How to run:

# Check the active algorithm ID (you need to select one from the HuskyLens 2 menu first)
python3 mcp_capure.py self.manage_applications.current_application '{}'

# Retrieve the image to "/tmp/huskylens-capture..." (replace 2 if the first command reports another ID)
python3 mcp_capure.py self.get_recognition_result '{"algorithm":2}'

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
    payload = dict(jsonrpc='2.0', method=method, params=params)
    if ident is not None:
        payload['id'] = ident
    r = requests.post(endpoint, json=payload, timeout=15)
    r.raise_for_status()
    if ident is None:
        return
    while True:
        kind, raw = events.get(timeout=45)
        if kind == 'error':
            raise RuntimeError(raw)
        value = json.loads(raw)
        if value.get('id') == ident:
            if 'error' in value:
                raise RuntimeError(value['error'])
            return value['result']

send('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'camera-capture', 'version': '1.0'}}, 1)
send('notifications/initialized', {})
if len(sys.argv) == 1:
    print(json.dumps(send('tools/list', {}, 2), indent=2))
else:
    result = send('tools/call', {'name': sys.argv[1], 'arguments': json.loads(sys.argv[2])}, 2)
    for i, item in enumerate(result.get('content', [])):
        if item.get('type') == 'image':
            ext = 'png' if item.get('mimeType') == 'image/png' else 'jpg'
            path = Path(f'/tmp/huskylens-capture-{i}.{ext}')
            path.write_bytes(base64.b64decode(item['data']))
            print(f'Image saved: {path}')
        else:
            print(json.dumps(item))


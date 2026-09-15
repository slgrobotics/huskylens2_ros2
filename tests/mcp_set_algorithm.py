#!/usr/bin/env python3

import json
import queue
import threading
from urllib.parse import urljoin

import requests

"""
Minimal helper to switch the HuskyLens 2 to Object Recognition (algorithm 2)
and exit immediately so the menu-screen change can be observed.

Usage:
    python3 mcp_set_algorithm.py
"""

BASE_URL = 'http://huskylens.local:3000'
SSE_URL = f'{BASE_URL}/sse'
ALGORITHM_ID = 2  # Object Recognition


def read_events(events):
    try:
        with requests.get(SSE_URL, stream=True, timeout=(10, 60)) as response:
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


def send(session, endpoint, events, method, params, ident=None):
    payload = dict(jsonrpc='2.0', method=method, params=params)
    if ident is not None:
        payload['id'] = ident
    response = session.post(endpoint, json=payload, timeout=15)
    response.raise_for_status()
    if ident is None:
        return

    while True:
        try:
            kind, raw = events.get(timeout=45)
        except queue.Empty as exc:
            raise TimeoutError(f'MCP response timed out for {method}') from exc
        if kind == 'error':
            raise RuntimeError(raw)
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        if value.get('id') == ident:
            if 'error' in value:
                raise RuntimeError(value['error'])
            if 'result' not in value:
                continue
            return value['result']


def connect(session):
    events = queue.Queue()
    threading.Thread(target=read_events, args=(events,), daemon=True).start()
    try:
        kind, endpoint_path = events.get(timeout=15)
    except queue.Empty as exc:
        raise TimeoutError('Timed out waiting for the MCP endpoint') from exc
    if kind != 'endpoint':
        raise RuntimeError((kind, endpoint_path))

    endpoint = urljoin(SSE_URL, endpoint_path)
    send(session, endpoint, events, 'initialize', {
        'protocolVersion': '2024-11-05',
        'capabilities': {},
        'clientInfo': {'name': 'camera-switcher', 'version': '1.0'},
    }, 1)
    send(session, endpoint, events, 'notifications/initialized', {})
    return endpoint, events


def switch_application(session, endpoint, events):
    print(f'Switching HuskyLens to {ALGORITHM_ID} / Object Recognition...', flush=True)
    result = send(session, endpoint, events, 'tools/call', {
        'name': 'self.manage_applications.switch_application',
        'arguments': {'algorithm': ALGORITHM_ID},
    }, 3)
    print(f'Switch response: {result}', flush=True)
    return result


def main():
    with requests.Session() as session:
        endpoint, events = connect(session)
        try:
            switch_application(session, endpoint, events)
        finally:
            print('Done. Exiting now.', flush=True)


if __name__ == '__main__':
    main()


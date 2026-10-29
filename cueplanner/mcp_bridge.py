"""Minimal read-only MCP stdio client for the third-party mcp-score server.

No mcp-score sources are bundled. This uses documented MCP tools, not the
unversioned private WebSocket plugin API. Use a separate Python 3.14 tool env
for `mcp-score`; the cue analyzer itself runs on Python 3.10+.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from typing import Any


class BridgeError(RuntimeError):
    pass


class ScoreMcpClient:
    def __init__(self, executable='mcp-score', args=('serve',), timeout=15):
        self.command = [executable, *args]
        self.timeout = timeout
        self.process = None
        self._next_id = 0
        self._lines = queue.Queue()
        self._stderr = []

    def __enter__(self):
        try:
            self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          encoding='utf-8', errors='replace', bufsize=1)
        except OSError as exc:
            raise BridgeError(f'Cannot start MCP server {self.command[0]!r}: {exc}') from exc
        threading.Thread(target=self._drain_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        try:
            reply = self.request('initialize', {
                'protocolVersion': '2025-06-18',
                'capabilities': {},
                'clientInfo': {'name':'mcp-score-cue-planner', 'version':'0.2.0'}
            })
            if not isinstance(reply, dict) or not reply.get('protocolVersion'):
                raise BridgeError('Server did not return an MCP initialization response')
            self._send({'jsonrpc':'2.0', 'method':'notifications/initialized'})
            return self
        except Exception:
            self.close()
            raise

    def _drain_stdout(self):
        try:
            for line in self.process.stdout:
                if line.strip():
                    self._lines.put(line.strip())
        finally:
            self._lines.put(None)

    def _drain_stderr(self):
        try:
            for line in self.process.stderr:
                if len(self._stderr) < 25:
                    self._stderr.append(line.strip()[:400])
        except OSError:
            pass

    def _send(self, message):
        if not self.process or self.process.poll() is not None:
            raise BridgeError('MCP server is no longer running')
        try:
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise BridgeError('Lost MCP server stdin') from exc

    def request(self, method: str, params: dict | None = None) -> Any:
        self._next_id += 1
        ident = self._next_id
        self._send({'jsonrpc':'2.0', 'id':ident, 'method':method, 'params':params or {}})
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BridgeError(f'MCP timeout waiting for {method}; {self._stderr[-3:]}')
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise BridgeError(f'MCP timeout waiting for {method}; {self._stderr[-3:]}') from exc
            if line is None:
                raise BridgeError(f'MCP server exited during {method}; {self._stderr[-3:]}')
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BridgeError('Non-JSON data on MCP stdout (is the MCP command correct?)') from exc
            if message.get('id') != ident:
                # Tool progress and notifications are asynchronous.
                # Unexpected request ids are ignored; this client is sequential.
                continue
            if 'error' in message:
                raise BridgeError(f'MCP {method} failed: {message["error"]}')
            return message.get('result')

    def list_tools(self) -> set[str]:
        names = set()
        cursor = None
        for _ in range(10):
            resp = self.request('tools/list', {'cursor':cursor} if cursor else {})
            if not isinstance(resp, dict):
                raise BridgeError('Malformed MCP tool list')
            names.update(t['name'] for t in resp.get('tools', []) if 'name' in t)
            cursor = resp.get('nextCursor')
            if not cursor:
                return names
        raise BridgeError('MCP tools/list pagination limit exceeded')

    def call_tool(self, name: str, arguments=None) -> Any:
        if name not in self.list_tools():
            raise BridgeError(f'MCP tool {name!r} not exposed by installed server')
        reply = self.request('tools/call', {'name':name, 'arguments':arguments or {}})
        if not isinstance(reply, dict) or reply.get('isError'):
            raise BridgeError(f'MCP tool {name!r} error: {reply!r}')
        if 'structuredContent' in reply:
            return reply['structuredContent']
        texts = [x['text'] for x in reply.get('content', []) if x.get('type') == 'text']
        if not texts:
            raise BridgeError(f'No text returned from {name}')
        if len(texts) == 1:
            try:
                return json.loads(texts[0])
            except json.JSONDecodeError:
                return texts[0]
        return texts

    def connect(self, host='localhost', port=8765) -> dict:
        # The default host intentionally stays local. Do not expose bridge to WAN.
        if host not in ('localhost', '127.0.0.1', '::1'):
            raise BridgeError('Only a local MuseScore bridge is allowed')
        if not 1 <= port <= 65535:
            raise BridgeError('Port out of range')
        conn = self.call_tool('connect_to_musescore', {'host':host, 'port':port})
        return {'connection': conn,
                'ping': self.call_tool('ping_score_app'),
                'live_score': self.call_tool('get_live_score_info')}

    def select_measure(self, measure: int, staff: int) -> Any:
        if measure < 1 or staff < 0:
            raise BridgeError('Invalid measure or staff')
        return self.call_tool('get_measure_content', {'measure':measure, 'staff':staff})

    def close(self):
        if not self.process:
            return
        proc = self.process
        self.process = None
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()
                proc.wait(timeout=2)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                stream.close()
            except OSError:
                pass

    def __exit__(self, *_):
        self.close()


def verify_live(offline_plan: dict, live_info: Any) -> dict:
    """Best-effort identity checks; these cannot establish file identity!"""
    info = live_info
    # Most MCP servers serialize ScoreInfo as JSON text; some wrap in structured output.
    if isinstance(info, dict) and 'result' in info and isinstance(info['result'], dict):
        info = info['result']
    if not isinstance(info, dict):
        raise BridgeError('Unexpected live score metadata format')
    checks = {}
    live_measures = info.get('measure_count')
    checks['measure_count_matches'] = isinstance(live_measures, int) and live_measures == offline_plan['measure_count']
    live_parts = info.get('part_count')
    checks['part_count_matches'] = isinstance(live_parts, int) and live_parts == offline_plan['part_count']
    offline_title = offline_plan.get('title') or ''
    live_title = info.get('title') or ''
    checks['title_matches_if_available'] = (not offline_title or not live_title or offline_title == live_title)
    return {'checks':checks,
            'metadata_consistent':all(checks.values()),
            'identity_proven':False,
            'warning':'Matching metadata is not proof that the open score equals the on-disk file; save/check the exact score in MuseScore.',
            'live_score':info}

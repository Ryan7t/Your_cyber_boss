#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Local HTTP server for Electron integration.
Provides chat, config, history, and document endpoints.
"""
import argparse
import json
import os
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from config import settings
from core import BossAgent
from ui.null_ui import NullUI


class AgentService:
    """Wraps BossAgent for HTTP usage."""

    def __init__(self):
        self._lock = threading.Lock()
        self._events = deque()
        self._agent = None
        self._start_agent()

    def _start_agent(self):
        if self._agent is not None:
            self._agent.shutdown()
        self._agent = BossAgent(ui=NullUI())
        self._agent.scheduler.start(self._on_deadline_reached)

    def _on_deadline_reached(self):
        threading.Thread(target=self._auto_followup_worker, daemon=True).start()

    def _auto_followup_worker(self):
        with self._lock:
            response = self._agent.handle_auto_followup()
        if response:
            self._events.append({
                "type": "auto_followup",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "message": response
            })

    def get_history(self):
        with self._lock:
            if self._agent.memory.is_empty():
                self._agent.handle_startup()
            return self._agent.memory.get_all()

    def chat(self, message: str) -> str:
        with self._lock:
            if message is None:
                message = ""
            if not message.strip():
                return self._agent.handle_proactive_followup()
            return self._agent.handle_user_input(message)

    def clear_history(self):
        with self._lock:
            self._agent.memory.clear()
            self._agent.scheduler.clear_deadline()
            self._events.clear()

    def get_events(self):
        events = []
        while self._events:
            events.append(self._events.popleft())
        return events

    def get_config(self):
        return settings.get_runtime_config()

    def update_config(self, updates: dict):
        with self._lock:
            config = settings.update_runtime_config(updates)
            self._start_agent()
            return config

    def get_scheduler_status(self):
        with self._lock:
            return self._agent.scheduler.get_status()

    def list_documents(self):
        documents_dir = settings.documents_dir
        if not documents_dir or not os.path.exists(documents_dir):
            return {
                "documents_dir": documents_dir,
                "files": [],
                "count": 0
            }
        files = [
            name for name in os.listdir(documents_dir)
            if name.lower().endswith(".docx")
        ]
        files.sort()
        return {
            "documents_dir": documents_dir,
            "files": files,
            "count": len(files)
        }


def make_handler(service: AgentService):
    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {}

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/health":
                self._send_json(200, {"status": "ok"})
                return
            if path == "/config":
                self._send_json(200, service.get_config())
                return
            if path == "/history":
                self._send_json(200, {"items": service.get_history()})
                return
            if path == "/events":
                self._send_json(200, {"items": service.get_events()})
                return
            if path == "/documents":
                self._send_json(200, service.list_documents())
                return
            if path == "/scheduler":
                self._send_json(200, service.get_scheduler_status())
                return
            self._send_json(404, {"error": "not_found"})

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/chat":
                data = self._read_json()
                message = data.get("message", "")
                response = service.chat(message)
                self._send_json(200, {"response": response})
                return
            if path == "/config":
                data = self._read_json()
                config = service.update_config(data)
                self._send_json(200, config)
                return
            if path == "/history/clear":
                service.clear_history()
                self._send_json(200, {"ok": True})
                return
            self._send_json(404, {"error": "not_found"})

        def log_message(self, format, *args):
            return

    return Handler


def run_server(host: str, port: int):
    service = AgentService()
    server = ThreadingHTTPServer((host, port), make_handler(service))
    print(f"[server] listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="BossAgent local HTTP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()

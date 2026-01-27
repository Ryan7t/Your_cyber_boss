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
import uuid
import traceback
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
        self._events_lock = threading.Lock()
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
            self._push_event({
                "type": "auto_followup",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "message": response
            })

    def _push_event(self, event: dict):
        with self._events_lock:
            self._events.append(event)

    def get_history(self):
        with self._lock:
            if self._agent.memory.is_empty():
                self._agent.handle_startup()
            items = self._agent.memory.get_all()
            return [
                {"record_index": index, **record}
                for index, record in enumerate(items)
            ]

    def get_history_record(self, record_index: int) -> dict:
        with self._lock:
            items = self._agent.memory.get_all()
            if record_index < 0 or record_index >= len(items):
                return {}
            return items[record_index]

    def chat(self, message: str, message_id: str = None) -> dict:
        message_id = message_id or str(uuid.uuid4())

        def event_callback(event: dict):
            if "message_id" not in event:
                event["message_id"] = message_id
            self._push_event(event)

        with self._lock:
            before = len(self._agent.memory.get_all())
            if message is None:
                message = ""
            if not message.strip():
                response = self._agent.handle_proactive_followup(event_callback=event_callback, message_id=message_id)
            else:
                response = self._agent.handle_user_input(message, event_callback=event_callback, message_id=message_id)
            after = len(self._agent.memory.get_all())
            saved = after > before
        record_index = after - 1 if saved else None
        return {"message_id": message_id, "response": response, "saved": saved, "record_index": record_index}

    def chat_stream(self, message: str, send_event, message_id: str = None) -> str:
        message_id = message_id or str(uuid.uuid4())

        def event_callback(event: dict):
            if "message_id" not in event:
                event["message_id"] = message_id
            send_event(event)

        with self._lock:
            before = len(self._agent.memory.get_all())
            if message is None:
                message = ""
            if not message.strip():
                response = self._agent.handle_proactive_followup(event_callback=event_callback, message_id=message_id)
            else:
                response = self._agent.handle_user_input(message, event_callback=event_callback, message_id=message_id)
            after = len(self._agent.memory.get_all())
            saved = after > before
        record_index = after - 1 if saved else None
        send_event({
            "type": "done",
            "message_id": message_id,
            "response": response,
            "saved": saved,
            "record_index": record_index
        })
        return message_id

    def retry_record_stream(self, record_index: int, send_event, message_id: str = None):
        message_id = message_id or str(uuid.uuid4())

        def event_callback(event: dict):
            if "message_id" not in event:
                event["message_id"] = message_id
            event["record_index"] = record_index
            send_event(event)

        with self._lock:
            history = self._agent.memory.get_all()
            if record_index < 0 or record_index >= len(history):
                send_event({"type": "error", "content": "invalid_record", "message_id": message_id, "record_index": record_index})
                return
            request_input = history[record_index].get("request_input", "")
            # 临时只使用重试前的历史
            original_history = self._agent.memory.history
            self._agent.memory.history = history[:record_index]
            try:
                response, conversation_messages, should_save = self._agent.generate_response(
                    request_input,
                    event_callback=event_callback,
                    message_id=message_id
                )
            finally:
                self._agent.memory.history = original_history
            if should_save:
                self._agent.memory.replace_record(record_index, conversation_messages, request_input=request_input)

        send_event({
            "type": "done",
            "message_id": message_id,
            "response": response,
            "saved": should_save,
            "record_index": record_index
        })

    def update_history_message(self, record_index: int, message_index: int, role: str, content: str) -> dict:
        with self._lock:
            updated = self._agent.memory.update_message(
                record_index=record_index,
                message_index=message_index,
                role=role,
                content=content
            )
            return {"ok": bool(updated)}

    def clear_history(self):
        with self._lock:
            self._agent.memory.clear()
            self._agent.scheduler.clear_deadline()
            with self._events_lock:
                self._events.clear()

    def get_events(self):
        events = []
        with self._events_lock:
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

    def _read_prompt(self, path: str) -> str:
        if not path or not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""

    def get_prompts(self) -> dict:
        return {
            "system_prompt": self._read_prompt(settings.system_prompt_file),
            "context_intro": self._read_prompt(settings.context_intro_file)
        }

    def update_prompts(self, updates: dict) -> dict:
        os.makedirs(settings.prompt_overrides_dir, exist_ok=True)
        mapping = {
            "system_prompt": ("system_prompt.txt", "system_prompt_file"),
            "context_intro": ("context_intro.txt", "context_intro_file")
        }
        for key, (filename, attr) in mapping.items():
            if key not in updates:
                continue
            value = updates.get(key, "")
            override_path = os.path.join(settings.prompt_overrides_dir, filename)
            try:
                with open(override_path, "w", encoding="utf-8") as f:
                    f.write(value)
                setattr(settings, attr, override_path)
            except Exception:
                pass

        with self._lock:
            self._start_agent()
        return self.get_prompts()


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
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/health":
                self._send_json(200, {"status": "ok"})
                return
            if path == "/config":
                self._send_json(200, service.get_config())
                return
            if path == "/history":
                self._send_json(200, {"items": service.get_history()})
                return
            if path == "/history/record":
                params = dict(part.split("=", 1) for part in parsed.query.split("&") if "=" in part)
                if "index" not in params:
                    self._send_json(400, {"error": "invalid_request"})
                    return
                try:
                    index = int(params["index"])
                except ValueError:
                    self._send_json(400, {"error": "invalid_request"})
                    return
                record = service.get_history_record(index)
                if not record:
                    self._send_json(404, {"error": "not_found"})
                    return
                self._send_json(200, record)
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
            if path == "/prompts":
                self._send_json(200, service.get_prompts())
                return
            self._send_json(404, {"error": "not_found"})

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/chat":
                data = self._read_json()
                message = data.get("message", "")
                message_id = data.get("message_id")
                payload = service.chat(message, message_id=message_id)
                self._send_json(200, payload)
                return
            if path == "/chat/stream":
                data = self._read_json()
                message = data.get("message", "")
                message_id = data.get("message_id")
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

                def send_event(event: dict):
                    try:
                        payload = json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n"
                        self.wfile.write(payload)
                        self.wfile.flush()
                    except BrokenPipeError:
                        return
                    except Exception:
                        return

                try:
                    service.chat_stream(message, send_event=send_event, message_id=message_id)
                except Exception:
                    send_event({"type": "error", "content": traceback.format_exc()})
                return
            if path == "/history/retry/stream":
                data = self._read_json()
                record_index = data.get("record_index")
                message_id = data.get("message_id")
                if record_index is None:
                    self._send_json(400, {"error": "invalid_request"})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

                def send_event(event: dict):
                    try:
                        payload = json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n"
                        self.wfile.write(payload)
                        self.wfile.flush()
                    except BrokenPipeError:
                        return
                    except Exception:
                        return

                try:
                    service.retry_record_stream(int(record_index), send_event=send_event, message_id=message_id)
                except Exception:
                    send_event({"type": "error", "content": traceback.format_exc()})
                return
            if path == "/config":
                data = self._read_json()
                config = service.update_config(data)
                self._send_json(200, config)
                return
            if path == "/prompts":
                data = self._read_json()
                prompts = service.update_prompts(data)
                self._send_json(200, prompts)
                return
            if path == "/history/clear":
                service.clear_history()
                self._send_json(200, {"ok": True})
                return
            if path == "/history/update":
                data = self._read_json()
                record_index = data.get("record_index")
                message_index = data.get("message_index")
                role = data.get("role")
                content = data.get("content", "")
                if record_index is None or role is None:
                    self._send_json(400, {"error": "invalid_request"})
                    return
                result = service.update_history_message(
                    record_index=int(record_index),
                    message_index=None if message_index is None else int(message_index),
                    role=str(role),
                    content=str(content)
                )
                self._send_json(200, result)
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

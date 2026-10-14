"""Read-only demo server. Bound to loopback; no third-party assets or telemetry."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

from .io import ROOT, decode_json
from .bundle import read_bundle
from .rag import RagAssistant


def make_handler(report, output_path, export_bytes=None, assistant=None):
    # Freeze the CSV with the loaded report so a later CLI run cannot mix versions.
    export_bytes = output_path.read_bytes() if export_bytes is None else export_bytes
    client_report = {k: report[k] for k in ("summary", "rows", "notes", "token_cost_log")}
    assistant = assistant or RagAssistant(report)
    client_report["question_mode"] = {"model": assistant.writer.model, "timeout_seconds": assistant.writer.timeout,
                                      "contract": "Retrieved facts; optional local model selects the answer plan."}
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def send(self, payload, content_type="application/json", status=200):
            if not isinstance(payload, bytes):
                payload = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/results":
                self.send(client_report)
            elif path == "/api/export":
                self.send(export_bytes, "text/csv; charset=utf-8")
            elif path in ("/", "/app.js", "/styles.css"):
                name = "index.html" if path == "/" else path[1:]
                kind = {"index.html": "text/html", "app.js": "text/javascript", "styles.css": "text/css"}[name]
                try:
                    self.send((ROOT / "web" / name).read_bytes(), kind + "; charset=utf-8")
                except OSError:
                    self.send({"error": "Demo asset is temporarily unavailable."}, status=503)
            else:
                self.send({"error": "Not found"}, status=404)

        def do_POST(self):
            if self.path != "/api/question":
                self.send({"error": "Not found"}, status=404)
                return
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("Chunked requests are not supported.")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("Question request is too large or empty.")
                body = decode_json(self.rfile.read(length), "Question request")
                if not isinstance(body, dict):
                    raise ValueError("Question request must be a JSON object.")
                question = body["question"]
                if not isinstance(question, str) or not question.strip() or len(question) > 1000:
                    raise ValueError("Enter a question of at most 1000 characters.")
                self.send(assistant.answer(question))
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self.send({"error": str(exc)}, status=400)
            except TimeoutError:
                self.send({"error": "Question request timed out; send it again."}, status=408)
            except OSError:
                self.send({"error": "Question request could not be read."}, status=400)

        def log_message(self, format, *args):
            pass

    return Handler


def load_report(output_dir):
    return read_bundle(output_dir)[0]


def serve(output_dir, port, model=None, base_url="http://127.0.0.1:11434", timeout=60):
    if not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535.")
    report, snapshot, _ = read_bundle(output_dir)
    assistant = RagAssistant(report, model, base_url, timeout)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(report, output_dir / "output.csv", snapshot["output.csv"], assistant))
    print(f"Freight Watch: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

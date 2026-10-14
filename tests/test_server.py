import csv
import io
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

from freight_watch.engine import analyze
from freight_watch.io import DATA_DIR, ROOT, write_output
from freight_watch.server import make_handler
from tests.test_engine import temporary_directory


class DemoServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = temporary_directory()
        cls.report = analyze(DATA_DIR / "shipment_records.csv", DATA_DIR / "context_notes.csv")
        cls.output_path = Path(cls.temp.name) / "output.csv"
        write_output(cls.output_path, cls.report["csv_rows"])
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.report, cls.output_path))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def test_html_assets_and_results_are_served(self):
        for path in ["/", "/styles.css", "/app.js"]:
            with urlopen(self.url + path) as response:
                self.assertEqual(response.status, 200)
                self.assertGreater(len(response.read()), 100)
        with urlopen(self.url + "/api/results") as response:
            self.assertEqual(json.load(response)["summary"]["route_weeks"], 728)

    def test_csv_download_is_exact_and_roundtrips(self):
        with urlopen(self.url + "/api/export") as response:
            raw = response.read()
        self.assertEqual(raw, self.output_path.read_bytes())
        self.assertEqual(len(list(csv.DictReader(io.StringIO(raw.decode())))), 728)

    def test_grounded_question_endpoint(self):
        request = Request(self.url + "/api/question", data=json.dumps({"question": "Why Ahmedabad-Mumbai on 2025-01-20?"}).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            answer = json.load(response)
        self.assertEqual(answer["findings"][0]["matched_note_id"], "N002")

    def test_invalid_question_and_path_traversal_are_rejected(self):
        request = Request(self.url + "/api/question", data=b'{"question": []}', headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/../config/note_rules.json")
        self.assertEqual(error.exception.code, 404)

    def test_malformed_json_shapes_utf8_and_large_body_are_rejected(self):
        for payload in [b"null", b"[]", b"not JSON", b"\xff", b'{"question":"' + b"x" * 4100 + b'"}',
                        b"[" * 1500 + b"0" + b"]" * 1500, b'{"question":NaN}']:
            request = Request(self.url + "/api/question", data=payload, headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 400)

    def test_missing_asset_has_json_error_and_security_headers(self):
        with patch("pathlib.Path.read_bytes", side_effect=FileNotFoundError("private filename")):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.url + "/styles.css")
            self.assertEqual(error.exception.code, 503)
            self.assertIn("script-src 'self'", error.exception.headers["Content-Security-Policy"])
            self.assertEqual(error.exception.headers["Referrer-Policy"], "no-referrer")
            self.assertNotIn("private filename", error.exception.read().decode())

    def test_export_is_frozen_with_the_loaded_report(self):
        original = self.output_path.read_bytes()
        try:
            self.output_path.write_text("different run", encoding="utf-8")
            with urlopen(self.url + "/api/export") as response:
                self.assertEqual(response.read(), original)
        finally:
            self.output_path.write_bytes(original)

    def test_rag_note_response_and_mode_are_exposed(self):
        with urlopen(self.url + "/api/results") as response:
            self.assertIsNone(json.load(response)["question_mode"]["model"])
        request = Request(self.url + "/api/question", data=b'{"question":"What does note N010 say?"}', headers={"Content-Type": "application/json"})
        with urlopen(request) as response: answer = json.load(response)
        self.assertEqual(answer["rag"]["mode"], "retrieval_only")
        self.assertEqual(answer["rag"]["retrieved"][0]["source_id"], "N010")
        self.assertEqual(answer["findings"], [])
        self.assertIn("cannot justify a cost increase", answer["answer"])


if __name__ == "__main__":
    unittest.main()

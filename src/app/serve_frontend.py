#!/usr/bin/env python3
"""在本地提供静态 FOMC 报告前端服务。"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import traceback
from pathlib import Path
from urllib.parse import unquote

import build_frontend_data
import generate_logic_chain_report
import online_inference


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "src" / "frontend" / "fomc_report_app"
FRONTEND_URL_PATH = "/src/frontend/fomc_report_app/"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):
        requested_path = unquote(self.path.split("?", 1)[0])

        if requested_path in ("", "/"):
            self.send_response(302)
            self.send_header("Location", FRONTEND_URL_PATH)
            self.end_headers()
            return

        return super().do_GET()

    def do_POST(self):
        requested_path = unquote(self.path.split("?", 1)[0])

        if requested_path == "/api/generate-logic-chain":
            return self.handle_generate_logic_chain()

        return self.write_json({"error": "Not found"}, status=404)

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))

        if length <= 0:
            return {}

        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def write_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_generate_logic_chain(self):
        try:
            request = self.read_json_body()
            api_key = os.environ.get("SJTU_API_KEY") or os.environ.get("OPENAI_API_KEY")

            if not api_key:
                return self.write_json(
                    {
                        "error": "API key not found. Set SJTU_API_KEY before starting the server.",
                    },
                    status=400,
                )

            user_question = str(request.get("user_question", "")).strip()
            model = str(
                request.get("model")
                or os.environ.get("SJTU_MODEL")
                or generate_logic_chain_report.DEFAULT_MODEL
            )
            base_url = str(
                request.get("base_url")
                or os.environ.get("SJTU_API_BASE_URL")
                or generate_logic_chain_report.DEFAULT_BASE_URL
            )
            frontend_payload = online_inference.build_frontend_payload(
                user_question=user_question,
                current_text=str(request.get("current_statement_text", "")).strip(),
                previous_text=str(request.get("previous_statement_text", "")).strip(),
                market_state_override=request.get("market_state") or {},
                base_event_id=str(request.get("base_event_id") or "") or None,
                top_k_cases=int(request.get("top_k_cases", 3)),
                model_family=str(request.get("model_family") or "hgbdt"),
            )
            payload = online_inference.build_llm_payload(frontend_payload)
            messages = generate_logic_chain_report.build_messages(payload)
            prompt_chars = sum(len(message["content"]) for message in messages)

            generate_logic_chain_report.PROMPT_OUT_FILE.write_text(
                json.dumps(
                    {
                        "base_url": base_url,
                        "model": model,
                        "prompt_chars": prompt_chars,
                        "messages": messages,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            content = generate_logic_chain_report.call_llm(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                timeout=int(request.get("timeout", 600)),
                retries=int(request.get("retries", 1)),
                max_tokens=int(request.get("max_tokens", 5000)),
            )

            generate_logic_chain_report.OUT_FILE.write_text(
                content.strip() + "\n",
                encoding="utf-8",
            )
            frontend_payload["llm_logic_chain_report"] = {
                "status": "generated",
                "content": content.strip() + "\n",
                "source_file": str(generate_logic_chain_report.OUT_FILE.relative_to(PROJECT_ROOT)),
                "message": "由前端请求触发 LLM 生成。",
            }

            return self.write_json(
                {
                    "status": "ok",
                    "model": model,
                    "prompt_chars": prompt_chars,
                    "report": content,
                    "frontend_data": frontend_payload,
                    "report_file": str(
                        generate_logic_chain_report.OUT_FILE.relative_to(PROJECT_ROOT)
                    ),
                }
            )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self.write_json(
                {
                    "error": str(exc),
                    "type": exc.__class__.__name__,
                },
                status=500,
            )

    def log_message(self, format, *args):  # noqa: A002
        return


def parse_args():
    parser = argparse.ArgumentParser(description="Serve the FOMC report frontend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not (FRONTEND_DIR / "index.html").exists():
        raise SystemExit(f"index.html not found: {FRONTEND_DIR}")

    handler = lambda *handler_args, **handler_kwargs: QuietHandler(  # noqa: E731
        *handler_args,
        directory=str(PROJECT_ROOT),
        **handler_kwargs,
    )

    socketserver.ThreadingTCPServer.allow_reuse_address = True

    with socketserver.ThreadingTCPServer((args.host, args.port), handler) as httpd:
        print(f"FOMC report frontend: http://{args.host}:{args.port}{FRONTEND_URL_PATH}")
        print(f"LLM endpoint: http://{args.host}:{args.port}/api/generate-logic-chain")
        print(f"Project files are served from: {PROJECT_ROOT}")
        print("Press Ctrl+C to stop.")
        httpd.serve_forever()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

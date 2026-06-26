from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def send_json(handler: BaseHTTPRequestHandler, data: object, status: int = 200, headers: dict[str, str] | None = None) -> None:
    body = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Connection", "close")
    for key, value in (headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


class MockApi(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    events: list[tuple[str, str, object]] = []

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        self.events.append(("GET", self.path, None))
        if self.path == "/v1/models":
            send_json(self, {"object": "list", "data": [{"id": "deepseek-v4-flash"}, {"id": "deepseek-v4-pro"}]})
            return
        if self.path == "/zotero/keys/mock-zotero-key":
            send_json(self, {"userID": 12345, "access": {"user": {"library": True, "notes": True}}})
            return
        if self.path.startswith("/zotero/users/12345/items/top"):
            send_json(self, [], headers={"Total-Results": "1"})
            return
        if self.path.startswith("/zotero/users/12345/items/ITEM123/children"):
            send_json(self, [])
            return
        if self.path.startswith("/zotero/items/new"):
            send_json(self, {"itemType": "note", "note": "", "tags": []})
            return
        if self.path.startswith("/localapi/users/0/items/ITEM123"):
            send_json(
                self,
                {
                    "key": "ITEM123",
                    "data": {
                        "key": "ITEM123",
                        "title": "Local Test Paper",
                        "creators": [{"firstName": "Ada", "lastName": "Lovelace", "creatorType": "author"}],
                        "date": "2026",
                        "DOI": "10.0000/local-test",
                        "abstractNote": "A local E2E test abstract.",
                    },
                    "links": {"alternate": {"href": "zotero://select/items/ITEM123"}},
                },
            )
            return
        send_json(self, {"error": f"not found: {self.path}"}, status=404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body: object = json.loads(raw.decode("utf-8")) if raw else None
        except Exception:
            body = raw.decode("utf-8", errors="replace")
        self.events.append(("POST", self.path, body))
        if self.path == "/v1/chat/completions":
            send_json(self, {"choices": [{"message": {"content": "Mock summary"}}]})
            return
        if self.path.startswith("/zotero/users/12345/items"):
            send_json(self, {"success": {"0": "NEWNOTE1"}, "failed": {}, "unchanged": {}})
            return
        send_json(self, {"error": f"not found: {self.path}"}, status=404)


def get_json(base_url: str, path: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(base_url + path, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base_url: str, path: str, data: dict | None = None, timeout: int = 20) -> dict:
    req = urllib.request.Request(
        base_url + path,
        data=json.dumps(data or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_api(base_url: str, proc: subprocess.Popen[str], timeout: int = 60) -> dict:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate(timeout=5)
            raise RuntimeError(f"app exited early rc={proc.returncode}\nSTDOUT:\n{out}\nSTDERR:\n{err}")
        try:
            return get_json(base_url, "/api/setup/status", timeout=2)
        except Exception as exc:
            last = exc
            time.sleep(0.5)
    raise TimeoutError(f"app did not become ready at {base_url}: {last}")


def task_exists(name: str) -> bool:
    result = subprocess.run(["schtasks.exe", "/Query", "/TN", name], capture_output=True, text=True, timeout=15)
    return result.returncode == 0


def delete_test_tasks(prefix: str) -> None:
    for idx in range(1, 25):
        for kind in ("Push", "Prepare"):
            subprocess.run(
                ["schtasks.exe", "/Delete", "/TN", f"{prefix}\\{kind}{idx}", "/F"],
                capture_output=True,
                text=True,
                timeout=15,
            )


def main() -> int:
    install_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Zotero Daily News"
    gui_exe = install_dir / "Zotero Daily News.exe"
    cli_exe = install_dir / "Zotero Daily News CLI.exe"
    if not gui_exe.exists() or not cli_exe.exists():
        raise SystemExit(f"Installed app not found under {install_dir}")

    root = Path(tempfile.mkdtemp(prefix="zdn-e2e-"))
    config_dir = root / "config"
    runtime_dir = root / "runtime"
    config_dir.mkdir(parents=True)
    runtime_dir.mkdir(parents=True)

    mock_port = free_port()
    app_port = free_port()
    (config_dir / "config.yaml").write_text(f"ui:\n  port: {app_port}\n", encoding="utf-8")
    task_prefix = "ZoteroDailyNewsCodexTest" + next(tempfile._get_candidate_names())

    server = ThreadingHTTPServer(("127.0.0.1", mock_port), MockApi)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    base_url = f"http://127.0.0.1:{app_port}"
    mock_base = f"http://127.0.0.1:{mock_port}"
    env = {
        **os.environ,
        "ZOTERO_DAILY_NEWS_CONFIG_DIR": str(config_dir),
        "ZOTERO_DAILY_NEWS_RUNTIME_DIR": str(runtime_dir),
        "ZOTERO_DAILY_NEWS_TASK_PREFIX": task_prefix,
        "ZOTERO_API_BASE_URL": mock_base + "/zotero",
        "ZOTERO_LOCAL_API_BASE_URL": mock_base + "/localapi",
        "NO_PROXY": "127.0.0.1,localhost,::1",
    }

    env["DEEPSEEK_API_KEY"] = ""
    env["ZOTERO_API_KEY"] = ""
    env["ZOTERO_LIBRARY_ID"] = ""

    proc = subprocess.Popen(
        [str(cli_exe), "--serve-only"],
        cwd=str(install_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        initial = wait_api(base_url, proc)
        if not initial.get("needs_setup"):
            raise AssertionError(f"expected first-run setup, got {initial}")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("#setup_modal.open", timeout=20000)
            page.fill("#setup_deepseek_api_key", "sk-local-test")
            page.fill("#setup_deepseek_base_url", mock_base + "/v1")
            page.fill("#setup_deepseek_briefing_model", "deepseek-v4-flash")
            page.fill("#setup_deepseek_deep_read_model", "deepseek-v4-pro")
            page.fill("#setup_zotero_api_key", "mock-zotero-key")
            page.fill("#setup_zotero_library_id", "")
            page.click("#setup_verify_btn")
            page.wait_for_function(
                "!document.querySelector('#setup_modal').classList.contains('open')",
                timeout=60000,
            )
            browser.close()

        status = get_json(base_url, "/api/setup/status")
        if status.get("needs_setup"):
            raise AssertionError(f"setup still needed: {status}")
        if status.get("scheduler", {}).get("platform") != "windows":
            raise AssertionError(f"expected Windows scheduler status: {status}")
        task_name = f"{task_prefix}\\Push1"
        if not task_exists(task_name):
            raise AssertionError(f"test scheduled task was not created: {task_name}")

        summaries = runtime_dir / "summaries"
        hubs = runtime_dir / "hubs"
        summaries.mkdir(parents=True, exist_ok=True)
        hubs.mkdir(parents=True, exist_ok=True)
        note_id = "20260627_ITEM123_local-test"
        md_path = summaries / f"{note_id}.md"
        hub_path = hubs / f"{note_id}.html"
        md_path.write_text(
            "# Local Test Paper\n\n"
            "> **Briefing:** Mock local briefing\n\n"
            "## Summary\n\n"
            "Safe markdown body.\n\n"
            "<script>alert(1)</script>\n"
            "[bad](javascript:alert(1))\n",
            encoding="utf-8",
        )
        hub_path.write_text(
            '<!doctype html><meta charset="utf-8"><title>Local Test</title><h1>Local Test Paper</h1><p>summary</p>',
            encoding="utf-8",
        )
        queue = {
            "created_at": "2026-06-27T05:10:00",
            "prepared_at": "2026-06-27T05:10:00",
            "queue_size": 1,
            "push_count": 1,
            "items": [
                {
                    "item_key": "ITEM123",
                    "title": "Local Test Paper",
                    "authors": "Ada Lovelace",
                    "status": "ready",
                    "deep_read": "skipped",
                    "has_pdf": False,
                    "note_id": note_id,
                    "hub_path": str(hub_path),
                    "briefing": "Mock local briefing",
                }
            ],
        }
        (runtime_dir / "queue.json").write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector('button[onclick="runNow(false)"]', timeout=20000)
            page.locator('button[onclick="runNow(false)"]').first.click()
            page.wait_for_function(
                "document.querySelector('#stdout_log') && document.querySelector('#stdout_log').textContent.includes('@@NOTIFY@@')",
                timeout=60000,
            )
            browser.close()

        q_after = json.loads((runtime_dir / "queue.json").read_text(encoding="utf-8"))
        item_status = q_after["items"][0].get("status")
        if item_status != "pushed":
            raise AssertionError(f"queue item not pushed after UI run: {q_after}")

        push_result = post_json(base_url, f"/api/notes/{note_id}/push-zotero", {"mode": "create"})
        if not push_result.get("ok") or push_result.get("note_key") != "NEWNOTE1":
            raise AssertionError(f"Zotero push failed: {push_result}")
        created_posts = [event for event in MockApi.events if event[0] == "POST" and event[1].startswith("/zotero/users/12345/items")]
        if not created_posts:
            raise AssertionError("mock Zotero did not receive note create request")
        note_payload = json.dumps(created_posts[-1][2], ensure_ascii=False)
        if "<script" in note_payload or "javascript:" in note_payload or "onclick" in note_payload:
            raise AssertionError(f"HTML sanitizer failed: {created_posts[-1][2]}")

        cli_queue = json.loads((runtime_dir / "queue.json").read_text(encoding="utf-8"))
        cli_queue["items"][0]["status"] = "ready"
        (runtime_dir / "queue.json").write_text(json.dumps(cli_queue, ensure_ascii=False, indent=2), encoding="utf-8")
        cli_result = subprocess.run(
            [str(cli_exe), "--push-queue", "--no-notify"],
            cwd=str(install_dir),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )
        if cli_result.returncode != 0 or "@@NOTIFY@@" not in cli_result.stdout:
            raise AssertionError(
                f"CLI smoke failed rc={cli_result.returncode}\nstdout={cli_result.stdout}\nstderr={cli_result.stderr}"
            )

        print(
            json.dumps(
                {
                    "ok": True,
                    "root": str(root),
                    "app_url": base_url,
                    "mock_url": mock_base,
                    "task_prefix": task_prefix,
                    "created_task": task_name,
                    "setup_needs_setup_after": status.get("needs_setup"),
                    "queue_status_after_ui_push": item_status,
                    "zotero_created_note": push_result.get("note_key"),
                    "cli_smoke_returncode": cli_result.returncode,
                    "mock_zotero_create_requests": len(created_posts),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        delete_test_tasks(task_prefix)
        server.shutdown()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())

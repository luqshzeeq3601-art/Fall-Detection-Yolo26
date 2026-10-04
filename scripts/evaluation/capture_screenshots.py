"""Capture portfolio screenshot evidence from the live Streamlit evaluation dashboard via Chrome DevTools Protocol.

Supports configurable ports via CLI:
    python scripts/evaluation/capture_screenshots.py --port 8506 --cdp-port 9223
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

import requests
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOG = logging.getLogger("capture_screenshots")

ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT / "docs" / "assets" / "results"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class DevToolsBrowserClient:
    """Lightweight Chrome DevTools Protocol client."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self._req_id = 0

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url, max_size=50 * 1024 * 1024)

    async def close(self):
        if self.ws:
            await self.ws.close()

    async def send(self, method: str, params: dict | None = None) -> dict:
        self._req_id += 1
        req_id = self._req_id
        payload = {"id": req_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(payload))
        while True:
            raw = await self.ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP Error in {method}: {msg['error']}")
                return msg.get("result", {})

    async def evaluate_js(self, expression: str) -> any:
        res = await self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        return res.get("result", {}).get("value")

    async def capture_screenshot(self, target_path: Path):
        res = await self.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        data = base64.b64decode(res["data"])
        target_path.write_bytes(data)
        LOG.info("Saved screenshot: %s (%d bytes)", target_path.name, len(data))


async def run_evidence_capture(port: int, cdp_port: int):
    base_url = f"http://127.0.0.1:{port}"
    user_data = Path(r"C:\Users\ZeeqRyz\AppData\Local\Temp") / f"chrome_portfolio_qa_{cdp_port}"
    if user_data.exists():
        shutil.rmtree(user_data, ignore_errors=True)

    LOG.info("Starting headless Chrome with DevTools on port %d...", cdp_port)
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={user_data}",
        "--window-size=1920,1080",
        "--hide-scrollbars",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ])

    time.sleep(2.5)
    client = None
    try:
        # Find page target
        targets_resp = requests.get(f"http://127.0.0.1:{cdp_port}/json")
        targets = targets_resp.json()
        page_target = next(t for t in targets if t.get("type") == "page")
        ws_url = page_target["webSocketDebuggerUrl"]

        client = DevToolsBrowserClient(ws_url)
        await client.connect()
        await client.send("Page.enable")
        await client.send("Runtime.enable")
        await client.send("DOM.enable")
        await client.send("Emulation.setDeviceMetricsOverride", {
            "width": 1920,
            "height": 1080,
            "deviceScaleFactor": 1,
            "mobile": False,
        })
        await client.send("Emulation.setEmulatedMedia", {
            "media": "screen",
            "features": [{"name": "prefers-color-scheme", "value": "light"}],
        })

        async def load_and_capture(url: str, filename: str, scroll_y: int = 0, scroll_selector: str | None = None, min_sleep: float = 2.5):
            LOG.info("Navigating to %s for %s...", url, filename)
            await client.send("Page.navigate", {"url": url})
            # Wait for metrics or images
            for _ in range(30):
                ready = await client.evaluate_js(
                    "document.querySelectorAll('div[data-testid=\"stMetric\"]').length >= 5"
                )
                if ready:
                    break
                await asyncio.sleep(0.5)

            await asyncio.sleep(min_sleep)

            if scroll_selector:
                await client.evaluate_js(
                    f"""
                    (() => {{
                        const el = document.querySelector('{scroll_selector}');
                        if (el) el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                    }})()
                    """
                )
            else:
                await client.evaluate_js(f"window.scrollTo(0, {scroll_y})")

            await asyncio.sleep(1.0)
            await client.capture_screenshot(ASSETS_DIR / filename)

        # 1. overview.png
        LOG.info("Capturing 1/9: overview.png...")
        await load_and_capture(f"{base_url}/?view=overview", "overview.png", scroll_y=0)

        # 2. confusion-matrix.png
        LOG.info("Capturing 2/9: confusion-matrix.png...")
        await load_and_capture(
            f"{base_url}/?view=overview",
            "confusion-matrix.png",
            scroll_y=280,
            min_sleep=1.5,
        )

        # 3. fall-forward-tp.png
        LOG.info("Capturing 3/9: fall-forward-tp.png (Forward Fall TP)...")
        await load_and_capture(
            f"{base_url}/?view=explorer&seq=upfall_s12_a01_t03_c1",
            "fall-forward-tp.png",
            scroll_y=430,
            min_sleep=2.5,
        )

        # 4. fall-backward-tp.png
        LOG.info("Capturing 4/9: fall-backward-tp.png (Backward Fall TP)...")
        await load_and_capture(
            f"{base_url}/?view=explorer&seq=upfall_s12_a03_t03_c1",
            "fall-backward-tp.png",
            scroll_y=430,
            min_sleep=2.5,
        )

        # 5. fall-side-tp.png
        LOG.info("Capturing 5/9: fall-side-tp.png (Sideways Fall TP)...")
        await load_and_capture(
            f"{base_url}/?view=explorer&seq=upfall_s12_a04_t03_c1",
            "fall-side-tp.png",
            scroll_y=430,
            min_sleep=2.5,
        )

        # 6. fall-false-negative.png
        LOG.info("Capturing 6/9: fall-false-negative.png (Hard Case / Missed Fall FN)...")
        await load_and_capture(
            f"{base_url}/?view=explorer&seq=upfall_s12_a01_t03_c2",
            "fall-false-negative.png",
            scroll_y=430,
            min_sleep=2.5,
        )

        # 7. adl-walking-tn.png
        LOG.info("Capturing 7/9: adl-walking-tn.png (Walking ADL TN)...")
        await load_and_capture(
            f"{base_url}/?view=explorer&seq=upfall_s12_a06_t03_c1",
            "adl-walking-tn.png",
            scroll_y=430,
            min_sleep=2.5,
        )

        # 8. adl-false-positive.png
        LOG.info("Capturing 8/9: adl-false-positive.png (Hard Case / Bed Dive FP)...")
        await load_and_capture(
            f"{base_url}/?view=explorer&seq=upfall_s13_a11_t03_c1",
            "adl-false-positive.png",
            scroll_y=430,
            min_sleep=2.5,
        )

        # 9. performance-benchmark.png
        LOG.info("Capturing 9/9: performance-benchmark.png (RTX 3070 Benchmarks)...")
        await load_and_capture(
            f"{base_url}/?view=benchmarks",
            "performance-benchmark.png",
            scroll_y=200,
            min_sleep=2.0,
        )

        LOG.info("All 9 screenshots captured successfully!")

    finally:
        if client:
            await client.close()
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture evidence screenshots from Streamlit evaluation app")
    parser.add_argument("--port", type=int, default=8506, help="Streamlit dashboard port (default: 8506)")
    parser.add_argument("--cdp-port", type=int, default=9223, help="Chrome DevTools port (default: 9223)")
    args = parser.parse_args()

    asyncio.run(run_evidence_capture(port=args.port, cdp_port=args.cdp_port))

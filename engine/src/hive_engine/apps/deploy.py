"""Real deploys: push a static site folder to Vercel and wait until the live URL serves it.

    r = await vercel_deploy(ws / "site", project="whisk-demo")
    r.url  -> "https://whisk-demo-ten.vercel.app" (the project's public production alias)

Uses the Vercel CLI through npx (logged in on this Mac). The folder is copied into a stable staging
directory named after the project, so `vercel deploy --yes` links to the same project every run
(its `.vercel/` link is kept between runs) and the production alias never changes.

Scope: the account has more than one team and the CLI refuses to guess in non-interactive mode.
VERCEL_SCOPE picks it (default: the personal team, "lukietees-projects").
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

log = logging.getLogger("hive.deploy")

DEFAULT_SCOPE = "lukietees-projects"
SKIP = {"FINISHED", ".vercel", ".DS_Store"}


@dataclass
class DeployResult:
    ok: bool
    url: str | None = None            # public production alias
    deployment_url: str | None = None  # this deployment (behind Vercel login on protected projects)
    seconds: float = 0.0
    error: str | None = None
    notes: list[str] = field(default_factory=list)


def _stage(site: Path, project: str) -> Path:
    """Copies the site into <tmp>/hive_vercel/<project>/, keeping its .vercel link."""
    stage = Path(tempfile.gettempdir()) / "hive_vercel" / project
    stage.mkdir(parents=True, exist_ok=True)
    for old in stage.iterdir():
        if old.name == ".vercel":
            continue
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    for item in site.iterdir():
        if item.name in SKIP:
            continue
        dest = stage / item.name
        shutil.copytree(item, dest) if item.is_dir() else shutil.copy2(item, dest)
    return stage


def _parse(stdout: str) -> dict:
    """The CLI prints one JSON object on stdout in non-interactive mode."""
    start = stdout.find("{")
    try:
        return json.loads(stdout[start:]) if start >= 0 else {}
    except json.JSONDecodeError:
        return {}


async def wait_live(url: str, expect: str | None = None, timeout: float = 30.0) -> bool:
    """Polls until the URL serves 200 (and contains `expect`, e.g. the new price, if given)."""
    end = time.monotonic() + timeout
    async with httpx.AsyncClient(follow_redirects=False, timeout=10,
                                 headers={"cache-control": "no-cache"}) as client:
        while time.monotonic() < end:
            try:
                r = await client.get(url, params={"t": str(time.time())})
                if r.status_code == 200 and (expect is None or expect in r.text):
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1.0)
    return False


async def vercel_deploy(site: Path, project: str = "whisk-demo", timeout: float = 90.0,
                        expect: str | None = None) -> DeployResult:
    """Deploys `site` to production. Never raises: failures come back as ok=False with an error."""
    t0 = time.monotonic()
    scope = os.environ.get("VERCEL_SCOPE", DEFAULT_SCOPE)
    try:
        stage = _stage(site, project)
        proc = await asyncio.create_subprocess_exec(
            "npx", "--yes", "vercel", "deploy", "--yes", "--prod", "--scope", scope,
            cwd=str(stage), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return DeployResult(False, seconds=round(time.monotonic() - t0, 1), error=f"timed out after {timeout:.0f}s")
        data = _parse(out.decode(errors="replace"))
        dep = data.get("deployment") or {}
        url = dep.get("productionUrl")
        if proc.returncode != 0 or data.get("status") != "ok" or not url:
            msg = data.get("message") or err.decode(errors="replace").strip().splitlines()[-1:] or ["deploy failed"]
            return DeployResult(False, seconds=round(time.monotonic() - t0, 1),
                                error=msg if isinstance(msg, str) else msg[0])
        res = DeployResult(True, url=url, deployment_url=dep.get("url"))
        left = max(5.0, timeout - (time.monotonic() - t0))
        if not await wait_live(url, expect, timeout=min(left, 30.0)):
            res.notes.append("alias not serving the new build yet")
        res.seconds = round(time.monotonic() - t0, 1)
        return res
    except Exception as exc:  # npx missing, disk errors…: the scenario falls back to the local URL
        log.warning("vercel deploy failed: %r", exc)
        return DeployResult(False, seconds=round(time.monotonic() - t0, 1), error=f"{type(exc).__name__}: {exc}")


__all__ = ["DeployResult", "vercel_deploy", "wait_live"]

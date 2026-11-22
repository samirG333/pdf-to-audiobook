"""Parallel, resumable speech synthesis with edge-tts."""
from __future__ import annotations

import asyncio
import hashlib
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import edge_tts

VOICES = {
    "vlasta": "cs-CZ-VlastaNeural",
    "antonin": "cs-CZ-AntoninNeural",
}
MIN_BYTES = 1024


def resolve_voice(name: str) -> str:
    return VOICES.get(name.lower(), name)


@dataclass
class Job:
    text: str
    path: Path

    @property
    def done(self) -> bool:
        return self.path.exists() and self.path.stat().st_size >= MIN_BYTES


def chunk_path(folder: Path, prefix: str, text: str, voice: str, rate: str) -> Path:
    digest = hashlib.sha1(f"{voice}|{rate}|{text}".encode()).hexdigest()[:10]
    return folder / f"{prefix}_{digest}.mp3"


async def _synthesize(job: Job, voice: str, rate: str, retries: int,
                      log: Callable[[str], None]) -> None:
    tmp = job.path.with_suffix(".part")
    delay = 2.0
    for attempt in range(1, retries + 1):
        try:
            communicate = edge_tts.Communicate(job.text, voice, rate=rate)
            await asyncio.wait_for(communicate.save(str(tmp)), timeout=180)
            if not tmp.exists() or tmp.stat().st_size < MIN_BYTES:
                raise RuntimeError("empty audio received")
            os.replace(tmp, job.path)
            return
        except Exception as exc:  # network errors, throttling, NoAudioReceived ...
            tmp.unlink(missing_ok=True)
            if attempt == retries:
                raise RuntimeError(f"{job.path.name}: failed after {retries} attempts: {exc}") from exc
            wait = min(delay, 90) + random.uniform(0, 1.5)
            log(f"[yellow]retry {attempt}/{retries - 1}[/] {job.path.name}: {type(exc).__name__}: {exc} – čekám {wait:.0f} s")
            await asyncio.sleep(wait)
            delay *= 2


async def run_jobs(jobs: list[Job], voice: str, rate: str, workers: int, retries: int,
                   on_done: Callable[[Job], None], log: Callable[[str], None]) -> list[str]:
    """Synthesize every unfinished job, `workers` at a time. Returns error messages."""
    sem = asyncio.Semaphore(workers)
    errors: list[str] = []

    async def one(job: Job):
        async with sem:
            try:
                await _synthesize(job, voice, rate, retries, log)
            except Exception as exc:
                errors.append(str(exc))
                log(f"[red]chyba[/] {exc}")
                return
        on_done(job)

    await asyncio.gather(*(one(j) for j in jobs))
    return errors

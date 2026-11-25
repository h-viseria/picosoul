"""Vosk microphone session: start audio / stop audio."""

from __future__ import annotations

import json
import queue
import re
import threading
from collections.abc import Callable
from typing import Any

_START_RE = re.compile(
    r"^\s*(?:start|enable|begin)\s+(?:audio|voice|listening|microphone|mic)\s*$",
    re.I,
)
_STOP_RE = re.compile(
    r"^\s*(?:stop|end|disable|quit)\s+(?:audio|voice|listening|microphone|mic)\s*$",
    re.I,
)


def is_start_audio_command(text: str) -> bool:
    return bool(_START_RE.match((text or "").strip()))


def is_stop_audio_command(text: str) -> bool:
    return bool(_STOP_RE.match((text or "").strip()))


class VoiceSession:
    """
    Background mic → Vosk STT.

    While running, completed phrases are passed to on_utterance(text).
    Type (or say) 'stop audio' to stop.
    """

    def __init__(
        self,
        *,
        model_path: str | None = None,
        model_url: str | None = None,
        sample_rate: int = 16000,
        device: int | None = None,
        blocksize: int = 8000,
    ) -> None:
        self.model_path = model_path
        self.model_url = model_url
        self.sample_rate = int(sample_rate)
        self.device = device
        self.blocksize = int(blocksize)

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False
        self._stopped_notified = False
        self._on_utterance: Callable[[str], None] | None = None
        self._on_stopped: Callable[[], None] | None = None
        self._on_error: Callable[[BaseException], None] | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._running

    def start(
        self,
        on_utterance: Callable[[str], None],
        *,
        on_stopped: Callable[[], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> None:
        with self._lock:
            if self._running:
                raise RuntimeError("Audio already running — type 'stop audio' first")
            leftover = self._thread
            self._on_utterance = on_utterance
            self._on_stopped = on_stopped
            self._on_error = on_error
            self._stop.clear()
            self._stopped_notified = False
            self._running = True
            self._thread = threading.Thread(
                target=self._run,
                name="osagent-voice",
                daemon=True,
            )
            new_thread = self._thread
        if leftover and leftover.is_alive() and leftover is not threading.current_thread():
            leftover.join(timeout=3.0)
        new_thread.start()

    def stop(self) -> None:
        with self._lock:
            was = self._running
            self._stop.set()
            self._running = False
            t = self._thread
            self._thread = None
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=3.0)
        if was:
            self._notify_stopped()

    def _notify_stopped(self) -> None:
        with self._lock:
            if self._stopped_notified:
                return
            self._stopped_notified = True
            stopped_cb = self._on_stopped
        if stopped_cb:
            try:
                stopped_cb()
            except Exception:
                pass

    def _emit(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        # Spoken stop/start — don't send to the agent
        if is_stop_audio_command(text):
            self._stop.set()
            self._running = False
            self._notify_stopped()
            return
        if is_start_audio_command(text):
            return
        cb = self._on_utterance
        if cb:
            cb(text)

    def _run(self) -> None:
        try:
            self._listen_loop()
        except Exception as exc:  # noqa: BLE001
            err_cb = self._on_error
            if err_cb:
                try:
                    err_cb(exc)
                except Exception:
                    print(f"[voice] error: {exc}")
            else:
                print(f"[voice] error: {exc}")
        finally:
            self._running = False

    def _listen_loop(self) -> None:
        try:
            import sounddevice as sd  # type: ignore
            from vosk import KaldiRecognizer, Model  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Voice deps missing. Install with: "
                'pip install vosk sounddevice  (or requirements-voice.txt)'
            ) from exc

        from osagent.voice.models import ensure_vosk_model

        model_dir = ensure_vosk_model(self.model_path, url=self.model_url)
        model = Model(str(model_dir))
        rec = KaldiRecognizer(model, self.sample_rate)
        rec.SetWords(False)

        audio_q: queue.Queue[bytes | None] = queue.Queue()

        def _callback(indata: Any, frames: int, _time: Any, status: Any) -> None:
            if status:
                pass
            audio_q.put(bytes(indata))

        kwargs: dict[str, Any] = {
            "samplerate": self.sample_rate,
            "blocksize": self.blocksize,
            "dtype": "int16",
            "channels": 1,
            "callback": _callback,
        }
        if self.device is not None:
            kwargs["device"] = self.device

        with sd.RawInputStream(**kwargs):
            print("[voice] listening… (type or say 'stop audio' to stop)")
            while not self._stop.is_set():
                try:
                    data = audio_q.get(timeout=0.25)
                except queue.Empty:
                    continue
                if data is None:
                    break
                if rec.AcceptWaveform(data):
                    try:
                        payload = json.loads(rec.Result())
                    except json.JSONDecodeError:
                        continue
                    self._emit(str(payload.get("text") or ""))
                # partial results ignored — wait for final phrase

            # flush trailing audio
            try:
                payload = json.loads(rec.FinalResult())
                # Don't re-handle stop after we already shut down from speech
                if not self._stop.is_set():
                    self._emit(str(payload.get("text") or ""))
            except Exception:
                pass

"""Optional speech-to-text (Vosk) — talk instead of type."""

from __future__ import annotations

from osagent.voice.session import VoiceSession, is_start_audio_command, is_stop_audio_command

__all__ = [
    "VoiceSession",
    "is_start_audio_command",
    "is_stop_audio_command",
]

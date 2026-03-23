"""
Layer 0: Audio device simulators.

MockMicrophone generates synthetic sine-wave audio frames (PCM bytes).
MockSpeaker is a null sink that accepts and discards audio data.

No external runtime dependencies (pure Python math; no pyaudio, sounddevice, etc.).
"""

import math
import struct
import time
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


from simulation.hal.device import MicrophoneInterface, SpeakerInterface


class MockMicrophone(MicrophoneInterface):
    """
    Synthetic audio source that generates sine-wave PCM (Pulse-Code Modulation)
    frames.

    Implements :class:`~simulation.hal.device.MicrophoneInterface`.

    Each ``read()`` call returns a ``bytes`` object containing 16-bit signed PCM
    samples at the configured sample rate and frequency.

    Example::

        mic = MockMicrophone(sample_rate=16000, channels=1, chunk_size=1024)
        mic.start()
        frame = mic.read()   # bytes of length chunk_size * 2 (16-bit samples)
        mic.stop()
    """

    def __init__(
        self,
        sample_rate: int = 16_000,
        channels: int = 1,
        chunk_size: int = 1024,
        frequency_hz: float = 440.0,   # A4 — audible sine wave
        amplitude: float = 0.3,         # 0.0–1.0; 0.3 avoids clipping
    ):
        self.sample_rate  = sample_rate
        self.channels     = channels
        self.chunk_size   = chunk_size
        self.frequency_hz = frequency_hz
        self.amplitude    = amplitude
        self._running     = False
        self._sample_idx  = 0
        logger.info("MockMicrophone initialized (%dHz, %dch, chunk=%d)",
                    sample_rate, channels, chunk_size)

    def start(self):
        self._running    = True
        self._sample_idx = 0
        logger.debug("MockMicrophone started")

    def stop(self):
        self._running = False
        logger.debug("MockMicrophone stopped")

    def read(self) -> bytes:
        """
        Return one chunk of synthetic PCM audio (16-bit signed, little-endian).

        Raises RuntimeError if not started.
        """
        if not self._running:
            raise RuntimeError("Call start() before read()")

        samples: List[int] = []
        two_pi_f_over_sr = 2.0 * math.pi * self.frequency_hz / self.sample_rate
        max_val = 32767  # 2^15 - 1

        for _ in range(self.chunk_size):
            # One sample per channel (channels share same sine phase for simplicity)
            value = self.amplitude * math.sin(two_pi_f_over_sr * self._sample_idx)
            sample = int(value * max_val)
            for _ in range(self.channels):
                samples.append(sample)
            self._sample_idx += 1

        return struct.pack(f"<{len(samples)}h", *samples)

    @property
    def bytes_per_chunk(self) -> int:
        """Number of bytes returned by each read() call."""
        return self.chunk_size * self.channels * 2  # 16-bit = 2 bytes per sample

    def __repr__(self):
        return (f"MockMicrophone(sample_rate={self.sample_rate}, "
                f"channels={self.channels}, chunk_size={self.chunk_size})")


class MockSpeaker(SpeakerInterface):
    """
    Null-sink audio output that accepts and discards PCM (Pulse-Code Modulation)
    data.

    Implements :class:`~simulation.hal.device.SpeakerInterface`.

    Useful as a drop-in replacement for real audio output in tests and
    headless environments.

    Example::

        speaker = MockSpeaker(sample_rate=16000)
        speaker.start()
        speaker.write(pcm_bytes)
        speaker.stop()
    """

    def __init__(
        self,
        sample_rate: int = 16_000,
        channels: int = 1,
    ):
        self.sample_rate  = sample_rate
        self.channels     = channels
        self._running     = False
        self.bytes_written = 0
        logger.info("MockSpeaker (null sink) initialized (%dHz, %dch)",
                    sample_rate, channels)

    def start(self):
        self._running   = True
        self.bytes_written = 0
        logger.debug("MockSpeaker started")

    def stop(self):
        self._running = False
        logger.debug("MockSpeaker stopped (%d bytes discarded)", self.bytes_written)

    def write(self, data: bytes) -> int:
        """Discard audio data; return number of bytes 'written'."""
        if not self._running:
            raise RuntimeError("Call start() before write()")
        self.bytes_written += len(data)
        return len(data)

    def play_tone(self, frequency_hz: float = 440.0, duration_sec: float = 0.5):
        """Simulate playing a tone (generates and discards PCM; no actual audio)."""
        if not self._running:
            raise RuntimeError("Call start() before play_tone()")
        n_samples = int(self.sample_rate * duration_sec)
        fake_bytes = n_samples * self.channels * 2
        self.bytes_written += fake_bytes
        logger.debug("MockSpeaker: discarded %.1f sec at %.1fHz (%d bytes)",
                     duration_sec, frequency_hz, fake_bytes)

    def __repr__(self):
        return f"MockSpeaker(sample_rate={self.sample_rate}, channels={self.channels})"

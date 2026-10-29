"""Derive the quieter one-second asset without modifying the original tone."""
from array import array
from pathlib import Path
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
with wave.open(str(ROOT / 'src/static/dtmf5-2sec.wav'), 'rb') as source:
    assert (source.getnchannels(), source.getsampwidth(), source.getframerate()) == (1, 2, 8000)
    samples = array('h', source.readframes(8000))
if sys.byteorder != 'little':
    samples.byteswap()
# Retain the original fade-in; add a 10 ms fade-out to the new endpoint.
for i, sample in enumerate(samples):
    fade = min(1.0, (len(samples) - 1 - i) / 79)
    samples[i] = round(sample * 0.5 * fade)
if sys.byteorder != 'little':
    samples.byteswap()
with wave.open(str(ROOT / 'src/static/dtmf5-1sec-half.wav'), 'wb') as output:
    output.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
    output.writeframes(samples.tobytes())

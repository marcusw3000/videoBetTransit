"""Read-only measurement; reports fresh frames, not repeated publisher frames.

Run with the project's Python while the worker is running. No source URLs,
tokens, or configuration contents are printed.
"""
import argparse
import json
import statistics
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--duration", type=float, default=90)
args = parser.parse_args()
if args.duration < 2:
    parser.error('--duration must be at least 2 seconds')
samples = []
start = time.monotonic()
while time.monotonic() - start < args.duration:
    with urllib.request.urlopen("http://127.0.0.1:8090/health", timeout=3) as response:
        health = json.load(response)
    sample = {"seconds": round(time.monotonic() - start, 2), **{
        key: health.get(key) for key in (
            "framesProcessed", "capturedFrames", "publishedFrames", "annotatedFrameAgeMs",
            "rawFrameAgeMs", "streamConnected", "streamFailures", "publisherRestartCount",
        )
    }}
    samples.append(sample)
    if len(samples) % 10 == 0:
        print(json.dumps(sample), flush=True)
    time.sleep(1)

# Startup is reported separately, not counted as a freeze of an already-live
# feed. All samples after the first processed frame remain in the measurement.
startup_samples = len(samples)
for index, sample in enumerate(samples):
    if sample['framesProcessed'] > 0:
        startup_samples = index
        break
samples = samples[startup_samples:]
if len(samples) < 2:
    print(json.dumps({'startupSamples': startup_samples, 'error': 'Insufficient live frames'}))
    raise SystemExit(1)
rates = [(b["framesProcessed"] - a["framesProcessed"]) / (b["seconds"] - a["seconds"])
         for a, b in zip(samples, samples[1:])]
ages = [s["annotatedFrameAgeMs"] for s in samples if s["annotatedFrameAgeMs"] is not None]
print(json.dumps({
    "startupSamples": startup_samples,
    "durationSeconds": samples[-1]["seconds"] - samples[0]["seconds"],
    "freshFpsAverage": round(statistics.mean(rates), 2),
    "freshFpsMin": round(min(rates), 2),
    "freshFpsMax": round(max(rates), 2),
    "samplesWithoutNewFrames": sum(rate == 0 for rate in rates),
    "maxFrameAgeMs": max(ages, default=None),
    "disconnectedSamples": sum(not s["streamConnected"] for s in samples),
    "publisherRestarts": samples[-1]["publisherRestartCount"] - samples[0]["publisherRestartCount"],
    "captureFps": round((samples[-1]['capturedFrames'] - samples[0]['capturedFrames']) / (samples[-1]['seconds'] - samples[0]['seconds']), 2),
    "publishFps": round((samples[-1]['publishedFrames'] - samples[0]['publishedFrames']) / (samples[-1]['seconds'] - samples[0]['seconds']), 2),
}), flush=True)

#!/usr/bin/env python3
"""The loudness of the sound track of a recording, to check sounds without listening.

Prints the peak of every 0.1 s of the track from START for LENGTH seconds, with a bar: the steps of
a walking character are a peak about once a second, the music is an even level.

usage: audio_peaks.py <video> [START seconds, default 0] [LENGTH seconds, default 10]
"""
import array
import subprocess
import sys

RATE = 8000
SLICE = RATE // 10


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    start = sys.argv[2] if len(sys.argv) > 2 else "0"
    length = sys.argv[3] if len(sys.argv) > 3 else "10"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", start, "-t", length, "-i", sys.argv[1], "-vn",
                          "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"], capture_output=True, check=True).stdout
    samples = array.array("h", raw)
    for i in range(0, len(samples) - SLICE, SLICE):
        peak = max(abs(x) for x in samples[i:i + SLICE])
        print(f"{float(start) + i / RATE:7.1f} {peak:6d} {'#' * (peak // 400)}")


if __name__ == "__main__":
    main()

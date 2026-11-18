#!/usr/bin/env python3
"""shorts-pipeline: turn a plain-text script into a captioned vertical Short.

    python pipeline.py script.txt -o short.mp4

Script format: plain text. Each sentence becomes one scene (one caption card,
one voiced line), so the picture changes about every 2-4 seconds. Put your
punchline in the first sentence. Long sentences are split at commas.

Needs ffmpeg + ffprobe on PATH. Voice-over uses Windows built-in speech (SAPI)
or `espeak-ng` if installed; otherwise the video is silent with timing from
word count. Standard library only.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import wave
from pathlib import Path

W, H, FPS = 1080, 1920, 30
PALETTE = ["0x1b2a49", "0x7a2e2e", "0x23524a", "0x4a3a1a", "0x3b2a5c"]
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
MAX_WORDS = 14          # split sentences longer than this at commas
WRAP_CHARS = 18         # caption line width at font size 84
WORDS_PER_SEC = 2.6     # silent-mode reading speed


def split_scenes(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    sentences = re.split(r"(?<=[.!?])\s+", text)
    scenes: list[str] = []
    for s in sentences:
        if not s:
            continue
        if len(s.split()) > MAX_WORDS and "," in s:
            parts = [p.strip() for p in re.split(r"(?<=,)\s+", s) if p.strip()]
            buf = ""
            for p in parts:                      # re-merge tiny fragments
                if buf and len((buf + " " + p).split()) > MAX_WORDS:
                    scenes.append(buf)
                    buf = p
                else:
                    buf = (buf + " " + p).strip()
            if buf:
                scenes.append(buf)
        else:
            scenes.append(s)
    return scenes


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)]).stdout
    return float(out.strip())


SAPI_PS1 = r"""
param([string]$TextFile, [string]$OutWav, [int]$Rate)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = $Rate
$s.SetOutputToWaveFile($OutWav)
$s.Speak([IO.File]::ReadAllText($TextFile))
$s.Dispose()
"""


def tts(text: str, out_wav: Path, work: Path, rate: int) -> bool:
    """Try to synthesise speech to out_wav. Returns False if no engine."""
    txt = work / "tts.txt"
    txt.write_text(text, encoding="utf-8")
    try:
        if sys.platform == "win32":
            ps1 = work / "sapi.ps1"
            ps1.write_text(SAPI_PS1, encoding="utf-8")
            run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(ps1), str(txt), str(out_wav), str(rate)])
            return out_wav.exists() and out_wav.stat().st_size > 1000
        if shutil.which("espeak-ng"):
            run(["espeak-ng", "-f", str(txt), "-w", str(out_wav)])
            return out_wav.exists()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return False


def silent_wav(path: Path, seconds: float) -> None:
    rate = 22050
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))


def render_scene(i: int, text: str, bg: str, wav: Path, dur: float,
                 work: Path, total: int) -> Path:
    caption = work / f"cap{i}.txt"
    caption.write_text("\n".join(textwrap.wrap(text, WRAP_CHARS)), encoding="utf-8")
    out = work / f"scene{i:03d}.mp4"
    # drawtext reads text + font from files in `work` (cwd), which avoids
    # all of ffmpeg's filter-string escaping rules.
    vf = (f"drawtext=fontfile=font.ttf:textfile=cap{i}.txt:fontsize=84:"
          f"fontcolor=white:borderw=6:bordercolor=black:line_spacing=18:"
          f"x=(w-text_w)/2:y=(h-text_h)/2")
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "lavfi", "-i", f"color=c={bg}:s={W}x{H}:r={FPS}",
           "-i", wav.name,
           "-t", f"{dur:.3f}",
           "-vf", f"{vf}", "-r", str(FPS),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "160k",
           "-shortest", out.name]
    run(cmd, cwd=work)
    return out


def build(script: Path, out: Path, rate: int, pad: float, keep: bool) -> int:
    scenes = split_scenes(script.read_text(encoding="utf-8"))
    if not scenes:
        print("script is empty", file=sys.stderr)
        return 2
    font = next((f for f in FONT_CANDIDATES if Path(f).exists()), None)
    if not font:
        print("no bold font found; edit FONT_CANDIDATES in pipeline.py", file=sys.stderr)
        return 2

    work = Path(tempfile.mkdtemp(prefix="shorts_"))
    shutil.copy(font, work / "font.ttf")
    try:
        parts: list[Path] = []
        voiced = True
        for i, text in enumerate(scenes):
            wav = work / f"v{i}.wav"
            if voiced and not tts(text, wav, work, rate):
                voiced = False
                print("note: no speech engine found, making a silent video")
            if voiced:
                dur = duration(wav) + pad
                # pad wav with silence to cover `pad`
                padded = work / f"v{i}p.wav"
                run(["ffmpeg", "-v", "error", "-y", "-i", str(wav),
                     "-af", f"apad=pad_dur={pad}", str(padded)])
                wav = padded
            else:
                dur = max(1.6, len(text.split()) / WORDS_PER_SEC) + pad
                silent_wav(wav, dur)
            # last scene reuses the first background so the loop point matches
            bg = PALETTE[0] if (i == len(scenes) - 1 and len(scenes) > 1) \
                else PALETTE[i % len(PALETTE)]
            parts.append(render_scene(i, text, bg, wav, dur, work, len(scenes)))
            print(f"scene {i + 1}/{len(scenes)}: {dur:.1f}s  {text[:50]}")

        listing = work / "list.txt"
        listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
             "-i", "list.txt", "-c", "copy", "-movflags", "+faststart",
             str(out.resolve())], cwd=work)
        total = duration(out)
        size = out.stat().st_size / 1_048_576
        print(f"\nwrote {out}  ({total:.1f}s, {size:.1f} MB)")
        if not 55 <= total <= 75:
            print("tip: your retention target is 55-75 s; adjust the script length")
        return 0
    except subprocess.CalledProcessError as e:
        print("ffmpeg/ffprobe failed:\n" + (e.stderr or str(e)), file=sys.stderr)
        return 1
    finally:
        if keep:
            print(f"kept working files in {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("short.mp4"))
    ap.add_argument("--rate", type=int, default=2, help="SAPI speech rate -10..10 (default 2)")
    ap.add_argument("--pad", type=float, default=0.25, help="silence after each line, seconds")
    ap.add_argument("--keep", action="store_true", help="keep temp working folder")
    ap.add_argument("--dry-run", action="store_true", help="only print the scene split")
    args = ap.parse_args(argv)

    if args.dry_run:
        for i, s in enumerate(split_scenes(args.script.read_text(encoding="utf-8")), 1):
            print(f"{i:2d}. {s}")
        return 0
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            print(f"{tool} not found on PATH", file=sys.stderr)
            return 2
    return build(args.script, args.output, args.rate, args.pad, args.keep)


if __name__ == "__main__":
    sys.exit(main())

# shorts-pipeline

[![tests](https://github.com/SamruddhBorker/shorts-pipeline/actions/workflows/tests.yml/badge.svg)](https://github.com/SamruddhBorker/shorts-pipeline/actions/workflows/tests.yml)
 
One command from a text script to a finished vertical (1080x1920) captioned
Short: voice-over, big caption cards, scene changes every few seconds.

```bash
python pipeline.py example_script.txt -o short.mp4
python pipeline.py my_script.txt --dry-run     # preview the scene split
```

## How it works

1. Splits the script into scenes (one sentence each; long ones split at commas)
2. Speaks each scene (Windows SAPI, or `espeak-ng` on Linux/macOS; silent fallback)
3. Renders a caption card per scene with ffmpeg, timed to the voice
4. Concatenates everything into one MP4
5. The last card reuses the first card's colour to help the loop

Built around three retention rules: **punchline first, change every ~2 s,
seamless loop**. Put the hook in your first sentence. It prints a tip if the
result is outside 55–75 s.

## Requirements

- Python 3.9+
- `ffmpeg` and `ffprobe` on PATH
- no pip packages

## Options

| flag | meaning |
|---|---|
| `-o` | output file (default `short.mp4`) |
| `--rate` | speech speed, -10 to 10 (Windows) |
| `--pad` | silence after each line, seconds |
| `--keep` | keep the temporary working folder |
| `--dry-run` | only print the scenes |

## Tests

```bash
python -m unittest -v
```

Pairs well with [shorts-export-checker](../shorts-export-checker) to verify the
output before upload.

## License

MIT

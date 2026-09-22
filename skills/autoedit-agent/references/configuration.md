# Configuration and optional APIs

The core `scripts/autoedit.py` is Python-standard-library-only. Install FFmpeg and
FFprobe separately and put them on PATH. No model key, TTS key, Resolve install,
MCP process, paid editor, or internet connection is required for local rendering.

Optional macOS Jianying: `python -m pip install pyJianYingDraft==0.3.0`. The package
is used as a base serializer; this repository post-processes its output into a Mac
`draft_info.json` draft and self-contained `Resources/`. Run `doctor --backend jianying`
on the target Mac. Set `JY_DRAFT_ROOT` when your Jianying draft library is not at the
standard Movies path. The default installation does not install the optional package.

Adapted original cloud helpers remain available in this skill as `analyze_frames.py` and
`generate_tts.py`. They require `requests` and `python-dotenv` (repository
`requirements-api.txt`). Use a provider contract that matches the helper; not every
API that advertises TTS uses the same request or binary-response shape.

For frame analysis, configure `LLM_BASE_URL`, `LLM_MODEL`, optional `LLM_API_KEY`,
and optional `LLM_TIMEOUT_SECONDS`; the helper calls `<base>/chat/completions`.
The new extractor's `frames-index.json` is accepted by the analysis helper.

```bash
python scripts/analyze_frames.py --frames-index "<frames>/frames-index.json" --output "<new-analysis.jsonl>" --topic "<approved-topic>"
```

For TTS, configure `TTS_BASE_URL` (complete endpoint), optional `TTS_API_KEY` and
`TTS_MODEL`; `TTS_REFERENCE_AUDIO` is used only with explicitly authorized
`--mode multipart`. JSON input is a list of `{ "id": "line-1", "text": "..." }`.
The server must return binary WAV as the response body, not a URL, JSON wrapper or another format.
The output directory must be new; filenames are generated independently of narration IDs.

```bash
python scripts/generate_tts.py --script "<approved-narration.json>" --output "<new-tts-directory>"
```

Approval is required before external uploads or billable calls, even when a key
exists. Load `.env` from your working project; never commit it, private endpoint
values, source media, generated manifests with personal paths, or voice samples.
Review per-frame errors and every TTS output; never treat HTTP success as content
quality, correct pronunciation, or valid synchronized narration.

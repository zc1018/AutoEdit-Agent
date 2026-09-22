"""Optional, approved HTTP TTS helper. Requires a binary WAV response."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import requests
from dotenv import load_dotenv
from autoedit import probe, stream, write_json


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--endpoint', default=os.getenv('TTS_BASE_URL',''))
    parser.add_argument('--model', default=os.getenv('TTS_MODEL',''))
    parser.add_argument('--reference-audio', type=Path, default=os.getenv('TTS_REFERENCE_AUDIO') or None)
    parser.add_argument('--mode', choices=('json','multipart'), default='json')
    args = parser.parse_args()
    if not args.endpoint:
        raise SystemExit('Set TTS_BASE_URL or pass --endpoint for the approved provider.')
    segments = json.loads(args.script.read_text(encoding='utf-8'))
    if not isinstance(segments,list) or not segments:
        raise SystemExit('Narration must be a nonempty JSON list of {id,text}.')
    ids = set()
    for index, segment in enumerate(segments,1):
        if not isinstance(segment,dict) or not isinstance(segment.get('text'),str) or not segment['text'].strip():
            raise SystemExit('Each narration segment needs nonempty text.')
        sid = str(segment.get('id') or index)
        if sid in ids:
            raise SystemExit('Narration IDs must be unique.')
        ids.add(sid)
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    headers = {'Authorization':'Bearer '+os.environ['TTS_API_KEY']} if os.getenv('TTS_API_KEY') else {}
    manifest = []
    try:
        for index, segment in enumerate(segments,1):
            payload = {'text':segment['text'], 'model':args.model}
            if args.mode == 'multipart' and args.reference_audio:
                with args.reference_audio.open('rb') as audio:
                    response = requests.post(args.endpoint, data=payload, headers=headers,
                        files={'reference_audio':(args.reference_audio.name,audio,'audio/wav')}, timeout=1200)
            elif args.mode == 'multipart':
                response = requests.post(args.endpoint, data=payload, headers=headers, timeout=1200)
            else:
                response = requests.post(args.endpoint, json=payload, headers=headers, timeout=1200)
            response.raise_for_status()
            content = response.content
            if content[:4] != b'RIFF' or content[8:12] != b'WAVE':
                raise ValueError('Provider must return binary WAV, not JSON, a URL, or another audio format.')
            # IDs remain metadata; never concatenate user/model-provided IDs into a file path.
            target = output/f'segment-{index:04}.wav'
            with target.open('xb') as handle:
                handle.write(content)
            info = probe(target)
            if stream(info,'audio') is None:
                raise ValueError('TTS response has no decodable audio stream.')
            manifest.append({'id':str(segment.get('id') or index),'text':segment['text'],
                             'audio_path':str(target),'duration_seconds':float(info['format']['duration'])})
        write_json(output/'tts-manifest.json', manifest)
    except Exception as exc:
        write_json(output/'FAILED.json', {'status':'failed','error_type':type(exc).__name__,
                                          'completed_segments':len(manifest)})
        raise SystemExit(f'TTS failed ({type(exc).__name__}); completed files preserved for review.') from None
    print(output/'tts-manifest.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

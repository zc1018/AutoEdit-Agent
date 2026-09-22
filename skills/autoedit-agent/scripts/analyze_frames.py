"""Optional approved cloud frame review. Adapted from the original repository helper."""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import requests
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames-index', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--topic', required=True)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    endpoint, model = os.getenv('LLM_BASE_URL', ''), os.getenv('LLM_MODEL', '')
    if not endpoint or not model:
        raise SystemExit('Set LLM_BASE_URL and LLM_MODEL before approved API analysis.')
    rows = [r for r in json.loads(args.frames_index.read_text(encoding='utf-8')) if r.get('ok')]
    if args.limit > 0:
        rows = rows[:args.limit]
    headers = {'Content-Type':'application/json'}
    if os.getenv('LLM_API_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['LLM_API_KEY']
    failed = 0
    # Exclusive create prevents replacing an existing approved review.
    with args.output.open('x', encoding='utf-8') as handle:
        for row in rows:
            try:
                encoded = base64.b64encode(Path(row['image_path']).read_bytes()).decode('ascii')
                prompt = ('Analyze this frame objectively for a video editor. Return JSON with '
                          'description, visible_text, people, actions, setting, technical_quality, '
                          'continuity_clues, suggested_uses and tags. Do not invent details. Topic: ' + args.topic)
                payload = {'model':model, 'temperature':.2, 'response_format':{'type':'json_object'},
                           'messages':[{'role':'user','content':[{'type':'text','text':prompt},
                           {'type':'image_url','image_url':{'url':f'data:image/jpeg;base64,{encoded}'}}]}]}
                response = requests.post(endpoint.rstrip('/')+'/chat/completions', headers=headers,
                                         json=payload, timeout=int(os.getenv('LLM_TIMEOUT_SECONDS','300')))
                response.raise_for_status()
                result = json.loads(response.json()['choices'][0]['message']['content'])
                item = dict(row, analysis=result, error='')
            except Exception as exc:
                failed += 1
                # Do not write URL/token-bearing HTTP exception strings into a shareable report.
                item = dict(row, analysis={}, error=type(exc).__name__)
            handle.write(json.dumps(item, ensure_ascii=False)+'\n')
            handle.flush()
    print(json.dumps({'output':str(args.output), 'frames':len(rows), 'failed':failed}))
    return 2 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())

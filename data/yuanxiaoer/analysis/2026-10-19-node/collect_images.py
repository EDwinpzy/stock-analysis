from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json

import requests

OUT = Path(__file__).resolve().parent
post = json.loads((OUT.parents[1] / 'posts' / '2vZYBKxSFEq.json').read_text(encoding='utf-8'))
jobs = [('post', u) for u in post['images']]
jobs += [(r['id'], u) for r in post['author_replies'] for u in r.get('images', []) if '/face/' not in u]

def fetch(job):
    key, url = job
    response = requests.get(url, timeout=25)
    response.raise_for_status()
    path = OUT / (key + '-' + url.split('/')[-1])
    path.write_bytes(response.content)
    return {'location': key, 'url': url, 'path': str(path), 'byte_sha256': hashlib.sha256(response.content).hexdigest()}

rows = list(ThreadPoolExecutor(max_workers=4).map(fetch, jobs))
(OUT / 'image_manifest.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(rows, ensure_ascii=False, indent=2))

# Publish the working demo as a Hugging Face Space (Gradio SDK).
# NOTE (25 Nov 2026): Hugging Face answered 402 Payment Required: Gradio and Docker Spaces now need PRO; free accounts get static Spaces only.
# Staging and the vehicle-number check below work (dry run: 41 files, 156 MB); the upload needs a PRO account or another host.
# Ships code + aggregated outputs + the built router network; never the ticket file or GPS.
# One-time: `pip install huggingface_hub` and `hf auth login` (your own token, stored locally).
# Usage: .venv/Scripts/python.exe scripts/deploy_hf.py <hf-username>/seatcast-delhi
import re
import shutil
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FILES = ['pyproject.toml', 'requirements.txt', 'config.yaml', 'LICENSE']
DIRS = ['src', 'web', 'config']
DATA = ['data/out/cells.parquet', 'data/out/operator.parquet', 'data/out/segments.geojson', 'data/out/coverage.json',
        'data/out/gps_checks.json', 'data/out/route_profiles.json', 'data/work/network.npz',
        'data/raw/gtfs/stops.txt', 'data/raw/gtfs/routes.txt', 'data/raw/gtfs/trips.txt']
SPACE_README = '''---
title: SeatCast Delhi
emoji: 🚌
colorFrom: yellow
colorTo: red
sdk: gradio
app_file: app.py
python_version: 3.12
pinned: false
license: mit
---

SeatCast Delhi: how crowded Delhi's buses usually are, stretch by stretch, next to every journey option.
Built for the Delhi Transport Stack Hackathon 2026, Problem 2. Code and method: https://github.com/sahilsahu4102/SeatCast

Data: crowding aggregates derived from October 2026 app e-tickets and GPS, and the Delhi bus GTFS,
courtesy of the Transport Department, GNCTD / Delhi Transport Stack. No ticket or vehicle-level data is included.
'''
APP = '''from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from seatcast.api import app

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=7860)
'''
VEHICLE = re.compile(rb'\bDL\d{1,2}[A-Z]{1,3}\d{1,4}\b', re.I)


def stage(d):
    for f in FILES:
        if f != 'requirements.txt':
            shutil.copy2(ROOT / f, d / f)
    req = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
    (d / 'requirements.txt').write_text(
        ''.join(line for line in req.splitlines(keepends=True) if line.strip() != '-e .'),
        encoding='utf-8')
    for x in DIRS:
        shutil.copytree(ROOT / x, d / x, ignore=shutil.ignore_patterns('__pycache__', '*.egg-info'))
    for f in DATA:
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, d / f)
    (d / 'README.md').write_text(SPACE_README, encoding='utf-8')
    (d / 'app.py').write_text(APP, encoding='utf-8')
    (d / '.gitattributes').write_text('*.parquet filter=lfs diff=lfs merge=lfs -text\n*.npz filter=lfs diff=lfs merge=lfs -text\n'
                                      '*.geojson filter=lfs diff=lfs merge=lfs -text\ndata/raw/gtfs/*.txt filter=lfs diff=lfs merge=lfs -text\n'
                                      'route_profiles.json filter=lfs diff=lfs merge=lfs -text\n', encoding='utf-8')
    check_private(d)


def check_private(d):
    for f in d.rglob('*'):
        if not f.is_file():
            continue
        if f.suffix == '.parquet':
            import pyarrow.parquet as pq
            for batch in pq.ParquetFile(f).iter_batches():
                for col in batch.to_pydict().values():
                    if any(isinstance(v, str) and VEHICLE.search(v.encode()) for v in col):
                        raise ValueError(f'vehicle number pattern found in staged file: {f.relative_to(d)}')
        elif f.suffix == '.npz':
            with np.load(f, allow_pickle=False) as z:
                for name in z.files:
                    arr = z[name]
                    if arr.dtype.kind in 'US':
                        for val in arr.flat:
                            s = val.decode() if isinstance(val, bytes) else str(val)
                            if VEHICLE.search(s.encode()):
                                raise ValueError(f'vehicle number pattern found in staged file: {f.relative_to(d)}')
        elif VEHICLE.search(f.read_bytes()):
            raise ValueError(f'vehicle number pattern found in staged file: {f.relative_to(d)}')


if __name__ == '__main__':
    if len(sys.argv) != 2 or '/' not in sys.argv[1]:
        sys.exit('usage: python scripts/deploy_hf.py <hf-username>/<space-name>')
    repo = sys.argv[1]
    api = HfApi()
    api.create_repo(repo, repo_type='space', space_sdk='gradio', exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.deploy-hf-', dir=ROOT) as t:
        d = Path(t)
        stage(d)
        api.upload_folder(repo_id=repo, repo_type='space', folder_path=d, commit_message='Deploy SeatCast Delhi')
    print(f'https://huggingface.co/spaces/{repo}')

# Publish the working demo as a Hugging Face Space (Docker, free CPU tier: 2 vCPU, 16 GB RAM).
# Ships code + aggregated outputs + the built router network; never the ticket file or GPS.
# One-time: `pip install huggingface_hub` and `hf auth login` (your own token, stored locally).
# Usage: .venv/Scripts/python.exe scripts/deploy_hf.py <hf-username>/seatcast-delhi
import shutil
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

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
sdk: docker
app_port: 7860
pinned: false
license: mit
---

SeatCast Delhi: how crowded Delhi's buses usually are, stretch by stretch, next to every journey option.
Built for the Delhi Transport Stack Hackathon 2026, Problem 2. Code and method: https://github.com/sahilsahu4102/SeatCast

Data: crowding aggregates derived from October 2026 app e-tickets and GPS, and the Delhi bus GTFS,
courtesy of the Transport Department, GNCTD / Delhi Transport Stack. No ticket or vehicle-level data is included.
'''
DOCKERFILE = '''FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "seatcast.api:app", "--host", "0.0.0.0", "--port", "7860"]
'''


def stage(d):
    for f in FILES:
        shutil.copy2(ROOT / f, d / f)
    for x in DIRS:
        shutil.copytree(ROOT / x, d / x, ignore=shutil.ignore_patterns('__pycache__', '*.egg-info'))
    for f in DATA:
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, d / f)
    (d / 'README.md').write_text(SPACE_README, encoding='utf-8')
    (d / 'Dockerfile').write_text(DOCKERFILE, encoding='utf-8')
    (d / '.gitattributes').write_text('*.parquet filter=lfs diff=lfs merge=lfs -text\n*.npz filter=lfs diff=lfs merge=lfs -text\n'
                                      '*.geojson filter=lfs diff=lfs merge=lfs -text\n*.txt filter=lfs diff=lfs merge=lfs -text\n'
                                      'route_profiles.json filter=lfs diff=lfs merge=lfs -text\n', encoding='utf-8')


if __name__ == '__main__':
    if len(sys.argv) != 2 or '/' not in sys.argv[1]:
        sys.exit('usage: python scripts/deploy_hf.py <hf-username>/<space-name>')
    repo = sys.argv[1]
    api = HfApi()
    api.create_repo(repo, repo_type='space', space_sdk='docker', exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        stage(d)
        api.upload_folder(repo_id=repo, repo_type='space', folder_path=d, commit_message='Deploy SeatCast Delhi')
    print(f'https://huggingface.co/spaces/{repo}')

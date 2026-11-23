from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW, WORK, OUT = ROOT / 'data' / 'raw', ROOT / 'data' / 'work', ROOT / 'data' / 'out'


@lru_cache
def cfg():
    return yaml.safe_load((ROOT / 'config.yaml').read_text(encoding='utf-8'))

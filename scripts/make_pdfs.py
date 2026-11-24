# Render docs/PROPOSAL.md and docs/TECH_NOTE.md to PDF for submission (needs `pip install markdown` and Microsoft Edge).
# Usage: .venv/Scripts/python.exe scripts/make_pdfs.py
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
EDGE = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
CSS = '''
@page { size: A4; margin: 16mm 15mm; }
body { font: 10.5pt/1.45 "Segoe UI", Arial, sans-serif; color: #1b1c1e; }
h1 { font-size: 19pt; margin: 0 0 6pt; } h2 { font-size: 13.5pt; margin: 14pt 0 4pt; border-bottom: 1.5px solid #1b1c1e; }
h3 { font-size: 11.5pt; margin: 10pt 0 3pt; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 9.5pt; page-break-inside: avoid; }
th, td { border: 1px solid #c9c9c1; padding: 3pt 5pt; text-align: left; vertical-align: top; }
th { background: #f0f0ea; } code { font: 9pt Consolas, monospace; background: #f3f3ee; padding: 0 2pt; }
blockquote { margin: 6pt 0; padding: 2pt 10pt; border-left: 3px solid #ffd400; background: #fbfbf4; }
a { color: #1c5cab; text-decoration: none; } li { margin: 1.5pt 0; }
'''
DOCS = {'PROPOSAL.md': 'SeatCast_Proposal.pdf', 'TECH_NOTE.md': 'SeatCast_Technical_Note.pdf'}


def reindent(text):
    # GitHub nests lists at 3 spaces; Python-Markdown needs 4
    out = []
    for line in text.split('\n'):
        n = len(line) - len(line.lstrip(' '))
        lvl = 1 if 2 <= n <= 4 else 2 if 5 <= n <= 8 else 0  # docs nest at 2 or 3 spaces per level
        out.append(' ' * (4 * lvl) + line[n:] if lvl else line)
    return '\n'.join(out)


def render(src, out):
    body = markdown.markdown(reindent(src.read_text(encoding='utf-8')), extensions=['tables', 'fenced_code', 'sane_lists'])
    with tempfile.TemporaryDirectory() as d:
        html = Path(d) / 'doc.html'
        html.write_text(f'<!doctype html><meta charset="utf-8"><title>{out.stem}</title><style>{CSS}</style>{body}', encoding='utf-8')
        subprocess.run([str(EDGE), '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
                        f'--print-to-pdf={out}', html.as_uri()], check=True, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(out.relative_to(ROOT), f'{out.stat().st_size // 1024} KB')


if __name__ == '__main__':
    for md, pdf in DOCS.items():
        render(ROOT / 'docs' / md, ROOT / 'docs' / pdf)
    sys.exit(0)

"""Verify repository files against the release manifest, using Python stdlib."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'release-manifest.json').read_text(encoding='utf-8'))
errors = []
for name, expected in manifest['files'].items():
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        errors.append({'file': name, 'error': 'missing or outside repository'})
    elif sha256(path.read_bytes()).hexdigest() != expected:
        errors.append({'file': name, 'error': 'hash mismatch'})
print(json.dumps({'passed': not errors, 'version': manifest['version'],
                  'files': len(manifest['files']), 'errors': errors}, ensure_ascii=False))
if errors:
    sys.exit(1)
sys.exit(subprocess.run([sys.executable, str(root / 'skills/workflow-orchestrator/scripts/method_check.py')]).returncode)

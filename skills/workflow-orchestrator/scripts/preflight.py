"""Probe the selected runtime, browser and evidence schema before project mutations.

Only temporary probe files are created. This does not authorize a workflow stage
or certify real-device compatibility, user validation or an exported prototype.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

import workspace


def run(command, timeout=20):
    return subprocess.run(command, capture_output=True, encoding='utf-8',
                          errors='replace', timeout=timeout,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def probe_python(executable):
    try:
        proc = run([executable, '-I', '-X', 'utf8', '-c',
                    'import json,sys;print(json.dumps({"executable":sys.executable,"version":list(sys.version_info[:3])}))'])
        data = json.loads(proc.stdout) if proc.returncode == 0 else {}
        version = data.get('version', [])
        ok = len(version) == 3 and tuple(version) >= (3, 10, 0)
        return {'status': 'passed' if ok else 'failed', 'requested': executable,
                'observed': data, 'error': '' if ok else 'Requires an actually running Python 3.10+.'}
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {'status': 'failed', 'requested': executable, 'error': str(exc)}


def find_browser():
    candidates = [shutil.which(name) for name in
                  ('msedge', 'chrome', 'chromium', 'chromium-browser', 'google-chrome')]
    for base in (os.environ.get('PROGRAMFILES'), os.environ.get('PROGRAMFILES(X86)'),
                 os.environ.get('LOCALAPPDATA')):
        if base:
            candidates.extend(str(Path(base) / tail) for tail in
                              ('Microsoft/Edge/Application/msedge.exe', 'Google/Chrome/Application/chrome.exe'))
    return next((p for p in candidates if p and Path(p).is_file()), None)


def probe_browser(executable):
    executable = find_browser() if executable == 'auto' else executable
    if not executable:
        return {'status': 'pending', 'error': 'No local Chromium browser found; use an available browser tool and record its actual smoke test.'}
    try:
        with tempfile.TemporaryDirectory(prefix='workflow-browser-probe-') as scratch:
            base = Path(scratch)
            marker = 'probe-' + uuid.uuid4().hex
            page = base / 'probe.html'
            page.write_text('<!doctype html><meta charset="utf-8"><p id="result">pending</p>'
                            '<script>document.getElementById("result").textContent=' + json.dumps(marker) + '</script>', encoding='utf-8')
            proc = run([executable, '--headless=new', '--disable-gpu', '--no-first-run',
                        '--no-default-browser-check', '--disable-background-networking',
                        '--user-data-dir=' + str(base / 'profile'), '--dump-dom', page.as_uri()], timeout=30)
            ok = proc.returncode == 0 and ('id="result">' + marker + '</p>') in proc.stdout
            return {'status': 'passed' if ok else 'failed', 'executable': executable,
                    'operation': 'Open a local HTML file and observe JavaScript update its DOM.',
                    'observed': 'expected DOM marker' if ok else 'expected DOM marker absent',
                    'error': '' if ok else proc.stderr[-1200:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'status': 'failed', 'executable': executable, 'error': str(exc)}


def browser_tool_record(path):
    """Accept an actual external-tool record without calling it a local probe."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict):
            raise ValueError('Browser tool record must be a JSON object.')
        required = ('tool', 'at', 'operation', 'expected', 'observed', 'evidence')
        if data.get('status') != 'passed' or not all(isinstance(data.get(k), str) and data[k].strip() for k in required):
            raise ValueError('Browser tool record requires passed status, tool, at, operation, expected, observed and evidence locator.')
        return {'status': 'recorded', 'record': str(Path(path).resolve()),
                'observed': data, 'limit': 'Caller-supplied actual tool evidence; this script does not independently verify it.'}
    except (OSError, ValueError, TypeError) as exc:
        return {'status': 'failed', 'error': str(exc)}


def probe_evidence(kind, root=None, payload=None):
    try:
        if payload:
            if root is None:
                raise ValueError('--root is required when checking --payload evidence.')
            value = json.loads(Path(payload).read_text(encoding='utf-8-sig'))
            if not isinstance(value, dict):
                raise ValueError('put payload must be a JSON object.')
            entries = value.get('evidence', [])
            if not isinstance(entries, list):
                raise ValueError('put evidence must be an array.')
            for entry in entries:
                workspace.evidence(Path(root).resolve(), entry)
        with tempfile.TemporaryDirectory(prefix='workflow-evidence-probe-') as scratch:
            base = Path(scratch)
            (base / 'probe.txt').write_text('TEST schema probe, not business evidence.', encoding='utf-8')
            workspace.evidence(base, {'kind': kind, 'path': 'probe.txt', 'locator': 'TEST full text'})
        return {'status': 'passed', 'kind': kind, 'payload_entries_checked': len(entries) if payload else 0,
                'scope': 'Evidence category, locator, existing contained file; not full put or factual verification.'}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'status': 'failed', 'kind': kind, 'error': str(exc),
                'hint': 'Generated files use evidence.kind=source; prototype is a review_bundle file role, not an evidence kind.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--browser', default='auto', help='auto, a local Chromium executable, tool or skip')
    parser.add_argument('--browser-evidence', help='Actual browser-tool smoke-test JSON record')
    parser.add_argument('--skip-browser-reason')
    parser.add_argument('--evidence-kind', default='source')
    parser.add_argument('--root')
    parser.add_argument('--payload', help='Optional planned put JSON: check its evidence files without registering anything')
    parser.add_argument('--report', help='New report file; never overwrite an existing report')
    args = parser.parse_args(argv)
    if args.browser == 'skip':
        browser = {'status': 'not_applicable', 'reason': args.skip_browser_reason} if args.skip_browser_reason else {'status': 'failed', 'error': 'Skipping a browser probe needs the actual non-browser task scope.'}
    elif args.browser == 'tool':
        browser = browser_tool_record(args.browser_evidence) if args.browser_evidence else {'status': 'failed', 'error': '--browser-evidence is required for tool mode.'}
    else:
        browser = probe_browser(args.browser)
    checks = {'python': probe_python(args.python), 'browser': browser,
              'evidence': probe_evidence(args.evidence_kind, args.root, args.payload)}
    ready = all(v['status'] in ('passed', 'recorded', 'not_applicable') for v in checks.values())
    report = {'at': datetime.now(timezone.utc).isoformat(), 'ready': ready, 'checks': checks,
              'limits': 'Environment/schema only. Browser scope is this smoke test, not project UX, native app or real-device validation. No project state changed.'}
    if args.report:
        try:
            with Path(args.report).open('x', encoding='utf-8') as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            print(json.dumps({'error': str(exc), 'ready': False}, ensure_ascii=False))
            return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ready else 2


if __name__ == '__main__':
    raise SystemExit(main())

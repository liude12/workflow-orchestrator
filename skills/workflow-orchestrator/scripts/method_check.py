"""Read-only integrity check for bundled specialist methods, not execution QA."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


def check(root: Path) -> dict:
    root = root.resolve()
    errors: list[dict] = []
    checked: list[str] = []

    def issue(code, location, detail):
        errors.append({'code': code, 'location': location, 'detail': detail})

    def file_info(rel, expected, location):
        if not isinstance(rel, str) or not rel or '\\' in rel or ':' in rel:
            issue('path', location, 'Expected a relative POSIX file path.')
            return None
        pure = PurePosixPath(rel)
        if pure.is_absolute() or '..' in pure.parts or '.' in rel.split('/'):
            issue('path', location, 'Absolute or traversing paths are not permitted.')
            return None
        path = root.joinpath(*pure.parts)
        try:
            path.resolve().relative_to(root)
            data = path.read_bytes()
        except (ValueError, OSError) as exc:
            issue('file', location, str(exc))
            return None
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            issue('digest', location, 'Expected a SHA-256 value.')
        elif hashlib.sha256(data).hexdigest() != expected:
            issue('changed', location, 'File differs from the reviewed catalog version.')
        checked.append(rel)
        return data

    try:
        catalog = json.loads((root / 'methods/catalog.json').read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        catalog = None
        issue('catalog', 'methods/catalog.json', str(exc))
    if not isinstance(catalog, dict) or type(catalog.get('schema_version')) is not int or catalog.get('schema_version') != 1:
        issue('schema', 'catalog', 'Expected an object with schema_version 1.')
    else:
        licenses = catalog.get('licenses')
        sources = catalog.get('sources')
        methods = catalog.get('methods')
        if not isinstance(licenses, dict) or not licenses:
            issue('schema', 'licenses', 'Expected a nonempty license map.')
            licenses = {}
        for key, value in licenses.items():
            loc = 'licenses.' + key
            if not isinstance(value, dict) or value.get('spdx') != 'MIT':
                issue('license', loc, 'This catalog currently declares MIT source resources only.')
                continue
            file_info(value.get('path'), value.get('sha256'), loc)
        if not isinstance(sources, dict):
            issue('schema', 'sources', 'Expected a source map.')
            sources = {}
        for key, value in sources.items():
            loc = 'sources.' + key
            if not isinstance(value, dict):
                issue('schema', loc, 'Expected a source object.')
                continue
            commit = value.get('commit')
            url = value.get('url')
            if (not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit)
                    or not isinstance(url, str) or not url.startswith('https://')
                    or '/' + commit + '/' not in url):
                issue('source', loc, 'Expected a source URL pinned to its full commit.')
            if not isinstance(value.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
                issue('source', loc, 'Expected the inspected upstream source SHA-256.')
            if not isinstance(value.get('license'), str) or value['license'] not in licenses:
                issue('license', loc, 'Source license is not included in this catalog.')
        if not isinstance(methods, list) or not methods:
            issue('schema', 'methods', 'Expected a nonempty method list.')
            methods = []
        seen = set()
        for index, method in enumerate(methods):
            loc = f'methods[{index}]'
            if not isinstance(method, dict):
                issue('schema', loc, 'Expected a method object.')
                continue
            name = method.get('id')
            if not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9]*(?:-[a-z0-9]+)*', name):
                issue('identity', loc, 'Invalid method id.')
                continue
            if name in seen:
                issue('duplicate', loc, name)
            seen.add(name)
            entry = method.get('entry')
            if entry != f'methods/{name}/SKILL.md':
                issue('identity', loc, 'Entry must match the method id.')
            data = file_info(entry, method.get('sha256'), loc)
            if data is not None:
                try:
                    body = data.decode('utf-8-sig')
                    header = body.split('---', 2)[1] if body.startswith('---') else ''
                    match = re.search(r'^name:\s*[\'\"]?([a-z0-9-]+)[\'\"]?\s*$', header, re.M)
                    if not match or match.group(1) != name:
                        issue('identity', loc, 'SKILL frontmatter name differs from catalog.')
                except UnicodeError:
                    issue('encoding', loc, 'SKILL is not UTF-8.')
            stages = method.get('stages')
            if (not isinstance(stages, list) or not stages
                    or any(stage not in ['S1', 'S2', 'S3', 'S4', 'S5'] for stage in stages)
                    or len(stages) != len(set(stages))):
                issue('stage', loc, 'Expected distinct supported stages.')
            origins = method.get('sources')
            if not isinstance(origins, list) or any(not isinstance(x, str) or x not in sources for x in origins):
                issue('source', loc, 'Unknown or malformed method source references.')
            if not origins and method.get('origin') != 'workflow-original':
                issue('source', loc, 'An unsourced method must declare workflow-original.')
        found = {path.parent.name for path in (root / 'methods').glob('*/SKILL.md')}
        if found != seen:
            issue('coverage', 'methods', 'Catalog and packaged method entries differ: ' + ', '.join(sorted(found ^ seen)))
    return {'kind': 'METHOD_PACKAGE_INTEGRITY_ONLY', 'root': str(root), 'passed': not errors,
            'checked_files': sorted(set(checked)), 'errors': errors,
            'limits': ['No method was executed.', 'No external command/plugin was probed.',
                       'Upstream hashes are provenance declarations; no network verification was performed.',
                       'No product correctness, human validation or authorization is established.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    result = check(args.root)
    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open('x', encoding='utf-8') as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
        except OSError as exc:
            print(json.dumps({'passed': False, 'report_error': str(exc)}, ensure_ascii=False))
            return 1
    print(json.dumps({'passed': result['passed'], 'checked_files': len(result['checked_files']),
                      'errors': result['errors'], 'kind': result['kind']}, ensure_ascii=False))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    sys.exit(main())

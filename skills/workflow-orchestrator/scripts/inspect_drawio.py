"""Read-only checks for uncompressed draw.io sources and stated scenario paths.

Paths JSON: {"paths": [{"name": "case", "page": 1, "nodes": ["N01", "N02"]}]}.
This checks graph structure, not whether business rules or path coverage are correct.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def inspect(source, cases):
    tree = ET.fromstring(source.read_bytes())
    if tree.tag == 'mxGraphModel':
        models = [tree]
    elif tree.tag == 'mxfile':
        diagrams = tree.findall('diagram')
        models = [d.find('mxGraphModel') for d in diagrams]
        if not models or any(model is None for model in models):
            raise ValueError('Compressed/unsupported input: export uncompressed XML with draw.io -x -f xml -u first.')
    else:
        raise ValueError('Expected mxfile or mxGraphModel XML.')
    pages, errors = [], []
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise ValueError('paths must be a list of path objects.')
    for number, model in enumerate(models, 1):
        root = model.find('root')
        if root is None or any(child.tag != 'mxCell' for child in root):
            raise ValueError('Unsupported cell wrappers/root: use explicit mxCell XML or inspect manually; no pass claimed.')
        cells = model.findall('./root/mxCell')
        vertices = [{'id': c.get('id'), 'label': c.get('value', '')} for c in cells if c.get('vertex') == '1']
        vertex_ids = {v['id'] for v in vertices if v['id']}
        if not vertices:
            errors.append(f'page {number}: no vertices to inspect')
        ids = [cell.get('id') for cell in cells]
        if len(set(ids)) != len(ids) or any(not cell_id for cell_id in ids):
            errors.append(f'page {number}: missing/duplicate cell IDs')
        edges = [{'id': c.get('id'), 'source': c.get('source'), 'target': c.get('target'), 'label': c.get('value', '')}
                 for c in cells if c.get('edge') == '1']
        for edge in edges:
            for terminal in ('source', 'target'):
                if edge[terminal] not in vertex_ids:
                    errors.append(f'page {number}: edge {edge["id"]} {terminal} {edge[terminal]!r} is not a vertex')
        pages.append({'page': number, 'vertices': vertices, 'edges': edges})
    for case in cases:
        number, nodes = case.get('page', 1), case['nodes']
        if type(number) is not int or not 1 <= number <= len(pages):
            raise ValueError('Path page must be a valid 1-based index.')
        if not isinstance(nodes, list) or len(nodes) < 2 or not all(isinstance(n, str) for n in nodes):
            raise ValueError('Each path needs at least two node ID strings.')
        page = pages[number - 1]
        vertices = {v['id'] for v in page['vertices']}
        edges = {(e['source'], e['target']) for e in page['edges']}
        for node in nodes:
            if node not in vertices:
                errors.append(f'{case.get("name", "path")}: unknown vertex {node}')
        for start, end in zip(nodes, nodes[1:]):
            if (start, end) not in edges:
                errors.append(f'{case.get("name", "path")}: missing edge {start} -> {end}')
    return {'pass': not errors, 'source': str(source.resolve()),
            'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'paths_checked': len(cases), 'errors': errors, 'pages': pages,
            'limit': 'Structure and supplied paths only; does not establish business validity, coverage, or visual quality.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--paths', type=Path)
    args = parser.parse_args()
    try:
        cases = json.loads(args.paths.read_text(encoding='utf-8-sig'))['paths'] if args.paths else []
        report = inspect(args.source, cases)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['pass'] else 2
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        print(json.dumps({'pass': False, 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

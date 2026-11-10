"""Read-only S4 trace/HTML marker checks; never proves behavior or grants a gate."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PureWindowsPath
import re
import sys


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def obj(value, label):
    need(isinstance(value, dict), label + ': object required')
    return value


def items(value, label, nonempty_list=False):
    need(isinstance(value, list), label + ': array required')
    need(not nonempty_list or value, label + ': must not be empty')
    return value


def strings(value, label, required=False):
    result = items(value, label, required)
    need(all(nonempty(x) for x in result), label + ': nonempty strings required')
    need(len(result) == len(set(result)), label + ': duplicate identifier/reference')
    return result


def token(value, label):
    need(nonempty(value) and re.fullmatch(r'[^\s/@]+', value), label + ': stable token required (no whitespace, / or @)')
    return value


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result

    def reject(value):
        raise ValueError('invalid JSON constant: ' + value)

    return obj(json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique,
                          parse_constant=reject), 'spec')


def local_file(root, relative, label):
    need(nonempty(relative), label + ': file path required')
    need(not Path(relative).is_absolute() and not PureWindowsPath(relative).is_absolute()
         and not PureWindowsPath(relative).drive and not PureWindowsPath(relative).root and '\\' not in relative,
         label + ': use a relative / path')
    need('..' not in Path(relative).parts, label + ': parent traversal forbidden')
    target = (root / relative).resolve()
    need(target.is_relative_to(root) and target.is_file(), label + ': missing file or path outside root')
    return target


def entry_file(root, path, label):
    target = Path(path).resolve()
    need(target.is_relative_to(root) and target.is_file(), label + ': file must exist within root')
    return target


class Markers(HTMLParser):
    """Read actual HTML elements, including template content, never script strings."""
    void = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.entries = []
        self.dom_ids = set()
        self.template_serial = 0

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        label = 'HTML line ' + str(line)
        keys = [k for k, _ in attrs]
        need(len(keys) == len(set(keys)), label + ': duplicate attribute')
        data = dict(attrs)
        parent = self.stack[-1] if self.stack else {'pages': [], 'region': None, 'template': False, 'dom_scope': 0}
        if 'id' in data:
            dom_key = (parent['dom_scope'], data['id'])
            need(nonempty(data['id']) and dom_key not in self.dom_ids, label + ': duplicate/empty DOM id')
            self.dom_ids.add(dom_key)
        pages = list(parent['pages'])
        region = parent['region']
        declared_page = data.get('data-ui-page')
        if 'data-ui-page' in data:
            token(declared_page, label + ' page')
            need(not pages or pages == [declared_page], label + ': page nested in a different page')
            pages, region = [declared_page], None
        if 'data-ui-owner' in data:
            owners = strings((data['data-ui-owner'] or '').split(), label + ' owners', True)
            for owner in owners:
                token(owner, label + ' owner')
            need(not pages or set(owners) == set(pages), label + ': explicit page owner conflicts with containing page')
            pages = owners
        if 'data-ui-region-owner' in data:
            owner = token(data['data-ui-region-owner'], label + ' region owner')
            need(region is None or region == owner, label + ': explicit region owner conflicts with containing region')
            region = owner
        template = parent['template'] or tag == 'template'
        dom_scope = parent['dom_scope']
        if tag == 'template':
            # The template element is in its parent's tree; its content is a new DocumentFragment.
            self.template_serial += 1
            dom_scope = self.template_serial
        if 'data-ui-region' in data:
            region = token(data['data-ui-region'], label + ' region')
        if declared_page:
            self.entries.append(('page', declared_page, None, None, template, line, None))
        for attr, kind in [('data-ui-region', 'region'), ('data-ui-control', 'control'), ('data-ui-state', 'state')]:
            if attr not in data:
                continue
            identifiers = strings((data[attr] or '').split(), label + ' states', True) if kind == 'state' else [data[attr]]
            for identifier in identifiers:
                token(identifier, label + ' ' + kind)
            need(pages, label + ': ' + kind + ' has no page owner')
            need(kind != 'control' or region is not None, label + ': control has no region owner')
            for page in pages:
                for identifier in identifiers:
                    self.entries.append((kind, page, identifier, region, template, line, data.get('data-ui-instance')))
        if tag not in self.void:
            self.stack.append({'tag': tag, 'pages': pages, 'region': region, 'template': template, 'dom_scope': dom_scope})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]['tag'] == tag:
                del self.stack[index:]
                break


def check(root, spec_path, html_path):
    root = Path(root).resolve()
    need(root.is_dir(), 'root must be an existing directory')
    spec_path = entry_file(root, spec_path, 'spec')
    html_path = entry_file(root, html_path, 'html')
    spec = read_json(spec_path)
    need(type(spec.get('schema_version')) is int and spec['schema_version'] == 1, 'schema_version must be 1')
    sources, identities = {}, set()
    for index, source in enumerate(items(spec.get('sources'), 'sources', True)):
        label = f'sources[{index}]'
        obj(source, label)
        ref = source.get('ref')
        need(nonempty(ref) and ref.count('@') == 1, label + ': use ID@version')
        identity, version = ref.split('@')
        token(identity, label + ' id'); token(version, label + ' version')
        need(ref not in sources and identity not in identities, label + ': duplicate source id/version; one applicable version per id')
        need(source.get('kind') in {'T02', 'T03', 'T04', 'P04', 'SCN', 'PAGE', 'FUN', 'RULE', 'TASK', 'NFR'}, label + ': unsupported source kind')
        need(nonempty(source.get('locator')), label + ': source locator required')
        path = local_file(root, source.get('path'), label)
        need(isinstance(source.get('sha256'), str) and re.fullmatch(r'[0-9a-f]{64}', source['sha256']), label + ': sha256 required')
        need(digest(path) == source['sha256'], label + ': source hash mismatch (stale source)')
        sources[ref] = source
        identities.add(identity)

    def refs(value, label, kind=None, required=True):
        values = strings(value, label, required)
        for ref in values:
            need(ref in sources, label + ': unknown reference or wrong version: ' + ref)
            need(kind is None or sources[ref]['kind'] == kind, label + ': expected ' + str(kind) + ': ' + ref)
        return values

    scope = obj(spec.get('scope'), 'scope')
    need(scope.get('mode') in {'full', 'partial'}, 'scope.mode must be full or partial')
    need(nonempty(scope.get('reason')), 'scope.reason required')
    scope_pages = set(refs(scope.get('pages'), 'scope.pages', 'PAGE'))
    scope_tasks = set(refs(scope.get('tasks'), 'scope.tasks', 'TASK'))
    if scope['mode'] == 'full':
        need(scope_pages == {r for r, s in sources.items() if s['kind'] == 'PAGE'}, 'full scope must cover all catalog PAGE references')
        need(scope_tasks == {r for r, s in sources.items() if s['kind'] == 'TASK'}, 'full scope must cover all catalog TASK references')
    required, assigned_tasks = {}, set()
    for index, row in enumerate(items(spec.get('requirements'), 'requirements', True)):
        label = f'requirements[{index}]'; obj(row, label)
        page = refs([row.get('page')], label + '.page', 'PAGE')[0]
        need(page in scope_pages and page not in required, label + ': duplicate/out-of-scope page')
        tasks = set(refs(row.get('tasks'), label + '.tasks', 'TASK'))
        need(tasks <= scope_tasks, label + ': task outside scope')
        assigned_tasks |= tasks
        row_refs = set(refs(row.get('source_refs'), label + '.source_refs'))
        region_ids = set(strings(row.get('regions'), label + '.regions', True))
        state_ids = set(strings(row.get('states'), label + '.states', True))
        control_ids = set(strings(row.get('controls'), label + '.controls'))
        for value in region_ids | state_ids | control_ids:
            token(value, label)
        required[page] = {'regions': region_ids, 'states': state_ids, 'controls': control_ids, 'refs': row_refs}
    need(set(required) == scope_pages, 'requirements must cover every in-scope page')
    need(assigned_tasks == scope_tasks, 'requirements leave an in-scope task uncovered')

    pages = {}
    for index, page in enumerate(items(spec.get('pages'), 'pages', True)):
        label = f'pages[{index}]'; obj(page, label)
        ref = refs([page.get('ref')], label + '.ref', 'PAGE')[0]
        need(ref in scope_pages and ref not in pages, label + ': duplicate/out-of-scope page')
        regions, controls, states, used_refs = {}, {}, {}, set()
        for rindex, region in enumerate(items(page.get('regions'), label + '.regions', True)):
            rlabel = f'{label}.regions[{rindex}]'; obj(region, rlabel)
            rid = token(region.get('id'), rlabel)
            need(rid not in regions, rlabel + ': duplicate region id')
            used_refs.update(refs(region.get('source_refs'), rlabel + '.source_refs'))
            regions[rid] = region
            for cindex, control in enumerate(items(region.get('controls'), rlabel + '.controls')):
                clabel = f'{rlabel}.controls[{cindex}]'; obj(control, clabel)
                cid = token(control.get('id'), clabel)
                need(cid not in controls, clabel + ': duplicate control id within page')
                used_refs.update(refs(control.get('source_refs'), clabel + '.source_refs'))
                controls[cid] = rid
        for sindex, state in enumerate(items(page.get('states'), label + '.states', True)):
            slabel = f'{label}.states[{sindex}]'; obj(state, slabel)
            sid = token(state.get('id'), slabel)
            need(sid not in states, slabel + ': duplicate state id')
            used_refs.update(refs(state.get('source_refs'), slabel + '.source_refs'))
            sregions = set(strings(state.get('regions'), slabel + '.regions', True))
            scontrols = set(strings(state.get('controls'), slabel + '.controls'))
            need(sregions <= set(regions), slabel + ': unknown region')
            need(scontrols <= set(controls), slabel + ': unknown control')
            need(all(controls[c] in sregions for c in scontrols), slabel + ': control region outside state coverage')
            states[sid] = sregions
        need(required[ref]['regions'] <= set(regions), label + ': missing required region mapping')
        need(required[ref]['states'] <= set(states), label + ': missing required state mapping')
        need(required[ref]['controls'] <= set(controls), label + ': missing required control mapping')
        need(required[ref]['refs'] <= used_refs, label + ': required source has no region/control/state mapping')
        pages[ref] = {'regions': regions, 'controls': controls, 'states': states}
    need(set(pages) == scope_pages, 'pages mapping must cover every in-scope page')
    by_id = {ref.split('@')[0]: data for ref, data in pages.items()}
    excluded = {'region': set(), 'control': set(), 'state': set()}
    excluded_pages = set()
    for index, row in enumerate(items(scope.get('excluded', []), 'scope.excluded')):
        label = f'scope.excluded[{index}]'; obj(row, label)
        need(scope['mode'] == 'partial', label + ': exclusions require partial scope')
        ref = refs([row.get('page')], label + '.page', 'PAGE')[0]
        need(ref in scope_pages and ref not in excluded_pages, label + ': duplicate/out-of-scope exclusion page')
        excluded_pages.add(ref)
        need(nonempty(row.get('reason')), label + ': reuse reason/version locator required')
        refs(row.get('source_refs'), label + '.source_refs')
        page = ref.split('@')[0]
        mapped = pages[ref]
        for kind, field in [('region', 'regions'), ('control', 'controls')]:
            for identifier in strings(row.get(field), label + '.' + field):
                token(identifier, label + '.' + field)
                need(identifier not in mapped[field], label + ': exclusion overlaps checked ' + kind)
                need(identifier not in required[ref][field], label + ': exclusion cannot hide required ' + kind)
                excluded[kind].add((page, identifier))
        for state in items(row.get('states'), label + '.states'):
            obj(state, label + '.states[]')
            identifier = token(state.get('id'), label + '.states[].id')
            for region in strings(state.get('regions'), label + '.states[].regions', True):
                token(region, label + '.states[].regions')
                need(region not in mapped['states'].get(identifier, set()), label + ': exclusion overlaps checked state/region')
                key = (page, identifier, region)
                need(key not in excluded['state'], label + ': duplicate state exclusion')
                need(region in mapped['regions'] or (page, region) in excluded['region'], label + ': excluded state needs checked or explicitly reused region')
                excluded['state'].add(key)
    parser = Markers()
    parser.feed(html_path.read_text(encoding='utf-8-sig'))
    parser.close()
    observed = {}
    out_of_scope = set()
    unchecked = {'region': set(), 'control': set(), 'state': set()}
    for kind, page, identifier, region, template, line, instance in parser.entries:
        label = f'HTML line {line}'
        if page not in by_id:
            need(scope['mode'] == 'partial', label + ': unknown/out-of-scope page: ' + page)
            out_of_scope.add(page)
            continue
        mapped = by_id[page]
        if kind in unchecked:
            plural = {'region': 'regions', 'control': 'controls', 'state': 'states'}[kind]
            outside = identifier not in mapped[plural]
            outside = outside or (kind == 'state' and region not in mapped['states'].get(identifier, set()))
            if scope['mode'] == 'partial' and outside:
                key = (page, identifier, region) if kind == 'state' else (page, identifier)
                need(key in excluded[kind], label + ': unknown ' + kind + ' is not explicitly excluded/reused: ' + identifier)
                unchecked[kind].add((page, identifier, region or ''))
                continue
        if kind == 'region':
            need(identifier in mapped['regions'], label + ': unknown region: ' + identifier)
        elif kind == 'control':
            need(identifier in mapped['controls'], label + ': unknown control: ' + identifier)
            need(mapped['controls'][identifier] == region, label + ': control attached to wrong region')
        elif kind == 'state':
            need(identifier in mapped['states'], label + ': unknown state: ' + identifier)
            need(region in mapped['states'][identifier], label + ': state attached to wrong/missing region')
        key = (kind, page, identifier, region) if kind == 'state' else (kind, page, identifier)
        entries = observed.setdefault(key, [])
        same_material = [entry for entry in entries if entry['template'] == template]
        if entries and (kind != 'control' or same_material):
            # Repeated row controls can share a semantic id only with distinct instance keys.
            need(kind == 'control' and not template and nonempty(instance)
                 and all(nonempty(e['instance']) and e['instance'] != instance for e in same_material),
                 label + ': duplicate ' + kind + ' marker: ' + str(identifier))
        entries.append({'line': line, 'template': template, 'instance': instance})
    for page, mapped in by_id.items():
        need(('page', page, None) in observed, 'HTML missing page marker: ' + page)
        for kind, field in [('region', 'regions'), ('control', 'controls'), ('state', 'states')]:
            for identifier in mapped[field]:
                if kind == 'state':
                    for region in mapped['states'][identifier]:
                        need((kind, page, identifier, region) in observed,
                             f'HTML missing state marker: {page}/{identifier} in region {region}')
                else:
                    need((kind, page, identifier) in observed, f'HTML missing {kind} marker: {page}/{identifier}')
    template_only = [dict({'kind': key[0], 'page': key[1], 'id': key[2]}, **({'region': key[3]} if key[0] == 'state' else {}))
                     for key, value in observed.items()
                     if all(entry['template'] for entry in value)]
    return {'kind': 'STRUCTURE_ONLY', 'passed': True, 'scope': scope,
            'spec_sha256': digest(spec_path), 'html_sha256': digest(html_path),
            'source_files_checked': len({s['path'] for s in sources.values()}),
            'page_count': len(pages), 'marker_count': len(observed),
            'template_only': template_only,
            'template_marker_occurrences': sum(e['template'] for value in observed.values() for e in value),
            'non_template_marker_occurrences': sum(not e['template'] for value in observed.values() for e in value),
            'unchecked_pages': sorted(out_of_scope),
            'unchecked_regions': [{'page': p, 'id': i} for p, i, _ in sorted(unchecked['region'])],
            'unchecked_controls': [{'page': p, 'id': i, 'region': r} for p, i, r in sorted(unchecked['control'])],
            'unchecked_states': [{'page': p, 'id': i, 'region': r} for p, i, r in sorted(unchecked['state'])],
            'limitations': ['检查源快照、声明引用和 HTML 元素标记；不能证明上游业务清单完整或来源当前有效/已获批准。',
                            '隐藏节点及 template 只证明声明存在；不检查脚本文本中的动态 HTML，不证明实际可见、信息正确、权限生效或任务可完成。',
                            '必须另存同版浏览器实际查看与操作证据；本结果不代替 Q04 语义检查、品牌评审、真人验证或阶段授权。']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--html', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = check(args.root, args.spec, args.html)
    except (ValueError, OSError, RecursionError) as exc:
        result = {'kind': 'STRUCTURE_ONLY', 'passed': False, 'error': str(exc)}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())

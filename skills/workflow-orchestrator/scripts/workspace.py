"""Local product-workflow records. No model calls or automatic business approval.

Run with --help. Payloads are UTF-8 JSON files; paths inside records are workspace-relative.
Only this script writes state.json. Markdown bodies and evidence are immutable snapshots.
"""
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
import review_bundle
import trial_entry

STAGES = ('S1', 'S2', 'S3', 'S4', 'S5')
TYPES = {'SRC', 'RESEARCH', 'PROB', 'T01', 'SCN', 'RULE', 'T02', 'FUN', 'PAGE', 'NFR',
         'T03', 'P04', 'T04', 'TASK', 'REQ', 'AC', 'T05'}
OWNERS = {'RESEARCH': 'S1', 'PROB': 'S1', 'T01': 'S1', 'SCN': 'S2', 'RULE': 'S2', 'T02': 'S2',
          'FUN': 'S3', 'PAGE': 'S3', 'NFR': 'S3', 'T03': 'S3', 'P04': 'S4',
          'T04': 'S4', 'TASK': 'S4', 'REQ': 'S5', 'AC': 'S5', 'T05': 'S5'}
MANAGEMENT = '06-project-management'
STAGE_DIRS = dict(zip(STAGES, ('01-discovery', '02-business-modeling',
    '03-product-solution', '04-prototype-validation', '05-prd-review')))
ARTIFACT_DIRS = {'RESEARCH': 'competitor-research', 'T01': 'requirements', 'T02': 'models', 'T03': 'specifications',
    'P04': 'prototypes', 'T04': 'validation', 'T05': 'prd'}
CHINESE_NAMES = {
    '00-project-basics': '00-项目资料', '01-discovery': '01-需求澄清',
    '02-business-modeling': '02-业务建模', '03-product-solution': '03-产品方案',
    '04-prototype-validation': '04-原型验证', '05-prd-review': '05-PRD交付',
    MANAGEMENT: '06-项目管理', 'original-inputs': '原始资料', 'references': '参考资料',
    'competitor-research': '竞品调研', 'analysis': '需求分析', 'requirements': '需求定义',
    'models': '业务模型', 'diagrams': '业务图表', 'specifications': '产品规格',
    'prototypes': '交互原型', 'validation': '验证记录', 'prd': 'PRD文档',
    'deliveries': '交付包', 'records': '成果记录', 'evidence': '证据资料',
    'project-info.md': '项目基本信息.md', 'project-status.md': '项目状态.md',
    'project-versions.md': '项目版本记录.md', 'artifact-versions.md': '成果版本清单.md',
    'changes.md': '变更记录.md', 'impact-analysis.md': '影响分析记录.md',
    'handoffs.md': '阶段交接记录.md', 'pending-decisions.md': '待决事项.md',
    'quality-checks.md': '质量检查记录.md',
    'delivery-checks.md': '交付验收记录.md',
}


def state_candidates(root):
    return [local(root, name) for name in (CHINESE_NAMES[MANAGEMENT] + '/state.json',
                                         MANAGEMENT + '/state.json', 'state.json')]


def generated_path(root, relative):
    """Name newly generated files; never translate paths persisted in records."""
    found = [path for path in state_candidates(root) if path.is_file()]
    need(len(found) <= 1, 'Multiple state files found; resolve the ambiguous project before writing.')
    # An existing English v2 workspace continues in place, including future versions.
    # New workspaces and legacy migrations use Chinese names without rewriting old refs.
    if found and found[0].parent.name == MANAGEMENT:
        return relative
    # Only the layout root and its section/view name are localized. The remaining
    # tail contains immutable item IDs and filenames, including IDs such as "records".
    return '/'.join(CHINESE_NAMES.get(part, part) if index < 2 else part
                    for index, part in enumerate(relative.split('/')))


def state_path(root):
    found = [path for path in state_candidates(root) if path.is_file()]
    need(len(found) <= 1, 'Multiple state files found; inspect interrupted migration or manual renaming.')
    need(found, 'Workspace not initialized.')
    return found[0]


def discover(root, max_depth=4):
    """Bounded local discovery; symlinks and hidden/build/test trees are not followed."""
    need(root.is_dir(), 'Discovery root does not exist.')
    projects, errors = [], []
    def walk(folder, depth):
        candidates = state_candidates(folder)
        found = [p for p in candidates if p.is_file()]
        if found:
            try:
                need(len(found) == 1, 'Multiple state files; inspect migration or manual renaming.')
                data = read(found[0])
                need('product' in data and 'items' in data, 'Not a product workspace state.')
                projects.append({'root': str(folder), 'product': data['product'],
                    'schema_version': data.get('schema_version'),
                    'layout': 'legacy' if found[0].parent == folder else 'v2',
                    'directory_language': 'legacy' if found[0].parent == folder else
                        'zh' if found[0].parent.name == CHINESE_NAMES[MANAGEMENT] else 'en',
                    'state_path': str(found[0])})
            except (ValueError, OSError, KeyError) as exc:
                errors.append({'root': str(folder), 'error': str(exc)})
            return
        if depth >= max_depth:
            return
        for child in sorted(folder.iterdir()):
            if child.is_dir() and not child.is_symlink() and not child.name.startswith('.') and child.name not in (
                    'node_modules', 'backups', 'tests', '备份', '测试', '__pycache__') and '-migration-backup-' not in child.name:
                walk(child, depth + 1)
    walk(root, 0)
    return {'status': 'none' if not projects else 'unique' if len(projects) == 1 else 'multiple',
            'projects': projects, 'errors': errors, 'max_depth': max_depth,
            'action': 'repair_invalid_state' if errors else 'confirm_name_and_location' if not projects else
                      'resume' if len(projects) == 1 else 'ask_user_to_select'}


def layout(root):
    for relative in ('00-project-basics/original-inputs', '00-project-basics/references',
            '01-discovery/competitor-research', '01-discovery/analysis', '01-discovery/requirements',
            '02-business-modeling/models', '02-business-modeling/diagrams',
            '03-product-solution/specifications', '04-prototype-validation/prototypes',
            '04-prototype-validation/validation', '05-prd-review/prd', '05-prd-review/deliveries',
            MANAGEMENT + '/evidence'):
        local(root, generated_path(root, relative)).mkdir(parents=True, exist_ok=True)


def historical(state, identifier, version):
    item = ref(state, identifier)
    if item['version'] == version:
        return item
    for old in item.get('history', []):
        if old['version'] == version:
            return effective_authority(state, old)
    raise ValueError(f'Unknown historical version: {identifier}@{version}')


def effective_authority(state, item):
    """Overlay append-only rechecks; original historical records stay untouched."""
    rows = [row for row in state.get('authority_rechecks', [])
            if row['id'] == item['id'] and row['version'] == item['version']]
    if not rows:
        return item
    effective = copy.deepcopy(item)
    for row in rows:
        record = copy.deepcopy(row['record'])
        if record['category'] == 'V':
            effective['checks']['V'] = record
        elif record['category'] == 'approval':
            effective['approvals'][record['role']] = record
        else:
            effective['validation'] = record
    effective['authority_rechecks'] = copy.deepcopy(rows)
    return effective


def now():
    return datetime.now(timezone.utc).isoformat()


def need(condition, message):
    if not condition:
        raise ValueError(message)


def slug(value):
    need(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value),
         'Identifier must use letters, numbers, underscores or hyphens (1-64).')
    return value


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(root, value):
    need(isinstance(value, str) and value, 'Missing relative path.')
    relative = Path(value)
    need(not relative.is_absolute(), 'Workspace records require relative paths.')
    path = (root / relative).resolve()
    need(path.is_relative_to(root.resolve()), 'Path escapes workspace.')
    return path


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def atomic(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def atomic_text(path, text):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(text, encoding='utf-8')
    os.replace(temp, path)


@contextmanager
def transaction(root):
    path = state_path(root)
    need(path.parent != root, 'Legacy project is read-only; run migrate first.')
    lock = path.parent / '.write-lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError('Workspace is being written. Retry after the writer ends; do not remove a live lock.')
    try:
        os.close(fd)
        state = read(path)
        need(state.get('schema_version') == 2, 'Unsupported schema version.')
        before = copy.deepcopy(state)
        with ExitStack() as rollback:
            yield state, rollback
            if state != before:
                state['revision'] += 1
                atomic(path, state)
            rollback.pop_all()
        # Derived views are repairable; state.json remains the sole metadata source.
        if state != before:
            render_views(root, state)
    finally:
        lock.unlink(missing_ok=True)


def event(state, kind, data):
    state['events'].append({'at': now(), 'kind': kind, **data})


def ref(state, identifier, version=None):
    need(identifier in state['items'], f'Unknown item: {identifier}')
    item = state['items'][identifier]
    if version is not None:
        need(item['version'] == version, f'Stale reference: {identifier}@{version}; current={item["version"]}')
    return item


def evidence(root, value):
    need(isinstance(value, dict), 'Evidence must be an object.')
    need(value.get('kind') in ('source', 'human_reply', 'operation', 'user_observation', 'review'),
         'Evidence kind must identify a real source, reply, operation, observation or review.')
    need(bool(value.get('locator')), 'Evidence requires a locator (paragraph, line, task or timestamp).')
    path = local(root, value.get('path'))
    need(path.is_file(), f'Evidence missing: {path}')
    return {**value, 'sha256': digest(path)}


def evidence_ok(root, value):
    try:
        path = local(root, value['path'])
        return path.is_file() and digest(path) == value['sha256']
    except (ValueError, KeyError):
        return False


def snapshot(root, state, source):
    source = Path(source).resolve()
    need(source.is_file(), 'Snapshot input must be a file.')
    name = digest(source) + source.suffix.lower()
    dest = local(root, generated_path(root, '00-project-basics/original-inputs/' + name))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copyfile(source, dest)
    need(digest(dest) == digest(source), 'Existing snapshot was modified; refusing to reuse it.')
    result = {'path': dest.relative_to(root).as_posix(), 'sha256': digest(dest),
              'original_path': str(source), 'captured_at': now()}
    event(state, 'snapshot', result)
    return result


def init(root, product):
    need(isinstance(product, str) and product.strip(), 'Project name required.')
    need(not any(path.exists() for path in state_candidates(root)),
         'Workspace already exists; use resume or migrate.')
    if root.exists():
        found = discover(root)
        need(not found['projects'] and not found['errors'], 'Existing or invalid project found; do not initialize over it.')
    root.mkdir(parents=True, exist_ok=True)
    layout(root)
    state = {'schema_version': 2, 'product': product, 'revision': 0,
             'requirements': {}, 'items': {}, 'questions': {}, 'events': [], 'deliveries': [],
             'impacts': [], 'handoffs': []}
    # Exclusive creation prevents accidentally replacing an existing workspace.
    relative_state = generated_path(root, MANAGEMENT + '/state.json')
    with local(root, relative_state).open('x', encoding='utf-8') as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
    info = local(root, generated_path(root, '00-project-basics/project-info.md'))
    if not info.exists():
        info.write_text(f'# 项目基本信息\n\n项目名称：{product}\n\n责任人按实际确认登记。原始输入不得修改。\n', encoding='utf-8')
    render_views(root, state)
    return {'workspace': str(root), 'product': product, 'state_path': relative_state}


def checked_plan(state, plan, target):
    need(set(plan) == set(STAGES), 'Plan must explain all five stages.')
    plan = copy.deepcopy(plan)
    for stage, choice in plan.items():
        need(choice.get('mode') in ('execute', 'reuse', 'not_applicable') and choice.get('reason'),
             f'{stage}: mode and reason required.')
        if choice['mode'] == 'reuse':
            ids = choice.get('items')
            need(isinstance(ids, list) and ids and len(ids) == len(set(ids)), f'{stage}: reuse requires unique item IDs.')
            versions = {}
            for key in ids:
                item = ref(state, key)
                need(item['target'] == target, f'{stage}: reused item target mismatch: {key}')
                need(item['stage'] == stage, f'{stage}: reused item belongs to another stage: {key}')
                need(item.get('current_valid_version') == item['version'], f'{stage}: reused item is not effective: {key}')
                need(not authority_problems(state, item), f'{stage}: reused item authority requires review: {key}')
                versions[key] = item['version']
            need(choice.get('versions', versions) == versions, f'{stage}: reused versions changed; review and replan.')
            choice['versions'] = versions
    return plan


def new(state, data):
    identifier = slug(data['id'])
    need(identifier not in state['requirements'], 'Requirement already exists.')
    plan = checked_plan(state, data.get('plan', {}), data['target'])
    roles = data.get('roles', {})
    validate_roles(roles)
    state['requirements'][identifier] = {'id': identifier, 'title': data['title'],
        'target': data['target'], 'roles': roles, 'plan': plan, 'next_action': data.get('next_action', 'S1'),
        'status': 'draft'}
    event(state, 'new_requirement', {'id': identifier})
    return state['requirements'][identifier]


def validate_roles(roles):
    need(isinstance(roles, dict), 'Roles must be a dictionary.')
    need(all(isinstance(values, list) and all(isinstance(name, str) and name.strip() for name in values)
             for values in roles.values()), 'Each role must contain a list of actual names.')


def configure(state, data):
    req = state['requirements'][data['requirement']]
    need(data.get('reason'), 'Configuration change requires reason.')
    validate_roles(data['roles'])
    old = copy.deepcopy(req['roles'])
    # Order, duplicates and empty role lists do not change anyone's authority.
    memberships = lambda roles: {role: set(names) for role, names in roles.items() if names}
    if memberships(old) == memberships(data['roles']):
        return req
    before_items = {key: set(authority_problems(state, item)) for key, item in state['items'].items()}
    before_handoffs = [set(handoff_authority_problems(state, row)) for row in state.get('handoffs', [])]
    req['roles'] = copy.deepcopy(data['roles'])
    affected = {key: sorted(set(authority_problems(state, item)) - before_items[key])
                for key, item in state['items'].items()}
    affected_handoffs = [{'requirement': row['requirement'], 'from_stage': row['from_stage'],
                         'at': row.get('at'), 'errors': errors}
                        for row, before in zip(state.get('handoffs', []), before_handoffs)
                        if (errors := sorted(set(handoff_authority_problems(state, row)) - before))]
    # Authority is rechecked dynamically, including references reused by other
    # requirements. Neither changed membership nor a new approver changes content.
    event(state, 'configure', {**data, 'before': old,
                              'authority_rechecks': {key: errors for key, errors in affected.items() if errors},
                              'handoff_rechecks': affected_handoffs})
    return req


def authority_problems(state, item, visited=None):
    """Current membership checks, kept separate from content/version validity."""
    item = effective_authority(state, item)
    visited = set() if visited is None else visited
    node = (item['id'], item['version'])
    if node in visited:
        return []
    visited = visited | {node}
    roles = state['requirements'][item['requirement']]['roles']
    errors = []
    check = item.get('checks', {}).get('V', {})
    if check.get('result') == 'pass' and check.get('method') == 'human_review':
        if not any(check.get('actor') in members for members in roles.values()):
            errors.append(f'{item["id"]}: reviewer authority changed')
        delegation = check.get('delegation')
        if item['type'] in ('RULE', 'T02'):
            responsible = delegation.get('by') if isinstance(delegation, dict) else check.get('actor')
            if responsible not in roles.get('business', []):
                errors.append(f'{item["id"]}: business review authority changed')
    for role in item.get('decision_roles', []):
        approval = item.get('approvals', {}).get(role, {})
        if approval.get('result') == 'approved' and approval.get('actor') not in roles.get(role, []):
            errors.append(f'{item["id"]}: {role} approval authority changed')
    validation = item.get('validation', {})
    if validation.get('result') == 'waived' and validation.get('actor') not in roles.get('product', []):
        errors.append(f'{item["id"]}: user-validation waiver authority changed')
    for link in item.get('refs', []):
        try:
            upstream = historical(state, link['id'], link['version'])
        except ValueError:
            continue  # Missing content references are reported by problems().
        errors.extend(authority_problems(state, upstream, visited))
    return sorted(set(errors))


def handoff_authority_problems(state, row):
    roles = state['requirements'].get(row['requirement'], {}).get('roles', {})
    errors = [] if row.get('actor') in roles.get('product', []) else ['Product authority changed.']
    for version in row.get('versions', []):
        try:
            item = historical(state, version['id'], version['version'])
        except ValueError:
            continue
        errors.extend(authority_problems(state, item))
    return sorted(set(errors))


def replan(state, data):
    req = state['requirements'][data['requirement']]
    need(data.get('reason'), 'Replanning requires an impact reason.')
    plan = checked_plan(state, data['plan'], req['target'])
    before = copy.deepcopy(req['plan'])
    changed = {stage for stage in STAGES if plan[stage] != before[stage]}
    affected = [item['id'] for item in state['items'].values()
                if item['requirement'] == req['id'] and item['stage'] in changed]
    req['plan'] = plan
    if affected:
        invalidate(state, affected, data['reason'])
    if changed:
        req['status'] = 'needs_review'
    event(state, 'replan', {'before': before, **copy.deepcopy(data)})
    return {'requirement': req['id'], 'changed_stages': sorted(changed), 'affected': affected}


def dependents(state, identifiers):
    reached = set(identifiers)
    while True:
        more = {key for key, item in state['items'].items()
                if any(r['id'] in reached for r in item['refs'])}
        if more <= reached:
            return reached
        reached |= more


def invalidate(state, identifiers, reason):
    affected = dependents(state, identifiers)
    for identifier in affected:
        item = state['items'][identifier]
        item['validity'] = 'needs_update'
        item['current_valid_version'] = None
        item.pop('held_valid_version', None)
        item['stale_reason'] = reason
    # Delivered snapshots remain historical facts; current live baseline needs review.
    for req in state['requirements'].values():
        if any(state['items'][key]['requirement'] == req['id'] for key in affected):
            req['status'] = 'needs_review'
    return sorted(affected)


def pending_impacts(state, source, reason):
    affected = dependents(state, [source['id']]) - {source['id']}
    for key in sorted(affected):
        target = ref(state, key)
        target.setdefault('held_valid_version', target.get('current_valid_version'))
        target['current_valid_version'] = None
        for previous in state['impacts']:
            if previous['source_id'] == source['id'] and previous['target_id'] == key and previous['status'] == 'pending':
                previous['status'] = 'superseded_by_source_revision'
                previous['superseded_by_source_version'] = source['version']
        state['impacts'].append({'source_id': source['id'], 'source_version': source['version'],
            'target_id': key, 'target_version': target['version'], 'status': 'pending',
            'reason': reason, 'created_at': now()})
        state['requirements'][target['requirement']]['status'] = 'needs_review'
    return sorted(affected)


def impact(root, state, data):
    source = ref(state, data['source_id'], data['source_version'])
    target = ref(state, data['target_id'])
    rows = [row for row in state['impacts'] if row['source_id'] == source['id'] and
            row['source_version'] == source['version'] and row['target_id'] == target['id'] and
            row['target_version'] == target['version'] and row['status'] == 'pending']
    need(rows, 'No pending impact for these current versions.')
    need(data.get('result') in ('affected', 'unaffected'), 'Impact result must be affected/unaffected.')
    need(data.get('reason') and data.get('actor'), 'Impact needs actor and explanation.')
    proof = evidence(root, data['evidence'])
    need(proof['kind'] in ('source', 'human_reply', 'review', 'operation'), 'Impact evidence is not applicable.')
    if data['result'] == 'unaffected':
        need(target.get('held_valid_version') == target['version'] and target['validity'] == 'valid',
             'No-impact may preserve an existing effective version, not approve a draft or invalid item.')
    for row in rows:
        row.update({'status': data['result'], 'reason': data['reason'], 'actor': data['actor'],
                    'evidence': proof, 'resolved_at': now()})
    if data['result'] == 'affected':
        target['validity'] = 'needs_update'
        target['current_valid_version'] = None
        target['stale_reason'] = data['reason']
        target.pop('held_valid_version', None)
    elif not any(row['target_id'] == target['id'] and row['target_version'] == target['version'] and
                 row['status'] == 'pending' for row in state['impacts']):
        target['current_valid_version'] = target.pop('held_valid_version', None)
    event(state, 'impact', copy.deepcopy(rows[-1]))
    return rows[-1]


def stage_review_problems(root, item):
    return review_bundle.registered_problems(root, item)


def put(root, state, data, rollback):
    requirement = state['requirements'][data['requirement']]
    kind = data['type']
    need(kind in TYPES, 'Unsupported item type.')
    stage = data.get('stage', OWNERS.get(kind))
    need(stage in STAGES and (kind not in OWNERS or OWNERS[kind] == stage), 'Invalid owning stage.')
    identifier = data.get('id')
    if not identifier:
        prefix = requirement['id'] + '-' + kind + '-'
        numbers = [int(i[len(prefix):]) for i in state['items']
                   if i.startswith(prefix) and i[len(prefix):].isdigit()]
        identifier = prefix + f'{max(numbers, default=0) + 1:03d}'
    slug(identifier)
    old = state['items'].get(identifier)
    need(data.get('expected_version', 0) == (old['version'] if old else 0), 'Concurrent or stale edit.')
    if old:
        need(old['requirement'] == requirement['id'] and old['type'] == kind, 'Item identity cannot change.')
        need(bool(data.get('change_reason')), 'Updates require change_reason.')
        need(kind != 'T05' or not old.get('review_bundle') or 'review_bundle' in data,
             'This T05 uses PRD/SRS review_bundle; include both documents in the new version.')
    refs = data.get('refs', [])
    need(isinstance(refs, list), 'refs must be a list.')
    for link in refs:
        upstream = historical(state, link['id'], link['version'])
        need(upstream['target'] == requirement['target'], 'Cross-target references require a separate versioned item.')
        need(link['id'] != identifier and link['id'] not in dependents(state, [identifier]), 'Dependency cycle.')
    need(kind == 'SRC' or refs, 'Non-source items require at least one source or upstream reference.')
    body_file = Path(data['body_file']).resolve()
    body = body_file.read_text(encoding='utf-8-sig')
    need(body.strip(), 'Empty body.')
    title = data['title']
    decisions = data.get('decision_roles', old.get('decision_roles', []) if old else [])
    need(isinstance(decisions, list) and all(role in ('business', 'product', 'delivery') for role in decisions),
         'Unknown decision role.')
    required = sorted(set(decisions + (['business'] if kind == 'RULE' else ['product'] if kind == 'T01' else [])))
    need(not any('review_role' in e for e in data.get('evidence', [])),
         'Use review_bundle.files to register a review role.')
    attachments = [evidence(root, entry) for entry in data.get('evidence', [])]
    need(kind != 'SRC' or attachments, 'Source requires a captured evidence file and locator.')
    version = (old['version'] if old else 0) + 1
    section = ARTIFACT_DIRS.get(kind, 'analysis' if stage == 'S1' else 'records')
    path = local(root, generated_path(root, f'{STAGE_DIRS[stage]}/{section}/{identifier}/v{version}.md'))
    bundle = None
    if 'review_bundle' in data:
        spec = data['review_bundle']
        body_name, members, labels = review_bundle.entries(kind, spec, body_file)
        destination = path.with_suffix('')
        review_bundle.write_version(destination, members, rollback)
        path = destination / body_name
        bundle = {'root': destination.relative_to(root).as_posix()}
        if 'layout_heading' in spec:
            bundle['layout_heading'] = spec['layout_heading']
        for name, (role, locator) in labels.items():
            attachments.append({'path': (destination / name).relative_to(root).as_posix(),
                                'locator': locator, 'kind': 'operation' if role == 'operations' else 'source',
                                'sha256': hashlib.sha256(members[name]).hexdigest(), 'review_role': role})
    else:
        if kind == 'P04':
            review_bundle.validate_p04_snapshot(root, path.relative_to(root).as_posix(), body.encode('utf-8'), attachments)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            need(path.read_text(encoding='utf-8') == body, 'Uncommitted snapshot exists; inspect it before retrying.')
        else:
            with path.open('x', encoding='utf-8') as stream:
                rollback.callback(path.unlink, missing_ok=True)
                stream.write(body)
    item = {'id': identifier, 'requirement': requirement['id'], 'type': kind, 'stage': stage,
            'title': title, 'target': requirement['target'], 'version': version,
            'path': path.relative_to(root).as_posix(), 'sha256': digest(path), 'refs': refs,
            'evidence': attachments, 'decision_roles': required,
            'validity': 'draft', 'checks': {}, 'approvals': {}, 'updated_at': now(),
            'latest_version': version, 'current_valid_version': None,
            'last_approved_version': old.get('last_approved_version') if old else None}
    if bundle:
        item['review_bundle'] = bundle
    if old:
        item['history'] = old.get('history', []) + [{k: copy.deepcopy(v) for k, v in old.items() if k != 'history'}]
    state['items'][identifier] = item
    # A revision replaces the pending target, while retaining its old analysis as history.
    for row in state['impacts']:
        if row['target_id'] == identifier and row['target_version'] != version and row['status'] == 'pending':
            row['status'] = 'superseded_by_revision'
    affected = pending_impacts(state, item, data['change_reason']) if old else []
    if old:
        state['requirements'][item['requirement']]['status'] = 'needs_review'
    event(state, 'put', {'id': identifier, 'version': version, 'affected': affected,
                        'reason': data.get('change_reason', 'New item')})
    return {'id': identifier, 'version': version, 'affected': affected, 'path': item['path']}


def human_review_problem(root, item, roles, check, *, check_authority=True):
    actor = check.get('actor')
    if check_authority and not any(actor in members for members in roles.values()):
        return 'Reviewer not registered.'
    delegation = check.get('delegation')
    if delegation is None:
        if check_authority and item['type'] in ('RULE', 'T02') and actor not in roles.get('business', []):
            return 'Business review requires the responsible person or their evidenced delegation for this item version.'
        return None
    if not isinstance(delegation, dict) or item['type'] not in ('RULE', 'T02'):
        return 'Invalid business review delegation.'
    if ((check_authority and delegation.get('by') not in roles.get('business', [])) or delegation.get('to') != actor
            or delegation.get('id') != item['id'] or type(delegation.get('version')) is not int
            or delegation['version'] != item['version']):
        return 'Business review delegation does not cover this reviewer and item version.'
    proof = delegation.get('evidence')
    if (not isinstance(proof, dict) or proof.get('kind') not in ('review', 'human_reply', 'source')
            or not evidence_ok(root, proof)):
        return 'Business review delegation evidence is missing or has changed.'
    return None


def missing_draft_closure(item):
    check = item.get('checks', {}).get('I', {})
    return (item['type'] == 'T02' and check.get('result') == 'pass' and 'closure' not in check
            and item.get('last_approved_version') != item['version'] and item['validity'] != 'valid')


def check_business_closure(root, check):
    """Match the critical journeys declared in a T02 check to actual rows in its operation log."""
    closure = check.get('closure')
    need(isinstance(closure, dict), 'T02 I pass requires closure cases tied to operation evidence.')
    cases = closure.get('cases')
    need(isinstance(cases, list) and cases, 'T02 closure needs at least one tested journey.')
    proof = check['evidence']
    need(proof.get('kind') == 'operation', 'T02 closure requires a UTF-8 operation log.')
    lines = local(root, proof['path']).read_text(encoding='utf-8-sig').splitlines()
    tested = set()
    for index, case in enumerate(cases, 1):
        label = f'T02 closure case {index}'
        need(isinstance(case, dict), f'{label}: expected a case object.')
        fields = ('kind', 'source', 'object', 'expected', 'status')
        need(all(isinstance(case.get(k), str) and case[k].strip() for k in fields),
             f'{label}: kind, source, object, expected and status are required.')
        kind = case['kind']
        need(kind in ('handoff', 'cross_entry', 'single'), f'{label}: unknown journey kind.')
        need(case['status'] == 'passed', f'{label}: unresolved or untested journey cannot support I pass.')
        steps = case.get('steps')
        need(isinstance(steps, list) and steps, f'{label}: no observed steps.')
        previous = 0
        transfers = []
        for step in steps:
            need(isinstance(step, dict), f'{label}: expected a step object.')
            keys = ('actor', 'entry', 'action', 'observed')
            need(all(isinstance(step.get(k), str) and step[k].strip() for k in keys),
                 f'{label}: each step needs actor, entry, action and observed result.')
            number = step.get('line')
            need(type(number) is int and previous < number <= len(lines),
                 f'{label}: cite distinct log lines in execution order.')
            previous = number
            row = lines[number - 1].strip()
            cells = row.split('\t') if '\t' in row else row.strip('|').split('|')
            values = [case['object'], *(step[k] for k in keys)]
            need([c.strip() for c in cells[:5]] == values,
                 f'{label}: line {number} does not match object, actor, entry, action and observation.')
            if 'to' in step:
                recipient = step['to']
                need(isinstance(recipient, str) and recipient.strip() and recipient != step['actor']
                     and (recipient in step['observed'] or recipient in [c.strip() for c in cells[5:]]),
                     f'{label}: line {number} must identify the receiving actor.')
                transfers.append((number, recipient))
        need(steps[-1]['observed'] == case['expected'], f'{label}: observed endpoint differs from expected.')
        if kind == 'handoff':
            need(transfers, f'{label}: identify each handoff with the sending step and its recipient (to).')
        for line, recipient in transfers:
            need(any(s['line'] > line and s['actor'] == recipient for s in steps),
                 f'{label}: {recipient} did not act on this object after line {line}.')
        if transfers:
            tested.add('handoff')
        if kind == 'cross_entry':
            need(len({s['entry'] for s in steps}) >= 2, f'{label}: missing the second entry on this object.')
        tested.add(kind)
    missing = {'handoff', 'cross_entry'} - tested
    reasons = closure.get('not_applicable', {})
    need(isinstance(reasons, dict) and set(reasons) == missing
         and all(isinstance(reason, str) and reason.strip() for reason in reasons.values()),
         'T02 closure: test applicable handoffs and cross-entry cases; explain each inapplicable kind.')


def historical_authority_target(root, state, data):
    """Only reauthorize exact historical content still used by valid current scope."""
    need(data.get('historical_authority_recheck') is True and data.get('reason'),
         'Historical authority recheck requires explicit historical_authority_recheck=true and reason.')
    need(type(data['version']) is int and data['version'] > 0, 'Historical authority recheck requires an exact integer version.')
    allowed = {'id', 'version', 'category', 'actor', 'result', 'criteria', 'conclusion', 'evidence',
               'method', 'independence', 'delegation', 'role', 'risk_reason', 'scope',
               'historical_authority_recheck', 'reason'}
    need(set(data) <= allowed, 'Historical authority recheck cannot change content, refs or other item fields.')
    item = historical(state, data['id'], data['version'])
    roles = state['requirements'][item['requirement']]['roles']
    category = data['category']
    previous = None
    if category == 'V' and data.get('method') == 'human_review' and data.get('result') == 'pass':
        previous = item.get('checks', {}).get('V', {})
        need(previous.get('result') == 'pass' and previous.get('method') == 'human_review'
             and human_review_problem(root, item, roles, previous), 'Historical V review has no revoked authority to recheck.')
    elif category == 'approval' and data.get('result') == 'approved':
        role = data.get('role')
        previous = item.get('approvals', {}).get(role, {})
        need(role in item['decision_roles'] and previous.get('result') == 'approved'
             and previous.get('actor') not in roles.get(role, []), 'Historical approval has no revoked authority to recheck.')
    elif category == 'validation' and data.get('result') == 'waived':
        previous = item.get('validation', {})
        need(previous.get('result') == 'waived' and previous.get('actor') not in roles.get('product', []),
             'Historical waiver has no revoked authority to recheck.')
    else:
        raise ValueError('Historical authority recheck only permits passing human V review, approval or waiver.')
    target = (item['id'], item['version'])
    memo = {}
    for anchor in state['items'].values():
        version = anchor.get('current_valid_version')
        if not version or problems(root, state, anchor['id'], version=version, _memo=memo, check_authority=False):
            continue
        pending, seen = [(anchor['id'], version)], set()
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            seen.add(node)
            if node == target:
                return copy.deepcopy(item), copy.deepcopy(previous)
            pending.extend((link['id'], link['version']) for link in historical(state, *node)['refs'])
    raise ValueError('Historical version is not used by a currently valid content scope with applicable impact evidence.')


def record(root, state, data):
    current = ref(state, data['id'])
    historical_recheck = data['version'] != current['version']
    if historical_recheck:
        item, previous = historical_authority_target(root, state, data)
    else:
        need(not data.get('historical_authority_recheck'), 'Historical authority recheck requires an older exact version.')
        item = current
    category = data['category']
    need(category in ('I', 'V', 'approval', 'validation'), 'Unknown record category.')
    need(data.get('actor') and data.get('conclusion'), 'Actor and conclusion required.')
    proof = evidence(root, data['evidence'])
    result = {**data, 'evidence': proof, 'recorded_at': now()}
    roles = state['requirements'][item['requirement']]['roles']
    if 'delegation' in data:
        delegation = data['delegation']
        need(category == 'V' and data.get('method') == 'human_review' and isinstance(delegation, dict)
             and item['type'] in ('RULE', 'T02'), 'Delegation applies only to a RULE/T02 human review.')
        result['delegation'] = {**delegation, 'evidence': evidence(root, delegation.get('evidence'))}
    if category == 'I':
        need(data.get('result') in ('pass', 'fail'), 'I result must be pass/fail.')
        need(data.get('criteria'), 'I requires checked criteria and locatable evidence.')
        if item['type'] == 'T02' and data['result'] == 'pass':
            check_business_closure(root, result)
        item['checks']['I'] = result
    elif category == 'V':
        need(data.get('result') in ('pass', 'fail'), 'V result must be pass/fail.')
        need(data.get('method') in ('human_review', 'actual_operation', 'source_cross_check'), 'V method missing.')
        need(data.get('independence') and data.get('criteria'), 'V requires independence limits and criteria.')
        if data['method'] == 'human_review':
            need(proof['kind'] in ('review', 'human_reply'), 'Human review requires review/reply evidence.')
            problem = human_review_problem(root, item, roles, result)
            need(problem is None, problem)
        else:
            need(proof['kind'] in ('operation', 'source', 'user_observation'), 'Evidence incompatible with V method.')
            need(item['type'] not in ('RULE', 'T01', 'T02', 'T05'), 'This item needs responsible human review.')
        item['checks']['V'] = result
    elif category == 'approval':
        role = data['role']
        need(role in ('business', 'product', 'delivery'), 'Unknown authority role.')
        need(data['actor'] in roles.get(role, []), 'Actor lacks registered authority.')
        need(proof['kind'] in ('human_reply', 'review', 'source'), 'Approval needs actual human/source evidence.')
        need(data.get('result') in ('approved', 'rejected'), 'Approval result must be approved/rejected.')
        item['approvals'][role] = result
    else:
        need(item['type'] in ('P04', 'T04'), 'Validation must bind to prototype or validation report.')
        status = data.get('result')
        need(status in ('verified', 'waived', 'pending'), 'Unknown validation result.')
        if status == 'verified':
            need(proof['kind'] == 'user_observation' and data.get('tasks') and data.get('participant_role'),
                 'Verified needs real user task observations.')
        if status == 'waived':
            need(data['actor'] in roles.get('product', []) and proof['kind'] in ('human_reply', 'review'),
                 'Waiver needs authorized product owner and actual reply.')
            need(data.get('risk_reason') and data.get('scope'), 'Waiver scope/risk reason missing.')
        item['validation'] = result
    if historical_recheck:
        row = {'id': item['id'], 'version': item['version'], 'record': result,
               'previous_record': previous, 'at': now()}
        state.setdefault('authority_rechecks', []).append(row)
        event(state, 'historical_authority_recheck', copy.deepcopy(row))
        return {'id': item['id'], 'version': item['version'], 'category': category,
                'saved': True, 'historical_authority_recheck': True}
    event(state, 'record', {'id': item['id'], 'version': item['version'], 'record': result})
    if data.get('result') in ('rejected', 'fail', 'pending'):
        invalidate(state, [item['id']], 'Check/decision/validation requires resolution.')
    elif item.get('stale_reason') == 'Check/decision/validation requires resolution.':
        item['validity'] = 'draft'
        item.pop('stale_reason', None)
    return {'id': item['id'], 'category': category, 'saved': True}


def problems(root, state, identifier, visited=None, version=None, historical_ok=False, _memo=None, *, check_authority=True):
    visited = set() if visited is None else visited
    memo = {} if _memo is None else _memo
    item = historical(state, identifier, version) if version is not None else ref(state, identifier)
    node = (identifier, item['version'])
    if node in visited:
        return [f'{identifier}: dependency cycle']
    key = (*node, historical_ok, check_authority)
    if key in memo:
        return list(memo[key])
    visited = visited | {node}
    errors = []
    if item['validity'] == 'needs_update' and not historical_ok:
        errors.append(f'{identifier}: needs update')
    if not historical_ok:
        for row in state.get('impacts', []):
            if row['target_id'] == identifier and row['target_version'] == item['version']:
                if row['status'] == 'pending':
                    errors.append(f'{identifier}: pending impact from {row["source_id"]}@{row["source_version"]}')
                elif row['status'] == 'unaffected' and not evidence_ok(root, row['evidence']):
                    errors.append(f'{identifier}: no-impact evidence missing or changed')
    if not evidence_ok(root, {'path': item['path'], 'sha256': item['sha256']}):
        errors.append(f'{identifier}: body missing or edited outside maintenance tool')
    for proof in item['evidence']:
        if not evidence_ok(root, proof):
            errors.append(f'{identifier}: evidence missing or changed')
    for recheck in item.get('authority_rechecks', []):
        for saved in (recheck['previous_record'], recheck['record']):
            proofs = [saved.get('evidence', {})]
            if saved.get('delegation'):
                proofs.append(saved['delegation'].get('evidence', {}))
            if any(not evidence_ok(root, proof) for proof in proofs):
                errors.append(f'{identifier}: historical authority recheck evidence missing or changed')
    for link in item['refs']:
        upstream = state['items'].get(link['id'])
        if not upstream:
            errors.append(f'{identifier}: stale reference {link["id"]}@{link["version"]}')
            continue
        unchanged = upstream.get('current_valid_version', upstream['version'] if upstream['validity'] == 'valid' else None)
        waiver = any(row['source_id'] == link['id'] and row['source_version'] == upstream['version'] and
            row['target_id'] == identifier and row['target_version'] == item['version'] and
            row['status'] == 'unaffected' and evidence_ok(root, row['evidence'])
            for row in state.get('impacts', []))
        allow_old = historical_ok or waiver
        try:
            historical(state, link['id'], link['version'])
            if link['version'] != unchanged and not allow_old:
                errors.append(f'{identifier}: upstream not effective or stale {link["id"]}@{link["version"]}')
            else:
                errors.extend(problems(root, state, link['id'], visited, link['version'], allow_old, memo,
                                       check_authority=check_authority))
        except ValueError as exc:
            errors.append(str(exc))
    for level in ('I', 'V'):
        check = item['checks'].get(level)
        if not check or check.get('result') != 'pass' or not evidence_ok(root, check['evidence']):
            errors.append(f'{identifier}: {level} check incomplete/failed/stale')
        elif level == 'I' and item['type'] == 'T02':
            # Honor an already effective legacy version. Require closure when completing an open draft.
            if 'closure' in check or (not historical_ok and missing_draft_closure(item)):
                try:
                    check_business_closure(root, check)
                except (KeyError, OSError, ValueError, TypeError) as exc:
                    errors.append(f'{identifier}: {exc}')
        elif level == 'V' and check.get('method') == 'human_review':
            roles = state['requirements'][item['requirement']]['roles']
            problem = human_review_problem(root, item, roles, check, check_authority=check_authority)
            if problem:
                errors.append(f'{identifier}: {problem}')
    for role in item['decision_roles']:
        approval = item['approvals'].get(role)
        roles = state['requirements'][item['requirement']]['roles']
        if (not approval or approval.get('result') != 'approved' or not evidence_ok(root, approval['evidence'])
                or (check_authority and approval['actor'] not in roles.get(role, []))):
            errors.append(f'{identifier}: missing/stale {role} decision')
    if item['type'] in ('P04', 'T04'):
        validation = item.get('validation', {})
        if validation.get('result') not in ('verified', 'waived') or not evidence_ok(root, validation.get('evidence', {})):
            errors.append(f'{identifier}: required user validation/waiver incomplete')
        elif check_authority and validation.get('result') == 'waived' and validation.get('actor') not in state['requirements'][item['requirement']]['roles'].get('product', []):
            errors.append(f'{identifier}: user-validation waiver authority changed')
    if item['type'] == 'P04':
        errors.extend(stage_review_problems(root, item))
    for question in state['questions'].values() if not historical_ok else []:
        if question['status'] == 'open' and question['blocking'] and identifier in question['affected']:
            errors.append(f'{identifier}: blocking question {question["id"]}')
    result = sorted(set(errors))
    # Reuse only during one stable validation pass. Historical applicability is
    # distinct, and cycle errors depend on the ancestor path, so never cache them.
    if not any(error.endswith(': dependency cycle') for error in result):
        memo[key] = tuple(result)
    return result


def gate(root, state, identifiers):
    memo = {}
    errors = sorted({error for identifier in identifiers for error in problems(root, state, identifier, _memo=memo)})
    return {'pass': not errors, 'items': identifiers, 'errors': errors}


def promote(root, state, identifier):
    result = gate(root, state, [identifier])
    need(result['pass'], '\n'.join(result['errors']))
    state['items'][identifier]['validity'] = 'valid'
    state['items'][identifier]['current_valid_version'] = state['items'][identifier]['version']
    state['items'][identifier]['last_approved_version'] = state['items'][identifier]['version']
    event(state, 'promote', {'id': identifier, 'version': state['items'][identifier]['version']})
    return result


def question(root, state, data):
    identifier = slug(data['id'])
    need(data.get('question') and data.get('owner') and data.get('next_action'), 'Question, owner and next_action required.')
    need(isinstance(data.get('blocking'), bool), 'blocking must be true/false.')
    need(data.get('affected'), 'Question requires affected item IDs.')
    for key in data['affected']:
        ref(state, key)
    status = data.get('status', 'open')
    need(status in ('open', 'closed'), 'Unknown question status.')
    if status == 'closed':
        data['resolution_evidence'] = evidence(root, data['resolution_evidence'])
    state['questions'][identifier] = {**data, 'status': status, 'updated_at': now()}
    if status == 'open' and data['blocking']:
        invalidate(state, data['affected'], 'Blocking question: ' + identifier)
    event(state, 'question', {'question': copy.deepcopy(state['questions'][identifier])})
    return state['questions'][identifier]


def resume(root, state, requirement=None):
    memo = {}
    reqs = [state['requirements'][requirement]] if requirement else list(state['requirements'].values())
    result = []
    for req in reqs:
        items = [item for item in state['items'].values() if item['requirement'] == req['id']]
        result.append({'requirement': {**req, 'status': requirement_delivery_status(root, state, req)}, 'items': [
            {**{key: item.get(key) for key in ('id', 'type', 'stage', 'version', 'latest_version',
             'current_valid_version', 'last_approved_version', 'path', 'validity', 'refs')},
             'display_status': display_status(state, item)}
            for item in items], 'issues': {item['id']: problems(root, state, item['id'], _memo=memo) for item in items},
            'questions': [q for q in state['questions'].values() if q['status'] == 'open' and
                          any(i['id'] in q['affected'] for i in items)]})
    handoffs = []
    for row in state.get('handoffs', []):
        if requirement and row['requirement'] != requirement:
            continue
        errors = handoff_problems(root, state, row, _memo=memo)
        handoffs.append({**row, 'current_applicable': not errors, 'applicability_errors': errors})
    impacts = state.get('impacts', [])
    if requirement:
        related = {item['id'] for item in state['items'].values() if item['requirement'] == requirement}
        impacts = [row for row in impacts if row['source_id'] in related or row['target_id'] in related]
    return {'product': state['product'], 'revision': state['revision'], 'requirements': result,
            'legacy': state.get('schema_version') == 1, 'read_only': state.get('schema_version') == 1,
            'impacts': impacts, 'handoffs': handoffs,
            'deliveries': [delivery_status(root, state, row) for row in state.get('deliveries', [])
                           if not requirement or row['requirement'] == requirement]}


def checkpoint(state, data):
    req = state['requirements'][data['requirement']]
    need(data.get('next_action'), 'next_action required.')
    req['next_action'] = data['next_action']
    event(state, 'checkpoint', data)
    return {'saved': True}


def require_review_files(root, items):
    for item in items:
        errors = stage_review_problems(root, item)
        need(not errors, '\n'.join(errors))


def delivery_handoff(root, state, req, items):
    selected = {(i['id'], i['version']) for i in items if i['stage'] == 'S5'}
    for row in reversed(state.get('handoffs', [])):
        if (row['requirement'] == req['id'] and row['from_stage'] == 'S5'
                and row['to_stage'] == 'delivery' and row.get('result') == 'approved'
                and not handoff_problems(root, state, row) and selected <= closure(state, row['items']).keys()):
            return row
    raise ValueError('Delivery requires a current S5 product handoff covering the selected S5 items.')


def delivery_files(included, impacts, approval, handoff_row):
    records = [approval, handoff_row['evidence']]
    for item in included.values():
        records.append(item)
        for recheck in item.get('authority_rechecks', []):
            for saved in (recheck['previous_record'], recheck['record']):
                records.append(saved['evidence'])
                if saved.get('delegation'):
                    records.append(saved['delegation']['evidence'])
        records.extend(item['evidence'])
        records.extend(check['evidence'] for check in item['checks'].values())
        records.extend(row['evidence'] for row in item['approvals'].values())
        delegation = item['checks'].get('V', {}).get('delegation')
        if delegation:
            records.append(delegation['evidence'])
        if item.get('validation'):
            records.append(item['validation']['evidence'])
    records.extend(row['evidence'] for row in impacts if row.get('evidence'))
    files = {}
    for record in records:
        relative = record['path']
        windows_path = PureWindowsPath(relative)
        need(not windows_path.anchor and '..' not in windows_path.parts and windows_path.parts,
             f'Unsafe delivery path: {relative}')
        need(all(part == part.rstrip(' .') and not re.search(r'[<>:"|?*\x00-\x1f]', part)
                 for part in windows_path.parts), f'Unsafe filename in delivery path: {relative}')
        need(windows_path.parts[0].casefold() not in ('delivery.json', 'delivery.json.tmp'),
             f'Delivery metadata path is reserved: {relative}')
        need(files.get(relative, record['sha256']) == record['sha256'], f'Conflicting file versions: {relative}')
        files[relative] = record['sha256']
    return files


def require_direct_delivery_path(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    # Windows 3.9 exposes junctions through lstat even if their target is missing.
    junction = getattr(info, 'st_reparse_tag', 0) == getattr(stat, 'IO_REPARSE_TAG_MOUNT_POINT', -1)
    need(not stat.S_ISLNK(info.st_mode) and not junction and path.resolve() == path,
         'Redirected delivery path: ' + str(path))


def export_delivery(root, path, files, delivery, rollback):
    # Validate all inputs before creating a numbered package. Copy into a private
    # staging directory, checking copied bytes, and expose the finished folder in one rename.
    for rel, expected in files.items():
        src = local(root, rel)
        need(src.is_file() and digest(src) == expected, f'Delivery source missing or changed: {rel}')
    ancestor = root
    for part in path.relative_to(root).parts:
        ancestor = ancestor / part
        require_direct_delivery_path(ancestor)
    if os.path.lexists(path):
        # A previous process may have finished the immutable package immediately
        # before persisting state.json. Adopt only that exact verified package.
        need(path.is_dir() and not path.is_symlink(), 'Conflicting delivery path exists.')
        metadata = path / 'delivery.json'
        require_direct_delivery_path(metadata)
        need(metadata.is_file(), 'Incomplete delivery folder; inspect it before retry.')
        existing = read(metadata)
        need(existing == {**delivery, 'at': existing.get('at')} and existing.get('at'),
             'Existing delivery metadata differs; inspect it before retry.')
        expected_paths = {Path(rel).as_posix() for rel in files} | {'delivery.json'}
        actual_paths = set()
        pending = [path]
        while pending:
            for child in pending.pop().iterdir():
                require_direct_delivery_path(child)
                if child.is_dir():
                    pending.append(child)
                else:
                    actual_paths.add(child.relative_to(path).as_posix())
        need(actual_paths == expected_paths, 'Existing delivery file list differs.')
        need(all(digest(local(path, rel)) == expected for rel, expected in files.items()),
             'Existing delivery bytes differ.')
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    # The project root gives the staging copy a shorter path on Windows. A
    # separately mounted delivery directory must stage on its own filesystem.
    staging_parent = root if root.stat().st_dev == path.parent.stat().st_dev else path.parent
    with TemporaryDirectory(prefix='.export-', dir=staging_parent) as temp:
        staging = Path(temp) / 'bundle'
        staging.mkdir()
        for relative, expected in files.items():
            dest = local(staging, relative)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local(root, relative), dest)
            need(digest(dest) == expected, f'File changed during export: {relative}')
        atomic(staging / 'delivery.json', delivery)
        def publish():
            need(not os.path.lexists(path), 'Delivery path appeared during export; inspect before retry.')
            staging.rename(path)
        review_bundle.windows_file_operation(publish, lambda: staging.is_dir() and not os.path.lexists(path),
                                             f'暂时无法保存交付包。关闭占用目录的预览或同步程序后，使用同一请求重试：{path}')
        rollback.callback(shutil.rmtree, path)
    return delivery


def deliver(root, state, data, rollback):
    req = state['requirements'][data['requirement']]
    identifiers = data['items']
    need(identifiers and len(identifiers) == len(set(identifiers)), 'Unique delivery item IDs required.')
    items = [ref(state, key) for key in identifiers]
    plan = checked_plan(state, req['plan'], req['target'])
    reused = {key for choice in plan.values() if choice['mode'] == 'reuse' for key in choice['items']}
    need(all(i['requirement'] == req['id'] or i['id'] in reused for i in items), 'Delivery scope contains unrelated items.')
    need(plan['S5']['mode'] != 'not_applicable', 'Formal delivery requires an applicable S5.')
    need(all(i['target'] == req['target'] for i in items), 'Delivery target mismatch.')
    required_types = {'S1': {'T01'}, 'S2': {'T02'}, 'S3': {'T03'}, 'S4': {'T04', 'P04'}, 'S5': {'T05', 'AC', 'REQ'}}
    for stage, policy in plan.items():
        if policy['mode'] == 'not_applicable':
            continue
        if policy['mode'] == 'reuse':
            need(set(policy['items']) <= set(identifiers), f'Missing reused {stage} items.')
        selected_types = {i['type'] for i in items if i['stage'] == stage}
        missing = sorted(required_types[stage] - selected_types)
        need(not missing, f'{stage}: delivery missing required items: {", ".join(missing)}')
    result = gate(root, state, identifiers)
    need(result['pass'], '\n'.join(result['errors']))
    for item in items:
        need(item['validity'] == 'valid' and item.get('current_valid_version') == item['version'],
             f'Not current/effective: {item["id"]}')
    require_review_files(root, items)
    approved_handoff = delivery_handoff(root, state, req, items)
    approval = evidence(root, data['evidence'])
    need(data['actor'] in req['roles'].get('delivery', []), 'Delivery actor not authorized.')
    need(approval['kind'] in ('human_reply', 'review') and data.get('conclusion'), 'Delivery needs actual approval.')
    need(data.get('result') == 'approved', 'Delivery requires an explicit approved result.')
    # This exact manifest must be presented for approval, then named by its hash in the payload.
    current_manifest = matching_manifest(state, identifiers, req['id'], data.get('approved_manifest_sha256'))
    need(current_manifest is not None, 'Approval must bind to the current delivery manifest hash.')
    manifest_rows = current_manifest['manifest']
    manifest_hash = current_manifest['sha256']
    number = len(state['deliveries']) + 1
    parent = root / generated_path(root, '05-prd-review/deliveries')
    path = parent / f'{number:04d}'
    included = closure(state, identifiers)
    files = delivery_files(included, current_manifest['impacts'], approval, approved_handoff)
    delivery = {'number': number, 'requirement': req['id'], 'target': req['target'],
                'requirement_snapshot': copy.deepcopy(req),
                'manifest': manifest_rows, 'manifest_sha256': manifest_hash, 'handoff': copy.deepcopy(approved_handoff),
                'impacts': copy.deepcopy(current_manifest['impacts']), 'approval': {**data, 'evidence': approval},
                'at': now(), 'path': path.relative_to(root).as_posix(),
                'items': {f'{key[0]}@{key[1]}': value for key, value in sorted(included.items())}}
    delivery = export_delivery(root, path, files, delivery, rollback)
    state['deliveries'].append(delivery)
    req['status'] = 'exported'
    req['next_action'] = f'交付包 {number:04d} 已导出；从包内实际检查后登记 delivery-check。'
    event(state, 'deliver', {'number': number, 'requirement': req['id']})
    return delivery


def delivery_targets(delivery):
    """Required reading and application entries, not every page/resource in an app."""
    entries = []
    for item in delivery['items'].values():
        if item['type'] == 'T05':
            entries.append(('documents', item))
        for row in item.get('evidence', []):
            suffix = Path(row['path']).suffix.lower()
            if row.get('review_role') == 'srs':
                entries.append(('documents', row))
            if row.get('review_role') == 'prototype' or (item['type'] == 'P04' and suffix in ('.html', '.htm')):
                entries.append(('prototype', row))
            if suffix == '.drawio':
                entries.append(('diagram', row))
        if item['type'] == 'P04' and Path(item['path']).suffix.lower() in ('.html', '.htm'):
            entries.append(('prototype', item))
    unique = {}
    for kind, entry in entries:
        key = (kind, entry['sha256'])
        if key not in unique:
            unique[key] = {'kind': kind, 'target': entry['path'], 'sha256': entry['sha256'], 'aliases': []}
        if entry['path'] not in unique[key]['aliases']:
            unique[key]['aliases'].append(entry['path'])
    # A PRD bundle may carry a readable name for the same P04 snapshot. Accept
    # that registered HTML alias without treating every support page as a new app.
    for item in delivery['items'].values():
        for entry in [item] + item.get('evidence', []):
            key = ('prototype', entry['sha256'])
            if (key in unique and Path(entry['path']).suffix.lower() in ('.html', '.htm')
                    and entry['path'] not in unique[key]['aliases']):
                unique[key]['aliases'].append(entry['path'])
    return list(unique.values())


def delivery_integrity(root, delivery):
    """Check the frozen exported bytes without editing the authorized directory."""
    try:
        relative = delivery['path']
        package = root / relative
        need(local(root, relative) == package, 'Redirected or non-canonical delivery path.')
        ancestor = root
        for part in package.relative_to(root).parts:
            ancestor /= part
            require_direct_delivery_path(ancestor)
        need(package.is_dir(), 'Delivery package is missing.')
        metadata = package / 'delivery.json'
        require_direct_delivery_path(metadata)
        need(metadata.is_file() and read(metadata) == delivery, 'Delivery metadata missing or changed.')
        files = delivery_files(delivery['items'], delivery.get('impacts', []),
                               delivery['approval']['evidence'], delivery['handoff'])
        actual, pending = set(), [package]
        while pending:
            for child in pending.pop().iterdir():
                require_direct_delivery_path(child)
                if child.is_dir():
                    pending.append(child)
                else:
                    actual.add(child.relative_to(package).as_posix())
        expected_paths = {Path(name).as_posix() for name in files} | {'delivery.json'}
        need(actual == expected_paths, 'Delivery file list changed or is incomplete.')
        changed = [name for name, sha in files.items() if digest(local(package, name)) != sha]
        need(not changed, 'Delivery files changed: ' + ', '.join(changed))
        return []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [str(exc)]


def delivery_status(root, state, delivery):
    rows = [row for row in state.get('delivery_checks', [])
            if row['number'] == delivery['number'] and row['manifest_sha256'] == delivery['manifest_sha256']]
    last = rows[-1] if rows else None
    errors = delivery_integrity(root, delivery)
    if last:
        for proof in [last['evidence']] + [c['evidence'] for c in last['checks']]:
            if not evidence_ok(root, proof):
                errors.append('Delivery-check evidence missing or changed: ' + proof.get('path', '?'))
    status = 'delivery_failed' if errors or (last and last['result'] == 'fail') else 'delivered' if last else 'exported'
    return {'number': delivery['number'], 'requirement': delivery['requirement'], 'path': delivery['path'],
            'manifest_sha256': delivery['manifest_sha256'], 'status': status,
            'display_status': {'exported': '已导出，待包内检查', 'delivery_failed': '交付验收未通过',
                               'delivered': '交付验收完成'}[status],
            'required_checks': delivery_targets(delivery), 'latest_check': last, 'integrity_errors': errors}


def requirement_delivery_status(root, state, req):
    latest_handoffs = {row['from_stage']: row for row in state.get('handoffs', [])
                       if row['requirement'] == req['id']}
    if (any(authority_problems(state, item) for item in state['items'].values() if item['requirement'] == req['id'])
            or any(handoff_authority_problems(state, row) for row in latest_handoffs.values())):
        return 'needs_review'
    if req.get('status') not in ('delivered', 'exported', 'delivery_failed'):
        return req['status']
    packages = [row for row in state.get('deliveries', []) if row['requirement'] == req['id']]
    return delivery_status(root, state, packages[-1])['status'] if packages else 'exported'


def delivery_check(root, state, data):
    """Record actual package-operation evidence. This does not authenticate observations."""
    packages = [row for row in state.get('deliveries', []) if row['number'] == data.get('number')]
    need(len(packages) == 1, 'Unknown delivery number.')
    delivery = packages[0]
    need(data.get('manifest_sha256') == delivery['manifest_sha256'], 'Check must bind to this delivery manifest.')
    need(data.get('result') in ('pass', 'fail') and data.get('actor') and data.get('conclusion'),
         'Delivery check requires actor, pass/fail and conclusion.')
    proof = evidence(root, data['evidence'])
    need(proof['kind'] == 'operation', 'Delivery check needs an actual package operation log.')
    need(not local(root, proof['path']).is_relative_to(root / delivery['path']),
         'Check evidence must be outside the immutable delivery package.')
    # An operation log names the exact package; old source-workspace testing alone is insufficient.
    report = local(root, proof['path']).read_text(encoding='utf-8-sig')
    need(delivery['path'] in report and delivery['manifest_sha256'] in report,
         'Operation log must identify the package path and manifest hash.')
    expected = delivery_targets(delivery)
    allowed = {(r['kind'], name): r for r in expected for name in r['aliases']}
    checks, covered = [], set()
    need(isinstance(data.get('checks'), list), 'checks must be a list.')
    for row in data['checks']:
        need(isinstance(row, dict), 'Check entry must be an object.')
        target = allowed.get((row.get('kind'), row.get('target')))
        need(target is not None, 'Check target must be a registered reading/prototype/diagram entry.')
        identity = (target['kind'], target['sha256'])
        need(identity not in covered, 'Duplicate check for the same entry/content.')
        covered.add(identity)
        need(row.get('result') in ('pass', 'fail') and row.get('conclusion'), 'Entry check needs result and conclusion.')
        row_proof = evidence(root, row.get('evidence', proof))
        need(row_proof['kind'] == 'operation', 'Entry check requires actual operation evidence.')
        need(not local(root, row_proof['path']).is_relative_to(root / delivery['path']),
             'Check evidence must be outside the immutable delivery package.')
        text = local(root, row_proof['path']).read_text(encoding='utf-8-sig')
        need(delivery['path'] in text and delivery['manifest_sha256'] in text and row['target'] in text,
             'Entry operation evidence must identify package, manifest and target.')
        if row['kind'] == 'prototype' and row['result'] == 'pass':
            tasks = row.get('tasks')
            need(isinstance(tasks, list) and tasks, 'Prototype check requires executed tasks.')
            for task in tasks:
                need(isinstance(task, dict) and task.get('result') == 'pass', 'Passed prototype needs passed task observations.')
                for key in ('task', 'expected', 'observed'):
                    need(isinstance(task.get(key), str) and task[key].strip() and task[key] in text,
                         'Task, expected and observed must be locatable in operation evidence.')
        checks.append({**copy.deepcopy(row), 'sha256': target['sha256'], 'evidence': row_proof})
    errors = delivery_integrity(root, delivery)
    if data['result'] == 'pass':
        need(not errors, '\n'.join(errors))
        need(covered == {(r['kind'], r['sha256']) for r in expected}, 'Required entry checks are incomplete.')
        need(all(row['result'] == 'pass' for row in checks), 'A failed entry cannot complete delivery.')
    result = {'number': delivery['number'], 'requirement': delivery['requirement'],
              'manifest_sha256': delivery['manifest_sha256'], 'package_path': delivery['path'],
              'actor': data['actor'], 'result': data['result'], 'conclusion': data['conclusion'],
              'evidence': proof, 'checks': checks, 'integrity_errors': errors, 'at': now()}
    state.setdefault('delivery_checks', []).append(result)
    req = state['requirements'][delivery['requirement']]
    latest = [row for row in state['deliveries'] if row['requirement'] == req['id']][-1]
    # Inspecting an older package must not finish newer work or overwrite its next action.
    if latest['number'] == delivery['number'] and req['status'] in ('delivered', 'exported', 'delivery_failed'):
        req['status'] = 'delivered' if data['result'] == 'pass' else 'delivery_failed'
        req['next_action'] = ('交付验收完成；保留实际检查证据及适用限制。' if data['result'] == 'pass'
                              else '交付验收未通过；按问题修订来源、复检并核对清单授权后重新导出。')
    event(state, 'delivery_check', {'number': delivery['number'], 'requirement': req['id'],
                                   'result': data['result'], 'conclusion': data['conclusion']})
    return result


def closure(state, identifiers):
    included = {}
    pending = [(key, ref(state, key)['version']) for key in identifiers]
    while pending:
        key = pending.pop()
        if key in included:
            continue
        item = historical(state, *key)
        included[key] = item
        pending.extend((link['id'], link['version']) for link in item['refs'])
    return included


def manifest(state, identifiers, requirement=None, *, legacy_roles=None):
    included = closure(state, identifiers)
    rows = []
    for (identifier, version), item in sorted(included.items()):
        # Bind approval to the exact exported dependency, prototype and review records as well as prose.
        content = {k: item.get(k) for k in ('id', 'version', 'type', 'title', 'target', 'sha256', 'refs',
                   'evidence', 'decision_roles', 'checks', 'approvals', 'validation')}
        if 'review_bundle' in item:
            content['review_bundle'] = item['review_bundle']
        if item.get('authority_rechecks'):
            content['authority_rechecks'] = item['authority_rechecks']
        rows.append({'id': identifier, 'version': item['version'], 'sha256': item['sha256'],
                     'record_sha256': hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()})
    requirements = {item['requirement'] for item in included.values()}
    if requirement:
        requirements.add(requirement)
    context = [{key: state['requirements'][identifier][key] for key in ('id', 'target', 'plan')}
               for identifier in sorted(requirements)]
    if legacy_roles is not None:
        for row in context:
            row['roles'] = legacy_roles.get(row['id'], state['requirements'][row['id']]['roles'])
    impacts = [row for row in state.get('impacts', []) if (row['target_id'], row['target_version']) in included]
    bundle = {'manifest': rows, 'context': context, 'impacts': impacts}
    if legacy_roles is None:
        # Recorded decisions bind their exact actors, roles, evidence and versions.
        # Their CURRENT authority is checked by gate/handoff/deliver, separately
        # from the content hash, so unrelated roster changes do not require consent again.
        bundle['authority_policy'] = 'current_registered_roles'
    if requirement and len(context) > 1:
        bundle['receiving_requirement'] = requirement
    return {**bundle, 'sha256': hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()}


def matching_manifest(state, identifiers, requirement, expected_hash):
    """Honor exact old manifests without treating their old roster as authority.

    Legacy hashes included all role memberships. Rebuild only known historical
    rosters; all content, checks, evidence, scope and plans must still hash exactly.
    Callers separately require the current authority checks to pass.
    """
    current = manifest(state, identifiers, requirement)
    if current['sha256'] == expected_hash:
        return current
    roles = {key: copy.deepcopy(req['roles']) for key, req in state['requirements'].items()}
    candidate = manifest(state, identifiers, requirement, legacy_roles=roles)
    if candidate['sha256'] == expected_hash:
        return candidate
    for row in reversed(state.get('events', [])):
        if row.get('kind') != 'configure' or not isinstance(row.get('before'), dict):
            continue
        roles[row['requirement']] = row['before']
        candidate = manifest(state, identifiers, requirement, legacy_roles=roles)
        if candidate['sha256'] == expected_hash:
            return candidate
    return None


def handoff(root, state, data):
    req = state['requirements'][data['requirement']]
    stage = data['from_stage']
    need(stage in STAGES, 'Invalid handoff source stage.')
    following = STAGES[STAGES.index(stage) + 1] if stage != 'S5' else 'delivery'
    need(data.get('to_stage') == following, 'Handoff must name the next business stage (or delivery).')
    need(data.get('result') == 'approved' and data.get('conclusion'), 'Handoff requires an explicit decision.')
    need(data.get('actor') in req['roles'].get('product', []), 'Handoff actor lacks product authority.')
    proof = evidence(root, data['evidence'])
    need(proof['kind'] in ('human_reply', 'review'), 'Handoff needs actual product-owner reply/review.')
    identifiers = data['items']
    need(identifiers and len(identifiers) == len(set(identifiers)), 'Unique handoff item IDs required.')
    items = [ref(state, key) for key in identifiers]
    policy = req['plan'][stage]
    reused = set(policy['items']) if policy['mode'] == 'reuse' else set()
    need(policy['mode'] != 'not_applicable' and reused <= set(identifiers), 'Handoff does not match the stage plan.')
    need(all(item['stage'] == stage and item['target'] == req['target'] and
             (item['requirement'] == req['id'] or item['id'] in reused) for item in items),
         'Handoff items must belong to the selected stage, target and requirement or its approved reuse list.')
    need(all(ref(state, key)['version'] == v for key, v in policy.get('versions', {}).items()),
         'Reused version changed; review the new version and replan.')
    need(any(item['type'] == 'T0' + stage[1] for item in items), 'Handoff requires the stage deliverable T01-T05.')
    if stage == 'S2':
        for item in items:
            if item['type'] == 'T02':
                need('closure' in item['checks'].get('I', {}),
                     'New S2 handoff requires a current T02 I closure check; register the operation evidence.')
    if stage == 'S4':
        need(any(item['type'] == 'P04' for item in items), 'S4 handoff requires the interactive prototype.')
    require_review_files(root, items)
    result = gate(root, state, identifiers)
    need(result['pass'], '\n'.join(result['errors']))
    need(all(item.get('current_valid_version') == item['version'] for item in items),
         'Handoff requires current effective versions; promote first.')
    row = {**copy.deepcopy(data), 'evidence': proof, 'at': now(),
           'versions': [{'id': item['id'], 'version': item['version'], 'sha256': item['sha256']} for item in items],
           'manifest_sha256': manifest(state, identifiers, req['id'])['sha256']}
    state['handoffs'].append(row)
    req['next_action'] = following
    event(state, 'handoff', copy.deepcopy(row))
    return row


def handoff_problems(root, state, row, _memo=None):
    memo = {} if _memo is None else _memo
    errors = []
    req = state['requirements'].get(row['requirement'], {})
    if row['actor'] not in req.get('roles', {}).get('product', []):
        errors.append('Product authority changed.')
    if not evidence_ok(root, row['evidence']):
        errors.append('Handoff evidence missing or changed.')
    for version in row['versions']:
        item = state['items'].get(version['id'])
        if not item or item.get('current_valid_version') != version['version'] or item['sha256'] != version['sha256']:
            errors.append(f'{version["id"]}: handoff version no longer effective.')
        else:
            errors.extend(problems(root, state, item['id'], _memo=memo))
            errors.extend(stage_review_problems(root, item))
    if not errors and matching_manifest(state, row['items'], row['requirement'], row.get('manifest_sha256')) is None:
        errors.append('Handoff manifest changed; review the changed scope, records or plan.')
    return sorted(set(errors))


def display_status(state, item):
    checks = item.get('checks', {})
    if any(check.get('result') == 'fail' for check in checks.values()):
        return '质检不通过'
    if any(row['target_id'] == item['id'] and row['target_version'] == item['version'] and
           row['status'] == 'pending' for row in state.get('impacts', [])):
        return '待更新（待影响分析）'
    if any(q['status'] == 'open' and q['blocking'] and item['id'] in q['affected']
           for q in state['questions'].values()):
        return '待人工决策'
    if any(r.get('result') == 'rejected' for r in item.get('approvals', {}).values()):
        return '待人工决策'
    if item.get('validation', {}).get('result') == 'pending':
        return '待人工决策'
    if item['validity'] == 'needs_update':
        return '待更新'
    if authority_problems(state, item):
        return '待授权复核'
    if not checks:
        return '处理中'
    if missing_draft_closure(item):
        return '待补闭环实测'
    if any(checks.get(level, {}).get('result') != 'pass' for level in ('I', 'V')):
        return '待质检'
    if item['type'] in ('P04', 'T04') and item.get('validation', {}).get('result') not in ('verified', 'waived'):
        return '待人工决策'
    if any(item.get('approvals', {}).get(role, {}).get('result') != 'approved' for role in item['decision_roles']):
        return '待授权'
    if item.get('current_valid_version') == item['version']:
        return '有效'
    return '处理中（待登记生效）'


def render_views(root, state):
    """Rebuild human-readable views from state; never parse these views as metadata."""
    memo = {}
    directory = local(root, generated_path(root, MANAGEMENT))
    def cell(value):
        return str(value if value is not None else '无').replace('|', '\\|').replace('\n', '<br>')
    def save(filename, title, headers, rows):
        text = f'# {title}\n\n项目：{state["product"]}　索引修订：{state["revision"]}\n\n'
        text += '由 state.json 生成；请通过维护命令修改记录。\n\n'
        text += '| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join('---' for _ in headers) + ' |\n'
        text += ''.join('| ' + ' | '.join(cell(value) for value in row) + ' |\n' for row in rows)
        atomic_text(local(root, generated_path(root, MANAGEMENT + '/' + filename)), text)
    labels = {'draft': '处理中', 'valid': '有效', 'needs_update': '待更新', 'needs_review': '待复核',
              'delivered': '交付验收完成', 'exported': '已导出，待包内检查', 'delivery_failed': '交付验收未通过',
              'pending': '待分析', 'affected': '受影响', 'unaffected': '无影响',
              'superseded_by_revision': '已由新版本处理'}
    items = list(state['items'].values())
    reqs = list(state['requirements'].values())
    save('project-status.md', '项目状态', ['需求', '目标版本', '状态', '下一步'],
         [[r['id'], r['target'], labels.get(requirement_delivery_status(root, state, r), r['status']), r.get('next_action')] for r in reqs])
    save('project-versions.md', '项目版本记录', ['需求', '目标版本', '当前状态'],
         [[r['id'], r['target'], labels.get(requirement_delivery_status(root, state, r), r['status'])] for r in reqs])
    save('delivery-checks.md', '交付验收记录', ['交付包', '状态', '结论', '操作证据', '完整性问题'],
         [[r['path'], r['display_status'], (r['latest_check'] or {}).get('conclusion', '尚无包内实测记录'),
           (r['latest_check'] or {}).get('evidence', {}).get('path'), '; '.join(r['integrity_errors'])]
          for r in (delivery_status(root, state, d) for d in state.get('deliveries', []))])
    save('artifact-versions.md', '成果版本清单', ['成果', '最新版本', '当前有效版本', '历史已确认版本', '状态', '位置'],
         [[i['id'], i['version'], i.get('current_valid_version'), i.get('last_approved_version'),
           display_status(state, i), i['path']] for i in items])
    save('changes.md', '变更记录', ['时间', '操作', '对象', '原因'],
         [[e['at'], e['kind'], e.get('id', e.get('requirement', '项目')), e.get('reason', e.get('conclusion', '见索引事件'))]
          for e in state['events']])
    save('impact-analysis.md', '影响分析记录', ['来源及版本', '成果及版本', '结论', '原因', '依据'],
         [[f'{r["source_id"]}@{r["source_version"]}', f'{r["target_id"]}@{r["target_version"]}',
           labels.get(r['status'], r['status']), r['reason'], r.get('evidence', {}).get('path')]
          for r in state.get('impacts', [])])
    save('handoffs.md', '阶段交接记录', ['需求', '交接', '决定人', '结论', '依据', '版本范围', '当前适用性'],
         [[r['requirement'], r['from_stage'] + ' → ' + r['to_stage'], r['actor'], r['conclusion'],
           r['evidence']['path'], ', '.join(f'{v["id"]}@{v["version"]}' for v in r['versions']),
           '有效' if not handoff_problems(root, state, r, _memo=memo) else '待复核；历史决定保留']
          for r in state.get('handoffs', [])])
    save('pending-decisions.md', '待决事项', ['编号', '问题', '责任人', '是否阻塞', '状态', '下一步'],
         [[q['id'], q['question'], q['owner'], '是' if q['blocking'] else '否', q['status'], q['next_action']]
          for q in state['questions'].values()])
    checks = []
    for item in items:
        for version in item.get('history', []) + [item]:
            for level, check in version['checks'].items():
                checks.append([item['id'], version['version'], level, check['result'],
                               check['conclusion'], check['evidence']['path']])
    for row in state.get('authority_rechecks', []):
        check = row['record']
        checks.append([row['id'], row['version'], check['category'] + '（历史授权补核）',
                       check['result'], check['conclusion'], check['evidence']['path']])
    save('quality-checks.md', '质量检查记录', ['成果', '版本', '层级', '结果', '结论', '证据'], checks)
    trial = directory / '查看与试用.html'
    atomic_text(trial, trial_entry.render(root, state, directory,
                                         authority_check=lambda item: authority_problems(state, item)))
    return {'views': [str(p.relative_to(root)) for p in sorted(directory.glob('*.md'))] + [str(trial.relative_to(root))]}


def migrate(root, apply=False):
    path = state_path(root)
    old = read(path)
    need(path.parent == root and old.get('schema_version') == 1, 'Only legacy schema 1 root/state.json needs migration.')
    need(not (root / '.write-lock').exists(), 'Legacy writer lock exists; stop the writer before migration.')
    result = {'mode': 'preview', 'root': str(root), 'from_schema': 1, 'to_schema': 2,
              'items': len(old['items']), 'preserve_paths': True,
              'actions': ['完整目录备份并核对哈希', '新增分阶段目录与中文管理视图',
                          '保留原有正文与证据路径', '升级版本指针并归档原始状态文件']}
    if not apply:
        return result
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = root.parent / (root.name + '-migration-backup-' + stamp)
    need(not backup.exists() and backup.parent.resolve() == root.parent.resolve(), 'Invalid backup path.')
    lock = root / '.write-lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        shutil.copytree(root, backup, ignore=shutil.ignore_patterns('.write-lock'))
        for source in root.rglob('*'):
            if source.is_file() and source != lock:
                copied = backup / source.relative_to(root)
                need(copied.is_file() and digest(source) == digest(copied), 'Migration backup verification failed.')
        state = copy.deepcopy(old)
        state.update({'schema_version': 2, 'impacts': [], 'handoffs': []})
        for item in state['items'].values():
            item['latest_version'] = item['version']
            item['current_valid_version'] = item['version'] if item['validity'] == 'valid' else None
            approved = [v['version'] for v in item.get('history', []) + [item] if v['validity'] == 'valid']
            item['last_approved_version'] = max(approved, default=None)
        state['revision'] += 1
        event(state, 'migrate', {'backup': str(backup), 'from_schema': 1})
        layout(root)
        destination = local(root, generated_path(root, MANAGEMENT))
        atomic(destination / 'state.json', state)
        os.replace(path, destination / 'migration-original-state-v1.json')
        render_views(root, state)
        return {**result, 'mode': 'applied', 'backup': str(backup)}
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('command', choices=['init', 'new', 'configure', 'replan', 'snapshot', 'put', 'record', 'question',
                                          'checkpoint', 'resume', 'gate', 'promote', 'manifest', 'deliver', 'delivery-check',
                                          'discover', 'impact', 'handoff', 'views', 'migrate'])
    parser.add_argument('--data', type=Path, help='UTF-8 JSON payload')
    parser.add_argument('--product')
    parser.add_argument('--file')
    parser.add_argument('--requirement')
    parser.add_argument('--items', nargs='+')
    parser.add_argument('--apply', action='store_true', help='Apply legacy migration after a verified full backup.')
    parser.add_argument('--max-depth', type=int, default=4, help='Discovery depth within the selected root.')
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        data = read(args.data) if args.data else {}
        if args.command == 'discover':
            need(0 <= args.max_depth <= 10, 'Discovery depth must be 0-10.')
            result = discover(root, args.max_depth)
        elif args.command == 'migrate':
            result = migrate(root, args.apply)
        elif args.command == 'init':
            need(bool(args.product), '--product required.')
            result = init(root, args.product)
        elif args.command in ('resume', 'gate', 'manifest'):
            state = read(state_path(root))
            need(state.get('schema_version') in (1, 2), 'Unsupported schema version.')
            if args.command == 'resume':
                result = resume(root, state, args.requirement)
            else:
                need(bool(args.items), '--items required.')
                result = (gate(root, state, args.items) if args.command == 'gate'
                          else manifest(state, args.items, args.requirement))
        else:
            with transaction(root) as (state, rollback):
                if args.command == 'snapshot':
                    result = snapshot(root, state, args.file)
                elif args.command == 'new':
                    result = new(state, data)
                elif args.command == 'configure':
                    result = configure(state, data)
                elif args.command == 'replan':
                    result = replan(state, data)
                elif args.command == 'put':
                    result = put(root, state, data, rollback)
                elif args.command == 'record':
                    result = record(root, state, data)
                elif args.command == 'question':
                    result = question(root, state, data)
                elif args.command == 'checkpoint':
                    result = checkpoint(state, data)
                elif args.command == 'promote':
                    need(args.items and len(args.items) == 1, 'promote accepts one item.')
                    result = promote(root, state, args.items[0])
                elif args.command == 'impact':
                    result = impact(root, state, data)
                elif args.command == 'handoff':
                    result = handoff(root, state, data)
                elif args.command == 'delivery-check':
                    result = delivery_check(root, state, data)
                elif args.command == 'views':
                    # Explicit repair must run even when metadata is unchanged.
                    # No-op configure still leaves both metadata and views untouched.
                    result = {'rebuilt': True, **render_views(root, state)}
                else:
                    result = deliver(root, state, data, rollback)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not (args.command == 'gate' and not result['pass']) else 2
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

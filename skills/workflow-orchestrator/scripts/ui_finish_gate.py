"""Read-only validation of a UI review packet and its prescribed next action.

Checks files, hashes and decision structure, not visual quality, reviewer isolation
or human approval. It never changes workspace state or grants user validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def object_value(value, label):
    need(isinstance(value, dict), label + ' must be an object.')
    return value


def json_object(path, label):
    def unique_keys(pairs):
        value = {}
        for key, item in pairs:
            need(key not in value, 'Duplicate JSON key: ' + key)
            value[key] = item
        return value

    def invalid_constant(value):
        raise ValueError('Invalid JSON constant: ' + value)

    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'),
                           object_pairs_hook=unique_keys, parse_constant=invalid_constant)
    except RecursionError as exc:
        raise ValueError(label + ' JSON nesting is too deep.') from exc
    return object_value(value, label)


def file_entry(root, entry):
    object_value(entry, 'File entry')
    relative = entry.get('path')
    need(nonempty(relative) and not Path(relative).is_absolute(), 'Evidence path must be relative.')
    path = (root / relative).resolve()
    need(path.is_relative_to(root), 'Evidence path escapes project root.')
    need(path.is_file(), 'Evidence file missing: ' + relative)
    need(entry.get('sha256') == digest(path), 'Evidence hash mismatch: ' + relative)
    return path


def revised_files(root, entries, frozen_paths, frozen_hashes):
    need(isinstance(entries, list) and entries, 'Final implementation and screenshots required.')
    roles = set()
    paths = set()
    changed = {}
    for entry in entries:
        path = file_entry(root, entry)
        need(path not in paths, 'Duplicate final evidence path.')
        need(path not in frozen_paths, 'Final evidence needs a new path outside the frozen packet files.')
        role = entry.get('role')
        need(nonempty(role), 'Final evidence role required.')
        paths.add(path)
        roles.add(role)
        if entry['sha256'] not in frozen_hashes:
            changed[path] = role
    need({'implementation', 'screenshot'} <= roles, 'Final implementation and screenshots must be identified.')
    return changed


def check(root, report_path, fixes_path=None):
    root = root.resolve()
    need(root.is_dir(), 'Project root must be an existing directory.')
    report = json_object(report_path, 'Review report')
    need(type(report.get('schema_version')) is int and report['schema_version'] == 1,
         'Unsupported review schema.')
    reviewer = object_value(report.get('reviewer'), 'Reviewer')
    need(reviewer.get('role') == 'UI Finish-Gate Reviewer', 'Unexpected reviewer role.')
    need(reviewer.get('isolated') is True and nonempty(reviewer.get('session')), 'Isolated reviewer session required.')
    packet = object_value(report.get('packet'), 'Packet')
    for field in ('id', 'material_version', 'prototype_version'):
        need(nonempty(packet.get(field)), 'Missing packet field: ' + field)
    need(packet.get('material_status') == 'ready', 'Materials must pass A01 before implementation review.')
    evidence = packet.get('files')
    need(isinstance(evidence, list) and evidence, 'Frozen packet files required.')
    observed = {}
    resolved_paths = set()
    roles = set()
    for entry in evidence:
        path = file_entry(root, entry)
        need(nonempty(entry.get('role')), 'Evidence role required.')
        need(path not in resolved_paths, 'Duplicate packet evidence path.')
        resolved_paths.add(path)
        observed[entry['path']] = entry['sha256']
        roles.add(entry['role'])
    need({'standards', 'implementation', 'screenshot', 'comparison'} <= roles,
         'Packet needs standards, implementation, screenshot and comparison evidence.')

    conclusions = object_value(report.get('conclusions'), 'Conclusions')
    verdict = conclusions.get('verdict')
    need(verdict in ('go', 'no-go', 'conditions-go'), 'Invalid finish verdict.')
    categories = ('functional', 'brand_visual', 'platform_adaptation', 'user_validation')
    for category in categories:
        conclusion = conclusions.get(category)
        need(isinstance(conclusion, dict), 'Missing conclusion: ' + category)
        allowed = ('verified', 'waived', 'pending') if category == 'user_validation' else ('pass', 'fail', 'pending', 'not-applicable', 'conditions')
        need(conclusion.get('status') in allowed, 'Invalid category status: ' + category)
        need(nonempty(conclusion.get('scope')) and nonempty(conclusion.get('note')), 'Scope and note required: ' + category)
        links = conclusion.get('evidence')
        need(isinstance(links, list) and links, 'Evidence references required: ' + category)
        need(all(isinstance(link, str) and link in observed for link in links), 'Unknown conclusion evidence: ' + category)
    # UI gate success cannot hide known visual/platform defects. Function and real
    # user verification remain separate, and must be checked by their own workflow.
    if verdict == 'go':
        need(conclusions['brand_visual']['status'] == 'pass', 'go needs a passing brand-visual conclusion.')
        need(conclusions['platform_adaptation']['status'] in ('pass', 'not-applicable'), 'go needs a resolved platform conclusion.')
    if verdict == 'conditions-go':
        need(all(conclusions[k]['status'] not in ('fail', 'pending') for k in ('brand_visual', 'platform_adaptation')),
             'Unresolved visual/platform blockers require no-go, not conditional passage.')

    opinions = report.get('opinions')
    need(isinstance(opinions, list), 'Opinions must be an array.')
    by_id = {}
    for opinion in opinions:
        need(isinstance(opinion, dict), 'Opinion must be an object.')
        for key in ('id', 'target', 'problem', 'requested_change', 'acceptance_criteria'):
            need(nonempty(opinion.get(key)), 'Missing opinion field: ' + key)
        need(type(opinion.get('required')) is bool, 'Opinion required must be boolean.')
        if 'required_changed_roles' in opinion:
            expected = opinion['required_changed_roles']
            need(isinstance(expected, list) and expected
                 and all(role in ('implementation', 'screenshot', 'comparison') for role in expected),
                 'required_changed_roles must list implementation, screenshot or comparison.')
        need(opinion['id'] not in by_id, 'Duplicate opinion ID.')
        by_id[opinion['id']] = opinion
    required = {key for key, opinion in by_id.items() if opinion['required']}
    need(not (verdict == 'go' and required), 'go cannot leave required changes.')
    need(not (verdict != 'go' and not required), 'Non-go verdict must identify concrete required changes.')
    need(not fixes_path or verdict == 'conditions-go', 'Fix closure only applies to conditions-go; no-go needs a new isolated review.')

    passed = verdict == 'go'
    next_action = {'go': 'continue_with_separate_functional_and_user_checks',
                   'no-go': 'revise_then_new_isolated_review_without_round_limit',
                   'conditions-go': 'implement_this_round_conditions_once_without_new_review'}[verdict]
    if fixes_path:
        fixes = json_object(fixes_path, 'Fix closure')
        need(fixes.get('report_sha256') == digest(report_path), 'Fixes refer to a different review report.')
        need(fixes.get('packet_id') == packet['id'], 'Fixes refer to a different packet.')
        need(type(fixes.get('round')) is int and fixes['round'] == 1, 'conditions-go has exactly one implementation pass.')
        need(fixes.get('verification_kind') == 'implementation-check', 'Closure is execution verification, not a new expert review.')
        changes = fixes.get('changes')
        need(isinstance(changes, list), 'Changes must be a list.')
        changed_files = revised_files(root, fixes.get('after_files'), resolved_paths, set(observed.values()))
        done = set()
        for change in changes:
            object_value(change, 'Change')
            identifier = change.get('opinion_id')
            need(nonempty(identifier) and identifier in by_id and identifier not in done,
                 'Unknown or repeated opinion in closure.')
            need(change.get('status') == 'done' and nonempty(change.get('note')), 'Each listed condition must actually be implemented.')
            proof = change.get('evidence')
            need(isinstance(proof, list) and proof, 'Implementation evidence required.')
            cited = {file_entry(root, entry) for entry in proof}
            changed_roles = {changed_files[path] for path in cited if path in changed_files}
            expected = by_id[identifier].get('required_changed_roles')
            if expected:
                need(set(expected) <= changed_roles, 'Missing revised evidence for opinion: ' + identifier)
            else:
                # Original schema-v1 opinions normally describe a visual change.
                # They may point only at the new screenshot in a complete fixes packet.
                need({'implementation', 'screenshot'} <= set(changed_files.values()),
                     'Visual fixes need changed implementation and screenshot content.')
                need(bool(changed_roles & {'implementation', 'screenshot'}),
                     'Opinion must cite its revised implementation or screenshot: ' + identifier)
            done.add(identifier)
        need(required <= done, 'Required conditions remain unimplemented.')
        # Standards stay frozen; new standards/scope need their own packet, not
        # a retrospective reinterpretation of this review's conditions.
        need(fixes.get('standards_sha256') == {e['path']: e['sha256'] for e in evidence if e['role'] == 'standards'},
             'Standards changed or were not bound to the original packet.')
        passed = True
        next_action = 'conditions_implemented_continue_without_new_expert_review'
    return {'structure_valid': True, 'review_verdict': verdict, 'ui_finish_gate_passed': passed,
            'next_action': next_action, 'conclusions': conclusions,
            'stage_approval_granted': False, 'user_validation_granted': False,
            'limit': 'Checks supplied records and hashes only; does not attest visual quality, isolation, actual viewing, or human authority.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--fixes', type=Path)
    args = parser.parse_args()
    try:
        result = check(args.root, args.report, args.fixes)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'structure_valid': False, 'error': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ui_finish_gate_passed'] else 2


if __name__ == '__main__':
    sys.exit(main())

"""Read-only review-entry dependency check. Does not execute browser tasks or grant approval."""
import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.ids, self.styles = [], set(), []
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'):
            self.ids.add(a['id'])
        if tag == 'a' and a.get('name'):
            self.ids.add(a['name'])
        if a.get('style'):
            self.styles.append(a['style'])
        if tag == 'style':
            self.in_style = True
        if tag == 'base':
            self.links.append((a.get('href', ''), 'base'))
        for key in ('href', 'src', 'poster', 'data'):
            if key in a and (key != 'data' or tag == 'object'):
                kind = 'asset' if key != 'href' or tag == 'link' else 'link'
                if tag != 'base':
                    self.links.append((a[key], kind))
        for part in a.get('srcset', '').split(','):
            if part.strip():
                self.links.append((part.strip().split()[0], 'asset'))

    def handle_endtag(self, tag):
        if tag == 'style':
            self.in_style = False

    def handle_data(self, data):
        if self.in_style:
            self.styles.append(data)


def css_links(text):
    urls = [x.strip(' \t\n\'"') for x in re.findall(r'url\(\s*([^)]*)\)', text, re.I)]
    urls += re.findall(r'@import\s+[\'"]([^\'"]+)[\'"]', text, re.I)
    return [(x, 'asset') for x in urls]


def inspect(root, entry):
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('root must be a directory')
    start = (root / entry).resolve()
    if not start.is_relative_to(root) or not start.is_file():
        raise ValueError('entry must be an existing file inside root')
    queue, seen, errors, external, fragments = deque([start]), {}, [], [], []
    while queue:
        path = queue.popleft()
        if path in seen:
            continue
        relative = path.relative_to(root).as_posix()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            errors.append({'file': relative, 'error': str(exc)})
            continue
        seen[path] = {'path': relative, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        suffix = path.suffix.lower()
        if suffix not in ('.html', '.htm', '.md', '.css'):
            continue
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            errors.append({'file': relative, 'error': 'text is not UTF-8'})
            continue
        if suffix in ('.html', '.htm'):
            page = Page()
            page.feed(text)
            links = page.links + [link for style in page.styles for link in css_links(style)]
            seen[path]['anchors'] = sorted(page.ids)
        elif suffix == '.css':
            links = css_links(text)
        else:
            # Ignore fenced code: template examples are not outgoing document links.
            text = re.sub(r'(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$', '', text)
            links = [(m.group(1) or m.group(2), 'asset' if m.group(0).startswith('!') else 'link')
                     for m in re.finditer(r'!?\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+[\'"][^\n]*?[\'"])?\s*\)', text)]
        for target, kind in links:
            if not target:
                continue
            try:
                url = urlsplit(target)
            except ValueError:
                errors.append({'file': relative, 'target': target, 'error': 'invalid URL'})
                continue
            if kind == 'base':
                errors.append({'file': relative, 'target': target, 'error': 'base href changes portable relative links'})
                continue
            if url.scheme or url.netloc:
                if url.scheme in ('http', 'https') or url.netloc:
                    external.append({'file': relative, 'target': target, 'kind': kind})
                    if kind == 'asset':
                        errors.append({'file': relative, 'target': target, 'error': 'external asset required; offline use not established'})
                elif url.scheme in ('mailto', 'tel') and kind == 'link':
                    pass
                elif url.scheme == 'data' and kind == 'asset':
                    pass
                else:
                    errors.append({'file': relative, 'target': target, 'error': 'non-portable or unsupported URL scheme'})
                continue
            decoded = unquote(url.path)
            destination = (path.parent / decoded).resolve() if decoded else path
            if not destination.is_relative_to(root):
                errors.append({'file': relative, 'target': target, 'error': 'local link escapes root'})
                continue
            if not destination.is_file():
                errors.append({'file': relative, 'target': target, 'error': 'local target missing or is a directory'})
                continue
            queue.append(destination)
            if url.fragment and destination.suffix.lower() in ('.html', '.htm'):
                fragments.append((relative, target, destination, unquote(url.fragment)))
    for source, target, destination, anchor in fragments:
        if destination in seen and anchor not in seen[destination].get('anchors', []):
            errors.append({'file': source, 'target': target, 'error': 'HTML anchor missing'})
    return {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'root': str(root), 'entry': start.relative_to(root).as_posix(),
        'structure_pass': not errors, 'files': sorted(seen.values(), key=lambda x: x['path']),
        'errors': errors, 'external_links': external,
        'browser_task_validation': 'not_run', 'recipient_access': 'not_verified',
        'human_validation': 'not_verified', 'delivery_approval': 'not_granted',
        'limits': 'Checks recognized local Markdown/HTML/CSS links and assets only. Markdown reference-style links/anchors, dynamically generated URLs, external link availability, business behavior, actual browser opening, visual correctness, recipient ACL, human validation and approval require separate evidence.'
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--entry', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.report.is_symlink():
            raise ValueError('report must not be a symbolic link')
        destination = args.report.resolve()
        if destination.is_relative_to(args.root.resolve()):
            raise ValueError('report must be outside the checked directory')
        if not destination.parent.is_dir():
            raise ValueError('report parent directory must already exist')
        result = inspect(args.root, args.entry)
        # Never overwrite an existing file, even when it is outside the checked tree.
        with destination.open('x', encoding='utf-8') as report:
            report.write(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps({'structure_pass': result['structure_pass'], 'files': len(result['files']),
                          'errors': result['errors'], 'report': str(destination)}, ensure_ascii=False))
        return 0 if result['structure_pass'] else 2
    except (OSError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

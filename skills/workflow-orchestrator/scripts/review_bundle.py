"""Freeze an explicitly selected review folder with its relative links intact."""
import hashlib
import html
from html.parser import HTMLParser
import os
from pathlib import Path, PureWindowsPath
import posixpath
import re
import shutil
import tempfile
import time
from urllib.parse import unquote, urlsplit


FENCED_EXAMPLE = re.compile(r'(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[ \t]*$')
MARKDOWN_LITERALS = re.compile(
    r'(?P<fenced>^ {0,3}(?P<backticks>`{3,})[^\n`]*\n.*?'
    r'(?:^ {0,3}(?P=backticks)`*[ \t]*(?=\n|\Z)|\Z)'
    r'|^ {0,3}(?P<tildes>~{3,})[^\n]*\n.*?'
    r'(?:^ {0,3}(?P=tildes)~*[ \t]*(?=\n|\Z)|\Z))'
    r'|(?P<comment><!--.*?(?:-->|\Z))'
    r'|(?P<inline>(?<!`)(?P<ticks>`+)(?!`).*?(?<!`)(?P=ticks)(?!`))'
    r'|(?P<indented>(?:\A|(?<=\n\n))(?: {4}|\t)[^\n]*'
    r'(?:\n(?:(?: {4}|\t)[^\n]*|[ \t]*(?=\n|\Z)))*)', re.M | re.S)


def markdown_reading_text(text):
    """Remove literal/hidden examples without joining adjacent Markdown tokens.

    Match in source order: a comment marker inside code is literal, and a code
    fence inside a comment cannot swallow a visible link after the comment.
    """
    def visible(match):
        if match.group('indented'):
            # Four spaces can be a real list continuation rather than code.
            # Retain continuations below the list's additional four-space code
            # indent; ordinary indented paragraphs don't start code without a
            # preceding blank line and aren't matched in the first place.
            current_indent = len(match[0].expandtabs(4)) - len(match[0].expandtabs(4).lstrip(' '))
            for line in reversed(text[:match.start()].splitlines()):
                if not line.strip():
                    continue
                expanded = line.expandtabs(4)
                marker = re.match(r'^( *)(?:[-+*]|\d{1,9}[.)]) +', expanded)
                if marker:
                    if len(marker[0]) <= current_indent < len(marker[0]) + 4:
                        # Recheck within the list container so comments/code in
                        # a visible continuation cannot become reading links.
                        width = len(marker[0])
                        nested = '\n'.join(line[width:] if line.startswith(' ' * width) else line
                                           for line in match[0].expandtabs(4).split('\n'))
                        return markdown_reading_text(nested)
                    break
                if not expanded.startswith(' '):
                    break
        return re.sub(r'[^\n]', ' ', match[0])
    return MARKDOWN_LITERALS.sub(visible, text)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_name(value):
    require(isinstance(value, str) and value.strip(), 'Missing review file name.')
    name = value.replace('\\', '/')
    require(not PureWindowsPath(name).anchor and not any(
        not part or part.endswith((' ', '.')) or PureWindowsPath(part).is_reserved()
        or re.search(r'[<>:"|?*\x00-\x1f]', part) for part in name.split('/')), 'Unsafe review file name: ' + name)
    return name


def css_refs(text):
    css = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    for match in re.finditer(r"""url\(\s*(?:'([^']*)'|"([^"]*)"|([^)'"]+))\s*\)|@import\s+['"]([^'"]+)['"]""", css, re.I):
        yield next(value.strip() for value in match.groups() if value is not None), False


class HtmlRefs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.in_style = False
        self.in_head = False
        self.in_script = False
        self.in_title = False
        self.has_surface = False

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if tag == 'head':
            self.in_head = True
        elif tag == 'body':
            self.in_head = False
        self.in_script = tag == 'script'
        self.in_title = tag == 'title'
        if self.in_script and attrs.get('src'):
            self.has_surface = True
        if not self.in_head and tag in ('img', 'svg', 'canvas', 'input', 'select', 'textarea',
                                       'button', 'iframe', 'object', 'embed', 'audio', 'video'):
            self.has_surface = True
        require(tag != 'base' or not attrs.get('href'), 'Use document-relative links, without an HTML base URL.')
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        if tag == 'a' and attrs.get('name'):
            self.ids.add(attrs['name'])
        for key in ('href', 'src', 'poster', 'data' if tag == 'object' else 'xlink:href'):
            if attrs.get(key):
                self.links.append((attrs[key], tag in ('a', 'area') and key == 'href'))
        if attrs.get('srcset'):
            for src in re.findall(r'(?:^|,\s*)\s*((?:data:[^\s]+|[^\s,]+))', attrs['srcset']):
                self.links.append((src, False))
        self.links.extend(css_refs(attrs.get('style') or ''))
        self.in_style = tag == 'style'

    def handle_endtag(self, tag):
        if tag == 'head':
            self.in_head = False
        if tag == 'script':
            self.in_script = False
        if tag == 'title':
            self.in_title = False
        if tag == 'style':
            self.in_style = False

    def handle_data(self, data):
        if data.strip() and (self.in_script or not (self.in_head or self.in_style or self.in_title)):
            self.has_surface = True
        if self.in_style:
            self.links.extend(css_refs(data))


def document_links(name, payload):
    suffix = Path(name).suffix.lower()
    if suffix not in ('.md', '.html', '.htm', '.css', '.svg'):
        return [], set(), bool(payload.decode('utf-8-sig', errors='replace').strip()) if suffix in (
            '.txt', '.json', '.csv') else bool(payload.strip())
    text = payload.decode('utf-8-sig').replace('\r\n', '\n')
    has_text = bool(text.strip())
    if suffix == '.css':
        return list(css_refs(text)), set(), bool(text.strip())
    parser = HtmlRefs()
    links = []
    if suffix == '.md':
        # These literal examples aren't clickable in the review reader.
        text = markdown_reading_text(text)
        destination = r'(?:<([^>\n]+)>|((?:[^\s()]|\([^()]*\))+))'
        pattern = r'(!?)\[[^\]\n]*\]\(\s*' + destination + r"""(?:\s+(?:"[^"]*"|'[^']*'))?\s*\)"""
        for m in re.finditer(pattern, text):
            links.append((html.unescape(m[2] or m[3]), not m[1]))
        definitions = {}
        for m in re.finditer(r'(?m)^ {0,3}\[([^\]]+)\]:\s*' + destination, text):
            definitions[m[1].casefold()] = m[2] or m[3]
        for m in re.finditer(r'(!?)\[([^\]\n]+)\](?:\[([^\]\n]*)\])?(?![(:])', text):
            target = definitions.get((m[3] or m[2]).casefold())
            if target:
                links.append((target, not m[1]))
    parser.feed(text)
    parser.close()
    return links + parser.links, parser.ids, parser.has_surface if suffix in ('.html', '.htm') else has_text


def targets(name, payload):
    links, ids, has_content = document_links(name, payload)
    local = []
    for raw, clickable in links:
        uri = urlsplit(raw.strip())
        if uri.scheme in ('https', 'http', 'mailto', 'tel', 'data') or (
                not uri.scheme and uri.netloc and raw.startswith('//')):
            continue
        path = unquote(uri.path).replace('\\', '/')
        require(not uri.scheme and not PureWindowsPath(path).anchor and ':' not in path,
                f'{name}: nonportable reference: {raw}')
        target = posixpath.normpath(posixpath.join(posixpath.dirname(name), path)) if path else name
        require(target != '..' and not target.startswith('../'), f'{name}: link leaves review bundle: {raw}')
        local.append((target, clickable, unquote(uri.fragment)))
    return local, ids, has_content


def layout_in_body(body, heading):
    if not isinstance(heading, str) or not heading.strip():
        return False
    text = FENCED_EXAMPLE.sub('', body.decode('utf-8-sig').replace('\r\n', '\n'))
    match = re.search(r'(?m)^(#{1,6})[ \t]+' + re.escape(heading.strip()) + r'[ \t]*$', text)
    if not match:
        return False
    section = re.split(r'(?m)^#{1,' + str(len(match[1])) + r'}\s+', text[match.end():], maxsplit=1)[0]
    return bool(section.strip())


def reading_files(graph, start):
    reached = set()
    queue = [start]
    while queue:
        current = queue.pop()
        if current not in reached:
            reached.add(current)
            queue.extend(target for target, clickable, _ in graph[current] if clickable)
    return reached


def validate(kind, body, members, roles, heading):
    """Check all local resources, then follow actual reading links from this body."""
    graph = {}
    anchors = {}
    populated = {}
    for name, content in members.items():
        graph[name], anchors[name], populated[name] = targets(name, content)
    for name, links in graph.items():
        for target, _, fragment in links:
            require(target in members, f'{name}: missing registered review file: {target}')
            if fragment and Path(target).suffix.lower() in ('.html', '.htm', '.svg'):
                require(fragment in anchors[target], f'{name}: missing anchor: {target}#{fragment}')
    reached = reading_files(graph, body)
    required = (('srs',) if kind == 'T05' else ('prototype',) if kind == 'P04'
                else ('prototype', 'operations') + (('layout',) if kind == 'T03' else ()))
    if kind == 'T05':
        specifications = [name for name, role in roles.items() if role == 'srs']
        require(len(specifications) == 1, 'T05: register exactly one SRS file.')
        require(body in reading_files(graph, specifications[0]), 'T05: SRS needs a reading link back to PRD.')
    for role in required:
        if role == 'layout' and layout_in_body(members[body], heading):
            continue
        choices = [name for name, value in roles.items() if value == role and name in reached]
        require(choices, f'{kind}: registered body needs a reading link to {role}.')
        for name in choices:
            allowed = {'prototype': ('.html', '.htm'), 'layout': ('.md', '.html', '.htm', '.pdf'),
                       'operations': ('.md', '.json', '.txt', '.csv', '.html', '.htm'), 'srs': ('.md',)}
            require(Path(name).suffix.lower() in allowed[role] and populated[name],
                    f'{kind}: invalid {role} file: {name}')


def entries(kind, spec, body_path):
    require(kind in ('T02', 'T03', 'P04', 'T05') and isinstance(spec, dict),
            'review_bundle applies to T02/T03/P04/T05.')
    base = Path(spec['root']).resolve(strict=True)
    require(base.is_dir() and body_path.is_relative_to(base), 'Review body must be inside selected root.')
    body = file_name(body_path.relative_to(base).as_posix())
    require(Path(body).suffix.lower() == '.md', 'Review body must be Markdown.')
    members = {body: body_path.read_bytes()}
    labels = {}
    require(isinstance(spec.get('files'), list), 'review_bundle.files must be a list.')
    for row in spec['files']:
        name = file_name(row['path'])
        require(name.casefold() not in {key.casefold() for key in members}, 'Duplicate review file: ' + name)
        path = (base / name).resolve(strict=True)
        require(path.is_relative_to(base) and path.is_file(), 'Review input escapes selected root: ' + name)
        role = row['role']
        allowed_roles = (('srs', 'support') if kind == 'T05' else ('prototype', 'support') if kind == 'P04'
                         else ('prototype', 'operations', 'layout', 'support'))
        require(role in allowed_roles and
                isinstance(row.get('locator'), str) and row['locator'].strip(), 'Review role and locator required.')
        members[name] = path.read_bytes()
        labels[name] = (role, row['locator'])
    validate(kind, body, members, {name: pair[0] for name, pair in labels.items()}, spec.get('layout_heading'))
    return body, members, labels


def windows_file_operation(action, retryable, failure_message):
    for delay in (0, 0.05, 0.12, 0.25, 0.5):
        if delay:
            time.sleep(delay)
        try:
            return action()
        except OSError as exc:
            if getattr(exc, 'winerror', None) not in (5, 32, 33) or not retryable():
                raise
            last_error = exc
    raise OSError(failure_message) from last_error


def remove_version(dest):
    if dest.exists():
        windows_file_operation(lambda: shutil.rmtree(dest), lambda: dest.is_dir() and not dest.is_symlink(),
                               f'临时占用导致回滚未完成。关闭正在使用此版本的程序，检查未登记目录 {dest} 后再试。')


def write_version(dest, members, rollback):
    dest.parent.mkdir(parents=True, exist_ok=True)
    require(not os.path.lexists(dest), 'Review version directory already exists; inspect before retrying.')
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix='.review-') as temp:
        staging = Path(temp) / 'files'
        for name, content in members.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        def publish():
            require(not os.path.lexists(dest), 'Review version directory already exists; inspect before retrying.')
            staging.rename(dest)

        windows_file_operation(publish, lambda: staging.is_dir() and not os.path.lexists(dest),
                               f'暂时无法保存审核版本。关闭占用目录的预览或同步程序后，使用同一请求重试：{dest}')
        rollback.callback(remove_version, dest)


def validate_p04_snapshot(root, body_name, body_content, attachments):
    """Validate legacy/single-file P04 paths before put writes any version files.

    Names are final project-relative paths, not work-draft paths. An existing local
    file is not enough: every local target must be included in the evidence map.
    """
    root = root.resolve()
    body_name = file_name(body_name)
    members = {body_name: body_content}
    roles = {}
    names = {body_name.casefold()}
    for row in attachments:
        name = file_name(row['path'])
        require(name.casefold() not in names, 'Duplicate P04 registered file: ' + name)
        names.add(name.casefold())
        path = (root / name).resolve(strict=True)
        require(path.is_relative_to(root) and path.is_file(), 'P04 attachment outside project: ' + name)
        content = path.read_bytes()
        require(hashlib.sha256(content).hexdigest() == row['sha256'], 'P04 content changed: ' + name)
        members[name] = content
        if Path(name).suffix.lower() in ('.html', '.htm'):
            roles[name] = 'prototype'
    validate('P04', body_name, members, roles, None)


def registered_problems(root, item):
    if item['type'] not in ('T02', 'T03', 'P04', 'T05') or (item['type'] == 'T05' and 'review_bundle' not in item):
        return []
    spec = item.get('review_bundle')
    if item['type'] == 'P04' and not spec:
        try:
            body = (root / file_name(item['path'])).resolve(strict=True)
            require(body.is_relative_to(root.resolve()), 'P04 body outside project.')
            payload = body.read_bytes()
            require(hashlib.sha256(payload).hexdigest() == item['sha256'], 'P04 body content changed.')
            validate_p04_snapshot(root, item['path'], payload, item['evidence'])
        except (TypeError, KeyError, ValueError, OSError) as exc:
            return [f"{item['id']}: P04 entry/resources need repair in a new version before handoff/delivery: {exc}"]
        return []
    if not spec:
        return [f"{item['id']}: register this version's review_bundle before formal handoff/delivery."]
    try:
        base = (root / file_name(spec['root'])).resolve(strict=True)
        require(base.is_relative_to(root.resolve()), 'Review directory outside project.')
        registered = [(item, None)] + [(e, e['review_role']) for e in item['evidence'] if 'review_role' in e]
        members, roles = {}, {}
        for row, role in registered:
            path = (root / file_name(row['path'])).resolve(strict=True)
            name = path.relative_to(base).as_posix()
            content = path.read_bytes()
            require(hashlib.sha256(content).hexdigest() == row['sha256'], 'Review content changed: ' + name)
            members[name] = content
            if role:
                roles[name] = role
            else:
                body = name
        validate(item['type'], body, members, roles, spec.get('layout_heading'))
    except (TypeError, KeyError, ValueError, OSError) as exc:
        return [f"{item['id']}: {exc}"]
    return []

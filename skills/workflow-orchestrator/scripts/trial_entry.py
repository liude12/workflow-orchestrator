"""A stable, derived reading/trial index. Never creates approvals or changes snapshots."""
import hashlib
import html
import os
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import quote, unquote, urlsplit


TITLES = {'T01': '需求定义', 'T02': '业务模型与业务原型',
          'T03': '功能方案、布局与功能验证原型', 'P04': '打磨后的原型',
          'T04': '原型验证记录', 'T05': 'PRD 与 SRS'}
ORDER = {kind: index for index, kind in enumerate(TITLES)}
LINKS = {'prototype': '试用原型', 'operations': '查看实际操作记录',
         'layout': '查看页面布局', 'srs': '阅读 SRS'}


def intact_file(root, record):
    """Return a verified file and its exact bytes, never re-read unverified content."""
    value = record.get('path')
    if not isinstance(value, str) or not value or PureWindowsPath(value).anchor:
        return None
    relative = Path(value)
    if relative.is_absolute() or '..' in relative.parts:
        return None
    try:
        target = (root / relative).resolve(strict=True)
        if not target.is_relative_to(root.resolve()) or not target.is_file():
            return None
        content = target.read_bytes()
        if hashlib.sha256(content).hexdigest() != record.get('sha256'):
            return None
        return target, content
    except (OSError, ValueError):
        return None


def file_href(target, directory):
    return quote(Path(os.path.relpath(target, directory)).as_posix(), safe='/')


def safe_link(root, directory, record):
    """Resolve only intact registered local files, relative to the derived index."""
    found = intact_file(root, record)
    return file_href(found[0], directory) if found else None


def preview_link(value, source, directory, allowed, preview_targets):
    """Markdown links may use safe HTTPS or this item's verified registered files."""
    if not value or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme:
            if (parts.scheme.lower() == 'https' and parts.hostname
                    and not parts.username and not parts.password and not '\\' in value):
                parts.port  # Reject malformed port numbers before emitting a link.
                return value
            return None
        if parts.netloc or parts.query or not parts.path:
            return None
        path = unquote(parts.path)
        if PureWindowsPath(path).anchor or Path(path).is_absolute():
            return None
        target = (source.parent / path).resolve()
        if target not in allowed:
            return None
        if target in preview_targets:
            return '#' + preview_targets[target]
        result = file_href(target, directory)
        return result + ('#' + quote(unquote(parts.fragment), safe='') if parts.fragment else '')
    except (OSError, ValueError):
        return None


def markdown_preview(content, source, directory, allowed, preview_targets):
    """Small escaped Markdown reader; unsupported syntax stays visible as text."""
    esc = lambda value: html.escape(value, quote=True)

    def inline(value):
        # No raw HTML, images, script, style, event handlers or embedded resources.
        tokens = re.compile(r'`([^`]+)`|(!?)\[([^\]\n]+)\]\(([^\s()]+)\)|\*\*([^*\n]+)\*\*')
        result, start = [], 0
        for match in tokens.finditer(value):
            result.append(esc(value[start:match.start()]))
            if match.group(1) is not None:
                result.append('<code>' + esc(match.group(1)) + '</code>')
            elif match.group(3) is not None:
                link = None if match.group(2) else preview_link(match.group(4), source, directory, allowed, preview_targets)
                result.append('<a href="' + esc(link) + '" rel="noreferrer">' + esc(match.group(3)) + '</a>'
                              if link else esc(match.group(0)))
            else:
                result.append('<strong>' + esc(match.group(5)) + '</strong>')
            start = match.end()
        result.append(esc(value[start:]))
        return ''.join(result)

    def cells(line):
        return [cell.strip() for cell in line.strip().strip('|').split('|')]

    lines, result, i = content.decode('utf-8-sig', errors='replace').splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.lstrip().startswith('```') or line.lstrip().startswith('~~~'):
            fence, block = line.lstrip()[:3], [line]
            i += 1
            while i < len(lines):
                block.append(lines[i]); i += 1
                if block[-1].lstrip().startswith(fence):
                    break
            result.append('<pre>' + esc('\n'.join(block)) + '</pre>')
            continue
        heading = re.match(r'^(#{1,6})\s+(.+)$', line)
        if heading:
            level = len(heading.group(1))
            result.append(f'<h{level}>' + inline(heading.group(2)) + f'</h{level}>')
            i += 1
            continue
        if i + 1 < len(lines) and '|' in line:
            divider = cells(lines[i + 1])
            headers = cells(line)
            if len(headers) == len(divider) and all(re.fullmatch(r':?-{3,}:?', c) for c in divider):
                rows = ['<tr>' + ''.join('<th>' + inline(c) + '</th>' for c in headers) + '</tr>']
                i += 2
                while i < len(lines) and '|' in lines[i] and lines[i].strip():
                    rows.append('<tr>' + ''.join('<td>' + inline(c) + '</td>' for c in cells(lines[i])) + '</tr>')
                    i += 1
                result.append('<div class="table-scroll"><table>' + ''.join(rows) + '</table></div>')
                continue
        listing = re.match(r'^\s*(?:([-+*])|\d+[.)])\s+(.+)$', line)
        if listing:
            tag = 'ul' if listing.group(1) else 'ol'
            rows = []
            while i < len(lines):
                row = re.match(r'^\s*(?:([-+*])|\d+[.)])\s+(.+)$', lines[i])
                if not row or ('ul' if row.group(1) else 'ol') != tag:
                    break
                rows.append('<li>' + inline(row.group(2)) + '</li>'); i += 1
            result.append('<' + tag + '>' + ''.join(rows) + '</' + tag + '>')
            continue
        # Preserve each source line as a readable paragraph; never interpret HTML.
        result.append('<p>' + inline(line) + '</p>')
        i += 1
    return ''.join(result)


def reading_entry(record, label, directory, verified, anchors, preview_targets):
    found = verified.get(record.get('path'))
    if not found:
        return None
    target, content = found
    href = file_href(target, directory)
    esc = lambda value: html.escape(str(value), quote=True)
    if target.suffix.lower() not in ('.md', '.markdown', '.txt', '.log'):
        return '<a href="' + href + '">' + esc(label) + '</a>'
    allowed = {row[0] for row in verified.values()}
    return ('<details class="preview"><summary>' + esc(label) + '（页内预览）</summary>'
            '<p class="preview-note">便捷预览，仅展示本版登记且哈希核对通过的内容；正式内容、格式与版本以原稿为准。'
            '不支持的排版保留为文字。<a download href="' + href + '">打开 / 保存原稿</a></p>'
            '<div class="document" id="' + anchors[record['path']] + '" data-preview-path="' + esc(record['path']) + '">'
            + markdown_preview(content, target, directory, allowed, preview_targets) + '</div></details>')


def card(root, directory, item, state_label, scope=''):
    esc = lambda value: html.escape(str(value), quote=True)
    links = []
    missing = []
    previews = []
    verified = {record['path']: found for record in [item] + item.get('evidence', [])
                if (found := intact_file(root, record)) is not None}
    navigation = []
    seen, seen_paths = set(), {item.get('path')}
    for record in item.get('evidence', []):
        role = record.get('review_role')
        if item.get('type') == 'P04' and Path(record.get('path', '')).suffix.lower() in ('.html', '.htm'):
            role = 'prototype'
        identity = (role, record.get('sha256'))
        if role not in LINKS or identity in seen or record.get('path') in seen_paths:
            continue
        seen.add(identity); seen_paths.add(record.get('path'))
        suffix = '' if sum(r.get('review_role') == role for r in item.get('evidence', [])) <= 1 else ' · ' + Path(record['path']).name
        navigation.append((record, LINKS[role] + suffix))
    anchors, preview_targets = {}, {}
    # Only files that actually get a reading panel receive a preview destination.
    # Scope also keeps the same reused item unique across requirement sections.
    for record in [item] + [record for record, _ in navigation]:
        found = verified.get(record.get('path'))
        if found and found[0].suffix.lower() in ('.md', '.markdown', '.txt', '.log'):
            identity = '\0'.join((scope, str(item['id']), str(item['version']), record['path']))
            anchor = 'preview-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]
            anchors[record['path']] = anchor
            preview_targets.setdefault(found[0], anchor)
    body = reading_entry(item, '阅读本版说明', directory, verified, anchors, preview_targets)
    if body:
        (previews if body.startswith('<details') else links).append(body)
    else:
        missing.append('正文缺失或已变化，请先让 AI 核对')
    # Navigation files alone cannot establish that the recorded checks remain intact.
    proofs = list(item.get('evidence', []))
    for check_record in item.get('checks', {}).values():
        proofs.append(check_record.get('evidence', {}))
        if check_record.get('delegation'):
            proofs.append(check_record['delegation'].get('evidence', {}))
    proofs.extend(row.get('evidence', {}) for row in item.get('approvals', {}).values())
    if item.get('validation'):
        proofs.append(item['validation'].get('evidence', {}))
    if any(safe_link(root, directory, proof) is None for proof in proofs):
        missing.append('附件或质量/批准/验证证据缺失或已变化，原结论需复核')
    for record, label in navigation:
        target = reading_entry(record, label, directory, verified, anchors, preview_targets)
        if target:
            (previews if target.startswith('<details') else links).append(target)
        else:
            missing.append(label + '：文件缺失或已变化')
    if missing:
        state_label = '文件待核对；不可据此认定有效'
    check = item.get('checks', {}).get('I')
    check_note = '尚无已登记的内部检查结果。'
    if check:
        if safe_link(root, directory, check.get('evidence', {})) is None:
            check_note = '内部检查：证据待核对；不沿用原通过结论。'
        else:
            check_note = '内部检查：' + ('通过' if check.get('result') == 'pass' else '未通过') + '。' + str(check.get('conclusion', ''))
    return (f'<article data-item="{esc(item["id"])}" data-version="{esc(item["version"])}">'
            f'<div class="state">{esc(state_label)} · 版本 {esc(item["version"])}</div>'
            f'<h3>{esc(TITLES[item["type"]])}</h3><p>{esc(item.get("title", ""))}</p>'
            f'<div class="links">{"".join(links)}</div>'
            + ''.join(previews)
            + f'<p class="check">{esc(check_note)}</p>'
            + ''.join(f'<p class="missing">{esc(message)}</p>' for message in missing)
            + '</article>')


def render(root, state, directory, *, authority_check=None):
    """Return HTML; the caller supplies current authority checks for exact versions."""
    root, directory = Path(root), Path(directory)
    esc = lambda value: html.escape(str(value), quote=True)
    def authority_label(item, label):
        if authority_check is not None and authority_check(item):
            return '内容版本保留；待授权复核'
        return label
    groups = []
    for req in state.get('requirements', {}).values():
        items = [i for i in state.get('items', {}).values()
                 if i.get('requirement') == req['id'] and i.get('type') in TITLES]
        # Explicitly reused stages remain visible under the receiving requirement.
        selected = {i['id']: (i, None) for i in items}
        for plan in req.get('plan', {}).values():
            if plan.get('mode') == 'reuse':
                for identifier in plan.get('items', []):
                    item = state.get('items', {}).get(identifier)
                    if item and item.get('type') in TITLES:
                        selected.setdefault(identifier, (item, plan.get('versions', {}).get(identifier, 'unknown')))
        cards = []
        for item, pinned in sorted(selected.values(), key=lambda pair: (ORDER[pair[0]['type']], pair[0]['id'])):
            if pinned is not None:
                chosen = next((v for v in [item] + item.get('history', []) if v['version'] == pinned), None)
                if chosen:
                    label = '计划复用的当前有效版' if item.get('current_valid_version') == pinned else '计划复用版本；当前适用性待复核'
                    cards.append(card(root, directory, chosen, authority_label(chosen, label), req['id']))
                else:
                    cards.append('<article><h3>' + esc(TITLES[item['type']]) + '</h3><p class="missing">计划指定的复用版本未找到，请先让 AI 核对；未自动改用最新稿。</p></article>')
                continue
            valid_version = item.get('current_valid_version')
            if valid_version and valid_version != item['version']:
                valid = next((h for h in item.get('history', []) if h['version'] == valid_version), None)
                if valid:
                    cards.append(card(root, directory, valid, authority_label(valid, '登记为当前有效版'), req['id']))
            label = '登记为当前有效版' if valid_version == item['version'] else '最新候选稿；尚未生效'
            cards.append(card(root, directory, item, authority_label(item, label), req['id']))
        groups.append(f'<section><h2>{esc(req.get("title", req["id"]))}</h2>'
                      f'<p class="meta">目标版本：{esc(req.get("target", "未记录"))}</p>'
                      f'<div class="cards">{"".join(cards) or "<p>尚无已登记成果；本轮工作稿请从当前回复打开。</p>"}</div></section>')
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(state.get("product", "项目"))} · 查看与试用</title>'
            '<style>body{font:16px/1.6 system-ui,"Microsoft YaHei",sans-serif;color:#24364b;background:#f4f7fb;margin:0}'
            'main{max-width:1120px;margin:auto;padding:32px 20px}h1{margin:0;font-size:30px}h2{font-size:23px;margin:30px 0 0}'
            'h3{font-size:20px;margin:10px 0}.meta,.check{color:#59697b}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}'
            'article{background:white;border:1px solid #dce4ee;border-radius:12px;padding:20px;overflow-wrap:anywhere}'
            '.state{font-weight:600;color:#70551c}.links{display:flex;flex-wrap:wrap;gap:10px}a{color:#174c96;padding:8px 10px;border:1px solid #b9cbe3;border-radius:6px;text-decoration:none}'
            '.preview{margin:14px 0;border:1px solid #c9d6e7;border-radius:8px}.preview summary{cursor:pointer;padding:12px;color:#174c96;font-weight:600}'
            '.cards>article:has(.preview[open]){grid-column:1/-1}.preview-note{font-size:13px;color:#59697b;padding:0 14px}.preview-note a{display:inline-block;padding:2px 6px}'
            '.document{padding:0 16px 16px;max-height:70vh;overflow:auto}.document h1{font-size:25px}.document h2{font-size:22px;margin-top:20px}.document h3{font-size:19px}'
            '.document p{margin:10px 0}.document a{padding:0;border:0;text-decoration:underline}.document pre{white-space:pre-wrap;background:#f3f5f8;padding:10px}'
            '.document code{background:#eef1f6;padding:2px 4px}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;min-width:280px}th,td{border:1px solid #c9d6e7;padding:8px;text-align:left}th{background:#edf2f8}'
            'a:hover,a:focus-visible{background:#e9f1fd;outline:2px solid #3575c4}.primary{background:#eef4ff}.missing{color:#a22537}.note{background:#e7eef8;padding:14px 18px;border-radius:8px}</style>'
            '</head><body><main>'
            f'<h1>{esc(state.get("product", "项目"))} · 查看与试用</h1>'
            '<p>先读本版说明中的“本次变化、怎么试、需要你决定什么”，再打开同版原型。</p>'
            '<p class="note">业务验证原型验证业务运转，功能验证原型验证功能承接，S4 原型验证交互体验。'
            '候选稿可以试用，但不代表业务已批准、真人已验证或正式交付完成。</p>'
            + ''.join(groups)
            + f'<footer><p class="meta">由项目记录生成，索引修订 {esc(state.get("revision", ""))}。'
            '沿用此入口；AI 更新记录后刷新页面。原型内使用示例数据，实际操作结果见对应记录。'
            '正式交付以获批包及包内验收为准，本页不替代交付包。</p></footer></main></body></html>')

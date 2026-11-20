"""Read-only atlas projections. No builders, learner stores, network or models."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import threading
from urllib.parse import parse_qsl, urlencode

ROOT = Path(__file__).resolve().parent
DEFAULT_AUDIT_PATH = ROOT.parent.parent / '教育/docs/research/education-tool-evaluation-20261030/graph-evaluation/audit.py'
AUDIT_PATH = Path(os.environ.get('ATLAS_AUDIT_PATH', str(DEFAULT_AUDIT_PATH if DEFAULT_AUDIT_PATH.exists() else ROOT / 'audit.py')))
SCHEMA_VERSION = 1
NODE_LIMIT = 40
EDGE_LIMIT = 80
EXTERNAL_IDS = tuple(f'S{i:02}' for i in range(1, 8))
LOCAL_TITLES = {
    'curriculum': ('高中三科课程', '课程表现目标与研究扩展分列'),
    'foundation': ('初小基础课程', '本地课程设计，不是教材逐字内容'),
    'papers': ('题卷知识关系', '实际题级调用、经验桥与跨题跨卷联系'),
    'thinking': ('思考步骤与机制', '助手研究路径，不是能力测量或学习掌握'),
    'textbooks': ('教材与教辅', '书、已登记章与PDF物理页；不是全书章节审读'),
    'mapping': ('图谱关联映射层', '保留候选、语义判断与缺口；不是独立图谱种类'),
    'ledger': ('知识聚合台账', '已有台账的绑定与状态；不是独立图谱或私有学习记录'),
}
NOTICE = '仅本机只读研究。来源不按同名合并；关系、助手审读与学生掌握分开。图中仅显示有界邻域，搜索和分页覆盖全部节点。'
SUBJECT_LABELS = {'math': '数学', 'Mathematics': '数学', 'english': '英语', 'English': '英语', 'chinese': '语文', 'physics': '物理', 'chemistry': '化学', 'biology': '生物', 'geo': '地理', 'history': '历史', 'politics': '政治', 'unknown': '未登记'}
KINDS = {'knowledge', 'question', 'step', 'mechanism', 'book', 'chapter', 'page', 'mapping', 'unit', 'source', 'experiment'}
KIND_LABELS = dict(zip(('knowledge', 'question', 'step', 'mechanism', 'book', 'chapter', 'page', 'mapping', 'unit', 'source', 'experiment'), ('知识', '题目', '步骤', '机制', '书', '章/节', '物理页', '映射', '单元', '来源实体', '实验')))
PROPERTY_LABELS = {'id': '原ID', 'name': '原名称', 'kind': '原类型', 'type': '原类型', 'label': '原标签/类型', 'grade': '原年级', 'rawGrade': '原始年级字段', 'grades': '原年级列表', 'ageRange': '原年龄范围（不换算年级）', 'gradeNumbers': '明确年级数值', 'stageGroup': '原学段组', 'stage': '原学段', 'subject': '原学科', 'locator': '原定位', 'bookPrefix': '原书前缀', 'isbn': 'ISBN', 'book': '教材名称', 'chapter': '原章节', 'section': '原节', 'mark': '原标记', 'paragraph': '原段落', 'temp': '教材定位原JSON', 'definition': '原定义', 'description': '原描述', 'group': '原分组', 'originGroup': '原来源组'}


def safe_properties(value):
    """Keep original values, excluding credential fields even in nested metadata."""
    if isinstance(value, dict):
        return {k: safe_properties(v) for k, v in value.items()
                if not re.search(r'password|secret|api[_-]?key|access[_-]?token|authorization|cookie|credential', k, re.I)}
    if isinstance(value, (list, tuple)):
        return [safe_properties(v) for v in value]
    return value


def property_details(value):
    return [{'label': PROPERTY_LABELS.get(k, '原属性 · ' + k), 'value': text(v)} for k, v in safe_properties(value).items()]


CONTENT_FIELDS = ('definition', 'description', 'passage', 'attributes', 'examples',
                  'learningObjectives', 'learning_objectives', 'learning objectives', 'objectives', 'stem')
SUPPLEMENT_FILE = 'data/graph-reading-supplement.json'
SUPPLEMENT_ROLE = 'assistant_authored_general_biology_note_待教师复核'


def content_fields(record):
    """Preserve registered top-level and nested content; never join different IDs."""
    if not isinstance(record, dict):
        return {}
    result = {k: safe_properties(record[k]) for k in CONTENT_FIELDS if record.get(k)}
    properties = record.get('properties', {})
    if isinstance(properties, dict):
        result.update(safe_properties(properties))
    return result


def content_description(body):
    return text(next((body[k] for k in CONTENT_FIELDS if body.get(k)), ''))


def load_raw_bodies(source):
    """Read both pinned S02 projections, keeping global fields beside math bodies."""
    if source.sid == 'S02':
        result = {}
        for suffix in [('global_KG', 'nodes.json'), ('subject_specific_KG', 'math.json')]:
            paths = [Path(path) for path in source.files if Path(path).parts[-2:] == suffix]
            if len(paths) != 1:
                raise AtlasError('S02正文登记缺失或重复', 503)
            path = paths[0]
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != source.files[str(path)]['sha256']:
                raise AtlasError('S02正文与来源登记失配', 503)
            document = json.loads(data)
            rows = document if isinstance(document, list) else document['nodes']
            counts = Counter(row['id'] for row in rows)
            for row in rows:
                if counts[row['id']] == 1:
                    body = result.setdefault(row['id'], {})
                    for key, value in content_fields(row).items():
                        body.setdefault(key, value)
        return result
    from review_set_alignment import raw_bodies
    return raw_bodies(source)


def native_kind(raw):
    kind = str(raw).casefold()
    return {'book': 'book', 'chapter': 'chapter', 'section': 'chapter', 'exercise': 'question', 'experiment': 'experiment',
            'concept': 'knowledge', 'conceptual': 'knowledge', 'procedural': 'knowledge', 'skill': 'knowledge',
            'source_topic': 'knowledge', 'source_knowledge_point': 'knowledge', 'application': 'knowledge',
            'reasoning': 'knowledge', 'modeling': 'knowledge', 'language': 'knowledge', 'representational': 'knowledge'}.get(kind, 'source')
MAPPING_FILES = ('六题图谱映射.json', '小初高补充映射.json', '网盘补充映射.json', 'K12关联与解析核验.json')


def point_subject(value):
    """Only explicit subject fields or language namespaces infer language identity."""
    explicit = value.get('courseSubject') or value.get('subject')
    if explicit:
        return explicit
    identifier = value.get('id', '')
    for prefixes, subject in [(('chinese-', 'zh-', 'cn-'), 'chinese'), (('english-', 'en-'), 'english'), (('m-', 'math-'), 'math')]:
        if identifier.startswith(prefixes):
            return subject
    return 'unknown'


def printed_question_label(question):
    printed = text(question.get('printedNumber', question['number']))
    if re.fullmatch(r'\d+', printed):
        return f'第{printed}题'
    return printed


class AtlasError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.http_status = status


def text(value):
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return '；'.join(text(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def parse_params(query, *, catalog=False):
    """Validate raw query, including duplicates, bad escapes and empty values."""
    if not isinstance(query, str) or len(query) > 20000 or re.search(r'%(?![0-9a-fA-F]{2})', query):
        raise AtlasError('查询参数格式无效')
    try:
        rows = parse_qsl(query, keep_blank_values=True, strict_parsing=True,
                         encoding='utf-8', errors='strict', max_num_fields=16)
    except (ValueError, UnicodeError):
        raise AtlasError('查询参数格式无效') from None
    allowed = set() if catalog else {'graph', 'q', 'subject', 'stage', 'group', 'page', 'size', 'node', 'hops', 'relation', 'edgePage', 'edgeSize', 'kind'}
    result = {}
    for key, value in rows:
        if key not in allowed or key in result:
            raise AtlasError('参数不受支持或重复')
        if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise AtlasError('参数为空或包含控制字符')
        limit = 1024 if key == 'node' else 160
        if len(value) > limit:
            raise AtlasError('参数超过长度上限')
        result[key] = value
    if catalog:
        return result
    result.setdefault('graph', 'curriculum')
    if result['graph'] not in {*EXTERNAL_IDS, *LOCAL_TITLES}:
        raise AtlasError('无效图谱标识')
    for key, default, low, high in [('page', 1, 1, None), ('size', 24, 1, 50), ('hops', 1, 1, 2), ('edgePage', 1, 1, None), ('edgeSize', 8, 1, 50)]:
        value = result.get(key, str(default))
        if not re.fullmatch(r'[1-9][0-9]*', value) or len(value) > 9:
            raise AtlasError('分页或跳数必须为合法正整数')
        result[key] = int(value)
        if result[key] < low or (high is not None and result[key] > high):
            raise AtlasError('分页或跳数超出范围')
    result.setdefault('relation', 'all')
    if len(result['relation']) > 160:
        raise AtlasError('无效关系筛选')
    if result.get('kind') and result['kind'] not in KINDS:
        raise AtlasError('无效节点类型筛选')
    return result


def node(identifier, label, kind='knowledge', **kwargs):
    result = {'id': str(identifier), 'label': text(label), 'kind': kind if kind in KINDS else 'source',
              'subject': text(kwargs.pop('subject', 'unknown')) or 'unknown',
              'stage': text(kwargs.pop('stage', 'unknown')) or 'unknown',
              'group': text(kwargs.pop('group', 'unknown')) or 'unknown',
              'description': text(kwargs.pop('description', ''))}
    for key in ('example', 'notation', 'boundary', 'status'):
        if kwargs.get(key):
            result[key] = text(kwargs[key])
    for key in ('keywords', 'source', 'links', 'details'):
        if kwargs.get(key):
            result[key] = kwargs[key]
    return result


class Projection:
    def __init__(self, identifier, title, boundary, version):
        self.id, self.title, self.boundary, self.version = identifier, title, boundary, version
        self.nodes = {}
        self.edges = []
        self.notes = []
        self.prerequisite_supported = True
        self.default = None
        self.meta = {}
        self.incoming = defaultdict(list)
        self.outgoing = defaultdict(list)
        self.originalIncoming = defaultdict(list)
        self.originalOutgoing = defaultdict(list)

    def add(self, value):
        identifier = value['id']
        if identifier in self.nodes:
            old = self.nodes[identifier]
            labels = list(dict.fromkeys([old['label'], value['label']]))
            if len(labels) > 1:
                old['label'] = ' / '.join(labels)
                old['status'] = 'ambiguous：同一原ID有多个标签'
            else:
                # Enrich a candidate placeholder with registered evidence of the same ID.
                for key, item in value.items():
                    if key not in {'id', 'label'} and (not old.get(key) or old.get(key) == 'unknown'):
                        old[key] = item
                if value.get('source'):
                    old['source'] = value['source']
                if value.get('details'):
                    old['details'] = value['details']
                if value.get('description') and old.get('description') == '已登记候选标题，未按名称合并':
                    old['description'] = value['description']
            return old
        self.nodes[identifier] = value
        return value

    def edge(self, source, target, relation, *, label=None, reason='', locator='', status='', boundary='', identifier=None, details=None, source_scope=None,
             original_source=None, original_target=None, original_relation=None, original_label=None):
        edge = {'id': identifier or f'{self.id}:e{len(self.edges)}', 'source': str(source), 'target': str(target),
                'relation': text(relation), 'label': text(label or relation),
                'fromLabel': self.nodes.get(str(source), {}).get('label', str(source)),
                'toLabel': self.nodes.get(str(target), {}).get('label', str(target))}
        edge['originalSource'] = text(source if original_source is None else original_source)
        edge['originalTarget'] = text(target if original_target is None else original_target)
        edge['originalRelation'] = text(relation if original_relation is None else original_relation)
        edge['originalLabel'] = text(label or relation if original_label is None else original_label)
        for key, value in [('reason', reason), ('sourceLocator', locator), ('status', status), ('boundary', boundary)]:
            if value:
                edge[key] = text(value)
        if details:
            edge['details'] = details
        if source_scope:
            edge['source_scope'] = source_scope
        self.edges.append(edge)

    def finish(self):
        for edge in self.edges:
            edge['fromLabel'] = self.nodes.get(edge['source'], {}).get('label', edge['source'])
            edge['toLabel'] = self.nodes.get(edge['target'], {}).get('label', edge['target'])
            self.incoming[edge['target']].append(edge)
            self.outgoing[edge['source']].append(edge)
            self.originalIncoming[edge.get('originalTarget', edge['target'])].append(edge)
            self.originalOutgoing[edge.get('originalSource', edge['source'])].append(edge)
        return self

    def structure(self, selected):
        """Return source-backed location paths, separate from semantic graph edges."""
        if not selected:
            return {'mode': 'none', 'paths': [], 'facets': [], 'note': '', 'truncated': 0}
        stage, subject = selected.get('stage', 'unknown'), selected.get('subject', 'unknown')
        properties = selected.get('originalContent', {}).get('properties', {})

        def detail(*labels):
            for label in labels:
                found = next((row['value'] for row in selected.get('details', []) if row['label'] == label and row['value']), None)
                if found not in (None, ''):
                    return found
            return ''

        def item(label, field, value, *, node_id=None, query=None, kind=''):
            result = {'label': text(label), 'field': field, 'value': text(value)}
            if node_id:
                result['nodeId'] = node_id
                result['kind'] = kind
            if query:
                result['query'] = {key: val for key, val in query.items() if val and val != 'unknown'}
            return result

        def virtual(label, field, value, query_value=None):
            return item(label, field, value, query={'q': query_value or value, 'stage': stage, 'subject': subject})

        current = item(selected['label'], 'knowledge', selected['label'], node_id=selected['id'], kind=selected['kind'])
        base = item(stage, 'stage', stage, query={'stage': stage, 'subject': subject}) if stage not in {'unknown', '多值'} else None
        paths, facets, note, mode = [], [], '', 'metadata'

        if self.id == 'S02':
            # Follow the actual native parent edges, not the bounded visual neighborhood.
            def native_chain(identifier, seen):
                node = self.nodes[identifier]
                here = item(node['label'], node['kind'], node['label'], node_id=identifier, kind=node['kind'])
                parents = [edge for edge in self.outgoing.get(identifier, [])
                           if edge['relation'] in {'appears_in', 'is_part_of'} and edge['target'] in self.nodes]
                if not parents or identifier in seen or len(seen) >= 8:
                    return [[here]]
                result = []
                for edge in parents[:8]:
                    for prefix in native_chain(edge['target'], seen | {identifier}):
                        result.append([*prefix, here])
                return result
            chains = native_chain(selected['id'], set())
            paths = [([base] if base else []) + chain for chain in chains[:12]]
            mode, note = 'native', '沿原生 appears_in / is_part_of 返回完整归属；这些不是先备边。'
            return {'mode': mode, 'paths': paths, 'facets': facets, 'note': note,
                    'truncated': max(0, len(chains) - len(paths))}

        if self.id == 'S01':
            domain = properties.get('domain') or detail('原属性 · domain')
            start, end = properties.get('ageRangeStart'), properties.get('ageRangeEnd')
            age = f'{start}–{end}岁' if start not in (None, '') and end not in (None, '') else detail('原年龄范围（不换算年级）')
            chain = [item(subject, 'subject', subject, query={'subject': subject})]
            if domain:
                chain.append(virtual(domain, 'domain', domain))
            if age:
                chain.append(virtual(age, 'age', age))
            chain.append(current)
            paths = [chain]
            mode, note = 'taxonomy', '原始组织是学科领域、年龄范围与先备图；没有教材章节，不换算成年级。'
        elif self.id == 'S03':
            grade = properties.get('grade') or detail('原年级')
            semester = properties.get('semester') or detail('原属性 · semester')
            chapter = properties.get('chapter') or detail('原章节')
            grade_label = f'{grade}年级' if str(grade).isdigit() else text(grade)
            volume = grade_label + (str(semester) + '册' if semester else '')
            chain = [base] if base else []
            if volume:
                chain.append(virtual(volume, 'volume', volume, text(grade)))
            if chapter:
                chain.append(virtual(chapter, 'chapter', chapter))
            chain.append(current)
            paths = [chain]
            domain = properties.get('domain') or detail('原属性 · domain')
            if domain:
                facets.append(item(domain, 'domain', domain))
            note = '按原 grade / semester / chapter 返回归属；先备与 mathLinks 仍在下方分开。'
        elif self.id == 'S04':
            group = selected.get('group', 'unknown')
            root = item(group, 'stageGroup', group, query={'q': group, 'subject': subject}) if group != 'unknown' else base
            grade_start, grade_end = properties.get('gradeRangeStart'), properties.get('gradeRangeEnd')
            grade = f'{grade_start}年级' if grade_start == grade_end and grade_start not in (None, '') else (
                f'{grade_start}–{grade_end}年级' if grade_start not in (None, '') and grade_end not in (None, '') else detail('原年级'))
            codes = properties.get('textbooks') or detail('原属性 · textbooks')
            codes = codes if isinstance(codes, list) else str(codes or '').split('；')
            for code in [text(code) for code in codes if text(code)][:12]:
                chain = [root] if root else []
                if base:
                    chain.append(virtual(stage, 'stage', stage))
                if grade:
                    chain.append(virtual(grade, 'grade', grade))
                chain.extend([virtual(code, 'textbookUnit', code), current])
                paths.append(chain)
            if not paths:
                paths = [[root, current] if root else [current]]
            mode, note = 'metadata', '按原学段、年级范围与教材单元代码显示；未把单元代码改写成未核实的章名。'
        elif self.id == 'S05':
            grade, volume = detail('原年级'), detail('volume')
            chapter = detail('chapter', '原章节')
            chain = [base] if base else []
            if grade:
                chain.append(virtual(grade, 'grade', grade))
            if volume:
                chain.append(virtual(volume, 'volume', volume))
            if chapter:
                chain.append(virtual(chapter, 'chapter', chapter))
            chain.append(current)
            paths = [chain]
            note = '按原学科、年级册次、单元簇返回；对应原项目的年级长卷组织。'
        elif self.id == 'S06':
            textbooks = properties.get('textbooks') or []
            for book in textbooks[:12]:
                if not isinstance(book, dict):
                    continue
                grade = book.get('grade') or text(properties.get('grades', [])) or detail('原年级')
                volume = book.get('volume', '')
                chain = [base] if base else []
                if grade:
                    chain.append(virtual(grade, 'grade', grade))
                if volume:
                    chain.append(virtual(volume, 'volume', volume, book.get('textbook_title') or volume))
                for chapter in book.get('chapter_path') or []:
                    chain.append(virtual(chapter, 'chapter', chapter))
                chain.append(current)
                paths.append(chain)
                if book.get('textbook_title'):
                    facets.append(item(book['textbook_title'], 'textbook', book['textbook_title']))
            if not paths:
                grade = text(properties.get('grades', [])) or detail('原年级')
                paths = [[*([base] if base else []), *([virtual(grade, 'grade', grade)] if grade else []), current]]
            note = '每个教材归属单独成路径；chapter_path 保留章到节顺序，多册不合并为唯一归属。'
        elif self.id == 'S07':
            book, chapter, section = detail('教材名称', '原属性 · book'), detail('原章节', '原属性 · chapter'), detail('原节', '原属性 · section')
            chain = [base] if base else []
            for label, field, value in [(book, 'book', book), (chapter, 'chapter', chapter), (section, 'section', section)]:
                if value:
                    chain.append(virtual(label, field, value))
            chain.append(current)
            paths = [chain]
            note = '这里展示 RDF 教材定位属性；不是先备边，也不代表已经读取教材正文。'
        else:
            paths = [[*([base] if base else []), current]] if base else [[current]]
            note = '当前来源没有额外的学段章节字段；只显示已登记位置，不补造层级。'

        return {'mode': mode, 'paths': paths[:12], 'facets': facets[:12], 'note': note,
                'truncated': max(0, len(paths) - 12)}

    def browse(self, params):
        values = list(self.nodes.values())
        filters = {}
        relation_counts = Counter(e['relation'] for e in self.edges)
        original_relation_counts = Counter(e.get('originalRelation', e['relation']) for e in self.edges)
        filters['relations'] = [{'value': k, 'label': next(e['label'] for e in self.edges if e['relation'] == k), 'count': v} for k, v in sorted(relation_counts.items())]
        filters['originalRelations'] = [{'value': k, 'label': next(e.get('originalLabel', e['label']) for e in self.edges if e.get('originalRelation', e['relation']) == k), 'count': v}
                                        for k, v in sorted(original_relation_counts.items())]
        filters['kinds'] = [{'value': k, 'label': KIND_LABELS[k], 'count': v} for k, v in sorted(Counter(n['kind'] for n in values).items())]
        relation = params['relation']
        raw_relation = relation[4:] if relation.startswith('raw:') else ''
        use_raw = relation == 'all' or bool(raw_relation)
        # Empty supported prerequisite/related filters remain compatible with schema v1.
        if relation != 'all' and not raw_relation and relation not in {'prerequisite', 'related', *relation_counts}:
            raise AtlasError('无效关系筛选；请使用 filters.relations 返回的类型')
        if raw_relation and raw_relation not in original_relation_counts:
            raise AtlasError('无效原始关系筛选；请使用 filters.originalRelations 返回的类型')
        for field, plural in [('subject', 'subjects'), ('stage', 'stages'), ('group', 'groups')]:
            counts = Counter(n[field] for n in values)
            filters[plural] = [{'value': k, 'label': SUBJECT_LABELS.get(k, k) if field == 'subject' else ('未登记' if k == 'unknown' else k), 'count': v}
                               for k, v in sorted(counts.items())]
        q = params.get('q', '').casefold()
        filtered = [n for n in values if all(not params.get(k) or params[k] == n[k] for k in ('subject', 'stage', 'group', 'kind'))
                    and (not q or q in text([n['id'], n['label'], n['description'], n.get('keywords', []), n.get('details', [])]).casefold())]
        notes = [NOTICE, *self.notes]
        page, size = params['page'], params['size']
        pages = (len(filtered) + size - 1) // size
        if page > max(1, pages):
            page = max(1, pages)
            notes.append(f'节点分页越界，已调整至第{page}页；共{pages}页。')
        page_nodes = filtered[(page - 1) * size:page * size]
        selected = None
        if 'node' in params:
            selected = self.nodes.get(params['node'])
            if selected is None:
                raise AtlasError('指定节点未找到；请使用此图返回的完整节点ID', 404)
        elif page_nodes:
            selected = next((n for n in filtered if page == 1 and not params.get('q') and n['id'] == self.default), page_nodes[0])
        relation = params['relation']
        accept = lambda e: relation == 'all' or (e.get('originalRelation', e['relation']) == raw_relation if use_raw else e['relation'] == relation)
        source_of = lambda e: e.get('originalSource', e['source']) if use_raw else e['source']
        target_of = lambda e: e.get('originalTarget', e['target']) if use_raw else e['target']
        incoming = self.originalIncoming if use_raw else self.incoming
        outgoing = self.originalOutgoing if use_raw else self.outgoing
        distance = {}
        adjacent = []
        if selected:
            start = selected['id']
            distance[start] = 0
            # Independent incoming/outgoing breadth-first traversals; cycles never recurse.
            for sign, index, endpoint in [(-1, incoming, 'source'), (1, outgoing, 'target')]:
                seen = {start}
                queue = deque([(start, 0)])
                while queue:
                    current, depth = queue.popleft()
                    if depth >= params['hops']:
                        continue
                    for edge in index.get(current, []):
                        if not accept(edge):
                            continue
                        other = target_of(edge) if endpoint == 'target' else source_of(edge)
                        if other not in self.nodes or other in seen:
                            continue
                        seen.add(other)
                        d = sign * (depth + 1)
                        if other not in distance or abs(d) < abs(distance[other]):
                            distance[other] = d
                        queue.append((other, depth + 1))
            adjacent = [e for e in self.edges if accept(e) and (source_of(e) == start or target_of(e) == start)]
        reached = set(distance)
        neighborhood_edges = [e for e in self.edges if accept(e) and source_of(e) in reached and target_of(e) in reached]
        order = sorted(distance, key=lambda ident: (abs(distance[ident]), self.nodes[ident]['kind'] == 'page', distance[ident], ident))
        shown = set(order[:NODE_LIMIT])
        shown_edges = [e for e in neighborhood_edges if e['source'] in shown and e['target'] in shown][:EDGE_LIMIT]
        # Stable relation pages are independent of the bounded rendered neighborhood.
        adjacent.sort(key=lambda e: e['relation'] in {'physical_page', 'chapter_page'})
        edge_size = params['edgeSize']
        edge_pages = (len(adjacent) + edge_size - 1) // edge_size
        edge_page = params['edgePage']
        if edge_page > max(1, edge_pages):
            edge_page = max(1, edge_pages)
            notes.append(f'关系分页越界，已调整至第{edge_page}页；共{edge_pages}页。')
        relation_page = adjacent[(edge_page - 1) * edge_size:edge_page * edge_size]
        def summary(value):
            # Only selected contains original long attributes; never mutate cached nodes.
            return {k: v for k, v in value.items() if k not in {'details', 'originalContent', 'readingSupplement', 'structureExplanation'}}
        if use_raw:
            notes.append('当前显示原始 rawSource/rawTarget/rawRelation；只有显式选择 prerequisite/related 等导航筛选时才使用归一化索引。')
        if not self.prerequisite_supported:
            notes.append('prerequisite_supported=false；当前读取模式不支持先备关系，不代表没有先备。RDF类型/对齐属性不视为先备。')
        elif relation != 'all' and not any(e['relation'] == relation for e in self.edges):
            notes.append('当前已载图没有登记此类关系，不生成替代边。')
        return {'schemaVersion': SCHEMA_VERSION,
                'graph': {'id': self.id, 'title': self.title, 'boundary': self.boundary, 'version': self.version,
                          'nodeCount': len(self.nodes), 'edgeCount': len(self.edges), 'meta': self.meta},
                'filters': filters,
                'list': {'nodes': [summary(n) for n in page_nodes], 'total': len(filtered), 'page': page, 'size': size, 'pages': pages},
                'selected': selected,
                'structure': self.structure(selected),
                'neighborhood': {'nodes': [dict(summary(self.nodes[i]), distance=distance[i]) for i in order[:NODE_LIMIT]],
                                 'edges': shown_edges, 'totalNodes': len(reached), 'totalEdges': len(neighborhood_edges),
                                 'truncated': len(reached) > len(shown) or len(neighborhood_edges) > len(shown_edges), 'nodeLimit': NODE_LIMIT, 'edgeLimit': EDGE_LIMIT},
                'relations': {'edges': relation_page, 'total': len(adjacent), 'truncated': len(adjacent) > len(relation_page), 'page': edge_page, 'size': edge_size, 'pages': edge_pages},
                'notice': '\n'.join(notes)}


class GraphBrowser:
    def __init__(self, root=ROOT, audit_path=AUDIT_PATH, native_loader=None, bodies_loader=None):
        self.root, self.audit_path = Path(root), Path(audit_path)
        self.native_loader, self.bodies_loader = native_loader, bodies_loader
        self._files = {}
        self._cache = {}
        self._lock = threading.RLock()
        self._source_locks = {sid: threading.Lock() for sid in EXTERNAL_IDS}
        self._audit = None

    def read(self, path, *, javascript=False):
        path = Path(path)
        with self._lock:
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            cached = self._files.get(path)
            if cached and cached[0] == signature and cached[1] is not None:
                return cached[1], cached[2]
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            content = data.decode('utf-8')
            if javascript:
                prefix = 'window.RESEARCH_DATA='
                if not content.startswith(prefix):
                    raise AtlasError('本地研究目录格式失配', 503)
                content = content[len(prefix):].strip().removesuffix(';')
            value = json.loads(content)
            self._files[path] = (signature, value, digest)
            return value, digest

    def data(self):
        return self.read(self.root / 'data/catalog.js', javascript=True)[0]

    def audit(self):
        with self._lock:
            if self._audit is None:
                spec = importlib.util.spec_from_file_location('atlas_readonly_audit', self.audit_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                self._audit = module
            return self._audit

    def version(self, paths):
        digest = hashlib.sha256()
        # Paths are trusted registrations, never request-selected paths.
        for path in sorted(set(map(Path, paths))):
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            with self._lock:
                cached = self._files.get(path)
                if cached and cached[0] == signature:
                    file_digest = cached[2]
                else:
                    h = hashlib.sha256()
                    with path.open('rb') as stream:
                        while chunk := stream.read(1024 * 1024):
                            h.update(chunk)
                    file_digest = h.hexdigest()
                    # Hash-only entries are separate from parsed JSON entries.
                    self._files[path] = (signature, None, file_digest)
            digest.update(str(path).encode())
            digest.update(file_digest.encode())
        return 'sha256:' + digest.hexdigest()

    def checked_material(self, base, relative, sha256, *, allowed=None):
        """Registered files only; signature-cached digest, no private learner reads."""
        base = Path(base).resolve()
        relative = Path(relative)
        if relative.is_absolute() or '..' in relative.parts or not re.fullmatch(r'[a-f0-9]{64}', str(sha256)):
            raise AtlasError('材料登记无效', 409)
        path = base / relative
        resolved = path.resolve()
        allowed = Path(allowed).resolve() if allowed is not None else base
        if not resolved.is_relative_to(allowed) or any(p.is_symlink() for p in [path, *path.parents] if p != base):
            raise AtlasError('材料路径越界或为符号链接', 409)
        if not path.is_file():
            raise AtlasError('登记材料未就绪', 404)
        self.version([path])
        if self._files[path][2] != sha256:
            raise AtlasError('材料与登记SHA-256失配', 409)
        return path

    def static_original(self, relative):
        for entry in self.data()['papers'].values():
            for original in entry['paper'].get('originals', {}).values():
                if relative in {original.get('assetFile'), original.get('staticURL')}:
                    return self.checked_material(self.root, relative, original.get('sha256'))
        raise AtlasError('未登记原材料URL', 404)

    def rdf_bodies(self, source):
        """Parse only the pinned TTL bytes in Source.files; RDF IRIs are values, not URLs to fetch."""
        import rdflib
        audit = self.audit()
        result = defaultdict(list)
        for name, receipt in source.files.items():
            path = Path(name)
            if path.suffix.lower() != '.ttl':
                continue
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != receipt['sha256']:
                raise AtlasError('TTL与来源登记失配', 503)
            rdf = rdflib.Graph()
            rdf.parse(data=data, format='turtle', publicID=audit.RDF_BASE)
            def raw_iri(term):
                value = str(term)
                if value == audit.RDF_BASE:
                    return '<>'
                return value.removeprefix(audit.RDF_BASE_ROOT)
            for subject, predicate, value in sorted(rdf, key=lambda t: tuple(map(str, t))):
                ident = raw_iri(subject)
                pred = str(predicate)
                original = str(value) if isinstance(value, rdflib.Literal) else raw_iri(value)
                short = pred.rsplit('#', 1)[-1]
                label = {'type': 'RDF原类型IRI（非先备）', 'label': 'RDF原标签', 'temp': '教材定位原JSON'}.get(short, 'RDF原属性 · ' + pred)
                result[ident].append({'label': label, 'value': original})
                if short == 'temp':
                    try:
                        metadata = json.loads(original)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(metadata, dict):
                        result[ident].extend(property_details(metadata))
        return result

    def external_registration(self, sid):
        record, _ = self.read(self.root / f'data/graph-coverage/{sid}.json')
        manifest, _ = self.read(self.audit_path.parent / 'logs/input-manifest.json')
        files = next(s['files'] for s in manifest['sources'] if s['sourceId'] == sid)
        paths = [Path(__file__).resolve(), self.audit_path, self.root / f'data/graph-coverage/{sid}.json',
                 self.audit_path.parent / 'topic-index.json', *[f['path'] for f in files]]
        if sid == 'S02':
            paths.append(self.root / SUPPLEMENT_FILE)
        version = self.version(paths)
        return record, version

    def catalog(self, query=''):
        parse_params(query, catalog=True)
        graphs = []
        index, _ = self.read(self.audit_path.parent / 'topic-index.json')
        unique = defaultdict(set)
        for row in index['items']:
            unique[row['sourceId']].add(row['id'])
        for sid in EXTERNAL_IDS:
            record, version = self.external_registration(sid)
            loaded = self._cache.get((sid, version))
            graphs.append({'id': sid, 'title': record['name'], 'subtitle': f"{record['sourceCounts']['nodes']}条源条目；浏览时核对实际加载",
                           'family': 'external', 'nodeCount': len(unique[sid]), 'edgeCount': len(loaded.edges) if loaded else record['sourceCounts']['edges'],
                           'meta': loaded.meta if loaded else {'originalSourceCounts': record['sourceCounts'], 'projectionLoaded': False, 'edgeCountBasis': 'registered_native_edges_auxiliary_pending_lazy_load'},
                           'boundary': '外源独立命名空间；目录为当前登记索引计数，browse核对加载条目/唯一节点/边。只读本地固定快照。',
                           'sourceName': record['name'], 'version': version})
        for identifier, (title, boundary) in LOCAL_TITLES.items():
            graph = self.local(identifier)
            subtitle = boundary
            if identifier == 'curriculum':
                points = self.data()['curriculumPoints'].values()
                regular = sum(p.get('scope') != 'research_extension' for p in points)
                extensions = sum(p.get('scope') == 'research_extension' for p in self.data()['curriculumPoints'].values())
                subtitle = f'{regular}课程节点 + {extensions}研究扩展（不计入课程数）'
            elif identifier == 'papers':
                papers = self.data()['papers']
                subtitle = f"{len(papers)}卷 · {sum(len(e['paper']['questions']) for e in papers.values())}题 · {len(self.data()['concepts'])}已用知识 · {sum(e['relation'] == 'mapping' for e in graph.edges)}调用映射"
            elif identifier == 'textbooks':
                subtitle = f"{len(self.read(self.root / 'data/textbook-catalog.json')[0])}教材 + {len(self.read(self.root / 'data/guidebooks.json')[0])}教辅；只登记实际章"
            graphs.append({'id': identifier, 'title': title, 'subtitle': subtitle,
                           'family': 'supplementary' if identifier in {'mapping', 'ledger'} else 'local',
                           'nodeCount': len(graph.nodes), 'edgeCount': len(graph.edges), 'boundary': boundary, 'version': graph.version})
        counts = Counter(g['family'] for g in graphs)
        return {'schemaVersion': SCHEMA_VERSION, 'version': 'sha256:' + hashlib.sha256(''.join(g['version'] for g in graphs).encode()).hexdigest(),
                'generatedAt': datetime.now(timezone.utc).isoformat(),
                'counts': {'external': counts['external'], 'local': counts['local'], 'browsable': counts['external'] + counts['local'], 'supplementary': counts['supplementary']},
                'graphs': graphs, 'notice': NOTICE + ' mapping与ledger是辅助投影，不算独立图谱种类。外源目录登记与加载计数的差异在browse标明。'}

    def browse(self, query=''):
        params = parse_params(query)
        graph = self.external(params['graph']) if params['graph'] in EXTERNAL_IDS else self.local(params['graph'])
        return graph.browse(params)

    def point(self, value, *, lower=False):
        refs = value.get('sourceRefs', [])
        data = self.data()
        reading = data.get('knowledgeReadings', {}).get(value['id'], {})
        meta = data.get('knowledgeReadingMeta', {})
        description = reading.get('plain') or value.get('definition') or value.get('description') or value.get('performance', '')
        domain = value.get('curriculumDomain', {})
        subject = point_subject(value)
        # The frozen 189-node registration contains only the math curriculum exports.
        # Language fields/namespaces take precedence; unknown future exports stay unknown.
        if lower and subject == 'unknown' and value.get('sourceLocator', '').split(':')[0].endswith(('/shared/curriculum.ts', '/shared/courses/junior.ts', '/shared/courses/junior-extra.ts')):
            subject = 'math'
        details = [{'label': label, 'value': text(value[key])} for key, label in [('performance', '表现目标'), ('objectives', '表现目标'), ('misconception', '易混点'), ('explanationPrompt', '解释问题'), ('transferPrompt', '迁移问题')] if value.get(key)]
        if reading:
            details.append({'label': '理解辅助来源', 'value': text([meta.get('origin', 'assistant_authored_learning_note'), meta.get('reviewStatus', '审核状态未登记'), meta.get('examples', ''), '不是课程定义原文；课程原来源与定位保持'])})
        return node(value['id'], value.get('title', value['id']),
                    subject=subject,
                    stage=value.get('stage', '研究扩展' if value.get('scope') == 'research_extension' else '高中'),
                    group='研究扩展' if value.get('scope') == 'research_extension' else domain.get('title', str(value.get('grade', 'unknown'))),
                    description=description, example=reading.get('example') or value.get('bridge'), notation=reading.get('notation'),
                    boundary=text([value.get('boundary') or value.get('sourceRole', ''), reading.get('boundary', '')]),
                    status=value.get('reviewStatus'), keywords=value.get('keywords', []),
                    source={'name': text([r.get('sourceId', '') for r in refs]) or '本地课程',
                            'locator': text([r.get('locator', '') for r in refs]) or value.get('sourceLocator', ''), 'version': '',
                            'role': text([value.get('sourceRole', '课程表现目标；不是学习掌握'), '描述/示例为助手理解辅助，非定义原文' if reading else '']),
                            'status': meta.get('reviewStatus', '审核状态未登记') if reading else value.get('reviewStatus', '')},
                    details=details)

    def question(self, pid, paper, question):
        number = question['number']
        links = [{'label': '原题与解读', 'url': '/?' + urlencode({'view': 'thinking', 'paper': pid, 'q': number})}]
        for kind, field in [('source', 'pages'), ('reference', 'referencePages')]:
            original = paper.get('originals', {}).get(kind, {})
            # Only the three accepted papers have an /api/paper registration.
            if pid in {'math-2025-national1', 'english-2026-national1', 'chinese-2024-national1'}:
                url = '/api/paper?' + urlencode({'paper': pid, 'kind': kind})
            else:
                relative = original.get('staticURL') or original.get('assetFile') or ''
                path = Path(relative)
                url = ''
                if relative.startswith('assets/originals/') and '..' not in path.parts:
                    self.checked_material(self.root, relative, original.get('sha256') or paper.get(kind + 'Sha256'))
                    url = '/' + relative
            if url:
                pages = question.get(field, [])
                for page in pages:
                    if type(page) is int and page >= 1:
                        links.append({'label': ('原题' if kind == 'source' else '原参考') + f' · PDF第{page}页', 'url': url + f'#page={page}'})
        return node(f'{pid}:q{number}', f"{paper.get('year', '')} {paper.get('familyLabel') or paper.get('title', pid)} {paper.get('subjectName', SUBJECT_LABELS.get(paper.get('subject'), paper.get('subject', '')))} {printed_question_label(question)} · {question.get('title', '')}", 'question',
                    subject=paper.get('subject', 'unknown'), stage='高中', group=pid,
                    description=question.get('understanding', question.get('questionText', '')),
                    boundary=text(paper.get('boundaries', [])), status=paper.get('reviewStatus'), links=links,
                    source={'name': paper.get('title', pid), 'locator': f'{printed_question_label(question)}（内部题号{number}）；PDF物理页{question.get("pages", [])}', 'version': paper.get('sourceSha256', ''), 'role': paper.get('sourceRole', '原题研究')},
                    details=[{'label': '原题条件', 'value': text(question.get('conditions', []))}])

    def local(self, identifier):
        paths = [Path(__file__).resolve(), self.root / 'data/catalog.js']
        extra = {'foundation': ['lower-curriculum.json'], 'textbooks': ['textbook-catalog.json', 'guidebooks.json'],
                 'thinking': ['thinking-first-paper.json', 'thinking-supplement.json', 'math-mechanism-index.json'],
                 'ledger': ['knowledge-ledger.json', 'lesson-units.json'], 'mapping': [f'graph-coverage/{sid}.json' for sid in EXTERNAL_IDS],
                 'curriculum': ['research-extensions.json']}
        paths += [self.root / 'data' / p for p in extra.get(identifier, [])]
        if identifier in {'papers', 'thinking', 'mapping'}:
            paths += [self.checked_material(self.root, o['assetFile'], o['sha256']) for entry in self.data()['papers'].values() for o in entry['paper'].get('originals', {}).values() if o.get('assetFile')]
        if identifier in {'textbooks', 'mapping'}:
            paths += [self.root / 'data/textbook-catalog.json', self.root / 'data/guidebooks.json']
            paths += [self.checked_material(self.root.parent, b['localFile'], b['sha256'], allowed=self.root.parent / ('原始资料与备选/ChinaTextbook' if f == 'textbook-catalog.json' else '原始资料与备选/网盘20261106/2027五三A版')) for f in ('textbook-catalog.json', 'guidebooks.json') for b in self.read(self.root / 'data' / f)[0]]
        if identifier == 'mapping':
            paths += [self.root.parent / '图谱关联' / p for p in MAPPING_FILES]
            paths.append(self.root.parent / '卡点训练/审核样本.json')
        version = self.version(paths)
        with self._lock:
            if (identifier, version) in self._cache:
                return self._cache[identifier, version]
            title, boundary = LOCAL_TITLES[identifier]
            graph = Projection(identifier, title, boundary, version)
            data = self.data()
            if identifier in {'curriculum', 'foundation'}:
                points = self.read(self.root / 'data/lower-curriculum.json')[0] if identifier == 'foundation' else data['curriculumPoints']
                for value in points.values():
                    graph.add(self.point(value, lower=identifier == 'foundation'))
                for value in points.values():
                    for parent in value.get('prerequisites', []):
                        graph.edge(parent, value['id'], 'prerequisite', label='登记先备', boundary='课程组织关系，不代表此题必修或学生掌握')
                graph.default = 'counting' if identifier == 'foundation' else 'm-set-complement'
                if identifier == 'curriculum':
                    graph.notes.append(f"课程节点{sum(p.get('scope') != 'research_extension' for p in points.values())}；研究扩展{sum(p.get('scope') == 'research_extension' for p in points.values())}单列，不计入课程分母。")
            elif identifier == 'papers':
                self.paper_graph(graph, data)
            elif identifier == 'textbooks':
                self.book_graph(graph)
            elif identifier == 'thinking':
                self.thinking_graph(graph, data)
            elif identifier == 'mapping':
                self.mapping_graph(graph, data)
            elif identifier == 'ledger':
                self.ledger_graph(graph)
            graph.finish()
            self._cache = {k: v for k, v in self._cache.items() if k[0] != identifier}
            self._cache[identifier, version] = graph
            return graph

    def paper_graph(self, graph, data):
        for value in data['concepts'].values():
            graph.add(self.point(value))
        for pid, entry in data['papers'].items():
            for question in entry['paper']['questions']:
                graph.add(self.question(pid, entry['paper'], question))
        for pid, entry in data['papers'].items():
            for q in entry['paper']['questions']:
                qid = f'{pid}:q{q["number"]}'
                for mapping in q.get('mappings', []):
                    graph.edge(mapping['pointId'], qid, 'mapping', label='本题知识调用', reason=mapping.get('slice', ''), status=mapping.get('role', ''))
                for parent in q.get('highPrerequisiteIds', []):
                    if parent in data['curriculumPoints']:
                        graph.add(self.point(data['curriculumPoints'][parent]))
                    graph.edge(parent, qid, 'question_prerequisite', label='题级高中先备建议', boundary='题级登记建议，不冒充课程原边或实证必要条件')
                bridge = q.get('bridge', {})
                for field in ('primaryIds', 'juniorIds'):
                    for parent in bridge.get(field, []):
                        if parent in data['lowerCurriculum']:
                            graph.add(self.point(data['lowerCurriculum'][parent], lower=True))
                        graph.edge(parent, qid, 'bridge', label='题级初小经验桥', reason=bridge.get('note', ''), boundary='候选经验联系，不是刚性先修路线')
                if bridge.get('anchorId'):
                    parent = bridge['anchorId']
                    if parent in data['curriculumPoints']:
                        graph.add(self.point(data['curriculumPoints'][parent]))
                    graph.edge(parent, qid, 'bridge_anchor', label='经验桥锚点', reason=bridge.get('note', ''))
                for ref in bridge.get('externalStageRefs', []):
                    ident = ref['sourceId'] + ':' + ref['nodeId']
                    value = data.get('stageCurriculum', {}).get(ident, {})
                    graph.add(node(ident, value.get('title', ref.get('label', ident)), subject=value.get('subject', 'unknown'), stage=ref.get('stage', 'unknown'), group=ref['sourceId'], description=value.get('description', ''), boundary='外源经验桥，身份保持独立'))
                    graph.edge(ident, qid, 'external_bridge', label='外源学段经验桥', reason=ref.get('reason', ''))
                for cross in q.get('crossQuestion', []):
                    graph.edge(qid, f'{pid}:q{cross["target"]}', 'cross_question', label='跨题联系', reason=cross.get('relation', ''))
                for cross in q.get('crossPaper', []):
                    graph.edge(qid, f'{cross["paperId"]}:q{cross["number"]}', 'cross_paper', label='跨卷联系', reason=text([cross.get('relation', ''), cross.get('change', '')]))
        graph.default = 'math-2025-national1:q2'
        graph.notes.append(f"{len(data['papers'])}卷、{sum(len(e['paper']['questions']) for e in data['papers'].values())}题、{len(data['concepts'])}已用知识；另保留桥接端点，故图节点总数不是题数加已用知识数。")

    def book_graph(self, graph):
        for filename, endpoint, group in [('textbook-catalog.json', 'textbook', '教材'), ('guidebooks.json', 'guidebook', '教辅')]:
            books = self.read(self.root / 'data' / filename)[0]
            for book in books:
                bid = book['id']
                self.checked_material(self.root.parent, book['localFile'], book['sha256'], allowed=self.root.parent / ('原始资料与备选/ChinaTextbook' if endpoint == 'textbook' else '原始资料与备选/网盘20261106/2027五三A版'))
                url = '/api/' + endpoint + '?' + urlencode({'id': bid})
                shared = {'subject': book.get('subject', 'unknown'), 'stage': book.get('stage', 'unknown'), 'group': group}
                graph.add(node(bid, book['title'], 'book', **shared, description=book.get('status', ''), status=book.get('status'),
                               boundary=book.get('copyrightStatus', '已登记文件，不代表全书审读'), links=[{'label': '原PDF', 'url': url + '#page=1'}], details=[{'label': '原PDF SHA-256', 'value': book['sha256']}],
                               source={'name': book['title'], 'locator': f"PDF共{book['pages']}物理页", 'version': book.get('version', book.get('edition', '')), 'role': group}))
                for p in range(1, book['pages'] + 1):
                    graph.add(node(f'{bid}:p{p}', f"{book['title']} · PDF第{p}页", 'page', **shared, description='PDF物理页，不推定对应章节或已核读',
                                   status='已登记物理页；内容审读状态另核', links=[{'label': '该物理页', 'url': url + f'#page={p}'}]))
                    graph.edge(bid, f'{bid}:p{p}', 'physical_page', label='包含物理页')
                for index, chapter in enumerate(book.get('chapters', [])):
                    cid = f'{bid}:c{index + 1}'
                    graph.add(node(cid, chapter['title'], 'chapter', **shared, description=chapter.get('readingNotes', ''), status=chapter.get('reviewStatus'),
                                   keywords=chapter.get('topics', []), boundary='仅当前登记章/片段，不扩写整书目录',
                                   links=[{'label': f'原PDF · 第{p}物理页', 'url': url + f'#page={p}'} for p in chapter.get('pages', []) if type(p) is int and 1 <= p <= book['pages']],
                                   details=[{'label': '纸书印刷页', 'value': text(chapter.get('printedPages', ''))}]))
                    graph.edge(bid, cid, 'registered_chapter', label='已登记章/片段')
                    for p in chapter.get('pages', []):
                        graph.edge(cid, f'{bid}:p{p}', 'chapter_page', label='登记章的物理页')
        graph.notes.append('全部登记PDF物理页可分页搜索；教辅没有登记章，不生成章名。页节点存在不代表已读该页。')

    def thinking_graph(self, graph, data):
        first = self.read(self.root / 'data/thinking-first-paper.json')[0]
        more = self.read(self.root / 'data/thinking-supplement.json')[0]
        mechanisms = self.read(self.root / 'data/math-mechanism-index.json')[0]
        for category in mechanisms['categories']:
            graph.add(node('mechanism:' + category['id'], category['title'], 'mechanism', group='机制分类', description=category['reason'], boundary='研究分类，不是能力或掌握等级'))
        papers = {first['paperId']: first, **more['papers']}
        for pid, item in papers.items():
            if pid not in data['papers']:
                continue
            paper = data['papers'][pid]['paper']
            questions = {q['number']: q for q in paper['questions']}
            for q in item['questions']:
                original = questions[q['number']]
                qnode = self.question(pid, paper, original)
                graph.add(qnode)
                qid = qnode['id']
                mid = qid + ':mechanism'
                graph.add(node(mid, original['title'] + ' · 思考机制', 'mechanism', subject=paper.get('subject', 'unknown'), stage='高中', group=pid,
                               description=q.get('mechanism', ''), boundary='助手依据题面研究，不是命题人访谈或学生实证', links=qnode['links']))
                graph.edge(qid, mid, 'mechanism', label='题面机制研究')
                previous = None
                for index, step in enumerate(q.get('steps', [])):
                    ident = qid + f':step{index + 1}'
                    graph.add(node(ident, step.get('title', f'步骤{index + 1}'), 'step', subject=paper.get('subject', 'unknown'), stage='高中', group=pid,
                                   description=step.get('action', ''), boundary='展示路径不是唯一正确解法；probe须实际作答', links=qnode['links'],
                                   details=[{'label': '为什么这样做', 'value': text(step.get('reason', ''))}, {'label': '思考追问', 'value': text(step.get('probe', ''))}]))
                    graph.edge(qid, ident, 'has_step', label='展示步骤', reason=step.get('reason', ''))
                    if previous:
                        graph.edge(previous, ident, 'sequence', label='展示顺序', boundary='不是已验证先备')
                    previous = ident
                classification = mechanisms.get('papers', {}).get(pid, {}).get(str(q['number']), {})
                for category in classification.get('classIds', []):
                    graph.edge(mid, 'mechanism:' + category, 'classification', label='机制关系', reason=classification.get('why', ''))
        graph.default = 'math-2025-national1:q2'

    def mapping_graph(self, graph, data):
        for point in data['curriculumPoints'].values():
            graph.add(self.point(point))
            for candidate in point.get('sourceCandidates', []):
                ident = candidate['id']
                graph.add(node(ident, candidate['name'], group=candidate.get('source', 'unknown'), description='已登记候选标题，未按名称合并', boundary='候选匹配不是语义覆盖'))
                graph.edge(point['id'], ident, 'candidate', label='名称候选', boundary='不是确认等价或先备')
        for sid in EXTERNAL_IDS:
            record = self.read(self.root / f'data/graph-coverage/{sid}.json')[0]
            for ident, source in record.get('sourceNodes', {}).items():
                graph.add(node(ident, source.get('label', ident), subject=source.get('subject', 'unknown'), stage=source.get('stage', 'unknown'), group=sid,
                               description=text(source.get('bodyEvidence', {})), source={'name': record['name'], 'locator': source.get('sourceLocator', ''), 'version': record['sourceVersion'], 'role': '已保存的来源证据；不加载全源'}))
            for paper in record.get('papers', []):
                for demand in paper['requirements']:
                    ident = 'mapping:' + sid + ':' + demand['demandId']
                    graph.add(node(ident, demand['label'], 'mapping', group=sid, description=demand['requirement'], status=demand['status'],
                                   boundary=demand.get('uncovered', ''), details=[{'label': '判断理由', 'value': demand['reason']}],
                                   links=[{'label': '实际题目与解读', 'url': '/?' + urlencode({'view': 'thinking', 'paper': paper['paperId'], 'q': demand['number']})}]))
                    graph.edge(demand['localPointId'], ident, 'demand_mapping', label='具体操作判断', status=demand['status'])
                    for target in demand['nodeIds']:
                        graph.edge(ident, target, 'source_review', label='来源逐项判断', reason=demand['reason'], status=demand['status'], boundary=demand.get('uncovered', ''))
        books = {b['id']: b for b in self.read(self.root / 'data/textbook-catalog.json')[0]}
        for index, review in enumerate(data.get('semanticReviews', [])):
            pid = review['paperId']
            paper = data['papers'][pid]['paper']
            numbers = review.get('questions', [review['question']])
            scope = {k: safe_properties(review[k]) for k in ('paperId', 'pointId', 'question', 'questions', 'questionScopes', 'canonical', 'requiredActions', 'semanticGaps', 'textbookEvidence') if k in review}
            scope['scopeType'] = 'question_slice_not_global_equivalence'
            links = []
            for q in paper['questions']:
                if q['number'] in numbers:
                    qnode = self.question(pid, paper, q)
                    graph.add(qnode)
                    links.extend(qnode.get('links', []))
            evidence = review.get('textbookEvidence', {})
            if evidence.get('bookId') in books:
                book = books[evidence['bookId']]
                self.checked_material(self.root.parent, book['localFile'], book['sha256'], allowed=self.root.parent / '原始资料与备选/ChinaTextbook')
                for p in evidence.get('pdfPages', []):
                    if type(p) is int and 1 <= p <= book['pages']:
                        page_id = f'{book["id"]}:p{p}'
                        url = '/api/textbook?' + urlencode({'id': book['id']}) + f'#page={p}'
                        links.append({'label': f'{book["title"]} · PDF第{p}物理页', 'url': url})
                        graph.add(node(page_id, f'{book["title"]} · PDF第{p}物理页', 'page', subject=book['subject'], stage=book['stage'], group=book['id'], links=[links[-1]], source={'name': book['title'], 'locator': f'PDF第{p}物理页', 'version': book['sha256'], 'role': '审读所登记教材依据'}))
            mid = f'semantic:{pid}:{review["pointId"]}:{index + 1}'
            scope_text = f'{paper.get("title", pid)}（{pid}）第{text(numbers)}题；适用切片：' + text(review.get('questionScopes', review.get('requiredActions', review['pointId'])))
            graph.add(node(mid, graph.nodes[review['pointId']]['label'] + ' · 第' + text(numbers) + '题语义切片', 'mapping', subject=paper.get('subject', 'unknown'), stage='高中', group=pid,
                           description=scope_text, status=review.get('status'), boundary='仅题级理解，不是知识节点全局等价；原canonical.scope未改', links=list({l['url']: l for l in links}.values()), details=property_details(scope)))
            graph.edge(review['pointId'], mid, 'semantic_scope', label='题级语义切片', reason=scope_text, source_scope=scope)
            for number in numbers:
                graph.edge(mid, f'{pid}:q{number}', 'semantic_question', label='适用于登记题目', reason=scope_text, source_scope=scope)
            for p in evidence.get('pdfPages', []):
                page_id = f'{evidence.get("bookId")}:p{p}'
                if page_id in graph.nodes:
                    graph.edge(mid, page_id, 'textbook_evidence', label='已登记教材依据', reason=scope_text, source_scope=scope)
            for source in review['sources']:
                target = source['target']
                ident = target['id']
                graph.add(node(ident, target.get('label', ident), native_kind(target.get('sourceKind')), subject=target.get('subject', 'unknown'), stage=target.get('stage', 'unknown'), group=source['sourceId'], description='已有题级语义审读记录',
                               details=property_details(target), source={'name': source['sourceId'], 'locator': target.get('sourceLocator', ''), 'version': target.get('sourceVersion', ''), 'role': '保留独立来源身份'}))
                source_scope = {**scope, **{k: safe_properties(source[k]) for k in ('sourceId', 'appliesTo', 'target') if k in source}}
                graph.edge(mid, ident, source['relation'], label=source.get('label') or source['relation'], reason=text([source['reason'], scope_text, source.get('appliesTo', '')]), boundary=source.get('conflict', ''), status=review.get('status', ''),
                           locator=target.get('sourceLocator', ''), details=property_details({k: v for k, v in source.items() if k not in {'target', 'relation', 'label', 'reason'}}), source_scope=source_scope)
        self.registered_mappings(graph, data)
        graph.notes.append('映射层含名称候选及逐动作明确判断；关系值保持原登记，不将aligned、transfer或locator伪造为prerequisite。')

    def registered_mappings(self, graph, data):
        """Project small, registered mapping receipts, not the K12 dataset copies."""
        base = self.root.parent / '图谱关联'
        sample_document = self.read(self.root.parent / '卡点训练/审核样本.json')[0]
        samples = {s['id']: s for s in sample_document['items']}

        def target(value, subject='unknown'):
            ident = value['id'] if isinstance(value, dict) else value
            if ident not in graph.nodes:
                point = data.get('curriculumPoints', {}).get(ident) or data.get('lowerCurriculum', {}).get(ident)
                graph.add(self.point(point) if point else node(ident, value.get('title', ident) if isinstance(value, dict) else ident, subject=subject, description='映射中登记的节点引用；不扩写课程定义'))
            return ident

        def receipt(filename, row, identifier, label, *, subject='unknown', locator='', description='', status='', boundary='', version='', links=None, details=None):
            document = self.read(base / filename)[0]
            restrictions = [document.get('scope', ''), boundary]
            for key in ('localResearchOnly', 'publicRedistributionAllowed', 'automatic_grading'):
                if key in document or key in row:
                    restrictions.append(f'{key}={json.dumps(row.get(key, document.get(key)), ensure_ascii=False)}')
            fields = [{'label': 'sourceId', 'value': text(row.get('sourceId', '图谱关联/' + filename))},
                      {'label': '登记ID / item_id', 'value': text(row.get('item_id', row.get('id', row.get('record_id', identifier))))}]
            fields += details or []
            graph.add(node(identifier, label, 'mapping', subject=subject, stage=row.get('stage', 'unknown'), group=filename,
                           description=description, status=status or '已登记事实；不代表官方审核', boundary=text(restrictions), links=links or [], details=fields,
                           source={'name': '图谱关联/' + filename, 'locator': locator, 'version': version or self.read(base / filename)[1],
                                   'role': row.get('sourceRole', row.get('sourceType', '题级教学研究映射，不是官方题标')), 'status': status or '已登记事实；不代表官方审核',
                                   **({'sourceId': row['sourceId']} if 'sourceId' in row else {})}))

        filename = MAPPING_FILES[0]
        document = self.read(base / filename)[0]
        for row in document['mappings']:
            sample = samples[row['item_id']]
            ident = 'registered:six:' + row['item_id']
            pid, number = row['item_id'].rsplit('-q', 1)
            paper = data.get('papers', {}).get(pid, {}).get('paper', {})
            question = next((q for q in paper.get('questions', []) if str(q['number']) == number), None)
            links = self.question(pid, paper, question).get('links', []) if question else []
            receipt(filename, row, ident, sample['title'], subject=sample['subject'],
                    locator=text([sample['source_path'], f'PDF物理页{row["original_pages"]}']), description=row['primary']['slice'],
                    status=text(sample['review']), boundary=text([*document['boundaries'], sample['source_notice'], row.get('note', ''), f'local_only={json.dumps(sample_document["local_only"])}', f'automatic_grading_enabled={json.dumps(sample_document["automatic_grading_enabled"])}', '工作台题已接入' if question else '未接入工作台；原PDF保留定位，未接入原PDF入口']),
                    version=sample['source_sha256'], links=links,
                    details=[{'label': '原物理页', 'value': text(row['original_pages'])}, {'label': '卷族', 'value': sample['paper_family']},
                             {'label': '原页审核状态', 'value': text(sample['review'])}, {'label': '额外动作', 'value': row.get('additional_action', '')}])
            graph.edge(target(row['primary'], sample['subject']), ident, 'registered_slice', label='六题独立切片映射', reason=row['primary']['slice'], status='automatic_grading=false')
            for field, relation, label in [('graph_direct_prerequisites', 'registered_graph_reference', '原图直接先备引用（非本题硬门槛）'), ('question_prerequisite_probes', 'registered_probe', '题级先备探查建议')]:
                for parent in row.get(field, []):
                    graph.edge(target(parent, sample['subject']), ident, relation, label=label, boundary='仅保留登记引用，不作为此题刚性先修路线')
            conditional = row.get('conditional_probe')
            if conditional:
                graph.edge(target(conditional, sample['subject']), ident, 'conditional_probe', label='条件性探查', reason=conditional['when'])
            if question:
                graph.add(self.question(pid, paper, question))
                graph.edge(ident, f'{pid}:q{number}', 'registered_question', label='已接入题目研究；不替换原映射')

        filename = MAPPING_FILES[1]
        for row in self.read(base / filename)[0]['bridges']:
            ident = 'registered:bridge:' + row['id']
            receipt(filename, row, ident, row['title'], subject=row['subject'], locator=text([row['sourceFile'], row['evidence']]),
                    description=row['evidence'], boundary=text([row['boundary'], '原资料入口未接入；保留原定位']))
            for item in row['targets']:
                graph.edge(ident, target(item, row['subject']), 'registered_bridge_candidate', label='已登记材料候选桥', reason=item['slice'], boundary=row['boundary'])

        filename = MAPPING_FILES[2]
        for row in self.read(base / filename)[0]['mappings']:
            ident = 'registered:netdisk:' + row['id']
            receipt(filename, row, ident, f'{row["year"]} {row["paper"]} {SUBJECT_LABELS[row["subject"]]} 第{row["questionNumber"]}题 · 网盘独立版本',
                    subject=row['subject'], locator=f'{row["sourceFile"]}；PDF物理页{row["evidencePage"]}', description=row['taskAction'],
                    status='assistant_source_reviewed_slice_not_official', boundary=text([row['boundary'], '未接入工作台；原PDF入口未接入，不替换同题其他版本']),
                    version=row['reviewedSha256'], details=[{'label': '原物理页', 'value': str(row['evidencePage'])}, {'label': '助手推导身份', 'value': text(row['derivation'])}])
            for item in row['pointMappings']:
                graph.edge(target(item, row['subject']), ident, 'registered_slice', label='网盘独立版本题级切片', reason=item['slice'], status=item['mappingStatus'], boundary=row['boundary'])

        filename = MAPPING_FILES[3]
        document = self.read(base / filename)[0]
        for row in document['candidate_links']:
            ident = 'registered:k12:' + row['record_id']
            receipt(filename, row, ident, row['record_id'], subject=point_subject({'id': row['local_node']}),
                    locator=f'图谱关联/{row["file"]}；第{row["line"]}行；{row["record_id"]}', description=row['relation'], status=row['status'],
                    boundary=text([document['license_from_local_readme'], *document['notes']]),
                    details=[{'label': '数据集', 'value': row['dataset']}, {'label': 'record_id', 'value': row['record_id']}])
            graph.edge(target({'id': row['local_node'], 'title': row['local_node_title']}), ident, 'registered_dataset_candidate', label=row['relation'], status=row['status'], locator=f'{row["file"]}:{row["line"]}')
        counts = Counter(n['group'] for n in graph.nodes.values() if n['id'].startswith('registered:'))
        graph.notes.append('额外登记：' + text([f'{name} {counts[name]}条' for name in MAPPING_FILES]) + '；K12数据集副本不是独立图谱，未加载JSONL。原资料无已登记入口时仅保留定位。')

    def ledger_graph(self, graph):
        ledger = self.read(self.root / 'data/knowledge-ledger.json')[0]
        data = self.data()
        units = {u['id']: u for u in self.read(self.root / 'data/lesson-units.json')[0]['units']}
        gaps = {'no-classroom': '尚无课堂', 'no-practice': '尚无练习'}
        for point in ledger['points'].values():
            original = data.get('concepts', {}).get(point['id']) or data.get('curriculumPoints', {}).get(point['id']) or point
            value = self.point(original)
            value['group'] = '聚合知识'
            value['status'] = point.get('status', original.get('reviewStatus', '已有台账登记；非个人学习进度'))
            value['boundary'] = text([value.get('boundary', ''), ledger['scope']])
            value.setdefault('details', []).extend([
                {'label': '课堂登记', 'value': text([units.get(uid, {}).get('title', uid) for uid in point['classroomUnits']]) or '尚无课堂'},
                {'label': '练习注册', 'value': text([text([p.get('title', p.get('unitId', p.get('id', '已登记练习'))), p.get('status', ''), p.get('statusText', '')]) if isinstance(p, dict) else p for p in point['practice']]) or '尚无练习'},
                {'label': '缺口', 'value': text([gaps.get(g, g) for g in point['gaps']])},
                {'label': '缺口原登记', 'value': text(point['gaps'])}])
            value['links'] = []
            for uid in point['classroomUnits']:
                unit = units.get(uid, {})
                pid, number = unit.get('paperId'), unit.get('entryNumber')
                paper = data.get('papers', {}).get(pid, {}).get('paper', {})
                if any(q['number'] == number for q in paper.get('questions', [])):
                    value['links'].append({'label': unit['title'] + ' · 已登记课堂', 'url': '/?' + urlencode({'view': 'classroom', 'paper': pid, 'q': number})})
            graph.add(value)
            for field in ('mainBindings', 'supportBindings'):
                for binding in point[field]:
                    pid = binding['paperId']
                    ident = f'{pid}:q{binding["number"]}'
                    graph.add(node(ident, ledger['papers'][pid]['label'] + ' ' + binding['label'], 'question', subject=ledger['papers'][pid]['subject'], stage='高中', group=pid,
                                   links=[{'label': '题目与解读', 'url': '/?' + urlencode({'view': 'thinking', 'paper': pid, 'q': binding['number']})}]))
                    graph.edge(point['id'], ident, 'binding', label='台账题级绑定', reason=binding.get('slice', ''), status=binding.get('role', ''))
            for uid in point['classroomUnits']:
                unit = units.get(uid, {})
                graph.add(node('unit:' + uid, unit.get('title', uid), 'unit', group='课堂登记',
                               description=unit.get('goal', '静态登记，不读取课堂或学习记录'), status=unit.get('status', '静态课堂登记；非课堂执行或掌握证据'),
                               boundary=unit.get('boundary', '只读静态登记，不启动模型'),
                               links=[link for link in value['links'] if link['label'] == unit.get('title', '') + ' · 已登记课堂']))
                graph.edge(point['id'], 'unit:' + uid, 'classroom_registration', label='课堂注册', status=unit.get('status', '静态登记'))
        for chain in ledger.get('chains', {}).values():
            ident = 'chain:' + chain['id']
            graph.add(node(ident, chain['label'], 'mapping', group='迁移设计', description=chain.get('statusText', ''), status=chain['status']))
            for step in chain['steps']:
                graph.edge(ident, f'{step["paperId"]}:q{step["number"]}', 'designed_route', label='迁移设计绑定', reason=step.get('role', ''), status=chain['status'])
        graph.notes.append(ledger['scope'])

    def explain_empty_nodes(self, graph):
        """Explain registered topology, not invented textbook or experiment prose."""
        for value in graph.nodes.values():
            if value['description'] or value.get('status', '').startswith('ambiguous'):
                continue
            sections = []
            links = []
            groups = defaultdict(list)
            for edge in graph.incoming[value['id']] + graph.outgoing[value['id']]:
                incoming = edge['target'] == value['id']
                other_id = edge['source'] if incoming else edge['target']
                other = graph.nodes.get(other_id)
                if not other or other_id == value['id']:
                    continue
                relation = edge['relation']
                if relation in {'is_part_of', 'appears_in', 'registered_chapter', 'physical_page', 'chapter_page'}:
                    key = '包含登记条目' if incoming else '所属登记位置'
                    if relation in {'registered_chapter', 'physical_page', 'chapter_page'}:
                        key = '包含登记条目' if not incoming else '所属登记位置'
                else:
                    key = ('原关系指向本项' if incoming else '本项原关系指向') + '（' + edge['label'] + '）'
                groups[key].append(other)
            for key, items in groups.items():
                unique = {item['id']: item for item in items}
                shown = list(unique.values())[:6]
                allocation = '（' + '、'.join(KIND_LABELS[kind] + str(count) + '项' for kind, count in Counter(item['kind'] for item in unique.values()).items()) + '）'
                sections.append(key + f' {len(unique)}项' + allocation + '：' + '、'.join(item['label'] for item in shown)
                                + ('等（完整条目见关系分页）' if len(unique) > 6 else '') + '。')
                for item in shown:
                    links.append({'label': item['label'] + ' · 图谱登记',
                                  'url': '/graphs.html?' + urlencode({'graph': graph.id, 'node': item['id']})})
            prefix = f'“{value["label"]}”是来源登记的{KIND_LABELS[value["kind"]]}条目。'
            explanation = prefix + ''.join(sections)
            if not sections:
                explanation += '当前快照只提供这一标题与身份，没有可连接的已登记条目。'
            explanation += '以上是原图结构说明，不是教材正文或实验步骤；来源快照未提供本项正文，不能据此推定具体页码或已掌握。'
            value['description'] = explanation
            value['structureExplanation'] = {'plain': explanation, 'sourceRole': 'source_topology_explanation_not_original_body'}
            value['status'] = 'source_structure_only；原快照无本项正文'
            value['source']['role'] = '来源原条目；描述为原图结构说明，非原正文'
            value.setdefault('links', []).extend(links)

    def apply_reading_supplements(self, graph, source):
        """Exact, pinned identities only; malformed notes fail closed before caching."""
        try:
            document, digest = self.read(self.root / SUPPLEMENT_FILE)
        except (ValueError, UnicodeError) as error:
            raise AtlasError('理解补充JSON无效', 503) from error
        if not isinstance(document, dict) or set(document) != {'schemaVersion', 'items'} or document['schemaVersion'] != 1 or not isinstance(document['items'], list):
            raise AtlasError('理解补充schema无效', 503)
        seen = set()
        pending = []
        raw_by_id = defaultdict(list)
        for raw in source.nodes:
            raw_by_id[raw['id']].append(raw)
        for item in document['items']:
            if not isinstance(item, dict) or set(item) != {'id', 'scope', 'sourceRole', 'plain', 'example', 'boundary', 'basis'}:
                raise AtlasError('理解补充字段无效', 503)
            ident, scope = item['id'], item['scope']
            if not isinstance(ident, str) or ident in seen or not ident.startswith('S02:') or ident not in graph.nodes:
                raise AtlasError('理解补充ID无效或重复', 503)
            seen.add(ident)
            raws = raw_by_id.get(ident.removeprefix('S02:'), [])
            if len(raws) != 1 or not isinstance(scope, dict) or set(scope) != {'sourceId', 'sourceVersion', 'label', 'subject', 'stage', 'bookPrefix', 'locator', 'sha256'}:
                raise AtlasError('理解补充scope无效', 503)
            raw = raws[0]
            expected = {key: raw.get(key, '') for key in ('subject', 'stage', 'bookPrefix', 'locator')}
            expected.update(sourceId='S02', sourceVersion=source.version, label=raw['name'])
            path = raw['locator'].partition('#')[0]
            expected['sha256'] = getattr(source, 'files', {}).get(path, {}).get('sha256', '')
            if scope != expected or expected['subject'] != '生物学' or expected['bookPrefix'] != 'biology_7a_rjb' or not re.fullmatch(r'[a-f0-9]{64}', expected['sha256']):
                raise AtlasError('理解补充与原节点身份/定位/SHA失配', 503)
            if item['sourceRole'] != SUPPLEMENT_ROLE or any(not isinstance(item[key], str) or not item[key].strip() or len(item[key]) > 2400 for key in ('plain', 'example', 'boundary', 'basis')):
                raise AtlasError('理解补充内容或作者身份无效', 503)
            if any(re.search(r'https?://|<[^>]+>', item[key]) for key in ('plain', 'example', 'boundary', 'basis')):
                raise AtlasError('理解补充不接受未登记URL或HTML', 503)
            pending.append((graph.nodes[ident], item))
        for value, item in pending:
            value['readingSupplement'] = {**safe_properties(item), 'version': 'sha256:' + digest,
                                           'locator': SUPPLEMENT_FILE + '#/items/' + str(document['items'].index(item))}
            # Original descriptions always win. Authored notes remain separately available.
            if not content_description(value['originalContent']['body']):
                value['description'] = item['plain']
                value['example'] = item['example']
                value['status'] = SUPPLEMENT_ROLE
                value['source']['role'] = '来源原条目；描述/例子为助手原创一般知识补充，非教材/非源正文；待教师复核'
            value['boundary'] = text([value.get('boundary', ''), item['boundary']])
            value.setdefault('details', []).append({'label': '助手原创理解补充（非源正文）', 'value': text([item['sourceRole'], item['basis'], item['boundary']])})

    def external(self, sid):
        with self._source_locks[sid]:
            record, version = self.external_registration(sid)
            if (sid, version) in self._cache:
                return self._cache[sid, version]
            if self.native_loader:
                source = self.native_loader(sid)
            else:
                source = self.audit().load_source(sid)
            # A shared legacy cache must not silently serve old parsed bytes under a new hash.
            for path, receipt in getattr(source, 'files', {}).items():
                self.version([path])
                if self._files[Path(path)][2] != receipt['sha256']:
                    raise AtlasError('来源快照与已载登记失配；未返回旧缓存', 503)
            if self.bodies_loader:
                bodies = self.bodies_loader(source)
            else:
                bodies = load_raw_bodies(source)
            body_locators = defaultdict(list)
            if sid == 'S02':
                for path, receipt in getattr(source, 'files', {}).items():
                    if Path(path).parts[-2:] != ('subject_specific_KG', 'math.json'):
                        continue
                    document, digest = self.read(path)
                    if digest != receipt['sha256']:
                        raise AtlasError('数学正文定位与来源SHA失配', 503)
                    rows = document['nodes']
                    counts = Counter(row['id'] for row in rows)
                    for index, row in enumerate(rows):
                        if counts[row['id']] == 1 and content_fields(row):
                            body_locators[row['id']].append({'locator': path + '#/nodes/' + str(index),
                                                            'sha256': digest, 'sourceVersion': source.version})
            rdf_details = self.rdf_bodies(source) if sid == 'S07' else {}
            graph = Projection(sid, record['name'], source.spec['scope'] + '；来源授权与学段原值保留；不是全库覆盖或学生掌握。', version)
            entries = defaultdict(list)
            for raw in source.nodes:
                entries[raw['id']].append(raw)
            for ident, rows in entries.items():
                labels = list(dict.fromkeys(n['name'] for n in rows))
                subjects = list(dict.fromkeys(n['subject'] for n in rows))
                stages = list(dict.fromkeys(n['stage'] for n in rows))
                body = bodies.get(ident, {}) if len(rows) == 1 else {}
                details = property_details(rows[0]) if len(rows) == 1 else [{'label': f'原条目{i + 1}', 'value': text(safe_properties(row))} for i, row in enumerate(rows)]
                original_properties = {}
                for row in rows:
                    location = row.get('locator', '')
                    path_name, _, pointer = location.partition('#')
                    # Only paths explicitly read/verified by audit, never a request path.
                    if path_name in getattr(source, 'files', {}) and Path(path_name).suffix == '.json' and pointer.startswith('/'):
                        document, digest = self.read(Path(path_name))
                        if digest != source.files[path_name]['sha256']:
                            raise AtlasError('节点定位文件与来源SHA失配', 503)
                        raw_record = document
                        try:
                            for part in pointer.lstrip('/').split('/'):
                                if isinstance(raw_record, list) and part == 'topics':
                                    continue
                                raw_record = raw_record[int(part)] if isinstance(raw_record, list) else raw_record[part]
                        except (KeyError, ValueError, IndexError, TypeError):
                            raw_record = None
                        if isinstance(raw_record, dict):
                            if raw_record.get('id', ident) != ident:
                                raise AtlasError('原节点ID与定位内容失配', 503)
                            original_properties = raw_record if len(rows) == 1 else {}
                            details.extend(property_details(raw_record))
                        elif isinstance(raw_record, list):
                            details.append({'label': '原十列记录', 'value': text(raw_record)})
                details.extend(rdf_details.get(ident, []))
                if len(rows) > 1:
                    details += [{'label': '全部原标签', 'value': text(labels)}, {'label': '原条目数', 'value': str(len(rows))}, {'label': '全部定位', 'value': text([n['locator'] for n in rows])}]
                for key, value in body.items():
                    if key not in {'description', 'definition'} and value:
                        details.append({'label': key, 'value': text(value)})
                if len(rows) == 1:
                    # Locator content is authoritative even when a legacy bodies loader
                    # only exported math. Keep nested global properties intact.
                    body = {**body, **content_fields(original_properties)}
                kind = native_kind(rows[0]['kind'])
                group = text(rows[0].get('originGroup') or rows[0].get('group') or rows[0].get('bookPrefix') or rows[0].get('stageGroup')) or 'unknown'
                if sid == 'S06':
                    group = text(original_properties.get('originGroup') or original_properties.get('group')) or rows[0]['locator'].split('#', 1)[0].split('/split/', 1)[-1]
                    details.append({'label': '原split文件组', 'value': rows[0]['locator'].split('#', 1)[0].split('/split/', 1)[-1]})
                graph.add(node(sid + ':' + ident, ' / '.join(labels), kind, subject=subjects[0] if len(subjects) == 1 else '多值', stage=stages[0] if len(stages) == 1 else '多值',
                               group=group, description=content_description(body), example=body.get('examples'),
                               status='ambiguous：同一原ID有多条标签记录；未隐式选取正文' if len(rows) > 1 else source.status,
                               boundary=source.spec['licenseStatus'], details=details,
                               source={'name': source.spec['name'], 'locator': text([n['locator'] for n in rows]), 'version': source.version, 'role': '来源原条目，不是学生掌握'},
                               links=[{'label': '来源仓库', 'url': 'https://github.com/' + source.spec['name'].split(' + ')[0]}]))
                value = graph.nodes[sid + ':' + ident]
                value['originalContent'] = {'properties': safe_properties(original_properties),
                                            'body': safe_properties(body), 'source': dict(value['source']),
                                            'bodyLocators': body_locators.get(ident, []) if len(rows) == 1 else []}
            for edge in source.edges:
                graph.edge(sid + ':' + edge['source'], sid + ':' + edge['target'], edge['relation'], label=edge.get('label') or edge.get('codedRelation') or edge['relation'],
                           reason=edge.get('reason', ''), locator=edge.get('locator', ''), identifier=edge['id'], status=edge.get('strength', ''),
                           boundary='原生来源关系；不等于当前题目必修路线',
                           details=property_details({key: edge[key] for key in ('rawRelation', 'codedRelation', 'rawSource', 'rawTarget') if key in edge}),
                           original_source=sid + ':' + edge['rawSource'], original_target=sid + ':' + edge['rawTarget'],
                           original_relation=edge['rawRelation'], original_label=edge.get('codedRelation') or edge['rawRelation'])
            auxiliary = getattr(source, 'details', {}).get('auxiliaryMathLinks', [])
            for index, edge in enumerate(auxiliary):
                graph.edge(sid + ':' + edge['source'], sid + ':' + edge['target'], 'math_link', label='mathLink', reason=edge.get('reason', ''), locator=edge.get('locator', ''), identifier=f'{sid}:math_link:{index}', boundary='来源 mathLinks 原方向；单独计数，不并入原生 dependencies', original_relation=edge['relation'], original_label='mathLink')
            registered = record['sourceCounts']
            actual = {'nodes': len(source.nodes), 'edges': len(source.edges), 'subjects': dict(Counter(n['subject'] for n in source.nodes))}
            graph.meta = {'sourceCounts': actual, 'originalSourceCounts': registered, 'uniqueNodes': len(entries), 'nativeEdgeCount': len(source.edges), 'auxiliaryEdgeCount': len(auxiliary), 'projectionEdgeCount': len(graph.edges), 'kindCounts': dict(Counter(n['kind'] for n in graph.nodes.values())), 'projectionLoaded': True, 'prerequisite_supported': source.prerequisite_supported}
            if auxiliary:
                graph.notes.append(f'附加mathLinks={len(auxiliary)}条独立math_link，保持原方向、非先备；图总边数={len(graph.edges)}，原生边={len(source.edges)}。')
            graph.notes.append('sourceCounts登记=' + text(registered) + '；实际加载=' + text(actual) + f'；unique nodes={len(entries)}；一致性=' + ('一致' if registered == actual else '不一致，请以实际加载为准'))
            if len(source.nodes) != len(entries):
                graph.notes.append(f'ambiguous：源nodes条目数{len(source.nodes)}，唯一ID数{len(entries)}；同ID多标签聚合，未按不同名字虚增节点。重复ID正文不隐式取最后一条。')
            dangling = sum(e['source'] not in graph.nodes or e['target'] not in graph.nodes for e in graph.edges)
            if dangling:
                graph.notes.append(f'{dangling}条原边有未登记端点，保留在边总数/关联边中，不伪造节点；不参与邻域扩展。')
            graph.prerequisite_supported = source.prerequisite_supported
            graph.finish()
            self.explain_empty_nodes(graph)
            if sid == 'S02':
                self.apply_reading_supplements(graph, source)
            graph.meta['originalContentCount'] = sum(bool(content_description(n['originalContent']['body'])) for n in graph.nodes.values())
            graph.meta['readingSupplementCount'] = sum('readingSupplement' in n for n in graph.nodes.values())
            graph.meta['structureExplanationCount'] = sum('structureExplanation' in n for n in graph.nodes.values())
            with self._lock:
                self._cache = {k: v for k, v in self._cache.items() if k[0] != sid}
                self._cache[sid, version] = graph
            return graph


_DEFAULT = GraphBrowser()


def atlas_catalog(query=''):
    return _DEFAULT.catalog(query)


def atlas_browse(query=''):
    return _DEFAULT.browse(query)


# ---------------------------------------------------------------- frozen release runtime
# Added for the offline /highschool-atlas/ release. Everything above stays the
# local-dev read-only browser; the additions below only serialize and rebuild
# frozen snapshots, so no service, provider or network code is imported.

FROZEN_DOC_VERSION = 1
FROZEN_DOC_KEYS = ('id', 'title', 'boundary', 'version', 'default', 'notes', 'meta',
                   'prerequisite_supported', 'nodes', 'edges')


def frozen_document(projection):
    """Serialize a Projection into the frozen JSON document written by publish_atlas."""
    graph = projection
    return {'schemaVersion': FROZEN_DOC_VERSION,
            'id': graph.id, 'title': graph.title, 'boundary': graph.boundary, 'version': graph.version,
            'default': graph.default, 'notes': list(graph.notes), 'meta': dict(graph.meta),
            'prerequisite_supported': bool(graph.prerequisite_supported),
            'nodes': [dict(graph.nodes[key]) for key in graph.nodes],
            'edges': [dict(edge) for edge in graph.edges]}


def restore_frozen_projection(document):
    """Rebuild a Projection from a frozen document for read-only browse/catalog service.

    No file, network, module or model access happens here; callers own validation
    of where the document came from.
    """
    required = {'schemaVersion', *FROZEN_DOC_KEYS}
    if not isinstance(document, dict) or set(document) != required or document['schemaVersion'] != FROZEN_DOC_VERSION:
        raise AtlasError('冻结图谱文档结构无效', 503)
    if not isinstance(document['id'], str) or not document['id'] or not isinstance(document['nodes'], list) \
            or not isinstance(document['edges'], list) or not isinstance(document['notes'], list) \
            or not isinstance(document['meta'], dict) or not isinstance(document['version'], str):
        raise AtlasError('冻结图谱文档字段无效', 503)
    graph = Projection(document['id'], document['title'], document['boundary'], document['version'])
    for value in document['nodes']:
        if not isinstance(value, dict) or {'id', 'label', 'kind', 'subject', 'stage', 'group', 'description'} - set(value):
            raise AtlasError('冻结节点结构无效', 503)
        graph.add(dict(value))
    for edge in document['edges']:
        if not isinstance(edge, dict) or {'id', 'source', 'target', 'relation'} - set(edge):
            raise AtlasError('冻结关系结构无效', 503)
        graph.edges.append(dict(edge))
    graph.default = document['default']
    graph.notes = [str(note) for note in document['notes']]
    graph.meta = document['meta']
    graph.prerequisite_supported = bool(document['prerequisite_supported'])
    return graph.finish()

'use strict';

(() => {
  const KIND_LABELS = { knowledge: '知识', question: '题目', step: '思考步骤', mechanism: '思考机制', book: '书', chapter: '章节 / 片段', page: 'PDF物理页', mapping: '映射记录', unit: '课堂登记', source: '来源实体', experiment: '实验' };
  const SUBJECTS = { math: '数学', Mathematics: '数学', english: '英语', English: '英语', chinese: '语文', Chinese: '语文', physics: '物理', chemistry: '化学', biology: '生物', unknown: '未标注', Computing: '计算机', Science: '科学', Geography: '地理', History: '历史', 'Learning to Learn': '学习方法', 'Life Skills': '生活技能', 'Personal & Social Development': '个人与社会发展' };
  const SOURCE_NAMES = { S01: 'Marble 开放知识图谱', S02: 'K12-KGraph', S03: '中文数学知识体系', S04: '中国学科技能体系', S05: 'China K12 知识体系', S06: 'K12 知识点库', S07: '清华 EDUKG' };
  const SOURCE_DESCRIPTIONS = { S01: '知识主题与依赖关系 · 保留原英语条目', S02: '知识节点与先备关系 · 原学科、学段保留', S03: '本地固定版本 · 不同学科分别检索', S04: '学科技能与依赖 · 原学段和年级保留', S05: '知识条目、先备与相关关系', S06: '分组知识点 · 原关系类型保留', S07: '概念与教材定位属性 · 当前无可查询先备边' };
  const SOURCE_PRESENTATIONS = {
    S01: { label: '学科领域 → 年龄范围 → 微主题；先备 DAG', url: 'https://github.com/withmarbleapp/os-taxonomy#marble-skill-taxonomy' },
    S02: { label: 'Book → Chapter → Section → Concept；appears_in 归属', url: 'https://haolpku.github.io/K12-KGraph-page/' },
    S03: { label: '学段 → 年级册次 → 章节 → 知识点', url: 'https://math.pansgo.com/explore/' },
    S04: { label: '学段年级 → 领域 → 教材单元 → 微主题', url: 'https://github.com/goralcao/china-skill-taxonomy/tree/main/viz' },
    S05: { label: '学科 → 年级册次 → 单元簇 → 知识点长卷', url: 'https://bewho.github.io/China-K12-knowledge-taxonomy/' },
    S06: { label: '学段学科 → 年级/模块 → chapter_path → 知识点', url: 'https://github.com/mmlong818/k12-knowledge-points' },
    S07: { label: '概念实体 → 教材、章、节定位属性', url: 'https://github.com/THU-KEG/EDUKG' }
  };
  const RELATION_LABELS = { appears_in: '归属 / 出现位置', is_part_of: '组成 / 属于', prerequisite: '来源登记先备', related: '原生相关', mapping: '本题知识用途', bridge: '基础经验联系', bridge_anchor: '经验桥锚点', external_bridge: '外源学段联系', question_prerequisite: '本题先备建议', cross_question: '卷内题目联系', cross_paper: '跨卷题目联系', has_step: '题目中的步骤', sequence: '展示顺序', mechanism: '题面机制', classification: '机制归类', physical_page: '书中物理页', registered_chapter: '已登记章节', chapter_page: '章节定位页', candidate: '名称候选 · 未确认等价', source_review: '来源支持判断', demand_mapping: '本题具体要求', binding: '真实卷题绑定', classroom_registration: '已登记课堂', designed_route: '迁移路线设计', aligned: '语义对应', transfer: '方法迁移', broader: '来源范围更宽', locator: '只提供定位', direct: '本题操作支持', partial: '部分支持', none: '未找到支持', out_of_scope: '范围外', historical_mapping: '独立版本映射', registered_mapping: '已有映射登记', prerequisite_probe: '题级先备探查', math_link: '附加数学联系 · 非先备', semantic_scope: '题级语义切片', semantic_question: '适用题目', textbook_evidence: '已登记教材依据', registered_question: '已有题目登记', registered_bridge_candidate: '材料候选桥', registered_slice: '独立版本题级切片', registered_dataset_candidate: '数据集候选联系' };
  const FIELD_LABELS = { evidence: '原来源的表现与例证', assessmentPrompt: '原来源的检查问题', definition: '原来源定义', description: '原来源说明', isbn: 'ISBN', book: '书籍定位', chapter: '章节定位', section: '小节定位', mark: '标记', textbook: '教材定位', performance: '表现目标', readingNotes: '已核读内容', pages: '物理页', page: '物理页', evidenceKind: '依据类型', limitation: '支持范围', paragraph: '原段落', mastery_criteria: '来源要求的表现', diagnostic_question: '原来源的检查例子', question: '问题', answer: '原来源答案', learningObjectives: '来源抽取的学习目标', source_evidence: '原来源的内容依据', annotations: '来源注释', domain: '知识领域', semester: '学期', standards: '来源自行关联的标准', note: '来源说明', confidence: '依据状态', definitionZh: '中文定义' };
  const TECHNICAL_FIELDS = new Set(['原ID', '原类型', '原条目数', '全部定位', 'provenance', 'rawId', 'sourceLocator', '原缺口值', '缺口原登记', '原PDF SHA-256', '原定位', '原名称', '原学科', '原学段', '原学段组', '原标签/类型', '教材定位原JSON', 'RDF原标签', 'RDF原类型IRI（非先备）', '原十列记录', 'record_id', '原属性 · id']);
  const isTechnicalField = detail => TECHNICAL_FIELDS.has(detail.label) || detail.label.startsWith('RDF原属性 · ') || /SHA-256|原属性 · (schema|crossSource|public|localResearch|scopeType|canonical|sourceRefs|sourceVersion|origin|locator|rawSource|rawTarget|external|standards)|原条目\d/.test(detail.label);
  const fieldLabel = value => { const raw = value.replace(/^原属性 · /, ''); return FIELD_LABELS[raw] || value; };
  const meaningful = value => value !== null && value !== undefined && !['', 'unknown', '；', 'None', 'False', 'True', 'false', 'true', '{}', '[]'].includes(String(value).trim()) && /[^；\s]/.test(String(value));
  function readableFields(details) {
    const seen = new Set();
    return (details || []).filter(d => meaningful(d.value) && !isTechnicalField(d) && d.label !== '理解辅助来源').filter(d => {
      const key = fieldLabel(d.label) + '|' + String(d.value).trim(); if (seen.has(key)) return false; seen.add(key); return true;
    });
  }
  const sourceNameFor = value => ({ 'math-2025-primary-copy': '普通高中数学课程标准 · 2025修订学校站副本', 'en-standard-2025': '普通高中英语课程标准 · 2025修订学校站副本', 'chi-hs-2025': '普通高中语文课程标准 · 2025修订学校站副本' }[value] || value);
  const boundaryFor = value => String(value || '').replace(/^；+/, '').replace('CC-BY-NC-4.0; source LICENSE retained', '原来源采用 CC BY-NC 4.0 非商业许可；仅本机研究，保留原许可。').replace('no license file in fixed Git tree; prior paper-license claim not reverified here', '当前固定版本没有许可文件；未确认公开再分发授权，仅本机查看。').replace('README declares PolyForm Noncommercial 1.0.0; linked LICENSE absent from fixed Git tree', '来源 README 声明非商业许可，固定版本未见所链接许可文件；本机研究，不公开分发。');
  const readableStatus = status => String(status).startsWith('assistant_authored_general_biology_note') ? '助手原创补充 · 非教材/非源正文 · 待教师复核' : String(status).startsWith('source_structure_only') ? '原图结构说明 · 来源未提供定义正文' : ({ loaded: '来源原记录 · 未作教学认证', direct: '本题操作支持 · 助手初审', partial: '部分支持 · 缺口保留', transfer: '方法迁移参考 · 非等价', locator: '只提供材料定位', out_of_scope: '当前要求在来源范围之外', none: '尚未找到对应支持', assistant_source_reviewed_slice_not_official: '原材料切片初审 · 非官方题标', assistant_authored_learning_note: '助手理解辅助 · 待教师复核' }[status] || status);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const number = value => new Intl.NumberFormat('zh-CN').format(Number(value) || 0);
  const titleFor = graph => SOURCE_NAMES[graph?.id] || graph?.title || '图谱';
  const kindFor = node => KIND_LABELS[node?.kind] || '节点';
  const subjectFor = value => SUBJECTS[value] || value || '未标注';
  const relationFor = edge => edge?.label && edge.label !== edge.relation ? edge.label : RELATION_LABELS[edge?.relation] || edge?.label || edge?.relation || '已登记关系';
  const relationTypeFor = edge => RELATION_LABELS[edge?.relation] || edge?.relation || '已登记关系';
  const cleanLocator = value => String(value || '').replace(/\/Users\/[^/]+\/Desktop\/cursor\//g, '').replace(/\/Users\/[^/]+\//g, '本机/');
  const safeHref = value => {
    if (typeof value !== 'string' || !value || /[\u0000-\u001f\u007f]/.test(value)) return null;
    if (value.startsWith('/') && !value.startsWith('//') && !value.includes('\\')) return value;
    if (/^graphs\.html(?:\?[^#]*)?$/.test(value) && !value.includes('\\')) return value;
    try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; } catch { return null; }
  };
  const routeQuery = state => {
    const result = new URLSearchParams();
    for (const key of ['graph', 'q', 'subject', 'stage', 'group', 'kind', 'node', 'page', 'hops', 'relation', 'edgePage', 'edgeSize']) {
      const value = state[key];
      if (value === undefined || value === null || value === '' || value === 'all' || (['page', 'hops', 'edgePage'].includes(key) && String(value) === '1')) continue;
      result.set(key, String(value));
    }
    return result.toString();
  };
  const estimateWidth = value => Array.from(value).reduce((sum, c) => sum + (/[^\x00-\xff]/.test(c) ? 14 : 7.2), 0);
  function wrapLabel(value, width = 190, maxLines = 3, measure = estimateWidth) {
    const tokens = String(value || '').match(/[A-Za-z0-9_]+|\s+|[^A-Za-z0-9_\s]/gu) || [];
    const lines = []; let current = '';
    for (const token of tokens) {
      if (measure(current + token) <= width) { current += token; continue; }
      if (current.trim()) { lines.push(current.trim()); current = ''; }
      if (measure(token) <= width) current = token.trimStart();
      else for (const c of Array.from(token)) { if (measure(current + c) > width && current) { lines.push(current); current = ''; } current += c; }
    }
    if (current.trim()) lines.push(current.trim());
    if (!lines.length) return ['未命名节点'];
    if (lines.length <= maxLines) return lines;
    const clipped = lines.slice(0, maxLines); let last = clipped[maxLines - 1];
    while (measure(last + '…') > width && last) last = Array.from(last).slice(0, -1).join('');
    clipped[maxLines - 1] = last + '…'; return clipped;
  }
  function diagramSlice(neighborhood, selectedId, limit = 17) {
    const nodes = neighborhood?.nodes || [];
    const selected = nodes.find(n => n.id === selectedId);
    if (!selected) return { nodes: [], edges: [], truncated: false };
    const rank = (a, b) => Math.abs(a.distance) - Math.abs(b.distance) || (a.kind === 'chapter' ? -1 : 0) - (b.kind === 'chapter' ? -1 : 0) || a.label.localeCompare(b.label, 'zh-CN');
    const before = nodes.filter(n => n.distance < 0).sort(rank);
    const after = nodes.filter(n => n.distance > 0).sort(rank);
    const half = Math.floor((limit - 1) / 2);
    const chosen = [selected, ...before.slice(0, half), ...after.slice(0, limit - 1 - Math.min(before.length, half))];
    if (chosen.length < limit) chosen.push(...before.slice(half, half + limit - chosen.length));
    const ids = new Set(chosen.map(n => n.id));
    return { nodes: chosen, edges: (neighborhood.edges || []).filter(e => ids.has(e.source) && ids.has(e.target)), truncated: chosen.length < nodes.length || !!neighborhood.truncated };
  }
  function formatValue(value) {
    if (value === null || value === undefined || value === '') return '';
    if (Array.isArray(value)) return `<ul class="value-list">${value.map(v => `<li>${formatValue(v)}</li>`).join('')}</ul>`;
    if (typeof value === 'object') return `<dl class="value-pairs">${Object.entries(value).map(([key, v]) => `<div><dt>${esc(FIELD_LABELS[key] || key)}</dt><dd>${formatValue(v)}</dd></div>`).join('')}</dl>`;
    const raw = String(value);
    if ((raw.startsWith('{') || raw.startsWith('[')) && raw.length < 30000) { try { return formatValue(JSON.parse(raw)); } catch { /* Preserve a non-JSON original as text. */ } }
    return esc(raw).replace(/\n/g, '<br>');
  }
  const helpers = { esc, safeHref, routeQuery, wrapLabel, diagramSlice, formatValue, relationFor, relationTypeFor, readableFields };
  if (typeof module !== 'undefined' && module.exports) module.exports = helpers;
  if (typeof document === 'undefined') return;

  const deployed = document.body.dataset.atlasDeployed === 'true';
  const atlasPrefix = deployed ? document.body.dataset.atlasPrefix : '/';
  if (deployed && atlasPrefix !== '/highschool-atlas/') throw new Error('图谱发布路径未登记');
  const atlasAPI = endpoint => atlasPrefix + 'api/atlas/' + endpoint;
  const main = document.getElementById('atlas-main');
  let catalog = null, current = null, state = {}, controller = null, debounce = 0, generation = 0, zoom = 1.2, routeWarning = '';
  let fullscreenMode = false, fullscreenRestore = null;
  const fullscreenActive = () => fullscreenMode || !!document.fullscreenElement;
  let canvas = null;
  try { canvas = document.createElement('canvas').getContext('2d'); if (canvas) canvas.font = '17px -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif'; } catch { /* Text geometry still has a deterministic fallback. */ }
  const measure = value => canvas ? canvas.measureText(value).width : estimateWidth(value);
  const $ = selector => document.querySelector(selector);
  const prefersDark = () => matchMedia('(prefers-color-scheme: dark)').matches;
  let userTheme = null;
  try { userTheme = localStorage.getItem('zhiti-atlas-theme'); } catch { /* Theme remains usable without storage. */ }
  if (['light', 'dark'].includes(userTheme)) document.documentElement.dataset.theme = userTheme;
  $('#theme-toggle').onclick = () => {
    const currentDark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : prefersDark();
    const theme = currentDark ? 'light' : 'dark';
    document.documentElement.dataset.theme = theme;
    $('#theme-toggle').setAttribute('aria-label', theme === 'dark' ? '切换为浅色主题' : '切换为深色主题');
    try { localStorage.setItem('zhiti-atlas-theme', theme); } catch { /* No persistence, no loss of browsing. */ }
  };
  function readRoute() {
    const params = new URLSearchParams(location.search); const result = {};
    for (const [key, value] of params) {
      if (!['graph', 'q', 'subject', 'stage', 'group', 'kind', 'node', 'page', 'hops', 'relation', 'edgePage', 'edgeSize'].includes(key)) { routeWarning = '链接含有不支持的参数。可返回图谱总览重新进入。'; continue; }
      if (Object.prototype.hasOwnProperty.call(result, key)) routeWarning = '链接含有重复参数。可清空筛选后继续。';
      result[key] = value;
    }
    return result;
  }
  function updateURL(push) {
    const query = routeQuery(state); const url = location.pathname + (query ? '?' + query : '');
    if (url === location.pathname + location.search) return;
    history[push ? 'pushState' : 'replaceState']({ atlas: true }, '', url);
  }
  function navigate(next, { push = true, scroll = false } = {}) {
    const oldGraph = state.graph; state = { ...next }; routeWarning = ''; updateURL(push);
    if (scroll || oldGraph !== state.graph) window.scrollTo({ top: 0, behavior: 'instant' });
    if (!state.graph) return renderOverview();
    if (!catalog.graphs.some(g => g.id === state.graph)) return renderError('这个图谱尚未登记', '链接中的图谱名称不在当前目录里。已有材料没有被修改，请从总览选择。');
    if (oldGraph !== state.graph || !$('#browse-view')) buildBrowseShell(); else syncControls();
    loadBrowse();
  }
  async function getJSON(url, signal) {
    const response = await fetch(url, { signal, credentials: 'same-origin', cache: 'no-store' });
    let result;
    try { result = await response.json(); } catch { throw new Error('服务未返回图谱数据。请确认知题本机服务已加载当前版本。'); }
    if (!response.ok) throw new Error(result.error || `读取失败（${response.status}）`);
    if (result.schemaVersion !== 1) throw new Error('图谱接口版本与页面不一致，未混用旧数据。');
    return result;
  }
  function miniGraph(kind) {
    const body = kind === 'thinking' ? '<path d="M8 25H49"></path><circle cx="9" cy="25" r="5"></circle><circle class="mini-focus" cx="28" cy="25" r="6"></circle><circle cx="48" cy="25" r="5"></circle>' : kind === 'textbooks' ? '<path d="M27 10V38M27 24H10M27 24H45"></path><rect class="mini-focus" x="20" y="3" width="14" height="12" rx="2"></rect><rect x="4" y="29" width="12" height="13" rx="2"></rect><rect x="38" y="29" width="12" height="13" rx="2"></rect>' : '<path d="M10 12L28 25L48 11M28 25L10 39M28 25L49 40"></path><circle cx="10" cy="12" r="4"></circle><circle cx="48" cy="11" r="4"></circle><circle cx="10" cy="39" r="4"></circle><circle cx="49" cy="40" r="4"></circle><circle class="mini-focus" cx="28" cy="25" r="7"></circle>';
    return `<svg class="mini-map" viewBox="0 0 58 48" aria-hidden="true">${body}</svg>`;
  }
  function graphHref(id, extra = {}) { return 'graphs.html?' + routeQuery({ graph: id, ...extra }); }
  function renderOverview() {
    generation++; controller?.abort(); current = null;
    if (fullscreenMode) { fullscreenMode = false; fullscreenRestore = null; document.body.classList.remove('atlas-fullscreen-open'); if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); }
    document.title = '知题 · 全部图谱'; $('#overview-link').setAttribute('aria-current', 'page');
    const local = catalog.graphs.filter(g => g.family === 'local');
    const external = catalog.graphs.filter(g => g.family === 'external');
    const extra = catalog.graphs.filter(g => g.family === 'supplementary');
    const publicMode = catalog.scope?.anonymousAccess === true;
    const localDescriptions = {
      curriculum: '数学 233 · 语文 119 · 英语 157，另有 2 个研究扩展', foundation: '189 个小学、初中知识 · 361 条登记先备', papers: '8 卷 210 题，525 条知识用途；跨题联系另列', thinking: '具体步骤、为什么这样想，以及题目的关键机制', textbooks: '5 本教材、29 份教辅 · 保留 PDF 物理页入口'
    };
    const localSection = local.length ? `<section class="directory-section"><div class="section-heading"><h2>本地已经建立的关系</h2><span>${local.length} 类</span></div><div class="directory-list">${local.map(g => `<a class="directory-row" data-graph-route="${esc(g.id)}" href="${esc(graphHref(g.id, g.id === 'textbooks' ? { node: 'ct-senior1:c1' } : {}))}">${miniGraph(g.id)}<div><h3>${esc(titleFor(g))}</h3><p>${esc(localDescriptions[g.id] || g.subtitle)}</p><div class="row-meta">${number(g.nodeCount)} 个图节点 · ${number(g.edgeCount)} 条关系</div></div><span class="row-arrow" aria-hidden="true">↗</span></a>`).join('')}</div><p class="directory-note">这里的图节点包含知识、题目、步骤或书页，不能相加当作“知识总数”。题级关系仍是研究判断，不代表学生已经掌握。</p></section>` : '';
    const extraSection = extra.length ? `<section class="supplementary-section"><div class="section-heading"><h2>关联与覆盖，也可以查</h2><span>辅助视图 · 不重复计入 ${number(catalog.counts.browsable)} 个入口</span></div><div class="supplementary-links">${extra.map(g => `<a data-graph-route="${esc(g.id)}" href="${esc(graphHref(g.id))}">${esc(titleFor(g))} ↗<small>${g.id === 'mapping' ? '候选、逐源支持与旧卷映射' : '真实卷题绑定、课堂与练习缺口'}</small></a>`).join('')}</div></section>` : '';
    const scopeText = publicMode ? '免密码公开的非商业图谱；仅包含许可明确的五份来源，各源许可证与署名保留。' : deployed ? '口令保护的私人非商业图谱；受限来源不对匿名访客开放，未获公开再分发授权。' : '本机只读，不上传材料。';
    const licenseNote = publicMode ? `<div class="scope-note"><span>许可与源码</span><p>S01 ODbL/CC BY-SA · S02 CC BY-NC-SA · S03 CC BY-NC · S04 ODbL/CC BY-SA · S06 PolyForm Noncommercial。<a href="${esc(catalog.scope.repository)}" rel="noopener noreferrer">GitHub 源码、完整许可证与署名 ↗</a></p></div>` : '';
    main.innerHTML = `<section id="atlas-overview"><div class="overview-heading"><div><div class="eyebrow">已有材料，放在同一处看清楚</div><h1>图谱，都在这里</h1><p>选一张图，搜索知识或题目。关系、解释和依据在同一页，沿着节点继续看。</p></div><div class="inventory-total"><strong>${number(catalog.counts.browsable)}</strong><small>个主浏览入口</small></div></div><div class="overview-grid">${localSection}<section class="directory-section"><div class="section-heading"><h2>外部知识图谱</h2><span>${external.length} 份独立来源</span></div><div class="directory-list">${external.map(g => `<a class="directory-row source-row" data-graph-route="${esc(g.id)}" href="${esc(graphHref(g.id))}"><span class="source-id">${esc(g.id)}</span><div><h3>${esc(titleFor(g))}</h3><p>${esc(SOURCE_DESCRIPTIONS[g.id])}</p></div><span class="source-stat">${number(g.nodeCount)}<small>来源实体</small></span><span class="row-arrow" aria-hidden="true">↗</span></a>`).join('')}</div><p class="directory-note">${publicMode ? '五源' : '七源'}保持原来的身份与关系，不按同名合并。目录计数来自当前本地登记，进入后核对实际加载；原语言和支持缺口保留。</p></section></div>${extraSection}<div class="scope-note"><span>使用范围</span><p>${scopeText} 能力测量、错误诊断和跨学科完整图谱尚未建成，不拿现有研究关系冒充。</p></div>${licenseNote}</section>`;
    window.ATLAS_STATUS = { ready: true, view: 'overview', graphCount: catalog.counts.browsable, renderedGraphLinks: catalog.graphs.length, version: catalog.version, publicMode };
  }
  function graphDescription(graph) {
    if (graph.family === 'external') return `${SOURCE_DESCRIPTIONS[graph.id]}。搜索原条目，直接读它的原关系与支持范围。`;
    const descriptions = { curriculum: '从一个知识看它的含义、基础与后续连接。509 个课程节点，2 个研究扩展单列，不当作官方逐题标签。', foundation: '从小学、初中知识看基础如何连接。来源是本地课程设计，先备关系是课程组织建议。', papers: '看具体题目用了什么知识、为什么这样连接，以及同卷和跨卷有哪些联系。', thinking: '把题目、思考步骤与关键机制接在一起。动作与理由直接呈现，不把展示顺序当作必修路线。', textbooks: '看书、已登记章节与真实物理页。教材 5 本，教辅 29 份；有页节点不代表这一页已核读。', mapping: '看知识、具体要求与七源支持的连接。名称候选、部分支持、方法迁移和教材定位保持区别。', ledger: '看已研究知识绑定了哪些卷题，哪些已经有课堂或练习、哪些还缺。不是个人学习进度。' };
    return descriptions[graph.id] || graph.subtitle;
  }
  function buildBrowseShell() {
    const graph = catalog.graphs.find(g => g.id === state.graph);
    current = null;
    document.title = `知题 · ${titleFor(graph)}`; $('#overview-link').removeAttribute('aria-current'); zoom = 1.2;
    main.innerHTML = `<section class="browse-view" id="browse-view" aria-busy="true"><div class="browse-heading"><div><div class="eyebrow">${graph.family === 'external' ? `${esc(graph.id)} · ${esc(graph.sourceName)}` : graph.family === 'supplementary' ? '关联与覆盖 · 辅助视图' : '本地课程与研究'}</div><h1>${esc(titleFor(graph))}</h1><p>${esc(graphDescription(graph))}</p></div><label class="graph-choice-label">换一张图谱<select id="graph-choice" aria-label="选择图谱">${['local', 'external', 'supplementary'].filter(family => catalog.graphs.some(g => g.family === family)).map(family => `<optgroup label="${{ local: '本地图谱', external: '外部来源', supplementary: '辅助视图' }[family]}">${catalog.graphs.filter(g => g.family === family).map(g => `<option value="${esc(g.id)}" ${g.id === graph.id ? 'selected' : ''}>${esc(titleFor(g))}</option>`).join('')}</optgroup>`).join('')}</select></label></div><form class="filter-bar" id="atlas-filters"><label class="search-label">搜索节点<div class="search-field"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m16 16 5 5"></path></svg><input id="node-search" type="search" autocomplete="off" maxlength="160" aria-label="搜索知识、题目或节点" placeholder="${graph.id === 'textbooks' ? '例如：集合、必修、PDF第19页' : graph.id === 'papers' || graph.id === 'thinking' ? '例如：补集、椭圆、2025' : graph.id === 'S01' ? '原语言检索，例如：Fractions、Adding' : '例如：补集、分数、主谓一致'}"></div></label><label>学科<select id="subject-filter" aria-label="按学科筛选"><option value="">全部学科</option></select></label><label>学段<select id="stage-filter" aria-label="按学段筛选"><option value="">全部学段</option></select></label><label>${['papers', 'thinking'].includes(graph.id) ? '试卷' : graph.id === 'foundation' ? '年级' : '分组'}<select id="group-filter" aria-label="按分组筛选"><option value="">全部分组</option></select></label><label>节点类型<select id="kind-filter" aria-label="按节点类型筛选"><option value="">全部类型</option></select></label></form><div class="graph-counts"><span>全图 <span class="count" id="full-node-count">${number(graph.nodeCount)}</span> 个节点</span><span><span class="count" id="full-edge-count">${number(graph.edgeCount)}</span> 条关系</span><span class="request-status" id="request-status" role="status">正在读取本地图谱…</span></div><div id="scope-alert"></div><div class="atlas-layout"><aside class="results-pane" aria-label="匹配节点"><div class="results-heading"><h2>节点列表</h2><span id="result-count">读取中</span></div><div class="node-results" id="node-results"></div><div class="pagination"><button type="button" id="previous-page" aria-label="上一页节点" disabled>←</button><span id="page-status">—</span><button type="button" id="next-page" aria-label="下一页节点" disabled>→</button></div></aside><div class="atlas-workspace"><div class="current-object" id="graph-stage"><section class="graph-card" aria-label="当前节点的关系图"><div class="graph-toolbar"><h2 id="graph-caption-title">围绕当前对象看关系</h2><div class="graph-controls"><select id="relation-filter" aria-label="关系类型"><option value="all">全部关系</option><option value="prerequisite">原生先备</option><option value="related">原生相关</option></select><select id="hops-filter" aria-label="关系跳数"><option value="1">一跳</option><option value="2">两跳</option></select><button type="button" id="zoom-out" aria-label="缩小关系图">−</button><button type="button" id="zoom-in" aria-label="放大关系图">＋</button><output id="graph-zoom" aria-label="图谱缩放比例">120%</output><button type="button" id="center-graph" aria-label="居中当前节点">居中</button><button type="button" id="fullscreen-graph" class="fullscreen-action" aria-label="全屏查看图谱" aria-pressed="false">全屏查看 ↗</button></div></div><div class="graph-viewport" id="graph-viewport" aria-label="关系图，可在图内横向和纵向滚动"><div class="initial-state"><span class="loading-dot" aria-hidden="true"></span><p>读取真实节点与连线</p></div></div><div class="graph-legend"><span><i></i>知识 / 当前对象</span><span><i class="legend-orange"></i>题目 / 步骤</span><span><i class="legend-aqua"></i>书 / 物理页</span></div><p class="graph-caption" id="neighborhood-status">点节点，说明和关系会在原位更新；图内可拖动。</p><p class="graph-hover" id="graph-hover" aria-live="polite">沿箭头看关系；下方文字同时保留原因。</p></section><article class="object-detail" id="object-detail" aria-label="当前节点的内容与依据"><p class="object-meta">加载后在这里直接读内容与依据。</p></article></div><section id="object-evidence" class="object-evidence" aria-label="当前节点的原内容与支持范围" hidden></section><section class="relations-section"><div class="relations-heading"><h2>这些连接，为什么成立</h2><span id="relations-count"></span></div><p class="relations-intro" id="relations-intro">真实关系与候选联系分开显示。它们不是对某个学生的判断。</p><div class="relation-rows" id="relation-rows"></div><div class="relations-pagination" id="relations-pagination"></div></section><div class="data-notes" id="data-notes"></div></div></div></section>`;
    $('#graph-choice').onchange = e => navigate({ graph: e.target.value, ...(e.target.value === 'textbooks' ? { node: 'ct-senior1:c1' } : {}) }, { scroll: true });
    $('#atlas-filters').onsubmit = event => { event.preventDefault(); clearTimeout(debounce); applyFilters(); };
    $('#node-search').oninput = () => { clearTimeout(debounce); debounce = setTimeout(applyFilters, 220); };
    for (const id of ['subject-filter', 'stage-filter', 'group-filter', 'kind-filter']) $('#' + id).onchange = applyFilters;
    $('#relation-filter').onchange = event => navigate({ ...state, relation: event.target.value, edgePage: undefined });
    $('#hops-filter').onchange = event => navigate({ ...state, hops: event.target.value });
    $('#previous-page').onclick = () => navigate({ ...state, page: Math.max(1, Number(current?.list.page || 1) - 1), node: undefined, edgePage: undefined });
    $('#next-page').onclick = () => navigate({ ...state, page: Number(current?.list.page || 1) + 1, node: undefined, edgePage: undefined });
    $('#zoom-out').onclick = () => changeZoom(-.2); $('#zoom-in').onclick = () => changeZoom(.2); $('#center-graph').onclick = centerDiagram;
    $('#fullscreen-graph').onclick = toggleFullscreen;
    bindPanning(); syncControls(); syncFullscreen();
  }
  function applyFilters() {
    if (!$('#node-search')) return;
    navigate({ ...state, q: $('#node-search').value.trim(), subject: $('#subject-filter').value, stage: $('#stage-filter').value, group: $('#group-filter').value, kind: $('#kind-filter').value, page: undefined, node: undefined, edgePage: undefined }, { push: false });
  }
  function groupLabel(value) {
    if (/^(math|english|chinese)-\d{4}-national\d$/.test(value)) {
      const [subject, year, family] = value.split('-'); return `${year} 全国${family.endsWith('2') ? 'Ⅱ' : 'Ⅰ'}卷${subjectFor(subject)}`;
    }
    if (state.graph === 'foundation' && /^\d+$/.test(value)) return `${value}年级`;
    return value === 'unknown' ? '未标注' : value;
  }
  function syncControls() {
    if (!$('#node-search')) return;
    $('#node-search').value = state.q || '';
    for (const [field, id] of [['subject', 'subject-filter'], ['stage', 'stage-filter'], ['group', 'group-filter'], ['kind', 'kind-filter']]) {
      const select = $('#' + id); if (Array.from(select.options).some(o => o.value === (state[field] || ''))) select.value = state[field] || '';
    }
    $('#relation-filter').value = state.relation || 'all'; $('#hops-filter').value = state.hops || '1';
  }
  function setFilterOptions(filters) {
    for (const [field, key, id, empty] of [['subject', 'subjects', 'subject-filter', '全部学科'], ['stage', 'stages', 'stage-filter', '全部学段'], ['group', 'groups', 'group-filter', '全部分组'], ['kind', 'kinds', 'kind-filter', '全部类型']]) {
      const select = $('#' + id); const rows = filters[key] || [];
      const options = `<option value="">${empty}</option>` + rows.map(row => `<option value="${esc(row.value)}">${esc(field === 'subject' ? subjectFor(row.value) : field === 'group' ? groupLabel(row.value) : field === 'kind' ? KIND_LABELS[row.value] || row.label : row.label)} · ${number(row.count)}</option>`).join('');
      if (select.innerHTML !== options) select.innerHTML = options;
      if (state[field] && !rows.some(row => row.value === state[field])) {
        const option = document.createElement('option'); option.value = state[field]; option.textContent = '链接中的筛选值 · ' + state[field]; select.append(option);
      }
      select.value = state[field] || ''; select.disabled = rows.length <= 1 && !state[field];
    }
    const relations = filters.relations || [];
    const relationSelect = $('#relation-filter');
    relationSelect.innerHTML = '<option value="all">全部关系</option>' + relations.map(row => `<option value="${esc(row.value)}">${esc(wrapLabel(relationTypeFor({ relation: row.value, label: row.label }), 180, 1)[0])} · ${number(row.count)}</option>`).join('');
    if (state.relation && !relations.some(row => row.value === state.relation)) {
      const option = document.createElement('option'); option.value = state.relation; option.textContent = RELATION_LABELS[state.relation] || state.relation; relationSelect.append(option);
    }
    relationSelect.value = state.relation || 'all';
    relationSelect.disabled = !relations.length;
  }
  async function loadBrowse() {
    const id = ++generation; controller?.abort(); controller = new AbortController();
    const signal = controller.signal; const timer = setTimeout(() => controller?.signal === signal && controller.abort(), 25000); const started = performance.now();
    const frame = $('#browse-view'); if (!frame) return;
    frame.setAttribute('aria-busy', 'true'); $('#request-status').textContent = '正在读取本地图谱…';
    try {
      const query = new URLSearchParams(routeQuery(state)); query.set('size', '24');
      const data = await getJSON(atlasAPI('browse') + '?' + query, signal);
      if (id !== generation) return;
      current = data;
      state.page = data.list.page; state.edgePage = data.relations.page; state.node = data.selected?.id;
      updateURL(false); renderBrowseResult(data);
      $('#request-status').textContent = `已读取 · ${((performance.now() - started) / 1000).toFixed(2)} 秒`;
      window.ATLAS_STATUS = { ready: true, view: 'browse', graph: data.graph.id, selected: data.selected?.id || null, total: data.list.total, page: data.list.page, relationPage: data.relations.page, nodeCount: data.graph.nodeCount, edgeCount: data.graph.edgeCount, shownNodes: $('#graph-viewport svg')?.dataset.shownNodes || 0, waitMs: Math.round(performance.now() - started), version: data.graph.version, error: null };
    } catch (error) {
      if (id !== generation) return;
      const message = error.name === 'AbortError' ? '读取超过 25 秒，尚未载入。原材料没有被修改。' : error.message;
      $('#request-status').textContent = '当前请求未成功';
      $('#scope-alert').innerHTML = `<div class="scope-alert" role="alert">${esc(message)}${current ? ' 下方仍是上次成功读取的结果，不是当前查询。' : ''} <button type="button" id="retry-request">重试读取</button> <button type="button" id="reset-request">清空筛选</button></div>`;
      $('#retry-request').onclick = loadBrowse; $('#reset-request').onclick = () => navigate({ graph: state.graph });
      if (!current) { $('#graph-viewport').innerHTML = '<p class="list-empty">尚未取得当前图谱，未绘制替代数据。</p>'; $('#object-detail').innerHTML = '<h2>材料尚未载入</h2><p class="object-description">请重试或返回总览。不会用虚构节点填充。</p>'; }
      window.ATLAS_STATUS = { ready: false, graph: state.graph, error: message };
    } finally { clearTimeout(timer); if (id === generation) frame.setAttribute('aria-busy', 'false'); }
  }
  function renderBrowseResult(data) {
    setFilterOptions(data.filters); syncControls();
    $('#full-node-count').textContent = number(data.graph.nodeCount); $('#full-edge-count').textContent = number(data.graph.edgeCount);
    $('#result-count').textContent = `${number(data.list.total)} 个匹配`;
    $('#page-status').textContent = data.list.pages ? `${data.list.page} / ${data.list.pages} 页` : '没有匹配';
    $('#previous-page').disabled = data.list.page <= 1; $('#next-page').disabled = data.list.page >= data.list.pages;
    const selectedId = data.selected?.id;
    $('#node-results').innerHTML = data.list.nodes.length ? data.list.nodes.map(n => `<button class="result-button" type="button" data-select-node="${esc(n.id)}" aria-pressed="${n.id === selectedId}"><span>${esc(n.label)}</span><small>${esc(kindFor(n))} · ${esc(subjectFor(n.subject))}${n.stage !== 'unknown' ? ' · ' + esc(n.stage) : ''}</small></button>`).join('') : '<div class="list-empty">没有匹配节点。<br>可清空关键词或改换筛选。<br><button type="button" id="clear-empty">清空筛选</button></div>';
    if ($('#clear-empty')) $('#clear-empty').onclick = () => navigate({ graph: state.graph });
    const unsupported = data.graph.id === 'S07';
    let note = routeWarning;
    if (unsupported) note = 'EDUKG 当前读取模式只有概念和定位属性，不支持先备关系查询。没有可画的原生先备边，不代表没有学习联系。';
    else if (data.notice.includes('一致性=不一致')) note = '当前登记与实际加载有差异。下方使用实际加载的节点和关系，不沿用旧统计。';
    else if (data.notice.includes('ambiguous')) note = '有原ID对应多个标签，已保留歧义，没有偷偷选一个名称或正文。';
    if (selectedId && !data.list.nodes.some(n => n.id === selectedId)) note = (note ? note + ' ' : '') + (data.list.total ? '正在显示链接指定的节点；它不在当前列表页，图和内容仍围绕这个节点。' : '搜索结果为0；仍按链接显示指定节点，不把它计入搜索匹配。清空筛选即可回到完整列表。');
    if (data.notice.includes('分页越界')) note = (note ? note + ' ' : '') + '链接中的分页超出范围，已调整到实际有效页。';
    $('#scope-alert').innerHTML = note ? `<div class="scope-alert" role="status">${esc(note)}</div>` : '';
    const prerequisiteOption = $('#relation-filter').querySelector('option[value="prerequisite"]');
    if (prerequisiteOption) prerequisiteOption.disabled = unsupported;
    renderNodeDetail(data.selected); drawDiagram(); renderRelations(); renderDataNotes(data);
  }
  function renderStructure(data) {
    const structure = data?.structure;
    if (!data?.selected || !structure) return '';
    const presentation = SOURCE_PRESENTATIONS[data.graph.id];
    const heading = structure.mode === 'native' ? '教材归属路径' : structure.mode === 'taxonomy' ? '原始分类与年龄范围' : '来源登记归属路径';
    const pathHTML = (path, pathIndex) => `<ol class="structure-path" aria-label="归属路径 ${pathIndex + 1}">${path.map((item, index) => {
      const last = index === path.length - 1;
      const label = esc(item.label);
      let content = `<span>${label}</span>`;
      if (last && item.nodeId === data.selected.id) content = `<strong aria-current="page">${label}</strong>`;
      else if (item.nodeId) content = `<button type="button" data-select-node="${esc(item.nodeId)}">${label}</button>`;
      else if (item.query) content = `<button type="button" data-structure-query="${esc(JSON.stringify(item.query))}">${label}</button>`;
      return `<li data-structure-field="${esc(item.field)}">${content}</li>`;
    }).join('<li class="structure-arrow" aria-hidden="true">→</li>')}</ol>`;
    return `<section class="structure-panel" aria-label="当前节点的归属结构"><div class="structure-heading"><h2>${heading}</h2>${presentation ? `<a href="${esc(presentation.url)}" target="_blank" rel="noopener noreferrer" title="${esc(presentation.label)}">原始项目呈现 ↗</a>` : ''}</div><div class="structure-paths">${(structure.paths || []).map(pathHTML).join('')}</div>${structure.facets?.length ? `<div class="structure-facets">${structure.facets.map(item => `<span>${esc(item.label)}</span>`).join('')}</div>` : ''}<p class="structure-note">${esc(structure.note || '')}${structure.truncated ? ` 另有 ${number(structure.truncated)} 条归属路径未展开。` : ''}</p></section>`;
  }
  function renderNodeDetail(n) {
    if (!n) { $('#object-detail').innerHTML = '<h2>没有匹配节点</h2><p class="object-description">试试另一关键词，或清空筛选继续。原图数据仍保留。</p>'; $('#object-evidence').hidden = true; $('#object-evidence').innerHTML = ''; return; }
    const fields = readableFields(n.details).filter(d => d.label !== '表现目标' && d.value !== n.description);
    const goals = (n.details || []).find(d => d.label === '表现目标' && d.value && d.value !== n.description);
    const links = (n.links || []).filter(link => link.available !== false && safeHref(link.url));
    const unavailableLinks = (n.links || []).filter(link => link.available === false);
    const supplementalFields = n.readingSupplement ? [{ label: '助手原创补充 · 非教材原文', value: n.readingSupplement.basis }] : [];
    const source = n.source;
    const statuses = [...new Set([n.status, source?.status].filter(Boolean).map(readableStatus))];
    const longBoundary = String(n.boundary || '').length > 180;
    const sourceFields = fields.filter(d => ['ISBN', '教材名称', '原章节', '原节', '纸书印刷页', '原年级', '原始年级字段'].includes(d.label)).slice(0, 5);
    const wideFields = [...fields.filter(d => !sourceFields.includes(d)), ...supplementalFields];
    const evidence = $('#object-evidence');
    evidence.hidden = !wideFields.length && !longBoundary;
    evidence.innerHTML = `<div class="relations-heading"><h2>原内容与支持范围</h2><span>内容来自登记材料，不凭标题补造</span></div><div class="evidence-fields">${wideFields.map(d => `<div class="detail-field"><h3>${esc(fieldLabel(d.label))}</h3><div>${formatValue(d.value)}</div></div>`).join('')}${longBoundary ? `<div class="detail-field evidence-boundary"><h3>适用范围与缺口</h3><p>${esc(boundaryFor(n.boundary))}</p></div>` : ''}</div>`;
    const description = n.description || (current.graph.id === 'S07' ? '此原条目用于概念或材料定位。当前记录没有独立定义正文，不以名称补造解释。' : '这个节点保留了名称与关系，独立解释正文尚未登记。下方可以查看实际连接。');
    $('#object-detail').innerHTML = `${renderStructure(current)}<div class="object-meta">${esc(kindFor(n))} · ${esc(subjectFor(n.subject))}${n.stage !== 'unknown' ? ' · ' + esc(n.stage) : ''}</div><h2>${esc(n.label)}</h2>${statuses.length ? `<p class="object-status">${statuses.map(esc).join(' · ')}</p>` : ''}<p class="object-description">${esc(description)}</p>${n.notation ? `<p class="object-notation">${esc(n.notation)}</p>` : ''}${n.example ? `<section class="object-section"><h3>用一个例子理解</h3><p class="object-example">${esc(n.example)}</p></section>` : ''}${goals ? `<section class="object-section"><h3>原课程表现目标</h3><p>${esc(goals.value)}</p></section>` : ''}${sourceFields.length ? `<section class="object-section"><dl class="detail-fields">${sourceFields.map(d => `<div class="detail-field"><dt>${esc(fieldLabel(d.label))}</dt><dd>${formatValue(d.value)}</dd></div>`).join('')}</dl></section>` : ''}${unavailableLinks.length ? `<section class="object-section"><h3>尚未上线的原材料</h3>${unavailableLinks.map(link => `<p class="object-boundary">${esc(link.label)}：${esc(link.reason || '本发行保留定位，不复制原文件。')}</p>`).join('')}</section>` : ''}${links.length ? `<section class="object-section"><h3>原题与原材料</h3><div class="original-links">${links.map(link => `<a href="${esc(safeHref(link.url))}" target="_blank" rel="noopener noreferrer">${esc(link.label)} ↗</a>`).join('')}</div></section>` : ''}${source ? `<section class="object-section"><h3>内容来自哪里</h3><p>${esc(sourceNameFor(source.name) || '当前登记材料')}</p>${source.role ? `<p class="object-boundary">${esc(source.role)}</p>` : ''}${source.locator ? `<p class="source-locator">${esc(cleanLocator(source.locator))}</p>` : ''}</section>` : ''}${n.boundary && !longBoundary ? `<section class="object-section"><h3>适用范围与缺口</h3><p class="object-boundary">${esc(boundaryFor(n.boundary))}</p></section>` : ''}${wideFields.length || longBoundary ? `<section class="fullscreen-evidence"><h3>内容与依据</h3>${wideFields.map(d => `<div class="detail-field"><h4>${esc(fieldLabel(d.label))}</h4><div>${formatValue(d.value)}</div></div>`).join('')}${longBoundary ? `<div class="detail-field"><h4>适用范围与缺口</h4><p>${esc(boundaryFor(n.boundary))}</p></div>` : ''}</section>` : ''}<details class="technical-note"><summary>节点标识与固定版本</summary><p>${esc(n.id)}</p>${source?.version ? `<p>${esc(source.version)}</p>` : ''}${(n.details || []).filter(d => (isTechnicalField(d) || d.label === '理解辅助来源') && d.value).map(d => `<p>${esc(d.label)}：${esc(cleanLocator(d.value))}</p>`).join('')}</details>`;
  }
  function drawDiagram() {
    const viewport = $('#graph-viewport'); if (!viewport || !current) return;
    if (!current.selected) { viewport.innerHTML = '<div class="initial-state"><h2>没有匹配节点</h2><p>清空筛选，回到实际关系。</p></div>'; $('#neighborhood-status').textContent = '未绘制图形，不用旧对象替代当前无结果状态。'; return; }
    const slice = diagramSlice(current.neighborhood, current.selected.id, fullscreenActive() ? 31 : 21);
    const columns = [...new Set(slice.nodes.map(n => n.distance))].sort((a, b) => a - b);
    const nodeW = 272, nodeH = 104, gapX = 114, rowGap = 22, paddingX = 54;
    const grouped = new Map(columns.map(d => [d, slice.nodes.filter(n => n.distance === d).sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))]));
    const maxRows = Math.max(1, ...[...grouped.values()].map(items => items.length));
    const height = Math.max(365, 64 + maxRows * (nodeH + rowGap) + 28); const width = Math.max(360, columns.length * nodeW + Math.max(0, columns.length - 1) * gapX + paddingX * 2);
    const positions = new Map();
    for (const [index, distance] of columns.entries()) {
      const items = grouped.get(distance), blockH = items.length * (nodeH + rowGap) - rowGap;
      const top = 62 + (height - 90 - blockH) / 2;
      items.forEach((n, row) => positions.set(n.id, { x: paddingX + index * (nodeW + gapX), y: top + row * (nodeH + rowGap) }));
    }
    let svg = `<svg id="atlas-diagram" width="${width * zoom}" height="${height * zoom}" viewBox="0 0 ${width} ${height}" data-natural-width="${width}" data-natural-height="${height}" data-shown-nodes="${slice.nodes.length}" role="group" aria-label="${esc(current.selected.label)}的实际关系，当前显示${slice.nodes.length}个节点"><defs><marker id="atlas-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M1 1L8 5L1 9" fill="none" stroke="var(--edge)" stroke-width="1.5"></path></marker></defs>`;
    columns.forEach((distance, index) => { const label = distance < 0 ? `关系指向当前 · ${Math.abs(distance)}跳` : distance > 0 ? `从当前连接出去 · ${distance}跳` : '当前对象'; svg += `<text class="graph-column-label" x="${paddingX + index * (nodeW + gapX) + nodeW / 2}" y="30" text-anchor="middle">${label}</text>`; });
    const edgeLabels = [];
    slice.edges.forEach((edge, index) => {
      const from = positions.get(edge.source), to = positions.get(edge.target); if (!from || !to) return;
      const forward = to.x > from.x; const sameColumn = to.x === from.x;
      const x1 = from.x + (sameColumn || forward ? nodeW : 0), x2 = to.x + (sameColumn || !forward ? nodeW : 0), y1 = from.y + nodeH / 2, y2 = to.y + nodeH / 2;
      const offset = sameColumn ? 40 : Math.abs(x2 - x1) * .52;
      const path = sameColumn ? `M${x1},${y1} C${x1 + offset},${y1} ${x2 + offset},${y2} ${x2},${y2}` : `M${x1},${y1} C${x1 + (forward ? offset : -offset)},${y1} ${x2 - (forward ? offset : -offset)},${y2} ${x2},${y2}`;
      const direct = edge.source === current.selected.id || edge.target === current.selected.id;
      svg += `<path class="graph-edge${direct ? '' : ' secondary'}${['candidate', 'bridge', 'external_bridge', 'designed_route'].includes(edge.relation) ? ' candidate' : ''}" d="${path}" marker-end="url(#atlas-arrow)"></path><path class="graph-edge-hit" d="${path}" data-edge-index="${index}"><title>${esc(edge.fromLabel)} → ${esc(edge.toLabel)} · ${esc(relationFor(edge))}${edge.reason ? '：' + esc(edge.reason) : ''}</title></path>`;
      if (direct && !sameColumn && edgeLabels.length < 8) edgeLabels.push({ x: (x1 + x2) / 2, y: (y1 + y2) / 2 - 7, text: relationTypeFor(edge) });
    });
    for (const label of edgeLabels) { const short = wrapLabel(label.text, 83, 2, measure); const labelWidth = Math.max(...short.map(measure)) + 10; svg += `<rect class="edge-caption-bg" x="${label.x - labelWidth / 2}" y="${label.y - 11}" width="${labelWidth}" height="${short.length * 13 + 4}" rx="3"></rect><text class="edge-caption" x="${label.x}" y="${label.y}" text-anchor="middle">${short.map((line, i) => `<tspan x="${label.x}" dy="${i ? 13 : 0}">${esc(line)}</tspan>`).join('')}</text>`; }
    slice.nodes.forEach(n => {
      const pos = positions.get(n.id); const lines = wrapLabel(n.label, nodeW - 31, 3, measure); const currentNode = n.id === current.selected.id;
      const typeLine = wrapLabel(kindFor(n) + (n.stage !== 'unknown' ? ' · ' + n.stage : ''), nodeW - 38, 1, measure)[0];
      svg += `<g class="atlas-node${currentNode ? ' current' : ''}" data-node-id="${esc(n.id)}" data-kind="${esc(n.kind)}" tabindex="0" role="button" aria-label="查看${esc(n.label)}" aria-pressed="${currentNode}" transform="translate(${pos.x} ${pos.y})"><title>${esc(n.label)} · ${esc(kindFor(n))}</title><rect class="node-box" width="${nodeW}" height="${nodeH}" rx="9"></rect><circle class="node-dot" cx="15" cy="16" r="3.5"></circle><text class="node-type" x="25" y="19">${esc(typeLine)}</text><text class="node-label" x="15" y="${lines.length === 1 ? 62 : 48}">${lines.map((line, i) => `<tspan x="15" dy="${i ? 22 : 0}">${esc(line)}</tspan>`).join('')}</text></g>`;
    });
    if (slice.nodes.length === 1 && current.graph.id === 'S07') svg += `<text class="graph-column-label" x="${width / 2}" y="${height - 22}" text-anchor="middle">当前模式未提供先备边，不补画箭头</text>`;
    viewport.innerHTML = svg + '</svg>';
    const currentPos = positions.get(current.selected.id); viewport.dataset.centerX = (currentPos.x + nodeW / 2) * zoom; viewport.dataset.centerY = (currentPos.y + nodeH / 2) * zoom;
    viewport.querySelectorAll('[data-node-id]').forEach(element => {
      element.onclick = () => selectNode(element.dataset.nodeId);
      element.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectNode(element.dataset.nodeId); } };
      const n = slice.nodes.find(n => n.id === element.dataset.nodeId);
      element.onpointerenter = element.onfocus = () => { $('#graph-hover').textContent = `${kindFor(n)} · ${n.label}`; };
    });
    viewport.querySelectorAll('[data-edge-index]').forEach(element => { element.onpointerenter = () => { const edge = slice.edges[Number(element.dataset.edgeIndex)]; $('#graph-hover').textContent = `${edge.fromLabel} → ${edge.toLabel} · ${relationFor(edge)}${edge.reason ? '：' + edge.reason : ''}`; }; });
    const allNodes = current.neighborhood.totalNodes, allEdges = current.neighborhood.totalEdges;
    $('#neighborhood-status').textContent = `当前图显示 ${slice.nodes.length} 个节点、${slice.edges.length} 条连线${slice.truncated ? `；本次邻域共有 ${number(allNodes)} 个节点、${number(allEdges)} 条关系，下方可分页查看当前对象的全部直接关系，两跳关系可沿相邻节点继续查。` : '，对应当前查询的实际邻域。'} 点节点原位更新；可拖动或滚动图形。`;
    requestAnimationFrame(centerDiagram); syncZoom();
  }
  function centerDiagram() {
    const viewport = $('#graph-viewport'); if (!viewport) return;
    viewport.scrollLeft = Math.max(0, Number(viewport.dataset.centerX || 0) - viewport.clientWidth / 2);
    viewport.scrollTop = Math.max(0, Number(viewport.dataset.centerY || 0) - viewport.clientHeight / 2);
  }
  function changeZoom(delta) {
    const viewport = $('#graph-viewport'), svg = $('#atlas-diagram');
    if (!viewport || !svg) return;
    const previous = zoom;
    zoom = Math.min(3, Math.max(.7, Math.round((zoom + delta) * 100) / 100));
    const focusX = (viewport.scrollLeft + viewport.clientWidth / 2) / previous;
    const focusY = (viewport.scrollTop + viewport.clientHeight / 2) / previous;
    svg.setAttribute('width', Number(svg.dataset.naturalWidth) * zoom);
    svg.setAttribute('height', Number(svg.dataset.naturalHeight) * zoom);
    viewport.dataset.centerX = Number(viewport.dataset.centerX || 0) * zoom / previous;
    viewport.dataset.centerY = Number(viewport.dataset.centerY || 0) * zoom / previous;
    viewport.scrollLeft = Math.max(0, focusX * zoom - viewport.clientWidth / 2);
    viewport.scrollTop = Math.max(0, focusY * zoom - viewport.clientHeight / 2);
    syncZoom();
  }
  function syncZoom() {
    if ($('#graph-zoom')) $('#graph-zoom').textContent = Math.round(zoom * 100) + '%';
    if ($('#zoom-out')) $('#zoom-out').disabled = zoom <= .7;
    if ($('#zoom-in')) $('#zoom-in').disabled = zoom >= 3;
  }
  function syncFullscreen() {
    const stage = $('#graph-stage');
    if (!stage) return;
    stage.classList.toggle('graph-expanded', fullscreenMode);
    document.body.classList.toggle('atlas-fullscreen-open', fullscreenMode);
    document.querySelectorAll('.site-header, .results-pane, .browse-heading, .filter-bar, .graph-counts, #scope-alert, .object-evidence, .relations-section, .data-notes, .site-footer').forEach(element => { element.inert = fullscreenMode; });
    const button = $('#fullscreen-graph');
    if (button) {
      button.textContent = fullscreenMode ? '退出全屏 ×' : '全屏查看 ↗';
      button.setAttribute('aria-label', fullscreenMode ? '退出图谱全屏并返回' : '全屏查看图谱');
      button.setAttribute('aria-pressed', String(fullscreenMode));
    }
    syncZoom();
  }
  async function toggleFullscreen() {
    if (fullscreenMode) return exitFullscreen();
    const stage = $('#graph-stage'), viewport = $('#graph-viewport');
    if (!stage || !current?.selected) return;
    fullscreenRestore = { top: scrollY, left: viewport.scrollLeft, graphTop: viewport.scrollTop, zoom, node: current.selected.id };
    fullscreenMode = true; syncFullscreen();
    // Native fullscreen requires the user's click; window-fill remains a usable fallback.
    if (stage.requestFullscreen) {
      try { await stage.requestFullscreen(); }
      catch { $('#graph-hover').textContent = '浏览器未允许原生全屏，已铺满当前窗口。按 Esc 或退出全屏返回。'; }
    }
    requestAnimationFrame(() => { drawDiagram(); syncZoom(); });
  }
  async function exitFullscreen() {
    const previous = fullscreenRestore;
    fullscreenMode = false; syncFullscreen();
    if (document.fullscreenElement && document.exitFullscreen) {
      try { await document.exitFullscreen(); } catch { /* Window-fill is already removed. */ }
    }
    requestAnimationFrame(() => {
      if (current?.selected) drawDiagram();
      requestAnimationFrame(() => {
        if (previous) {
          window.scrollTo({ top: previous.top, behavior: 'instant' });
          const viewport = $('#graph-viewport');
          if (viewport && current?.selected?.id === previous.node && zoom === previous.zoom) {
            viewport.scrollLeft = previous.left; viewport.scrollTop = previous.graphTop;
          }
        }
        $('#fullscreen-graph')?.focus({ preventScroll: true });
        fullscreenRestore = null; syncZoom();
      });
    });
  }
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement && fullscreenMode) exitFullscreen();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && fullscreenMode && !document.fullscreenElement) { event.preventDefault(); exitFullscreen(); }
  });
  function bindPanning() {
    const viewport = $('#graph-viewport'); let drag = null;
    viewport.onpointerdown = event => {
      if (event.button !== 0 || event.pointerType === 'touch' || event.target.closest('.atlas-node')) return;
      drag = { x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop, id: event.pointerId };
      viewport.setPointerCapture(event.pointerId); viewport.classList.add('is-dragging');
    };
    viewport.onpointermove = event => { if (!drag) return; viewport.scrollLeft = drag.left - (event.clientX - drag.x); viewport.scrollTop = drag.top - (event.clientY - drag.y); };
    const end = () => { if (drag && viewport.hasPointerCapture(drag.id)) viewport.releasePointerCapture(drag.id); drag = null; viewport.classList.remove('is-dragging'); };
    viewport.onpointerup = viewport.onpointercancel = end;
  }
  function selectNode(id) { if (!id || !current || current.graph.id !== state.graph || id === current.selected?.id) return; navigate({ ...state, node: id, edgePage: undefined }); }
  function renderRelations() {
    const rows = current?.relations.edges || []; const selected = current?.selected;
    const relationPage = current?.relations.page || 1, pageSize = current?.relations.size || 8, pageCount = current?.relations.pages || 0;
    $('#relations-count').textContent = `${number(current?.relations.total || 0)} 条直接关系`;
    $('#relations-intro').textContent = selected ? `围绕「${selected.label}」的直接连接。方向与关系类型按原登记保留。${pageCount > 1 ? ` 所有 ${number(current.relations.total)} 条关系都可在下方分页查看。` : ''}` : '当前没有选中节点，不显示旧对象的关系。';
    const visible = rows;
    $('#relation-rows').innerHTML = visible.length ? visible.map(edge => {
      const incoming = edge.target === selected?.id; const otherId = incoming ? edge.source : edge.target; const otherLabel = incoming ? edge.fromLabel : edge.toLabel;
      const fallback = { prerequisite: '这条先备关系来自原课程 / 来源登记，尚未作为本题必要条件或学习者实证验证。', physical_page: '这是原PDF从1开始的物理页编号，不推定它对应某个未登记章节。', registered_chapter: '这本书中已实际登记的章或片段，未补造其他目录。', chapter_page: '这个章 / 片段对应已登记的PDF物理页。', has_step: '这是作者展示的解题步骤，详细动作与理由保留在步骤节点。', sequence: '表示展示路径的先后，既不排除其他正确解法，也不是学习者已经完成。', binding: '连接来自台账中的真实卷、题号与知识用途。', classroom_registration: '这里只确认已有课堂登记，不读个人学习记录，也不表示效果已验证。' };
      return `<article class="relation-row"><div class="relation-direction">${esc(relationTypeFor(edge))}<span>${incoming ? '相邻对象 → 当前' : '当前 → 相邻对象'}</span>${edge.status ? `<span>${esc({ direct: '本题操作支持', partial: '部分支持', transfer: '迁移参考', locator: '定位参考', out_of_scope: '范围外', none: '未找到支持', main: '本题主知识', support: '本题辅助知识' }[edge.status] || edge.status)}</span>` : ''}</div><div class="relation-main"><button type="button" class="relation-node-link" data-select-node="${esc(otherId)}">${esc(otherLabel)}</button>${relationFor(edge) !== relationTypeFor(edge) ? `<p class="relation-context">原关系标记：${esc(relationFor(edge))}</p>` : ''}<p>${esc(edge.reason || fallback[edge.relation] || '原来源登记了这条关系；独立的连接理由尚未补充，不据此推出必修或掌握。')}</p>${edge.boundary ? `<p class="relation-boundary">${esc(edge.boundary)}</p>` : ''}${edge.details?.length || edge.source_scope || edge.sourceLocator ? `<details class="relation-proof"><summary>关系原登记与依据</summary>${edge.sourceLocator ? `<p>${esc(cleanLocator(edge.sourceLocator))}</p>` : ''}${edge.source_scope ? `<div>${formatValue(edge.source_scope)}</div>` : ''}${(edge.details || []).map(d => `<p>${esc(fieldLabel(d.label))}：${formatValue(d.value)}</p>`).join('')}</details>` : ''}</div></article>`;
    }).join('') : `<p class="relations-empty">${current?.graph.id === 'S07' ? '当前读取模式不支持先备查询。原属性在上方保留，不画虚构连接。' : selected ? '当前关系筛选下没有登记直接连接。可改为“全部关系”，或换一个节点；不等于不存在其他联系。' : '调整关键词或筛选，选择一个实际节点继续。'}</p>`;
    $('#relations-pagination').innerHTML = pageCount > 1 ? `<span>${(relationPage - 1) * pageSize + 1}—${(relationPage - 1) * pageSize + rows.length} / 全部 ${number(current.relations.total)} 条</span><button type="button" id="previous-relations" ${relationPage === 1 ? 'disabled' : ''}>上一组</button><button type="button" id="next-relations" ${relationPage === pageCount ? 'disabled' : ''}>下一组</button>` : '';
    if ($('#previous-relations')) $('#previous-relations').onclick = () => navigate({ ...state, edgePage: relationPage - 1 });
    if ($('#next-relations')) $('#next-relations').onclick = () => navigate({ ...state, edgePage: relationPage + 1 });
  }
  function renderDataNotes(data) {
    const meta = catalog.graphs.find(g => g.id === data.graph.id);
    const readable = [];
    if (meta.family === 'external') {
      readable.push('原来源：' + meta.sourceName + '。保留原语言与固定本地快照，' + (catalog.scope?.anonymousAccess ? '五源' : '七源') + '不按同名合并。');
      if (data.graph.meta?.auxiliaryEdgeCount) readable.push(`关系计数：${number(data.graph.meta.nativeEdgeCount)} 条原生边，另保留 ${number(data.graph.meta.auxiliaryEdgeCount)} 条独立数学联系；附加联系不是先备。`);
    }
    else if (data.graph.id === 'curriculum') readable.push('课程分母：509 个，另有 2 个研究扩展；先备引用不自动生成学习路线。');
    else if (data.graph.id === 'papers') readable.push('研究样本：8 卷 210 题，525 条题目—知识用途；图中另含经验桥、卷内与跨卷联系，所以图节点总数不等于题数加知识数。');
    else if (data.graph.id === 'textbooks') readable.push('只画实际登记的书、章与页。教材版权归原权利人，公开仓库可取得不等于获得公开再分发许可。');
    else readable.push(data.graph.boundary);
    readable.push('当前节点关系用于查清已有材料，不是官方命题认证、学习诊断或学生掌握证据。');
    $('#data-notes').innerHTML = readable.map(text => `<p>${esc(text)}</p>`).join('') + `<p class="version-stamp">实际数据版本已绑定 · ${new Date().toLocaleDateString('zh-CN')} ${catalog.scope?.anonymousAccess ? '公开非商业快照' : deployed ? '私人公网快照' : '本机读取'} · <a href="graphs.html">返回全部图谱</a></p>`;
  }
  function renderError(title, message) {
    controller?.abort();
    main.innerHTML = `<section class="error-state" role="alert"><h1>${esc(title)}</h1><p>${esc(message)}</p><div class="error-actions"><a href="graphs.html">返回全部图谱</a><button id="reload-atlas" type="button">重新读取</button></div></section>`;
    $('#reload-atlas').onclick = () => location.reload(); window.ATLAS_STATUS = { ready: false, error: message };
  }
  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const structureQuery = event.target.closest('[data-structure-query]');
    if (structureQuery) {
      event.preventDefault();
      const query = JSON.parse(structureQuery.dataset.structureQuery || '{}');
      navigate({ graph: state.graph, ...query }, { scroll: true });
      return;
    }
    const target = event.target.closest('[data-select-node]');
    if (target) { event.preventDefault(); selectNode(target.dataset.selectNode); return; }
    const link = event.target.closest('a[data-graph-route]');
    if (link) { event.preventDefault(); const url = new URL(link.href); const next = Object.fromEntries(url.searchParams); navigate(next, { scroll: true }); return; }
    const overview = event.target.closest('a[href="graphs.html"]');
    if (overview && catalog) { event.preventDefault(); navigate({}, { scroll: true }); }
  });
  window.addEventListener('popstate', () => { routeWarning = ''; const oldGraph = state.graph; state = readRoute(); if (!state.graph) renderOverview(); else if (!catalog.graphs.some(g => g.id === state.graph)) renderError('这个图谱尚未登记', '请返回总览重新选择。'); else { if (oldGraph !== state.graph || !$('#browse-view')) buildBrowseShell(); else syncControls(); loadBrowse(); } });
  async function start() {
    state = readRoute();
    try {
      catalog = await getJSON(atlasAPI('catalog'));
      if (!state.graph) renderOverview();
      else if (!catalog.graphs.some(g => g.id === state.graph)) renderError('这个图谱尚未登记', '链接中的图谱名称不在当前目录里。请返回总览选择。');
      else { buildBrowseShell(); await loadBrowse(); }
    } catch (error) { renderError('图谱目录暂未就绪', error.message + ' 页面需要现有知题本机服务，不能只用静态文件打开。'); }
  }
  start();
})();

'use strict';

(() => {
  const COMMIT = '135386badef498d6c3a0c73627580250883793ae';
  const RAW = `https://raw.githubusercontent.com/bewho/China-K12-knowledge-taxonomy/${COMMIT}/_raw/tokenmap-data.json`;
  let pending = null;

  const text = value => value == null ? '' : Array.isArray(value) ? value.map(text).join('；') : String(value);
  const number = value => Number(value) || 0;
  const gradeInfo = band => {
    const value = String(band || '');
    const chinese = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 };
    let years = [];
    if (/^高[一二三]/.test(value)) years = [10 + '一二三'.indexOf(value[1])];
    else if (/^\d+$/.test(value) && Number(value) >= 1 && Number(value) <= 12) years = [Number(value)];
    else {
      let match = value.match(/^([一二三四五六七八九])年级/);
      if (match) years = [chinese[match[1]]];
      match = value.match(/^([一二三四五六七八九])至([一二三四五六七八九])年级$/);
      if (match) years = Array.from({ length: chinese[match[2]] - chinese[match[1]] + 1 }, (_, i) => chinese[match[1]] + i);
      match = value.match(/^(\d+)[–~-](\d+)$/);
      if (match) years = Array.from({ length: Number(match[2]) - Number(match[1]) + 1 }, (_, i) => Number(match[1]) + i);
    }
    const stage = !years.length ? 'unknown' : Math.max(...years) <= 6 ? '小学' : Math.max(...years) <= 9 ? '初中' : Math.max(...years) <= 12 ? '高中' : 'cross-stage';
    return { stage, years };
  };
  const structureItem = (label, field, value, extra = {}) => ({ label: text(label), field, value: text(value), ...extra });
  const virtual = (node, label, field, value, queryValue) => structureItem(label, field, value, {
    query: Object.fromEntries(Object.entries({ q: queryValue || value, stage: node.stage, subject: node.subject }).filter(([, v]) => v && v !== 'unknown'))
  });

  function makeStructure(node) {
    if (!node) return { mode: 'none', paths: [], facets: [], note: '', truncated: 0 };
    const current = structureItem(node.label, 'knowledge', node.label, { nodeId: node.id, kind: node.kind });
    const chain = node.stage !== 'unknown' ? [structureItem(node.stage, 'stage', node.stage, { query: { stage: node.stage, subject: node.subject } })] : [];
    const grade = node.originalContent.properties.grade;
    const volume = node.originalContent.properties.volume;
    const chapter = node.originalContent.properties.chapter;
    if (grade) chain.push(virtual(node, grade, 'grade', grade));
    if (volume) chain.push(virtual(node, volume, 'volume', volume));
    if (chapter) chain.push(virtual(node, chapter, 'chapter', chapter));
    chain.push(current);
    return { mode: 'metadata', paths: [chain], facets: [], truncated: 0,
      note: '原源直读：按原学科、年级册次、单元簇返回；type 0/1 与原始端点不改写。' };
  }

  function build(document) {
    const nodes = {}, edges = [];
    const tuples = document.nodes || [];
    tuples.forEach((row, index) => {
      if (!Array.isArray(row) || row.length !== 10) throw new Error('S05原节点列数改变');
      const id = 'S05:' + row[0], subject = document.subjects[row[2]]?.name || 'unknown';
      const grade = document.bands[row[3]] || 'unknown', info = gradeInfo(grade);
      const properties = { grade, volume: row[6], chapter: row[7], description: row[8], evidence: row[9] };
      nodes[id] = {
        id, label: text(row[1]), kind: 'knowledge', subject, stage: info.stage, group: info.stage,
        description: text(row[8]), boundary: '原源直读；原始端点、type与理由不改写', status: 'source_original',
        details: [
          { label: '原ID', value: row[0] }, { label: '原名称', value: text(row[1]) },
          { label: '原学科', value: subject }, { label: '原学段', value: info.stage },
          { label: '原年级', value: grade }, { label: 'volume', value: row[6] },
          { label: 'chapter', value: row[7] }, { label: 'evidence', value: row[9] },
          { label: '原十列记录', value: JSON.stringify(row) }
        ],
        originalContent: { properties },
        source: { name: 'bewho/China-K12-knowledge-taxonomy', locator: `${RAW}#/nodes/${index}`, version: 'git:' + COMMIT, role: '原源直读，不重新分发原数据' },
        links: [{ label: '原始仓库', url: 'https://github.com/bewho/China-K12-knowledge-taxonomy', available: true }]
      };
    });
    (document.edges || []).forEach((row, index) => {
      const rawSource = 'S05:' + tuples[row[0]]?.[0], rawTarget = 'S05:' + tuples[row[1]]?.[0];
      if (!nodes[rawSource] || !nodes[rawTarget]) return;
      const type = String(row[2]), prerequisite = type === '1';
      const source = prerequisite ? rawTarget : rawSource, target = prerequisite ? rawSource : rawTarget;
      edges.push({
        id: 'S05:e' + index, source, target, relation: prerequisite ? 'prerequisite' : 'related',
        label: prerequisite ? 'prerequisite' : 'related', originalSource: rawSource, originalTarget: rawTarget,
        originalRelation: type, originalLabel: type, reason: text(row[3]), status: 'unspecified',
        fromLabel: nodes[source].label, toLabel: nodes[target].label,
        sourceLocator: `${RAW}#/edges/${index}`, boundary: '原源直读；导航归一与原始记录分开'
      });
    });
    const indexes = { originalIncoming: new Map(), originalOutgoing: new Map(), incoming: new Map(), outgoing: new Map() };
    const add = (map, key, edge) => { if (!map.has(key)) map.set(key, []); map.get(key).push(edge); };
    for (const edge of edges) {
      add(indexes.originalIncoming, edge.originalTarget, edge); add(indexes.originalOutgoing, edge.originalSource, edge);
      add(indexes.incoming, edge.target, edge); add(indexes.outgoing, edge.source, edge);
    }
    return { nodes, edges, indexes };
  }

  async function loadRaw(signal) {
    if (!pending) pending = fetch(RAW, { signal, credentials: 'omit', cache: 'force-cache' }).then(response => {
      if (!response.ok) throw new Error('S05原源读取失败（' + response.status + '）');
      return response.json();
    }).catch(error => { pending = null; throw error; });
    return pending;
  }

  function browse(model, query) {
    const params = new URLSearchParams(query), values = Object.values(model.nodes);
    const relation = params.get('relation') || 'all', rawRelation = relation.startsWith('raw:') ? relation.slice(4) : '';
    const useRaw = relation === 'all' || !!rawRelation;
    const relationCounts = new Map(), originalCounts = new Map();
    for (const edge of model.edges) {
      relationCounts.set(edge.relation, (relationCounts.get(edge.relation) || 0) + 1);
      originalCounts.set(edge.originalRelation, (originalCounts.get(edge.originalRelation) || 0) + 1);
    }
    const accept = edge => relation === 'all' || (useRaw ? edge.originalRelation === rawRelation : edge.relation === relation);
    if (rawRelation && !originalCounts.has(rawRelation)) throw new Error('原始关系类型不存在');
    const q = (params.get('q') || '').toLowerCase();
    const filtered = values.filter(node => {
      const fieldsMatch = ['subject', 'stage', 'group', 'kind'].every(key => !params.get(key) || params.get(key) === node[key]);
      const haystack = JSON.stringify([node.id, node.label, node.description, node.details]).toLowerCase();
      return fieldsMatch && (!q || haystack.includes(q));
    });
    const size = Math.min(50, Math.max(1, number(params.get('size')) || 24));
    const pages = Math.ceil(filtered.length / size);
    const page = Math.min(Math.max(1, number(params.get('page')) || 1), Math.max(1, pages));
    const pageNodes = filtered.slice((page - 1) * size, page * size);
    const selected = model.nodes[params.get('node')] || pageNodes[0] || null;
    const sourceOf = edge => useRaw ? edge.originalSource : edge.source, targetOf = edge => useRaw ? edge.originalTarget : edge.target;
    const incoming = useRaw ? model.indexes.originalIncoming : model.indexes.incoming;
    const outgoing = useRaw ? model.indexes.originalOutgoing : model.indexes.outgoing;
    const distance = {}, reachedEdges = [];
    if (selected) {
      distance[selected.id] = 0;
      for (const [sign, index, endpoint] of [[-1, incoming, 'source'], [1, outgoing, 'target']]) {
        const seen = new Set([selected.id]), queue = [[selected.id, 0]];
        while (queue.length) {
          const [current, depth] = queue.shift();
          const maxDepth = Math.min(2, Math.max(1, Number(params.get('hops') || 1)));
          if (depth >= maxDepth) { continue; }
          for (const edge of index.get(current) || []) {
            if (!accept(edge)) { continue; }
            const other = endpoint === 'target' ? targetOf(edge) : sourceOf(edge);
            if (!model.nodes[other] || seen.has(other)) { continue; }
            seen.add(other); distance[other] = sign * (depth + 1); queue.push([other, depth + 1]);
          }
        }
      }
    }
    const reached = new Set(Object.keys(distance));
    const neighborhoodEdges = model.edges.filter(edge => accept(edge) && reached.has(sourceOf(edge)) && reached.has(targetOf(edge)));
    const order = [...reached].sort((a, b) => Math.abs(distance[a]) - Math.abs(distance[b]) || a.localeCompare(b));
    const shown = new Set(order.slice(0, 40));
    const direct = selected ? model.edges.filter(edge => accept(edge) && (sourceOf(edge) === selected.id || targetOf(edge) === selected.id)) : [];
    const edgeSize = Math.min(50, Math.max(1, number(params.get('edgeSize')) || 8));
    const edgePages = Math.ceil(direct.length / edgeSize), edgePage = Math.min(Math.max(1, number(params.get('edgePage')) || 1), Math.max(1, edgePages));
    const summary = node => Object.fromEntries(Object.entries(node).filter(([key]) => !['details', 'originalContent'].includes(key)));
    const countRows = (field, plural) => {
      const counts = new Map(); for (const node of values) counts.set(node[field], (counts.get(node[field]) || 0) + 1);
      return [...counts].sort().map(([value, count]) => ({ value, label: value, count }));
    };
    return {
      schemaVersion: 1,
      graph: { id: 'S05', title: 'bewho/China-K12-knowledge-taxonomy', boundary: '原源直读，不重新打包原数据', version: 'git:' + COMMIT,
        nodeCount: values.length, edgeCount: model.edges.length,
        meta: { nativeEdgeCount: model.edges.length, projectionEdgeCount: model.edges.length, projectionLoaded: true, prerequisite_supported: true, upstreamDirect: true } },
      filters: { subjects: countRows('subject'), stages: countRows('stage'), groups: countRows('group'), kinds: countRows('kind'),
        relations: [...relationCounts].sort().map(([value, count]) => ({ value, label: value, count })),
        originalRelations: [...originalCounts].sort().map(([value, count]) => ({ value, label: value, count })) },
      list: { nodes: pageNodes.map(summary), total: filtered.length, page, size, pages },
      selected, structure: makeStructure(selected),
      coverage: (() => { const out = model.indexes.originalOutgoing.get(selected?.id)?.length || 0, inc = model.indexes.originalIncoming.get(selected?.id)?.length || 0; return { originalOutgoing: out, originalIncoming: inc, originalTotal: out + inc, hasOriginalRelation: out + inc > 0 }; })(),
      neighborhood: { nodes: order.slice(0, 40).map(id => ({ ...summary(model.nodes[id]), distance: distance[id] })),
        edges: neighborhoodEdges.filter(edge => shown.has(sourceOf(edge)) && shown.has(targetOf(edge))).slice(0, 80),
        totalNodes: reached.size, totalEdges: neighborhoodEdges.length, truncated: reached.size > 40 || neighborhoodEdges.length > 80, nodeLimit: 40, edgeLimit: 80 },
      relations: { edges: direct.slice((edgePage - 1) * edgeSize, edgePage * edgeSize), total: direct.length,
        truncated: direct.length > edgeSize, page: edgePage, size: edgeSize, pages: edgePages },
      notice: '原源固定提交直读；默认展示原始rawSource/rawTarget/type。prerequisite/related仅在选择导航归一时使用。'
    };
  }

  window.AtlasUpstreamS05 = {
    async load(query, signal) { return browse(build(await loadRaw(signal)), query); },
    raw: RAW,
    commit: COMMIT
  };
})();

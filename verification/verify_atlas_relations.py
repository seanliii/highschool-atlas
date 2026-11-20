"""Fail release on any changed node ID, edge endpoint or original relation code."""
from collections import Counter
from pathlib import Path
import json
import os

from graph_browser import EXTERNAL_IDS, GraphBrowser, LOCAL_TITLES

ROOT = Path(os.environ.get('ATLAS_SOURCE_ROOT', Path(__file__).resolve().parent))
FROZEN = Path(os.environ.get('ATLAS_FROZEN_ROOT', ROOT.parent / '.release/highschool-atlas-20261120/candidate-1/private/graphs'))
OUT = Path(os.environ.get('ATLAS_RELATION_AUDIT_OUT', FROZEN.parents[2] / 'relation-audit.json'))


def compare_edges(graph_id, live, frozen):
    mismatches = []
    live_by_id = {edge['id']: edge for edge in live.edges}
    frozen_by_id = {edge['id']: edge for edge in frozen['edges']}
    if set(live_by_id) != set(frozen_by_id):
        mismatches.append({'kind': 'edgeIds', 'missing': sorted(set(live_by_id) - set(frozen_by_id))[:10],
                           'added': sorted(set(frozen_by_id) - set(live_by_id))[:10]})
    for edge_id in sorted(set(live_by_id) & set(frozen_by_id)):
        source, target = live_by_id[edge_id], frozen_by_id[edge_id]
        for key in ['source', 'target', 'relation', 'originalSource', 'originalTarget', 'originalRelation', 'originalLabel', 'reason', 'status']:
            if source.get(key) != target.get(key):
                mismatches.append({'kind': 'edgeField', 'id': edge_id, 'field': key,
                                   'expected': source.get(key), 'actual': target.get(key)})
    return mismatches


def main():
    browser = GraphBrowser(root=ROOT)
    report = {'ok': True, 'graphs': []}
    for graph_id in [*EXTERNAL_IDS, *LOCAL_TITLES]:
        live = browser.external(graph_id) if graph_id in EXTERNAL_IDS else browser.local(graph_id)
        frozen = json.loads((FROZEN / (graph_id + '.json')).read_bytes())
        live_ids, frozen_ids = set(live.nodes), {node['id'] for node in frozen['nodes']}
        mismatches = []
        if live_ids != frozen_ids:
            mismatches.append({'kind': 'nodeIds', 'missing': sorted(live_ids - frozen_ids)[:10],
                               'added': sorted(frozen_ids - live_ids)[:10]})
        mismatches.extend(compare_edges(graph_id, live, frozen))
        direction_changes = sum(edge['source'] != edge['originalSource'] or edge['target'] != edge['originalTarget']
                                for edge in live.edges)
        original_codes = Counter(edge.get('originalRelation', edge['relation']) for edge in live.edges)
        row = {'id': graph_id, 'nodes': len(live_ids), 'edges': len(live.edges),
               'originalRelations': dict(sorted(original_codes.items())),
               'navigationDirectionDiffersFromOriginal': direction_changes,
               'mismatches': mismatches[:20], 'ok': not mismatches}
        report['graphs'].append(row)
        report['ok'] &= not mismatches
        print(json.dumps(row, ensure_ascii=False), flush=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'ok': report['ok'], 'report': str(OUT)}, ensure_ascii=False))
    if not report['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

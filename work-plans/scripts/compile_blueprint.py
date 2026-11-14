"""Deterministic structure conversion. Never add professional premises or graph edges."""
from pathlib import Path
from planning_common import require, schema, validate
CONFIG = Path(__file__).resolve().parents[1] / 'config'
VOCABULARY = schema(CONFIG / 'artifact_vocabulary.json')


def validate_formats(kind, formats, role):
    allowed = VOCABULARY[role].get(kind)
    require(allowed is not None, 'unknown_artifact_kind:' + kind)
    require(isinstance(formats, list) and len(formats) == len(set(formats)), 'invalid_preferred_formats')
    require(all(f in allowed for f in formats), 'format_not_allowed_for_kind:' + kind)
    require(bool(formats) == bool(allowed), 'empty_formats_only_for_direct_text:' + kind)


def compile_blueprint(value, seed_id):
    validate(value, schema(CONFIG / 'semantic_plan.schema.json'))
    inputs, operations = value['inputs'], value['operations']
    names = [r['name'] for r in inputs + operations]
    require(len(names) == len(set(names)), 'duplicate_semantic_name')
    ids = {name: 'i' + str(i + 1) for i, name in enumerate(names)}
    operation_names = {r['name'] for r in operations}
    nodes, edges, hypotheses = [], [], []
    for row in inputs:
        validate_formats(row['kind'], row['preferred_formats'], 'inputs')
        require((row['kind'] == 'text_instruction') == (row['source'] == 'task_instruction'), 'instruction_kind_source_mismatch')
        dependency = row.get('modality_dependency')
        node = {'id': ids[row['name']], 'type': 'external_input', 'description': row['description'],
                'kind': row['kind'], 'preferred_formats': list(row['preferred_formats']),
                'supply_channel': row['source'], 'critical': row.get('critical', True),
                'modality_candidates': [], 'modality_rationale': ''}
        if dependency:
            require(row['kind'] != 'text_instruction', 'direct_text_has_no_visual_dependency')
            require(dependency['supports'] in operation_names, 'modality_supports_unknown_operation')
            modality = {'visual': 'image', 'visual_spatial': 'spatial', 'temporal_visual':'video', 'auditory':'audio'}[dependency['modality']]
            node.update(modality_candidates=[modality], modality_rationale=dependency['required_operation'])
            hypotheses.append({'node_id': node['id'], 'modality_candidate': modality,
                               'information_needed': dependency['information_needed'],
                               'modality_rationale': dependency['required_operation'],
                               'supports_node_id': ids[dependency['supports']],
                               'evidence_status': 'unretrieved', 'necessity_status': 'hypothesis'})
        nodes.append(node)
    def add_edges(requires, target):
        for reference in requires:
            require(reference in ids, 'unknown_requirement_name:' + reference)
            edges.append([ids[reference], target])
    for row in operations:
        nodes.append({'id': ids[row['name']], 'type': row['type'], 'description': row['description']})
        add_edges(row['requires'], ids[row['name']])
    output = value['deliverable']
    validate_formats(output['kind'], output['preferred_formats'], 'deliverables')
    add_edges(output['requires'], 'out1')
    return {'seed_id': seed_id, 'work_objective': value['objective'],
            'deliverables': [{'id': 'out1', 'type': output['kind'], 'description': output['description'],
                              'preferred_formats': list(output['preferred_formats'])}],
            'information_nodes': nodes, 'dependencies': edges, 'modality_hypotheses': hypotheses}

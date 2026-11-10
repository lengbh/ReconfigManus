"""Verify that SMP attachments preserve all original material-flow geometry."""

import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any


def numbers(text: str) -> list[float]:
    return [float(value) for value in re.findall(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?', text)]


def same_geometry(actual: str, expected: str):
    first, second = numbers(actual), numbers(expected)
    assert len(first) == len(second) and all(
        math.isclose(a, b, rel_tol=0, abs_tol=1e-4) for a, b in zip(first, second)
    ), f'Original graph geometry changed: {actual} != {expected}'


def check_model(dot_file: Path, source: dict[str, Any], reference: dict[str, Any],
                neato: str, below: frozenset[int] = frozenset(), closer: frozenset[int] = frozenset()):
    rendered = json.loads(subprocess.check_output([neato, '-n2', '-Tjson', str(dot_file)], text=True))
    nodes = {item['_gvid']: item for item in rendered['objects'] if 'nodes' not in item}
    states = {(int(node['smp_station']), node['smp_state']) for node in nodes.values() if node.get('smp_state')}
    expected_states = set()
    expected_transitions = {}
    for vertex in source['vertices']:
        station = vertex['id']
        model = vertex.get('smp') or {
            'states': ['idle', 'running'],
            'transition_probabilities': {'idle': {'running': 1}, 'running': {'idle': 1}},
            'holding_time_distributions': {'idle': {'running': None},
                                           'running': {'idle': vertex['service_time_distribution']}},
        }
        expected_states.update((station, state) for state in model['states'])
        for before, row in model['transition_probabilities'].items():
            for after, probability in row.items():
                if probability > 0:
                    expected_transitions[(station, before, after)] = (
                        probability, model['holding_time_distributions'][before][after],
                    )
    assert states == expected_states, 'Rendered state set differs from the input model'
    machines = {int(node['smp_machine_id']): node for node in nodes.values() if node.get('smp_machine_id')}
    assert set(machines) == {vertex['id'] for vertex in source['vertices']}
    reference_nodes = {node['name']: node for node in reference['objects']}
    station_by_name = {str(index): vertex['id'] for index, vertex in enumerate(source['vertices'])}
    reference_names = {node['_gvid']: node['name'] for node in reference['objects']}
    reference_arcs = {
        (station_by_name[reference_names[edge['tail']]], station_by_name[reference_names[edge['head']]]): edge
        for edge in reference['edges']
    }
    for name, station in station_by_name.items():
        for field in ('pos', 'width', 'height'):
            same_geometry(machines[station][field], reference_nodes[name][field])
        assert machines[station]['label'] == reference_nodes[name]['label']

    associations = set()
    observed = {}
    flow_arcs = {}
    for edge in rendered['edges']:
        tail, head = nodes[edge['tail']], nodes[edge['head']]
        if edge.get('smp_association') == 'true':
            station = int(tail['smp_machine_id'])
            associations.add((station, int(head['smp_station'])))
            assert edge['dir'] == 'none' and edge['style'] == 'dotted'
            assert edge['smp_placement'] == ('below' if station in below else 'right')
            if station in closer:
                machine_x = float(tail['pos'].split(',')[0])
                block_edge = machine_x + 36 * float(tail['width'])
                original_end = float(reference['bb'].split(',')[2]) + 42 - 0.38 * 36
                path = numbers(edge['pos'])
                actual_length = path[-2] - path[0]
                assert math.isclose(actual_length, (original_end - block_edge) / 2, abs_tol=0.01)
        elif edge.get('smp_probability'):
            key = (int(tail['smp_station']), tail['smp_state'], head['smp_state'])
            observed[key] = (float(edge['smp_probability']), json.loads(edge['smp_holding']))
            assert not edge.get('label')
        else:
            flow_arcs[(int(tail['smp_machine_id']), int(head['smp_machine_id']))] = edge
    assert set(flow_arcs) == {(arc['tail'], arc['head']) for arc in source['arcs']}
    for key, edge in flow_arcs.items():
        for field in ('pos', 'lp'):
            same_geometry(edge[field], reference_arcs[key][field])
    assert associations == {(vertex['id'], vertex['id']) for vertex in source['vertices']}
    assert observed == expected_transitions, 'Rendered P or conditional F differs from the input model'

    right_bound = float(reference['bb'].split(',')[2])
    right_arc_bound = max(max(numbers(edge['pos'])[::2]) for edge in reference['edges'])
    state_rows = {}
    for node in nodes.values():
        if not node.get('smp_state'):
            continue
        station = int(node['smp_station'])
        machine = machines[station]
        x, y = map(float, node['pos'].split(','))
        machine_x, machine_y = map(float, machine['pos'].split(','))
        state_rows.setdefault(station, []).append((x, y))
        if station in below:
            assert y < machine_y - 36 * float(machine['height']), 'SMP is not below its machine'
        else:
            outside = right_arc_bound if station in closer else right_bound
            assert x - 36 * float(node['width']) > outside, 'SMP is inside the original graph arcs'
        assert node['label'] == node['smp_state'][0].upper()
    for station, positions in state_rows.items():
        assert len({y for _, y in positions}) == 1
        if station in below:
            machine_x = float(machines[station]['pos'].split(',')[0])
            # Graphviz rounds its JSON coordinates to a few decimal places.
            assert math.isclose(sum(x for x, _ in positions) / len(positions), machine_x, abs_tol=0.01)
    # The case-study's original S1-S5 column must remain exactly vertical.
    assert len({machines[station]['pos'].split(',')[0] for station in range(1, 6)}) == 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('renderer', type=Path)
    parser.add_argument('graph', type=Path)
    parser.add_argument('dot')
    parser.add_argument('neato')
    args = parser.parse_args()
    source = json.loads(args.graph.read_text())
    with tempfile.TemporaryDirectory(prefix="GraphRender's SMP test ") as directory:
        output = Path(directory)
        fixture = output / "system's graph.json"
        fixture.write_text(json.dumps(source))
        result = subprocess.run([str(args.renderer), str(fixture), 'dot'],
                                cwd=output, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        reference = json.loads(subprocess.check_output(
            [args.dot, '-Tjson', str(output / "system's graph.dot")], text=True,
        ))
        for below in (frozenset(), frozenset({6, 7})):
            arguments = ['--smp-below=6,7'] if below else []
            result = subprocess.run([str(args.renderer), str(fixture), 'pdf', '--smp', *arguments, '-k'],
                                    cwd=output, capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
            assert (output / "system's graph_states.pdf").read_bytes().startswith(b'%PDF-')
            check_model(output / "system's graph_states.dot", source, reference, args.neato, below)

        result = subprocess.run([str(args.renderer), str(fixture), 'pdf', '--smp', '--smp-below=6,7',
                                 '--smp-closer=1,2,3,4,5', '-k'],
                                cwd=output, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        check_model(output / "system's graph_states.dot", source, reference, args.neato,
                    frozenset({6, 7}), frozenset({1, 2, 3, 4, 5}))

        for vertex in source['vertices']:
            vertex['service_time_distribution'] = vertex.pop('smp')['holding_time_distributions']['running']['idle']
        fixture.write_text(json.dumps(source))
        result = subprocess.run([str(args.renderer), str(fixture), 'dot', '--smp'],
                                cwd=output, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        check_model(output / "system's graph_states.dot", source, reference, args.neato)

        result = subprocess.run([str(args.renderer), str(fixture), 'png', '-s', '-k'],
                                cwd=output, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert (output / "system's graph.png").read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        flow = json.loads(subprocess.check_output([args.dot, '-Tjson', str(output / "system's graph.dot")], text=True))
        assert len(flow['objects']) == len(source['vertices']) and len(flow['edges']) == len(source['arcs'])
        result = subprocess.run([str(args.renderer), str(fixture), 'pdf', '--smp', '-s'],
                                cwd=output, capture_output=True, text=True)
        assert result.returncode != 0 and 'Choose either' in result.stderr
    print('Original node positions, arc curves, label positions and all SMP attachments verified.')


if __name__ == '__main__':
    main()

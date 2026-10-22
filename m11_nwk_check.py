# -*- coding: utf-8 -*-
"""MIKE 11 pipe check; one row per selected Model=m11 pipe."""
import io
import os
import re

from crosscheck_common import number, text, normalized_field, field_map, selected_rows, full_ids, check, result, write_csv, summary, issue_note

M11_ALIASES = {
    'id': ('branch',), 'model': ('model',), 'inflow': ('z_inflow',),
    'outflow': ('z_outflow',), 'diameter': ('dia_mm', 'diamm'),
    'width': ('width_mm', 'widthmm'), 'height': ('height_mm', 'heightmm'),
    'length': ('l_m', 'lm', 'length_m', 'length', 'len_m'),
    'chainage': ('chainage', 'chainage_m', 'chain_m'),
}
M11_LABELS = {'inflow': 'Inflow', 'outflow': 'Outflow', 'diameter': 'Diameter',
          'width': 'Width', 'height': 'Height', 'length': 'Length', 'chainage': 'Chainage'}


def m11_line(block, key):
    match = re.search(r'^\s*' + key + r'\s*=\s*(.*?)\s*$', block, re.I | re.M)
    return match.group(1).strip() if match else None


def m11_numbers(value):
    return [number(token.strip()) for token in value.split(',')] if value else []


def m11_read_network(path):
    with io.open(path, encoding='latin-1') as stream:
        content = stream.read()
    chains = {}
    for block in re.findall(r'\[branch\](.*?)EndSect\s*//\s*branch', content, re.I | re.S):
        match = re.match(r"'([^']+)'\s*,\s*'[^']*'\s*,\s*([^,]+),\s*([^,]+)", m11_line(block, 'definitions') or '')
        if match:
            identity = match.group(1).strip()
            if identity in chains:
                raise ValueError('Duplicate MIKE 11 Branch: ' + identity)
            chains[identity] = (number(match.group(2)), number(match.group(3)))
    model = {}
    for block in re.findall(r'\[culvert_data\](.*?)EndSect\s*//\s*culvert_data', content, re.I | re.S):
        match = re.match(r"'([^']+)'\s*,\s*([^,]+)", m11_line(block, 'Location') or '')
        if not match:
            raise ValueError('Could not read a MIKE 11 culvert Location.')
        identity = match.group(1).strip()
        if identity in model:
            raise ValueError('Multiple culverts on Branch ' + identity + '; matching requires an extra ID.')
        attributes = m11_numbers(m11_line(block, 'Attributes'))
        if len(attributes) < 3:
            raise ValueError('Missing culvert attributes for ' + identity)
        record = dict(inflow=attributes[0], outflow=attributes[1], length=attributes[2],
                      chainage=number(match.group(2)), diameter=None, width=None, height=None,
                      na=set(), shape='UNKNOWN')
        geometry = re.search(r'\[Geometry\](.*?)EndSect\s*//\s*Geometry', block, re.I | re.S)
        if geometry:
            geometry = geometry.group(1)
            shape = m11_line(geometry, 'Type')
            record['shape'] = {'0': 'RECTANGULAR', '1': 'CIRCULAR', '3': 'IRREGULAR'}.get(shape, 'UNKNOWN')
            if shape == '1':
                record['diameter'] = number(m11_line(geometry, 'Cicular_Diameter'))
                record['na'].update(('width', 'height'))
            elif shape == '0':
                pair = m11_numbers(m11_line(geometry, 'Rectangular'))
                if len(pair) >= 2:
                    record['width'], record['height'] = pair[:2]
                record['na'].add('diameter')
            elif shape == '3':
                section = re.search(r'\[Irregular\](.*?)EndSect\s*//\s*Irregular', geometry, re.I | re.S)
                points = []
                if section:
                    for value in re.findall(r'^\s*Data\s*=\s*(.*?)\s*$', section.group(1), re.I | re.M):
                        pair = m11_numbers(value)
                        if len(pair) >= 2 and all(v is not None and abs(v) < 1e10 for v in pair[:2]):
                            points.append(pair[:2])
                if points:
                    record['width'] = max(point[1] for point in points)
                    record['height'] = max(point[0] for point in points) - min(point[0] for point in points)
                record['na'].add('diameter')
        record['chain_start'], record['chain_end'] = chains.get(identity, (None, None))
        model[identity] = record
    if not model:
        raise ValueError('No culverts found in the MIKE 11 network.')
    return model


def m11_compare(records, mapping, model):
    attributes = [key for key in ('inflow', 'outflow', 'diameter', 'width', 'height', 'length', 'chainage')
                  if key in mapping]
    headers = ['Model', 'Branch', 'Branch_Check']
    for attribute in attributes:
        shp_unit = 'mm' if attribute in ('diameter', 'width', 'height') else 'm'
        headers.extend([M11_LABELS[attribute] + '_SHP_' + shp_unit,
                        M11_LABELS[attribute] + '_M11_m', M11_LABELS[attribute] + '_Check'])
    headers.extend(['M11_Shape', 'M11_Culvert_Chainage_m', 'M11_Branch_Start_m', 'M11_Branch_End_m',
                    'SHP_Length_Field', 'Result', 'Notes'])
    rows, seen = [], set()
    for pipe in sorted(records, key=lambda record: text(record.get('id') or '')):
        identity = text(pipe.get('id') or '').strip()
        if not identity or identity in seen:
            raise ValueError('Blank or duplicate selected MIKE 11 Branch: ' + identity)
        seen.add(identity)
        reference = model.get(identity)
        checks = ['MATCH' if reference is not None else 'MISSING_IN_MODEL']
        row = ['m11', identity, checks[0]]
        notes = [] if reference is not None else ['Branch not found in MIKE 11 network.']
        for attribute in attributes:
            value = number(pipe.get(attribute))
            model_value = reference.get(attribute) if reference else None
            if reference is None:
                status = 'MISSING_IN_MODEL'
            elif attribute in reference['na']:
                status = 'N/A'
            else:
                factor = 0.001 if attribute in ('diameter', 'width', 'height') else 1.0
                status = check(value, model_value, factor)
            checks.append(status)
            row.extend([value, model_value, status])
            if reference is not None:
                unit = 'mm' if attribute in ('diameter', 'width', 'height') else 'm'
                note = issue_note(M11_LABELS[attribute], status, value, model_value, unit)
                if note:
                    notes.append(note)
        row.extend([reference['shape'] if reference else '',
                    reference['chainage'] if reference else None,
                    reference['chain_start'] if reference else None,
                    reference['chain_end'] if reference else None,
                    mapping.get('length', ''), result(checks), ' '.join(notes)])
        rows.append(row)
    return headers, rows


def run_m11(arcpy, layer, network, output):
    mapping = field_map(arcpy, layer, M11_ALIASES, ('id', 'model', 'inflow', 'outflow', 'diameter'))
    selected = selected_rows(arcpy, layer, mapping)
    pipes = [row for row in selected if text(row.get('model') or '').strip().lower() == 'm11']
    if not pipes:
        raise ValueError('No selected pipes have Model=m11.')
    model = m11_read_network(network)
    headers, rows = m11_compare(pipes, mapping, model)
    headers.extend(['Model_File_Type', 'Model_File'])
    for row in rows:
        row.extend([os.path.splitext(network)[1].lower(), os.path.basename(network)])
    write_csv(output, headers, rows)
    arcpy.AddMessage('{} other-model selected pipes skipped; {} m11 pipes checked.'.format(len(selected)-len(pipes),len(pipes)))
    summary(arcpy, rows, model, full_ids(arcpy, layer, mapping['id']), 'pipe')
    arcpy.AddMessage('Saved MIKE 11 CSV: ' + output)



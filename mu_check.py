# -*- coding: utf-8 -*-
"""Separate MIKE+ pipe and node comparisons, one CSV row per selected feature."""
import io
import os
import re
import sqlite3

from crosscheck_common import number, text, normalized_field, field_map, selected_rows, full_ids, check, result, write_csv, summary, issue_note

NODE_ALIASES = {'id': ('node_id', 'nodeid', 'muid'),
                'ground': ('gl', 'ground_l', 'groundlevel', 'groundleve', 'groundlev', 'ground_lvl'),
                'invert': ('invert_l', 'invertl', 'invertlevel', 'invertleve', 'bottom_level', 'bottomlevel', 'bottom_l'),
                'diameter': ('dia_mm', 'diamm', 'diam_mm', 'diameter_mm', 'diameter', 'diam')}
PIPE_ALIASES = {'id': ('branch',), 'model': ('model',), 'inflow': ('z_inflow',),
                'outflow': ('z_outflow',), 'diameter': ('dia_mm', 'diamm')}
NODE_HEADERS = ['Model', 'Node_ID', 'Node_Check',
                'GL_SHP_m', 'GL_SQLite_m', 'GL_Check',
                'Invert_L_SHP_m', 'Invert_L_SQLite_m', 'Invert_L_Check',
                'Diameter_SHP_mm', 'Diameter_SQLite_m', 'Diameter_Check',
                'Result', 'Notes']
PIPE_HEADERS = ['Model', 'Branch', 'Branch_Check',
                'Inflow_SHP_m', 'Upstream_SQLite_m', 'Inflow_Check',
                'Outflow_SHP_m', 'Downstream_SQLite_m', 'Outflow_Check',
                'Diameter_SHP_mm', 'Diameter_SQLite_m', 'Diameter_Check',
                'Result', 'Notes']


def mu_database_path(path):
    if not path.lower().endswith('.mupp'):
        return path
    with io.open(path, encoding='latin-1') as stream:
        content = stream.read()
    match = re.search(r'^\s*DBFilePath\s*=\s*\|([^|]+)\|', content, re.I | re.M)
    if not match:
        raise ValueError('No local SQLite DBFilePath in .mupp; choose .sqlite directly.')
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(path)),
                                        match.group(1).replace('\\', os.sep)))


def mu_read_table(path, feature):
    path = mu_database_path(path)
    if not os.path.isfile(path):
        raise ValueError('Database not found: ' + path + '. Choose .sqlite directly if filenames were changed.')
    table = 'msm_Node' if feature == 'node' else 'msm_Link'
    names = ('muid', 'groundlevel', 'invertlevel', 'diameter') if feature == 'node' else ('muid', 'uplevel', 'dwlevel', 'diameter')
    keys = ('ground', 'invert', 'diameter') if feature == 'node' else ('inflow', 'outflow', 'diameter')
    connection = sqlite3.connect(path)
    try:
        connection.execute('PRAGMA query_only=ON')
        columns = {row[1].lower() for row in connection.execute('PRAGMA table_info(' + table + ')')}
        if not set(names).issubset(columns):
            raise ValueError('Database has no supported ' + table + ' fields.')
        if 'altid' in columns and connection.execute('SELECT count(*) FROM ' + table + ' WHERE altid<>0').fetchone()[0]:
            raise ValueError(table + ' alternatives found; export the intended scenario first.')
        model = {}
        for row in connection.execute('SELECT ' + ','.join(names) + ' FROM ' + table):
            identity = text(row[0]).strip()
            if identity in model:
                raise ValueError('Duplicate SQLite ID: ' + identity)
            model[identity] = dict(zip(keys, [number(value) for value in row[1:]]))
        return model
    finally:
        connection.close()


def mu_read_nodes(path):
    return mu_read_table(path, 'node')


def mu_read_pipes(path):
    return mu_read_table(path, 'pipe')


def mu_compare(records, model, feature='node', diameter_factor=0.001, diameter_unit='mm'):
    rows, seen = [], set()
    attributes = ('ground', 'invert', 'diameter') if feature == 'node' else ('inflow', 'outflow', 'diameter')
    labels = {'ground': 'Ground level (GL)', 'invert': 'Bottom level (Invert_L)',
              'inflow': 'Upstream level (Z_Inflow)', 'outflow': 'Downstream level (Z_Outflow)', 'diameter': 'Diameter'}
    for record in sorted(records, key=lambda item: text(item.get('id') or '')):
        identity = text(record.get('id') or '').strip()
        if not identity or identity in seen:
            raise ValueError('Blank or duplicate selected ' + feature + ' ID: ' + identity)
        seen.add(identity)
        reference = model.get(identity)
        checks = ['MATCH' if reference is not None else 'MISSING_IN_MODEL']
        row = ['mu', identity, checks[0]]
        notes = [] if reference is not None else [feature.title() + ' ID not found in SQLite.']
        for attribute in attributes:
            value = number(record.get(attribute))
            model_value = reference.get(attribute) if reference else None
            status = ('MISSING_IN_MODEL' if reference is None else
                      check(value, model_value, diameter_factor if attribute == 'diameter' else 1))
            row.extend([value, model_value, status])
            checks.append(status)
            if reference is not None:
                note = issue_note(labels[attribute], status, value, model_value, diameter_unit if attribute == 'diameter' else 'm')
                if note:
                    notes.append(note)
        row.extend([result(checks), ' '.join(notes)])
        rows.append(row)
    return rows


def run_mu(arcpy, pipe_layer, node_layer, database, pipe_output, node_output,
           node_fields=None, node_diameter_unit='mm'):
    if not pipe_layer and not node_layer:
        raise ValueError('Choose the selected MU pipe layer, selected MU node layer, or both.')
    if pipe_layer and not pipe_output:
        raise ValueError('Choose an output pipe CSV.')
    if node_layer and not node_output:
        raise ValueError('Choose an output node CSV.')
    if node_layer and node_diameter_unit not in ('mm', 'm'):
        raise ValueError('Choose whether the node shapefile diameter is in millimetres or metres.')
    if pipe_layer and node_layer and os.path.normcase(os.path.abspath(pipe_output)) == os.path.normcase(os.path.abspath(node_output)):
        raise ValueError('Pipe and node CSV outputs must have different filenames.')
    jobs = []
    if pipe_layer:
        mapping = field_map(arcpy, pipe_layer, PIPE_ALIASES, ('id', 'model', 'inflow', 'outflow', 'diameter'))
        selected = selected_rows(arcpy, pipe_layer, mapping)
        pipes = [row for row in selected if text(row.get('model') or '').strip().lower() == 'mu']
        if not pipes:
            raise ValueError('No selected pipes have Model=mu.')
        model = mu_read_pipes(database)
        jobs.append((pipe_layer, mapping, PIPE_HEADERS, mu_compare(pipes, model, 'pipe'), model, pipe_output, 'pipe'))
        arcpy.AddMessage('{} other-model selected pipes skipped; {} mu pipes checked.'.format(len(selected)-len(pipes), len(pipes)))
    if node_layer:
        mapping = field_map(arcpy, node_layer, NODE_ALIASES, ('id', 'ground', 'invert', 'diameter'), node_fields)
        arcpy.AddMessage('Node fields: ID={}; GL={}; bottom={}; diameter={} ({}).'.format(
            mapping['id'], mapping['ground'], mapping['invert'], mapping['diameter'], node_diameter_unit))
        nodes = selected_rows(arcpy, node_layer, mapping)
        model = mu_read_nodes(database)
        node_headers = list(NODE_HEADERS)
        if node_diameter_unit == 'm':
            node_headers[node_headers.index('Diameter_SHP_mm')] = 'Diameter_SHP_m'
        factor = 0.001 if node_diameter_unit == 'mm' else 1.0
        jobs.append((node_layer, mapping, node_headers,
                     mu_compare(nodes, model, 'node', factor, node_diameter_unit), model, node_output, 'node'))
    for layer, mapping, base_headers, rows, model, output, feature in jobs:
        headers = base_headers + ['Model_File_Type', 'Model_File']
        for row in rows:
            row.extend([os.path.splitext(database)[1].lower(), os.path.basename(database)])
        write_csv(output, headers, rows)
        summary(arcpy, rows, model, full_ids(arcpy, layer, mapping['id']), feature)
        arcpy.AddMessage('Saved MIKE+ ' + feature + ' CSV: ' + output)



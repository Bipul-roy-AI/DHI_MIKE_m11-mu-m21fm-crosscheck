# -*- coding: utf-8 -*-
"""Compare selected ArcMap pipe geometry/inverts to MIKE 21 FM culverts.
All geometry numbers in shapefile fields are presumed millimetres.
"""
from __future__ import print_function
import csv
import io
import os
import re
import sys

TOLERANCE_METRES = 0.001
HEADERS = (
    'Branch',
    'M21FM Inflow (m)', 'Pipe Inflow (m)', 'Inflow Check',
    'M21FM Outflow (m)', 'Pipe Outflow (m)', 'Outflow Check',
    'M21FM Geometry Type',
    'M21FM Diameter (m)', 'Pipe Diameter (mm)', 'Diameter Check',
    'M21FM Width (m)', 'Pipe Width (mm)', 'Width Check',
    'M21FM Height (m)', 'Pipe Height (mm)', 'Height Check',
)
STATUS_INDICES = (3, 6, 10, 13, 16)


def _line(block, name):
    hit = re.search(r'^\s*' + re.escape(name) + r'\s*=\s*(.*?)\s*$', block, re.I | re.M)
    return hit.group(1).strip() if hit else None


def _first_numeric(block, keys):
    for key in keys:
        found = _line(block, key)
        if found is not None:
            return _numeric(found)
    return None


def _numeric(value):
    if value is None or str(value).strip() == '':
        return None
    return float(value)


def read_m21fm(path):
    with io.open(path, 'r', encoding='latin-1') as source:
        content = source.read()
    blocks = re.findall(r'\[culvert_data\](.*?)EndSect\s*//\s*culvert_data', content, re.I | re.S)
    if not blocks:
        raise ValueError('No [culvert_data] entries found in the model file.')
    model = {}
    for position, block in enumerate(blocks, 1):
        location = _line(block, 'Location')
        if location is None:
            raise ValueError('Model culvert {} has no Location.'.format(position))
        found = re.match(r"\s*'[^']*'\s*,\s*[^,]+\s*,\s*'([^']+)'", location)
        if not found:
            raise ValueError('Cannot read Branch from culvert {} Location: {}'.format(position, location))
        branch = found.group(1).strip()
        if branch in model:
            raise ValueError('Duplicate model Branch: ' + branch)
        values = [v.strip() for v in (_line(block, 'Attributes') or '').split(',')]
        if len(values) < 2 or not values[0] or not values[1]:
            raise ValueError('Missing invert levels for model Branch ' + branch)
        geometry = re.search(r'\[Geometry\](.*?)EndSect\s*//\s*Geometry', block, re.I | re.S)
        geo = geometry.group(1) if geometry else ''
        # Names vary by MIKE file version. Do not assert model Type=2 without readable dimensions.
        dia = _first_numeric(geo, ('Cicular_Diameter', 'Circular_Diameter'))
        width = _first_numeric(geo, ('Rectangular_Width', 'Rectangle_Width', 'Rectangular_Width_m', 'Rect_Width'))
        height = _first_numeric(geo, ('Rectangular_Height', 'Rectangle_Height', 'Rectangular_Height_m', 'Rect_Height'))
        raw_type = (_line(geo, 'Type') or '').strip()
        if raw_type == '1' and dia is not None:
            kind = 'CIRCULAR'
        elif width is not None and height is not None and raw_type != '1':
            kind = 'RECTANGULAR'
        else:
            kind = 'UNSUPPORTED_GEOMETRY'
        model[branch] = (_numeric(values[0]), _numeric(values[1]), kind, dia, width, height, raw_type)
    return model


def selected_pipes(arcpy, layer, dia_field, width_field, height_field):
    selection = getattr(arcpy.Describe(layer), 'FIDSet', '')
    if not selection or not str(selection).strip():
        raise ValueError('Select pipes in the ArcMap layer first. Browsing directly to a shapefile does not preserve selection.')
    actual = {f.name.lower(): f.name for f in arcpy.ListFields(layer)}
    requested = ['branch', 'z_inflow', 'z_outflow', dia_field, width_field, height_field]
    missing = [field for field in requested if not field or field.lower() not in actual]
    if missing:
        raise ValueError('Pipe layer is missing fields: ' + ', '.join(str(x) for x in missing))
    columns = [actual[f.lower()] for f in requested]
    pipes = {}
    with arcpy.da.SearchCursor(layer, columns) as cursor:
        for branch, inflow, outflow, diameter, width, height in cursor:
            branch = str(branch).strip() if branch is not None else ''
            if not branch:
                raise ValueError('Selected pipe has a blank Branch.')
            if branch in pipes:
                raise ValueError('Duplicate selected Branch: ' + branch)
            pipes[branch] = (_numeric(inflow), _numeric(outflow), _numeric(diameter),
                             _numeric(width), _numeric(height))
    if not pipes:
        raise ValueError('There are no selected pipes to compare.')
    return pipes


def _display(value, decimals=4):
    return ('{:0.' + str(decimals) + 'f}').format(value) if value is not None else ''


def _check(pipe_value, model_value):
    if pipe_value is None or model_value is None:
        return 'MISSING_VALUE'
    return 'MATCH' if abs(pipe_value - model_value) <= TOLERANCE_METRES else 'MISMATCH'


def _mm_to_m(value):
    return value / 1000.0 if value is not None else None


def compare(pipes, model):
    rows = []
    for branch in sorted(pipes):
        pi, po, pd, pw, ph = pipes[branch]
        if branch not in model:
            rows.append((branch, '', _display(pi), 'MISSING_IN_M21FM',
                         '', _display(po), 'MISSING_IN_M21FM', 'MISSING_IN_M21FM',
                         '', _display(pd, 1), 'MISSING_IN_M21FM',
                         '', _display(pw, 1), 'MISSING_IN_M21FM',
                         '', _display(ph, 1), 'MISSING_IN_M21FM'))
            continue
        mi, mo, kind, md, mw, mh, raw_type = model[branch]
        if kind == 'CIRCULAR':
            diameter_check, width_check, height_check = _check(_mm_to_m(pd), md), 'NOT_APPLICABLE', 'NOT_APPLICABLE'
        elif kind == 'RECTANGULAR':
            diameter_check, width_check, height_check = 'NOT_APPLICABLE', _check(_mm_to_m(pw), mw), _check(_mm_to_m(ph), mh)
        else:
            diameter_check = width_check = height_check = 'UNSUPPORTED_GEOMETRY'
        rows.append((branch, _display(mi), _display(pi), _check(pi, mi),
                     _display(mo), _display(po), _check(po, mo), kind,
                     _display(md), _display(pd, 1), diameter_check,
                     _display(mw), _display(pw, 1), width_check,
                     _display(mh), _display(ph, 1), height_check))
    return rows


def write_report(path, rows):
    if not path.lower().endswith('.csv'):
        raise ValueError('Output file must end in .csv')
    folder = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(folder):
        raise ValueError('CSV output folder does not exist: ' + folder)
    if sys.version_info[0] < 3:
        stream = open(path, 'wb')
        def encode_row(row):
            return [v.encode('utf-8') if isinstance(v, unicode) else v for v in row]
    else:
        stream = io.open(path, 'w', encoding='utf-8-sig', newline='')
        def encode_row(row):
            return row
    try:
        writer = csv.writer(stream)
        writer.writerow(encode_row(HEADERS))
        for row in rows:
            writer.writerow(encode_row(row))
    finally:
        stream.close()


def run(arcpy, layer, model_path, output_path, dia_field, width_field, height_field):
    pipes = selected_pipes(arcpy, layer, dia_field, width_field, height_field)
    model = read_m21fm(model_path)
    rows = compare(pipes, model)
    write_report(output_path, rows)
    mismatched = sum(any(row[i] == 'MISMATCH' for i in STATUS_INDICES) for row in rows)
    unsupported = sum(row[7] == 'UNSUPPORTED_GEOMETRY' for row in rows)
    arcpy.AddMessage('Checked {} selected pipes; {} with mismatches, {} unsupported geometries.'.format(len(rows), mismatched, unsupported))
    arcpy.AddMessage('CSV saved: ' + output_path)
    if unsupported:
        arcpy.AddWarning('Some model geometry keys could not be parsed. Check [Geometry] blocks and adjust field names in read_m21fm.')

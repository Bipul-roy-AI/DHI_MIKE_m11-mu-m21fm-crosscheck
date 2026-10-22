# -*- coding: utf-8 -*-
"""Small CSV and ArcMap helpers for Python 2.7/3."""
import csv
import io
import math
import os
import sys

try:
    text = unicode
except NameError:
    text = str


def number(value):
    if value is None or text(value).strip() == '':
        return None
    result = float(value)
    return None if math.isnan(result) or math.isinf(result) else result


def normalized_field(value):
    return ''.join(character for character in text(value).lower() if character.isalnum())


def field_map(arcpy, layer, aliases, required, overrides=None):
    fields = arcpy.ListFields(layer)
    actual = {field.name.lower(): field.name for field in fields}
    mapping = {}
    overrides = overrides or {}
    for key, names in aliases.items():
        explicit = overrides.get(key)
        if explicit:
            if text(explicit).lower() not in actual:
                raise ValueError('Selected field not found: ' + text(explicit))
            mapping[key] = actual[text(explicit).lower()]
            continue
        match = next((actual[name] for name in names if name in actual), None)
        if not match:
            accepted = {normalized_field(name) for name in names}
            matches = [field.name for field in fields if normalized_field(field.name) in accepted
                       or normalized_field(getattr(field, 'aliasName', field.name)) in accepted]
            match = matches[0] if len(matches) == 1 else None
        if match:
            mapping[key] = match
    missing = [key for key in required if key not in mapping]
    if missing:
        raise ValueError('Unmapped shapefile fields: {}. Available fields: {}. '
                         'Map the corresponding fields or choose the expected input layer.'.format(
                             ', '.join(missing), ', '.join(field.name for field in fields)))
    return mapping


def selected_rows(arcpy, layer, mapping):
    if not getattr(arcpy.Describe(layer), 'FIDSet', ''):
        raise ValueError('Select features in the map first, then choose that map layer.')
    keys = sorted(mapping)
    records = []
    with arcpy.da.SearchCursor(layer, [mapping[key] for key in keys]) as cursor:
        for values in cursor:
            records.append(dict(zip(keys, values)))
    if not records:
        raise ValueError('No selected features to check.')
    return records


def full_ids(arcpy, layer, field):
    ids = set()
    with arcpy.da.SearchCursor(arcpy.Describe(layer).catalogPath, [field]) as cursor:
        for row in cursor:
            if row[0] is not None:
                ids.add(text(row[0]).strip())
    return ids


def check(shp_value, model_value, factor=1.0):
    shp_value, model_value = number(shp_value), number(model_value)
    if shp_value is None:
        return 'MISSING_SHP_VALUE'
    if model_value is None:
        return 'MISSING_MODEL_VALUE'
    return 'MATCH' if abs(shp_value * factor - model_value) <= 0.001 + 1e-9 else 'MISMATCH'


def result(checks):
    if 'MISSING_IN_MODEL' in checks:
        return 'MISSING_IN_MODEL'
    if 'MISMATCH' in checks:
        return 'MISMATCH'
    if any(value.startswith('MISSING_') for value in checks):
        return 'REVIEW_MISSING_VALUE'
    return 'MATCH'


def issue_note(label, status, shp_value=None, model_value=None, shp_unit='', model_unit='m'):
    if status in ('MATCH', 'N/A'):
        return ''
    if status == 'MISMATCH':
        return '{} mismatch (SHP={} {}; model={} {}).'.format(
            label, shp_value, shp_unit, model_value, model_unit)
    if status == 'MISSING_MODEL_VALUE':
        return label + ' missing in model.'
    if status == 'MISSING_SHP_VALUE':
        return label + ' missing in shapefile.'
    if status == 'MISSING_IN_MODEL':
        return 'ID not found in model.'
    return label + ': ' + status + '.'


def write_csv(path, headers, rows):
    if not path.lower().endswith('.csv'):
        raise ValueError('Output must end in .csv.')
    if not os.path.isdir(os.path.dirname(os.path.abspath(path))):
        raise ValueError('The output folder does not exist.')
    handle = open(path, 'wb') if sys.version_info[0] < 3 else io.open(path, 'w', encoding='utf-8-sig', newline='')
    try:
        writer = csv.writer(handle)
        for row in [headers] + rows:
            values = []
            for value in row:
                if value is None:
                    value = ''
                if isinstance(value, float):
                    value = ('%.6f' % value).rstrip('0').rstrip('.')
                if sys.version_info[0] < 3 and isinstance(value, text):
                    value = value.encode('utf-8')
                values.append(value)
            writer.writerow(values)
    finally:
        handle.close()


def summary(arcpy, rows, model, source_ids, feature):
    missing = sorted(set(model) - source_ids)
    if missing:
        arcpy.AddWarning('{} model {} IDs absent from the full source shapefile: {}'.format(
            len(missing), feature, ', '.join(missing)))
    arcpy.AddMessage('{} CSV rows, one per checked {}. No extra model-only rows are added.'.format(len(rows), feature))



import re

def project_output_path(arcpy, layer):
    """Return an existing project's Temp CSV path, or None for manual choice.

    Accept a numbered SFRM project directory (002_SFRM_..., 004_SFRM_...)
    anywhere above the shapefile. Do not create missing directories.
    """
    path = arcpy.Describe(layer).catalogPath
    if not path:
        return None
    name = os.path.splitext(os.path.basename(path))[0]
    folder = os.path.dirname(path)
    while folder and os.path.dirname(folder) != folder:
        if re.match(r'^\d+_SFRM_.+', os.path.basename(folder), re.I):
            # Preserve spelling of an existing Temp directory.
            for entry in os.listdir(folder):
                if entry.lower() == 'temp' and os.path.isdir(os.path.join(folder, entry)):
                    return os.path.join(folder, entry, name + '_comparison.csv')
            return None
        folder = os.path.dirname(folder)
    return None



def add_csv_to_map(arcpy, path):
    """Add a saved report to the active ArcMap data frame once."""
    try:
        document = arcpy.mapping.MapDocument('CURRENT')
        frame = document.activeDataFrame
        target = os.path.normcase(os.path.abspath(path))
        for table in arcpy.mapping.ListTableViews(document, '', frame):
            try:
                if os.path.normcase(os.path.abspath(table.dataSource)) == target:
                    arcpy.RefreshTOC()
                    return
            except Exception:
                continue
        table = arcpy.mapping.TableView(path)
        arcpy.mapping.AddTableView(frame, table)
        arcpy.RefreshTOC()
        arcpy.AddMessage('Added CSV to ArcMap: ' + path)
    except Exception as exc:
        arcpy.AddWarning('CSV saved, but could not add it to ArcMap: {} ({})'.format(path, exc))


def run_and_add(arcpy, outputs, function, *args):
    """Refresh report tables, releasing existing map table references on reruns.

    Restore removed table views if the check fails. Source files are never deleted.
    """
    outputs = [path for path in outputs if path]
    removed = []
    try:
        document = arcpy.mapping.MapDocument('CURRENT')
        targets = set(os.path.normcase(os.path.abspath(path)) for path in outputs)
        for frame in arcpy.mapping.ListDataFrames(document):
            for table in arcpy.mapping.ListTableViews(document, '', frame):
                try:
                    if os.path.normcase(os.path.abspath(table.dataSource)) in targets:
                        arcpy.mapping.RemoveTableView(frame, table)
                        removed.append((frame, table))
                except Exception:
                    continue
    except Exception:
        pass
    try:
        function(*args)
    except Exception:
        for frame, table in removed:
            try:
                arcpy.mapping.AddTableView(frame, table)
            except Exception as exc:
                arcpy.AddWarning('Could not restore report table: ' + str(exc))
        raise
    restored = set()
    for frame, old_table in removed:
        try:
            path = old_table.dataSource
            table = arcpy.mapping.TableView(path)
            table.name = old_table.name
            arcpy.mapping.AddTableView(frame, table)
            restored.add(os.path.normcase(os.path.abspath(path)))
        except Exception as exc:
            arcpy.AddWarning('Could not refresh previous report table: ' + str(exc))
    for path in outputs:
        if os.path.normcase(os.path.abspath(path)) not in restored:
            add_csv_to_map(arcpy, path)
    try:
        arcpy.RefreshTOC()
    except Exception:
        pass

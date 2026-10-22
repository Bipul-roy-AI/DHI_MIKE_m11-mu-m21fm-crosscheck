# -*- coding: utf-8 -*-
"""ArcMap 10.8 batch comparison: selected compiled pipes vs many MIKE 21 FM models."""
from __future__ import print_function
import os
import re
import csv
import io
import sys
from collections import defaultdict
from m21fm_check import (read_m21fm, selected_pipes, compare,
                                     HEADERS, STATUS_INDICES)

BATCH_HEADERS = ('Catchment', 'Model File', 'Model Match Status',
                 'Candidate Models') + HEADERS


def parse_multivalue(text):
    """ArcPy multivalue paths are semicolon delimited and may be quoted."""
    if not text:
        return []
    return [x.strip().strip("'\"") for x in text.split(';') if x.strip().strip("'\"")]


def prefix(value):
    match = re.match(r'^([A-Za-z]{2})(?=_|$)', value.strip())
    return match.group(1).upper() if match else None


def model_prefix(path):
    return prefix(os.path.splitext(os.path.basename(path))[0])


def _missing_row(branch, pipe, status):
    """Reuse the original comparison format for unmatched selected pipes."""
    return compare({branch: pipe}, {})[0]


def compare_batch(pipes, models):
    """Locate exact Branch across ALL supplied models, then classify ownership.

    Numerical comparisons are made only for an unambiguous, correctly named
    model. This avoids mistaking a misfiled Branch for a successful match.
    """
    by_prefix = defaultdict(list)
    by_branch = defaultdict(list)
    for path, model in models:
        pfx = model_prefix(path)
        if pfx is None:
            raise ValueError('Model filename has no two-letter catchment prefix: ' + path)
        by_prefix[pfx].append((path, model))
        for branch in model:
            by_branch[branch].append((path, model))

    rows = []
    for branch in sorted(pipes):
        pfx = prefix(branch)
        matching_prefix_models = by_prefix.get(pfx, [])
        all_hits = by_branch.get(branch, [])
        proper = [(path, model) for path, model in all_hits
                  if model_prefix(path) == pfx]
        misplaced = [(path, model) for path, model in all_hits
                     if model_prefix(path) != pfx]

        if pfx is None:
            status = 'INVALID_BRANCH_PREFIX'
        elif proper and misplaced:
            status = 'CROSS_CATCHMENT_DUPLICATE'
        elif len(proper) > 1:
            status = 'DUPLICATE_BRANCH_IN_MODELS'
        elif len(misplaced) > 1:
            status = 'CROSS_CATCHMENT_DUPLICATE'
        elif len(proper) == 1:
            status = 'FOUND'
        elif len(misplaced) == 1:
            status = 'FOUND_IN_WRONG_CATCHMENT'
        elif not matching_prefix_models:
            status = 'NO_MODEL_FOR_PREFIX'
        else:
            status = 'BRANCH_NOT_FOUND'

        if status == 'FOUND':
            path, model = proper[0]
            record = compare({branch: pipes[branch]}, model)[0]
            model_file = os.path.basename(path)
            candidates = ''
        else:
            # Conflicts must not claim to have passed a numerical comparison.
            record = _missing_row(branch, pipes[branch], status)
            model_file = (os.path.basename(misplaced[0][0])
                          if status == 'FOUND_IN_WRONG_CATCHMENT' else '')
            if all_hits:
                candidates = '; '.join(sorted(os.path.basename(path)
                                              for path, _ in all_hits))
            elif status == 'BRANCH_NOT_FOUND':
                candidates = '; '.join(sorted(os.path.basename(path)
                                              for path, _ in matching_prefix_models))
            else:
                candidates = ''
        rows.append((pfx or '', model_file, status, candidates) + record)
    return rows


def write_batch(path, rows):
    if not path.lower().endswith('.csv'):
        raise ValueError('Output file must end in .csv')
    folder = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(folder):
        raise ValueError('CSV output folder does not exist: ' + folder)
    if sys.version_info[0] < 3:
        stream = open(path, 'wb')
        def encode(row):
            return [v.encode('utf-8') if isinstance(v, unicode) else v for v in row]
    else:
        stream = io.open(path, 'w', encoding='utf-8-sig', newline='')
        def encode(row):
            return row
    try:
        writer = csv.writer(stream)
        writer.writerow(encode(BATCH_HEADERS))
        writer.writerows(encode(row) for row in rows)
    finally:
        stream.close()


def run_batch(arcpy, layer, model_paths, output_path, dia_field, width_field, height_field):
    if not model_paths:
        raise ValueError('Add one or more .m21fm files for batch processing.')
    if len(set(os.path.normcase(os.path.abspath(p)) for p in model_paths)) != len(model_paths):
        raise ValueError('The same .m21fm file was added more than once.')
    pipes = selected_pipes(arcpy, layer, dia_field, width_field, height_field)
    models = [(path, read_m21fm(path)) for path in model_paths]
    rows = compare_batch(pipes, models)
    write_batch(output_path, rows)
    counts = defaultdict(int)
    for row in rows:
        counts[row[2]] += 1
    matched = counts['FOUND']
    mismatch = sum(row[2] == 'FOUND' and any(row[4 + i] == 'MISMATCH'
                   for i in STATUS_INDICES) for row in rows)
    flagged = len(rows) - matched
    arcpy.AddMessage('Batch: {} selected pipes; {} found in expected catchment; '
                     '{} numeric mismatches; {} flagged for model placement/matching.'.format(
                         len(rows), matched, mismatch, flagged))
    arcpy.AddMessage('Combined CSV saved: ' + output_path)
    for status in ('FOUND_IN_WRONG_CATCHMENT', 'CROSS_CATCHMENT_DUPLICATE',
                   'DUPLICATE_BRANCH_IN_MODELS', 'BRANCH_NOT_FOUND',
                   'NO_MODEL_FOR_PREFIX', 'INVALID_BRANCH_PREFIX'):
        if counts[status]:
            arcpy.AddWarning('{}: {} selected pipes. See Candidate Models in CSV.'.format(
                             status, counts[status]))

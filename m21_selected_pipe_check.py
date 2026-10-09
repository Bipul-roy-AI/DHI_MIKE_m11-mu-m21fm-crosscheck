# -*- coding: utf-8 -*-
"""Read selected ArcMap pipes and compare them to MIKE 21 FM culvert values."""
from __future__ import print_function

import csv
import io
import os
import re
import sys


HEADERS = (
    "Branch",
    "M21FM Inflow (m)", "Pipe Inflow (m)", "Inflow Check",
    "M21FM Outflow (m)", "Pipe Outflow (m)", "Outflow Check",
    "M21FM Diameter (m)", "Pipe Dia_mm (mm)", "Diameter Check",
)
TOLERANCE_METRES = 0.001


def _line(block, name):
    match = re.search(r"^\s*" + re.escape(name) + r"\s*=\s*(.*?)\s*$",
                      block, re.I | re.M)
    return match.group(1).strip() if match else None


def _numeric(value):
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def read_m21fm(path):
    with io.open(path, "r", encoding="latin-1") as source:
        content = source.read()
    blocks = re.findall(r"\[culvert_data\](.*?)EndSect\s*//\s*culvert_data",
                        content, re.I | re.S)
    if not blocks:
        raise ValueError("No [culvert_data] entries found in the model file.")
    model = {}
    for position, block in enumerate(blocks, 1):
        location = _line(block, "Location")
        if location is None:
            raise ValueError("Model culvert {} has no Location.".format(position))
        # In the supplied model: Location = '', -1e-155, 'ND_1', 'TopoID'.
        match = re.match(r"\s*'[^']*'\s*,\s*[^,]+\s*,\s*'([^']+)'", location)
        if not match:
            raise ValueError("Cannot read Branch from culvert {} Location: {}".format(
                position, location))
        branch = match.group(1).strip()
        if branch in model:
            raise ValueError("Duplicate model Branch: " + branch)
        attributes = _line(block, "Attributes")
        values = [value.strip() for value in attributes.split(",")] if attributes else []
        if len(values) < 2:
            raise ValueError("Missing invert levels for model Branch " + branch)
        geometry = re.search(r"\[Geometry\](.*?)EndSect\s*//\s*Geometry",
                             block, re.I | re.S)
        diameter = None
        if geometry and _line(geometry.group(1), "Type") == "1":
            # DHI uses this exact spelling in the attached .m21fm file.
            diameter = _numeric(_line(geometry.group(1), "Cicular_Diameter"))
        model[branch] = (_numeric(values[0]), _numeric(values[1]), diameter)
    return model


def selected_pipes(arcpy, layer):
    desc = arcpy.Describe(layer)
    selection = getattr(desc, "FIDSet", "")
    if not selection or not str(selection).strip():
        raise ValueError("Select the pipes in an ArcMap layer first, then choose "
                         "that layer in the Pipe file input. Browsing to the .shp "
                         "file does not carry an ArcMap selection.")
    actual = {field.name.lower(): field.name for field in arcpy.ListFields(layer)}
    needed = ("branch", "z_inflow", "z_outflow", "dia_mm")
    missing = [field for field in needed if field not in actual]
    if missing:
        raise ValueError("Pipe layer is missing fields: " + ", ".join(missing))
    columns = [actual[field] for field in needed]
    pipes = {}
    with arcpy.da.SearchCursor(layer, columns) as cursor:
        for branch, inflow, outflow, dia_mm in cursor:
            branch = str(branch).strip() if branch is not None else ""
            if not branch:
                raise ValueError("Selected pipe has a blank Branch.")
            if branch in pipes:
                raise ValueError("Duplicate selected Branch: " + branch)
            pipes[branch] = (_numeric(inflow), _numeric(outflow), _numeric(dia_mm))
    if not pipes:
        raise ValueError("There are no selected pipe features to compare.")
    return pipes


def _display(value, decimals=4):
    return ("{:0." + str(decimals) + "f}").format(value) if value is not None else ""


def _check(pipe_value, model_value):
    if pipe_value is None or model_value is None:
        return "MISSING_VALUE"
    return "MATCH" if abs(pipe_value - model_value) <= TOLERANCE_METRES else "MISMATCH"


def compare(pipes, model):
    rows = []
    for branch in sorted(pipes):
        pipe_in, pipe_out, pipe_mm = pipes[branch]
        if branch not in model:
            rows.append((branch, "", _display(pipe_in), "MISSING_IN_M21FM",
                         "", _display(pipe_out), "MISSING_IN_M21FM",
                         "", _display(pipe_mm, 1), "MISSING_IN_M21FM"))
            continue
        model_in, model_out, model_dia = model[branch]
        pipe_dia_m = pipe_mm / 1000.0 if pipe_mm is not None else None
        rows.append((branch,
                     _display(model_in), _display(pipe_in), _check(pipe_in, model_in),
                     _display(model_out), _display(pipe_out), _check(pipe_out, model_out),
                     _display(model_dia), _display(pipe_mm, 1), _check(pipe_dia_m, model_dia)))
    return rows


def write_report(path, rows):
    if not path.lower().endswith(".csv"):
        raise ValueError("Output file must end in .csv")
    folder = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(folder):
        raise ValueError("Output folder does not exist: " + folder)
    if sys.version_info[0] < 3:
        stream = open(path, "wb")
        to_csv = lambda row: [value.encode("utf-8") if isinstance(value, unicode) else value
                              for value in row]
    else:
        stream = io.open(path, "w", encoding="utf-8-sig", newline="")
        to_csv = lambda row: row
    try:
        writer = csv.writer(stream)
        writer.writerow(to_csv(HEADERS))
        for row in rows:
            writer.writerow(to_csv(row))
    finally:
        stream.close()


def run(arcpy, layer, model_path, output_path):
    pipes = selected_pipes(arcpy, layer)
    model = read_m21fm(model_path)
    rows = compare(pipes, model)
    write_report(output_path, rows)
    mismatched = sum(any(value == "MISMATCH" for value in
                         (row[3], row[6], row[9])) for row in rows)
    arcpy.AddMessage("Checked {} selected pipes; {} with mismatches.".format(
        len(rows), mismatched))
    arcpy.AddMessage("CSV saved: " + output_path)

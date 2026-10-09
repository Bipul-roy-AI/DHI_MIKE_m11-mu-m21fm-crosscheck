# M21Checker — Pipe Invert & Diameter Check for ArcMap 10.8

**M21Checker** is an ArcMap Python toolbox that compares **selected pipe features** against culvert definitions in a **MIKE 21 FM (`.m21fm`)** model file. It creates a branch-by-branch CSV report with the pipe values and model values side by side, flagging differences in invert elevations and diameters.

> **Compatibility:** ArcGIS Desktop / **ArcMap 10.8** (ArcPy, Python 2.7). This is an ArcMap toolbox, **not** an ArcGIS Pro toolbox. External `mikeio` and `pyshp` packages are not required.

## Features

- **Inflow invert elevation:** pipe `Z_inflow` vs. first culvert `Attributes` elevation.
- **Outflow invert elevation:** pipe `Z_outflow` vs. second culvert `Attributes` elevation.
- **Diameter:** pipe `Dia_mm` (millimetres) vs. MIKE model `Geometry/Cicular_Diameter` (metres), with appropriate unit conversion.
- **Branch matching:** matches pipe `Branch` against the branch parsed from each MIKE culvert `Location` field.
- **Tolerance:** a comparison is a match when the absolute difference is **≤ 0.001 m** (1 mm).
- **Selected features only:** operates on the currently selected pipes from an ArcMap feature layer.
- **CSV export:** reports `MATCH`, `MISMATCH`, `MISSING_VALUE`, or `MISSING_IN_M21FM` as applicable.

**Parser note:** `Cicular_Diameter` is intentionally spelled exactly as expected by this MIKE file parser. It is read for geometries with `Type = 1`.

## Requirements

1. **ArcMap 10.8** with the included ArcPy Python runtime.
2. A pipe feature layer with the fields below.
3. A MIKE 21 FM `.m21fm` model file containing culvert definitions.
4. A valid output folder for the generated CSV.

| Field | Meaning | Units |
| --- | --- | --- |
| `Branch` | Unique pipe branch identifier | Text/ID |
| `Z_inflow` | Inflow invert elevation | m |
| `Z_outflow` | Outflow invert elevation | m |
| `Dia_mm` | Pipe diameter | mm |

## Installation

1. Select **Code → Download ZIP** above and extract it (or clone this repository).
2. Keep `M21Checker.pyt` and `m21_selected_pipe_check.py` **in the same directory**. The two `.xml` files are ArcGIS metadata sidecars.
3. Open **ArcMap 10.8**.
4. In the **Catalog** window, select **Add Toolbox**, then browse to `M21Checker.pyt`.
5. Open **Pipe and M21FM Check → Pipe Invert and Diameter Check**.

If an older version appears in Catalog, remove the old toolbox entry and add the updated `M21Checker.pyt` file again.

## How to use

1. Add your pipe shapefile or feature dataset as a **layer** in ArcMap.
2. **Select the pipes** you want to check using ArcMap's selection tools or attribute table.
3. For **Pipe file**, select the existing **map layer from the dropdown**. **Do not browse directly to the `.shp` file**, because the file path does not preserve the ArcMap feature selection.
4. Choose your **MIKE 21 FM model** (`.m21fm`).
5. Specify the **Output comparison CSV** in a folder that already exists, for example `pipe_invert_diameter_check.csv`.
6. Run the tool and inspect the report.

**Important:** The tool requires an active feature selection and raises an error if none is present. A previously existing CSV at the same output path will be overwritten.

## CSV output

The tool writes one row per selected pipe branch, with the following columns:

| Column | Description |
| --- | --- |
| `Branch` | Selected pipe identifier |
| `M21FM Inflow (m)` | Inflow elevation in the MIKE model |
| `Pipe Inflow (m)` | Inflow elevation in the pipe layer |
| `Inflow Check` | Inflow comparison result |
| `M21FM Outflow (m)` | Outflow elevation in the MIKE model |
| `Pipe Outflow (m)` | Outflow elevation in the pipe layer |
| `Outflow Check` | Outflow comparison result |
| `M21FM Diameter (m)` | Culvert diameter in the MIKE model |
| `Pipe Dia_mm (mm)` | Pipe diameter in the feature layer |
| `Diameter Check` | Diameter comparison after mm-to-m conversion |

### Comparison status definitions

- **`MATCH`:** numerical values differ by at most 0.001 m.
- **`MISMATCH`:** numerical values differ by more than 0.001 m.
- **`MISSING_VALUE`:** a required numerical value is empty.
- **`MISSING_IN_M21FM`:** the selected pipe's Branch is not found in the MIKE culvert data.

Duplicate model Branch identifiers, duplicate selected pipe Branch identifiers, absent layer fields, and invalid output paths trigger errors rather than silent substitutions.

### Example from the supplied project notes

The original notes describe an example with **131 matching branches**. When all those pipes are checked, they report **2 inflow mismatches**, **4 outflow mismatches**, and **0 diameter mismatches**. The underlying example model and shapefile are **not** included here, so these figures have not been independently reproduced.

## Project files

```text
M21fm-culvert-checker/
├── M21Checker.pyt
├── m21_selected_pipe_check.py
├── M21Checker.pyt.xml
├── M21Checker.PipeInvertDiameterCheck.pyt.xml
├── README.md
└── .gitignore
```

- **`M21Checker.pyt`:** ArcMap toolbox UI, parameters and execution entry point.
- **`m21_selected_pipe_check.py`:** parsing, selected-feature validation, numerical comparison and CSV report generation.
- **`*.pyt.xml`:** ArcGIS toolbox and tool metadata.
- **`.gitignore`:** prevents committing generated Python caches and local report files.

The uploaded `m21_selected_pipe_check.pyc` was a compiled Python cache and is intentionally **not** part of the source repository. ArcMap can regenerate it.

## Scope and limitations

The parser follows the supplied MIKE model format: the third quoted `Location` value contains the branch, `Attributes` holds the inlet/outlet invert elevations, and geometry `Type = 1` exposes `Cicular_Diameter`. Other MIKE model exports may require modifications.

The original uploaded files do not include an executable example `.m21fm` model or pipe shapefile. The toolbox has **not been validated end-to-end in ArcMap with field data** here; test it against your project's selected layer and model before operational use.

## Licence

No open-source licence was supplied with these files. Unless you add a licence, the default copyright rules apply.

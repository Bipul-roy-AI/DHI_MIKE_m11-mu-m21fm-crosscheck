# -*- coding: utf-8 -*-
"""ArcMap 10.8 / Python 2.7. Keep all companion scripts in this folder."""
import os
import sys
try:
    import imp
    def _load_script(name, path):
        return imp.load_source(name, path)
except ImportError:
    import importlib.util
    def _load_script(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
import arcpy

_folder = os.path.dirname(os.path.abspath(__file__))
if _folder in sys.path:
    sys.path.remove(_folder)
sys.path.insert(0, _folder)
# Load this package's scripts explicitly; do not reuse another toolbox's cache.
for _name in ('crosscheck_common', 'm11_nwk_check', 'mu_check', 'm21fm_check', 'm21fm_batch_check'):
    _load_script(_name, os.path.join(_folder, _name + '.py'))
from crosscheck_common import field_map, normalized_field, project_output_path, run_and_add
from m11_nwk_check import run_m11
from mu_check import run_mu, NODE_ALIASES

class Toolbox(object):
    def __init__(self):
        self.label = 'm11, mu, m21fm crosscheck'
        self.alias = 'm11_mu_m21fm_crosscheck'
        self.tools = [M11NwkCheck, MUCheck, M21FMCheck, M21FMBatchCheck]

def _param(label, name, datatype, required=True):
    item = arcpy.Parameter(displayName=label, name=name, datatype=datatype,
                           parameterType='Required' if required else 'Optional', direction='Input')
    return item


def _initialization_error():
    import traceback
    error = _param('Initialization error - copy this text', 'initialization_error', 'GPString')
    error.value = traceback.format_exc()
    return [error]


def _show_initialization_error(params, count):
    if len(params) != count:
        params[0].setErrorMessage(str(params[0].value))
        return True
    return False


class M11NwkCheck(object):
    def __init__(self):
        self.label = 'm11 nwk check - pipe shp file'
        self.description = 'One row per selected Model=m11 pipe. Notes contain issues only.'
        self.canRunInBackground = False

    def getParameterInfo(self):
        try:
            pipes = _param('Selected pipe layer (Model=m11)', 'm11_selected_pipes', 'GPFeatureLayer')
            network = _param('MIKE 11 network (.nwk11)', 'm11_network_file', 'DEFile')
            network.filter.list = ['nwk11', 'nwk']
            output = arcpy.Parameter(displayName='Output MIKE 11 CSV (.csv)', name='m11_csv_path',
                                      datatype='DEFile', parameterType='Required', direction='Output')
            output.filter.list = ['csv']
            return [pipes, network, output]
        except Exception:
            return _initialization_error()

    def isLicensed(self):
        return True

    def updateParameters(self, params):
        if len(params) == 3 and params[0].value and not params[2].altered:
            try:
                auto_path = project_output_path(arcpy, params[0].value)
                params[2].value = auto_path[:-len('_comparison.csv')] + '_m11_check.csv' if auto_path else None
            except Exception:
                pass

    def updateMessages(self, params):
        if _show_initialization_error(params, 3):
            return
        if params[0].value and not params[2].valueAsText:
            params[2].setWarningMessage('No project Temp folder found. Choose an output CSV manually.')

    def execute(self, params, messages):
        if len(params) != 3:
            raise RuntimeError(str(params[0].value))
        run_and_add(arcpy, [params[2].valueAsText], run_m11, arcpy, params[0].value, params[1].valueAsText, params[2].valueAsText)


class MUCheck(object):
    def __init__(self):
        self.label = 'mu check - pipe and node shp file'
        self.description = 'MU pipes: upstream/downstream level and diameter. MU nodes: GL, Invert_L and diameter.'
        self.canRunInBackground = False

    def getParameterInfo(self):
        try:
            pipes = _param('Selected pipe layer (optional, Model=mu)', 'mu_selected_pipes', 'GPFeatureLayer', False)
            nodes = _param('Selected MU node layer (optional)', 'mu_selected_nodes', 'GPFeatureLayer', False)
            model = _param('Corrected MIKE Plus file (.sqlite or .mupp)', 'mu_model_file', 'DEFile')
            model.filter.list = ['sqlite', 'mupp']
            folder = _param('Existing folder for CSV reports', 'mu_csv_folder', 'DEFolder')
            node_id = _param('Node ID field', 'mu_node_id_field', 'GPString', False)
            ground = _param('Node ground level field (metres)', 'mu_node_gl_field', 'GPString', False)
            bottom = _param('Node bottom/invert level field (metres)', 'mu_node_invert_field', 'GPString', False)
            diameter = _param('Node diameter field', 'mu_node_diameter_field', 'GPString', False)
            units = _param('Node shapefile diameter unit', 'mu_node_diameter_unit', 'GPString', False)
            for parameter in (node_id, ground, bottom, diameter, units):
                parameter.filter.type = 'ValueList'
            units.filter.list = ['Millimetres (mm)', 'Metres (m)']
            return [pipes, nodes, model, folder, node_id, ground, bottom, diameter, units]
        except Exception:
            return _initialization_error()

    def isLicensed(self):
        return True

    def updateParameters(self, params):
        if len(params) != 9:
            return
        layer = params[0].value or params[1].value
        if layer and not params[3].altered:
            try:
                auto_path = project_output_path(arcpy, layer)
                params[3].value = os.path.dirname(auto_path) if auto_path else None
            except Exception:
                pass
        if params[1].value:
            try:
                fields = arcpy.ListFields(params[1].value)
                names = [field.name for field in fields]
                detected = field_map(arcpy, params[1].value, NODE_ALIASES, ())
                for index, key in ((4, 'id'), (5, 'ground'), (6, 'invert'), (7, 'diameter')):
                    params[index].filter.list = names
                    if not params[index].altered or params[index].valueAsText not in names:
                        params[index].value = detected.get(key)
                if not params[8].altered:
                    diameter_field = params[7].valueAsText
                    field = next((item for item in fields if item.name == diameter_field), None)
                    tokens = set()
                    if field:
                        tokens = {normalized_field(field.name), normalized_field(getattr(field, 'aliasName', field.name))}
                    if tokens & {'diamm', 'diammm', 'diametermm'}:
                        params[8].value = 'Millimetres (mm)'
                    elif tokens & {'diameterm', 'diametrem', 'diameterinmetres', 'diameterinmeters'}:
                        params[8].value = 'Metres (m)'
                    else:
                        params[8].value = None
            except Exception:
                # Explicit dropdown choices and the runtime field list remain available.
                pass

    def updateMessages(self, params):
        if _show_initialization_error(params, 9):
            return
        if (params[0].value or params[1].value) and not params[3].valueAsText:
            params[3].setWarningMessage('No project Temp folder found. Choose an existing output folder manually.')
        if params[1].value:
            for index in (4, 5, 6, 7, 8):
                if not params[index].valueAsText:
                    params[index].setErrorMessage('Choose this node field/unit before running.')

    def execute(self, params, messages):
        if len(params) != 9:
            raise RuntimeError(str(params[0].value))
        folder = params[3].valueAsText
        if not folder or not os.path.isdir(folder):
            raise ValueError('Choose an existing output folder.')
        pipes_csv = os.path.join(folder, 'mu_pipe_check.csv') if params[0].value else None
        nodes_csv = os.path.join(folder, 'mu_node_check.csv') if params[1].value else None
        node_fields = {key: params[index].valueAsText for index, key in
                       ((4, 'id'), (5, 'ground'), (6, 'invert'), (7, 'diameter'))}
        diameter_unit = {'Millimetres (mm)': 'mm', 'Metres (m)': 'm'}.get(params[8].valueAsText)
        run_and_add(arcpy, [pipes_csv, nodes_csv], run_mu, arcpy, params[0].value, params[1].value,
               params[2].valueAsText, pipes_csv, nodes_csv, node_fields, diameter_unit)


class M21FMCheck(object):
    def __init__(self):
        self.label = 'm21fm check - pipe shp'
        self.description = 'Compare selected pipes to MIKE 21 FM culverts by Branch, inverts and circular/rectangular geometry.'
        self.canRunInBackground = False

    def getParameterInfo(self):
        pipes = arcpy.Parameter(displayName='Pipe file (select pipes in map first)', name='pipes',
                                datatype='GPFeatureLayer', parameterType='Required', direction='Input')
        model = arcpy.Parameter(displayName='MIKE 21 FM model', name='model',
                                datatype='DEFile', parameterType='Required', direction='Input')
        model.filter.list = ['m21fm']
        dia = arcpy.Parameter(displayName='Diameter field (mm)', name='diameter_field',
                              datatype='Field', parameterType='Required', direction='Input')
        dia.parameterDependencies = [pipes.name]
        dia.filter.list = ['Short', 'Long', 'Float', 'Double', 'SmallInteger', 'Integer']
        width = arcpy.Parameter(displayName='Width field (mm)', name='width_field',
                                datatype='Field', parameterType='Required', direction='Input')
        width.parameterDependencies = [pipes.name]
        width.filter.list = ['Short', 'Long', 'Float', 'Double', 'SmallInteger', 'Integer']
        height = arcpy.Parameter(displayName='Height field (mm)', name='height_field',
                                 datatype='Field', parameterType='Required', direction='Input')
        height.parameterDependencies = [pipes.name]
        height.filter.list = ['Short', 'Long', 'Float', 'Double', 'SmallInteger', 'Integer']
        report = arcpy.Parameter(displayName='Output comparison CSV (project Temp)', name='report',
                                 datatype='DEFile', parameterType='Required', direction='Output')
        report.filter.list = ['csv']
        return [pipes, model, dia, width, height, report]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        layer = parameters[0]
        if not layer.valueAsText:
            return
        try:
            fields = {f.name.lower(): f.name for f in arcpy.ListFields(layer.value)}
            for i, target in [(2, 'dia_mm'), (3, 'width_mm'), (4, 'height_mm')]:
                if not parameters[i].altered and target in fields:
                    parameters[i].value = fields[target]
            # Do not replace an operator-chosen output path.
            if not parameters[5].altered:
                auto_path = project_output_path(arcpy, layer.value)
                if auto_path:
                    parameters[5].value = auto_path
                else:
                    # Clear a previous auto-filled path when switching projects.
                    parameters[5].value = None
        except (ValueError, IOError, OSError, RuntimeError):
            # Manual output selection remains possible if auto-detection fails.
            if not parameters[5].altered:
                parameters[5].value = None

    def updateMessages(self, parameters):
        if parameters[0].valueAsText and not parameters[5].valueAsText:
            parameters[5].setWarningMessage(
                'No existing Temp directory under a numbered *_SFRM_* project '
                'folder was detected. Choose a CSV output location manually.')

    def execute(self, parameters, messages):
        folder = os.path.dirname(os.path.abspath(__file__))
        if folder not in sys.path:
            sys.path.insert(0, folder)
        from m21fm_check import run
        try:
            if not parameters[5].valueAsText:
                raise ValueError('Choose a CSV output location before running the tool.')
            run_and_add(arcpy, [parameters[5].valueAsText], run, arcpy, parameters[0].value, parameters[1].valueAsText,
                parameters[5].valueAsText, parameters[2].valueAsText,
                parameters[3].valueAsText, parameters[4].valueAsText)
        except (ValueError, IOError, OSError) as exc:
            arcpy.AddError(str(exc))
            raise arcpy.ExecuteError(str(exc))


class M21FMBatchCheck(M21FMCheck):
    """Selected compiled shapefile against several model files."""
    def __init__(self):
        self.label = 'm21fm check - pipe shp (batch processing)'
        self.description = ('Check selected pipes from the compiled shapefile against multiple '
                            'MIKE 21 FM models. Prefix identifies catchment, full Branch identifies culvert.')
        self.canRunInBackground = False

    def getParameterInfo(self):
        params = M21FMCheck.getParameterInfo(self)
        params[0].displayName = 'Compiled pipe layer (select pipes in map first)'
        params[1].displayName = 'MIKE 21 FM models (add multiple files)'
        params[1].multiValue = True
        params[5].displayName = 'Combined batch comparison CSV (project Temp)'
        return params

    def updateParameters(self, parameters):
        M21FMCheck.updateParameters(self, parameters)
        output = parameters[5]
        if output.valueAsText and not output.altered:
            directory, filename = os.path.split(output.valueAsText)
            if filename.lower().endswith('_comparison.csv'):
                stem = filename[:-len('_comparison.csv')]
                output.value = os.path.join(directory, stem + '_batch_comparison.csv')

    def updateMessages(self, parameters):
        M21FMCheck.updateMessages(self, parameters)
        if parameters[0].valueAsText:
            try:
                base = os.path.splitext(os.path.basename(arcpy.Describe(parameters[0].value).catalogPath))[0]
                if base.lower() != 'plz_pipes_culverts':
                    parameters[0].setWarningMessage('Batch processing expects compiled plz_pipes_culverts.shp; currently using ' + base)
            except (ValueError, IOError, OSError, RuntimeError):
                pass

    def execute(self, parameters, messages):
        folder = os.path.dirname(os.path.abspath(__file__))
        if folder not in sys.path:
            sys.path.insert(0, folder)
        from m21fm_batch_check import run_batch, parse_multivalue
        try:
            if not parameters[5].valueAsText:
                raise ValueError('Choose a CSV output location before running the batch tool.')
            models = parse_multivalue(parameters[1].valueAsText)
            run_and_add(arcpy, [parameters[5].valueAsText], run_batch, arcpy, parameters[0].value, models, parameters[5].valueAsText,
                      parameters[2].valueAsText, parameters[3].valueAsText,
                      parameters[4].valueAsText)
        except (ValueError, IOError, OSError) as exc:
            arcpy.AddError(str(exc))
            raise arcpy.ExecuteError(str(exc))

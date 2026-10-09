# -*- coding: utf-8 -*-
"""ArcMap 10.8 toolbox with the selected-pipe comparison tool."""
import os
import sys

import arcpy


class Toolbox(object):
    def __init__(self):
        self.label = "Pipe and M21FM Check"
        self.alias = "pipe_m21fm_check"
        self.tools = [PipeInvertDiameterCheck]


class PipeInvertDiameterCheck(object):
    def __init__(self):
        self.label = "Pipe Invert and Diameter Check"
        self.description = "Compare selected pipes to MIKE culverts by Branch."
        self.canRunInBackground = False

    def getParameterInfo(self):
        pipes = arcpy.Parameter(displayName="Pipe file (select pipes in map first)",
                                name="pipes", datatype="GPFeatureLayer",
                                parameterType="Required", direction="Input")
        model = arcpy.Parameter(displayName="MIKE 21 FM model", name="model",
                                datatype="DEFile", parameterType="Required", direction="Input")
        model.filter.list = ["m21fm"]
        report = arcpy.Parameter(displayName="Output comparison CSV", name="report",
                                 datatype="DEFile", parameterType="Required", direction="Output")
        report.filter.list = ["csv"]
        return [pipes, model, report]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        if parameters[0].valueAsText and not parameters[2].altered:
            base = os.path.dirname(arcpy.Describe(parameters[0].value).catalogPath)
            parameters[2].value = os.path.join(base, "pipe_invert_diameter_check.csv")

    def updateMessages(self, parameters):
        pass

    def execute(self, parameters, messages):
        folder = os.path.dirname(os.path.abspath(__file__))
        if folder not in sys.path:
            sys.path.insert(0, folder)
        from m21_selected_pipe_check import run
        try:
            run(arcpy, parameters[0].value, parameters[1].valueAsText,
                parameters[2].valueAsText)
        except ValueError as exc:
            raise arcpy.ExecuteError(str(exc))

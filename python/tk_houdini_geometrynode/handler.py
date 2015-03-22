# Copyright (c) 2015 Pixomondo
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the MIT License included in this
# distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the MIT License. All rights
# not expressly granted therein are reserved by Pixomondo.
#
# === Original License ===
#
# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import os

import hou
import sgtk


class ToolkitGeometryNodeHandler(object):
    def __init__(self, app):
        self._app = app
        self._work_file_template = self._app.get_template("work_file_template")

    def _get_hipfile_fields(self):        
        """
        Extract fields from the current Houdini file using the template
        """
        curr_filename = hou.hipFile.path()
        
        work_fields = {}
        if self._work_file_template and self._work_file_template.validate(curr_filename):
            work_fields = self._work_file_template.get_fields(curr_filename)
                
        return work_fields

    def compute_path(self, node):
        # Get relevant fields from the scene filename and contents
        work_file_fields = self._get_hipfile_fields()
        if not work_file_fields:
            raise sgtk.TankError("This Houdini file is not a Shotgun Toolkit work file!")

        # Get the templates from the app
        template = self._app.get_template("work_cache_template")

        # create fields dict with all the metadata
        fields = {}
        fields["name"] = work_file_fields.get("name")
        fields["version"] = work_file_fields["version"]
        fields["node"] = node.name()
        fields["SEQ"] = "FORMAT: $F"

        # Get the camera width and height if necessary
        if "width" in template.keys or "height" in template.keys:
            # Get the camera
            cam_path = node.parm("geometry1_camera").eval()
            cam_node = hou.node(cam_path)
            if not cam_node:
                raise sgtk.TankError("Camera %s not found." % cam_path)

            fields["width"] = cam_node.parm("resx").eval()
            fields["height"] = cam_node.parm("resy").eval()

        fields.update(self._app.context.as_template_fields(template))
        
        path = template.apply_fields(fields)

        # TODO: Move this out to some sort of pre-render callback
        # out_dir = os.path.dirname(path)
        # self._app.ensure_folder_exists(out_dir)

        path = path.replace(os.path.sep, "/")

        return path

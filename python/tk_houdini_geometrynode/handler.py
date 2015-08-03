# Copyright (c) 2015 Pixomondo
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the MIT License included in this
# distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the MIT License. All rights
# not expressly granted therein are reserved by Pixomondo.

import os
import sys

import hou
import sgtk


class ToolkitGeometryNodeHandler(object):

    SG_NODE_CLASS = 'sgtk_geometry'
    PARM_OUTPUT_PATH = 'sopoutput'
    PARM_CONFIG = 'geometry_config'

    def __init__(self, app):
        self._app = app
        self._work_file_template = self._app.get_template("work_file_template")

    ############################################################################
    # Public methods

    def compute_path(self, node):
        # Get relevant fields from the scene filename and contents
        work_file_fields = self.__get_hipfile_fields()
        if not work_file_fields:
            msg = "This Houdini file is not a Shotgun Toolkit work file!"
            raise sgtk.TankError(msg)

        # Get the templates from the app
        template = self._app.get_template("work_cache_template")

        # create fields dict with all the metadata
        fields = {}
        fields["name"] = work_file_fields.get("name")
        fields["version"] = work_file_fields["version"]
        fields["renderpass"] = node.name()
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
        path = path.replace(os.path.sep, "/")

        return path

    def get_nodes(self, class_=None):
        """
        Returns a list of sgtk nodes
        """
        node_class = ToolkitGeometryNodeHandler.SG_NODE_CLASS
        sop = True if not class_ or class_ == 'sop' else False
        rop = True if not class_ or class_ == 'rop' else False
        nodes = []
        if sop:
            nodes += hou.nodeType(hou.sopNodeTypeCategory(),
                                  node_class).instances()
        if rop:
            nodes += hou.nodeType(hou.ropNodeTypeCategory(),
                                  node_class).instances()
        return nodes

    def get_node_profile_name(self, node):
        """
        Return the name of the profile the specified node is using
        """
        config_parm = node.parm(self.PARM_CONFIG)
        return config_parm.menuLabels()[config_parm.eval()]

    def get_files_on_disk(self, node):
        """
        Called from render publisher & UI (via exists_on_disk)
        Returns the files on disk associated with this node
        """
        return self.__get_files_on_disk(node)

    def create_file_node(self):
        """
        Used by geometry_filein_button callback.
        Creates a file node.
        Sets the path to the current output path of this node.
        Sets the node name to the current nodes names.
        """
        node = hou.pwd()

        parm = node.parm(self.PARM_OUTPUT_PATH)
        name = 'file_' + node.name()

        file_sop = node.parent().createNode("file")
        file_sop.parm("file").set(parm.menuLabels()[parm.eval()])
        file_sop.setName(name, unique_name=True)

        # Move it away from the origin
        file_sop.moveToGoodPosition()

    def set_default_node_name(self, node):
        name = self._app.get_setting('default_node_name')
        return node.setName(name, unique_name=True)

    def create_output_path_menu(self):
        """
        Creates the output path menu.
        """
        node = hou.pwd()

        # Build the menu
        menu = []
        menu.append("sgtk")

        try:
            menu.append(self.compute_path(node))
        except sgtk.TankError, err:
            warn_err = '{0}: {1}'.format(node.name(), err)
            self._app.log_warning(warn_err)
            menu.append("ERROR: %s" % err)

        return menu

    def convert_sg_to_geometry_nodes(self):
        """
        Utility function to convert all Shotgun Geometry nodes to regular
        Geometry nodes.

        # Example use:
        import sgtk
        eng = sgtk.platform.current_engine()
        app = eng.apps["tk-houdini-geometrynode"]
        # Convert Shotgun Geometry nodes to Geometry nodes:
        app.convert_to_geometry_nodes()
        """

        # get sgtk geometry nodes:
        sg_nodes = self.get_nodes()
        for sg_n in sg_nodes:
            sop_types = hou.sopNodeTypeCategory().nodeTypes()
            sop_type = sop_types[ToolkitGeometryNodeHandler.SG_NODE_CLASS]
            rop_types = hou.ropNodeTypeCategory().nodeTypes()
            rop_type = rop_types[ToolkitGeometryNodeHandler.SG_NODE_CLASS]
            is_sop = sg_n.type() == sop_type
            is_rop = sg_n.type() == rop_type

            # set as selected:
            node_name = sg_n.name()
            node_pos = sg_n.position()

            # create new regular Geometry node:

            if is_sop:
                geometry_operator = 'rop_geometry'
            elif is_rop:
                geometry_operator = 'geometry'
            else:
                continue

            new_n = sg_n.parent().createNode(geometry_operator)

            # copy across file parms:
            filename = self.__get_menu_label(sg_n.parm('sopoutput'))
            new_n.parm('sopoutput').set(filename)

            # copy across any knob values from the internal geometry node.
            # parmTuples
            exclude = ['sopoutput']
            self.__copy_parm_values(sg_n, new_n, exclude)

            # Store Toolkit specific information on geometry node
            # so that we can reverse this process later

            # Profile Name
            new_n.setUserData('tk_profile_name',
                              self.get_node_profile_name(sg_n))

            # Copy inputs and move outputs
            self.__copy_inputs_to_node(sg_n, new_n)
            self.__move_outputs_to_node(sg_n, new_n)
            self.__copy_color(sg_n, new_n)

            # delete original node:
            sg_n.destroy()

            # rename new node:
            new_n.setName(node_name)
            new_n.setPosition(node_pos)

    def convert_geometry_to_sg_nodes(self):
        """
        Utility function to convert all Geometry nodes to Shotgun
        Geometry nodes (only converts Geometry nodes that were previously
        Shotgun Geometry nodes)

        # Example use:
        import sgtk
        eng = sgtk.platform.current_engine()
        app = eng.apps["tk-houdini-geometrynode"]
        # Convert previously converted Geometry nodes back to
        # Shotgun Geometry nodes:
        app.convert_from_geometry_nodes()
        """

        # get geometry nodes:
        sop_nodes = hou.nodeType(hou.sopNodeTypeCategory(),
                                 'rop_geometry').instances()
        rop_nodes = hou.nodeType(hou.ropNodeTypeCategory(),
                                 'geometry').instances()
        nodes = sop_nodes + rop_nodes
        for n in nodes:

            user_dict = n.userDataDict()

            profile = user_dict.get('tk_profile_name')

            if not profile:
                # can't convert to a Shotgun Geometry Node
                # as we have missing parameters!
                continue

            # set as selected:
            # wn.setSelected(True)
            node_name = n.name()
            node_pos = n.position()

            # create new Shotgun Geometry node:
            node_class = ToolkitGeometryNodeHandler.SG_NODE_CLASS
            new_sg_n = n.parent().createNode(node_class)

            # set the profile
            try:
                parm = new_sg_n.parm(ToolkitGeometryNodeHandler.PARM_CONFIG)
                index = parm.menuLabels().index(profile)
                parm.set(index)
            except ValueError:
                pass

            # copy across and knob values from the internal geometry node.
            exclude = ['sopoutput']
            self.__copy_parm_values(n, new_sg_n, exclude)

            # Copy inputs and move outputs
            self.__copy_inputs_to_node(n, new_sg_n)
            self.__move_outputs_to_node(n, new_sg_n)
            self.__copy_color(n, new_sg_n)

            # delete original node:
            n.destroy()

            # rename new node:
            new_sg_n.setName(node_name)
            new_sg_n.setPosition(node_pos)

    ############################################################################
    # Public methods called from OTL - although these are public, they should
    # be considered as private and not used directly!

    def on_copy_path_to_clipboard_button_callback(self):
        """
        Callback from the gizmo whenever the 'Copy path to clipboard' button
        is pressed.
        """
        node = hou.pwd()

        # get the path depending if in full or proxy mode:
        render_path = self.__get_render_path(node)

        # use Qt to copy the path to the clipboard:
        from sgtk.platform.qt import QtGui
        QtGui.QApplication.clipboard().setText(render_path)

    def on_show_in_fs_button_callback(self):
        """
        Shows the location of the node in the file system.
        This is a callback which is executed when the show in fs
        button is pressed on the houdini output node.
        """
        node = hou.pwd()
        if not node:
            return

        render_dir = None

        # first, try to just use the current cached path:
        render_path = self.__get_render_path(node)
        if render_path:
            # the above method returns houdini style slashes, so ensure these
            # are pointing correctly
            render_path = render_path.replace("/", os.path.sep)

            dir_name = os.path.dirname(render_path)
            if os.path.exists(dir_name):
                render_dir = dir_name

        if not render_dir:
            # render directory doesn't exist so try using location
            # of rendered frames instead:
            try:
                files = self.get_files_on_disk(node)
                if len(files) == 0:
                    msg = ("There are no renders for this node yet!\n"
                           "When you render, the files will be written to "
                           "the following location:\n\n%s" % render_path)
                    hou.ui.displayMessage(msg)
                else:
                    render_dir = os.path.dirname(files[0])
            except Exception, e:
                msg = ("Unable to jump to file system:\n\n%s" % e)
                hou.ui.displayMessage(msg)

        # if we have a valid render path then show it:
        if render_dir:
            system = sys.platform

            # run the app
            if system == "linux2":
                cmd = "xdg-open \"%s\"" % render_dir
            elif system == "darwin":
                cmd = "open '%s'" % render_dir
            elif system == "win32":
                cmd = "cmd.exe /C start \"Folder\" \"%s\"" % render_dir
            else:
                raise Exception("Platform '%s' is not supported." % system)

            self._app.log_debug("Executing command '%s'" % cmd)
            exit_code = os.system(cmd)
            if exit_code != 0:
                msg = ("Failed to launch '%s'!" % cmd)
                hou.ui.displayMessage(msg)

    ############################################################################
    # Private methods

    def __copy_color(self, node_a, node_b):
        color_a = node_a.color()
        node_b.setColor(color_a)

    def __get_menu_label(self, parm, check_for_sgtk=True):
        if not check_for_sgtk:
            return parm.menuLabels()[parm.eval()]

        if parm.menuItems()[parm.eval()] == 'sgtk':
            return parm.menuLabels()[parm.eval()]
        else:
            return parm.menuItems()[parm.eval()]

    def __get_hipfile_fields(self):
        """
        Extract fields from the current Houdini file using the template
        """
        curr_filename = hou.hipFile.path()

        work_fields = {}
        if self._work_file_template \
                and self._work_file_template.validate(curr_filename):
            work_fields = self._work_file_template.get_fields(curr_filename)

        return work_fields

    def __get_render_path(self, node):
        output_parm = node.parm(self.PARM_OUTPUT_PATH)
        path = output_parm.menuLabels()[output_parm.eval()]
        return path

    def __get_render_template(self, node):
        """
        Get a specific render template for the current profile
        """
        return self.__get_template(node, "work_render_template")

    def __get_template(self, node, name):
        """
        Get the named template for the specified node.
        """
        return self._app.get_template(name)

    def __get_files_on_disk(self, node):
        """
        Called from render publisher & UI (via exists_on_disk)
        Returns the files on disk associated with this node
        """
        file_name = self.__get_render_path(node)
        template = self.__get_render_template(node)

        if not template.validate(file_name):
            msg = ("Could not resolve the files on disk for node %s."
                   "The path '%s' is not recognized by Shotgun!"
                   % (node.name(), file_name))
            raise Exception(msg)

        fields = template.get_fields(file_name)

        # make sure we don't look for any eye - %V or SEQ - %04d stuff
        frames = self._app.tank.paths_from_template(template, fields,
                                                    ["SEQ", "eye"])
        return frames

    def __copy_parm_values(self, source_node, target_node, exclude=None):
        """
        Copy parameter values of the source node to those of the target node
        if a parameter with the same name exists.
        """
        exclude = exclude if exclude else []
        parms = [p for p in source_node.parms() if p.name() not in exclude]
        for parm_to_copy in parms:

            parm_template = parm_to_copy.parmTemplate()
            # Skip folder parms.
            if isinstance(parm_template, hou.FolderSetParmTemplate):
                continue

            parm_to_copy_to = target_node.parm(parm_to_copy.name())
            # If the parm on the target node does not exist, skip this parm.
            if parm_to_copy_to is None:
                continue

            # If we have keys/expressions we need to copy them all.
            if parm_to_copy.keyframes():
                # Copy all hou.Keyframe objects.
                for key in parm_to_copy.keyframes():
                    parm_to_copy_to.setKeyframe(key)
            else:
                # If the parameter is a string copy the raw string.
                if isinstance(parm_template, hou.StringParmTemplate):
                    parm_to_copy_to.set(parm_to_copy.unexpandedString())
                # Copy the raw value.
                else:
                    parm_to_copy_to.set(parm_to_copy.eval())

    def __copy_inputs_to_node(self, node, target, ignore_missing=False):
        """ Copy all the input connections from this node to the
            target node.

            ignore_missing: If the target node does not have enough
                            inputs then skip this connection.
        """
        input_connections = node.inputConnections()

        num_target_inputs = len(target.inputConnectors())
        if num_target_inputs is 0:
            raise hou.OperationFailed("Target node has no inputs.")

        for connection in input_connections:
            index = connection.inputIndex()
            if index > (num_target_inputs - 1):
                if ignore_missing:
                    continue
                else:
                    raise hou.InvalidInput("Target node has too few inputs.")

            target.setInput(index, connection.inputNode())

    def __move_outputs_to_node(self, node, target):
        """ Move all the output connections from this node to the
            target node.
        """
        output_connections = node.outputConnections()

        for connection in output_connections:
            node = connection.outputNode()
            node.setInput(connection.inputIndex(), target)

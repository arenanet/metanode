"""
Base classes and functions for creating new Metanode classes.
"""

from collections import OrderedDict
import inspect
import json

import maya.api.OpenMaya as om2
import pymel.core as pm

from meta.config import *


class Register(type):
    """
    Meta type for tracking all Metanode classes in the import path.
    """
    __meta_types__ = {}

    def __init__(cls, *args, **kwargs):
        super(Register, cls).__init__(*args, **kwargs)
        fully_qualified = cls.__module__ + '.' + cls.__name__
        cls.__class__.__meta_types__[fully_qualified] = cls
        cls.meta_type = fully_qualified


class Metanode(object):
    """
    Base Metanode class. All Metanodes should inherit from this class.
    """
    __metaclass__ = Register
    meta_version = 1
    events = dict()
    callbacks = dict()

    def __init__(self, node):
        """
        Wrap a PyMel node with the Metanode class.
        """
        if not hasattr(node, META_TYPE):
            raise Exception("{0} isn't a Metanode".format(node))

        meta_type = node.attr(META_TYPE).get()
        if meta_type != self.meta_type and meta_type not in META_TO_RELINK.keys():
            if meta_type not in Register.__meta_types__.keys():
                raise Exception('{0} has an invalid meta type of {1}'.format(node, meta_type))

            raise Exception('{0} is not of meta type {1}. It appears to be of type {2}'.format(
                node,
                self.meta_type,
                meta_type))

        self.node = node
        self.uuid = get_object_uuid(node)
        self.attr_user_event = '{0}_attrChanged'.format(self.uuid)
        self.name_user_event = '{0}_nameChanged'.format(self.uuid)

    def __repr__(self):
        return '{0}.{1}({2!r})'.format(self.__class__.__module__, self.__class__.__name__, self.name)

    def __eq__(self, other):
        if hasattr(other, 'name'):
            return self.name == other.name
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    @classmethod
    def create(cls, name):
        """
        Create a new Metanode.

        :param string name: The name for the created node.
        :return: Metanode class wrapping the newly created node.
        """
        network_node = pm.createNode(NODE_TYPE)
        network_node.rename(name)

        for coreAttrName, coreAttrArgs in cls.attr_core().iteritems():
            value = coreAttrArgs.pop('value')
            network_node.addAttr(coreAttrName, **coreAttrArgs)
            network_node.attr(coreAttrName).set(value)
            network_node.attr(coreAttrName).setLocked(True)

        for coreAttrName, coreAttrArgs in cls.attr_class().iteritems():
            network_node.addAttr(coreAttrName, **coreAttrArgs)

        return cls(network_node)

    @classmethod
    def attr_core(cls):
        """:return OrderedDict: The core attributes all Metanodes have."""
        return OrderedDict([
            (META_TYPE, {'dt': 'string', 'k': False, 'value': cls.meta_type}),
            (META_VERSION, {'at': 'short', 'value': cls.meta_version}),
            (LINEAL_VERSION, {'at': 'short', 'value': cls.calculate_lineal_version()})])

    @classmethod
    def attr_class(cls):
        """
        Set of attributes this Metaclass adds to its network node.

        :return dict: key is attribute name and value is attribute settings.
        """
        return {}

    def attr_dynamic(self):
        """
        Set of attributes that need to be serialized but were not available during creation.

        :return dict: key is attribute name and value is attribute settings.
        """
        return {}

    @classmethod
    def calculate_lineal_version(cls):
        """:return int: Step through resolution order to find total meta_version"""
        lineage = inspect.getmro(cls)
        version = 0
        for inherited_class in lineage:
            try:
                version += inherited_class.meta_version
            except AttributeError:
                pass
        return version

    @classmethod
    def scene_metanodes(cls):
        """
        :return list: Metanodes of cls type in open scene.
        """
        metas = [node for node in pm.ls(type=NODE_TYPE) if node.hasAttr(META_TYPE)]
        class_type = [cls(node) for node in metas if node.attr(META_TYPE).get() == cls.meta_type]
        return class_type

    def is_orphaned(self):
        """
        Override this in derived classes to define when a node is orphaned or stranded in
        the scene and is safe to be cleaned up
        """
        return False

    def _get_attr_data(self, attr_name):
        """
        Query the attribute dictionaries for an attribute's creation arguments.

        :return dict: dictionary of the attribute's creation kwargs.
        """
        attr_data = self.attr_class().get(attr_name)
        if attr_data is None:
            attr_data = self.attr_dynamic().get(attr_name)
            if attr_data is None:
                raise AttributeError(
                    "'{0}' is not a registered attribute on a Metanode of type {1}".format(attr_name, self.meta_type))
        return attr_data

    def get(self, attr_name):
        """
        Get the value of the given attribute. Attribute name must be registered in one of the attr dictionaries.
        Currently supports attributes of type message, string, bool, float, int, enum

        :param string attr_name: Name of attribute to get
        :return: List or single value representing attribute value
        """
        result = None
        # Get attribute data
        attr_data = self._get_attr_data(attr_name)
        # If multi: (return list)
        if attr_data.get('multi', False):
            # Data Type: MESSAGE
            if attr_data.get('at') == 'message':
                # Get connections
                result = pm.listConnections(self.node.attr(attr_name), d=False, s=True)
            # Data Type: STRING/BOOL/FLOAT/INT/ENUM
            else:
                # Get value
                result = list(self.node.attr(attr_name).get())
        # If not multi: (return single value)
        else:
            # Data Type: MESSAGE
            if attr_data.get('at') == 'message':
                # Get connections
                node = pm.listConnections(self.node.attr(attr_name), d=False, s=True)
                if node:
                    result = node[0]
            # Data Type: STRING/BOOL/FLOAT/INT/ENUM
            else:
                # Get value
                result = self.node.attr(attr_name).get()

                if attr_data.get('dt') == 'string':
                    # Empty strings come back as None instead of ''
                    if result is None:
                        result = ''
                elif attr_data.get('dt') == 'stringArray':
                    # Empty stringArrays come back as an empty list
                    if result is None:
                        result = []
        return result

    def set(self, attr_name, value):
        """
        Set the value of the given attribute. Attribute name must be registered in one of the attr dictionaries.
        Currently supports attributes of type message, string, bool, float, int, enum

        :param attr_name: Name of attribute to edit
        :param value: List or single value representing value of attribute to set
        """
        # Get attribute data
        attr_data = self._get_attr_data(attr_name)
        # If multi: (value should be list)
        if attr_data.get('multi', False):
            if not isinstance(value, (list, tuple)):
                raise ValueError(
                    "'{0}' is a multi attribute and must be set with a list or tuple of data".format(attr_name))
            # Data Type: MESSAGE
            if attr_data.get('at') == 'message':
                for attr_element in self.node.attr(attr_name):
                    pm.removeMultiInstance(attr_element, b=True)
                # Value should be list of PyNodes, we connect node.message to slot
                for index, item in enumerate(value):
                    pm.connectAttr(item.message, self.node.attr(attr_name)[index])
            # Data Type: STRING/BOOL/FLOAT/INT/ENUM
            else:
                for attr_element in self.node.attr(attr_name):
                    pm.removeMultiInstance(attr_element, b=True)
                for index, item in enumerate(value):
                    self.node.attr(attr_name)[index].set(item)
        # If not multi:
        else:
            # Data Type: MESSAGE
            if attr_data.get('at') == 'message':
                # Value should be a PyNode, we connect node.message to slot
                if value is not None:
                    pm.connectAttr(value.message, self.node.attr(attr_name))
                # If value is None, disconnect the current value
                else:
                    pm.disconnectAttr(self.node.attr(attr_name), inputs=True)
            # Data Type: STRING/BOOL/FLOAT/INT/ENUM
            else:
                self.node.attr(attr_name).set(value)

    def update(self, *args, **kwargs):
        """
        Update a metanode to the most recent version.

        :return: New Metanode, Dict mapping attributes from the old node that could not be found on the new one,
        along with their values and connections
        """
        missing_attributes = {}
        could_not_set = []
        name = self.name
        new_metanode = None
        try:
            # Rename this node.
            self.node.rename('updating__{0}'.format(name))
            # Create new node with old name.
            new_metanode = self.__class__.create(name, *args, **kwargs)
            # For each user defined attr:
            attr_list = self.node.listAttr(userDefined=True, multi=True) + [self.node.message]
            for attr in attr_list:
                if attr.type() != 'message':
                    data = attr.get()
                else:
                    data = None

                # Source connections are those incoming to the attr, destination are outgoing
                source = attr.listConnections(plugs=True, source=True, destination=False)
                destination = attr.listConnections(plugs=True, source=False, destination=True)
                connections = source, destination

                attr_name = attr.name(includeNode=False)
                # if attribute does not exist on new node
                if not new_metanode.node.hasAttr(attr_name):
                    # add to missingAttributes
                    missing_attributes[attr_name] = data, connections
                    # Sometimes network nodes connected to other network nodes just disappear when those
                    # nodes are deleted. Disconnect them first to avoid that
                    for sAttr in source:
                        pm.disconnectAttr(sAttr, attr)
                    for dAttr in destination:
                        pm.disconnectAttr(attr, dAttr)
                else:
                    # Copy data values from old node to new.
                    if data is not None:
                        try:
                            if new_metanode.node.attr(attr_name).isLocked():
                                if not attr_name == META_VERSION and not attr_name == LINEAL_VERSION:
                                    pm.setAttr(attr_name, lock=False)
                                    new_metanode.set(attr_name, data)
                                    pm.setAttr(attr_name, lock=True)
                            else:
                                new_metanode.set(attr_name, data)
                        except RuntimeError:
                            could_not_set.append((attr_name, data))
                    # reconnect connections from old node to new
                    for sAttr in source:
                        pm.disconnectAttr(sAttr, attr)
                        pm.connectAttr(sAttr, new_metanode.node.attr(attr_name))
                    for dAttr in destination:
                        pm.disconnectAttr(attr, dAttr)
                        pm.connectAttr(new_metanode.node.attr(attr_name), dAttr)
            pm.delete(self.node)
        except Exception as exc:
            print exc
            print exc.message

            # If something went wrong part way through the update roll back to the original node state
            if new_metanode is not None:
                pm.delete(new_metanode.node)
            self.node.rename(name)
            raise

        return new_metanode, missing_attributes, could_not_set

    def serialize_attr(self, attr_name):
        """
        Returns a serialized format for the given attribute
        This behavior can be customized for some or all attributes by inherited classes
        The default return dictionary looks like this:
          {'name': 'fooAttr',
           'type': 'message',
           'value': 'barNode'}

        :param string attr_name: The attribute to retrieve data for
        :return: dict of attribute information
        """
        attr_data = self._get_attr_data(attr_name)
        data_type = attr_data.get('at') or attr_data.get('dt')
        value = self.get(attr_name)
        if data_type == 'message':
            if value is not None:
                # Message attr values are PyNodes, query name for serialization
                if attr_data.get('multi', False):
                    value = [item.name() for item in value]
                else:
                    value = value.name()

        return {'name': attr_name, 'type': data_type, 'value': value}

    def deserialize_attr(self, data):
        """
        Sets an attribute using a given serialized dict of data (generated by serialize_attr)
        This behavior can be customized for some or all attributes by inherited classes

        :param data: The dict of data to be used to set attribute(s)
        """
        if not data:
            return

        value = data.get('value')
        if data.get('type') == 'message':
            if value is not None:
                # Message attribute values should be PyNodes, but are serialized as the node name
                # If multi attribute, value will be a list
                if isinstance(value, (list, tuple)):
                    new_value = []
                    for i, v in enumerate(value):
                        try:
                            new_value.append(pm.PyNode(v))
                        except pm.MayaNodeError:
                            # Node does not exist, attribute cannot be set
                            pm.warning(
                                "Element {0} of multi attribute '{1}' cannot be set, node '{2}' does not exist".format(
                                    i, data.get('name'), v))
                    value = new_value
                else:
                    try:
                        value = pm.PyNode(value)
                    except pm.MayaNodeError:
                        # Node does not exist, attribute cannot be set
                        pm.warning("Attribute '{0}' cannot be set, node '{1}' does not exist".format(
                            data.get('name'), value))
                        return
        # This call will fail and raise AttributeError if attrName is not registered in __attr__ or __dynamic_attr__
        self.set(data.get('name'), value)

    def serialize(self, json_format=True):
        """
        Create a serialized representation of this node.

        :param bool json_format: formats serialized data as json
        :return: Serialized representation of this node
        """
        result = {'name': self.name, 'meta_type': self.meta_type, 'version': (self.node_version, self.node_lineal)}

        attributes = []
        for attrName in self.attr_class():
            serialized = self.serialize_attr(attrName)
            if serialized:
                attributes.append(serialized)
        result['attr'] = attributes

        dynamic_attr = []
        for attrName in self.attr_dynamic():
            serialized = self.serialize_attr(attrName)
            if serialized:
                dynamic_attr.append(serialized)
        result['dynamic_attr'] = dynamic_attr

        return json.dumps(result) if json_format else result

    def created_event(self):
        '''
        Create user events for attribute changes and node renames.
        '''
        sel_list = om2.MSelectionList()
        sel_list.add(self.node.name())
        m_obj = sel_list.getDependNode(0)
        if self.uuid not in self.events:
            # Attribute
            attribute_callback = om2.MNodeMessage.addAttributeChangedCallback(m_obj, self._attribute_changed)
            om2.MUserEventMessage.registerUserEvent(self.attr_user_event)
            # Name
            name_callback = om2.MNodeMessage.addNameChangedCallback(m_obj, self._name_changed)
            om2.MUserEventMessage.registerUserEvent(self.name_user_event)

            self.events[self.uuid] = {self.attr_user_event, self.name_user_event}
            self.callbacks[self.uuid] = {attribute_callback, name_callback}

    def deleted_event(self):
        '''
        Delete all callbacks of associated node.
        '''
        for callback in self.callbacks[self.uuid]:
            om2.MMessage.removeCallback(callback)
        self.callbacks.pop(self.uuid, None)
        for event in self.events[self.uuid]:
            om2.MUserEventMessage.deregisterUserEvent(event)
        self.events.pop(self.uuid, None)

    def _attribute_changed(self, attribute_message, plug_dst, plug_scr, *args):
        # Message attribute edits
        if attribute_message & om2.MNodeMessage.kOtherPlugSet:
            input_uuid = om2.MFnDependencyNode(plug_scr.node()).uuid()
            if plug_dst.isElement:
                plug_dst = plug_dst.array()
            if attribute_message & om2.MNodeMessage.kConnectionMade:
                om2.MUserEventMessage.postUserEvent(self.attr_user_event,
                                                    (self.uuid, plug_dst.partialName(), input_uuid, True))
            elif attribute_message & om2.MNodeMessage.kConnectionBroken:
                om2.MUserEventMessage.postUserEvent(self.attr_user_event,
                                                    (self.uuid, plug_dst.partialName(), input_uuid, False))
        # Data attribute edits
        elif attribute_message & om2.MNodeMessage.kAttributeSet:
            dst_attribute = plug_dst.attribute()
            dst_type = dst_attribute.apiType()
            if plug_dst.isElement:
                attr_name = plug_dst.array().partialName()
                index = plug_dst.logicalIndex()
            else:
                attr_name = plug_dst.partialName()
                index = None
            if dst_type == om2.MFn.kTypedAttribute:
                attr_type = om2.MFnTypedAttribute(dst_attribute).attrType()
                if attr_type == om2.MFnData.kString:
                    om2.MUserEventMessage.postUserEvent(self.attr_user_event,
                                                        (self.uuid, attr_name, plug_dst.asString(), index))
                elif attr_type == om2.MFnData.kStringArray:
                    data_object = plug_dst.asMDataHandle().data()
                    string_array = om2.MFnStringArrayData(data_object)
                    om2.MUserEventMessage.postUserEvent(self.attr_user_event,
                                                        (self.uuid, attr_name, string_array.array(), index))
            elif dst_type == om2.MFn.kNumericAttribute:
                dstUnitType = om2.MFnNumericAttribute(dst_attribute).numericType()
                if dstUnitType == om2.MFnNumericData.kBoolean:
                    om2.MUserEventMessage.postUserEvent(self.attr_user_event,
                                                        (self.uuid, attr_name, plug_dst.asBool(), index))
                elif dstUnitType in {om2.MFnNumericData.kFloat, om2.MFnNumericData.kDouble, om2.MFnNumericData.kAddr}:
                    om2.MUserEventMessage.postUserEvent(self.attr_user_event,
                                                        (self.uuid, attr_name, plug_dst.asDouble(), index))
                elif dstUnitType in {om2.MFnNumericData.kShort, om2.MFnNumericData.kInt,
                                     om2.MFnNumericData.kLong, om2.MFnNumericData.kByte}:
                    om2.MUserEventMessage.postUserEvent(self.attr_user_event,
                                                        (self.uuid, attr_name, plug_dst.asShort(), index))

    def _name_changed(self, *args):
        om2.MUserEventMessage.postUserEvent(self.name_user_event, (self.uuid, args[1], self.name))

    def subscribe_attr(self, func):
        '''
        Subscribe function to attribute changes. The data will come back as a tuple when changes are made.
        Message attribute changes will be;
        (meta_uuid(unicode), attribute_name(unicode), connected_node_uuid(unicode), connectionState(bool))
        while data attributes will be;
        (meta_uuid(unicode), attribute_name(unicode), new_value(attribute type), index(int or None)).

        :param func: function to call when attributes updated.
        :return long: Index reference to callback.
        '''
        index = om2.MUserEventMessage.addUserEventCallback(self.attr_user_event, func)
        self.callbacks[self.uuid].add(index)
        return self.uuid, index

    def subscribe_name(self, func):
        '''
        Subscribe function to node name changes. The data will be;
        (meta_uuid(unicode), old_name(unicode), new_name(unicode))

        :param func: function to call when name changes
        :return long: index reference to callback that can be used with unsubscribe call.
        '''
        index = om2.MUserEventMessage.addUserEventCallback(self.name_user_event, func)
        self.callbacks[self.uuid].add(index)
        return self.uuid, index

    @classmethod
    def unsubscribe(cls, callback_data):
        '''
        Remove callback for subscribed event.

        :param tuple callback_data: UUID and Index identifier for callback to remove.
        '''
        uuid, index = callback_data
        if uuid in cls.callbacks:
            cls.callbacks[uuid].remove(index)
            om2.MMessage.removeCallback(index)

    @property
    def name(self):
        """:return string: Name of the network node."""
        return self.node.name()

    @property
    def node_version(self):
        """:return int: Node's version value."""
        if self.node.hasAttr(META_VERSION):
            return self.node.attr(META_VERSION).get()
        return -1

    @property
    def node_lineal(self):
        """:return int: Node's linealVersion value."""
        if self.node.hasAttr(LINEAL_VERSION):
            return self.node.attr(LINEAL_VERSION).get()
        return -1

    @classmethod
    def changelog(cls):
        """
        Implement this in derived classes to return a description of changes to the
        Metanode when incrementing the version.

        :return: Dict mapping versions to change descriptions
        """
        return {1: 'Creation of Metanode class.'}


class SingletonMetanode(Metanode):
    """
    The base class for singleton Metanodes. Classes inherit from this if they wish to be
    the only instance of a particular metanode in the scene.
    """
    meta_version = 1

    @classmethod
    def instance(cls):
        """
        Controls access to the metanode type by returning one common instance of the node
        """
        nodes = cls.scene_metanodes()
        if nodes:
            if pm.objExists(cls.__name__):
                metanode = cls(pm.PyNode(cls.__name__))
            else:
                metanode = nodes[0]
        else:
            metanode = cls.create(cls.__name__)
        return metanode

    @classmethod
    def create(cls):
        return cls.super(SingletonMetanode, cls).create(cls.__name__)


def get_metanode(node, *args, **kwargs):
    """
    By passing a network node with a meta type attribute, a Metanode instance will
    be returned of the appropriate meta type.

    :param pm.PyNode() node: a Maya network node with a meta type attribute
    :return: A subclass of Metanode of the type set on the network node.
    """
    if isinstance(node, basestring):
        node = pm.PyNode(node)
    if not pm.hasAttr(node, META_TYPE):
        raise Exception("{0} isn't a Metanode".format(node))
    meta_type = node.attr(META_TYPE).get()
    if meta_type not in Register.__meta_types__.keys():
        raise Exception("{0} has an invalid meta type of {1}".format(node, meta_type))

    return Register.__meta_types__[meta_type](node, *args, **kwargs)


def get_scene_metanodes():
    """
    Get Dictionary of registered meta types with a list of the associated metanodes that exist in the scene.

    :return: Dictionary with every registered meta type as key with scene metanodes in lists.
    """
    class_dictionary = Register.__meta_types__
    meta_dictionary = dict([(registerType, []) for registerType in class_dictionary])
    for node in pm.ls(type=NODE_TYPE):
        if pm.hasAttr(node, META_TYPE):
            meta_type = node.attr(META_TYPE).get()
            if meta_type in meta_dictionary:
                metanode = class_dictionary[meta_type](node)
                meta_dictionary[meta_type].append(metanode)
    return meta_dictionary


def deserialize_metanode(data, node=None, json_format=True, verify_version=True, *args, **kwargs):
    """
    Deserialize the given serialized data into a Metanode.

    :param data: Serialized node data.
    :param PyNode node: The serialized data will be applied to the given network node. If None,
    a new node will be created. Note that if a node is given, its name and attribute values
    may be altered.
    :param bool json_format: If true the data will be loaded from JSON.
    :param bool verify_version: Check if data version matches current Metanode.
    :return: Deserialized Metanode
    """
    if json_format:
        data = json.loads(data)

    meta_type = data['meta_type']
    # Get the appropriate metanode class for the serialized data, and let that class handle the
    # deserialization process
    metanode_class = Register.__meta_types__.get(meta_type)

    if metanode_class is None:
        raise ValueError("Given serialized data specifies an unregistered meta type of {0}".format(meta_type))

    # If for a singleton metanode, ignore the given network node and deserialize onto the singleton class instance
    if issubclass(metanode_class, SingletonMetanode):
        metanode = metanode_class.instance()
    # Regular metanodes need to either use the given node or create a new one
    else:
        node_name = data['name']
        # If node is not none, do not create new node, just load data onto existing node
        # Note: For this to work for every Metanode class, each class' `create` function must
        # be able to be called with only `name` as an argument.
        if node is None:
            metanode = metanode_class.create(node_name, *args, **kwargs)
        else:
            # Ensure network node is of same meta types as metaclass, version up to date, etc
            node.rename(node_name)
            metanode = metanode_class(node)

    if verify_version:
        version, lineal_version = data['version']
        if metanode.node_version != version or metanode.node_lineal != lineal_version:
            pm.warning("Serialized data's version is inconsistent with current version of metanode class {0}".format(
                metanode_class.__name__))

    for attr_data in data['attr']:
        metanode.deserialize_attr(attr_data)

    if data['dynamic_attr']:
        for attr_name, attr_args in metanode.attr_dynamic.iteritems():
            metanode.node.addAttr(attr_name, **attr_args)
        for dynamic_data in data['dynamic_attr']:
            metanode.deserialize_attr(dynamic_data)

    return metanode


def get_object_uuid(node):
    """Get PyNode UUID value as string."""
    sel_list = om2.MSelectionList()
    sel_list.add(node.name())
    m_obj = sel_list.getDependNode(0)
    return om2.MFnDependencyNode(m_obj).uuid().asString()

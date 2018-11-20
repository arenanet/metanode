"""
Base classes and functions for creating new Metanode classes.
"""

from collections import OrderedDict
from config import META_TO_RELINK
import inspect

import pymel.core as pm

NODE_TYPE = 'network'
META_TYPE = 'metaType'
META_VERSION = 'metaVersion'
LINEAL_VERSION = 'linealVersion'


class Register(type):
    __meta_types__ = {}

    def __init__(cls, *args, **kwargs):
        fully_qualified = cls.__module__ + '.' + cls.__name__
        cls.__class__.__meta_types__[fully_qualified] = cls
        cls.meta_type = fully_qualified


class Metanode(object):
    """
    Base Metanode class. All Metanodes should inherit from this class.
    """
    __metaclass__ = Register
    meta_version = 1

    def __init__(self, node):
        """
        Wrap a PyMel node with the Metanode class.
        """
        if not hasattr(node, META_TYPE):
            raise Exception("{0} isn't a Metanode".format(node))

        if node.attr(META_TYPE).get() != self.meta_type and node.attr(META_TYPE).get() not in META_TO_RELINK.keys():
            if node.attr(META_TYPE).get() not in Register.__meta_types__.keys():
                raise Exception('{0} has an invalid meta type of {1}'.format(node, node.attr(META_TYPE).get()))

            raise Exception('{0} is not of meta type {1}. It appears to be of type {2}'.format(
                node,
                self.meta_type,
                node.attr(META_TYPE).get()))

        self.node = node

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

        :param string name:
        :return:
        """
        network_node = pm.createNode(NODE_TYPE)
        network_node.rename(name)

        for coreAttrName, coreAttrArgs in cls.__core_attr__().iteritems():
            value = coreAttrArgs.pop('value')
            network_node.addAttr(coreAttrName, **coreAttrArgs)
            network_node.attr(coreAttrName).set(value)
            network_node.attr(coreAttrName).setLocked(True)

        for coreAttrName, coreAttrArgs in cls.__attr__().iteritems():
            network_node.addAttr(coreAttrName, **coreAttrArgs)

        return cls(network_node)

    @classmethod
    def __core_attr__(cls):
        """:return OrderedDict: The core attributes all Metanodes have."""
        return OrderedDict([
            (META_TYPE, {'dt': 'string', 'k': False, 'value': cls.meta_type}),
            (META_VERSION, {'at': 'short', 'value': cls.meta_version}),
            (LINEAL_VERSION, {'at': 'short', 'value': cls.calculate_lineal_version()})])

    @classmethod
    def __attr__(cls):
        """
        Set of attributes this Metaclass adds to its network node.

        :return dict: key is attribute name and value is attribute settings.
        """
        return {}

    @classmethod
    def __dynamic_attr__(cls):
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

    def _get_attr_data(self, attr_name):
        '''
        Query the attribute dictionaries for an attribute's creation arguments.

        :return dict: dictionary of the attribute's creation kwargs.
        '''
        attr_data = self.__attr__().get(attr_name)
        if attr_data is None:
            attr_data = self.__dynamic_attr__().get(attr_name)
            if attr_data is None:
                raise AttributeError(
                    "'{0}' is not a registered attribute on a Metanode of type {1}".format(attr_name, self.meta_type))
        return attr_data

    def get(self, attr_name):
        '''
        Get the value of the given attribute. Attribute name must be registered in one of the attr dictionaries.
        Currently supports attributes of type message, string, bool, float, int, enum

        :param string attr_name: Name of attribute to get
        :return: List or single value representing attribute value
        '''
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
        '''
        Set the value of the given attribute. Attribute name must be registered in one of the attr dictionaries.
        Currently supports attributes of type message, string, bool, float, int, enum

        :param attr_name: Name of attribute to edit
        :param value: List or single value representing value of attribute to set
        '''
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

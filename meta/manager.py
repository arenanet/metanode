"""Manager class for storing and updating Metanodes."""

import maya.api.OpenMaya as om2
import pymel.core as pm

from meta.config import *
import meta.core


class MetanodeManager(object):
    """
    Manager class for storing state, and managing updates with recognized Metanodes in a scene.
    """
    meta_dict, network_nodes, relink, singleton, orphaned, update, deprecated = {}, [], [], [], [], [], []
    created_m_objs = []

    def __init__(self):
        self.update_network_nodes()

    @classmethod
    def node_created_callback(cls, m_obj, _):
        """
        Catches all network nodes that are created. Defer evaluates network node with metanode_created_callback
        so that network nodes have time to be inited as metas.

        :param m_obj: MObject for created network node.
        :param _: Extra argument passed from create event.
        :return:
        """
        cls.created_m_objs.append(m_obj)
        pm.evalDeferred('meta.manager.MetanodeManager._check_created_node()')

    @classmethod
    def _check_created_node(cls):
        """
        Catches all network nodes that are meta types. If they aren't in the meta dictionary they will be added.
        Should only apply to copied meta nodes and imported meta nodes as they dont go through the normal meta node
        create function. Always runs deferred, therefore this will not reliably catch metas from a batch process.
        If this is needed look at using update_meta_dictionary from your batch (scene load/new will also run
        update_meta_dictionary).
        """
        m_obj = cls.created_m_objs.pop(0)
        m_objs_uuid = om2.MFnDependencyNode(m_obj).uuid()
        if m_objs_uuid.valid():
            uuid = m_objs_uuid.asString()
            nodes = pm.ls(uuid)
            if nodes:
                if pm.hasAttr(nodes[0], META_TYPE):
                    if nodes[0].attr(META_TYPE).get() in meta.core.Register.__meta_types__.keys():
                        metanode_class = meta.core.Register.__meta_types__[nodes[0].attr(META_TYPE).get()]
                        if all(metanode.uuid != uuid for metanode in cls.meta_dict.get(metanode_class.meta_type, [])):
                            if metanode_class.meta_type not in cls.meta_dict:
                                cls.meta_dict[metanode_class.meta_type] = []
                            new_meta = metanode_class(nodes[0])
                            cls.meta_dict[metanode_class.meta_type].append(new_meta)
                            new_meta.created_event()

    @classmethod
    def node_deleted_callback(cls, m_obj, _):
        """
        Delete events created for any Metanode that is deleted.

        :param m_obj: MObject for deleted network node.
        :param _: Extra argument passed from delete event.
        """
        uuid = om2.MFnDependencyNode(m_obj).uuid().asString()
        for key, value in cls.meta_dict.iteritems():
            for metanode in value:
                if metanode.uuid == uuid:
                    value.remove(metanode)
                    metanode.deleted_event()
                    break

    @classmethod
    def update_meta_dictionary(cls):
        """
        Updates meta dictionary with any meta nodes found in scene, not yet in the dictionary. Runs when scene loads.
        Should only need to be run when normal metanodeCreatedCallback cant catch a new meta node.
        This can happen when differed events aren't processed such as in a batch file open with an import
         of meta nodes from another file.
        """
        update_meta_dictionary = meta.core.get_scene_metanodes()
        for update_meta_type, updateMetaList in update_meta_dictionary.iteritems():
            cls.meta_dict.setdefault(update_meta_type, [])
            for updateMeta in updateMetaList:
                if all(updateMeta.uuid != metanode.uuid for metanode in cls.meta_dict[update_meta_type]):
                    cls.meta_dict[update_meta_type].append(updateMeta)
                    updateMeta.created_event()

    @classmethod
    def update_network_nodes(cls):
        cls.network_nodes = [node for node in pm.ls(type=NODE_TYPE) if pm.hasAttr(node, META_TYPE)]

    @classmethod
    def get_invalid_nodes(cls):
        """
        Check all lists for nodes to fix.
        """
        return cls.relink + cls.singleton + cls.orphaned + cls.update + cls.deprecated

    def validate_metanodes(self):
        """
        Query metaDictionary and networkNodes for nodes to fix. This only gathers the nodes without fixing them.
        """
        self.get_relink()
        self.get_extra_singletons()
        self.get_orphaned()
        self.get_nodes_to_update()
        self.get_deprecated()

    def recursive_metanode_fix(self):
        """
        Call fixMetanodes then validateMetanodes until all issues are caught.
        """
        msg = ''
        while self.get_invalid_nodes():
            msg += self.fix_metanodes()
            self.validate_metanodes()
        return msg

    def fix_metanodes(self):
        """
        Execute all fix functions on gathered Metanodes.
        """
        msg = ''
        if self.relink:
            msg += self.update_relink()
        if self.singleton:
            msg += self.delete_extra_singletons()
        if self.orphaned:
            msg += self.delete_orphaned()
        if self.update:
            msg += self.update_metanodes()
        if self.deprecated:
            msg += self.delete_deprecated_meta_types()
        return msg

    @classmethod
    def _delete_metas(cls, metanodes, message_base):
        """
        Delete passed Metanodes and return message.

        :param list metanodes: list of meta classes
        :param string message_base: Message about why the Metanode was deleted
        :return string: Description of Metanodes deleted.
        """
        message = ''
        for metanode in reversed(metanodes):
            metanodes.remove(metanode)
            cls.network_nodes.remove(metanode.node)
            message += '{0}: {1}\n'.format(message_base, metanode.name)
            pm.lockNode(metanode.node, lock=False)
            pm.disconnectAttr(metanode.node)
            pm.delete(metanode.node)
        return message

    @classmethod
    def _delete_nodes(cls, nodes, message_base):
        """
        Delete passed nodes and return message.

        :param list nodes: list of network nodes
        :param string message_base: Message about why the node was deleted
        :return string: Description of nodes deleted.
        """
        message = ''
        for node in reversed(nodes):
            cls.network_nodes.remove(node)
            message += '{0}: {1}\n'.format(message_base, node.name())
            pm.lockNode(node, lock=False)
            pm.disconnectAttr(node)
            pm.delete(node)
            nodes.remove(node)
        return message

    # RELINK
    @classmethod
    def get_relink(cls):
        """
        Check network nodes for meta types to relink.
        """
        relink_dict = META_TO_RELINK
        for oldType, newType in relink_dict.iteritems():
            cls.relink = [node for node in cls.network_nodes if node.attr(META_TYPE).get() == oldType]

    @classmethod
    def update_relink(cls):
        """
        Iterate through cls.relink to relink meta types that have been moved or renamed.

        :return: String of relinked meta
        """
        relink_message = ''
        relink_dict = META_TO_RELINK
        for item in list(cls.relink):
            relink_message += 'Relinked outdated Metanode: {0}\n'.format(item.name())
            item.attr(META_TYPE).unlock()
            item.attr(META_TYPE).set(relink_dict[item.attr(META_TYPE).get()])
            item.attr(META_TYPE).lock()
            cls.relink.remove(item)
        return relink_message

    # Extra SINGLETON
    @classmethod
    def get_extra_singletons(cls):
        """
        Collect extra singleton nodes that are not the recognized instance.
        """
        cls.singleton = []
        class_dictionary = meta.core.Register.__meta_types__
        for meta_type in cls.meta_dict:
            if issubclass(class_dictionary[meta_type], meta.core.SingletonMetanode):
                if len(cls.meta_dict[meta_type]) > 1:
                    instance_meta = class_dictionary[meta_type].instance()
                    for singleton in cls.meta_dict[meta_type]:
                        if singleton.node != instance_meta.node:
                            cls.singleton.append(singleton)

    @classmethod
    def delete_extra_singletons(cls):
        """
        Delete any extra singleton nodes.

        :return string: message about what nodes were deleted
        """
        return cls._delete_metas(cls.singleton, 'Deleted duplicate singleton Metanode')

    # ORPHANED
    @classmethod
    def get_orphaned(cls):
        """
        Collect metanodes in the metaDictionary that are orphaned.
        """
        cls.orphaned = []
        for meta_type in cls.meta_dict:
            for metaNode in cls.meta_dict[meta_type]:
                if metaNode.is_orphaned():
                    cls.orphaned.append(metaNode)

    @classmethod
    def delete_orphaned(cls):
        """
        Delete all nodes in the cls.orphaned list.

        :return string: message about what Metanodes were deleted
        """
        return cls._delete_metas(cls.orphaned, 'Deleted orphaned Metanode')

    # UPDATE
    @classmethod
    def get_nodes_to_update(cls, force=False):
        """
        Find meta nodes with meta types in META_TO_CHECK that should be updated.

        :param force: force all Metanodes to be added
        :return: list of meta nodes to update
        """
        cls.update = []
        for meta_type in META_TO_CHECK:
            if not len(cls.meta_dict.get(meta_type, [])):
                continue
            for metanode in cls.meta_dict[meta_type]:
                if metanode.node.attr(META_TYPE).get() != meta_type:
                    cls.update.append(metanode)
                elif metanode.linealVersion() < metanode.calculateLinealVersion() or force:
                    cls.update.append(metanode)

    @classmethod
    def update_metanodes(cls):
        """
        Call .update() on all metanodes in cls.update and return update messages.
        """
        update_message = ''
        for metanode in reversed(cls.update):
            cls.update.remove(metanode)
            if pm.objExists(metanode.node):
                cls.network_nodes.remove(metanode.node)
                new, missing, could_not_set = metanode.update()
                if new:
                    cls.network_nodes.append(new.node)
                    update_message += 'Updating Metanode: {0}\n'.format(new)
                if missing:
                    update_message += 'New Metanode lacks previous attributes: {0}'.format(missing)
                if could_not_set:
                    update_message += 'Could not set attributes: {0}'.format(could_not_set)

        return update_message

    # DEPRECATED
    @classmethod
    def get_deprecated(cls):
        """
        Find meta nodes with meta types in META_TO_REMOVE that should be deleted and add them to cls.deprecated
        """
        deprecated_types = META_TO_REMOVE
        cls.deprecated = [node for node in cls.network_nodes if node.attr(META_TYPE).get() in deprecated_types]

    @classmethod
    def delete_deprecated_meta_types(cls):
        """
        Delete nodes in cls.deprecated and return a message of all deleted nodes.
        """
        return cls._delete_nodes(cls.deprecated, 'Deleted deprecated Metanode')


def metanode_refresh():
    """Call on scene start to update the MetanodeManager and check for invalid Metanodes."""
    manager = MetanodeManager()
    manager.update_meta_dictionary()
    manager.validate_metanodes()
    if manager.get_invalid_nodes():
        manager.recursive_metanode_fix()


metanode_refresh()

# Catch imported nodes
postImportCallback = om2.MSceneMessage.addCallback(om2.MSceneMessage.kAfterImport, metanode_refresh)

# Callbacks fired when network nodes are created and deleted to catch metanodes
networkNodeCreatedCallback = om2.MDGMessage.addNodeAddedCallback(MetanodeManager.node_created_callback, 'network')
networkNodeDeletedCallback = om2.MDGMessage.addNodeRemovedCallback(MetanodeManager.node_deleted_callback, 'network')

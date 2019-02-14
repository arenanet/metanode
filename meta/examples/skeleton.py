import json

import pymel.core as pm

import meta.core

attr_bind_pose = 'bindPose'
attr_zero_pose = 'zeroPose'
attr_root = 'root'
attr_no_bind = 'noBindJoints'
attr_no_export = 'noExportJoints'


class Skeleton(meta.core.Metanode):
    '''
    A Metanode for saving skeletons.
    '''
    metaversion = 1

    @classmethod
    def attr_class(cls):
        return {attr_bind_pose: {'dt': 'string'},
                attr_zero_pose: {'dt': 'string'},
                attr_root: {'at': 'message'},
                attr_no_bind: {'at': 'message', 'multi': True},
                attr_no_export: {'at': 'message', 'multi': True}}

    def store_bind_pose(self):
        '''
        Captures the current skeleton pose as the bind pose on the network node
        '''
        pose = json.dumps(get_pose(self.root))
        self.node.attr(attr_bind_pose).set(pose)

    def store_zero_pose(self):
        '''
        Captures the current skeleton pose as the zero pose on the network node
        '''
        pose = json.dumps(get_pose(self.root))
        self.node.attr(attr_zero_pose).set(pose)

    def apply_bind_pose(self):
        '''
        Sets skeleton to pose saved in bind pose attribute.
        '''
        pose = json.loads(self.get(attr_bind_pose))
        if pose:
            set_pose(pose)

    def apply_zero_pose(self):
        '''
        Sets skeleton to pose saved in zero pose attribute.
        '''
        pose = json.loads(self.get(attr_zero_pose))
        if pose:
            set_pose(pose)

    def append_no_bind(self, joints):
        '''
        Connects the helper joints to the network node.

        :param list joints: a list of helper joints to connect to the network node
        '''
        self.set(set(self.get(attr_no_bind) + joints), attr_no_bind)

    def append_no_export(self, joints):
        '''
        Connects the helper joints to the network node.

        :param list joints: a list of helper joints to connect to the network node
        '''
        self.set(set(self.get(attr_no_export) + joints), attr_no_export)

    def remove_no_bind(self, joints):
        '''
        Remove joints from the list of noBindJoints currently connected to the network node

        :param list joints: a list of helper joints to disconnect from the network node
        '''
        current = self.get(attr_no_bind)
        for joint in joints:
            if joint in current:
                current.remove(joint)
        self.set(joints, attr_no_bind)

    def remove_no_export(self, joints):
        '''
        Remove joints from the list of noExportJoints currently connected to the network node

        :param list joints: a list of noExportJoints to disconnect from the network node
        '''
        current = self.get(attr_no_export)
        for joint in joints:
            if joint in current:
                current.remove(joint)
        self.set(joints, attr_no_export)

    @property
    def root(self):
        '''
        :return: The root of the skeleton.
        '''
        return self.get(attr_root)

    @root.setter
    def root(self, root_joint):
        '''
        Connect the root attribute on the network node to the specified root joint

        :param PyNode root_joint: the joint to set as the root of the skeleton
        '''
        self.set(attr_root, root_joint)


def get_pose(root):
    data = []
    stack = [root]
    while stack:
        jnt = stack.pop()
        translate = pm.xform(jnt, q=True, translation=True, ws=True)
        rotate = pm.xform(jnt, q=True, rotation=True, ws=True)
        data.append((jnt.name(), translate, rotate))
        stack.extend(pm.listRelatives(jnt, type='joint'))
    return data


def set_pose(data):
    for jntName, t, r in data:
        if pm.uniqueObjExists(jntName):
            jnt = pm.PyNode(jntName)
        elif pm.uniqueObjExists(jntName[1:]):
            jnt = pm.PyNode(jntName[1:])
        else:
            print pm.warning('No joint found for {0}'.format(jntName))
            continue
        pm.xform(jnt, translation=t, ws=True)
        pm.xform(jnt, rotation=r, ws=True)

from collections import OrderedDict

import pymel.core as pm

import meta.core

attr_rig_components = 'rigComponents'
attr_rig = 'rig'
attr_rig_group = 'rigGroup'
attr_built = 'isBuild'
attr_socket = 'socket'
attr_component_group = 'componentGroup'
attr_controls = 'controls'
attr_bind = 'bindJoints'
attr_start_joint = 'startJoint'
attr_end_joint = 'endJoint'


class Rig(meta.core.Metanode):
    meta_version = 1

    @classmethod
    def attr_class(cls):
        return {attr_rig_components: {'at': 'message', 'multi': True},
                attr_rig_group: {'at': 'message'}}

    def add_component(self, new_component):
        '''
        Add a component to the rig component.

        :param new_component: a rig component that will be a part of the rig
        '''
        components = self.components
        components.append(new_component)
        component_nodes = [component.node for component in components]
        component_nodes = list(set(component_nodes))
        self.set(attr_rig_components, component_nodes)

        new_component.rig = self

    def build_rig(self):
        rig_group = pm.group(em=True, n=self.name + '_rig_group')
        lock_transforms(rig_group)
        hide_transforms(rig_group)
        self.set(attr_rig_group, rig_group)

        for component in self.components:
            component.build()

    def demolish_rig(self):
        for component in self.components:
            component.demolish()
        pm.delete(self.get(attr_rig_group))

    @property
    def components(self):
        nodes = self.get(attr_rig_components)
        components = list()
        for node in nodes:
            components.append(meta.core.get_metanode(node))
        return components


class Component(meta.core.Metanode):
    meta_version = 1

    attr_common = {
        attr_rig: {'at': 'message'},
        attr_built: {'at': 'bool', 'dv': False},
        attr_socket: {'at': 'message'},
        attr_component_group: {'at': 'message'},
        attr_controls: {'at': 'message', 'multi': True},
        attr_bind: {'at': 'message', 'multi': True}}

    attr_build = OrderedDict([])

    @classmethod
    def attr_class(cls):
        attrs = OrderedDict([])
        attrs.update(cls.attr_common)
        attrs.update(cls.attr_build)
        return attrs

    def build(self):
        '''
        Call to build individual component which requires the component not be built.
        '''
        if not self.built and self.valid():
            if self.bind_joints:
                pm.cutKey(self.bind_joints)
            self._create_rig()
            self.built = True

    def _create_rig(self):
        '''
        Component subclasses should implement this method. This handles the
        creation of the component in Maya which is highly specific to each component.

        The general outline of this method:
            -create group for component in Maya
            -build the controls and parts to get the specific rig component behaviour
            -lock and hide extraneous attributes from the channel box
            -connect built pieces to the network node for easy access through the metanode
            -call super to set the isBuilt attribute to True and generate animation control shapes
        '''
        pass

    def demolish(self):
        '''
        Tear down control. First stores the control shapes, then deletes the group
        holding the rig controls and unused control materials. Finally, sets the isBuilt
        flag to False
        '''
        if self.built:
            pm.delete(self.component_group)
            self.built = False

    def reset_controls(self):
        '''
        Zero out all controls, such that they are all reset to the position they
        were during rig creation, and all bind joints are in skeleton zeropose.
        '''
        for control in self.controls:
            for attr in ('{0}{1}'.format(at, ax) for at in 'tr' for ax in 'xyz'):
                control.attr(attr).set(0)
            for attr in 'sx sy sz'.split():
                control.attr(attr).set(1)

    def valid(self):
        return True

    @property
    def rig(self):
        return Rig(self.get(attr_rig))

    @rig.setter
    def rig(self, rig_meta):
        self.set(attr_rig, rig_meta.node)

    @property
    def bind_joints(self):
        return self.get(attr_bind)

    @bind_joints.setter
    def bind_joints(self, joints):
        self.set(attr_bind, joints)

    @property
    def controls(self):
        return self.get(attr_bind)

    @controls.setter
    def controls(self, joints):
        self.set(attr_bind, joints)

    @property
    def component_group(self):
        return self.get(attr_component_group)

    @component_group.setter
    def component_group(self, joints):
        self.set(attr_component_group, joints)

    @property
    def built(self):
        return self.get(attr_built)

    @built.setter
    def built(self, state):
        self.set(attr_built, state)


class FK(Component):
    meta_version = 1

    attr_build = OrderedDict([
        (attr_start_joint, {'at': 'message'}),
        (attr_end_joint, {'at': 'message'})])

    def _create_rig(self):
        start = self.get(attr_start_joint)
        end = self.get(attr_end_joint)
        socket = self.get(attr_socket)

        component_group = pm.group(em=True, n=self.name + '_component')
        if socket:
            copy_transforms(socket, component_group)
            pm.pointConstraint(socket, component_group, mo=False)
            pm.orientConstraint(socket, component_group, mo=False)
        pm.parent(component_group, self.rig.get(attr_rig_group))
        lock_transforms(component_group)
        hide_transforms(component_group)

        if start == end:
            bind_joints = [start]
        else:
            if end not in start.listRelatives(c=True, ad=True):
                raise Exception('{0} not a descendant of {1}'.format(end.name(), start.name()))

            bind_joints = list()
            bind_joints.append(end)
            node = end
            while not node == start:
                node = node.getParent()
                if pm.objectType(node) == 'joint':
                    bind_joints.append(node)
            bind_joints = bind_joints[::-1]

        controls = []
        for joint in bind_joints:
            name = joint.name()
            name = name.split('|')[-1]
            name = name + '_FK_CTRL'
            dup_joint = pm.duplicate(joint, parentOnly=True)[0]
            dup_joint.rename(name)
            controls.append(dup_joint)
        pm.parent(controls, w=1)
        for ind, joint in enumerate(controls[1:]):
            pm.parent(joint, controls[ind])

        zero_groups = []
        for joints in zip(controls, bind_joints):
            pm.pointConstraint(*joints, mo=False, w=1.0)
            orient = pm.orientConstraint(*joints, mo=False, w=1.0)
            # Set orient constraint to Shortest interpType
            orient.interpType.set(2)

        for control in controls:
            existing_parent = control.listRelatives(p=True)
            zero_group = pm.group(em=True, n="{0}_Zero".format(control.name().replace('_CTRL', '')))
            copy_transforms(control, zero_group)

            pm.parent(control, zero_group)
            if pm.objectType(control) == 'joint':
                control.rotate.set((0, 0, 0))
                control.attr('jointOrientX').set(0)
                control.attr('jointOrientY').set(0)
                control.attr('jointOrientZ').set(0)

            for parentNode in existing_parent:
                pm.parent(zero_group, parentNode)
            zero_groups.append(zero_group)

            control_shape = pm.circle(c=[0, 0, 0], nr=[0, 1, 0], sw=360, r=1, d=3, ut=0, tol=0, s=8, ch=1)[0]
            copy_transforms(control, control_shape)
            control_shape.rotateBy((0, 0, 90))
            pm.delete(control_shape, constructionHistory=True)
            shape = pm.listRelatives(control_shape, children=True, shapes=True)
            pm.parent(shape, control, shape=True, add=True)
            pm.delete(control_shape)

        pm.parent(zero_groups[0], component_group)

        for node in zero_groups:
            lock_transforms(node)
            hide_transforms(node)

        self.bind_joints = bind_joints
        self.controls = controls
        self.component_group = component_group

    def valid(self):
        if self.get(attr_start_joint) and self.get(attr_end_joint):
            return True
        else:
            return False


def copy_transforms(source, target):
    '''
    Copy position and rotation of source to target.

    :param source: Object to copy transformation
    :param target: Object to apply transformation
    '''
    translation = pm.xform(source, t=True, ws=True, q=True)
    pm.xform(target, t=translation, ws=True)

    rotation = pm.xform(source, ro=True, ws=True, q=True)
    rot_order = target.getRotationOrder()
    pm.xform(target, ro=rotation, ws=True, roo=source.getRotationOrder())
    target.setRotationOrder(rot_order, True)


def lock_transforms(transform, translate='xyz', rotate='xyz', scale='xyz'):
    '''
    Lock transforms attributes.

    :param pm.PyNode transform: Node to lock transform attributes
    :param string translate: a string of translate axes to lock
    :param string rotate: a string of rotate axes to lock
    :param string scale: a string of scale axes to lock
    :return: dictionary of axes that were locked
    '''
    locked_attrs = {'translate': '', 'rotate': '', 'scale': ''}

    for axis in translate:
        if not transform.attr('t' + axis).isLocked():
            transform.attr('t' + axis).setLocked(True)
            locked_attrs['translate'] = locked_attrs['translate'] + axis
    for axis in rotate:
        if not transform.attr('r' + axis).isLocked():
            transform.attr('r' + axis).setLocked(True)
            locked_attrs['rotate'] = locked_attrs['rotate'] + axis
    for axis in scale:
        if not transform.attr('s' + axis).isLocked():
            transform.attr('s' + axis).setLocked(True)
            locked_attrs['scale'] = locked_attrs['scale'] + axis

    return locked_attrs


def hide_transforms(transform, translate='xyz', rotate='xyz', scale='xyz'):
    '''
    Hide transforms attributes in channel box.

    :param pm.PyNode transform: Node to hide transform attributes
    :param string translate: a string of translate axes to hide
    :param string rotate: a string of rotate axes to hide
    :param string scale: a string of scale axes to hide
    :return: dictionary of axes that were hide
    '''
    for axis in translate:
        transform.attr('t' + axis).setKeyable(False)
        transform.attr('t' + axis).showInChannelBox(False)
    for axis in rotate:
        transform.attr('r' + axis).setKeyable(False)
        transform.attr('r' + axis).showInChannelBox(False)
    for axis in scale:
        transform.attr('s' + axis).setKeyable(False)
        transform.attr('s' + axis).showInChannelBox(False)

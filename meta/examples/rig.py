from collections import OrderedDict

import pymel.core as pm

import meta.core

attr_rig_components = 'rigComponents'
attr_rig = 'rig'
attr_built = 'isBuild'
attr_socket = 'socket'
attr_component_group = 'componentGroup'
attr_controls = 'controls'
attr_bind = 'bindJoints'


class Rig(meta.core.Metanode):
    meta_version = 1

    @classmethod
    def attr_class(cls):
        return {attr_rig_components: {'at': 'message', 'multi': True}}

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

        pm.connectAttr(self.node.message, new_component.node.rig)

    @property
    def components(self):
        return self.get(attr_rig_components)


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

    def build_component(self):
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
            pm.delete(self.componentGroup)
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
    def bind_joints(self):
        return self.get(attr_bind)

    @property
    def built(self):
        return self.get(attr_built)

    @built.setter
    def built(self, state):
        self.set(attr_built, state)


class FK(Component):
    meta_version = 1

    attr_build = OrderedDict([
        ('startJoint', {'at': 'message'}),
        ('endJoint', {'at': 'message'})])

    def _create_rig(self):
        pass

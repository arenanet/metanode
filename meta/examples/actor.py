import pymel.core as pm

import meta.core
import meta.examples.skeleton

attr_skeleton = 'skeleton'
attr_export_meshes = 'exportMeshes'
attr_export_collision = 'exportCollision'
attr_export_cloth = 'exportCloth'
attr_active_actor = 'activeActor'


class Actor(meta.core.Metanode):
    '''
    A Metanode for saving skeletons.
    '''
    meta_version = 1

    @classmethod
    def attr_class(cls):
        return {attr_skeleton: {'at': 'message'},
                attr_export_meshes: {'at': 'message', 'multi': True},
                attr_export_collision: {'at': 'message', 'multi': True},
                attr_export_cloth: {'at': 'message', 'multi': True}}

    @property
    def skeleton(self):
        return self.get(attr_skeleton)

    @skeleton.setter
    def skeleton(self, skeleton):
        if skeleton.__class__ is meta.examples.skeleton.Skeleton:
            self.set(attr_skeleton, skeleton.node)


class ActiveActor(meta.core.SingletonMetanode):
    '''
    Metanode Singleton for tracking the currently active Actor Metanode.
    '''
    meta_version = 1

    @classmethod
    def __metanodeattributes__(cls):
        return {attr_active_actor: {'at': 'message'}}

    @property
    def active_actor(self):
        return self.get(attr_active_actor)

    @active_actor.setter
    def active_actor(self, actor):
        self.set(actor.node, attr_active_actor)


def get_active_actor():
    '''
    :return: Actor
    '''
    return ActiveActor.instance().active_actor

import meta.core


class Skeleton(meta.core.Metanode):
    '''
    A Metanode for saving skeletons.
    '''
    metaversion = 1

    @classmethod
    def attr_class(cls):
        return {'skeletonPath' : {'dt':'string'},
                'bindPose' : {'dt':'string'},
                'zeroPose' : {'dt':'string'},
                'root': {'at':'message'},
                'noBindJoints': {'at':'message', 'multi':True},
                'noExportJoints': {'at':'message', 'multi':True}}


'''
This script exists to batch transfer animation from the LA Noire rigs to the new-style
skeleton builder rigs.
'''

from maya import cmds

import path
import misc
import logging
import str_utils
import morpheme

import maya_io
import simple_p4

import mapping_utils
import reference_utils

from animation import clip
import export_manager
import skeletonBuilder

logger = logging.getLogger(__name__)

RIG_FILEPATH = path.TB_DATA / 'animation/male/rig.ma'
RIG_ANIM_DIRPATH = RIG_FILEPATH.up() / 'animation'

MAPPING = (('PPT_ROOT', 'trajectory'),
           ('PPT_Hips', 'rootControl'),

           ('PPT__LeftFoot', 'legControl_L'),
           ('PPT_LeftKnee', 'leg_poleControl_L'),

           ('PPT__RightFoot', 'legControl_R'),
           ('PPT_RightKnee', 'leg_poleControl_R'),

           ('PPT_Spine1', 'spine_0_fkControl'),
           ('PPT_Spine2', 'spine_1_fkControl'),
           ('PPT_Spine3', 'spine_2_fkControl'),
           ('PPT_LowNeck', 'neck_0_Control'),
           ('PPT_UpNeck', 'neck_1_Control'),
           ('PPT_Head', 'headControl'),

           ('PPT_LeftClavicle', 'clavicleControl_L'),
           ('PPT_RightClavicle', 'clavicleControl_R'),

           ('PPT_LeftArm', 'fk_bicepControl_L'),
           ('PPT_LeftElbow', 'fk_elbowControl_L'),
           ('PPT_LeftHand', 'fk_wristControl_L'),
           ('PPT_LeftElbow_IK', 'arm_poleControl_L'),
           ('PPT_LeftHand_IK', 'armControl_L'),

           ('PPT_RightArm', 'fk_bicepControl_R'),
           ('PPT_RightElbow', 'fk_elbowControl_R'),
           ('PPT_RightHand', 'fk_wristControl_R'),
           ('PPT_RightElbow_IK', 'arm_poleControl_R'),

           ('PPT_RightHand_IK', 'armControl_R'),
           ('PPT_LeftIndex1', 'IndexControl_0_L'),
           ('PPT_LeftIndex2', 'IndexControl_1_L'),
           ('PPT_LeftIndex3', 'IndexControl_2_L'),
           ('PPT_LeftMiddle1', 'MidControl_0_L'),
           ('PPT_LeftMiddle2', 'MidControl_1_L'),
           ('PPT_LeftMiddle3', 'MidControl_2_L'),
           ('PPT_LeftRing1', 'RingControl_0_L'),
           ('PPT_LeftRing2', 'RingControl_1_L'),
           ('PPT_LeftRing3', 'RingControl_2_L'),
           ('PPT_LeftLittle1', 'PinkyControl_0_L'),
           ('PPT_LeftLittle2', 'PinkyControl_1_L'),
           ('PPT_LeftLittle3', 'PinkyControl_2_L'),
           ('PPT_LeftThumb1', 'ThumbControl_0_L'),
           ('PPT_LeftThumb2', 'ThumbControl_1_L'),
           ('PPT_LeftThumb3', 'ThumbControl_2_L'),

           ('PPT_RightIndex1', 'IndexControl_0_R'),
           ('PPT_RightIndex2', 'IndexControl_1_R'),
           ('PPT_RightIndex3', 'IndexControl_2_R'),
           ('PPT_RightMiddle1', 'MidControl_0_R'),
           ('PPT_RightMiddle2', 'MidControl_1_R'),
           ('PPT_RightMiddle3', 'MidControl_2_R'),
           ('PPT_RightRing1', 'RingControl_0_R'),
           ('PPT_RightRing2', 'RingControl_1_R'),
           ('PPT_RightRing3', 'RingControl_2_R'),
           ('PPT_RightLittle1', 'PinkyControl_0_R'),
           ('PPT_RightLittle2', 'PinkyControl_1_R'),
           ('PPT_RightLittle3', 'PinkyControl_2_R'),
           ('PPT_RightThumb1', 'ThumbControl_0_R'),
           ('PPT_RightThumb2', 'ThumbControl_1_R'),
           ('PPT_RightThumb3', 'ThumbControl_2_R'),
           )

KEY_REMAP = (('PPT_ROOT', 'PPT_ROOT'),
             ('PPT_Hips', 'Male_Hips'),

             ('PPT__LeftFoot', 'Male_LeftFoot'),
             ('PPT_LeftKnee', 'Male_LeftLeg'),
             ('PPT__RightFoot', 'Male_RightFoot'),
             ('PPT_RightKnee', 'Male_RightLeg'),

             ('PPT_Spine1', 'Male_Spine1'),
             ('PPT_Spine2', 'Male_Spine2'),
             ('PPT_Spine3', 'Male_Spine3'),
             ('PPT_LowNeck', 'Male_Neck1'),
             ('PPT_UpNeck', 'Male_Neck2'),
             ('PPT_Head', 'Male_Head'),

             ('PPT_LeftClavicle', 'Male_LeftShoulder'),
             ('PPT_RightClavicle', 'Male_RightShoulder'),

             ('PPT_LeftArm', 'Male_LeftArm'),
             ('PPT_LeftElbow', 'Male_LeftForeArm'),
             ('PPT_LeftHand', 'Male_LeftHand'),
             ('PPT_LeftElbow_IK', 'Male_LeftForeArm'),
             ('PPT_LeftHand_IK', 'Male_LeftHand'),

             ('PPT_RightArm', 'Male_RightArm'),
             ('PPT_RightElbow', 'Male_RightForeArm'),
             ('PPT_RightHand', 'Male_RightHand'),
             ('PPT_RightElbow_IK', 'Male_RightForeArm'),
             ('PPT_RightHand_IK', 'Male_RightHand'),

             ('PPT_LeftIndex1', 'Male_LeftIndex1'),
             ('PPT_LeftIndex2', 'Male_LeftIndex2'),
             ('PPT_LeftIndex3', 'Male_LeftIndex3'),
             ('PPT_LeftMiddle1', 'Male_LeftMiddle1'),
             ('PPT_LeftMiddle2', 'Male_LeftMiddle2'),
             ('PPT_LeftMiddle3', 'Male_LeftMiddle3'),
             ('PPT_LeftRing1', 'Male_LeftRing1'),
             ('PPT_LeftRing2', 'Male_LeftRing2'),
             ('PPT_LeftRing3', 'Male_LeftRing3'),
             ('PPT_LeftLittle1', 'Male_LeftLittle1'),
             ('PPT_LeftLittle2', 'Male_LeftLittle2'),
             ('PPT_LeftLittle3', 'Male_LeftLittle3'),
             ('PPT_LeftThumb1', 'Male_LeftThumb1'),
             ('PPT_LeftThumb2', 'Male_LeftThumb2'),
             ('PPT_LeftThumb3', 'Male_LeftThumb3'),

             ('PPT_RightIndex1', 'Male_RightIndex1'),
             ('PPT_RightIndex2', 'Male_RightIndex2'),
             ('PPT_RightIndex3', 'Male_RightIndex3'),
             ('PPT_RightMiddle1', 'Male_RightMiddle1'),
             ('PPT_RightMiddle2', 'Male_RightMiddle2'),
             ('PPT_RightMiddle3', 'Male_RightMiddle3'),
             ('PPT_RightRing1', 'Male_RightRing1'),
             ('PPT_RightRing2', 'Male_RightRing2'),
             ('PPT_RightRing3', 'Male_RightRing3'),
             ('PPT_RightLittle1', 'Male_RightLittle1'),
             ('PPT_RightLittle2', 'Male_RightLittle2'),
             ('PPT_RightLittle3', 'Male_RightLittle3'),
             ('PPT_RightThumb1', 'Male_RightThumb1'),
             ('PPT_RightThumb2', 'Male_RightThumb2'),
             ('PPT_RightThumb3', 'Male_Rightthumb3'),  # F me... Notice the lowercase t in Thumb? Yeah... Thats really there
             )

def replaceInMappingSrcs(newPrefix):
    '''
    replaces the Male_ prefix with the given string
    '''
    return [(src, tgt.replace('Male_', newPrefix)) for src, tgt in KEY_REMAP]

def getMappings():
    mapping, keyRemap = MAPPING, KEY_REMAP

    rootJoint = mapping_utils.findItem('Male_Hips')
    if not rootJoint:

        # try replacing the "Male_" prefix with the "Kelso_" prefix
        rootJoint = mapping_utils.findItem('Kelso_Hips')
        if rootJoint:
            keyRemap = replaceInMappingSrcs('Kelso_')
        else:
            raise ValueError("Oh noez!")

    mapping = str_utils.Mapping.FromPairs(MAPPING)
    keyRemap = str_utils.Mapping.FromPairs(keyRemap)

    return mapping_utils.resolveMappingToScene(mapping), mapping_utils.resolveMappingToScene(keyRemap)

def hasRigAlreadyBeenReferenced():
    return reference_utils.ReferencedFile.IsFilepathReferenced(RIG_FILEPATH)

def referenceRig():
    cmds.file(RIG_FILEPATH, reference=True, namespace='rig')

def iterFilesToConvert():
    missingFiles = []
    for network in morpheme.iterNetworks():
        for take in network.iterTakes():
            maFilepath = take.filepath.setExtension('ma')
            if not maFilepath.exists():
                maFilepath = take.sourceFilepath

            if not maFilepath.exists():
                missingFiles.append(take.filepath)
                continue

            yield maFilepath

    if missingFiles:
        for f in misc.removeDupes(missingFiles):
            print f

        raise Exception("Cannot find maya file for %d takes" % len(missingFiles))

@maya_io.d_suspendCallbacks
def tmp():
    #m, k = getMappings()
    #clip.autoGeneratePostTraceScheme(str_utils.Mapping(k.tgts, m.tgts))
    #return

    with simple_p4.ChangeContext('Batch remap to new rig') as theChange:
        animDirpath = path.TB_DATA / 'animation/database/characters'
        for f in iterFilesToConvert():
            if not f.hasExtension('ma'):
                continue

            # figure out the new location
            newLocation = RIG_ANIM_DIRPATH / ((f - animDirpath)[1:])
            newLocation.up().create()

            # if the new file already exists, the trace has already been done - bail
            if newLocation.exists():
                continue

            cmds.file(f, o=True, f=True, prompt=False)

            # if the rig has already been referenced, skip this file
            if hasRigAlreadyBeenReferenced():
                continue

            # rename the file before setting up export-ness (paths are auto-generated using the scene's filepath)
            cmds.file(rename=newLocation)

            referenceRig()
            mapping, keyRemap = getMappings()
            if not mapping.keys():
                logger.error("Skipping %s" % f)
                continue

            clip.Tracer(start=cmds.playbackOptions(q=True, min=True),
                        end=cmds.playbackOptions(q=True, max=True)
                        ).apply(mapping, False, keyRemap)

            # setup export shinanigans
            container = export_manager.ExportableContainer.Create()
            exportable = container.create(export_manager.Animation, ['rig:geo', 'rig:root'])
            exportable.export()

            with simple_p4.EditAddContext(newLocation, theChange):
                cmds.file(save=True, f=True)

@maya_io.d_suspendCallbacks
def exportAllAnimations():
    with simple_p4.ChangeContext('Batch re-export old skeleton constrained to new') as theChange:
        animBaseDirpath = path.TB_DATA / 'animation/male/animation'
        for f in animBaseDirpath.files(True):
            if not f.hasExtension('ma'):
                continue

            cmds.file(f, o=True, f=True, prompt=False)
            for container in export_manager.ExportableContainer.Iter():
                for exportable in container:
                    exportable.setNodes(['rig:animExportSet'])

            export_manager.exportAll()

            #with simple_p4.EditAddContext(f, theChange):
                #if f.getWritable():
                    #cmds.file(save=True, f=True)

@maya_io.d_suspendCallbacks
def transfer(oldFilepath):
    animDirpath = path.TB_DATA / 'animation/database/characters'

    # figure out the new location
    newLocation = RIG_ANIM_DIRPATH / ((oldFilepath - animDirpath)[1:])
    newLocation.up().create()

    cmds.file(oldFilepath, o=True, f=True, prompt=False)

    # if the rig has already been referenced, skip this file
    if not hasRigAlreadyBeenReferenced():
        referenceRig()

    # rename the file before setting up export-ness (paths are auto-generated using the scene's filepath)
    cmds.file(rename=newLocation)

    # make sure all arm parts are in fk mode (otherwise fk control tracing probably won't work)
    ikFkCls = skeletonBuilder.RigPart.GetNamedSubclass('IkFkArm')
    if ikFkCls:
        for part in ikFkCls.Iter():
            part.switchToFk()

    mapping, keyRemap = getMappings()
    if not mapping.keys():
        raise Exception("Failed to find nodes to map")

    clip.Tracer(start=cmds.playbackOptions(q=True, min=True),
                end=cmds.playbackOptions(q=True, max=True)
                ).apply(mapping, False, keyRemap)

    # setup export shinanigans
    container = export_manager.ExportableContainer.Create()
    exportable = container.create(export_manager.Animation, ['rig:geo', 'rig:root'])
    with simple_p4.EditAddContext(newLocation):
        cmds.file(save=True, f=True)

    exportable.export()

#end

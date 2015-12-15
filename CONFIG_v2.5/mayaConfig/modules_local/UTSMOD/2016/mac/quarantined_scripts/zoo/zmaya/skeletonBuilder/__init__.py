
import baseSkeletonPart
import baseRigPart

# import the skeleton primitives
import skeletonPart_spine
import skeletonPart_head

import skeletonPart_arm
import skeletonPart_hand

import skeletonPart_leg

# import the rig primitives
import baseRigPart
import rigPart_root

import rigPart_spines
import rigPart_heads

import rigPart_bipedLimbs
import rigPart_hands

import rigPart_curves
import rigPart_misc

# import user module loading
import userModules
userModules.importUserModules()

# Once user modules have been imported, we can setup the rig methods
baseRigPart.setupSkeletonPartRigMethods()

# convenience access...
SkeletonPart = baseSkeletonPart.SkeletonPart
RigPart = baseRigPart.RigPart
WorldPart = baseRigPart.WorldPart
buildRigForModel = baseRigPart.buildRigForModel

#end

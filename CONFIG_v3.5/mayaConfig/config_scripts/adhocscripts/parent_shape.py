import maya.cmds as cmds											
objectList = cmds.ls(selection = True);                           
shapes = "";
if len(objectList) != 2:
    cmds.error ("Please select two objects ONLY")
elif len(objectList)==2:
    cmds.warning ("Freezing Transformations")
    try:
        cmds.makeIdentity( apply=True, translate=True, rotate=True, scale=True )
    except:
        cmds.error (" Unable to freeze transformations, check if  transformations are locked")
        quit()
        
    cmds.warning ("Fetching children")
    try:
        shapes = cmds.listRelatives(objectList[0])
        
    except:
        cmds.error ("unable to list children, check selection")   
        quit();
    if shapes != None:
        cmds.warning ("found shapes, parenting will commence")
        for i in shapes:
            try: 
                cmds.parent(i,objectList[1], shape=True, add=True)
                cmds.warning ("parented: " + i)
            except:
                cmds.error ("parenting failed, please check selection or shape nodes in outliner") 
                quit();
        try:
            cmds.delete(objectList[0])
        except:
            cmds.error ("unable to delete:" +objectList[0] +"please remove node manually from outliner")   
            quit();      
        cmds.warning ("Operation completed successfully")  
    else:
        cmds.error ("No shapes found, please check selection");           

import re
import logging

import apiExtensions

def removeRefDuplication():
    refRex = re.compile('(ref[0-9]*_)+')
    for dag in apiExtensions.iterDags():

        # grab the node's leaf name
        name = dag.shortName()

        # if we have an offending name, rename it
        m = refRex.match(name)
        if m:
            dag.rename('ref_' + name[m.end():])
            logging.info("Renamed %s -> %s" % (name, dag))

#end


import os
import sys

# set defaults for various data locations
os.environ.setdefault('TB_DRIVE', 't:')
os.environ.setdefault('TB_PROJ', 'woto')

# this is used by the presets module
os.environ.setdefault('TB_PRESETS', 'u:/presets')

import path
import site

from deploy import location_map

def main():

    # add version specific directories
    thisDirpath = path.Path(__file__).up()
    versionDirpath = thisDirpath / ('%s.%s' % (sys.version_info[0], sys.version_info[1]))
    sys.path.append(versionDirpath)

    # this is a little nasty, but we need to add this so the pywin32.pth file gets dealt with...  In general we don't
    # use these stupid files
    site.addsitedir(versionDirpath)

    # is python being booted up by maya?  if so, append maya python tool paths
    if os.path.split(sys.executable)[1].lower().startswith('maya'):
        sys.path.append(thisDirpath.up() / 'Maya/python')

    # setup TB_DEV override paths - cast to string just to make sure there are no path.Path instances in there
    sys.path = map(str, location_map.insertOverrides(sys.path))

    # import as many modules as possible after the override paths have been inserted so DEV
    # locations override distribution locations
    import log

main()
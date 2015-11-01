
import sys
import logging
import datetime

import path

FORMAT = '%(asctime)-18s %(name)s %(levelname)s %(lineno)d %(message)s'

# generate a filename - name log files based on the date-time of this module being created
LOG_FILENAME = 'log_%s_%s.txt' % (path.Path(sys.executable).name(),
                                  datetime.datetime.now().strftime('%a-%b-%Y %H.%M.%S'))

LOG_FILEPATH = path.Path('~/Documents/WOTO') / LOG_FILENAME

#logging.basicConfig(filename=LOG_FILEPATH, filemode='w', format=FORMAT)

#end

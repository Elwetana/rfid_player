#!/usr/bin/python
#import swmixer
#import time

import multiprocessing
import os
import logging

logger = logging.getLogger("root.volume")

class VolumeControl(multiprocessing.Process):

    def __init__(self, pipe):
        multiprocessing.Process.__init__(self)
        self.pipe = pipe
        self.set_volume = 50

    def run(self):
        while True:
            if self.pipe.poll(1):
                cmnd = self.pipe.recv()
                if cmnd[0] == 'quit':
                    logger.warning("Volume control termnating")
                    break
                elif cmnd[0] == 'up':
                    self.set_volume += cmnd[1]
                elif cmnd[0] == 'down':
                    self.set_volume -= cmnd[1]
                #print 'Volume = {volume}%' .format(volume = set_volume)
                set_vol_cmd = 'sudo amixer cset numid=1 -- {volume}% > /dev/null' .format(volume = self.set_volume)
                #print set_vol_cmd
                os.system(set_vol_cmd)  # set volume
                #time.sleep(0.1)

if __name__ == "__main__":
    print "Volume control class"

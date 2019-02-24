#!/usr/bin/python

import alsaaudio
import multiprocessing
import os
import logging

logger = logging.getLogger("root.volume")

class VolumeControl(multiprocessing.Process):

    def __init__(self, pipe):
        multiprocessing.Process.__init__(self)
        self.pipe = pipe
        self.set_volume = 100

    def run(self):
        while True:
            if self.pipe.poll(1):
                cmnd = self.pipe.recv()
                if cmnd[0] == 'quit':
                    break
                elif cmnd[0] == 'up':
                    self.set_volume += cmnd[1]
                elif cmnd[0] == 'down':
                    self.set_volume -= cmnd[1]
                self.set_volume = min(max(self.set_volume, 0), 100)
                logger.warning("Setting volume to %s" % self.set_volume)
                mixer = alsaaudio.Mixer('PCM')
                mixer.setvolume(self.set_volume, alsaaudio.MIXER_CHANNEL_ALL)
        logger.warning("Volume control terminating")

if __name__ == "__main__":
    print "Volume control class"

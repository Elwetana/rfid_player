#!/usr/bin/python
import mad
#import ao
import alsaaudio
import sys
import os.path
import logging



class Player():

    def __init__(self):
        self.f = '../data/trnka1.mp3'
        self.seek_time = 0

    def play(self):
        try:
            mf = mad.MadFile(self.f)
        except IOError:
            print "Error opening file %s for playing" % self.f
            sys.exit(1)
        if self.seek_time > 5000:  #seeking is broken a bit, we have to flush the buffer by reading
            mf.seek_time(self.seek_time - 5000)
            for i in range(100):
                mf.read()
        #dev = ao.AudioDevice('alsa', rate=mf.samplerate())
        dev = alsaaudio.PCM(device='default')
        dev.setrate(mf.samplerate())
        iSave = 0
        why_stopped = ''
        print "Starting to play"
        while True:
            buf = mf.read()
            if (buf is None):
                if buf is None:
                    why_stopped = 'finished'
                break
            dev.write(buffer(buf))
            iSave += 1
            if iSave == 100:
                self.seek_time = mf.current_time()
        print "Finished playing"
        if why_stopped == 'finished':
            self.seek_time = 0

    def list_mixers(self):
        print "Available mixers"
        for m in alsaaudio.mixers():
            print m
        mixer = alsaaudio.Mixer('PCM')
        volumes = mixer.getvolume()
        for v in volumes:
            print v
        mixer.setvolume(100, alsaaudio.MIXER_CHANNEL_ALL)


if __name__ == "__main__":
    print "Start"
    p = Player()
    p.play()
    p.list_mixers()

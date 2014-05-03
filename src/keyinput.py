#!/usr/bin/python

import multiprocessing
from multiprocessing.managers import BaseManager
from evdev import InputDevice, categorize, ecodes, KeyEvent
import xml.parsers.expat

class KeyListener(multiprocessing.Process):

    def __init__(self, msg_queue, keymap_file = '../data/keymap.xml'):
        multiprocessing.Process.__init__(self)
        self.debug = 0
        self.msg_queue = msg_queue
        self.read_keymap(keymap_file)

    def run(self):
        dev = InputDevice('/dev/input/event0')
        print "Listener running"
        for event in dev.read_loop():
            if event.type == ecodes.EV_KEY:
                if self.debug > 3:
                    print(categorize(event))
                if event.type == ecodes.EV_KEY and event.value == 1: #event.value == 1 => this is key down
                    code = event.code
                    if self.debug > 2:
                        print "Key code:", code
                    if code in self.actions:
                        if self.debug > 2:
                            print 'Adding message to queue:', self.actions[code]
                        self.msg_queue.put((self.actions[code],0))
                        if self.actions[code] == 'quit':
                            break
        print "KeyListener terminating"

    def update_actions(self, name, attrs):
        if name == 'map':
            self.actions[ecodes.ecodes[attrs['key']]] = attrs['action']
    
    def read_keymap(self, keymap_file):
        self.actions = {}
        f = open(keymap_file, 'r')
        p = xml.parsers.expat.ParserCreate()
        p.StartElementHandler = self.update_actions
        p.ParseFile(f)
        f.close()
        print 'Keymap loaded'
        if self.debug > 2:
            print self.actions

if __name__ == "__main__":
    print 'This is module for KeyListener class'

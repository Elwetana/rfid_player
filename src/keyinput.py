#!/usr/bin/python

import multiprocessing
from multiprocessing.managers import BaseManager
from evdev import InputDevice, categorize, ecodes, KeyEvent
import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger("root.keyinput")

class KeyListener(multiprocessing.Process):

    def __init__(self, msg_queue, keymap_file = '../data/keymap.xml'):
        multiprocessing.Process.__init__(self)
        self.msg_queue = msg_queue
        self.read_keymap(keymap_file)

    def run(self):
        dev = InputDevice('/dev/input/event0')
        logger.warning("Listener running")
        for event in dev.read_loop():
            if event.type == ecodes.EV_KEY:
                logger.debug(categorize(event))
                if event.type == ecodes.EV_KEY and event.value == 1: #event.value == 1 => this is key down
                    code = event.code
                    logger.info("Key code: %s" % code)
                    if code in self.actions:
                        logger.info("Adding message to queue: %s" % (self.actions[code],))
                        self.msg_queue.put((self.actions[code],0))
                        if self.actions[code] == 'quit':
                            break
        logger.warning("KeyListener terminating")

    def read_keymap(self, keymap_file):
        self.actions = {}
        self.tree = ET.parse(keymap_file)
        actionmap = self.tree.getroot()
        for action in actionmap:
            self.actions[ecodes.ecodes[action.get('key')]] = action.get('action')
        logger.info('Keymap loaded')
        logger.debug(self.actions)

if __name__ == "__main__":
    print 'This is module for KeyListener class'

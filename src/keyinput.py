#!/usr/bin/python

import multiprocessing
from multiprocessing.managers import BaseManager
from message import Msg
from evdev import InputDevice, categorize, ecodes, KeyEvent, list_devices
from select import select
import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger(__name__)

class KeyMsg(Msg):

    def __init__(self, action):
        self.msg_type = 'key'
        self.value = action
        self.needs_ack = True

"""
The problem here is that the devices[fd].read() call does not timeout, so the loop in run() method will never terminate,
unless an event is passed to it -- therefore it's not possible to join this process if the main program wants to terminate
for other reasons.

There are two solutions I can see: inserting an event in the device to terminate the loop or rewriting this class
so that it works with asyncore loop() (see http://python-evdev.readthedocs.org/en/latest/tutorial.html#reading-events-with-asyncore)
The latter approach seems better to me.
"""
class KeyListener(multiprocessing.Process):

    def __init__(self, msg_queue, dev_names, keymap_file = '../data/keymap.xml'):
        multiprocessing.Process.__init__(self)
        self.msg_queue = msg_queue
        self.read_keymap(keymap_file)
	available_devices = list_devices()
	devices_to_use = [d for d in dev_names if d in available_devices]
        devices = map(InputDevice, devices_to_use)
        self.devices = {dev.fd: dev for dev in devices}

    def run(self):
        logger.warning("Key listener running")
        while True:
            r,w,x = select(self.devices, [], [])
            for fd in r:
                for event in self.devices[fd].read():
                    if (event.type != ecodes.EV_REL) and (event.type != ecodes.EV_SYN):
                        logger.info(categorize(event))
                    if event.type == ecodes.EV_KEY:
                        if event.type == ecodes.EV_KEY and event.value == 1: #event.value == 1 => this is key down
                            code = event.code
                            logger.info("Key code: %s" % code)
                            if code in self.actions:
                                logger.info("Adding message to queue: %s" % (self.actions[code],))
                                self.msg_queue.put(KeyMsg(self.actions[code]))
                                if self.actions[code] == 'quit':
                                    logger.warning("KeyListener terminating")
                                    return
                                if self.actions[code] == 'error':
                                    logger.warning("Error in KeyListner, respawn")
                                    return

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
    logging.basicConfig(level=logging.INFO)
    msg_queue = multiprocessing.Queue()
    keylistener = KeyListener(msg_queue, ['/dev/input/event0','/dev/input/event1'])
    keylistener.start()
    while True:
        msg = msg_queue.get()
        print msg.value
        if msg.value == 'quit':
            break
        if msg.value == 'error':
            keylistener.join()
            keylistener = KeyListener(msg_queue, ['/dev/input/event0','/dev/input/event1'])
            keylistener.start()
    keylistener.join()


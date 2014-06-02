#!/usr/bin/python

import multiprocessing
#from multiprocessing.managers import BaseManager
import xml.etree.ElementTree as ET
import logging
from keyinput import KeyListener
from player import Player
from volume import VolumeControl
from led import LedControl
from reader import RfidReader
import os, time, sys, copy
import sqlite3

class State:
    playing = 1
    stopped = 2

class Dispatcher:

    def __init__(self, list_file = '../data/list.xml', data_dir = '../data/'):
        self.read_list(list_file, data_dir)
        self.state = State.stopped
        self.time = 0
        self.workers = {}
        self.pipes = {}
        self.lastval = -1
        self.actions = {
            'rfid': self.msg_rfid,
            'key': self.msg_keys,
            'player': self.msg_player,
            'save_pos': self.msg_savepos
        }

    def create_worker(self, worker_name, worker_class, needs_pipe, needs_queue, *args):
        if needs_pipe:
            to_worker, from_worker = multiprocessing.Pipe()
            if needs_queue:
                self.workers[worker_name] = worker_class(from_worker, self.msg_queue, *args)
            else:
                self.workers[worker_name] = worker_class(from_worker, *args)
            self.pipes[worker_name] = to_worker
        else:
            self.workers[worker_name] = worker_class(self.msg_queue, *args)
        self.workers[worker_name].start()

    def start(self):
        self.msg_queue = multiprocessing.Queue()
        self.create_worker('key_listener', KeyListener, False, True, ['/dev/input/event0','/dev/input/event1'])
        self.create_worker('led_control', LedControl, True, False)
        self.create_worker('volume_control', VolumeControl, True, False)
        self.create_worker('player', Player, True, True)
        self.create_worker('rfid_reader', RfidReader, True, True)

        while True:
            msg = self.msg_queue.get()
            logging.info("Message of type %s received" % msg.msg_type)
            if msg.needs_ack:
                self.pipes['led_control'].send(('ack',0))
            if self.actions.get(msg.msg_type, self.msg_unknown)(msg):
                break
        self.workers['key_listener'].join()
        for worker in self.workers:
            if worker != 'key_listener':
                logging.warning('Trying to terminate the %s' % worker)
                self.pipes[worker].send(('quit',0))
                self.workers[worker].join()
        logging.warning('Terminating')

    def msg_rfid(self, msg):
        logging.info("RFID message received, value: %s" % msg.value)
        if (self.lastval != msg.value) or (self.state != State.playing):
            if msg.value in self.items:
                self.play_item(msg.value)
            else:
                logging.error("RFID value not present in list of items")
        else:
            logging.info("Ignoring accidental scan")
        return False

    def play_item(self, item_id):
        self.time = time.time()
        self.state = State.playing
        self.pipes['player'].send(('start',self.items[item_id]))
        self.lastval = item_id

    def msg_keys(self, msg):
        if msg.value == 'quit':
            return True
        to_player = ['next_track', 'prev_track', 'stop', 'play', 'ff', 'bb']
        to_volume = {'vol_up': ('up', 5), 'vol_down': ('down', 5)}
        to_self   = {'error': (self.handle_error, 0), 'next_item': (self.change_item, 1), 'prev_item': (self.change_item, -1)}
        if msg.value in to_player:
            logging.info('Message %s receieved, sending to player' % msg.value)
            self.pipes['player'].send((msg.value,0))
        elif msg.value in to_volume:
            logging.info('Message %s receieved, sending to volume control' % msg.value)
            self.pipes['volume_control'].send(to_volume[msg.value])
        elif msg.value in to_self:
            logging.info('Message %s receieved, sending to self' % msg.value)
            to_self[msg.value][0](to_self[msg.value][1])
        else:
            logging.error('Unknown message from keyboard')
        return False

    def msg_player(self, msg):
        logging.info('Message to LED controller')
        if msg.value == 'started':
            if msg.is_radio:
                self.pipes['led_control'].send(('play','radio'))
            else:
                self.pipes['led_control'].send(('play','local'))
        elif msg.value == 'stopped':
            self.state = State.stopped
            self.pipes['led_control'].send(('stop',0))
        return False

    def msg_savepos(self, msg):
        self.save_pos(*msg.value)
        return False

    def msg_unknown(self, msg):
        logging.info("Unknown message: %s" % msg)
        return False

    def change_item(self, direction):
        all_items = self.items.keys()
        if self.lastval in all_items:
            new_item_pos = all_items.index(self.lastval) + direction
        else:
            new_item_pos = 0
        if new_item_pos < 0:
            new_item_pos = len(all_items) - 1
        if new_item_pos == len(all_items):
            new_item_pos = 0
        self.play_item(all_items[new_item_pos])

    #this is to handle a special error thrown by the keyboard device
    def handle_error(self, _x):
         self.workers['key_listener'].join()
         self.workers['key_listener'] = KeyListener(self.msg_queue, ['/dev/input/event0','/dev/input/event1'])
         self.workers['key_listener'].start()

    def save_pos(self, seek_time, file_index, folder_name):
        logging.debug("Saving position")
        conn = sqlite3.connect('player.db')
        conn.execute('update lastpos set position = ?, fileindex = ? where foldername = ?', (seek_time, file_index, folder_name))
        conn.commit()

    def add_item(self, path, item_id):
        logging.warning("Adding path %s to items file" % path)
        self.tree.getroot().append(ET.Element(tag='item', attrib={'id': "%s" % item_id, 'path': path, 'type': 'book', 'desc': path}))
        self.tree.write(self.list_file, encoding='UTF-8')

    def check_list(self, data_dir):
        checklist = {}
        for item_id in self.items:
            if self.items[item_id]['type'] != 'radio':
                checklist[self.items[item_id]['path']] = item_id
        max_item_id = max(self.items.keys()) + 1
        for d in os.listdir(data_dir):
            dir_name = os.path.join(data_dir, d)
            if os.path.isdir(dir_name):
                files = os.listdir(dir_name)
                mp3_found = False
                for f in files:
                    if os.path.isdir(os.path.join(dir_name, f)):
                        logging.error("Item folder %s contains subdirectories." % d)
                        break
                    name, ext = os.path.splitext(f)
                    if ext.lower() == '.mp3':
                        mp3_found = True
                        if dir_name in checklist:
                            del checklist[dir_name]
                            break
                        else:
                            self.add_item(d, max_item_id)
                            max_item_id += 1
                            break
                if not mp3_found:
                    logging.error("Subdirectory %s contains no mp3 files" % d)
        for cl in checklist:
            logging.error("Path %s present in item xml file, but not found on disk" % cl)
            del self.items[checklist[cl]]

    def read_list(self, list_file, data_dir):
        self.items = {}
        self.list_file = list_file
        self.tree = ET.parse(list_file)
        itemmap = self.tree.getroot()
        for item in itemmap:
            if False in [x in item.attrib for x in ['id', 'desc', 'type', 'path']] :
                logging.error("Item does not have one of the required attributes")
                continue
            item_id = int(item.attrib['id'])
            self.items[item_id] = copy.deepcopy(item.attrib)
            del self.items[item_id]['id']
            if self.items[item_id]['type'] != 'radio':
                self.items[item_id]['path'] = os.path.join(data_dir, self.items[item_id]['path'])
        logging.info('Items loaded')
        logging.debug(self.items)
        self.check_list(data_dir)


if __name__ == "__main__":
    os.chdir(os.path.dirname(__file__))
    ##logging.config.fileConfig('logging.conf')
    logging.basicConfig(filename='../data/main.log', level=logging.WARNING)
    #logging.basicConfig(level=logging.INFO)
    fout = open('../data/stdout.log', 'a')
    ferr = open('../data/stderr.log', 'a')
    fout.write("---------------------------------------\n**** %s\n" % time.asctime())
    ferr.write("---------------------------------------\n**** %s\n" % time.asctime())
    sys.stdout = fout
    sys.stderr = ferr
    print 'Starting'
    dispatcher = Dispatcher()
    dispatcher.start()
    os.system("sudo shutdown -h now")

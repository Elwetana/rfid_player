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
import os, time, sys
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

    def create_worker(self, worker_name, worker_class, needs_pipe, needs_queue):
        if needs_pipe:
            to_worker, from_worker = multiprocessing.Pipe()
            if needs_queue:
                self.workers[worker_name] = worker_class(from_worker, self.msg_queue)
            else:
                self.workers[worker_name] = worker_class(from_worker)
            self.pipes[worker_name] = to_worker
        else:
            self.workers[worker_name] = worker_class(self.msg_queue)
        self.workers[worker_name].start()

    def start(self):
        self.msg_queue = multiprocessing.Queue()
        self.create_worker('key_listener', KeyListener, False, True)
        self.create_worker('led_control', LedControl, True, False)
        self.create_worker('volume_control', VolumeControl, True, False)
        self.create_worker('player', Player, True, True)
        self.create_worker('rfid_reader', RfidReader, True, True)

        lastval = None 
        while True:
            msg,val = self.msg_queue.get()
            if msg == 'rfid':
                logging.info("RFID message received, value: %s" % val)
                self.pipes['led_control'].send(('ack',0))
                #if time.time() - self.time > 3: #to avoid accidental multiple scans
                if lastval != val or self.state != State.playing:
                    if val in self.items:
                        self.time = time.time()
                        self.state = State.playing
                        self.pipes['player'].send(('play',self.items[val]))
                        lastval = val
                    else:
                        logging.error("RFID value not present in list of items")
                else:
                    logging.info("Ignoring accidental scan")
            elif msg == 'save_pos':
                self.save_pos(*val)
            elif msg == 'player_started':
                if val:
                    self.pipes['led_control'].send(('play','radio'))
                else:
                    self.pipes['led_control'].send(('play','local'))
            elif msg == 'player_stopped':
                self.state = State.stopped
                self.pipes['led_control'].send(('stop',0))
            elif msg == 'next':
                self.pipes['led_control'].send(('ack',0))
                logging.info('Message next receieved')
                self.pipes['player'].send(('next',0))
            elif msg == 'prev':
                self.pipes['led_control'].send(('ack',0))
                logging.info('Message prev receieved')
                self.pipes['player'].send(('prev',0))
            elif msg == 'stop':
                self.pipes['led_control'].send(('ack',0))
                logging.info('Trying to stop the player')
                self.pipes['player'].send(('stop',0))
            elif msg == 'vol_up':
                self.pipes['led_control'].send(('ack',0))
                logging.info('Volume up')
                self.pipes['volume_control'].send(('up', 5))
            elif msg == 'vol_down':
                self.pipes['led_control'].send(('ack',0))
                logging.info('Volume down')
                self.pipes['volume_control'].send(('down', 5))
            elif msg == 'quit':
                self.pipes['led_control'].send(('ack',0))
                self.workers['key_listener'].join()
                for worker in self.workers:
                    if worker != 'key_listener':
                        logging.warning('Trying to terminate the %s' % worker)
                        self.pipes[worker].send(('quit',0))
                        self.workers[worker].join()
                break
            else:
                logging.info("Unknown message: %s" % msg)
        logging.warning('Terminating')

    def save_pos(self, seek_time, file_index, folder_name):
        logging.debug("Saving position")
        conn = sqlite3.connect('player.db')
        conn.execute('update lastpos set position = ?, fileindex = ? where foldername = ?', (seek_time, file_index, folder_name))
        conn.commit()

    def add_item(self, path):
        #todo -- read data folder, add new subfolders to list file
        pass
        #newkey = max(self.cards.values()) + 1
        #print "Adding card rfid: %s, id: %s" % (rfid, newkey)
        #self.tree.getroot().append(ET.Element(tag='card', attrib={'rfid': rfid, 'key': "%s" % newkey}))
        #self.tree.write(self.cardmap_file, encoding='UTF-8')
        #self.cards[rfid] = newkey

    def read_list(self, list_file, data_dir):
        self.items = {}
        self.tree = ET.parse(list_file)
        itemmap = self.tree.getroot()
        for item in itemmap:
            item_id = int(item.attrib['id'])
            del item.attrib['id']
            self.items[item_id] = item.attrib
            if self.items[item_id]['type'] != 'radio':
                self.items[item_id]['path'] = os.path.join(data_dir, self.items[item_id]['path'])
        logging.info('Items loaded')
        logging.debug(self.items)


if __name__ == "__main__":
    os.chdir(os.path.dirname(__file__))
    logging.basicConfig(filename='../data/main.log', level=logging.INFO)
    fout = open('../data/stdout.log', 'a')
    ferr = open('../data/stderr.log', 'a')
    fout.write("---------------------------------------\n**** %s\n" % time.asctime())
    ferr.write("---------------------------------------\n**** %s\n" % time.asctime())
    sys.stdout = fout
    sys.stderr = ferr
    print 'Starting'
    dispatcher = Dispatcher()
    dispatcher.start()

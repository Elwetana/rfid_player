#!/usr/bin/python

import multiprocessing
#from multiprocessing.managers import BaseManager
import xml.etree.ElementTree as ET
import logging
from keyinput import KeyListener
from player import Player
from volume import VolumeControl
from reader import RfidReader
import os, time
import sqlite3

class State:
    playing = 1
    stopped = 2

class Dispatcher:

    def __init__(self, list_file = '../data/list.xml', data_dir = '../data/'):
        self.read_list(list_file, data_dir)
        self.state = State.stopped
        self.time = 0

    def start(self):
        msg_queue = multiprocessing.Queue()
        key_listener = KeyListener(msg_queue)
        key_listener.start()
        
        self.to_player, from_player = multiprocessing.Pipe()
        self.player = Player(from_player, msg_queue)
        self.player.start()

        self.to_volume, from_volume = multiprocessing.Pipe()
        self.volume_control = VolumeControl(from_volume)
        self.volume_control.start()

        self.to_reader, from_reader = multiprocessing.Pipe()
        self.rfid_reader = RfidReader(from_reader, msg_queue)
        self.rfid_reader.start()

        lastval = None 
        while True:
            msg,val = msg_queue.get()
            if msg == 'rfid':
                logging.info("RFID message received, value: %s" % val)
                #if time.time() - self.time > 3: #to avoid accidental multiple scans
                if lastval != val:
                    if val in self.items:
                        self.time = time.time()
                        self.state = State.playing
                        self.to_player.send(('play',self.items[val]))
                        lastval = val
                    else:
                        logging.error("RFID value not present in list of items")
                else:
                    logging.info("Ignoring accidental scan")
            elif msg == 'save_pos':
                self.save_pos(*val)
            elif msg == 'player_stopped':
                self.state = State.stopped
            elif msg == 'next':
                logging.info('Message next receieved')
                self.to_player.send(('next',0))
            elif msg == 'prev':
                logging.info('Message prev receieved')
                self.to_player.send(('prev',0))
            elif msg == 'stop':
                logging.info('Trying to stop the player')
                self.to_player.send(('stop',0))
            elif msg == 'vol_up':
                logging.info('Volume up')
                self.to_volume.send(('up', 5))
            elif msg == 'vol_down':
                logging.info('Volume down')
                self.to_volume.send(('down', 5))
            elif msg == 'quit':
                logging.warning('Trying to terminate the player')
                self.to_player.send(('quit',0))
                self.player.join()
                logging.warning('Trying to terminate the volume control')
                self.to_volume.send(('quit',0))
                self.volume_control.join()
                logging.warning('Trying to terminate the rfid reader')
                self.to_reader.send(('quit',0))
                self.rfid_reader.join()
                break
            else:
                logging.info("Unknown message: %s" % msg)
        logging.warning('Terminating')
        key_listener.join()

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
    logging.basicConfig(filename='../data/main.log', level=logging.INFO)
    print 'Starting'
    dispatcher = Dispatcher()
    dispatcher.start()

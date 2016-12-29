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
from http_server import HttpServer
from ws_server import WebSocketServer
import os, time, sys, copy
import sqlite3
import json

class State:
    playing = 1
    stopped = 2

class Dispatcher:

    def __init__(self, list_file = 'list.xml', local_dir = '../data/', remote_dir = '/mnt/z/Audio/_audio_books/_pi'):
        self.list_file = list_file
        self.local_dir = local_dir
        self.remote_dir = remote_dir
        self.tree = {}
        self.items = {}
        self.init_list()
        self.state = State.stopped
        self.time = 0
        self.workers = {}
        self.pipes = {}
        self.lastval = -1
        self.actions = {
            'rfid': self.msg_rfid,
            'key': self.msg_keys,
            'player': self.msg_player,
            'save_pos': self.msg_savepos,
            'http': self.msg_http,
            'ws': self.msg_ws
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
        self.create_worker('http_server', HttpServer, True, True)
        self.create_worker('websocket_server', WebSocketServer, True, True)

        while True:
            msg = self.msg_queue.get()
            logging.info("Message of type %s received" % msg.msg_type)
            if msg.needs_ack:
                self.pipes['led_control'].send(('ack',0))
            if self.actions.get(msg.msg_type, self.msg_unknown)(msg):
                logging.warning("Terminate message received")
                break
        self.workers['key_listener'].join() #tohle nefunguje, kdyz terminate msg. prijde ze serveru, protoze key_listener porad ceka
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

    def msg_http(self, msg):
        logging.debug("Http message with value %s processing" % msg.value)
        if msg.value == 'terminate':
            logging.info("Program terminated by HTTP request")
            return True
        if msg.value == 'reload_items':
            logging.info("Reloading the item list")
            self.read_list()
        if msg.value == 'reread_cards':
            logging.info("Rereading cards")
            self.pipes['rfid_reader'].send(('reread',0))
        return False

    def msg_ws(self, msg):
        logging.debug("WS message with value %s received" % msg.value)
        if msg.value == 'get_items':
            self.pipes['websocket_server'].send(('broadcast', json.dumps(["items", self.items])))
        if msg.value == 'get_cards':
            self.pipes['rfid_reader'].send(('get_cards', ''))
            i = 0
            while not(self.pipes['rfid_reader'].poll()):
                time.sleep(0.1)
                i += 1
                if i > 50: # we have waited 5 seconds
                    logger.error("Reader did not return cards")
                    self.pipes['websocket_server'].send(('broadcast', json.dumps(['error', 'cards not available'])))
                    return
            cmnd = self.pipes['rfid_reader'].recv()
            self.pipes['websocket_server'].send(('broadcast', cmnd[1]))
        if msg.value == 'update_item':
            update_data = msg.payload
            if update_data['id'] in self.items:
                self.update_item(update_data['path'], update_data['id'], update_data['desc'], self.remote_dir)
                if self.items[update_data['id']]['local']:
                    self.update_item(update_data['path'], update_data['id'], update_data['desc'], self.local_dir)
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

    def update_item(self, path, item_id, desc, data_dir):
        logging.warning("Updating book info about item with path %s" % path)
        root = self.tree[data_dir].getroot()
        books = [x for x in root if x.attrib['path'] == path]
        if len(books) > 1:
            logging.error("More than one book at path %s" % path)
            return
        if len(books) == 0:
            logging.error("Cannot find book at path %s" % path)
        book = books[0]
        book.attrib['id'] = "%s" % item_id
        book.attrib['desc'] = desc
        self.tree[data_dir].write(os.path.join(data_dir, self.list_file), encoding='UTF-8')

    def add_item(self, path, item_id, data_dir):
        path = unicode(path, 'utf-8')
        logging.warning("Adding path %s to items file in dir %s" % (path, data_dir))
        self.tree[data_dir].getroot().append(ET.Element(tag='item', attrib={'id': "%s" % item_id, 'path': path, 'type': 'book', 'desc': path}))
        self.tree[data_dir].write(os.path.join(data_dir, self.list_file), encoding='UTF-8')

    def check_list(self, data_dir, items):
        checklist = {}
        for item_id in items:
            if items[item_id]['type'] != 'radio':
                checklist[items[item_id]['path']] = item_id
        max_item_id = 0
        if len(items) > 0:
            max_item_id = max(items.keys()) + 1
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
                        d = unicode(d, 'utf-8')
                        if d in checklist:
                            del checklist[d]
                            break
                        else:
                            self.add_item(d, max_item_id, data_dir)
                            max_item_id += 1
                            break
                if not mp3_found:
                    logging.error("Subdirectory %s contains no mp3 files" % d)
        for cl in checklist:
            logging.error("Path %s present in item xml file, but not found on disk" % cl)
            del items[checklist[cl]]

    def read_list(self, data_dir):
        items = {}
        self.tree[data_dir] = ET.parse(os.path.join(data_dir, self.list_file))
        itemmap = self.tree[data_dir].getroot()
        for item in itemmap:
            if False in [x in item.attrib for x in ['id', 'desc', 'type', 'path']] :
                logging.error("Item does not have one of the required attributes")
                continue
            item_id = int(item.attrib['id'])
            items[item_id] = copy.deepcopy(item.attrib)
            del items[item_id]['id']
            #if items[item_id]['type'] != 'radio':
            #   items[item_id]['path'] = os.path.join(data_dir, items[item_id]['path'])
        logging.info('Items loaded from path %s' % data_dir)
        self.check_list(data_dir, items)
        return items

    def init_list(self):
        items = {}
        for k,v in {'local': self.local_dir, 'remote': self.remote_dir}.iteritems():
            items[k] = self.read_list(v)
        paths = {}
        for p in ['local', 'remote']:
            paths[p] = {items[p][k]['path']: k for k in items[p]}
        self.items = {k: dict(items['local'][k], local=True) for k in items['local']}

        """
        if rem_path exists locally and rem_id == loc_id and all data match ==> OK
        if rem_path exists locally and rem_id == loc_id and data do not match ==> update local xml with info from remote
        if rem_path exists locally and rem_id != loc_id ==>
            if rem_id is not occupied locally ==> update local xml file with info from remote
            if rem_id is used locally ==> push local record to new id, update xml file
        if rem_path does not exist locally =>
            if rem_id is not occupied locally ==> add info about remote file
            if rem_id is used locally ==> push local record to new id, update xml file
        """
        max_item_id = 1
        if len(self.items) > 0:
            max_item_id = max(self.items.keys()) + 1
        for mp3_path in paths['remote']:
            rem_id = paths['remote'][mp3_path]
            if mp3_path in paths['local']:
                loc_id = paths['local'][mp3_path]
                if loc_id != rem_id:
                    # we must check if the rem_id is already taken or not
                    if rem_id in self.items:
                        self.items[max_item_id] = self.items[rem_id]
                        paths['local'][self.items[rem_id]['path']] = max_item_id
                        max_item_id += 1
                    self.items[rem_id] = self.items[loc_id]
                    paths['local'][mp3_path] = rem_id
                    del self.items[loc_id]
            else:
                if rem_id in self.items:
                    # remote id is already taken
                    self.items[max_item_id] = self.items[rem_id]
                    paths['local'][self.items[rem_id]['path']] = max_item_id
                    max_item_id += 1
                self.items[rem_id] = dict(items['remote'][rem_id], local=False)
        # now check all local info whether it was changed or not
        old_local_paths = {items['local'][k]['path']: k for k in items['local']}
        for mp3_path in paths['local']:
            old_id = old_local_paths[mp3_path]
            cur_id = paths['local'][mp3_path]
            if cur_id != old_id or self.items[cur_id]['desc'] != items['local'][old_id]['desc']:
                self.update_item(path=mp3_path, item_id=cur_id,
                                 desc=self.items[cur_id]['desc'],
                                 data_dir=self.local_dir)
        # print "consolidated items", self.items

if __name__ == "__main__":
    os.chdir(os.path.dirname(__file__))
    ##logging.config.fileConfig('logging.conf')
    logging.basicConfig(format='%(asctime)s - %(name)s %(levelname)s: %(message)s',
                        filename='../data/main.log', level=logging.DEBUG)
    #logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.error("====================== START ===========================")
    fout = open('../data/stdout.log', 'a')
    ferr = open('../data/stderr.log', 'a')
    fout.write("---------------------------------------\n**** %s\n" % time.asctime())
    ferr.write("---------------------------------------\n**** %s\n" % time.asctime())
    #sys.stdout = fout
    #sys.stderr = ferr
    print 'Starting'
    dispatcher = Dispatcher()
    dispatcher.start()
    os.system("sudo shutdown -h now")

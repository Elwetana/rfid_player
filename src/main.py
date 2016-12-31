#!/usr/bin/python

"""
TODO:
[x] cardmap, read remote, update local
[x] if new card scanned, create desc, update both local and global cardmap, send message to ws server
[x] when item updated on web, update list.xml

[ ] copy remote item to local when required
[x] refactor read_items, just read the global list, if available, then check what is local
[x] verify that the local copy matches the remote (check copying errors)
[ ] updates from browser should be broadcast to other clients (or all clients and browser should recognize it as confirmation)
"""

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
        self.remote_present = False
        self.tree = {}
        self.items = None
        self.item_verification = None
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
        logging.info("RFID message received, action: %s, value: %s" % (msg.action, msg.value))
        if msg.action == "scan":
            if (self.lastval != msg.value) or (self.state != State.playing):
                if msg.value in self.items:
                    self.play_item(msg.value)
                else:
                    logging.error("RFID value not present in list of items")
            else:
                logging.info("Ignoring accidental scan")
            return False
        if msg.action == "new":
            self.pipes['websocket_server'].send(('new_card', json.dumps({"item_id": msg.value, "hid": msg.hid})))
            return False
        logging.error("Unknown RFID action %s" % msg.action)
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
            self.update_item(update_data['path'], update_data['id'], update_data['desc'])
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

    def update_item(self, path, item_id, desc):
        """
        Actually, we choose the item by path, and update item_id!
        :param path:
        :param item_id:
        :param desc:
        :return:
        """""
        logging.warning("Updating book info about item with path %s" % path)
        root = self.tree.getroot()
        books = [x for x in root if x.attrib['path'] == path]
        if len(books) > 1:
            logging.error("More than one book at path %s" % path)
            return
        if len(books) == 0:
            logging.error("Cannot find book at path %s" % path)
        book = books[0]
        orig_id = int(book.attrib['id'])
        self.items[item_id] = self.items[orig_id]
        self.items[item_id]['desc'] = desc
        book.attrib['id'] = "%s" % item_id
        book.attrib['desc'] = desc
        if self.remote_present:
            self.tree.write(os.path.join(self.remote_dir, self.list_file), encoding='UTF-8')
        self.tree.write(os.path.join(self.local_dir, self.list_file), encoding='UTF-8')

    def add_item(self, path, item_id):
        path = unicode(path, 'utf-8')
        logging.warning("Adding path %s to items file" % path)
        self.items[item_id] = {'path': path, 'desc': path, type: 'book'}
        self.tree.getroot().append(ET.Element(tag='item', attrib={'id': "%s" % item_id, 'path': path, 'type': 'book', 'desc': path}))
        if self.remote_present:
            self.tree.write(os.path.join(self.remote_dir, self.list_file), encoding='UTF-8')
        self.tree.write(os.path.join(self.local_dir, self.list_file), encoding='UTF-8')

    def handle_verifications(self):
        """
        Now we only log errors, maybe once we shall copy files from remote to local
        :return: None
        """
        for d in self.item_verification:
            d_uni = unicode(d, encoding='utf-8')
            for name in self.item_verification[d]:
                name_uni = unicode(name, encoding='utf-8')
                if 'error' in self.item_verification[d][name]:
                    logger.error("Item checking error in dir %s, file %s: %s" % (d_uni, name_uni, self.item_verification[d][name]['error']))
                else:
                    if not self.item_verification[d][name]['verified']:
                        logger.error("Size mismatch between local and remot in dir %s, file %s" % (d_uni, name_uni))

    def check_list(self, data_dir):
        """
        Verify that the folders actually exist, contain mp3 files, add new directories to the list
        When checking the remote dir, gather data about file sizes and then use it to verify the
        local data.
        :param data_dir: where to look
        :return: None
        """
        is_remote = (data_dir == self.remote_dir)
        checklist = {}
        for item_id in self.items:
            if self.items[item_id]['type'] != 'radio':
                checklist[self.items[item_id]['path']] = item_id
        max_item_id = 0
        if len(self.items) > 0:
            max_item_id = max(self.items.keys()) + 1
        for d in os.listdir(data_dir):
            if is_remote: # we shall be verifying the local dir later
                self.item_verification[d] = {}
            dir_name = os.path.join(data_dir, d)
            if not os.path.isdir(dir_name): # this is true for logs and XML files in data dir
                continue
            files = os.listdir(dir_name)
            mp3_found = False
            for f in files:
                if os.path.isdir(os.path.join(dir_name, f)):
                    logging.error("Item folder %s contains subdirectories." % d)
                    break
                name, ext = os.path.splitext(f)
                if ext.lower() == '.mp3':
                    mp3_found = True
                    if is_remote:
                        self.item_verification[d][name] = {'size': os.path.getsize(f), 'verified': False}
                    else:
                        if self.item_verification is not None:
                            if name in self.item_verification[d]:
                                self.item_verification[d][name]['verified'] = (os.path.getsize(f) == self.item_verification[d][f]['size'])
                            else:
                                self.item_verification[d][name] = {'error': 'extra file on local'}
            if mp3_found:
                d_uni = unicode(d, 'utf-8')
                if d_uni in checklist:
                    del checklist[d_uni]
                else:
                    if is_remote or not self.remote_present:
                        self.add_item(d_uni, max_item_id)
                        max_item_id += 1
                    else:
                        logger.error("Local item not available on remote: %s" % d_uni)
            else:
                logging.error("Subdirectory %s contains no mp3 files" % d)
        for cl in checklist:
            if is_remote or not self.remote_present:
                logging.error("Path %s present in item xml file, but not found on disk" % cl)
                del self.items[checklist[cl]]
            else:
                self.items[checklist[cl]]['local'] = False

    def read_list(self, data_dir):
        self.tree = ET.parse(os.path.join(data_dir, self.list_file))
        itemmap = self.tree.getroot()
        for item in itemmap:
            if False in [x in item.attrib for x in ['id', 'desc', 'type', 'path']] :
                logging.error("Item does not have one of the required attributes")
                continue
            item_id = int(item.attrib['id'])
            self.items[item_id] = copy.deepcopy(item.attrib)
            self.items[item_id]['local'] = True
            del self.items[item_id]['id']
        logging.info('Items loaded from path %s' % data_dir)

    def init_list(self):
        """
        Read and verify the remote item list if available. In this case, verify the local data with respect to the
         remote, and mark items missing locally as remote. If remote item list is not available, read local data,
         do local verification.
        :return: None
        """
        self.items = {}
        if os.path.exists(os.path.join(self.remote_dir, self.list_file)):
            self.remote_present = True
            self.item_verification = {}
            self.read_list(self.remote_dir)
            self.check_list(self.remote_dir)
            self.check_list(self.local_dir)
            self.handle_verifications()
            self.tree.write(os.path.join(self.local_dir, self.list_file), encoding='UTF-8')
        else:
            self.read_list(self.local_dir)
            self.check_list(self.local_dir)


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

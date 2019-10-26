#!/usr/bin/python

import serial, sys
import multiprocessing
import xml.etree.ElementTree as ET
import logging
from message import Msg
import json
import os.path
from config import READER, PATHS

logger = logging.getLogger(__name__)

class ReaderMsg(Msg):

    def __init__(self, action, rfid_data, human_readable_id=0):
        self.msg_type = 'rfid'
        self.action = action
        self.value = rfid_data
        self.hid = human_readable_id
        self.needs_ack = True

class RfidReader(multiprocessing.Process):

    rfidPort = READER.rfidPort
    baudrate = READER.baudrate
    timeout = READER.timeout

    def __init__(self, pipe, msg_queue, local_dir=PATHS.local_root, remote_dir=PATHS.remote_root,
                 cardmap_file='cardmap.xml'):
        multiprocessing.Process.__init__(self)
        self.pipe = pipe
        self.msg_queue = msg_queue
        self.local_dir = local_dir
        self.remote_dir = remote_dir
        self.cardmap_file = cardmap_file
        self.cards = None
        self.read_cards()

    def run(self):
        self.ser = serial.Serial()
        self.ser.baudrate = self.baudrate
        self.ser.port = self.rfidPort
        self.ser.timeout = self.timeout

        self.ser.open()
        if self.ser.isOpen():
            logger.warning("Open: " + self.ser.portstr)
        logger.warning("RFID reader reading")
        try:
            self.ser.flushInput()
            start_flag = "\x02"
            end_flag = "\x03"
            while True:
                c = self.ser.read()
                if c == start_flag:
                    c = ''
                    rfidData = ''
                    counter = 0
                    while c != end_flag and c != start_flag and counter < 13:
                        c = self.ser.read()
                        rfidData += str(c)
                        counter += 1
                    if counter != 13:
                        continue
                    rfidData = rfidData.replace(end_flag, '')
                    if not(self.verify_checksum(rfidData)):
                        continue
                    logger.info("Card Scanned: %s" % rfidData)
                    if rfidData in self.cards:
                        self.msg_queue.put(ReaderMsg("scan", self.cards[rfidData], self.get_card_id(rfidData)))
                    else:
                        logger.info("Adding new card")
                        self.add_card(rfidData)
                        self.msg_queue.put(ReaderMsg("new", self.cards[rfidData], self.get_card_id(rfidData)))
                if self.pipe.poll():
                    cmnd = self.pipe.recv()
                    logger.debug("Reader received message %s" % cmnd[0])
                    if cmnd[0] == 'reread':
                        self.read_cards()
                    if cmnd[0] == 'get_cards':
                        cards_id = {rfid : dict(item_id=self.cards[rfid], hid=self.get_card_id(rfid)) for rfid in self.cards}
                        self.pipe.send(('cards', json.dumps(['cards', cards_id])))
                    if cmnd[0] == 'quit':
                        break
        except:
            #logger.error("error: %s" % sys.exc_info())
            print sys.exc_info()

        finally:
            self.ser.close()
        logger.warning("RFID reader terminating")

    def clean_rfid(self, data):
        d = ""
        for c in data[1:-1]:
            if (c < '0') or (c > 'F'):
                logger.error("Removed invalid character from rfid data")
                continue
            d += c
        return d

    def verify_checksum(self, rfid):
        if len(rfid) != 12:
            return False
        checksum = 0
        for i in range(0, 9, 2):
            checksum = checksum ^ (((int(rfid[i], 16)) << 4) + int(rfid[i + 1], 16))
        return checksum == (int(rfid[10], 16) << 4) + int(rfid[11], 16)

    def get_card_id(self, rfid):
        return int(rfid[4:10], 16)

    def add_card(self, rfid):
        self.read_cards()
        newkey = max(self.cards.values()) + 1
        logger.warning("Adding card rfid: %s, id: %s" % (rfid, newkey))
        self.tree.getroot().append(ET.Element(tag='card', attrib={
            'desc': "card %s" % self.get_card_id(rfid),
            'rfid': rfid,
            'key': "%s" % newkey
        }))
        self.tree.write(os.path.join(self.local_dir, self.cardmap_file), encoding='UTF-8')
        if os.path.exists(os.path.join(self.remote_dir, self.cardmap_file)):
            self.tree.write(os.path.join(self.remote_dir, self.cardmap_file), encoding='UTF-8')
        self.cards[rfid] = newkey

    def read_cardmap_file(self, cardmap_file):
        self.tree = ET.parse(cardmap_file)
        cardmap = self.tree.getroot()
        for card in cardmap:
            self.cards[card.attrib['rfid']] = int(card.attrib['key'])
        logger.info('Card map loaded')

    def read_cards(self):
        self.cards = {}
        if os.path.exists(os.path.join(self.remote_dir, self.cardmap_file)):
            self.read_cardmap_file(os.path.join(self.remote_dir, self.cardmap_file))
            self.tree.write(os.path.join(self.local_dir, self.cardmap_file), encoding='UTF-8')
        else:
            self.read_cardmap_file(os.path.join(self.local_dir, self.cardmap_file))

    def check_cards(self):
        for card in self.cards:
            is_valid = self.verify_checksum(card)
            name = "invalid"
            if is_valid:
                name = self.get_card_id(card)

if __name__ == "__main__":
    print "RFID card reader class"
    logging.basicConfig(level=logging.INFO)
    msg_queue = multiprocessing.Queue()
    to_worker, from_worker = multiprocessing.Pipe()
    reader = RfidReader(from_worker, msg_queue)
    reader.start()

    import time
    reader.check_cards()
    to_worker.send(('get_cards', ''))
    i = 0
    while not(to_worker.poll()):
        time.sleep(0.1)
        i += 1
        if i > 50: # we have waited 5 seconds
            print "Reader did not return cards"
            sys.exit(1)
    cmnd = to_worker.recv()
    print cmnd
    while True:
        msg = msg_queue.get()
        print msg.value


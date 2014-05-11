#!/usr/bin/python

import serial, sys
import multiprocessing
import xml.etree.ElementTree as ET
import logging
from message import Msg

logger = logging.getLogger("root.reader")

class ReaderMsg(Msg):

    def __init__(self, rfid_data):
        self.msg_type = 'rfid'
        self.value = rfid_data
        self.needs_ack = True

class RfidReader(multiprocessing.Process):

    rfidPort = "/dev/ttyAMA0"
    baudrate = 9600
    timeout = 0.1

    def __init__(self, pipe, msg_queue, cardmap_file = '../data/cardmap.xml'):
        multiprocessing.Process.__init__(self)
        self.pipe = pipe
        self.msg_queue = msg_queue
        self.read_cards(cardmap_file)

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
            while True:
                self.ser.flushInput()
                rfidData = self.ser.readline().strip()
                if len(rfidData) > 0:
                    rfidData = self.clean_rfid(rfidData)
                    logger.info("Card Scanned: %s" % rfidData)
                    if rfidData in self.cards:
                        self.msg_queue.put(ReaderMsg(self.cards[rfidData]))
                    else:
                        logger.info("Adding new card")
                        self.add_card(rfidData)
                if self.pipe.poll():
                    cmnd = self.pipe.recv()
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

    def add_card(self, rfid):
        newkey = max(self.cards.values()) + 1
        logger.warning("Adding card rfid: %s, id: %s" % (rfid, newkey))
        self.tree.getroot().append(ET.Element(tag='card', attrib={'rfid': rfid, 'key': "%s" % newkey}))
        self.tree.write(self.cardmap_file, encoding='UTF-8')
        self.cards[rfid] = newkey

    def read_cards(self, cardmap_file):
        self.cards = {}
        self.cardmap_file = cardmap_file
        self.tree = ET.parse(cardmap_file)
        cardmap = self.tree.getroot()
        for card in cardmap:
            self.cards[card.attrib['rfid']] = int(card.attrib['key'])
        logger.info('Card map loaded')
        logger.debug(self.cards)

if __name__ == "__main__":
    print "RFID card reader class"
    logging.basicConfig(level=logging.INFO)
    msg_queue = multiprocessing.Queue()
    to_worker, from_worker = multiprocessing.Pipe()
    reader = RfidReader(from_worker, msg_queue)
    reader.start()
    while True:
        msg = msg_queue.get()
        print msg.value


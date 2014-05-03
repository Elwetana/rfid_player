#!/usr/bin/python

import serial, sys
import multiprocessing
import xml.etree.ElementTree as ET
import logging

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
            logging.warning("Open: " + self.ser.portstr)
        logging.warning("RFID reader reading")
        try:
            while True:
                self.ser.flushInput()
                rfidData = self.ser.readline().strip()
                if len(rfidData) > 0:
                    rfidData = rfidData[1:-1]
                    logging.info("Card Scanned: %s" % rfidData)
                    if rfidData in self.cards:
                        self.msg_queue.put(('rfid',self.cards[rfidData]))
                    else:
                        logging.info("Adding new card")
                        self.add_card(rfidData)
                if self.pipe.poll():
                    cmnd = self.pipe.recv()
                    if cmnd[0] == 'quit':
                        break
        except:
            logging.error("error: %s" % sys.exc_info())

        finally:
            self.ser.close()
        logging.warning("RFID reader terminating")

    def add_card(self, rfid):
        newkey = max(self.cards.values()) + 1
        logging.info("Adding card rfid: %s, id: %s" % (rfid, newkey))
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
        logging.info('Card map loaded')
        logging.debug(self.cards)

if __name__ == "__main__":
    print "RFID card reader class"

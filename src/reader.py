#!/usr/bin/python

import serial, sys
import multiprocessing
import xml.etree.ElementTree as ET

class RfidReader(multiprocessing.Process):

    rfidPort = "/dev/ttyAMA0"
    baudrate = 9600
    timeout = 0.1

    def __init__(self, pipe, msg_queue, cardmap_file = '../data/cardmap.xml'):
        multiprocessing.Process.__init__(self)
        self.debug = 3
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
            print "Open: " + self.ser.portstr
        print "Reading"
        try:
            while True:
                self.ser.flushInput()
                rfidData = self.ser.readline().strip()
                if len(rfidData) > 0:
                    rfidData = rfidData[1:-1]
                    if self.debug > 2:
                        print "Card Scanned: ", rfidData
                    if rfidData in self.cards:
                        self.msg_queue.put(('rfid',self.cards[rfidData]))
                    else:
                        if self.debug > 2:
                            print "Adding new card"
                        self.add_card(rfidData)
                if self.pipe.poll():
                    cmnd = self.pipe.recv()
                    if cmnd[0] == 'quit':
                        break
        except:
            print "error:", sys.exc_info()

        finally:
            self.ser.close()
        print "RFID reader terminating"

    def add_card(self, rfid):
        newkey = max(self.cards.values()) + 1
        if self.debug > 2:
            print "Adding card rfid: %s, id: %s" % (rfid, newkey)
        self.tree.getroot().append(ET.Element(tag='card', attrib={'rfid': rfid, 'key': "%s" % newkey}))
        self.tree.write(self.cardmap_file, encoding='UTF-8')
        self.cards[rfid] = newkey

    def update_cards(self, name, attrs):
        if name == "card":
            self.cards[attrs['rfid']] = attrs['key']

    def read_cards(self, cardmap_file):
        self.cards = {}
        self.cardmap_file = cardmap_file
        self.tree = ET.parse(cardmap_file)
        cardmap = self.tree.getroot()
        for card in cardmap:
            self.cards[card.attrib['rfid']] = int(card.attrib['key'])
        print 'Card map loaded'
        if self.debug > 2:
            print self.cards

if __name__ == "__main__":
    print "RFID card reader class"

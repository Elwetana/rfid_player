#!/usr/bin/python

import multiprocessing
from multiprocessing.managers import BaseManager
from keyinput import KeyListener
from player import Player
from volume import VolumeControl
from reader import RfidReader
import time


class Dispatcher:

    def __init__(self):
        pass
        #BaseManager.__init__(self)
#        self.player = player
#        player.play("/usr/local/lib/p_data/stin.mp3")

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

        while True:
            msg,val = msg_queue.get()
            if msg == 'next':
                print 'Message next receieved'
                self.to_player.send(('play','../data/stin/'))
            elif msg == 'stop':
                print 'Trying to stop the player'
                self.to_player.send(('stop',0))
            elif msg == 'quit':
                print 'Trying to terminate the player'
                self.to_player.send(('quit',0))
                self.player.join()
                print 'Trying to terminate the volume control'
                self.to_volume.send(('quit',0))
                self.volume_control.join()
                print 'Trying to terminate the rfid reader'
                self.to_reader.send(('quit',0))
                self.rfid_reader.join()
                break
            else:
                print 'Unknown message:', msg
        print 'Terminating'
        key_listener.join()

if __name__ == "__main__":
    print 'Starting'
    dispatcher = Dispatcher()
    dispatcher.start()

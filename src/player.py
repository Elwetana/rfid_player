#!/usr/bin/python

import multiprocessing
from time import sleep
from message import Msg
import sys
import sqlite3, os, subprocess, socket
import os.path
import xml.etree.ElementTree as ET
import logging
import urlparse
import vlc

logger = logging.getLogger(__name__)

class PlayerMsg(Msg):

    def __init__(self, state, is_radio = False):
        self.msg_type = 'player'
        self.value = state
        self.is_radio = is_radio

class SavePosMsg(Msg):

    def __init__(self, value):
        self.msg_type = 'save_pos'
        self.value = value

class Player(multiprocessing.Process):

    def __init__(self, pipe, msg_queue, ui_file = '../data/ui.xml'):
        multiprocessing.Process.__init__(self)
        self.pipe = pipe
        self.msg_queue = msg_queue
        self.read_ui(ui_file)

    def run(self):
        self.fest_process = subprocess.Popen(['festival', '--server'],stdout=subprocess.PIPE)
        l = self.fest_process.stdout.readline() #this just blocks until the server starts
        self.fest = socket.socket()
        self.fest.connect(('localhost',1314))
        self.folder_name = ''
        logger.warning("Player running")
        while True:
            if self.pipe.poll(None):
                cmnd = self.pipe.recv()
                if cmnd[0] == 'start':
                    self.folder_name = cmnd[1]['path']
                    self.entity_type = cmnd[1]['type']
                    self.entity_desc = cmnd[1]['desc']
                    self.root_folder = cmnd[1]['root']
                    self.isRadio = (self.entity_type == 'radio')
                    self.set_seek_time()
                    self.play()
                elif cmnd[0] == 'stop':
                    pass
                elif cmnd[0] == 'play':
                    if self.folder_name != '':
                        self.play(False)
                elif cmnd[0] == 'next_track':
                    if self.folder_name != '':
                        self.file_index += 1
                        self.seek_time = 0
                        self.play()
                elif cmnd[0] == 'prev_track':
                    if self.folder_name != '':
                        if self.seek_time < 10000:
                            self.file_index -= 1
                        self.seek_time = 0
                        self.play()
                elif cmnd[0] == 'ff':
                    if self.folder_name != '':
                        self.seek_time += 30000
                        self.play(False)
                elif cmnd[0] == 'bb':
                    if self.folder_name != '':
                        self.seek_time -= 30000
                        if self.seek_time < 0:
                            self.seek_time = 0
                        self.play(False)
                elif cmnd[0] == 'quit':
                    break
                else:
                    logger.error("Invalid message for player: %s" % cmnd[0])
                self.msg_queue.put(PlayerMsg('stopped'))
        self.fest.close()
        self.fest_process.kill()
        logger.warning('Player terminating')

    def set_seek_time(self):
        #get last played position
        if self.isRadio:
            self.seek_time, self.file_index = 0, 0
            return True
        conn = sqlite3.connect('player.db')
        row = conn.execute('select * from lastpos where foldername = ?', (self.folder_name,)).fetchone()
        file_index = 0
        seek_time = 0
        if row is None:
            logger.warning('creating record for %s in lastpos database' % self.folder_name)
            conn.execute('insert into lastpos (foldername, fileindex, position, completed) values (?, ?, ?, ?)', (self.folder_name, 0, 0, 0))
        else:
            file_index = row[1]
            seek_time = row[2]
            logger.warning('Resuming file %s in %s from %s' % (file_index, self.folder_name, seek_time))
        logger.debug('Updating last_seen')
        conn.execute('update lastpos set last_seen = CURRENT_TIMESTAMP;')
        conn.commit()
        self.seek_time, self.file_index = seek_time, file_index
        return True

    def get_radio_file(self):
        url = self.folder_name
        scheme, netloc, path, params, query, fragment = urlparse.urlparse(url)
        try:
            host, port = netloc.split(':')
        except ValueError:
            host, port = netloc, 80
        if not path:
            path = '/'
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, int(port)))
        sock.send('GET %s HTTP/1.0\r\n\r\n' % path)
        reply = sock.recv(1500)
        logger.info("Radio server says: %s" % repr(reply))
        logger.info("Prepared radio file. Scheme: %s, host: %s, port: %s, path: %s:" % (scheme, host, port, path))
        return sock.makefile()

    def get_audio_file(self, files):
        if self.file_index > len(files): #this happens when the whole folder was played. In this case we just restart from beginning
            self.file_index = len(files) - 1
        if self.file_index < 0: #this happens when prev is pressed too many times
            self.file_index = 0
        f = os.path.join(self.root_folder, self.folder_name, files[self.file_index])
        logger.info("Audio file to be played: %s" % f)
        return f

    def get_files(self):
        if self.isRadio:
            return ['']
        files = os.listdir(os.path.join(self.root_folder, self.folder_name))
        files.sort()
        return files

    def play(self, do_speak = True):
        logger.info("Getting ready to play")
        files = self.get_files()
        if do_speak:
            self.speak(self.seek_time, self.file_index)
        why_stopped = 'finished'
        if self.file_index >= len(files): # this can happen if we e.g. remove files from the directory
            self.file_index = 0
        while self.file_index < len(files) and why_stopped == 'finished':
            logger.info("opening MediaPlayer")
            if self.isRadio:
                f = self.get_radio_file()
            else:
                f = self.get_audio_file(files)
            try:
                mp = vlc.MediaPlayer(f)
                mp.play()
            except VLCException:
                logger.error("Error opening file %s for playing" % f)
                break
            logger.info("seeking file")
            if self.seek_time > 10000L: # we start a little bit before the actual last time, for context
                mp.set_time(self.seek_time - 10000L)
            status = mp.get_state()
            if not(status == vlc.State.Opening or status == vlc.State.Playing):
                logger.fatal("Cannot open file %s" % f)
                break
            while not status == vlc.State.Playing:
                sleep(1)
                status = mp.get_state()
            iSave = 0
            why_stopped = 'finished'
            logger.info("Starting to play")
            self.msg_queue.put(PlayerMsg('started', self.isRadio))
            while mp.is_playing():
                sleep(1)
                if not self.isRadio:
                    iSave += 1
                    self.seek_time = mp.get_time()
                    if iSave == 10:
                        self.msg_queue.put(SavePosMsg((self.seek_time, self.file_index, self.folder_name)))
                        # self.save_pos()
                        iSave = 0
                if self.pipe.poll():
                    mp.stop()
                    self.save_pos()
                    why_stopped = 'message'
            if why_stopped == 'finished':
                self.seek_time = 0
                self.file_index += 1

    def save_pos(self):
        if not self.isRadio:
            logger.info("Saving position")
            conn = sqlite3.connect('player.db')
            conn.execute('update lastpos set position = ?, fileindex = ? where foldername = ?', (self.seek_time, self.file_index, self.folder_name))
            conn.commit()
            #if we finished the last track, we shall mark it as complete (this is purely statistical, is not used by the program)
            if (self.seek_time == 0) and (self.file_index == len(files)):
                conn.execute('update lastpos set completed = completed + 1 where foldername = ?', (self.folder_name, ))
                conn.commit()

    def speak(self, seek_time, file_index):
        # Message:
        # for books: <desc> <chapter index> "chapter" <"from beginning" | "from start">
        # for music: <desc> <track index> "track"
        # for radio: "radio" <desc>
        msg = ""
        number = u""
        if file_index < 0: #happens when prev message was received too many times. Should be probably fixed elsewhere
            file_index = 0
        if file_index < 20:
            number = self.ui['numbers']["%s" % (file_index + 1)]
        elif file_index < 999:
            if file_index == 99:
                number = u"{cent}".format(cent = self.ui['numbers']['100th'])
            else:
                hund_index = ((file_index + 1) // 100) * 100
                tens_index = ((file_index + 1) // 10) * 10 
                ones_index = ((file_index + 1) % 10)
                if hund_index > 0:
                    number = u"{hund} ".format(hund = self.ui['numbers']["%s" % hund_index])
                if ones_index == 0:
                    number += u"{tens}".format(tens = self.ui['numbers']["%s" % tens_index])
                else:
                    number += u"{tens} {ones}".format(tens = self.ui['numbers']["%s" % tens_index], ones = self.ui['numbers']["%s" % ones_index])
        if self.entity_type == 'book':
            msg_cont = u"{play} {start}.".format(play = self.ui['states']['play'], start = self.ui['states']['start'])
            if seek_time > 0:
                msg_cont = u"{cont}.".format(cont = self.ui['states']['cont'])
            msg = u"{desc}. {index} {chapter}. {m}".format(desc = self.entity_desc, index = number, chapter = self.ui['entities']['chapter'], m = msg_cont)
        elif self.entity_type == 'music':
            msg = u"{desc}. {index} {track}".format(desc = self.entity_desc, index = number, track = self.ui['entities']['track'])
        elif self.entity_type == 'radio':
            msg = u"{radio} {desc}".format(radio = self.ui['entities']['radio'], desc = self.entity_desc)
        else:
            logger.error("Invalid entity type: %s in player" % self.entity_type)
        logger.info("Msg: %s" % msg)
        msg = u"(SayText \"{msg}\")".format(msg = msg)
        self.fest.sendall('(audio_mode \'sync)')
        data = self.fest.recv(1024)
        self.fest.sendall(msg.encode('iso-8859-2'))
        data = self.fest.recv(1024)
        logger.info("Festival server replied %s" % data)

    def read_ui_segment(self, ui_root, segment, lang):
        segment_root = ui_root.find(segment)
        self.ui[segment] = {}
        for node in segment_root:
            self.ui[segment][node.get('id')] = node.find('txt').get(lang)

    def read_ui(self, ui_file):
        self.ui = {}
        self.tree = ET.parse(ui_file)
        ui = self.tree.getroot()
        lang = ui.find('lang').get('default')
        self.read_ui_segment(ui, 'numbers', lang)
        self.read_ui_segment(ui, 'states', lang)
        self.read_ui_segment(ui, 'entities', lang)
        logger.info('UI map read')
        logger.debug(self.ui)

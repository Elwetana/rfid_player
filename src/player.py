#!/usr/bin/python
import multiprocessing
import mad, ao, sys
import sqlite3, os

class Player(multiprocessing.Process):

    def __init__(self, pipe, msg_queue):
        multiprocessing.Process.__init__(self)
        self.debug = 1
        self.pipe = pipe
        self.msg_queue = msg_queue

    def run(self):
        while True:
            if self.pipe.poll(None):
                cmnd = self.pipe.recv()
                if cmnd[0] == 'play':
                    self.folder_name = cmnd[1]
                    self.play()
                    self.msg_queue.put('player_stopped')
                if cmnd[0] == 'quit':
                    break
        print 'Player terminating'

    def play(self):
        #get last played position
        conn = sqlite3.connect('player.db')
        row = conn.execute('select * from lastpos where foldername = ?', (self.folder_name,)).fetchone()
        file_index = 0
        seek_time = 0
        if row is None:
            if self.debug > 0:
                print 'creating record for %s in lastpos database' % self.file_name
            with conn:
                conn.execute('insert into lastpos (foldername, fileindex, position) values (?, ?)', (self.folder_name, 0, 0))
        else:
            file_index = row[1]
            seek_time = row[2]
            if self.debug > 0:
                print 'Resuming file %s in %s from %s' % (file_index, self.folder_name, seek_time)
        #now we know which file to play and from when
        files = os.listdir(self.folder_name)
        files.sort()
        if file_index > len(files): #this happens when the whole folder was played. In this case we just restart from beginning
            file_index = 0
        why_stopped = 'finished'
        while file_index < len(files) and why_stopped == 'finished':
            mf = mad.MadFile(os.path.join(self.folder_name,files[file_index]))
            if seek_time > 5000:  #seeking is broken a bit, we have to flush the buffer by reading
                mf.seek_time(seek_time - 5000)
                for i in range(100):
                    mf.read()
            dev = ao.AudioDevice('alsa', rate=mf.samplerate())
            iSave = 0
            why_stopped = ''
            if self.debug > 0:
                print 'Starting to play', files[file_index]
            while True:
                buf = mf.read()
                #print len(buf) #4608
                if (buf is None) or self.pipe.poll():
                    if buf is None:
                        why_stopped = 'finished'
                    break
                dev.play(buf, len(buf))
                #it would be good to be able to write, but it would have to be a different thread
                #iSave += 1
                #if iSave == 100:
                #    with conn:
                #        conn.execute('update lastpos set position = ? where filename = ?', (mf.current_time(), self.file_name))
                #    print 'updating position in db'
                #    iSave = 0
            seek_time = mf.current_time()
            if why_stopped == 'finished':
                seek_time = 0
                file_index += 1
            conn.execute('update lastpos set position = ?, fileindex = ? where foldername = ?', (seek_time, file_index, self.folder_name))
            conn.commit()


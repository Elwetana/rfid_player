#!/usr/bin/python

import sys
import multiprocessing
import SocketServer
import BaseHTTPServer
import logging
import sqlite3
import os
from message import Msg

import WebSocketServer


logger = logging.getLogger("root.reader")

class HttpMsg(Msg):

    def __init__(self, http_data):
        self.msg_type = 'http'
        self.value = http_data
        self.needs_ack = True

class HttpHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    configRoot = '/opt/rp_play/http'
    msgMap = {
            '/terminate' : 'terminate',
            '/reload' : 'reload_items',
            '/reread' : 'reread_cards'
            }
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        if self.path in HttpHandler.msgMap:
            self.server.msg_queue.put(HttpMsg(HttpHandler.msgMap[self.path]))
        self.path = '/index.html'
        f = open(HttpHandler.configRoot + self.path)
        html = f.read()
        f.close()
        #replace the 'template tag' {LastposTable} with table data
        html = html.replace('{LastposTable}', self.getLastposTable())
        self.wfile.write(html)

    def getLastposTable(self):
        html = ''
        html += '<table>\n'
        html += '<tr><th>Folder</th><th>File Index</th><th>Position</th><th>Completed</th><th>File Count</th></tr>\n'
        conn = sqlite3.connect(os.path.join(self.configRoot, '../src/player.db'))
        rows = conn.execute('select foldername, fileindex, position, completed from lastpos;')
        for row in rows.fetchall():
            try:
                files = os.listdir(os.path.join(self.configRoot, row[0]))
            except OSError: #this happens when the book was deleted
                continue
            html += '<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>\n' % (row[0][7:], row[1], row[2], row[3], len(files))
        html += '</table>\n'
        return html

class HttpServer(multiprocessing.Process):

    serverPort = 80
    timeout = 0.1

    def __init__(self, pipe, msg_queue):
        multiprocessing.Process.__init__(self)
        self.pipe = pipe
        self.msg_queue = msg_queue

    def run(self):
        self.server = BaseHTTPServer.HTTPServer(('',HttpServer.serverPort), HttpHandler)
        self.server.timeout = HttpServer.timeout
        self.server.msg_queue = self.msg_queue

        try:
            while True:
                self.server.handle_request()
                if self.pipe.poll():
                    cmnd = self.pipe.recv()
                    if cmnd[0] == 'quit':
                        break
        except:
            #logger.error("error: %s" % sys.exc_info())
            print sys.exc_info()

        logger.warning("HTTP server terminating")

class SimpleEcho(WebSocketServer.WebSocket):

    def handleMessage(self):
        # echo message back to client
        print "*",
        self.sendMessage(self.data)
        self.server.msg_queue.put(HttpMsg(self.data))

    def handleConnected(self):
        print self.address, 'connected'

    def handleClose(self):
        print self.address, 'closed'

    def broadcast(self, message):
        self.sendMessage(message)



if __name__ == "__main__":
    print "HTTP server class"
    logging.basicConfig(level=logging.INFO)
    msg_queue = multiprocessing.Queue()
    to_worker, from_worker = multiprocessing.Pipe()
    server = WebSocketServer.SimpleWebSocketServer('192.168.88.181', 8000, SimpleEcho, from_worker, msg_queue)
    # server = HttpServer(from_worker, msg_queue)
    server.start()
    while True:
        msg = msg_queue.get()
        print msg.value


#!/usr/bin/python

import sys
import multiprocessing
import BaseHTTPServer
import logging
import sqlite3
import os
import codecs
from message import HttpMsg
from config import WS_SERVER, PATHS

logger = logging.getLogger(__name__)


class HttpHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    configRoot = '../http'
    dataRoot = '../data'
    msgMap = {
            '/terminate': 'terminate',
            '/reload':    'reload_items',
            '/reread':    'reread_cards'
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
        # replace the 'template tag' {LastposTable} with table data
        html = html.replace('{LastposTable}', self.getLastposTable())
        html = html.replace('{ws_address}', WS_SERVER.ws_address)
        html = html.replace('{ServerName}', WS_SERVER.server_name)
        self.wfile.write(html)

    def getLastposTable(self):
        html = '<p>Last positions</p>\n'
        html += '<table>\n'
        html += '<tr><th>Folder</th><th>File Index</th><th>Position</th><th>Completed</th><th>File Count</th></tr>\n'
        conn = sqlite3.connect(os.path.join(self.dataRoot, '../src/player.db'))
        rows = conn.execute('select foldername, fileindex, position, completed from lastpos;')
        for row in rows.fetchall():
            n_files = -1
            try:
                files = os.listdir(os.path.join(PATHS.local_root, row[0]))
                n_files = len(files)
            except OSError:  # this happens when the book was deleted
                n_files = -2
            if n_files == -2:
                try:
                    files = os.listdir(os.path.join(PATHS.remote_root, row[0]))
                    n_files = len(files)
                except OSError:
                    n_files = -3
            html += '<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>\n' % \
                    (codecs.encode(row[0],"utf8"), row[1], row[2], row[3], n_files)
        html += '</table>\n'
        return html


class HttpServer(multiprocessing.Process):

    serverPort = 80
    timeout = 0.1

    def __init__(self, pipe, msg_queue):
        multiprocessing.Process.__init__(self)
        self.pipe = pipe
        self.msg_queue = msg_queue
        self.server = None

    def run(self):
        self.server = BaseHTTPServer.HTTPServer(('', HttpServer.serverPort), HttpHandler)
        self.server.timeout = HttpServer.timeout
        self.server.msg_queue = self.msg_queue
        logger.warning("HTTP server running")
        try:
            while True:
                self.server.handle_request()
                if self.pipe.poll():
                    cmnd = self.pipe.recv()
                    if cmnd[0] == 'quit':
                        break
        except:
            print sys.exc_info()

        logger.warning("HTTP server terminating")

if __name__ == "__main__":
    print "HTTP server class"
    logging.basicConfig(level=logging.INFO)
    msg_queue = multiprocessing.Queue()
    to_worker, from_worker = multiprocessing.Pipe()
    server = HttpServer(from_worker, msg_queue)
    server.start()
    while True:
        msg = msg_queue.get()
        print "Received message from server:", msg.value


#!/usr/bin/python

import sys
import multiprocessing
import SocketServer
import BaseHTTPServer
import logging
from message import Msg

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
        self.wfile.write(f.read())
        f.close()


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

if __name__ == "__main__":
    print "HTTP server class"
    logging.basicConfig(level=logging.INFO)
    msg_queue = multiprocessing.Queue()
    to_worker, from_worker = multiprocessing.Pipe()
    server = HttpServer(from_worker, msg_queue)
    server.start()
    while True:
        msg = msg_queue.get()
        print msg.value


#!usr/bin/python

class Msg:
    msg_type = 'Base'
    value = ''
    needs_ack = False

class HttpMsg(Msg):

    def __init__(self, http_data):
        self.msg_type = 'http'
        self.value = http_data
        self.needs_ack = True

class WebsocketMsg(Msg):
    def __init__(self, ws_data, payload = None):
        self.msg_type = 'ws'
        self.value = ws_data
        self.payload = payload
        self.needs_ack = False
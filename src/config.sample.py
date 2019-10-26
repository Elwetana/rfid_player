#!/usr/bin/python

import socket

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.168.88.254', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

class READER:
    rfidPort = "/dev/ttyAMA0"
    baudrate = 9600
    timeout = 0.1


class WS_SERVER:
    ip_address = get_local_ip()
    ws_address = 'ws://%s:8000' % ip_address
    server_name = 'BIG BOX'

class PATHS:
    local_root = '../data'
    remote_root = '/mnt/z/Audio/_audio_books/_pi'


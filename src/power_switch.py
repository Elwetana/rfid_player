#!/usr/bin/python

import multiprocessing
from message import Msg
import RPi.GPIO as GPIO
import logging

logger = logging.getLogger(__name__)

class PowerMsg(Msg):

    def __init__(self):
        self.msg_type = 'power'
        self.action = 'quit' 


class PowerSwitch(multiprocessing.Process):

    def __init__(self, pipe, msg_queue):
        multiprocessing.Process.__init__(self)
        self.pipe = pipe
        self.msg_queue = msg_queue
        self.gpio_pin = 3
        self.timeout = 100

    def run(self):
        logger.warning("Power switch controller running")
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        while True:
            channel = GPIO.wait_for_edge(self.gpio_pin, GPIO.FALLING, timeout=self.timeout)
            if channel is not None:
                logger.warning("Power switch edge detected")
                self.msg_queue.put(PowerMsg())
            if self.pipe.poll():
                logger.info("power switch message received")
                cmnd = self.pipe.recv()
                if cmnd[0] == 'quit':
                    break
                else:
                    logger.error("Message not recognized for power switch module: %s" % cmnd[0])

        logger.warning('Terminating Power Switch')

if __name__ == "__main__":
    print "PowerSwitch class"

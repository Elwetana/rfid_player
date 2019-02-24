#!/usr/bin/python

import multiprocessing
import RPi.GPIO as GPIO
import os, time
import logging

logger = logging.getLogger(__name__)

class LedControl(multiprocessing.Process):

    def __init__(self, pipe):
        multiprocessing.Process.__init__(self)
        self.pipe = pipe
        self.pins = {'green2': 11, 'yellow2': 13, 'red1': 15}
        self.flash_interval = 0.1
        self.blink_interval = 0.25

    def run(self):
        self.init_pins()
        self.stop_led()
        self.is_playing = ''
        self.play_on = False
        logger.warning("Led controller running")
        while True:
            if self.pipe.poll(self.blink_interval):
                logger.info("led message received")
                cmnd = self.pipe.recv()
                if cmnd[0] == 'quit':
                    self.set_led_on_quit()
                    break
                elif cmnd[0] == 'ack':
                    self.ack()
                elif cmnd[0] == 'play':
                    logger.info("Led to play as %s" % cmnd[1])
                    self.is_playing = cmnd[1]
                    self.play_led()
                elif cmnd[0] == 'stop':
                    logger.info("led to play stop")
                    self.is_playing = ''
                    self.play_on = False
                    self.stop_led()
                else:
                    logger.error("Message not recognized for led module: %s" % cmnd[0])
            if self.is_playing != '':
                self.play_led()

        logger.warning('Terminating Led Controler')

    def init_pins(self):
        GPIO.setmode(GPIO.BOARD) ## Use board pin numbering
        for pin in self.pins:
            GPIO.setup(self.pins[pin], GPIO.OUT) ## Setup GPIO Pin 7 to OUT

    def ack(self):
        GPIO.output(self.pins['red1'], True)
        time.sleep(self.flash_interval)
        GPIO.output(self.pins['red1'], False)

    def stop_led(self):
        GPIO.output(self.pins['yellow2'], False)
        GPIO.output(self.pins['green2'], True)

    def play_led(self):
        if self.play_on:
            GPIO.output(self.pins['yellow2'], False)
            GPIO.output(self.pins['green2'], False)
        else:
            GPIO.output(self.pins['yellow2'], self.is_playing == 'radio')
            GPIO.output(self.pins['green2'], self.is_playing == 'local')
        self.play_on = not self.play_on

    def set_led_on_quit(self):
        GPIO.output(self.pins['yellow2'], False)
        GPIO.output(self.pins['green2'], False)
        GPIO.output(self.pins['red1'], True)

    def blink_red(self):
        GPIO.output(self.pins['red1'], True)
        time.sleep(1)
        GPIO.output(self.pins['red1'], False)

    def blink_yellow(self):
        GPIO.output(self.pins['yellow2'], True)
        time.sleep(1)
        GPIO.output(self.pins['yellow2'], False)


    def blink_green(self):
        GPIO.output(self.pins['green2'], True)
        time.sleep(1)
        GPIO.output(self.pins['green2'], False)

if __name__ == "__main__":
    print "LedControl class"
    logging.basicConfig(level=logging.INFO)
    to_pipe, from_pipe = multiprocessing.Pipe()
    ledControl = LedControl(to_pipe)
    ledControl.init_pins()
    ledControl.blink_red()
    ledControl.blink_yellow()
    ledControl.blink_green()


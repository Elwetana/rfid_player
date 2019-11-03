#!/usr/bin/python

import RPi.GPIO as GPIO
import curses
from time import sleep

pins = {'green2':  {'pin': 11, 'pos': 3, 'pair': 1},
        'yellow2': {'pin': 13, 'pos': 4, 'pair': 2},
        'red1':    {'pin': 15, 'pos': 7, 'pair': 3}}

GPIO.setmode(GPIO.BOARD)
for pin in pins:
    GPIO.setup(pins[pin]['pin'], GPIO.OUT)

stdscr = curses.initscr()
curses.cbreak()
# win = curses.newwin(5, 16, 0, 0)
curses.start_color()
curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
curses.curs_set(0)
stdscr.timeout(10)

i = 0
while True:
    for pin in pins:
        v = GPIO.input(pins[pin]['pin'])
        if v == 0:
            npair = 0
        else:
            npair = pins[pin]['pair']
    #    print v,
        # stdscr.addstr(3, pins[pin]['pos'], u'\u25c9', curses.color_pair(npair))
        stdscr.addstr(3, pins[pin]['pos'], '@', curses.color_pair(npair))
    #print
    #stdscr.addstr(3, 10, str(i), curses.color_pair(3))
    stdscr.refresh()
    i += 1
    if i > 9:
        i = 0
    c = stdscr.getch()
    if c == ord('q'):
        break

curses.curs_set(1)
curses.nocbreak()
curses.endwin()

#RFID audio player

*Audio player for Raspberry Pi, controlled by RFID tags, focused on reading audio books, intended for people who are blind or visually impaired*

##About

My mother-in-law suffers from macular degeneration (AMD) and as a result she can read for all practical purposes nothing at all. She also cannot control any devices with tiny buttons and even tinier displays, like iPod or any other MP3 players. There are audio players for blind/visually impaired people but these are quite expensive and still rely on keys as a primary means of input. This means that if you have a library of say 20 audiobooks (not too big), you have to press up or down arrow ten times to get the the item you need.

I wanted to create a simple player that could be controlled by RFID tags. These tags are cheap and recyclable. They can be brightly colored (or have Braille on them) and each tag can be made to correspond to one item: a book, a music album or an Internet radio.

The person using the device simply selects the tag that he wants to listen to, swipes it across the box and it starts playing. I am using Festival text-to-speech to synthetize the name of the book/item to be played to provide audio feedback to this action.

I got a simple air mouse on DX.com and I am using it as a sort of remote control: the listener can use it to skip tracks, move forward or backward, control volume, stop the player or turn it off.

The program also runs a simple HTTP server that can be accessed from another computer and used to manage data: add or remove books and cards.

##Schematics

The wiring is very simple. RDM630 RFID reader is connected to pin 10 (RxD). Three pins control LEDs that indicate function: two LEDs indicate playing/standing (one for radio, other for locally accessed playback), one indicates input (scanning a card, pressing a key on controller), one is always on power indicator.

The schematics is in file schema.svg and schema.png in this folder.

##Dependencies

* libao: there is a bug in libao alsa plugin for current Raspbian (Wheezy). See this link: http://stackoverflow.com/questions/8963915/libao-example-doesnt-work-when-compiled-as-python-module
* evdev: https://github.com/gvalkov/python-evdev
* festival/festvox
* pymad: https://github.com/jaqx0r/pymad (NB: do not use pip for this, as there is another package called mad; clone jaqx0r's repository and run setup; do apt-get install libmad0-dev beforehand)

##Conclusion
If you find this idea interesting to you, please drop me a line. Thank you.

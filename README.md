#RFID audio player

*Audio player for Raspberry Pi, controlled by RFID tags, focused on reading audio books, intended for people who are blind or visually impaired*

##Dependencies

* libao: there is a bug in libao alsa plugin for current Raspbian (Wheezy). See this link: http://stackoverflow.com/questions/8963915/libao-example-doesnt-work-when-compiled-as-python-module
* evdev: https://github.com/gvalkov/python-evdev
* festival/festvox
* pymad

#!/usr/bin/python

import sqlite3

con = sqlite3.connect('player.db')
con.execute("drop table if exists lastpos")
con.execute("create table lastpos (foldername varchar primary key, fileindex integer, position integer)")
con.commit()

for row in con.execute("select * from lastpos"):
    print row

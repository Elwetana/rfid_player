#!/usr/bin/python

import sqlite3

con = sqlite3.connect('player.db')
#con.execute("drop table if exists lastpos")
#con.execute("create table lastpos (foldername varchar primary key, fileindex integer, position integer, completed integer)")
con.execute('alter table lastpos add column last_seen varchar')
con.execute('update lastpos set last_seen = \'2000-01-01 00:00:01\'')
con.commit()

for row in con.execute("select * from lastpos"):
    print row

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2010, 2011 The ghack Authors. All rights reserved.
# Use of this source code is governed by the GNU General Public License
# version 3 (or any later version). See the file COPYING for details.

"""
A game class, which renders game state for the player and handles
player input. All input state changes are sent to an external service,
which is responsible for updating the game's state in response, and
implementing the actual gameplay logic
"""

import curses
import sys
import os

from debug import debug
from objects import Entity, Vector

class HealthBar:
    def __init__(self, capacity = 10, width = 12):
        self.cap = max(1, capacity)
        self.width = max(1, width)
        self.update(0)

    def update(self, value):
        self.value = value if value != None else 0
        cap = max(1, self.cap)
        val = min(self.value, cap)
        fill = int(round(val / float(cap) * (self.width - 2)))
        self.bar = '[' + '#' * fill + ' ' * (self.width - 2 - fill) + ']'

    def set_capacity(self, capacity):
        self.cap = capacity if capacity != None else 0

    def set_width(self, width):
        self.width = max(1, width)

    def __str__(self):
        return str(self.bar)

class Game(object):
    def __init__(self, name):
        self.name = name
        self.entities = {}
        self.direction = Vector()
        self.healthbar = HealthBar()
        self.player = None
        self.HUD_WIDTH = 30
        self.MSG_LINES = 5 # num lines for message area
        self.messages = []
        self.kills = 0

        self._init_curses()

    def _init_curses(self):
        self.scr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        curses.start_color()
        self.scr.keypad(1)

        curses.curs_set(0)
        self.scr.nodelay(1)	# Make getch() non-blocking
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_YELLOW)
        curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_RED)
        self.create_hud()

    def update(self, elapsed_seconds):
        """Runs every frame"""
        self.running = True
        self.redraw()
        self._handle_input()

    def add_entity(self, id, name=None):
        if id in self.entities:
            debug("Entity id %d added twice" % id)
        self.entities[id] = Entity(id, name)

    def remove_entity(self, id, name=None):
        if id not in self.entities:
            debug("Entity id %d removed without being added" % id)
            return
        del self.entities[id]

    def update_entity(self, id, state_id, value=None):
        if id not in self.entities:
            debug("Entity id %d updated without being added" % id)
            return
        self.entities[id].set_state(state_id, value)
        self.redraw()

    def assign_control(self, uid, revoked):
        self.player = uid if not revoked else None

    def entity_death(self, uid, name, kuid, kname):
        if kuid == self.player:
            self.add_message("You killed %s!" % name)
            self.kills += 1
        else:
            self.add_message("%s was killed by %s!" % (name, kname))

    def combat_hit(self, auid, aname, vuid, vname, damage):
        self.add_message("%s hit %s for %d damage!" % (aname, vname, damage))

    def get_player(self):
        if self.player != None:
            if self.entities.has_key(self.player):
                return self.entities[self.player]
        return None

    def create_hud(self):
        y,x = self.scr.getmaxyx()
        try:
            self.hudwin = curses.newwin(5,self.HUD_WIDTH,1,x-self.HUD_WIDTH-1)
            self.hudwin.nodelay(1)
            self.msgwin = curses.newwin(self.MSG_LINES,x-2,y-self.MSG_LINES-1,1)
            self.msgwin.nodelay(1)
        except curses.error:
            sys.stderr.write("HUD cannot be created!\n")
        self.add_message("You have entered Spider Forest") # :D

    def draw_hud(self, player):
        hp = maxhp = 1

        if 'MaxHealth' in player.states:
            maxhp = int(round(player.states['MaxHealth']))
        if 'Health' in player.states:
            hp = int(round(player.states['Health']))

        hplen = len(str(hp))
        maxhplen = len(str(maxhp))
        hpstrlen = maxhplen * 2 + 1
        pct = hp / float(maxhp)
        hpcolor = 3 if pct < 0.33 else (2 if pct < 0.66 else 1)

        self.healthbar.set_capacity(maxhp)
        self.healthbar.update(hp)
        self.healthbar.set_width(self.HUD_WIDTH - 11 - hpstrlen)
        self.hudwin.erase()
        try:
            self.hudwin.addstr(1,1,"Health:",curses.color_pair(1) | curses.A_BOLD)
            self.hudwin.addstr(1,9+maxhplen-hplen,str(hp),curses.color_pair(hpcolor))
            self.hudwin.addstr(1,9+maxhplen,"/"+str(maxhp),curses.color_pair(1))
            self.hudwin.addstr(1,10+hpstrlen,str(self.healthbar),curses.color_pair(1))
            self.hudwin.addstr(2,1,"Kills:",curses.color_pair(1)| curses.A_BOLD)
            self.hudwin.addstr(2,9,str(self.kills),curses.color_pair(1))
            self.hudwin.border()
        except curses.error:
            sys.stderr.write("HUD cannot be drawn!\n")
        self.hudwin.noutrefresh()

    def draw_messages(self):
        self.msgwin.erase()
        try:
            for i, msg in enumerate(self.messages):
                y = self.MSG_LINES - i - 1
                self.msgwin.addstr(y, 0, msg, curses.color_pair(1))
        except curses.error:
            sys.stderr.write("Failed to draw message area\n")
        self.msgwin.noutrefresh()

    def add_message(self, msg):
        self.messages.insert(0, msg)
        if len(self.messages) > self.MSG_LINES:
            self.messages.pop()

    def redraw(self):
        #print "%d Entities:" % len(self.entities)
        self.scr.erase()
        def in_bounds(x,y):
            by,bx = self.scr.getbegyx()
            my,mx = self.scr.getmaxyx()
            return bx<x<mx and by<y<my

        def restrict(x,lower,upper):
            return min(max(lower,x),upper)

        offsety = offsetx = 0
        maxy, maxx = self.scr.getmaxyx()
        midy, midx = maxy/2, maxx/2
        player = self.get_player()
        if player and 'Position' in player.states:
            pos = player.states['Position']
            offsety,offsetx = midy-pos.y,midx-pos.x


        for entity in self.entities.values():
            #print(entity.name, entity.states)
            if entity.states.has_key('Position'):
                pos = entity.states['Position']
                if entity.states.has_key('Asset'):
                    asset = entity.states['Asset']
                    #self.scr.addstr(int(pos.y),int(pos.x), '⩕⎈☸⨳⩕⩖⩕@', curses.color_pair(4))
                    posx = pos.x + offsetx
                    posy = pos.y + offsety
                    color = 4
                    if 'Health' in entity.states and 'MaxHealth' in entity.states:
                        hp = entity.states['Health']
                        maxhp = entity.states['MaxHealth']
                        pct = hp / float(maxhp)
                        color = 6 if pct < 0.33 else (5 if pct < 0.66 else 4)
                    if in_bounds(posx,posy):
                        try:
                            self.scr.addstr(int(posy),int(posx), asset, curses.color_pair(color))
                        except curses.error:
                            sys.stderr.write("Failed to draw asset %s at y,x=%d,%d\n" %
                                (asset, int(posy), int(posx)))
        self.scr.border()
        try:
            self.scr.addstr(0,max(midx-9,0),"GHack SpiderForest",curses.color_pair(1))
        except curses.error:
            print("oh no!")

        self.scr.noutrefresh()
        if player:
            self.draw_hud(player)
        self.draw_messages()
        curses.doupdate()

    def _handle_input(self):
        ch = self.scr.getch()
        # Cardinal directions
        if ch == curses.KEY_UP or ch == ord('k') or ch == ord('8'):
            self.move(0,-1)
        elif ch == curses.KEY_DOWN or ch == ord('j') or ch == ord('2'):
            self.move(0,1)
        elif ch == curses.KEY_LEFT or ch == ord('h') or ch == ord('4'):
            self.move(-1,0)
        elif ch == curses.KEY_RIGHT or ch == ord('l') or ch == ord('6'):
            self.move(1,0)
        # Diagonals
        elif ch == curses.KEY_HOME or ch == ord('y') or ch == ord('7'):
            self.move(-1,-1)
        elif ch == curses.KEY_PPAGE or ch == ord('u') or ch == ord('9'):
            self.move(1,-1)
        elif ch == curses.KEY_NPAGE or ch == ord('b') or ch == ord('1'):
            self.move(-1,1)
        elif ch == curses.KEY_END or ch == ord('n') or ch == ord('3'):
            self.move(1,1)
        # Others
        elif ch == curses.KEY_RESIZE:
            self.create_hud()
        elif ch == ord('g'):
            for entity in self.entities.values():
                sys.stderr.write(str(entity.id) + str(entity.name)+str(entity.states)+"\n")
        elif ch == ord('q'):
            self.running = False

    def move(self, x, y):
        """Sending commands is weird. For now, just save it somewhere for
        the network to pick up
        """

        self.direction = Vector(x, y)

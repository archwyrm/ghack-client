#!/usr/bin/env python

# Copyright 2010, 2011 The ghack Authors. All rights reserved.
# Use of this source code is governed by the GNU General Public License
# version 3 (or any later version). See the file COPYING for details.

import struct
import sys

from proto import protocol_pb2 as ghack_pb2
import netclient
import messages
from debug import debug
from game.objects import Vector

"""
Client:
    Holds a client connection to the game server. 
"""

class Client(object):
    def __init__(self, game):
        self.game = game
        self.conn = None
        self.handler = None
        self.version = 1
        self.connected = False

    def run(self):
        """Start the client connection"""
        self.connect()

    def update(self, elapsed_seconds):
        """Runs every frame"""
        if self.game.direction.len_squared() > 0:
            self.send(messages.move(self.game.direction))
            self.game.direction = Vector()

    def handle(self, msg):
        """
        Handle messages. Needs to be replaced with more generic handler
        objects for the various states, and soon
        """
        debug("<<", msg)
        if self.handler:
            self.handler.handle_msg(msg)
        else:
            debug("No handler for message, ignoring")


    def connect(self):
        """Do the client-server handshake"""
        connect = messages.connect(self.version)
        self.handler = ConnectHandler(self)
        self.send(connect)

    def disconnect(self):
        "Disconnect from the server"
        disconnect = messages.disconnect(ghack_pb2.Disconnect.QUIT,
                "Client disconnected")
        self.handler = None
        self.send(disconnect)

        self.conn.close()

    def send(self, msg):
        "Send a message to the server"
        debug(">>", msg)
        msg_bytes = msg.SerializeToString()
        self.conn.send_bytes(struct.pack('H', len(msg_bytes)))
        self.conn.send_bytes(msg_bytes)

class Handler(object):
    """
    Client state is implemented in message handlers.

    A complicated Handler defines a mapping of type -> function in
    handlers, which don't have to worry about unwrapping messages or
    splitting logic.

    Handlers can also define a list of expected message types that are
    passed (with the wrapping Message intact) to handle()
    """
    def __init__(self, client):
        self.client = client

    expected_types = []
    handlers = {}

    def handle_msg(self, msg):
        """Handle a message"""
        if msg.type in self.handlers:
            handler = self.handlers[msg.type](self)
            handler(self.client, messages.unwrap(msg))
        elif msg.type in self.expected_types:
            self.handle(self.client, msg)
        else:
            self.unexpected(msg)


    def unexpected(self, msg):
        """Handle an unexpected message"""
        try:
            s = str(msg)
            print >> sys.stderr, "Unexpected message:", s
        except KeyError:
            print >> sys.stderr, "Unknown message, ignoring"

class ConnectHandler(Handler):
    """Handles the server's connect reply"""
    expected_types = [ghack_pb2.Message.CONNECT]
    def handle(self, client, msg):
        connect = msg.connect

        if connect.version != client.version:
            sys.stderr.write("Version strings do not match\n")
            client.close()

        login = messages.login(client.game.name)
        client.handler = LoginResultHandler(client)
        client.send(login)

class LoginResultHandler(Handler):
    expected_types = [ghack_pb2.Message.LOGINRESULT]
    def handle(self, client, msg):
        login_result = msg.login_result

        if not login_result.succeeded:
            sys.stderr.write("Login failed: " +
                    LOGIN_FAILS[login_result.reason])
            client.close()
        client.handler = GameHandler(client)
        client.connected = True

        print >> sys.stderr, "Connection established"


class GameHandler(Handler):
    handlers = {
            ghack_pb2.Message.ADDENTITY: lambda h: h.handle_add,
            ghack_pb2.Message.REMOVEENTITY: lambda h: h.handle_remove,
            ghack_pb2.Message.UPDATESTATE: lambda h: h.handle_update,
            ghack_pb2.Message.ASSIGNCONTROL: lambda h: h.handle_assign_control,
            ghack_pb2.Message.ENTITYDEATH: lambda h: h.handle_entity_death,
            ghack_pb2.Message.COMBATHIT: lambda h: h.handle_combat_hit,
        }
    def handle_add(self, client, add):
        args = {'id': add.id}
        if add.name:
            args['name'] = add.name
        client.game.add_entity(**args)

    def handle_remove(self, client, remove):
        args = {'id': remove.id}
        if remove.name:
            args['name'] = remove.name
        client.game.remove_entity(**args)

    def handle_update(self, client, update):
        args = {'id': update.id, 'state_id': update.state_id}
        args['value'] = messages.unwrap_state(update.value)
        client.game.update_entity(**args)

    def handle_assign_control(self, client, assign_control):
        args = {'uid': assign_control.uid, 'revoked': assign_control.revoked}
        client.game.assign_control(**args)

    def handle_entity_death(self, client, entity_death):
        args = {'uid': entity_death.uid, 'name': entity_death.name,
                'kuid': entity_death.killer_uid, 'kname': entity_death.killer_name}
        client.game.entity_death(**args)

    def handle_combat_hit(self, client, combat_hit):
        args = {'auid': combat_hit.attacker_uid, 'aname': combat_hit.attacker_name,
                'vuid': combat_hit.victim_uid, 'vname': combat_hit.victim_name,
                'damage': combat_hit.damage}
        client.game.combat_hit(**args)

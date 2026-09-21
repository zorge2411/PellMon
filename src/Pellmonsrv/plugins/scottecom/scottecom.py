#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2013  Anders Nylund

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
from Scotteprotocol import Protocol
import logging
import threading
from Pellmonsrv.plugin_categories import protocols
from Pellmonsrv.database import Item, Getsetitem, Plainitem
from . import menus
from .descriptions import dataDescriptions

class scottecom(protocols):
    def __init__(self):
        protocols.__init__(self)

    def activate(self, conf, glob, db, *args, **kwargs):
        protocols.activate(self, conf, glob, db, *args, **kwargs)
        self.logger = logging.getLogger('pellMon')
        self.dbvalues={}
        self.itemrefs = []
        self.protocol = None

        # Connection state items. Generic names (no scotte prefix) so other protocol
        # plugins can publish the same pair. Registered before, and outside of, the
        # protocol setup so they exist even when setup fails.
        self.conn_state_item = self._make_state_item('burner_connection', 'Burner connection',
            'Connection state of the burner: connected, no_connection or demo', 'no_connection')
        self.conn_reason_item = self._make_state_item('burner_connection_reason', 'Burner connection details',
            'Why the burner is not connected, or that values are simulated', 'burner setup has not completed')

        # Initialize protocol and setup the database according to version_string
        try:
            # A missing or blank serialport means demo mode; anything else is a real port
            serialport = (self.conf.get('serialport') or '').strip()
            chipversion = self.conf.get('chipversion') or 'auto'
            self.protocol = Protocol(serialport if serialport else None, chipversion)
            self._on_connection_change(self.protocol.connection_state, self.protocol.connection_reason)
            self.protocol.on_connection_change = self._on_connection_change
            self.allparameters = self.protocol.getDataBase()

            """Get list of all data/parameter/command items"""
            params = self.protocol.getDataBase()
            for item in params:
                dbitem = Getsetitem(item, None, lambda i:self.getItem(i), lambda i,v:self.setItem(i,v))
                if hasattr(params[item], 'max'): 
                    dbitem.max = str(params[item].max)
                if hasattr(params[item], 'min'): 
                    dbitem.min = str(params[item].min)
                if hasattr(params[item], 'frame'): 
                    if hasattr(params[item], 'address'): 
                        dbitem.type = 'R/W'
                    else:
                        dbitem.type = 'R'
                else:
                    dbitem.type = 'W'
                dbitem.longname = dataDescriptions[item][0]
                dbitem.unit = dataDescriptions[item][1]
                dbitem.description = dataDescriptions[item][2]
                dbitem.tags = menus.itemtags(item)
                self.db.insert(dbitem)
                self.itemrefs.append(dbitem)

            # Create and start settings_pollthread to log settings changed locally
            settings = [item for item in params if 'Settings' in menus.itemtags(item)]
            ht = threading.Timer(3, self.settings_pollthread, args=(settings,))
            ht.setDaemon(True)
            ht.start()

            # Create and start alarm_pollthread to log settings changed locally
            ht = threading.Timer(5, self.alarm_pollthread, args=(('mode', 'alarm'),))
            ht.setDaemon(True)
            ht.start()

            self.dataDescriptions = dataDescriptions
        except Exception as e:
            self.logger.exception('scottecom protocol setup failed')
            if self.protocol is None:
                self._on_connection_change('no_connection', 'burner protocol setup failed: %s' % e)

    def _make_state_item(self, name, longname, description, value):
        item = Plainitem(name, value)
        item.longname = longname
        item.unit = ''
        item.description = description
        item.type = 'R'
        item.tags = ['All']
        self.db.insert(item)
        self.itemrefs.append(item)
        return item

    def _on_connection_change(self, state, reason):
        """Protocol state callback: the daemon's Database thread notices the changed
        values within 2 s and pushes them to the web UI."""
        self.conn_state_item.value = state
        self.conn_reason_item.value = reason
        self.logger.info('burner connection: %s (%s)', state, reason)

    def getItem(self, item, raw=False):
        return self.protocol.getItem(item, raw)

    def setItem(self, item, value, raw=False):
        return self.protocol.setItem(item, value, raw)

    def getDataBase(self):
        db = self.protocol.getDataBase()
        return db.keys()

    def settings_pollthread(self, settings):
        """Loop through all items tagged as 'Settings' and write a message to the log when their values have changed"""
        for item in settings:
            try:
                param = self.allparameters[item]
                value = self.protocol.getItem(item, raw=True)
                if item in self.dbvalues:
                    if not value==self.dbvalues[item]:
                        log_change = True
                        # These are settings but their values are changed by the firmware also, 
                        # so small changes are suppressed from the log
                        selfmodifying_params = {'feeder_capacity': 25, 'feeder_low': 0.5, 'feeder_high': 0.8, 'time_minutes': 3, 'magazine_content': 1}
                        try:
                            change = abs(float(value) - float(self.dbvalues[item]))
                            squelch = selfmodifying_params[item]
                            # These items change by themselves, log change only when squelch is exceeded
                            if change <= squelch:
                                log_change = False
                        except:
                            pass
                        # Don't log clock turn around
                        if (item == 'time_minutes' and change == 1439): 
                            log_change = False
                        if log_change:
                            self.settings_changed(item, self.dbvalues[item], value)
                self.dbvalues[item]=value
            except:
                pass
        # run this thread again after 30 seconds
        ht = threading.Timer(30, self.settings_pollthread, args=(settings,))
        ht.setDaemon(True)
        ht.start()

    def alarm_pollthread(self, alarms):
        # Log changes to 'mode' and 'alarm'
        try:
            for param in alarms:
                value = self.protocol.getItem(param)
                if param in self.dbvalues:
                    if not value==self.dbvalues[param]:
                        self.settings_changed(param, self.dbvalues[param], value, param)
                self.dbvalues[param] = value
        except:
            pass
        # run this thread again after 30 seconds
        ht = threading.Timer(30, self.alarm_pollthread, args=(alarms,))
        ht.setDaemon(True)
        ht.start()


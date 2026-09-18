#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2013  Anders Nylund

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import socket
from random import randrange, SystemRandom
import time
from Crypto.PublicKey import RSA
import base64
import threading
import errno
from .frames import Request_frame, Response_frame
from .protocolexceptions import *
from logging import getLogger
from . import language
import xtea

logger = getLogger('pellMon')

class Proxy:
    settings = ('boiler', 'hot_water', 'regulation', 'weather', 'weather2', 'oxygen', 'cleaning', 'hopper', 'fan', 'auger', 'ignition', 'pump', 
        'sun', 'vacuum', 'misc', 'alarm', 'manual')
#    consumption_data = ('total_hours', 'total_days', 'total_months', 'total_years', 'dhw_hours', 'dhw_days', 'dhw_months', 'dhw_years', 'counter')

    def __init__(self, password, port=1920, addr=None, serial=None, transport=None, start_threads=True):
        self.password = password
        self.discover_addr = (addr, port)
        self.lock = threading.Lock()
        self.serial = serial
        self.controller_online = False
        self.connected = False

        if transport is not None:
            self.s = transport
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if addr == '<broadcast>':
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.settimeout(0.5)
            self.s = s
        self.request = Request_frame()
        self.response = Response_frame(self.request)
        self.request.pincode = self.password
        self.request.sequencenumber = randrange(0,100)

        if start_threads:
            self.t = threading.Thread(target=lambda:self.find_controller())
            self.t.setDaemon(True)
            self.t.start()

            self.t = threading.Thread(target=lambda:self.xtea_refresh_thread())
            self.t.setDaemon(True)
            self.t.start()


    def get_rsakey(self):
        if hasattr(self.request, 'public_key'):
            return True
        if not self.controller_online:
            return False
        for retry in range(3):
            try:
                logger.debug('get rsa, retry %s', retry)
                r = self.get(1, 'misc.rsa_key')
                key = base64.b64decode(r)
                self.request.public_key = RSA.importKey(key)
                return True
            except Exception:
                logger.exception('get_rsakey failed')
                pass # retry 3 times
            time.sleep(1)
        return False

    
    def set_xteakey(self):
        xtea_key = bytes([SystemRandom().randrange(256) for x in range(16)]).decode('latin-1')
        try:
            self.set('misc.xtea_key', xtea_key)
        except protocol_error:
            logger.info('Key exchange failed, wrong password?')

    def set(self, path, value):
        if not self.controller_online:
            raise protocol_offline('controller offline')
        for retry in range(7):
            try:
                with self.lock:
                    if not hasattr(self.request, 'xtea_key'):
                        use_rsa = True
                    else:
                        use_rsa = False
                    if use_rsa:
                        self.s.settimeout(5)
                        logger.debug('use rsa for xtea set')
                    else:
                        self.s.settimeout(1.5)
                    #print 'set value', value
                    response = self.make_request(2, path+'='+value, encrypt=True)
                    if response.status == 0:
                        if path == 'misc.xtea_key':
                            self.request.xtea_key = xtea.new(value.encode('latin-1'), mode=xtea.MODE_ECB, IV=b'\00'*8, rounds=64, endian='!')
                        return 'ok'
                    logger.debug('set error: %s', response.status)
                    raise protocol_error
            except protocol_error:
                if retry >= 1:
                    logger.debug('set retry %s', retry)
                if path == 'misc.xtea_key':
                    try:
                        logger.debug('xtea_set uncertain, del key and use rsa')
                        del self.request.xtea_key
                    except AttributeError:
                        pass
            finally:
                self.s.settimeout(0.5)
            if path == 'misc.xtea_key':
                time.sleep(2)
            else:
                time.sleep(0.2)
        logger.warning('no more set retry for %s', path)
        raise protocol_error('set %s failed'%path)

    def get(self, function, path, group=False):
        if not self.controller_online:
            raise protocol_offline('controller offline')
        for retry in range(7):
            try:
                with self.lock:
                    response = self.make_request(function, path)
                    if response.status == 0:
                        if not group:
                            return response.payload.split('=', 1)[1]
                        else:
                            return response.payload.split(';')
            except: #protocol_error:
                if retry >= 1:
                    logger.debug('get retry %s', retry)
            time.sleep(0.2)
        logger.warning('no more get retry for %s', path)
        raise protocol_error

    def find_controller(self):
        while True:
            try:
                controller_online = False
                for retry in range(3):
                    with self.lock:
                        request = self.request
                        request.function = 0
                        request.payload = 'NBE_DISCOVERY'
                        request.sequencenumber += 1
                        if request.sequencenumber >= 99:
                           request.sequencenumber = 0
                        try:
                            if not self.controller_online:
                                self.s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                                self.s.settimeout(3)
                                self.s.sendto(request.encode(), self.discover_addr)
                            else:
                                self.s.sendto(request.encode(), self.addr)
                            while True:
                                try:
                                    while True:
                                        try:
                                            data, server = self.s.recvfrom(4096)
                                        except socket.error as e:
                                            if e.errno != errno.EINTR:
                                                raise
                                        else:
                                            break
                                    self.response.decode(data)
                                    res = self.response.parse_payload()
                                    if self.serial: 
                                        if 'Serial' in res and res['Serial'] == self.serial:
                                            self.ip = res['IP']
                                            controller_online = True
                                            self.addr = server
                                            break
                                    else:
                                        self.ip = res['IP']
                                        controller_online = True
                                        self.addr = server
                                        break
                                except seqnum_error:
                                    logger.exception('find controller error')
                                    pass
                        except Exception:
                            logger.exception('find controller retry %s', retry)
                            pass
                        else:
                            break
                        finally:
                            if not self.controller_online:
                                self.s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 0)
                                self.s.settimeout(0.5)
                    time.sleep(2)

                if controller_online and not self.controller_online:
                    if self.connected:
                        logger.info('Reconnected to controller on %s'%self.addr[0])
                    self.controller_online = controller_online
                    self.connected = True
                    if self.get_rsakey():
                        self.set_xteakey()

                if self.controller_online and not controller_online:
                    logger.warning('Lost connection to controller')

                self.controller_online = controller_online

                if controller_online and not hasattr(self.request, 'xtea_key'):
                    if self.get_rsakey():
                        self.set_xteakey()

                if controller_online:
                    time.sleep(5)
                else:
                    time.sleep(1)
            except Exception:
                logger.exception('find_controller loop error')
                pass #don't ever die in this thread

    def dir(self):
        dirlist = []
        for s in self.settings:
            dl = self.get(3, s+'.*', group=True)
            for d in dl:
                d_name, d = d.split('=')
                d_min, d_max, d_default, d_decimals = d.split(',')
                dd = {'path':s+'.'+d_name, 'name':d_name, 'function':1, 'grouppath':s+'.*', 'group':s, 'min':d_min, 'max':d_max, 'decimals':d_decimals, 'type':'R/W', 'value':'-'}
                try:
                    dd['get_text'] = language.get_enumeration_function('-'.join((s, d_name)) )
                except KeyError:
                    pass
                try:
                    dd['get_enum_list'] = language.get_enumeration_list('-'.join((s, d_name)) )
                    #print 'added get_enum_list', dd['name'], dd['get_enum_list']
                except KeyError:
                    pass
                dirlist.append(dd)

        dl = self.get(5, '*', group=True)
        for d in dl:
            d_name, d_value = d.split('=')
            dd = {'path':d_name, 'name':d_name, 'function':5, 'grouppath':'*', 'group':'advanced_data', 'type':'R', 'value':d_value}
            try:
                dd['get_text'] = language.get_enumeration_function('advanced_data-'+d_name)
            except KeyError:
                pass
            dirlist.append(dd)

        dl = self.get(4, '*', group=True)
        for d in dl:
            d_name, d_value = d.split('=')
            dd = {'path':d_name, 'name':d_name, 'function':4, 'grouppath':'*', 'group':'operating_data', 'type':'R', 'value':d_value}
            if d_name == 'state':
                dd['get_text'] = language.state_text
            if d_name == 'substate':
                dd['get_text'] = language.substate_text
            try:
                dd['get_text'] = language.get_enumeration_function('operating_data-'+d_name)
            except KeyError:
                pass
            dirlist.append(dd)
        d_name = 'counter'
        dirlist.append({'path':d_name, 'name':d_name, 'function':6, 'group':'consumption_data', 'type':'R', 'value':d_value})
        return dirlist

    @classmethod
    def discover(cls, password, port, serial=None):
        return cls(password, port, addr='<broadcast>', serial=serial)

    def make_request(self, function, payload, encrypt=False):
        try:
            self.request.sequencenumber += 1
            if self.request.sequencenumber > 99:
                self.request.sequencenumber = 0
            self.request.payload = payload
            self.request.function = function
            self.request.encrypted = encrypt
            self.request.pincode = self.password
            self.s.sendto(self.request.encode(), self.addr)
            while True:
                try:
                    while True:
                        try:
                            data, server = self.s.recvfrom(4096)
                        except socket.error as e:
                            if e.errno != errno.EINTR:
                                raise
                        else:
                            break
                    self.response.decode(data)
                    return self.response
                except seqnum_error:
                    logger.exception('seqnum error, function %s', function)
                    pass #just read again on seqnum error
                else:
                    break
        except socket.timeout as e:
            logger.exception('timeout, func: %s missed seqnum: %s', function, self.request.sequencenumber)
            raise protocol_timeout(str(e))
        except Exception as e:
            logger.exception('other exc, seqnum %s', self.request.sequencenumber)
            raise protocol_error(str(e))

    def xtea_refresh_thread(self):
        while True:
            if self.controller_online:
                try:
                    if self.get_rsakey():
                        self.set_xteakey()
                except Exception as e:
                    del self.request.xtea_key
                    del self.request.public_key
                    try:
                        if self.get_rsakey():
                            self.set_xteakey()
                        logger.debug('xtea set')
                    except Exception as e:
                        pass
            time.sleep(5)


class Controller:
    def __init__(self, host, password, port=1900, seqnums=True):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.bind((host, port))
        self.password = password
        self.request = V3_request_frame()
        self.response = V3_response_frame(self.request)

        if seqnums:
            self.seqnums = 0
        else:
            self.seqnums = None

    def run(self):
        while True:
            d = self.s.recvfrom(1024)
            data = d[0]
            addr = d[1]
            self.request.decode(data)
            print ('< ' + self.request.payload.decode('ascii'))
            # discovery response
            if self.request.function == 0:
                self.response.function = self.request.function
                self.response.payload = 'Serial=1234;IP=%s'%addr[0]
                self.response.status = 0
                frame = self.response.encode()
                self.s.sendto(frame , addr)
                print ('  > ' + frame.decode('ascii'))
            else:
                # check password
                if True: #self.requset.pincode == self.password:
                    if self.request.function == 1:
                        self.response.function = self.request.function
                        if self.request.payload == 'boiler.temp':
                            self.response.payload = 'boiler.temp=90'
                            self.response.status = 0
                        elif self.request.payload == 'misc.rsa_key':
                            self.response.payload = 'casyugdyasguyagusduaysgdaysudyasgdyuasdgua'
                            self.response.status = 0
                        frame = self.response.encode()
                        self.s.sendto(frame , addr)
                    else:
                        self.response.function = self.request.function
                        self.response.payload = 'illegal function'
                        self.response.status = 1
                        frame = self.response.encode()
                        self.s.sendto(frame , addr)
                    print ('  > ' + frame.decode('ascii'))
                else:
                    self.response.function = self.request.function
                    self.response.payload = 'wrong password'
                    self.response.status = 1
                    frame = self.response.encode()
                    self.s.sendto(frame , addr)
                    print ('  > ' + frame.decode('ascii'))




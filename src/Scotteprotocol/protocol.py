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

from threading import Lock
from logging import getLogger 
import time
import queue
import threading
import serial
from .enumerations import dataEnumerations
from .transformations import dataTransformations
logger = getLogger('pellMon')

# Number of consecutive give-ups (each is one attempt plus one retry) after
# which the burner is considered unreachable.
FAILURE_THRESHOLD = 3

CONNECTED = 'connected'
NO_CONNECTION = 'no_connection'
DEMO = 'demo'

class Protocol(threading.Thread):
    """Provides read/write functions for parameters/measurement data 
    for a bio comfort pellet burner connected through rs232"""
    
    def __init__(self, device, version_string, transport=None, start_thread=True):   
        """Initialize the protocol and database according to given version"""
        threading.Thread.__init__(self)
        self.dummyDevice = False
        self.port_failed = False
        self.checksum = True
        self.frame_term_crlf = False
        self.device = device
        # Connection state, published by the plugin as burner_connection items
        self.connection_state = CONNECTED
        self.connection_reason = ''
        self.on_connection_change = None
        self._conn_lock = threading.Lock()
        self._consecutive_failures = 0
        if transport is not None:
            self.dummyDevice = False
            self.device = device if device else repr(transport)
            self.ser = transport
            self.dataBase = self.createDataBase('6.99' if not version_string else version_string)
            self.q = queue.Queue(300)
            threading.Thread.__init__(self)
            self.daemon = True
            if start_thread:
                self.start()
            return

        if device is None:
            # Demo mode: no serial port configured, values are simulated
            self.dummyDevice = True
            self.connection_state = DEMO
            self.connection_reason = 'no serialport is configured, values are simulated'
            self.dataBase = self.createDataBase('6.99')
            return     
        # Open serial port
        s = serial.Serial()
        s.port     = device
        s.baudrate = 9600
        s.parity   = 'N'
        s.rtscts   = False
        s.xonxoff  = False
        s.timeout  = 1        
        try:
            s.open()
        except serial.SerialException as e:
            logger.error("Could not open serial port %s: %s", device, e)
            # Do not pretend: serve no values, keep item names for the UI layout
            self.port_failed = True
            self.ser = None
            self.connection_state = NO_CONNECTION
            self.connection_reason = 'serial port %s cannot be opened: %s' % (device, e)
            self.dataBase = self.createDataBase('6.99')
            return 
        logger.info('serial port ok')
        self.ser = s
            
        # message queue, used to send frame polling commands to pollThread
        self.q = queue.Queue(300)
        self.dataBase = self.createDataBase('4.99')
        
        # Create and start poll_thread
        threading.Thread.__init__(self)
        self.daemon = True
        self.start()
   
        if version_string == 'auto':
            try:
                version_string = self.getItem('version').lstrip()
                logger.info('chip version detected as: %s'%version_string)
            except (OSError, KeyError, IndexError, ValueError, TypeError):
                self.checksum=False
                logger.info('protocol checksums turned off')
                try:
                    version_string = self.getItem('version').lstrip()
                    logger.info('chip version detected as: %s'%version_string)
                except (OSError, KeyError, IndexError, ValueError, TypeError):
                    self.frame_term_crlf= True
                    try:
                        version_string = self.getItem('version').lstrip()
                        logger.info('chip version detected with checksums of and crlf on as: %s'%version_string)
                    except (OSError, KeyError, IndexError, ValueError, TypeError):
                        version_string = '4.00'
                        logger.info("can't read program version, assuming 4.00")
                        try:
                            testread = self.getItem('power').lstrip()
                            logger.info('Connected with protocol checksums turned off and crlf on')
                        except (OSError, KeyError, IndexError, ValueError, TypeError):
                            logger.info('Not connected? Check the cables')
        else:
            logger.info('chip version from config: %s'%version_string)
            try:
                testread = self.getItem('power').lstrip()
                logger.info('Connected')
            except (OSError, KeyError, IndexError, ValueError, TypeError):
                self.checksum=False
                try:
                    testread = self.getItem('power').lstrip()
                    logger.info('Connected with protocol checksums turned off')
                except (OSError, KeyError, IndexError, ValueError, TypeError):
                    self.frame_term_crlf= True
                    try:
                        testread = self.getItem('power').lstrip()
                        logger.info('Connected with protocol checksums turned off and crlf on')
                    except (OSError, KeyError, IndexError, ValueError, TypeError):
                        logger.info('Not connected? Check the cables')

        self.dataBase = self.createDataBase(version_string)

    def getDataBase(self):
        return self.dataBase  

    def _set_connection_state(self, state, reason):
        """Change the connection state; the callback fires once per transition."""
        with self._conn_lock:
            if state == self.connection_state and reason == self.connection_reason:
                return
            changed = state != self.connection_state
            self.connection_state = state
            self.connection_reason = reason
            callback = self.on_connection_change
        if not changed:
            return
        if state == NO_CONNECTION:
            logger.warning('burner connection state: %s (%s)', state, reason)
        else:
            logger.info('burner connection state: %s (%s)', state, reason)
        if callback is not None:
            try:
                callback(state, reason)
            except Exception:
                logger.exception('connection state callback failed')

    def _notify_result(self, ok):
        """Feed the outcome of a real device poll into the state machine."""
        if self.dummyDevice or self.port_failed:
            return
        with self._conn_lock:
            if ok:
                self._consecutive_failures = 0
                give_up = False
            else:
                self._consecutive_failures += 1
                give_up = self._consecutive_failures >= FAILURE_THRESHOLD
        if ok:
            self._set_connection_state(CONNECTED, '')
        elif give_up:
            self._set_connection_state(NO_CONNECTION, 'burner not answering on %s' % self.device)
                
    def getItem(self, param, raw=False): 
        if self.dummyDevice:
            return '1234'
        if self.port_failed:
            raise IOError(0, 'no connection to the burner')
        """Read data/parameter value"""
        #logger.debug('getitem')
        dataparam=self.dataBase[param]
        if hasattr(dataparam, 'frame'):
            ok=True
            # If the frame containing this data hasn't been read recently
            # or if the specific index has been written after the frame was last read
            # or if the specific index has just been written (might still give old value when read
            # so a retry should do a new poll)
            # then re-read
            writeTime = dataparam.frame.indexWriteTime[dataparam.index]
            readTime = dataparam.frame.readtime
            if time.time()-readTime > 8.0 or writeTime>readTime or time.time()-writeTime < 4.0:
                try:
                    responseQueue = queue.Queue(3)
                    try:  # Send "read parameter value" message to pollThread
                        if writeTime>readTime or time.time()-writeTime < 4.0:
                            self.q.put(("FORCE_GET", dataparam.frame,responseQueue))
                        else:
                            self.q.put(("GET", dataparam.frame,responseQueue))
                        try:  # and wait for a response                 
                            ok=responseQueue.get(True, 5)
                        except queue.Empty:
                            ok=False
                            logger.debug('GetItem: Response timeout')
                    except queue.Full:
                        ok=False
                        logger.info('Getitem: MessageQueue full')
                except Exception:
                    logger.exception('Getitem: Create responsequeue failed') 
                    ok=False
                # only real device polls drive the state machine
                self._notify_result(bool(ok))
            if (ok):
                if dataparam.decimals == -1: # not a number, return as is
                    return dataparam.frame.get(dataparam.index)
                else:
                    value = dataparam.frame.get(dataparam.index)
                    try:
                        return dataEnumerations[param][int(value)]
                    except (KeyError, ValueError, IndexError, TypeError):                        
                        try:
                            formatStr="{:0."+str(dataparam.decimals)+"f}"
                            data = formatStr.format( float(value) / pow(10, dataparam.decimals)  )
                            try:
                                if not raw:
                                    data = dataTransformations[param].decode(value)
                            except (KeyError, ValueError, TypeError, AttributeError):
                                pass
                            return data
                        except (ValueError, TypeError):
                            raise IOError(0, "Getitem result is not a number")
            else:
                raise IOError(0, "GetItem failed")
        else: 
            raise IOError(0, "A command can't be read") 

    def setItem(self, param, s, raw=False):
        """Write a parameter/command.

        Returns the string 'OK' on success. Never returns device reply text.
        Raises ValueError for local validation failures (not a number, out of
        range, not a setting) and IOError if the device rejected the write or
        did not answer. The raw device reply is only written to the log."""
        try:
            if not raw:
                s = dataTransformations[param].encode(s)
        except (KeyError, ValueError, TypeError, AttributeError):
            pass
        if self.dummyDevice:
            return 'OK'
        if self.port_failed:
            raise IOError(0, 'no connection to the burner')
        dataparam=self.dataBase[param]
        if not hasattr(dataparam, 'address'):
            logger.warning('setItem %s: not a setting value', param)
            raise ValueError('Not a setting value')
        try:
            value=float(s)
        except (ValueError, TypeError):
            logger.warning('setItem %s: %r is not a number', param, s)
            raise ValueError('not a number')
        if not (value >= dataparam.min and value <= dataparam.max):
            logger.warning('setItem %s: value %r out of range %s..%s', param, s, dataparam.min, dataparam.max)
            raise ValueError("Expected value "+str(dataparam.min)+".."+str(dataparam.max))
        try:
            if hasattr(dataparam, 'frame'):
                # Save time when this index was written
                dataparam.frame.indexWriteTime[dataparam.index] = time.time()
            if hasattr(dataparam, 'decimals'):
                decimals = dataparam.decimals
            else:
                decimals = 0
            s=("{:0>4.0f}".format(value * pow(10, decimals)))
            # Send "write parameter value" message to pollThread
            responseQueue = queue.Queue() 
            self.q.put(("PUT", dataparam.address + s, responseQueue))
            response = responseQueue.get()
        except Exception as e:
            logger.exception('Unexpected error in setItem: %s', e)
            raise IOError(0, 'SetItem failed')
        # Only "no answer" says anything about connectivity; a rejection is still an answer
        self._notify_result(response != "No answer")
        if response == self.addCheckSum('OK'):
            logger.info('Parameter %s = %s'%(param,s))
            return 'OK'
        logger.warning('setItem %s rejected or unanswered, raw reply %r', param, response)
        raise IOError(0, 'SetItem failed: device rejected write or did not answer')
            
    def createDataBase(self, version_string):
        """return a dictionary of parameters supported on version_string"""
        from .datamap import dataBaseMap 
        db={}
        for param_name in dataBaseMap:
            mappings = dataBaseMap[param_name]
            for supported_versions in mappings: 
                if version_string >= supported_versions[0] and version_string < supported_versions[1]:
                    db[param_name] = mappings[supported_versions]
        return db   

    def run(self):
        """Run as thread. Waits on queue self.q for frame read / parameter write commands, responds in an 
        other queue received with the command"""
        logger.debug('thred run')
        while True:  
            commandqueue = self.q.get() 
            logger.debug('got command')
            # Write parameter/command       
            if commandqueue[0]=="PUT":
                s=self.addCheckSum(commandqueue[1])
                logger.debug('serial write'+s)
                self.ser.flushInput()
                if self.frame_term_crlf:
                    s += '\r\n'
                self.ser.write(s.encode('latin-1'))
                logger.debug('serial written'+s)        
                line=""
                if not self.frame_term_crlf:
                    try:
                        if self.checksum:
                            line=self.ser.read(3).decode('latin-1')
                        else:
                            line=self.ser.read(2).decode('latin-1')
                        logger.debug('serial read'+line)
                    except (serial.SerialException, OSError) as e: 
                        logger.exception('Serial read error: %s', e)
                    except Exception:
                        logger.exception('Unexpected error during serial read')
                    if line:
                        # Send back the response
                        commandqueue[2].put(line)
                    else:
                        commandqueue[2].put("No answer")
                        logger.info('No answer')
                else:
                    # These old versions don't answer at all, assume it went ok
                    commandqueue[2].put("OK")
            
            # Get frame command
            if commandqueue[0]=="GET" or commandqueue[0]=="FORCE_GET":
                responsequeue = commandqueue[2]
                frame = commandqueue[1]
                # This frame could have been read recently by a previous queued read request, so check again if it's necessary to read
                if time.time()-frame.readtime > 8.0 or commandqueue[0]=="FORCE_GET":
                    sendFrame = self.addCheckSum(frame.pollFrame)
                    # terminate once; the same bytes are used for the first attempt and the retry
                    if self.frame_term_crlf:
                        sendFrame += '\r\n'
                    logger.debug('sendFrame = '+sendFrame)
                    line=""
                    try:
                        self.ser.flushInput()
                        logger.debug('serial write')
                        self.ser.write(sendFrame.encode('latin-1'))
                        logger.debug('serial written')  
                        line=self.ser.read(frame.getLength(self)).decode('latin-1')
                        logger.debug('serial read'+line)
                    except (serial.SerialException, OSError) as e:
                        logger.exception('Serial communication error: %s', e)
                    except Exception:
                        logger.exception('Unexpected error during serial communication')
                    result = False
                    if line:    
                        logger.debug('Got answer, parsing') 
                        result=commandqueue[1].parse(line, self)
                        if result:
                            try:
                                responsequeue.put(result)
                            except Exception:
                                logger.exception('command response queue put 1 fail')    
                    else:
                        logger.debug('Timeout')
                    if not result:           
                        logger.debug('Retrying')
                        try:
                            self.ser.flushInput()
                            logger.debug('serial write')
                            self.ser.write(sendFrame.encode('latin-1'))
                            logger.debug('serial written')
                            line=self.ser.read(frame.getLength(self)).decode('latin-1')
                            logger.debug('answer: '+line)
                        except (serial.SerialException, OSError) as e:
                            logger.exception('Serial communication error on retry: %s', e)
                        except Exception:
                            logger.exception('Unexpected error during serial communication retry')
                        if line:
                            logger.debug('Got answer, parsing')
                            result=commandqueue[1].parse(line, self)
                            try:
                                responsequeue.put(result)
                            except Exception:
                                logger.exception('command response queue put 1 fail')
                        else:   
                            try:
                                logger.debug('Try to put False, answer was empty')
                                responsequeue.put(False)
                            except Exception:
                                logger.exception('command response queue put 2 fail')
                            logger.info('Timeout again, give up and return fail')
                else: 
                    responsequeue.put(True) 

    def addCheckSum(self, s):
        if not self.checksum:
            return s
        else:
            if isinstance(s, bytes):
                s = s.decode('latin-1')
            x=0;
            logger.debug('addchecksum:')
            for c in s: x=x^ord(c)
            rs=s+chr(x)
            logger.debug(rs)
            return rs

    def checkCheckSum(self, s):
        x=0;
        if self.checksum:
            if isinstance(s, bytes):
                s = s.decode('latin-1')
            for c in s: 
                x=x^ord(c)
        return x

class Frame:
    """Handle parsing of response strings to the different frame formats, and 
    provide thread safe get data function"""
    
    def __init__(self, dd, frame):
        self.mutex=Lock()
        self.dataDef=dd 
        self.pollFrame=frame
        self.readtime=0.0
        self.indexWriteTime = [0.0]*len(self.dataDef)
        self.frameLength=0
        for i in self.dataDef:
            self.frameLength += i
    
    def getLength(self, protocol):
        if protocol.checksum:
            return self.frameLength+1
        else:
            if protocol.frame_term_crlf:
                return self.frameLength + 2
            else:
                return self.frameLength

    def parse(self, s, protocol):
        logger.debug('Check checksum in parse '+s)
        if protocol.checkCheckSum(s):
            logger.debug('Parse: checksum error on response message: ' + s)
            return False
        logger.debug('Checksum OK')
        if s==protocol.addCheckSum('E1'):
            logger.debug('Parse: response message = E1, data does not exist')    
            return False
        if s==protocol.addCheckSum('E0'):
            logger.debug('Parse: response message = E0, checksum fail')  
            return False                        
        index=0
        if self.getLength(protocol) == len(s):
            logger.debug('Correct length')
            with self.mutex:
                self.data=[]
                self.readtime=time.time()
                logger.debug("reset readtime")
                for i in self.dataDef:
                    index2=index+i
                    self.data.append(s[index:index2])
                    index=index2
            logger.debug('Return True from parser')
            return True
        else:
            logger.debug("Parse: wrong length "+str(len(s))+', expected '+str(self.getLength(protocol)))
            return False
        
    def get(self, index):
        with self.mutex:
            data=self.data[index]
        return data
    


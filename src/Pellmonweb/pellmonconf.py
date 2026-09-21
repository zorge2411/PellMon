#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2014  Anders Nylund

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
#from version import __version__
import os.path
#import sys
from os import linesep
import sys
import cherrypy
import argparse
from mako.lookup import TemplateLookup
import json
#import re
#import cPickle as pickle
#import parser
from html import escape
import codecs
import errno
#from weakref import WeakValueDictionary
#import dbparser as parser
#import webbrowser
import configparser
import urllib.parse
from logging import getLogger
from .security import check_same_origin as _check_same_origin

logger = getLogger('pellMon')

class Pellmonconf:
    def __init__(self, config_file = '', lookup = None):
        self.lookup = lookup
        self.filelist = []
        self.dirs = {}
        filename = os.path.basename(config_file)
        self.filelist.append(filename)
        self.dirs[filename] = os.path.dirname(config_file) 
        # no interpolation: config values contain '%' (e.g. DS:%s:DERIVE:%u:0:U)
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform=str
        try:
            parser.read(config_file)
        except:
            sys.stderr.write('config file %s unreadable\n'%filename)
        try:
            config_dir = parser.get('conf', 'config_dir')
            for root, dirs, files in os.walk(config_dir):
                for name in files:
                    if os.path.splitext(name)[1] == '.conf':
                        f = os.path.join(root, name)
                        filename = os.path.join(os.path.basename(config_dir), os.path.relpath(f, config_dir))
                        self.filelist.append(filename)
                        self.dirs[filename] = os.path.normpath(os.path.join(config_dir, '..'))
        except IOError:
            pass
    @cherrypy.expose
    def complete(self, line, **kwargs):
        line = escape(line)
        r = completer(line)
        line, completelist, truncated = r
        completelist_html = ''
        if truncated:
            completelist_html += '<h5>First 100:</h5>'
        for item in completelist:
            common = item
            rest = ''
            if len(line) >= 1 and item.lower().startswith(line.lower()):
                common = item[0:len(line)]
                rest = item[len(common):]
                completelist_html += '<a href="?item=%s"> <span class="common_itemtext">%s</span>%s </a>'%(item, common, rest)
            else:
                completelist_html += '<a href="?item=%s"> <span class="common_itemtext">%s</span> </a>'%(item, item)

        return json.dumps([line, completelist_html, completelist[:1]])


    @cherrypy.expose
    def index(self, filename = 'pellmon.conf'):
        tmpl = self.lookup.get_template("source.html")
        return tmpl.render(filename=filename, filelist=self.filelist)

    def _resolve(self, filename):
        if not isinstance(filename, str) or not filename:
            raise ValueError('no filename')
        if filename not in self.dirs:
            logger.warning('rejected config file access: %r', filename)
            raise ValueError('not an allowed config file')
        base = os.path.realpath(self.dirs[filename])
        path = os.path.realpath(os.path.join(self.dirs[filename], filename))
        try:
            inside = os.path.commonpath([path, base]) == base
        except ValueError:
            inside = False
        if not inside:
            logger.warning('rejected config file access: %r', filename)
            raise ValueError('path escapes config directory')
        return path

    @cherrypy.expose
    def source(self, filename = None):
        try:
            line = 1
            path = self._resolve(filename)
            with codecs.open(path, 'r', 'utf-8', 'strict') as f:
                data = f.read()
                return json.dumps({'filename':filename, 'data':data, 'line':int(line), 'linesep':linesep})
        except Exception as e:
            return json.dumps({'error':str(e)})

    @cherrypy.expose
    def save(self, filename='', data=None):
        if cherrypy.request.method == "POST":
            if not _check_same_origin():
                logger.warning('rejected cross-origin config save: origin=%r host=%r',
                               cherrypy.request.headers.get('Origin') or cherrypy.request.headers.get('Referer'),
                               cherrypy.request.headers.get('Host'))
                return json.dumps({'success':False, 'error':'cross-origin request rejected'})
            try:
                path = self._resolve(filename)
                with codecs.open(path, 'w', 'utf-8') as f:
                    f.write(data)
                    return json.dumps({'success':True})
            except ValueError as e:
                return json.dumps({'success':False, 'error':str(e)})
            except OSError as e:
                if e.errno in (errno.EROFS, errno.EACCES, errno.EPERM):
                    logger.warning('read-only config file save rejected: %r (errno %s)', filename, e.errno)
                    return json.dumps({'success':False, 'error':'%s is read-only (mounted read-only or not writable by the web user); edit it on the host and restart the containers'%filename})
                return json.dumps({'success':False, 'error':str(e)})
        else:
            error = {'msg':'only POST'}
            return json.dumps({'success':False, 'error':error})

try:
    from Pellmonsrv.directories import DATADIR, CONFDIR, LOCALSTATEDIR
except ImportError:
    DATADIR = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))
    CONFDIR = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))
    LOCALSTATEDIR = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', '..'))

def run():
    MEDIA_DIR = os.path.join(DATADIR, 'Pellmonweb', 'media')
    lookup = TemplateLookup(directories=[os.path.join(DATADIR, 'Pellmonweb', 'html_conf')])
    config_file = os.path.join(CONFDIR, 'pellmon.conf')
    logger.debug('config file: %s', config_file)
    argparser = argparse.ArgumentParser(prog='pellmonconf')

    argparser.add_argument('-P', '--port', default=8083, help='Port number for webinterface, default 8083')
    argparser.add_argument('-H', '--host', default='127.0.0.1', help='Host for webinterface, default 127.0.0.1')
    args = argparser.parse_args()
    global_conf = {
            'global':   {
                          #'tools.sessions.on' : True,
                          #'tools.sessions.timeout': 7200,
                          'server.socket_host': args.host,
                          'server.socket_port': int(args.port),
                          'engine.autoreload.on': True,
                          #'checker.on': False,
                          #'tools.log_headers.on': False,
                          #'request.show_tracebacks': False,
                          #'request.show_mismatched_params': False,
                          'log.screen': False,
                        }
                  }
    app_conf =  {'/media':
                    {'tools.staticdir.on': True,
                     'tools.staticdir.dir': MEDIA_DIR,
                     'tools.staticdir.content_types': {'svg': 'image/svg+xml'},
                     'tools.encode.on' : True,
                     'tools.encode.encoding' : 'utf-8'
                    }                    
                }

    # Intentional CLI output (D-04): this is the manually-invoked standalone
    # tool's startup banner, deliberately excluded from the OBS-03 print sweep.
    print('Open http://<ip>:%u with your webbrowser to view the configuration tool'%int(args.port))
    print('Run as root to be able to save changes')
    print('Quit with CTRL-C')
    cherrypy.config.update(global_conf)
    cherrypy.tree.mount(Pellmonconf(config_file, lookup), '/', config=app_conf)
    cherrypy.engine.start()
    cherrypy.engine.block()


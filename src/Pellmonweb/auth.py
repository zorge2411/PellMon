# -*- coding: utf-8 -*-
#
# Form based authentication for CherryPy. Requires the
# Session tool to be loaded.
#
"""
    Copyright (C) 2013  Anders Nylund
    
    Based on http://tools.cherrypy.org/wiki/AuthenticationAndAccessRestrictions

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


import cherrypy
from html import escape
from mako.template import Template
from mako.lookup import TemplateLookup
import urllib
import os
import hashlib
import hmac
import secrets
import logging

logger = logging.getLogger('pellMon')


def hash_password(password, salt=None, iterations=100000):
    if salt is None:
        salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
    return 'pbkdf2:sha256:%d$%s$%s' % (iterations, salt, derived.hex())


def verify_password(stored_credential, provided_password):
    if not stored_credential or not provided_password:
        return False
    stored_str = str(stored_credential)
    provided_str = str(provided_password)
    if stored_str.startswith('pbkdf2:'):
        if stored_str.startswith('pbkdf2:sha256:'):
            try:
                parts = stored_str.split('$')
                if len(parts) != 3:
                    return False
                iter_part = parts[0].split(':')[-1]
                iterations = int(iter_part)
                salt = parts[1]
                stored_hash = parts[2].lower()
                derived = hashlib.pbkdf2_hmac('sha256', provided_str.encode('utf-8'), salt.encode('utf-8'), iterations)
                return hmac.compare_digest(derived.hex(), stored_hash)
            except Exception:
                return False
        return False
    # Legacy plaintext fallback
    return hmac.compare_digest(stored_str, provided_str)


SESSION_KEY = '_cp_username'

    # An example implementation which uses an ORM could be:
    # u = User.get(username)
    # if u is None:
    #     return u"Username %s is unknown to me." % username
    # if u.password != md5.new(password).hexdigest():
    #     return u"Incorrect password"

def check_auth(*args, **kwargs):
    """A tool that looks in config for 'auth.require'. If found and it
    is not None, a login is required and the entry is evaluated as alist of
    conditions that the user must fulfill"""
    conditions = cherrypy.request.config.get('auth.require', None)
    # format GET params
    get_parmas = urllib.parse.quote(cherrypy.request.request_line.split()[1])
    if conditions is not None:
        username = cherrypy.session.get(SESSION_KEY)
        if username:
            cherrypy.request.login = username
            for condition in conditions:
                # A condition is just a callable that returns true or false
                if not condition():
                    # Send old page as from_page parameter
                    raise cherrypy.HTTPRedirect(cherrypy.request.script_name+"/auth/login?from_page=%s" % get_parmas)
        else:
            # Send old page as from_page parameter
            raise cherrypy.HTTPRedirect(cherrypy.request.script_name+"/auth/login?from_page=%s" %get_parmas) 
    
cherrypy.tools.auth = cherrypy.Tool('before_handler', check_auth)

def require(*conditions):
    """A decorator that appends conditions to the auth.require config
    variable."""
    def decorate(f):
        if not hasattr(f, '_cp_config'):
            f._cp_config = dict()
        if 'auth.require' not in f._cp_config:
            f._cp_config['auth.require'] = []
        f._cp_config['auth.require'].extend(conditions)
        return f
    return decorate


# Conditions are callables that return True
# if the user fulfills the conditions they define, False otherwise
#
# They can access the current username as cherrypy.request.login
#
# Define those at will however suits the application.

def member_of(groupname):
    def check():
        # replace with actual check if <username> is in <groupname>
        return cherrypy.request.login == 'joe' and groupname == 'admin'
    return check

def name_is(reqd_username):
    return lambda: reqd_username == cherrypy.request.login

# These might be handy

def any_of(*conditions):
    """Returns True if any of the conditions match"""
    def check():
        for c in conditions:
            if c():
                return True
        return False
    return check

# By default all conditions are required, but this might still be
# needed if you want to use it inside of an any_of(...) condition
def all_of(*conditions):
    """Returns True if all of the conditions match"""
    def check():
        for c in conditions:
            if not c():
                return False
        return True
    return check


# Controller to provide login and logout actions

class AuthController(object):
    
    def __init__(self, credentials, lookup):
        self.credentials = credentials
        self.lookup = lookup
    
    def on_login(self, username):
        """Called on successful login"""
        remote_addr = cherrypy.request.headers.get("Remote-Addr", "unknown") if hasattr(cherrypy.request, "headers") else "unknown"
        cherrypy.log('Login from %s as username: %s' % (remote_addr, username))

    def on_logout(self, username):
        """Called on logout"""
        remote_addr = cherrypy.request.headers.get("Remote-Addr", "unknown") if hasattr(cherrypy.request, "headers") else "unknown"
        cherrypy.log('Logout from %s, username: %s' % (remote_addr, username))

    def get_loginform(self, username, msg="Enter login information", from_page="/"):
        from_page = escape(from_page, True)
        username = escape(username, True)
        tmpl = self.lookup.get_template("login.html")
        return tmpl.render(user_name=username, username=cherrypy.session.get('_cp_username'), from_page=from_page, msg=msg, webroot=cherrypy.request.script_name)

    def check_credentials(self, username, password):
        """Verifies credentials for username and password.
        Returns None on success or a string describing the error on failure"""
        remote_addr = cherrypy.request.headers.get("Remote-Addr", "unknown") if hasattr(cherrypy.request, "headers") else "unknown"
        user_str = str(username)[:50] if username is not None else ""
        try:
            if isinstance(self.credentials, dict):
                stored_val = self.credentials.get(username)
                if stored_val is not None and verify_password(stored_val, password):
                    if not str(stored_val).startswith('pbkdf2:'):
                        logger.warning("User '%s' authenticated using legacy plaintext password; please migrate configuration to PBKDF2 hash.", username)
                    return None
            else:
                for u, p in self.credentials:
                    if u == username and verify_password(p, password):
                        if not str(p).startswith('pbkdf2:'):
                            logger.warning("User '%s' authenticated using legacy plaintext password; please migrate configuration to PBKDF2 hash.", username)
                        return None
            cherrypy.log('Login failed from %s, username: %s' % (remote_addr, user_str))
            return "Incorrect username or password."
        except Exception:
            cherrypy.log('Login failed from %s, username: %s' % (remote_addr, user_str))
            return "Incorrect username or password."

    @cherrypy.expose
    def login(self, username=None, password=None, from_page='/'):
        if from_page == '/':
            from_page = cherrypy.request.script_name

        if username is None or password is None:
            return self.get_loginform("", from_page=from_page)
        
        error_msg = self.check_credentials(username, password)
        if error_msg:
            return self.get_loginform(username, error_msg, from_page)
        else:
            cherrypy.session[SESSION_KEY] = cherrypy.request.login = username
            self.on_login(username)
            raise cherrypy.HTTPRedirect(from_page)
    
    @cherrypy.expose
    def logout(self, from_page=cherrypy.request.script_name):
        sess = cherrypy.session
        username = sess.get(SESSION_KEY, None)
        sess[SESSION_KEY] = None
        if username:
            cherrypy.request.login = None
            self.on_logout(username)
        raise cherrypy.HTTPRedirect(cherrypy.request.script_name if cherrypy.request.script_name else '/' )

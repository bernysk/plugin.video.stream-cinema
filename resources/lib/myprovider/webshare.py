# -*- coding: UTF-8 -*-
#/*
# *
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with this program; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# *
# */
from crypto.md5crypt import md5crypt
from datetime import timedelta
import elementtree.ElementTree as ET
import hashlib
from provider import ResolveException
import traceback
import urlparse
import util
from resources.lib.sctop import post, checkSupportHTTPS, getSettingAsBool, setSetting, getSetting
import xbmcgui


class Webshare():
    def __init__(self, username=None, password=None, cache=None):
        self.username = username.encode('utf-8')
        self.password = password.encode('utf-8')
        self.base_url = 'http://webshare.cz/'
        if getSettingAsBool('ws_checkssl') is False:
            setSetting('ws_checkssl', 'true')
            res = checkSupportHTTPS(self.base_url)
            setSetting('ws_usessl', 'true' if res is True else 'false')
        if getSettingAsBool('ws_usessl') is True:
            self.base_url = self.base_url.replace('http://', 'https://')
        self.cache = cache
        self.win = xbmcgui.Window(10000)
        self._userData = None
        self.token = None
        self.getToken()

    def _url(self, url):
        if url.startswith('http'):
            return url
        return self.base_url + url.lstrip('./')

    def _create_request(self, url, base):
        args = dict(urlparse.parse_qsl(url))
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'text/xml; charset=UTF-8',
            'User-Agent': 'Stream-Cinema',
            'Referer': self.base_url
        }
        req = base.copy()
        for key in req:
            if key in args:
                req[key] = args[key]
        return headers, req

    def checkHTTPS(self, userData):
        util.debug('[SC] kontrolujem nastavenia HTTPS s WS [%s] [%s]' %
                   (getSetting('ws_usessl'),
                    userData.find('wants_https_download').text))
        toggle = False
        if getSettingAsBool('ws_usessl') is not True and userData.find(
                'wants_https_download').text == '1':
            toggle = True
        elif getSettingAsBool('ws_usessl') is True and userData.find(
                'wants_https_download').text == '0':
            toggle = True

        if toggle:
            headers, req = self._create_request('/', {'wst': self.token})
            try:
                util.info('[SC] userData menim nastavenie http(s)')
                data = post(
                    self._url('api/toggle_https_download/'),
                    req,
                    headers=headers,
                    output="content")
                util.debug('[SC] zmena: %s' % str(data))
            except:
                self.clearToken()
                return False
            pass

    def login(self):
        util.debug('[SC] start login')
        if not self.username or not self.password:
            util.debug('[SC] idem sa odhlasit lebo nemam meno/heslo')
            self.logout()
            return True  # fall back to free account
        elif self.token is not None:
            userData = self.userData(True)
            if userData is not False:
                self.checkHTTPS(userData)
                return True
            self.clearToken()

        if self.username and self.password and len(self.username) > 0 and len(
                self.password) > 0:
            self.logout()
            util.info('[SC] Login user=%s, pass=***** (%d)' %
                      (self.username, len(self.password)))

            try:
                # get salt
                headers, req = self._create_request(
                    '', {'username_or_email': self.username})
                data = post(
                    self._url('api/salt/'),
                    req,
                    headers=headers,
                    output="content")
                util.info('[SC] salt: %s' % str(data))
                xml = ET.fromstring(str(data))
                if not xml.find('status').text == 'OK' or xml.find(
                        'salt').text is None:
                    util.error(
                        '[SC] Server returned error status, response: %s' %
                        data)
                    return False
                salt = xml.find('salt').text
                if salt is None:
                    return False
                # create hashes
                password = hashlib.sha1(
                    md5crypt(self.password, salt.encode('utf-8'))).hexdigest()
                digest = hashlib.md5(self.username + ':Webshare:' +
                                     self.password).hexdigest()
                # login
                headers, req = self._create_request(
                    '', {
                        'username_or_email': self.username,
                        'password': password,
                        'digest': digest,
                        'keep_logged_in': 1
                    })
                data = post(
                    self._url('api/login/'),
                    req,
                    headers=headers,
                    output="content")
                xml = ET.fromstring(data)
                if not xml.find('status').text == 'OK':
                    self.clearToken()
                    util.error(
                        '[SC] Server returned error status, response: %s' %
                        data)
                    return False
                self.saveToken(xml.find('token').text)
                util.info('[SC] Login successfull')
                userData = self.userData(True)
                self.checkHTTPS(userData)
                return True
            except Exception as e:
                util.info('[SC] Login error %s' % str(e))
        self.clearToken()
        return False

    def userData(self, all=False):
        self.getToken()
        if self.token is not None:
            if self._userData is None:
                headers, req = self._create_request('/', {'wst': self.token})
                try:
                    util.info('[SC] userData')
                    data = post(
                        self._url('api/user_data/'),
                        req,
                        headers=headers,
                        output="content")
                except:
                    self.clearToken()
                    return False
                util.info('[SC] userdata dat: %s' % str(data))
                xml = ET.fromstring(str(data))
                self._userData = xml
            else:
                xml = self._userData
            if not xml.find('status').text == 'OK':
                self.clearToken()
                return False
            if all == True:
                return xml
            util.debug("[SC] userInfo: %s %s" % (xml.find('ident').text,
                                                 xml.find('vip').text))
            if xml.find('vip').text == '1':
                xbmcgui.Window(10000).setProperty('ws.vip', '1')
                xbmcgui.Window(10000).setProperty('ws.ident',
                                                  xml.find('ident').text)
                xbmcgui.Window(10000).setProperty('ws.days',
                                                  xml.find('vip_days').text)
                return int(xml.find('vip_days').text)
            else:
                xbmcgui.Window(10000).setProperty('ws.vip', '0')

        return False

    def logout(self):
        util.info("[SC] logout")
        headers, req = self._create_request('/', {'wst': self.token})
        try:
            post(
                self._url('api/logout/'),
                req,
                headers=headers,
                output="content")
        except:
            util.debug("[SC] chyba logout")
            pass
        self.clearToken()

    def clearToken(self):
        util.debug('[SC] mazem token z nastavenia')
        setSetting('ws_token', '')
        setSetting('ws_chsum', '')
        self.token = None
        self._userData = None
        pass

    def getToken(self):
        try:
            chsum = getSetting('ws_chsum')
            if chsum is None or chsum == '':
                return
            testchsum = hashlib.md5(
                "%s|%s" % (self.password.encode('utf-8'),
                           self.username.encode('utf-8'))).hexdigest()
            util.debug('[SC] chsum [%s] [%s]' % (chsum, testchsum))
            if chsum != testchsum:
                util.debug('[SC] prihlasovacie udaje niesu zhodne s tokenom')
                return

            token = getSetting('ws_token')

            if token is not None and token != '':
                util.debug('[SC] mame token')
                self.token = token
            else:
                util.debug('[SC] NEMAME token')
                self.token = None
        except:
            util.debug('[SC] token ERR %s' % str(traceback.format_exc()))
            self.token = None

    def saveToken(self, token):
        self.token = str(token)
        util.debug('[SC] ukladam token')
        setSetting('ws_token', token)
        setSetting(
            'ws_chsum',
            hashlib.md5("%s|%s" % (self.password.encode('utf-8'),
                                   self.username.encode('utf-8'))).hexdigest())
        pass

    def resolve(self, ident):
        headers, req = self._create_request('/', {
            'ident': ident,
            'wst': self.token
        })
        util.info(headers)
        util.info(req)
        try:
            data = post(
                self._url('api/file_link/'),
                req,
                headers=headers,
                output="content")
            xml = ET.fromstring(data)
            if not xml.find('status').text == 'OK':
                self.clearToken()
                util.error(
                    '[SC] Server returned error status, response: %s' % data)
                raise ResolveException(xml.find('message').text)
            return xml.find('link').text
        except Exception as e:
            self.clearToken()
            raise ResolveException(e)

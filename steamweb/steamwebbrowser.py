from __future__ import print_function
import time
import re
import os
import requests
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from base64 import b64encode
from sys import version_info
if version_info.major >= 3: # Python 3
    from http.cookiejar import LWPCookieJar
    import configparser
    from weakref import finalize
else: # Python 2
    from cookielib import LWPCookieJar
    import ConfigParser as configparser
    from builtins import input, int
    def finalize(obj, func, *args, **kwargs):
        ''' Stub method as there is no weakref.finalize in Python 2 '''
        pass

DEFAULT_USERAGENT = 'Mozilla/5.0 (compatible, MSIE 11, Windows NT 6.3; Trident/7.0; rv:11.0) like Gecko'

class SteamWebError(Exception):
    ''' Base class for exceptions in this module. '''
    pass

class LoginFailedError(SteamWebError):
    ''' Raised when the login failed (for whatever reason) '''
    pass

class IncorrectLoginError(LoginFailedError):
    ''' Raised when credentials are wrong '''
    pass

class InputError(SteamWebError):
    ''' Base class for input errors '''
    pass

class NoCaptchaCodeError(InputError):
    ''' Raised when no captcha code was given '''
    pass

class NoEmailCodeError(InputError):
    ''' Raised when no email code was given '''
    pass

class NoTwoFactorCodeError(InputError):
    ''' Raised then no two factor code was given '''
    pass

class SteamWebBrowser(object):
    name = 'SteamWebBrowser'
    browser = None
    rsa_cipher = None
    rsa_timestamp = None
    re_nonascii = re.compile(r'[^\x00-\x7F]')
    re_fs_safe = re.compile(r'[^\w-]')
    
    def __init__(self, username=None, password=None):
        self._username = self._remove_nonascii(username)
        self._password = self._remove_nonascii(password)

        self.session = requests.Session()
        self.session.mount("http://", requests.adapters.HTTPAdapter(max_retries=2))
        self.session.mount("https://", requests.adapters.HTTPAdapter(max_retries=2))
        self.set_useragent()

        cookie_file = os.path.join(self.appdata_path, self._make_fs_safe(username)+'.lwp')
        self.session.cookies = LWPCookieJar(cookie_file)
        if not os.path.exists(cookie_file):
            # initialize new (empty) cookie file
            self._save_cookies()
        else:
            # load cookies
            self.session.cookies.load(ignore_discard=True)

        # Avoid ResourceWarning: unclosed <ssl.SSLSocket ...> with python 3
        finalize(self, self.session.close)

    def _save_cookies(self):
        return self.session.cookies.save(ignore_discard=True)

    @property
    def appdata_path(self):
        if not getattr(self, '_appdata_path', False):
            # Determine and create path if not exist
            if 'STEAMWEBROWSER_HOME' in os.environ:
                confighome = os.environ['STEAMWEBROWSER_HOME']
            elif 'APPDATA' in os.environ:
                confighome = os.environ['APPDATA']
            elif 'XDG_CONFIG_HOME' in os.environ:
                confighome = os.environ['XDG_CONFIG_HOME']
            else:
                confighome = os.path.join(os.environ['HOME'], '.config')
            # Store it for later reference and create it if it does not exist
            self._appdata_path = os.path.join(confighome, self.name)
            for p in [p for p in (confighome, self._appdata_path) if not os.path.isdir(p)]:
                os.mkdir(p, 0o700)
        return self._appdata_path

    def set_useragent(self, useragent=DEFAULT_USERAGENT):
        self.session.headers.update({'User-Agent': useragent})

    def post(self, url, data=None, **kwargs):
        h = self._hash_cookies()
        r = self.session.post(url, data, **kwargs)
        # Will raise HTTPError on 4XX client error or 5XX server error response
        r.raise_for_status()
        if h != self._hash_cookies():
            # Cookies have changed
            self._save_cookies()
        return r

    def get(self, url, **kwargs):
        h = self._hash_cookies()
        r = self.session.get(url, **kwargs)
        # Will raise HTTPError on 4XX client error or 5XX server error response
        r.raise_for_status()
        if h != self._hash_cookies():
            # Cookies have changed
            self._save_cookies()
        return r
    
    def _remove_nonascii(self, instr):
        ''' Steam strips non-ascii characters before sending across the web.
        '''
        return self.re_nonascii.sub('', instr).encode('ascii')
    
    def _make_fs_safe(self, instr):
        ''' Returns a very conservative filesystem-safe name for instr.
        It avoids most non-word or digit values as is max. 27 characters long
        '''
        instr = self.re_fs_safe.sub('', instr)
        return instr[:27] # 27 + '.lwp' = 31, considered maximum
    
    @staticmethod
    def _get_donotcachetime():
        return int(round(time.time() * 1000))

    def _log_cookies(self, prefix=''):
        for c in self.session.cookies:
            print(prefix, repr(c))

    def _has_cookie(self, name, domain='steamcommunity.com'):
        if len([c for c in self.session.cookies if c.name==name and c.domain==domain]) > 0:
            return True
        return False

    def _hash_cookies(self):
        ''' Returns the hash of a list of hashes from sorted repr() of every cookie in jar as
            LWPCookieJar does not change it's hash when cookies change.
        '''
        return hash(frozenset([hash(c) for c in sorted([repr(c) for c in self.session.cookies])]))

    def _get_rsa_key(self):
        ''' get steam RSA key, build and return cipher '''
        url = 'https://steamcommunity.com/login/getrsakey/'
        values = {
                'username': self._username,
                'donotcache' : self._get_donotcachetime(),
        }
        req = self.post(url, data=values)
        data = req.json()
        if not data['success']:
            raise SteamWebError('Failed to get RSA key', data)
        # Construct RSA and cipher
        mod = int(str(data['publickey_mod']), 16)
        exp = int(str(data['publickey_exp']), 16)
        rsa = RSA.construct((mod, exp))
        self.rsa_cipher = PKCS1_v1_5.new(rsa)
        self.rsa_timestamp = data['timestamp']

    def _get_encrypted_password(self):
        if not self.rsa_cipher:
            self._get_rsa_key()
        # str.encode('base64') returns a formatted string (including newlines) so use b64encode instead
        return b64encode(self.rsa_cipher.encrypt(self._password))

    def logged_in(self):
        r = self.session.head('https://store.steampowered.com/login/')
        # Request will be redirected if we are logged in already
        return r.status_code == 302

    @staticmethod
    def _handle_captcha(captcha_data, message=''):
        ''' Called when a captcha must be solved
        Writes the image to a temporary file and asks the user to enter the code.

        Args:
            captcha_data: Bytestring of the PNG captcha image.
            message: Optional. A message from Steam service.

        Returns:
            A string containing the solved captcha code.
        '''
        from tempfile import NamedTemporaryFile
        tmpf = NamedTemporaryFile(suffix='.png')
        tmpf.write(captcha_data)
        tmpf.flush()
        print('Please take a look at the captcha image "%s" and provide the code:' % tmpf.name)
        captcha_text = input('Enter code: ')
        tmpf.close()
        return captcha_text

    @staticmethod
    def _handle_emailauth(maildomain='', message=''):
        ''' Called when SteamGuard requires authentication via e-mail.
        Asks the user to enter the code.

        Args:
            maildomain: Optional. The mail domain of the e-mail address the SteamGuard
                code is send to.
            message: Optional. A message from Steam service.

        Returns:
            A string containing the code.
        '''
        print('SteamGuard requires email authentication...')
        emailauth = input('Please enter the code sent to your mail addres at "%s": ' % maildomain)
        emailauth.upper()
        return emailauth

    @staticmethod
    def _handle_twofactor(message=''):
        ''' Called when SteamGuard requires two-factor authentication..
        Asks the user to enter the code.

        Args:
            message: Optional. A message from Steam service.

        Returns:
            A string containing the code.
        '''
        print('SteamGuard requires mobile authentication...')
        twofactorcode = input('Please enter the code sent to your phone: ')
        twofactorcode.upper()
        return twofactorcode

    def login(self, captchagid='-1', captcha_text='', emailauth='', emailsteamid='', loginfriendlyname='', twofactorcode=''):
        # Force a new RSA key request for every call
        self._get_rsa_key()

        # Login
        url = 'https://steamcommunity.com/login/dologin/'
        values = {
                'username': self._username,
                'password': self._get_encrypted_password(),
                'emailauth': emailauth, # SteamGuard email code
                'loginfriendlyname': loginfriendlyname, # SteamGuard "friendly" browser name
                'captchagid': captchagid, # ID of the captcha
                'captcha_text': captcha_text, # Captha text
                'emailsteamid': emailsteamid, # SteamGuard emailid
                'rsatimestamp': self.rsa_timestamp, # returned by getrsa call
                'remember_login': True,
                'donotcache': self._get_donotcachetime(),
                'twofactorcode' : twofactorcode,
        }

        req = self.post(url, data=values)
        data = req.json()
        if data.get('message'):
            # TODO: log message
            if data.get('message') == 'Incorrect login.':
                raise IncorrectLoginError(data.get('message'))

        if data['success'] == True and data['login_complete'] == True:
            # Transfer to get the cookies for the store page too
            data['transfer_parameters']['remember_login'] = True
            req = self.post(data['transfer_url'], data['transfer_parameters'])
            # Logged in

        elif data.get('captcha_needed') == True and data.get('captcha_gid', '-1') != '-1':
            imgdata = self.get('https://steamcommunity.com/public/captcha.php',
                                        params={'gid': data['captcha_gid']})
            captcha_text = self._handle_captcha(imgdata.content, data.get('message', ''))
            if not captcha_text:
                raise NoCaptchaCodeError('Captcha code not provided.')
            return self.login(captchagid=data['captcha_gid'], captcha_text=captcha_text)

        elif data.get('emailauth_needed') == True:
            emailauth = self._handle_emailauth(data['emaildomain'], data.get('message', ''))
            if not emailauth:
                raise NoEmailCodeError('E-mail code not provided.')
            return self.login(emailauth=emailauth, emailsteamid=data['emailsteamid'])

        elif data.get('requires_twofactor') == True:
            twofactorcode = self._handle_twofactor(data.get('message', ''))
            if not twofactorcode:
                raise NoTwoFactorCodeError('Two factor code not provided.')
            return self.login(twofactorcode=twofactorcode)

        else:
            raise LoginFailedError('Unable to login', data)

class SteamWebBrowserCfg(SteamWebBrowser):
    ''' SteamWebBrowser with built-in config file support
    '''
    def __init__(self):
        self.cfg = configparser.ConfigParser()
        cfg_path = os.path.join(self.appdata_path, 'config.cfg')
        if os.path.isfile(cfg_path):
            self.cfg.read(cfg_path)
        self._init_config(cfg_path)

        # Init superclass with username and password from config
        super(SteamWebBrowserCfg, self).__init__(
                self.cfg.get('steamweb', 'username').strip(),
                self.cfg.get('steamweb', 'password').strip()
        )
        # Overwrite User-Agent with the one in config
        self.set_useragent(self.cfg.get('steamweb', 'useragent'))

    def _init_config(self, cfg_path):
        cfg_changed = False
        if not self.cfg.has_section('steamweb'):
            self.cfg.add_section('steamweb')
            cfg_changed = True
        if not self.cfg.has_option('steamweb', 'username'):
            self.cfg.set('steamweb', 'username', input('Your Steam username: '))
            cfg_changed = True
        if not self.cfg.has_option('steamweb', 'password'):
            from getpass import getpass
            self.cfg.set('steamweb', 'password', getpass('Password: '))
            cfg_changed = True
        if not self.cfg.has_option('steamweb', 'useragent'):
            self.cfg.set(
                'steamweb',
                'useragent',
                DEFAULT_USERAGENT
            )
            cfg_changed = True

        if cfg_changed:
            with open(cfg_path, 'wb') as cfg_fd:
                self.cfg.write(cfg_fd)

# coding=utf-8
"""
Autodiscover is a Microsoft method for automatically getting the hostname of the Exchange server and the server
version of the server holding the email address using only the email address and password of the user (and possibly
User Principal Name). The protocol for autodiscovering an email address is described in detail in
http://msdn.microsoft.com/en-us/library/hh352638(v=exchg.140).aspx. Handling error messages is described here:
http://msdn.microsoft.com/en-us/library/office/dn467392(v=exchg.150).aspx. This is not fully implemented.

WARNING: We are taking many shortcuts here, like assuming SSL and following 302 Redirects automatically.
If you have problems autodiscovering, start by doing an official test at https://testconnectivity.microsoft.com
"""
from __future__ import unicode_literals

from contextlib import contextmanager
import getpass
import glob
import logging
import os
import shelve
import sys
import tempfile
from threading import Lock

import dns.resolver
from future.moves.queue import LifoQueue
from future.utils import raise_from, PY2, python_2_unicode_compatible
from six import text_type

from . import transport
from .credentials import Credentials
from .errors import AutoDiscoverFailed, AutoDiscoverRedirect, AutoDiscoverCircularRedirect, TransportError, \
    RedirectError, ErrorNonExistentMailbox, UnauthorizedError
from .protocol import BaseProtocol, Protocol
from .transport import DEFAULT_ENCODING, DEFAULT_HEADERS
from .util import create_element, get_xml_attr, add_xml_child, to_xml, is_xml, post_ratelimited, xml_to_str, \
    get_domain, CONNECTION_ERRORS, SSL_ERRORS


log = logging.getLogger(__name__)

REQUEST_NS = 'http://schemas.microsoft.com/exchange/autodiscover/outlook/requestschema/2006'
AUTODISCOVER_NS = 'http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006'
ERROR_NS = 'http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006'
RESPONSE_NS = 'http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a'

# 'shelve' may pickle objects using different pickle protocol versions. Append the python major+minor version numbers
# to the filename. Also append the username, to avoid permission errors.
major, minor = sys.version_info[:2]
user = getpass.getuser()
shelve_filename = 'exchangelib.cache.{user}.py{major}{minor}'.format(user=user, major=major, minor=minor)
AUTODISCOVER_PERSISTENT_STORAGE = os.path.join(tempfile.gettempdir(), shelve_filename)


@contextmanager
def shelve_open_with_failover(filename):
    # We can expect empty or corrupt files. Whatever happens, just delete the cache file and try again.
    # 'shelve' may add a backend-specific suffix to the file, so also delete all files with a suffix.
    # We don't know which file caused the error, so just delete them all.
    try:
        shelve_handle = shelve.open(filename)
    except Exception as e:
        for f in glob.glob(filename + '*'):
            log.warning('Deleting invalid cache file %s (%r)', f, e)
            os.unlink(f)
        shelve_handle = shelve.open(filename)
    yield shelve_handle
    if PY2:
        shelve_handle.close()


@python_2_unicode_compatible
class AutodiscoverCache(object):
    # Stores the translation from (email domain, credentials) -> AutodiscoverProtocol object so we can re-use TCP
    # connections to an autodiscover server within the same process. Also persists the email domain -> (autodiscover
    # endpoint URL, auth_type) translation to the filesystem so the cache can be shared between multiple processes.

    # According to Microsoft, we may forever cache the (email domain -> autodiscover endpoint URL) mapping, or until
    # it stops responding. My previous experience with Exchange products in mind, I'm not sure if I should trust that
    # advice. But it could save some valuable seconds every time we start a new connection to a known server. In any
    # case, the persistent storage must not contain any sensitive information since the cache could be readable by
    # unprivileged users. Domain, endpoint and auth_type are OK to cache since this info is make publicly available on
    # HTTP and DNS servers via the autodiscover protocol. Just don't persist any credentials info.

    # If an autodiscover lookup fails for any reason, the corresponding cache entry must be purged.

    # 'shelve' is supposedly thread-safe and process-safe, which suits our needs.
    def __init__(self):
        self._protocols = {}  # Mapping from (domain, credentials) to AutodiscoverProtocol

    @property
    def _storage_file(self):
        return AUTODISCOVER_PERSISTENT_STORAGE

    def clear(self):
        # Wipe the entire cache
        with shelve_open_with_failover(self._storage_file) as db:
            db.clear()
        self._protocols.clear()

    def __contains__(self, key):
        domain = key[0]
        with shelve_open_with_failover(self._storage_file) as db:
            return str(domain) in db

    def __getitem__(self, key):
        protocol = self._protocols.get(key)
        if protocol:
            return protocol
        domain, credentials = key
        with shelve_open_with_failover(self._storage_file) as db:
            endpoint, auth_type = db[str(domain)]  # It's OK to fail with KeyError here
        protocol = AutodiscoverProtocol(service_endpoint=endpoint, credentials=credentials, auth_type=auth_type)
        self._protocols[key] = protocol
        return protocol

    def __setitem__(self, key, protocol):
        # Populate both local and persistent cache
        domain = key[0]
        with shelve_open_with_failover(self._storage_file) as db:
            db[str(domain)] = (protocol.service_endpoint, protocol.auth_type)
        self._protocols[key] = protocol

    def __delitem__(self, key):
        # Empty both local and persistent cache. Don't fail on non-existing entries because we could end here
        # multiple times due to race conditions.
        domain = key[0]
        with shelve_open_with_failover(self._storage_file) as db:
            try:
                del db[str(domain)]
            except KeyError:
                pass
        try:
            del self._protocols[key]
        except KeyError:
            pass

    def close(self):
        # Close all open connections
        for (domain, _), protocol in self._protocols.items():
            log.debug('Domain %s: Closing sessions', domain)
            protocol.close()
            del protocol
        self._protocols.clear()

    def __del__(self):
        # pylint: disable=bare-except
        try:
            self.close()
        except:
            # __del__ should never fail
            pass

    def __str__(self):
        return text_type(self._protocols)


_autodiscover_cache = AutodiscoverCache()
_autodiscover_cache_lock = Lock()


def close_connections():
    _autodiscover_cache.close()


def discover(email, credentials):
    """
    Performs the autodiscover dance and returns the primary SMTP address of the account and a Protocol on success. The
    autodiscover and EWS server might not be the same, so we use a different Protocol to do the autodiscover request,
    and return a hopefully-cached Protocol to the callee.
    """
    log.debug('Attempting autodiscover on email %s', email)
    assert isinstance(credentials, Credentials)
    domain = get_domain(email)
    # We may be using multiple different credentials and changing our minds on SSL verification. This key combination
    # should be safe.
    autodiscover_key = (domain, credentials)
    # Use lock to guard against multiple threads competing to cache information
    if autodiscover_key in _autodiscover_cache:
        # Python dict() is thread safe, so accessing _autodiscover_cache without a lock should be OK
        protocol = _autodiscover_cache[autodiscover_key]
        assert isinstance(protocol, AutodiscoverProtocol)
        log.debug('Cache hit for domain %s credentials %s: %s', domain, credentials, protocol.server)
        try:
            # This is the main path when the cache is primed
            primary_smtp_address, protocol = _autodiscover_quick(credentials=credentials, email=email,
                                                                 protocol=protocol)
            assert primary_smtp_address
            assert isinstance(protocol, Protocol)
            return primary_smtp_address, protocol
        except AutoDiscoverFailed:
            # Autodiscover no longer works with this domain. Clear cache and try again
            del _autodiscover_cache[autodiscover_key]
            return discover(email=email, credentials=credentials)
        except AutoDiscoverRedirect as e:
            log.debug('%s redirects to %s', email, e.redirect_email)
            if email.lower() == e.redirect_email.lower():
                raise_from(AutoDiscoverCircularRedirect('Redirect to same email address: %s' % email), None)
            # Start over with the new email address
            return discover(email=e.redirect_email, credentials=credentials)

    log.debug('Waiting for _autodiscover_cache_lock')
    with _autodiscover_cache_lock:
        log.debug('_autodiscover_cache_lock acquired')
        # Don't recurse while holding the lock!
        if autodiscover_key in _autodiscover_cache:
            # Cache was primed by some other thread while we were waiting for the lock.
            log.debug('Cache filled for domain %s while we were waiting', domain)
        else:
            log.debug('Cache miss for domain %s credentials %s', domain, credentials)
            log.debug('Cache contents: %s', _autodiscover_cache)
            try:
                # This eventually fills the cache in _autodiscover_hostname
                primary_smtp_address, protocol = _try_autodiscover(hostname=domain, credentials=credentials,
                                                                   email=email)
                assert primary_smtp_address
                assert isinstance(protocol, Protocol)
                return primary_smtp_address, protocol
            except AutoDiscoverRedirect as e:
                if email.lower() == e.redirect_email.lower():
                    raise_from(AutoDiscoverCircularRedirect('Redirect to same email address: %s' % email), None)
                log.debug('%s redirects to %s', email, e.redirect_email)
                email = e.redirect_email
            finally:
                log.debug('Releasing_autodiscover_cache_lock')
    # We fell out of the with statement, so either cache was filled by someone else, or autodiscover redirected us to
    # another email address. Start over.
    return discover(email=email, credentials=credentials)


def _try_autodiscover(hostname, credentials, email):
    # Implements the full chain of autodiscover server discovery attempts. Tries to return autodiscover data from the
    # final host.
    try:
        return _autodiscover_hostname(hostname=hostname, credentials=credentials, email=email, has_ssl=True)
    except RedirectError as e:
        return _try_autodiscover(e.server, credentials, email)
    except AutoDiscoverFailed:
        try:
            return _autodiscover_hostname(hostname='autodiscover.%s' % hostname, credentials=credentials, email=email,
                                          has_ssl=True)
        except RedirectError as e:
            return _try_autodiscover(e.server, credentials, email)
        except AutoDiscoverFailed:
            try:
                return _autodiscover_hostname(hostname='autodiscover.%s' % hostname, credentials=credentials,
                                              email=email, has_ssl=False)
            except RedirectError as e:
                return _try_autodiscover(e.server, credentials, email)
            except AutoDiscoverFailed:
                try:
                    hostname_from_dns = _get_canonical_name(hostname='autodiscover.%s' % hostname)
                    if not hostname_from_dns:
                        hostname_from_dns = _get_hostname_from_srv(hostname='autodiscover.%s' % hostname)
                    # Start over with new hostname
                    return _try_autodiscover(hostname=hostname_from_dns, credentials=credentials, email=email)
                except AutoDiscoverFailed:
                    # Start over with new hostname
                    try:
                        hostname_from_dns = _get_hostname_from_srv(hostname='_autodiscover._tcp.%s' % hostname)
                        return _try_autodiscover(hostname=hostname_from_dns, credentials=credentials, email=email)
                    except AutoDiscoverFailed:
                        raise_from(AutoDiscoverFailed('All steps in the autodiscover protocol failed'), None)


def _get_auth_type_or_raise(url, email, hostname):
    # Returns the auth type of the URL. Raises any redirection errors
    try:
        return _get_autodiscover_auth_type(url=url, email=email)
    except RedirectError as e:
        redirect_url, redirect_hostname, redirect_has_ssl = e.url, e.server, e.has_ssl
        log.debug('We were redirected to %s', redirect_url)
        canonical_hostname = _get_canonical_name(redirect_hostname)
        if canonical_hostname:
            log.debug('Canonical hostname is %s', canonical_hostname)
            redirect_hostname = canonical_hostname
        # Try the process on the new host, without 'www'. This is beyond the autodiscover protocol and an attempt to
        # work around seriously misconfigured Exchange servers. It's probably better to just show the Exchange
        # admins the report from https://testconnectivity.microsoft.com
        if redirect_hostname.startswith('www.'):
            redirect_hostname = redirect_hostname[4:]
        if redirect_hostname == hostname:
            log.debug('We were redirected to the same host')
            raise_from(AutoDiscoverFailed('We were redirected to the same host'), None)
        raise_from(RedirectError(url='%s://%s' % ('https' if redirect_has_ssl else 'http', redirect_hostname)), None)


def _autodiscover_hostname(hostname, credentials, email, has_ssl):
    # Tries to get autodiscover data on a specific host. If we are HTTP redirected, we restart the autodiscover dance on
    # the new host.
    url = '%s://%s/Autodiscover/Autodiscover.xml' % ('https' if has_ssl else 'http', hostname)
    log.debug('Trying autodiscover on %s', url)
    auth_type = _get_auth_type_or_raise(url=url, email=email, hostname=hostname)
    autodiscover_protocol = AutodiscoverProtocol(service_endpoint=url, credentials=credentials, auth_type=auth_type)
    r = _get_autodiscover_response(protocol=autodiscover_protocol, email=email)
    domain = get_domain(email)
    try:
        ews_url, primary_smtp_address = _parse_response(r.text)
        if not primary_smtp_address:
            primary_smtp_address = email
    except (ErrorNonExistentMailbox, AutoDiscoverRedirect):
        # These are both valid responses from an autodiscover server, showing that we have found the correct
        # server for the original domain. Fill cache before re-raising
        log.debug('Adding cache entry for %s (hostname %s)', domain, hostname)
        _autodiscover_cache[(domain, credentials)] = autodiscover_protocol
        raise

    # Cache the final hostname of the autodiscover service so we don't need to autodiscover the same domain again
    log.debug('Adding cache entry for %s (hostname %s, has_ssl %s)', domain, hostname, has_ssl)
    _autodiscover_cache[(domain, credentials)] = autodiscover_protocol
    # Autodiscover response contains an auth type, but we don't want to spend time here testing if it actually works.
    # Instead of forcing a possibly-wrong auth type, just let Protocol auto-detect the auth type.
    return primary_smtp_address, Protocol(service_endpoint=ews_url, credentials=credentials, auth_type=None)


def _autodiscover_quick(credentials, email, protocol):
    r = _get_autodiscover_response(protocol=protocol, email=email)
    ews_url, primary_smtp_address = _parse_response(r.text)
    if not primary_smtp_address:
        primary_smtp_address = email
    log.debug('Autodiscover success: %s may connect to %s as primary email %s', email, ews_url, primary_smtp_address)
    # Autodiscover response contains an auth type, but we don't want to spend time here testing if it actually works.
    # Instead of forcing a possibly-wrong auth type, just let Protocol auto-detect the auth type.
    return primary_smtp_address, Protocol(service_endpoint=ews_url, credentials=credentials, auth_type=None)


def _get_autodiscover_auth_type(url, email):
    try:
        data = _get_autodiscover_payload(email=email)
        return transport.get_autodiscover_authtype(service_endpoint=url, data=data)
    except TransportError as e:
        if isinstance(e, RedirectError):
            raise
        raise_from(AutoDiscoverFailed('Error guessing auth type: %s' % e), None)
    except SSL_ERRORS as e:
        raise_from(AutoDiscoverFailed('Error guessing auth type: %s' % e), None)
    except CONNECTION_ERRORS as e:
        raise_from(AutoDiscoverFailed('Error guessing auth type: %s' % e), None)


def _get_autodiscover_payload(email):
    # Builds a full Autodiscover XML request
    payload = create_element('Autodiscover', xmlns=REQUEST_NS)
    request = create_element('Request')
    add_xml_child(request, 'EMailAddress', email)
    add_xml_child(request, 'AcceptableResponseSchema', RESPONSE_NS)
    payload.append(request)
    return xml_to_str(payload, encoding=DEFAULT_ENCODING, xml_declaration=True)


def _get_autodiscover_response(protocol, email):
    data = _get_autodiscover_payload(email=email)
    try:
        # Rate-limiting is an issue with autodiscover if the same setup is hosting EWS and autodiscover and we just
        # hammered the server with requests. We allow redirects since some autodiscover servers will issue different
        # redirects depending on the POST data content.
        session = protocol.get_session()
        r, session = post_ratelimited(protocol=protocol, session=session, url=protocol.service_endpoint,
                                      headers=DEFAULT_HEADERS.copy(), data=data, allow_redirects=True)
        protocol.release_session(session)
        log.debug('Response headers: %s', r.headers)
    except RedirectError:
        raise
    except (TransportError, UnauthorizedError):
        log.debug('No access to %s using %s', protocol.service_endpoint, protocol.auth_type)
        raise_from(
            AutoDiscoverFailed('No access to %s using %s' % (protocol.service_endpoint, protocol.auth_type)), None
        )
    if not is_xml(r.text):
        # This is normal - e.g. a greedy webserver serving custom HTTP 404's as 200 OK
        log.debug('URL %s: This is not XML: %s', protocol.service_endpoint, r.text[:1000])
        raise AutoDiscoverFailed('URL %s: This is not XML: %s' % (protocol.service_endpoint, r.text[:1000]))
    return r


def _raise_response_errors(elem):
    # Find an error message in the response and raise the relevant exception
    try:
        resp = elem.find('{%s}Response' % ERROR_NS)
        error = resp.find('{%s}Error' % ERROR_NS)
        errorcode = get_xml_attr(error, '{%s}ErrorCode' % ERROR_NS)
        message = get_xml_attr(error, '{%s}Message' % ERROR_NS)
        if message in ('The e-mail address cannot be found.', "The email address can't be found."):
            raise ErrorNonExistentMailbox('The SMTP address has no mailbox associated with it')
        raise AutoDiscoverFailed('Unknown error %s: %s' % (errorcode, message))
    except AttributeError:
        raise_from(AutoDiscoverFailed('Unknown autodiscover response: %s' % xml_to_str(elem)), None)


def _parse_response(response):
    # We could return lots more interesting things here
    if not is_xml(response):
        raise AutoDiscoverFailed('Unknown autodiscover response: %s' % response)
    autodiscover = to_xml(response)
    resp = autodiscover.find('{%s}Response' % RESPONSE_NS)
    if resp is None:
        _raise_response_errors(autodiscover)
    account = resp.find('{%s}Account' % RESPONSE_NS)
    action = get_xml_attr(account, '{%s}Action' % RESPONSE_NS)
    redirect_email = get_xml_attr(account, '{%s}RedirectAddr' % RESPONSE_NS)
    if action == 'redirectAddr' and redirect_email:
        # This is redirection to e.g. Office365
        raise AutoDiscoverRedirect(redirect_email)
    # The AccountType element is only available if we are not redirecting
    assert get_xml_attr(account, '{%s}AccountType' % RESPONSE_NS) == 'email'
    # AutoDiscoverSMTPAddress might not be present in the XML, so primary_smtp_address might be None. In this
    # case, the original email address IS the primary address
    user = resp.find('{%s}User' % RESPONSE_NS)
    primary_smtp_address = get_xml_attr(user, '{%s}AutoDiscoverSMTPAddress' % RESPONSE_NS)
    protocols = {get_xml_attr(p, '{%s}Type' % RESPONSE_NS): p for p in account.findall('{%s}Protocol' % RESPONSE_NS)}
    # There are three possible protocol types: EXCH, EXPR and WEB.
    # EXPR is meant for EWS. See http://blogs.technet.com/b/exchange/archive/2008/09/26/3406344.aspx
    # We allow fallback to EXCH if EXPR is not available to support installations where EXPR is not available.
    try:
        protocol = protocols['EXPR']
    except KeyError:
        try:
            protocol = protocols['EXCH']
        except KeyError:
            # Neither type was found. Give up
            raise_from(AutoDiscoverFailed('Invalid AutoDiscover response: %s' % xml_to_str(autodiscover)), None)

    ews_url = get_xml_attr(protocol, '{%s}EwsUrl' % RESPONSE_NS)
    log.debug('Primary SMTP: %s, EWS endpoint: %s', primary_smtp_address, ews_url)
    assert ews_url and primary_smtp_address
    return ews_url, primary_smtp_address


def _get_canonical_name(hostname):
    log.debug('Attempting to get canonical name for %s', hostname)
    resolver = dns.resolver.Resolver()
    resolver.timeout = AutodiscoverProtocol.TIMEOUT
    try:
        canonical_name = resolver.query(hostname).canonical_name.to_unicode().rstrip('.')
    except dns.resolver.NXDOMAIN:
        log.debug('Nonexistent domain %s', hostname)
        return None
    if canonical_name != hostname:
        log.debug('%s has canonical name %s', hostname, canonical_name)
        return canonical_name
    return None


def _get_hostname_from_srv(hostname):
    # An SRV entry may contain e.g.:
    #   canonical name = mail.ucl.dk.
    #   service = 8 100 443 webmail.ucn.dk.
    # or throw dns.resolver.NoAnswer
    # The first three numbers in the service line are priority, weight, port
    log.debug('Attempting to get SRV record on %s', hostname)
    resolver = dns.resolver.Resolver()
    resolver.timeout = AutodiscoverProtocol.TIMEOUT
    try:
        answers = resolver.query(hostname, 'SRV')
        for rdata in answers:
            try:
                vals = rdata.to_text().strip().rstrip('.').split(' ')
                # pylint: disable=expression-not-assigned
                int(vals[0]), int(vals[1]), int(vals[2])  # Just to raise errors if these are not ints
                svr = vals[3]
            except (ValueError, KeyError):
                raise_from(
                    AutoDiscoverFailed('Incompatible SRV record for %s (%s)' % (hostname, rdata.to_text())), None
                )
            else:
                return svr
    except dns.resolver.NoNameservers:
        raise_from(AutoDiscoverFailed('No name servers for %s' % hostname), None)
    except dns.resolver.NoAnswer:
        raise_from(AutoDiscoverFailed('No SRV record for %s' % hostname), None)
    except dns.resolver.NXDOMAIN:
        raise_from(AutoDiscoverFailed('Nonexistent domain %s' % hostname), None)


@python_2_unicode_compatible
class AutodiscoverProtocol(BaseProtocol):
    # Protocol which implements the bare essentials for autodiscover
    TIMEOUT = 10  # Seconds

    def __init__(self, *args, **kwargs):
        super(AutodiscoverProtocol, self).__init__(*args, **kwargs)
        self._session_pool = LifoQueue(maxsize=self.SESSION_POOLSIZE)
        for _ in range(self.SESSION_POOLSIZE):
            self._session_pool.put(self.create_session(), block=False)

    def __str__(self):
        return '''\
Autodiscover endpoint: %s
Auth type: %s''' % (
            self.service_endpoint,
            self.auth_type,
        )

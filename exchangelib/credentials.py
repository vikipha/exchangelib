# coding=utf-8
"""
Implements an Exchange user object and access types. Exchange provides two different ways of granting access for a
login to a specific account. Impersonation is used mainly for service accounts that connect via EWS. Delegate is used
for ad-hoc access e.g. granted manually by the user.
See http://blogs.msdn.com/b/exchangedev/archive/2009/06/15/exchange-impersonation-vs-delegate-access.aspx
"""
from __future__ import unicode_literals

import logging

from future.utils import python_2_unicode_compatible

log = logging.getLogger(__name__)

IMPERSONATION = 'impersonation'
DELEGATE = 'delegate'


@python_2_unicode_compatible
class Credentials(object):
    """
    Keeps login info the way Exchange likes it.

    :param username: Usernames for authentication are of one of these forms:
    * PrimarySMTPAddress
    * WINDOMAIN\\username
    * User Principal Name (UPN)

    :param password: Clear-text password
    """
    EMAIL = 'email'
    DOMAIN = 'domain'
    UPN = 'upn'

    def __init__(self, username, password):
        if username.count('@') == 1:
            self.type = self.EMAIL
        elif username.count('\\') == 1:
            self.type = self.DOMAIN
        else:
            self.type = self.UPN
        self.username = username
        self.password = password

    @property
    def fail_fast(self):
        # Used to choose the error handling policy. When True, a fault-tolerant policy is used. False, a fail-fast
        # policy is used.
        return True

    def __eq__(self, other):
        return self.username == other.username and self.password == other.password

    def __hash__(self):
        return hash((self.username, self.password))

    def __repr__(self):
        return self.__class__.__name__ + repr((self.username, '********'))

    def __str__(self):
        return self.username


class ServiceAccount(Credentials):
    def __init__(self, username, password, max_wait=3600):
        """
        A Credentials class that enables fault-tolerance handling. Tells internal methods to do an exponential backoff
        when requests start failing, and wait up to max_wait seconds before failing.
        """
        super(ServiceAccount, self).__init__(username, password)
        self.max_wait = max_wait

    @property
    def fail_fast(self):
        return False

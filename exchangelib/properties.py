from __future__ import unicode_literals

import abc
import logging

from six import text_type, string_types

from .fields import SubField, TextField, EmailField, ChoiceField, DateTimeField, EWSElementField, MailboxField, \
    Choice, BooleanField, IdField, ExtendedPropertyField
from .services import MNS, TNS
from .util import get_xml_attr, create_element, set_xml_value, value_to_xml_text

string_type = string_types[0]
log = logging.getLogger(__name__)


class Body(text_type):
    # Helper to mark the 'body' field as a complex attribute.
    # MSDN: https://msdn.microsoft.com/en-us/library/office/jj219983(v=exchg.150).aspx
    body_type = 'Text'


class HTMLBody(Body):
    # Helper to mark the 'body' field as a complex attribute.
    # MSDN: https://msdn.microsoft.com/en-us/library/office/jj219983(v=exchg.150).aspx
    body_type = 'HTML'


class EWSElement(object):
    __metaclass__ = abc.ABCMeta

    ELEMENT_NAME = None
    FIELDS = []
    NAMESPACE = TNS  # Either TNS or MNS

    __slots__ = tuple()

    def __init__(self, **kwargs):
        for f in self.FIELDS:
            setattr(self, f.name, kwargs.pop(f.name, None))
        if kwargs:
            raise AttributeError("%s are invalid kwargs for this class" % ', '.join("'%s'" % k for k in kwargs.keys()))

    def clean(self, version=None):
        # Validate attribute values using the field validator
        for f in self.FIELDS:
            if not f.supports_version(version):
                continue
            if isinstance(f, ExtendedPropertyField) and not hasattr(self, f.name):
                # The extended field may have been registered after this item was created. Set default values.
                setattr(self, f.name, f.clean(None, version=version))
                continue
            val = getattr(self, f.name)
            setattr(self, f.name, f.clean(val, version=version))

    @classmethod
    def from_xml(cls, elem, account):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (cls, elem.tag, cls.response_tag())
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.FIELDS}
        elem.clear()
        return cls(**kwargs)

    def to_xml(self, version):
        self.clean(version=version)
        # WARNING: The order of addition of XML elements is VERY important. Exchange expects XML elements in a
        # specific, non-documented order and will fail with meaningless errors if the order is wrong.

        # Call create_element() without args, to not fill up the cache with unique attribute values.
        elem = create_element(self.request_tag())

        # Add attributes
        for f in self.attribute_fields():
            if f.is_read_only:
                continue
            value = getattr(self, f.name)
            if value is None or (f.is_list and not value):
                continue
            elem.set(f.field_uri, value_to_xml_text(getattr(self, f.name)))

        # Add elements and values
        for f in self.supported_fields(version=version):
            if f.is_read_only:
                continue
            value = getattr(self, f.name)
            if value is None or (f.is_list and not value):
                continue
            set_xml_value(elem, f.to_xml(value, version=version), version)
        return elem

    @classmethod
    def request_tag(cls):
        assert cls.ELEMENT_NAME
        return {
            TNS: 't:%s' % cls.ELEMENT_NAME,
            MNS: 'm:%s' % cls.ELEMENT_NAME,
        }[cls.NAMESPACE]

    @classmethod
    def response_tag(cls):
        assert cls.NAMESPACE and cls.ELEMENT_NAME
        return '{%s}%s' % (cls.NAMESPACE, cls.ELEMENT_NAME)

    @classmethod
    def attribute_fields(cls):
        return tuple(f for f in cls.FIELDS if f.is_attribute)

    @classmethod
    def supported_fields(cls, version=None):
        # Return non-ID field names. If version is specified, only return the fields supported by this version
        return tuple(f for f in cls.FIELDS if not f.is_attribute and f.supports_version(version))

    @classmethod
    def get_field_by_fieldname(cls, fieldname):
        if not hasattr(cls, '_fields_map'):
            cls._fields_map = {f.name: f for f in cls.FIELDS}
        try:
            return cls._fields_map[fieldname]
        except KeyError:
            raise ValueError("'%s' is not a valid field on '%s'" % (fieldname, cls.__name__))

    @classmethod
    def add_field(cls, field, idx):
        # Insert a new field at the preferred place in the tuple and invalidate the fieldname cache
        cls.FIELDS.insert(idx, field)
        try:
            delattr(cls, '_fields_map')
        except AttributeError:
            pass

    @classmethod
    def remove_field(cls, field):
        # Remove the given field and invalidate the fieldname cache
        cls.FIELDS.remove(field)
        try:
            delattr(cls, '_fields_map')
        except AttributeError:
            pass

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return hash(
            tuple(tuple(getattr(self, f.name) or ()) if f.is_list else getattr(self, f.name) for f in self.FIELDS)
        )

    def __str__(self):
        return self.__class__.__name__ + '(%s)' % ', '.join(
            '%s=%s' % (f.name, repr(getattr(self, f.name))) for f in self.FIELDS if getattr(self, f.name) is not None
        )

    def __repr__(self):
        return self.__class__.__name__ + '(%s)' % ', '.join(
            '%s=%s' % (f.name, repr(getattr(self, f.name))) for f in self.FIELDS
        )


class MessageHeader(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565307(v=exchg.150).aspx
    ELEMENT_NAME = 'InternetMessageHeader'

    FIELDS = [
        TextField('name', field_uri='HeaderName', is_attribute=True),
        SubField('value'),
    ]

    __slots__ = ('name', 'value')


class ItemId(EWSElement):
    # 'id' and 'changekey' are UUIDs generated by Exchange
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580234(v=exchg.150).aspx
    ELEMENT_NAME = 'ItemId'

    ID_ATTR = 'Id'
    CHANGEKEY_ATTR = 'ChangeKey'
    FIELDS = [
        IdField('id', field_uri=ID_ATTR, is_required=True),
        IdField('changekey', field_uri=CHANGEKEY_ATTR, is_required=False),
    ]

    __slots__ = ('id', 'changekey')

    def __init__(self, *args, **kwargs):
        if not kwargs:
            # Allow to set attributes without keyword
            kwargs = dict(zip(self.__slots__, args))
        super(ItemId, self).__init__(**kwargs)


class ParentItemId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa563720(v=exchg.150).aspx
    ELEMENT_NAME = 'ParentItemId'
    NAMESPACE = MNS

    __slots__ = ItemId.__slots__


class RootItemId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/bb204277(v=exchg.150).aspx
    ELEMENT_NAME = 'RootItemId'
    NAMESPACE = MNS

    ID_ATTR = 'RootItemId'
    CHANGEKEY_ATTR = 'RootItemChangeKey'
    FIELDS = [
        IdField('id', field_uri=ID_ATTR, is_required=True),
        IdField('changekey', field_uri=CHANGEKEY_ATTR, is_required=True),
    ]

    __slots__ = ItemId.__slots__


class ConversationId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899527(v=exchg.150).aspx
    ELEMENT_NAME = 'ConversationId'

    FIELDS = [
        IdField('id', field_uri=ItemId.ID_ATTR, is_required=True),
        # Sometimes required, see MSDN link
        IdField('changekey', field_uri=ItemId.CHANGEKEY_ATTR),
    ]

    __slots__ = ItemId.__slots__


class ParentFolderId(ItemId):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa494327(v=exchg.150).aspx
    ELEMENT_NAME = 'ParentFolderId'

    __slots__ = ItemId.__slots__


class Mailbox(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa565036(v=exchg.150).aspx
    ELEMENT_NAME = 'Mailbox'

    FIELDS = [
        TextField('name', field_uri='Name'),
        EmailField('email_address', field_uri='EmailAddress'),
        ChoiceField('routing_type', field_uri='RoutingType', choices={Choice('SMTP')}, default='SMTP'),
        ChoiceField('mailbox_type', field_uri='MailboxType', choices={
            Choice('Mailbox'), Choice('PublicDL'), Choice('PrivateDL'), Choice('Contact'), Choice('PublicFolder'),
            Choice('Unknown'), Choice('OneOff')
        }, default='Mailbox'),
        EWSElementField('item_id', value_cls=ItemId, is_read_only=True),
    ]

    __slots__ = ('name', 'email_address', 'routing_type', 'mailbox_type', 'item_id')

    def clean(self, version=None):
        super(Mailbox, self).clean(version=version)
        if not self.email_address and not self.item_id:
            # See "Remarks" section of https://msdn.microsoft.com/en-us/library/office/aa565036(v=exchg.150).aspx
            raise ValueError("Mailbox must have either 'email_address' or 'item_id' set")

    def __hash__(self):
        # Exchange may add 'mailbox_type' and 'name' on insert. We're satisfied if the item_id or email address matches.
        if self.item_id:
            return hash(self.item_id)
        return hash(self.email_address.lower())


class AvailabilityMailbox(EWSElement):
    # Like Mailbox, but with slightly different attributes
    #
    # MSDN: https://msdn.microsoft.com/en-us/library/aa564754(v=exchg.140).aspx
    ELEMENT_NAME = 'Mailbox'
    FIELDS = [
        TextField('name', field_uri='Name'),
        EmailField('email_address', field_uri='Address', is_required=True),
        ChoiceField('routing_type', field_uri='RoutingType', choices={Choice('SMTP')}, default='SMTP'),
    ]

    __slots__ = ('name', 'email_address', 'routing_type')

    def __hash__(self):
        # Exchange may add 'name' on insert. We're satisfied if the email address matches.
        return hash(self.email_address.lower())

    @classmethod
    def from_mailbox(cls, mailbox):
        assert isinstance(mailbox, Mailbox)
        return cls(name=mailbox.name, email_address=mailbox.email_address, routing_type=mailbox.routing_type)


class Attendee(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/aa580339(v=exchg.150).aspx
    ELEMENT_NAME = 'Attendee'

    RESPONSE_TYPES = {'Unknown', 'Organizer', 'Tentative', 'Accept', 'Decline', 'NoResponseReceived'}

    FIELDS = [
        MailboxField('mailbox', is_required=True),
        ChoiceField('response_type', field_uri='ResponseType', choices={Choice(c) for c in RESPONSE_TYPES},
                    default='Unknown'),
        DateTimeField('last_response_time', field_uri='LastResponseTime'),
    ]

    __slots__ = ('mailbox', 'response_type', 'last_response_time')

    def __hash__(self):
        # TODO: maybe take 'response_type' and 'last_response_time' into account?
        return hash(self.mailbox)


class RoomList(Mailbox):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899514(v=exchg.150).aspx
    ELEMENT_NAME = 'RoomList'
    NAMESPACE = MNS

    __slots__ = Mailbox.__slots__

    @classmethod
    def response_tag(cls):
        # In a GetRoomLists response, room lists are delivered as Address elements
        # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899404(v=exchg.150).aspx
        return '{%s}Address' % TNS


class Room(Mailbox):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899479(v=exchg.150).aspx
    ELEMENT_NAME = 'Room'

    __slots__ = Mailbox.__slots__

    @classmethod
    def from_xml(cls, elem, account):
        if elem is None:
            return None
        assert elem.tag == cls.response_tag(), (elem.tag, cls.response_tag())
        id_elem = elem.find('{%s}Id' % TNS)
        res = cls(
            name=get_xml_attr(id_elem, '{%s}Name' % TNS),
            email_address=get_xml_attr(id_elem, '{%s}EmailAddress' % TNS),
            mailbox_type=get_xml_attr(id_elem, '{%s}MailboxType' % TNS),
            item_id=ItemId.from_xml(elem=id_elem.find(ItemId.response_tag()), account=account),
        )
        elem.clear()
        return res


class Member(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/dd899487(v=exchg.150).aspx
    ELEMENT_NAME = 'Member'

    FIELDS = [
        MailboxField('mailbox', is_required=True),
        ChoiceField('status', field_uri='Status', choices={
            Choice('Unrecognized'), Choice('Normal'), Choice('Demoted')
        }, default='Normal'),
    ]

    __slots__ = ('mailbox', 'status')

    def __hash__(self):
        # TODO: maybe take 'status' into account?
        return hash(self.mailbox)


class EffectiveRights(EWSElement):
    # MSDN: https://msdn.microsoft.com/en-us/library/office/bb891883(v=exchg.150).aspx
    ELEMENT_NAME = 'EffectiveRights'

    FIELDS = [
        BooleanField('create_associated', field_uri='CreateAssociated', default=False),
        BooleanField('create_contents', field_uri='CreateContents', default=False),
        BooleanField('create_hierarchy', field_uri='CreateHierarchy', default=False),
        BooleanField('delete', field_uri='Delete', default=False),
        BooleanField('modify', field_uri='Modify', default=False),
        BooleanField('read', field_uri='Read', default=False),
        BooleanField('view_private_items', field_uri='ViewPrivateItems', default=False),
    ]

    __slots__ = tuple(f.name for f in FIELDS)

    def __contains__(self, item):
        return getattr(self, item, False)

==========
Change Log
==========

HEAD
----


1.10.7
------
* Added support for registering extended properties on folders.
* Added support for creating, updating, deleting and emptying folders.


1.10.6
------
* Added support for getting and setting ``Account.oof_settings`` using the new ``OofSettings`` class.
* Added snake_case named shortcuts to all distinguished folders on the ``Account`` model. E.g.
  ``Account.search_folders``.


1.10.5
------
* Bugfix release


1.10.4
------
* Added support for most item fields. The remaining ones are mentioned in issue #203.


1.10.3
------
* Added an ``exchangelib.util.PrettyXmlHandler`` log handler which will pretty-print and highlight XML requests
  and responses.

1.10.2
------
* Greatly improved folder navigation. See the 'Folders' section in the README
* Added deprecation warnings for ``Account.folders`` and ``Folder.get_folder_by_name()``


1.10.1
------
* Bugfix release


1.10.0
------
* Removed the ``verify_ssl`` argument to ``Account``, ``discover`` and ``Configuration``. If you need to disable SSL
  verification, register a custom ``HTTPAdapter`` class. A sample adapter class is provided for convenience:

  .. code-block:: python

      from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
      BaseProcotol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter


1.9.6
-----
* Support new Office365 build numbers

1.9.5
-----
* Added support for the ``effective_rights``field on items and folders.
* Added support for custom ``requests`` transport adapters, to allow proxy support, custom TLS validation etc.
* Default value for the ``affected_task_occurrences`` argument to ``Item.move_to_trash()``, ``Item.soft_delete()``
  and ``Item.delete()`` was changed to ``'AllOccurrences'`` as a less surprising default when working with simple
  tasks.
* Added ``Task.complete()`` helper method to mark tasks as complete.

1.9.4
-----
* Added minimal support for the ``PostItem`` item type
* Added support for the ``DistributionList`` item type
* Added support for receiving naive datetimes from the server. They will be localized using the new ``default_timezone``
  attribute on ``Account``
* Added experimental support for recurring calendar items. See examples in issue #37.

1.9.3
-----
* Improved support for ``filter()``, ``.only()``, ``.order_by()`` etc. on indexed properties. It is now possible to
  specify labels and subfields, e.g. ``.filter(phone_numbers=PhoneNumber(label='CarPhone', phone_number='123'))``
  ``.filter(phone_numbers__CarPhone='123')``, ``.filter(physical_addresses__Home__street='Elm St. 123')``,
  `.only('physical_addresses__Home__street')`` etc.
* Improved performance of ``.order_by()`` when sorting on multiple fields.
* Implemented QueryString search. You can now filter using an EWS QueryString, e.g. ``filter('subject:XXX')``

1.9.2
-----
* Added ``EWSTimeZone.localzone()`` to get the local timezone
* Support ``some_folder.get(item_id=..., changekey=...)`` as a shortcut to get a single item when you know the ID and
  changekey.
* Support attachments on Exchange 2007

1.9.1
-----
* Fixed XML generation for Exchange 2010 and other picky server versions
* Fixed timezone localization for ``EWSTimeZone`` created from a static timezone

1.9.0
-----
* Expand support for ``ExtendedProperty`` to include all possible attributes. This required renaming the ``property_id``
  attribute to ``property_set_id``.
* When using the ``Credentials`` class, ``UnauthorizedError`` is now raised if the credentials are wrong.
* Add a new ``version`` attribute to ``Configuration``, to force the server version if version guessing does not work.
  Accepts a ``exchangelib.version.Version`` object.
* Rework bulk operations ``Account.bulk_foo()`` and ``Account.fetch()`` to return some exceptions unraised, if it is deemed
  the exception does not apply to all items. This means that e.g. ``fetch()`` can return a mix of ```Item`` and
  ``ErrorItemNotFound`` instances, if only some of the requested ``ItemId`` were valid. Other exceptions will be raised
  immediately, e.g. ``ErrorNonExistentMailbox`` because the exception applies to all items. It is the responsibility of
  the caller to check the type of the returned values.
* The ``Folder`` class has new attributes ``total_count``, ``unread_count`` and ``child_folder_count``, and a ``refresh()``
  method to update these values.
* The argument to ``Account.upload()`` was renamed from ``upload_data`` to just ``data``
* Support for using a string search expression for ``Folder.filter()`` was removed. It was a cool idea but using QuerySet
  chaining and ``Q`` objects is even cooler and provides the same functionality, and more.
* Add support for ``reminder_due_by`` and ``reminder_minutes_before_start`` fields on ``Item`` objects. Submitted by
  ``@vikipha``.
* Added a new ``ServiceAccount`` class which is like ``Credentials`` but does what ``is_service_account`` did before. If
  you need fault-tolerane and used ``Credentials(..., is_service_account=True)`` before, use ``ServiceAccount`` now. This
  also disables fault-tolerance for the ``Credentials`` class, which is in line with what most users expected.
* Added an optional ``update_fields`` attribute to ``save()`` to specify only some  fields to be updated.
* Code in in ``folders.py`` has been split into multiple files, and some classes will have new import locaions. The most
  commonly used classes have a shortcut in __init__.py
* Added support for the ``exists`` lookup in filters, e.g. ``my_folder.filter(categories__exists=True|False)`` to filter
  on the existence of that field on items in the folder.
* When filtering, ``foo__in=value`` now requires the value to be a list, and ``foo__contains`` requires the value to be
  a list if the field itself is a list, e.g. ``categories__contains=['a', 'b']``.
* Added support for fields and enum entries that are only supported in some EWS versions
* Added a new field ``Item.text_body`` which is a read-only version of HTML body content, where HTML tags are stripped
  by the server. Only supported from Exchange 2013 and up.
* Added a new choice ``WorkingElsewhere`` to the ``CalendarItem.legacy_free_busy_status`` enum. Only supported from
  Exchange 2013 and up.


1.8.1
-----
* Fix completely botched ``Message.from`` field renaming in 1.8.0
* Improve performance of QuerySet slicing and indexing. For example, ``account.inbox.all()[10]`` and
  ``account.inbox.all()[:10]`` now only fetch 10 items from the server even though ``account.inbox.all()`` could contain
  thousands of messages.

1.8.0
-----
* Renamed ``Message.from`` field to ``Message.author``. ``from`` is a Python keyword so ``from`` could only be accessed as
  ``Getattr(my_essage, 'from')`` which is just stupid.
* Make ``EWSTimeZone`` Windows timezone name translation more robust
* Add read-only ``Message.message_id`` which holds the Internet Message Id
* Memory and speed improvements when sorting querysets using ``order_by()`` on a single field.
* Allow setting ``Mailbox`` and ``Attendee``-type attributes as plain strings, e.g.:

  .. code-block:: python

      calendar_item.organizer =  'anne@example.com'
      calendar_item.required_attendees =  ['john@example.com', 'bill@example.com']

      message.to_recipients =  ['john@example.com', 'anne@example.com']


1.7.6
-----
* Bugfix release

1.7.5
-----
* ``Account.fetch()`` and ``Folder.fetch()`` are now generators. They will do nothing before being evaluated.
* Added optional ``page_size`` attribute to ``QuerySet.iterator()`` to specify the number of items to return per HTTP
  request for large query results. Default ``page_size`` is 100.
* Many minor changes to make queries less greedy and return earlier

1.7.4
-----
* Add Python2 support

1.7.3
-----
* Implement attachments support. It's now possible to create, delete and get attachments connected to any item type:

  .. code-block:: python

      from exchangelib.folders import FileAttachment, ItemAttachment

      # Process attachments on existing items
      for item in my_folder.all():
          for attachment in item.attachments:
              local_path = os.path.join('/tmp', attachment.name)
              with open(local_path, 'wb') as f:
                  f.write(attachment.content)
                  print('Saved attachment to', local_path)

      # Create a new item with an attachment
      item = Message(...)
      binary_file_content = 'Hello from unicode æøå'.encode('utf-8')  # Or read from file, BytesIO etc.
      my_file = FileAttachment(name='my_file.txt', content=binary_file_content)
      item.attach(my_file)
      my_calendar_item = CalendarItem(...)
      my_appointment = ItemAttachment(name='my_appointment', item=my_calendar_item)
      item.attach(my_appointment)
      item.save()

      # Add an attachment on an existing item
      my_other_file = FileAttachment(name='my_other_file.txt', content=binary_file_content)
      item.attach(my_other_file)

      # Remove the attachment again
      item.detach(my_file)

  Be aware that adding and deleting attachments from items that are already created in Exchange (items that have an
  ``item_id``) will update the ``changekey`` of the item.

* Implement ``Item.headers`` which contains custom Internet message headers. Primarily useful for ``Message`` objects.
  Read-only for now.


1.7.2
-----
* Implement the ``Contact.physical_addresses`` attribute. This is a list of ``exchangelib.folders.PhysicalAddress``
  items.
* Implement the ``CalendarItem.is_all_day`` boolean to create all-day appointments.
* Implement ``my_folder.export()`` and ``my_folder.upload()``. Thanks to @SamCB!
* Fixed ``Account.folders`` for non-distinguished folders
* Added ``Folder.get_folder_by_name()`` to make it easier to get sub-folders by name.
* Implement ``CalendarView`` searches as ``my_calendar.view(start=..., end=...)``. A view differs from a normal
  ``filter()`` in that a view expands recurring items and returns recurring item occurrences that are valid in the time
  span of the view.
* Persistent storage location for autodiscover cache is now platform independent
* Implemented custom extended properties. To add support for your own custom property, subclass
  ``exchangelib.folders.ExtendedProperty`` and call ``register()`` on the item class you want to use the extended
  property with. When you have registered your extended property, you can use it exactly like you would use any other
  attribute on this item type. If you change your mind, you can remove the extended property again with ``deregister()``:

  .. code-block:: python

      class LunchMenu(ExtendedProperty):
          property_id = '12345678-1234-1234-1234-123456781234'
          property_name = 'Catering from the cafeteria'
          property_type = 'String'

      CalendarItem.register('lunch_menu', LunchMenu)
      item = CalendarItem(..., lunch_menu='Foie gras et consommé de légumes')
      item.save()
      CalendarItem.deregister('lunch_menu')

* Fixed a bug on folder items where an existing HTML body would be converted to text when calling ``save()``. When
  creating or updating an item body, you can use the two new helper classes ``exchangelib.Body`` and
  ``exchangelib.HTMLBody`` to specify if your body should be saved as HTML or text. E.g.:

  .. code-block:: python

      item = CalendarItem(...)
      # Plain-text body
      item.body = Body('Hello UNIX-beard pine user!')
      # Also plain-text body, works as before
      item.body = 'Hello UNIX-beard pine user!'
      # Exchange will see this as an HTML body and display nicely in clients
      item.body = HTMLBody('<html><body>Hello happy <blink>OWA user!</blink></body></html>')
      item.save()

1.7.1
-----
* Fix bug where fetching items from a folder that can contain multiple item types (e.g. the Deleted Items folder) would
  only return one item type.
* Added ``Item.move(to_folder=...)`` that moves an item to another folder, and ``Item.refresh()`` that updates the
  Item with data from EWS.
* Support reverse sort on individual fields in ``order_by()``, e.g. ``my_folder.all().order_by('subject', '-start')``
* ``Account.bulk_create()`` was added to create items that don't need a folder, e.g. ``Message.send()``
* ``Account.fetch()`` was added to fetch items without knowing the containing folder.
* Implemented ``SendItem`` service to send existing messages.
* ``Folder.bulk_delete()`` was moved to ``Account.bulk_delete()``
* ``Folder.bulk_update()`` was moved to ``Account.bulk_update()`` and changed to expect a list of ``(Item, fieldnames)``
  tuples where Item is e.g. a ``Message`` instance and ``fieldnames`` is a list of attributes names that need updating.
  E.g.:

  .. code-block:: python

      items = []
      for i in range(4):
          item = Message(subject='Test %s' % i)
          items.append(item)
      account.sent.bulk_create(items=items)

      item_changes = []
      for i, item in enumerate(items):
          item.subject = 'Changed subject' % i
          item_changes.append(item, ['subject'])
      account.bulk_update(items=item_changes)


1.7.0
-----
* Added the ``is_service_account`` flag to ``Credentials``. ``is_service_account=False`` disables the fault-tolerant error
  handling policy and enables immediate failures.
* ``Configuration`` now expects a single ``credentials`` attribute instead of separate ``username`` and ``password``
  attributes.
* Added support for distinguished folders ``Account.trash``, ``Account.drafts``, ``Account.outbox``,
  ``Account.sent`` and ``Account.junk``.
* Renamed ``Folder.find_items()`` to ``Folder.filter()``
* Renamed ``Folder.add_items()`` to ``Folder.bulk_create()``
* Renamed ``Folder.update_items()`` to ``Folder.bulk_update()``
* Renamed ``Folder.delete_items()`` to ``Folder.bulk_delete()``
* Renamed ``Folder.get_items()`` to ``Folder.fetch()``
* Made various policies for message saving, meeting invitation sending, conflict resolution, task occurrences and
  deletion available on ``bulk_create()``, ``bulk_update()`` and ``bulk_delete()``.
* Added convenience methods ``Item.save()``, ``Item.delete()``, ``Item.soft_delete()``, ``Item.move_to_trash()``, and
  methods ``Message.send()`` and ``Message.send_and_save()`` that are specific to ``Message`` objects. These methods
  make it easier to create, update and delete single items.
* Removed ``fetch(.., with_extra=True)`` in favor of the more fine-grained ``fetch(.., only_fields=[...])``
* Added a ``QuerySet`` class that supports QuerySet-returning methods ``filter()``, ``exclude()``, ``only()``,
  ``order_by()``, ``reverse()````values()`` and ``values_list()`` that all allow for chaining. ``QuerySet`` also has
  methods ``iterator()``, ``get()``, ``count()``, ``exists()`` and ``delete()``. All these methods behave like their
  counterparts in Django.


1.6.2
-----
* Use of ``my_folder.with_extra_fields = True`` to get the extra fields in ``Item.EXTRA_ITEM_FIELDS`` is deprecated (it was
  a kludge anyway). Instead, use ``my_folder.get_items(ids, with_extra=[True, False])``. The default was also changed to
  ``True``, to avoid head-scratching with newcomers.


1.6.1
-----
* Simplify ``Q`` objects and ``Restriction.from_source()`` by using Item attribute names in expressions and kwargs
  instead of EWS FieldURI values. Change ``Folder.find_items()`` to accept either a search expression, or a list of
  ``Q`` objects just like Django ``filter()`` does. E.g.:

  .. code-block:: python

      ids = account.calendar.find_items(
            "start < '2016-01-02T03:04:05T' and end > '2016-01-01T03:04:05T' and categories in ('foo', 'bar')",
            shape=IdOnly
      )

      q1, q2 = (Q(subject__iexact='foo') | Q(subject__contains='bar')), ~Q(subject__startswith='baz')
      ids = account.calendar.find_items(q1, q2, shape=IdOnly)


1.6.0
-----
* Complete rewrite of ``Folder.find_items()``. The old ``start``, ``end``, ``subject`` and
  ``categories`` args are deprecated in favor of a Django QuerySet filter() syntax. The
  supported lookup types are ``__gt``, ``__lt``, ``__gte``, ``__lte``, ``__range``, ``__in``,
  ``__exact``, ``__iexact``, ``__contains``, ``__icontains``, ``__contains``, ``__icontains``,
  ``__startswith``, ``__istartswith``, plus an additional ``__not`` which translates to ``!=``.
  Additionally, *all* fields on the item are now supported in ``Folder.find_items()``.

  **WARNING**: This change is backwards-incompatible! Old uses of ``Folder.find_items()`` like this:

  .. code-block:: python

      ids = account.calendar.find_items(
          start=tz.localize(EWSDateTime(year, month, day)),
          end=tz.localize(EWSDateTime(year, month, day + 1)),
          categories=['foo', 'bar'],
      )

  must be rewritten like this:

  .. code-block:: python

      ids = account.calendar.find_items(
          start__lt=tz.localize(EWSDateTime(year, month, day + 1)),
          end__gt=tz.localize(EWSDateTime(year, month, day)),
          categories__contains=['foo', 'bar'],
      )

  failing to do so will most likely result in empty or wrong results.

* Added a ``exchangelib.restrictions.Q`` class much like Django Q objects that can be used to
  create even more complex filtering. Q objects must be passed directly to ``exchangelib.services.FindItem``.


1.3.6
-----
* Don't require sequence arguments to ``Folder.*_items()`` methods to support ``len()``
  (e.g. generators and ``map`` instances are now supported)
* Allow empty sequences as argument to ``Folder.*_items()`` methods


1.3.4
-----
* Add support for ``required_attendees``, ``optional_attendees`` and ``resources``
  attribute on ``folders.CalendarItem``. These are implemented with a new ``folders.Attendee``
  class.


1.3.3
-----
* Add support for ``organizer`` attribute on ``CalendarItem``.  Implemented with a
  new ``folders.Mailbox`` class.


1.2
---
* Initial import

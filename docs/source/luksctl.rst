.. _luksctl_bin:

================================
LUKSCtl: LUKS volumes management
================================

LUKSCtl allows to open, close and check encrypted volumes through a command line utility.

The ``luksctl`` script reads informations about the encrypted device in the ``cryptdev.ini`` file written by
:ref:`fastluks_bin` and uses them to run and parse ``cryptsetup``, ``dmsetup`` and ``mount``/``umount`` commands.

Three actions are possible with ``luksctl``:

* ``open``: open and mount the encrypted storage;
* ``close``: umount and close the encrypted storage;
* ``status``: show the encrypted storage status.

.. note::

   The ``luksctl`` script requires superuser rights.


------------------------------
luksctl open: open LUKS volume
------------------------------
To open a LUKS volume, ``luksctl open`` can be used, which prompts the user for the encryption passphrase:

.. code-block:: console

    (pyluks) [root@vm ~]# luksctl open
    Enter passphrase for /dev/disk/by-uuid/101de0a7-e4f5-4d40-9829-541a2b34c1bf:
    Name:              crypt
    State:             ACTIVE
    Read Ahead:        8192
    Tables present:    LIVE
    Open count:        1
    Event number:      0
    Major, minor:      252, 0
    Number of targets: 1
    UUID: CRYPT-LUKS1-101de0a7e4f54d409829541a2b34c1bf-crypt


    Encrypted volume: [ OK ]


--------------------------------
luksctl close: close LUKS volume
--------------------------------
To close a LUKS volume, ``luksctl close`` can be used:

.. code-block:: console

    (pyluks) [root@vm ~]# luksctl close
    Encrypted volume umount: [ OK ]


----------------------------------------
luksctl status: check LUKS volume status
----------------------------------------
To check if a LUKS volume is open or closed, ``luksctl status`` can be used. If the volume is open, the command output
will be similar to the following:

.. code-block:: console
    
    (pyluks) [root@pyluks-test ~]# luksctl status
    Name:              crypt
    State:             ACTIVE
    Read Ahead:        8192
    Tables present:    LIVE
    Open count:        1
    Event number:      0
    Major, minor:      252, 0
    Number of targets: 1
    UUID: CRYPT-LUKS1-101de0a7e4f54d409829541a2b34c1bf-crypt


    Encrypted volume: [ OK ]


Otherwise, if the LUKS volume is closed, the command output will be as follows:

.. code-block:: console

    (pyluks) [root@vm ~]# luksctl status
    Encrypted volume: [ FAIL ]
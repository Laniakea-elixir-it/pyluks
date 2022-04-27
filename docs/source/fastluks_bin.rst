.. _fastluks_bin:

===============
FastLUKS script
===============

The ``fastluks`` script allows to perform volume encryption and setup directly from the command line, using the
functions present in the fastluks subpackage.

This script performs basically the same steps described in :ref:`fastluks`, encrypting the device and setting up the
volume for usage. Beside those, this script has some additional steps, namely:

* It uses two lockfiles (one for encryption and one for volume setup) to avoid multiple instances of the script
  running at the same time, resulting in unwanted results during volume encryption. The lock on the lockfile is
  acquired when the script start and is released on termination or on failure.
  The ID of the process performing encryption or volume setup is written in the lockfile.
  The path to the lockfile is:
    * ``/var/run/fast-luks-encryption.lock`` for encryption;
    * ``/var/run/fast-luks-volume-setup.lock`` for volume setup.
* It writes all the information related to the device and the encryption procedure into the **cryptdev.ini file**,
  which is used by luksctl and luksctl_api to get information about the encrypted device and to set the log files
  path
* It writes two files (one at end of the encryption and one at the end of the volume setup) that are read by
  the `Laniakea luks-encryption ansible role <https://github.com/Laniakea-elixir-it/ansible-role-luks-encryption>`_ to
  ensure that volume encryption is ended successfully.
    * The path to the success files for encryption is ``/var/run/fast-luks-encryption.success``, where the string
      ``LUKS encryption completed.`` is written.
    * The path to the success file for volume setup is ``/var/run/fast-luks-volume-setup.success``, where the string
      ``Volume setup completed.`` is written.


----------------
Script arguments
----------------
After installing pyluks in a virtual environment and activating it, the ``fastluks`` script can be run.
The arguments that can be passed to the script can be seen with ``fastluks -h``:

============================= ================================================================= ===========================
        Argument                                        Description                                       Default
============================= ================================================================= ===========================
``--device``                  Device to encrypt                                                 /dev/vdb
``--cryptdev``                Name of the encrypted device                                      crypt
``--mountpoint``              Path where the encrypted device is mounted                        /export
``--filesystem``              Encrypted device filesystem                                       ext4
``--cipher``                  Cipher algorithm used for encryption                              aes-xts-plain64
``--key-size``                Key size used for encryption                                      256
``--hash``                    Hash algorithm used for encryption                                sha256
``--header-backup-dir``       Directory where the header backup is stored                       /etc/luks
``--header-backup-file``      Name of the file containing the header backup                     luks-header.bck
``--cryptdev-file``           Path where the cryptdev.ini file is stored                        /etc/luks/luks-cryptdev.ini
``--passphrase-length``       Length of the auto-generated passphrase for encryption            8
``--passphrase``              Optional argument for setting a custom passphrase                 None
``--save-passphrase-locally`` If set, the passphrase is stored locally in the cryptdev.ini file False
``--vault``                   If set, the passphrase is stored on Vault                         False
``--vault-url``               Vault instance URL                                                None
``--wrapping-token``          Wrapping token to write the secret to Vault                       None
``--secret-path``             Path were the secret is stored in Vault                           None
``--user-key``                Vault secret key                                                  None
``-V``                        Return fastluks version                                           //
============================= ================================================================= ===========================


---------------------
Passphrase management
---------------------
The ``fastluks`` script provides two solutions for the encryption passphrase management:

* The passphrase can be stored in plain text in the **cryptdev.ini file**. This option is usually used for testing
  purposes, since in this way the passphrase can be retrieved and the data on the volume can be decrypted by anyone
  having access to the machine.
* The passphrase can be stored in HashiCorp Vault, a tool for managing and securely accessing secrets. A properly
  configured Vault instance is needed for this option, see `Laniakea documentation on Vault configuration 
  <https://laniakea.readthedocs.io/en/latest/admin_documentation/vault/vault_config.html>`_ for a description on the
  configuration used in the Laniakea usecase.


--------------
Usage examples
--------------
As described above, two solutions are possible for passphrase management. These correspond to different arguments
passed to the ``fastluks`` script:

* To store the passphrase locally in plaintext, the ``--save-passphrase-locally`` flag is used.
* To store the passphrase on an existing Vault instance, the ``--vault`` flag is used in conjuction with the Vault-related
  arguments, ``--vault-url``, ``--wrapping-token``, ``--secret-path`` and ``--user-key``.

.. note::

   The script requires superuser rights.


Saving the passphrase locally
=============================
For test purposes, it may be useful to run the script without using a Vault instance to store the passphrase.
With ``--save-passphrase-locally``, the passphrase is stored in the cryptdev.ini file together with the other
information related to the encrypted device.

In this case, the encryption procedure can be run just by specifying the device and the mentioned flag:


.. code-block:: console

  (pyluks) [root@vm ~]# lsblk
  NAME   MAJ:MIN RM SIZE RO TYPE MOUNTPOINT
  vda    253:0    0  20G  0 disk
  └─vda1 253:1    0  20G  0 part /
  vdb    253:16   0   1G  0 disk

  (pyluks) [root@pyluks-test ~]# fastluks --device /dev/vdb --save-passphrase-locally
  INFO 2022-04-08 13:53:53 Check if the required applications are installed...
  INFO 2022-04-08 13:53:53 cryptsetup is not installed. Installing...
  INFO 2022-04-08 13:53:53 Distribution: CentOS. Using yum.
  INFO 2022-04-08 13:53:56 cryptsetup installed.
  INFO 2022-04-08 13:53:56 Start the encryption procedure.
  DEBUG 2022-04-08 13:53:56 LUKS header information for /dev/vdb
  DEBUG 2022-04-08 13:53:56 Cipher algorithm: aes-xts-plain64
  DEBUG 2022-04-08 13:53:56 Hash algorithm sha256
  DEBUG 2022-04-08 13:53:56 Keysize: 256
  DEBUG 2022-04-08 13:53:56 Device: /dev/vdb
  DEBUG 2022-04-08 13:53:56 Crypt device: crypt
  DEBUG 2022-04-08 13:53:56 Mapper: /dev/mapper/crypt
  DEBUG 2022-04-08 13:53:56 Mountpoint: /export
  DEBUG 2022-04-08 13:53:56 File system: ext4
  INFO 2022-04-08 13:54:01 Open LUKS volume
  INFO 2022-04-08 13:54:03 Device informations and key have been saved in /etc/luks/luks-cryptdev.ini
  INFO 2022-04-08 13:54:03 SUCCESSFUL.
  INFO 2022-04-08 13:54:03 Creating filesystem.
  INFO 2022-04-08 13:54:04 Mounting encrypted device.
  INFO 2022-04-08 13:54:04 SUCCESSFUL.

  (pyluks) [root@vm ~]# lsblk
  NAME    MAJ:MIN RM  SIZE RO TYPE  MOUNTPOINT
  vda     253:0    0   20G  0 disk
  └─vda1  253:1    0   20G  0 part  /
  vdb     253:16   0    1G  0 disk
  └─crypt 252:0    0 1022M  0 crypt /export

With this procedure, the cryptdev.ini file (written by default in ``/etc/luks/luks-cryptdev.ini``) should look like this:

.. code-block:: text

  [luks]
  cipher_algorithm = aes-xts-plain64
  hash_algorithm = sha256
  keysize = 256
  device = /dev/vdb
  uuid = 837c40b0-99a4-421c-bb90-a3b022107157
  cryptdev = crypt
  mapper = /dev/mapper/crypt
  mountpoint = /export
  filesystem = ext4
  header_path = /etc/luks/luks-header.bck
  passphrase = PYVzS2yf



Saving the passphrase in Vault
==============================
This solution is preferred in production, since it allows to securely store and retrive the passphrase. Also, through
Vault's secrets management and luksctl_api it's possible to check the volume status and open it with an API call.
More informations on how the luksctl api works in the :ref:`luksctl_api` page.

In this case, the ``fastluks`` script must be run with the ``--vault`` flag and the following additional arguments: ``--vault-url``,
``--wrapping-token``, ``--secret-path``, ``--user-key``

.. code-block:: console

  (pyluks) [root@vm ~]# lsblk
  NAME   MAJ:MIN RM SIZE RO TYPE MOUNTPOINT
  vda    253:0    0  20G  0 disk
  └─vda1 253:1    0  20G  0 part /
  vdb    253:16   0   1G  0 disk

  (pyluks) [root@vm ~]# fastluks --device --vault --vault-url http://vault_instance_url/ --wrapping-token wrapping_token_string --secret-path /path/to/secret --user-key secret_key
  INFO 2022-04-13 12:35:45 Check if the required applications are installed...
  INFO 2022-04-13 12:35:45 dmsetup is already installed.
  INFO 2022-04-13 12:35:45 cryptsetup is not installed. Installing...
  INFO 2022-04-13 12:35:45 Distribution: CentOS. Using yum.
  INFO 2022-04-13 12:35:48 cryptsetup installed.
  INFO 2022-04-13 12:35:49 Start the encryption procedure.
  DEBUG 2022-04-13 12:35:49 LUKS header information for /dev/vdb
  DEBUG 2022-04-13 12:35:49 Cipher algorithm: aes-xts-plain64
  DEBUG 2022-04-13 12:35:49 Hash algorithm sha256
  DEBUG 2022-04-13 12:35:49 Keysize: 256
  DEBUG 2022-04-13 12:35:49 Device: /dev/vdb
  DEBUG 2022-04-13 12:35:49 Crypt device: crypt
  DEBUG 2022-04-13 12:35:49 Mapper: /dev/mapper/crypt
  DEBUG 2022-04-13 12:35:49 Mountpoint: /export
  DEBUG 2022-04-13 12:35:49 File system: ext4
  INFO 2022-04-13 12:35:54 Passphrase stored in Vault
  INFO 2022-04-13 12:35:54 Open LUKS volume
  INFO 2022-04-13 12:35:57 Device informations have been saved in /etc/luks/luks-cryptdev.ini
  INFO 2022-04-13 12:35:57 SUCCESSFUL.
  INFO 2022-04-13 12:35:57 Creating filesystem.
  INFO 2022-04-13 12:35:57 Mounting encrypted device.

  (pyluks) [root@vm ~]# lsblk
  NAME    MAJ:MIN RM  SIZE RO TYPE  MOUNTPOINT
  vda     253:0    0   20G  0 disk
  └─vda1  253:1    0   20G  0 part  /
  vdb     253:16   0    1G  0 disk
  └─crypt 252:0    0 1022M  0 crypt /export
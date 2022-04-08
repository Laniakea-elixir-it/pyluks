.. _fastluks:

=====================================
fastluks: volume encryption and setup
=====================================

The fastluks subpackage provides basic functionalities to set up and encrypt a volume device. These functions are provided through the device class.
An object of this class can be instantiated by defining four attributes:

* **device_name**: the name of the volume to be encrypted.
* **cryptdev**: the name of the cryptdevice which is mapped to the device itself once it's encrypted.
* **mountpoint**: mountpoint for the cryptdevice.
* **filesystem**: filesystem for the device.


--------------------
Install dependencies
--------------------
To encrypt a device, some preliminary steps are required. First of all, it's necessary to install the command line tool
**cryptsetup** and the kernel module **dm-crypt**, on which pyluks is based.
To install these two dependencies open a Python command prompt:

.. warning::

   Currently, pyluks supports CentOS and Ubuntu and has been tested on CentOS7, Ubuntu 18.04 and Ubuntu 20.04.

.. note::

   For most operations related to device encryption, root privileges are required.
   Open the Python command prompt as root user:
   
   .. code-block:: console
      
      [user@vm ~]$ sudo su -
      [root@vm ~]$ . /path/to/pyluks_venv/bin/activate
      (pyluks_venv) [root@vm ~]$ python3


.. code-block:: python

   >>> from pyluks import fastluks
   >>> fastluks.check_cryptsetup()
   INFO 2022-03-30 09:29:25 Check if the required applications are installed...

   INFO 2022-03-30 09:29:25 cryptsetup is not installed. Installing...

   INFO 2022-03-30 09:29:25 Distribution: CentOS. Using yum.

   INFO 2022-03-30 09:29:25 cryptsetup installed.


-----------------
Volume encryption
-----------------

Once the dependencies are installed, it's possible to perform volume encryption. To do that, a **device** object
containing information about the device to be encrypted needs to be instantiated:

.. code-block:: python

   >>> from pyluks.fastluks import device
   >>> my_device = device(device_name='/dev/vdb', cryptdev='crypt', mountpoint='/export', filesystem='ext4')


Once the device object is created, it's possible to check that it's correctly defined and that it's not already encrypted.\
Here, ``check_vol()`` verifies that the specified mountpoint is not already mounted and that the device_name is a block device,
returning False if the check fails:

.. code-block:: python

   >>> my_device.check_vol()
   >>> my_device.is_encrypted()
   False

If the checks are passed, storage encryption can be done safely. It's possible to proceed unmounting and encrypting the device.
For a strong alphanumeric encryption passphrase, use the ``create_random_secret()`` function. The device can then be encrypted with
``luksFormat()``:

.. code-block:: python

   >>> from pyluks.fastluks import create_random_secret
   >>> secret = create_random_secret(passphrase_length=16)
   >>> print(secret)
   NcGPq6e7owcWNAc4
   >>>
   >>> my_device.umount_vol() # make sure the device is unmounted
   >>> command_stdout,_,_ = my_device.luksFormat(s3cret=secret, cipher_algorithm='aes-xts-plain64', keysize=256, hash_algorithm='sha256')
   >>> print(command_stdout)
   Command successful.

   >>> my_device.is_encrypted()
   True


Unlock and check the device
===========================
Once encrypted, the device can be unlocked, mapping the LUKS partition to a new device using the device mapper kernel module:

.. code-block:: python

   >>> my_device.open_device(secret)
   INFO 2022-03-30 09:29:25 Open LUKS volume

A final check can be done on the unlocked device.

.. code-block:: python

   >>> my_device.encryption_status()


.. note::

   The output of ``encryption_status()`` is logged to the fastluks log file. The check on a successfully encrypted device should
   return information about the device itself and should be similar to the following:

   .. code-block:: text

      /dev/mapper/crypt is active.
         type:    LUKS1
         cipher:  aes-xts-plain64
         keysize: 256 bits
         key location: dm-crypt
         device:  /dev/vdb
         sector size:  512
         offset:  4096 sectors
         size:    2093056 sectors
         mode:    read/write
      Command successful.


------------
Volume setup
------------
After encryption, the unlocked volume can be formatted and mounted to read and write data on it.

.. code-block:: python

   >>> my_device.create_fs() # create filesystem
   INFO 2022-03-30 09:29:25 Creating filesystem.

   >>> my_device.mount_vol() # mount volume
   INFO 2022-03-30 09:29:25 Mounting encrypted device.


-------------
Header backup
-------------
Since lost of a LUKS encrypted partition header results in not being able to decrypt data, it is usually a good
practice to backup the header on another disk. Header backup can be done with the ``luksHeaderBackup()`` function.
Make sure that ``luks_header_backup_dir`` exists before running this command:

.. code-block:: python

   >>> import os
   >>> os.mkdir('/etc/luks')
   >>> my_device.luksHeaderBackup(luks_header_backup_dir='/etc/luks', luks_header_backup_file='luks-header.bck')


The procedure described here can be replicated with the command line script **fastluks**, which uses the functions
in this subpackage to encrypt and setup a volume.
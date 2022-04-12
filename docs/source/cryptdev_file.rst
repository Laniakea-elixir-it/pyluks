.. _cryptdev_file:

=================
Cryptdev.ini file
=================
The cryptdev.ini file is written by :ref:`fastluks_bin` upon device encryption and is used by :ref:`luksctl_bin`
and :ref:`luksctl_api` to manage the encrypted device. The cryptdev.ini file can be found in `/etc/luks/luks-cryptdev.ini`.

It is composed of two sections:

* The ``luks`` section contains information about the encrypted device and it should not be modified. Once encryption
  is done with :ref:`fastluks_bin`, this section should look like this:

    .. code-block:: ini

        [luks]
        cipher_algorithm = aes-xts-plain64
        hash_algorithm = sha256
        keysize = 256
        device = /dev/vdb
        uuid = 101de0a7-e4f5-4d40-9829-541a2b34c1bf
        cryptdev = crypt
        mapper = /dev/mapper/crypt
        mountpoint = /export
        filesystem = ext4
        header_path = /etc/luks/luks-header.bck

* The ``logs`` section contains the paths were the logs of each pyluks script is written. Each field can be modified
  to make each script log to different paths. Once encryption is done with :ref:`fastluks_bin`, this section should
  look like this:

    .. code-block:: ini
    
        [logs]
        fastluks = /tmp/fastluks.log
        luksctl = /tmp/luksctl.log
        luksctl_api = /tmp/luksctl-api.log



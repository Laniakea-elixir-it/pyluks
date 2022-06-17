# import dependencies
import os, sys
from configparser import ConfigParser

# Import internal dependencies
from ..utilities import run_command, create_logger



################################################################################
# LOGGING FACILITY

LOGGER_NAME = 'luksctl'

# Instantiate the logger
luksctl_logger = create_logger(luks_cryptdev_file='/etc/luks/luks-cryptdev.ini',
                               logger_name=LOGGER_NAME,
                               loggers_section='logs')



################################################################################
# LUKSCtl class

class LUKSCtl:
    """Class that provides functions to manage a LUKS encrypted device. It reads the encrypted device information
    from the cryptdev .ini file.
    """


    def __init__(self, config_file):
        """Instantiate a LUKSCtl object.

        :param config_file: Path to the cryptdev .ini file.
        :type config_file: str
        """

        self.config_file = config_file

        config = ConfigParser()
        config.read(config_file)
        luks_config = config['luks']

        self.cipher_algorithm = luks_config['cipher_algorithm']
        self.hash_algorithm = luks_config['hash_algorithm']
        self.keysize = luks_config['keysize']
        self.device = luks_config['device']
        self.uuid = luks_config['uuid']
        self.cryptdev = luks_config['cryptdev']
        self.mapper = luks_config['mapper']
        self.mountpoint = luks_config['mountpoint']
        self.filesystem = luks_config['filesystem']


    def get_cipher_algorithm(self): return self.cipher_algorithm
    def get_hash_algorithm(self): return self.hash_algorithm
    def get_keysize(self): return self.keysize
    def get_device(self): return self.device
    def get_uuid(self): return self.uuid
    def get_cryptdev(self): return self.cryptdev
    def get_mapper(self): return self.mapper
    def get_mountpoint(self): return self.mountpoint
    def get_filesystem(self): return self.filesystem


    def set_cipher_algorithm(self, cipher_algorithm): self.cipher_algorithm = cipher_algorithm
    def set_hash_algorithm(self, hash_algorithm): self.hash_algorithm = hash_algorithm
    def set_keysize(self, keysize): keysize = keysize
    def set_device(self, device): self.device = device
    def set_uuid(self, uuid): self.uuid = uuid
    def set_cryptdev(self, cryptdev): self.cryptdev = cryptdev
    def set_mapper(self, mapper): self.mapper = mapper
    def set_mountpoint(self, mountpoint): self.mountpoint = mountpoint
    def set_filesystem(self, filesystem): self.filesystem = filesystem


    def dmsetup_info(self):
        """Runs the command 'dmsetup info' on the cryptdevice.

        :return: Returns the command exit code.
        :rtype: int
        """

        _, _, status = run_command(f'dmsetup info /dev/mapper/{self.cryptdev}')
        return status
  

    def display_dmsetup_info(self):
        """Displays the cryptdevice status. It prints the device information, followed by 'Encrypted volume: [ OK ]'
        if the device is correctly setup and open, otherwise it prints 'Encrypted volume: [ FAIL ]'.
        """

        stdOutValue, stdErrValue, status = run_command(f'dmsetup info /dev/mapper/{self.cryptdev}')

        if str(status) == '0':
            print(stdOutValue)
            print('Encrypted volume: [ OK ]')
            sys.exit(0)
        else:
            luksctl_logger.debug(f'[luksctl] {stdErrValue}')
            print('Encrypted volume: [ FAIL ]')
            sys.exit(1)
    

    def luksopen_device(self):
        """Opens the cryptdevice, mounts it and call the LUKSCtl.display_dmsetup_info method. It prints
        'Encrypted volume mount: [ FAIL ]' if the mount command returns an error.
        """

        run_command(f'cryptsetup luksOpen /dev/disk/by-uuid/{self.uuid} {self.cryptdev}')
    
        _, _, status = run_command(f'mount /dev/mapper/{self.cryptdev} {self.mountpoint}')
    
        if str(status) == '0':
            self.display_dmsetup_info()
        else:
            print('Encrypted volume mount: [ FAIL ]')
            sys.exit(1)
    

    def luksclose_device(self):
        """Unmounts, closes the cryptdevice and calls the LUKSCtl.dmsetup_info method. It prints
        'Encrypted volume umount: [ OK ]' if the cryptdevice is correctly closed, 'Encrypted volume umount [ FAIL ]'
        otherwise.
        """

        run_command(f'umount {self.mountpoint}') # Unmount device

        run_command(f'cryptsetup close {self.cryptdev}') # Close device

        # if dmsetup_setup fails (status 1) the volume has been correctly closed
        if str(self.dmsetup_info()) == '0':
            print('Encrypted volume umount: [ FAIL ]')
            sys.exit(1)
        else:
            print('Encrypted volume umount: [ OK ]')
            sys.exit(0)

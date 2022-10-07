# Import dependencies
import random
from string import ascii_letters, digits, ascii_lowercase
import os
import sys
from pathlib import Path
from datetime import datetime
import re
import distro
from configparser import ConfigParser

# Import internal dependencies
from ..utilities import run_command, create_logger, DEFAULT_LOGFILES
from ..vault_support import write_secret_to_vault



################################################################################
# VARIABLES

alphanum = ascii_letters + digits
#now = datetime.now().strftime('-%b-%d-%y-%H%M%S')
# Get Distribution
# Ubuntu and centos currently supported
def check_distro(function):
    """Decorator function to check that the wrapped function is run on Ubuntu or CentOS.

    :param function: Function to be wrapped.
    :type function: function
    :raises Exception: Raises an exception when the wrapped function is not run on Ubuntu or CentOS
    :return: Wrapper function
    :rtype: function
    """
    global DISTNAME
    DISTNAME = distro.id()
    def wrapper_function(*args, **kwargs):
        if DISTNAME not in ['ubuntu','centos']:
            raise Exception('Distribution not supported: Ubuntu and Centos currently supported')
        return function()
    return wrapper_function



################################################################################
# LOGGING FACILITY

LOGGER_NAME = 'fastluks'

# Instantiate the logger
fastluks_logger = create_logger(luks_cryptdev_file='/etc/luks/luks-cryptdev.ini',
                                logger_name=LOGGER_NAME,
                                loggers_section='logs')



################################################################################
# FUNCTIONS

class LUKSError(Exception):
    pass



#____________________________________
# Volume encryption and setup functions
def create_random_cryptdev_name(n=8):
    """Generates a random string of ascii lowercase characters used as cryptdev name

    :param n: Length of the string, defaults to 8
    :type n: int
    :return: Random string of n characters
    :rtype: str
    """
    return ''.join([random.choice(ascii_lowercase) for i in range(n)])


@check_distro
def install_cryptsetup(logger=None):
    """Install the cryptsetup command line tool, used to interface with dm-crypt for creating,
    accessing and managing encrypted devices. It uses either apt or yum depending on the Linux distribution.

    :param logger: Logger object used to log information about the installation of cryptsetup, defaults to None
    :type logger: logging.Logger, optional
    """
    if DISTNAME == 'ubuntu':
        fastluks_logger.info('Distribution: Ubuntu. Using apt.')
        run_command('apt-get install -y cryptsetup pv', logger)
    else:
        fastluks_logger.info('Distribution: CentOS. Using yum.')
        run_command('yum install -y cryptsetup-luks pv', logger)


@check_distro
def check_cryptsetup():
    """Checks if the dm-crypt module and cryptsetup are installed.
    """
    fastluks_logger.info('Check if the required applications are installed...')
    
    _, _, dmsetup_status = run_command('type -P dmsetup &>/dev/null')
    if dmsetup_status != 0:
        fastluks_logger.info('dmsetup is not installed. Installing...')
        if DISTNAME == 'ubuntu':
            run_command('apt-get install -y dmsetup')
        else:
            run_command('yum install -y device-mapper')
    else:
        fastluks_logger.info('dmsetup is already installed.')
    
    _, _, cryptsetup_status = run_command('type -P cryptsetup &>/dev/null')
    if cryptsetup_status != 0:
        fastluks_logger.info('cryptsetup is not installed. Installing...')
        install_cryptsetup(logger=fastluks_logger)
        fastluks_logger.info('cryptsetup installed.')
    else:
        fastluks_logger.info('cryptsetup is already installed.')


def create_random_secret(passphrase_length):
    """Creates a random passphrase of alphanumeric characters.

    :param passphrase_length: Passphrase length
    :type passphrase_length: int
    :return: Alphanumeric string of the specified length
    :rtype: str
    """
    return ''.join([random.choice(alphanum) for i in range(passphrase_length)])


def end_encrypt_procedure(SUCCESS_FILE):
    """Sends a signal to unlock waiting condition, writing 'LUKS encryption completed' in the specified
    success file. This file is used by automation software (e.g. Ansible) to make sure that the encryption
    procedure is completed.

    :param SUCCESS_FILE: Path to the encryption success file to be written.
    :type SUCCESS_FILE: str
    """
    with open(SUCCESS_FILE, 'w') as success_file:
        success_file.write('LUKS encryption completed.') # WARNING DO NOT MODFIFY THIS LINE, THIS IS A CONTROL STRING FOR ANSIBLE
    fastluks_logger.info('SUCCESSFUL.')


def end_volume_setup_procedure(SUCCESS_FILE):
    """Sends signal to unlock waiting condition, writing 'LUKS setup completed' in the specified success
    file. This file is used by automation software (e.g. Ansible) to make sure that the setup procedure
    is completed.

    :param SUCCESS_FILE: Path to the setup success file to be written.
    :type SUCCESS_FILE: str
    """
    with open(SUCCESS_FILE,'w') as success_file:
        success_file.write('Volume setup completed.') # WARNING DO NOT MODFIFY THIS LINE, THIS IS A CONTROL STRING FOR ANSIBLE
    fastluks_logger.info('SUCCESSFUL.')


def read_ini_file(cryptdev_ini_file):
    """Reads the cryptdev .ini file. Returns a dictionary containing the information of the encrypted
    device written in the .ini file.

    :param cryptdev_ini_file: Path to the cryptdev .ini file
    :type cryptdev_ini_file: str
    :return: Dictionary containing informations about the encrypted device in key-value pairs
    :rtype: dict
    """
    config = ConfigParser()
    config.read_file(open(cryptdev_ini_file))
    luks_section = config['luks']
    return {key:luks_section[key] for key in luks_section}



################################################################################
# DEVICE CLASSE

class device:
    """Device class used to create, access and manage encrypted devices. 
    """


    def __init__(self, device_name, cryptdev, mountpoint, filesystem,
                 cipher_algorithm='aes-xts-plain64', keysize=256, hash_algorithm='sha256'):
        """Instantiate a device object

        :param device_name: Name of the volume, e.g. /dev/vdb
        :type device_name: str
        :param cryptdev: Name of the cryptdevice, e.g. crypt
        :type cryptdev: str
        :param mountpoint: Mountpoint for the encrypted device, e.g. /export
        :type mountpoint: str
        :param filesystem: Filesystem for the volume, e.g. ext4
        :type filesystem: str
        :param cipher_algorithm: Algorithm for the encryption, e.g. aes-xts-plain64
        :type cipher_algorithm: str
        :param keysize: Key-size for the cipher algorithm, e.g. 256
        :type keysize: int
        :param hash_algorithm: Hash algorithm used for key derivaiton, e.g. sha256
        :type hash_algorithm: int
        """
        self.device_name = device_name
        self.cryptdev = cryptdev
        self.mountpoint = mountpoint
        self.filesystem = filesystem
        self.cipher_algorithm = cipher_algorithm
        self.keysize = keysize
        self.hash_algorithm = hash_algorithm

    def check_vol(self):
        """Checks if the mountpoint already has a volume mounted to it and if the device_name
        specified in the device object is a volume.

        :return: False if the device_name of the device object doesn't correspond to block device
        :rtype: bool
        """
        fastluks_logger.debug('Checking storage volume.')

        # Check if a volume is already mounted to mountpoint
        if os.path.ismount(self.mountpoint):
            mounted_device, _, _ = run_command(f'df -P {self.mountpoint} | tail -1 | cut -d" " -f 1')
            fastluks_logger.debug(f'Device name: {mounted_device}')

        else:
            # Check if device_name is a volume
            if Path(self.device_name).is_block_device():
                fastluks_logger.debug(f'External volume on {self.device_name}. Using it for encryption.')
                if not os.path.isdir(self.mountpoint):
                    fastluks_logger.debug(f'Creating {self.mountpoint}')
                    os.makedirs(self.mountpoint, exist_ok=True)
                    fastluks_logger.debug(f'Device name: {self.device_name}')
                    fastluks_logger.debug(f'Mountpoint: {self.mountpoint}')
            else:
                fastluks_logger.error('Device not mounted, exiting! Please check logfile:')
                fastluks_logger.error(f'No device mounted to {self.mountpoint}')
                run_command('df -h', logger=fastluks_logger)
                raise LUKSError('Volume checks not satisfied') # unlock and terminate process


    def is_encrypted(self):
        """Checks if the device is encrypted.

        :return: True if the volume is encrypted, otherwise False.
        :rtype: bool
        """
        fastluks_logger.debug('Checking if the volume is already encrypted.')
        devices, _, _ = run_command('lsblk -p -o NAME,FSTYPE')
        if re.search(f'{self.device_name}\s+crypto_LUKS', devices):
                fastluks_logger.debug('The volume is already encrypted')
                return True
        else:
            return False


    def umount_vol(self):
        """Unmount the device
        """
        fastluks_logger.debug('Umounting device.')
        run_command(f'umount {self.mountpoint}', logger=fastluks_logger)
        fastluks_logger.debug(f'{self.device_name} umounted, ready for encryption!')


    def luksFormat(self, s3cret):
        """Sets up a the device in LUKS encryption mode: sets up the LUKS device header and encrypts
        the passphrase with the indidcated cryptographic options. 

        :param s3cret: Passphrase for the encrypted volume.
        :type s3cret: str
        :param cipher_algorithm: Algorithm for the encryption, e.g. aes-xts-plain64
        :type cipher_algorithm: str
        :param keysize: Key-size for the cipher algorithm, e.g. 256
        :type keysize: int
        :param hash_algorithm: Hash algorithm used for key derivation, e.g. sha256
        :type hash_algorithm: str
        :return: A tuple containing stdout, stderr and status of the cryptsetup luksFormat command.
        :rtype: tuple
        """
        return run_command(f'printf "{s3cret}\n" | cryptsetup -v --cipher {self.cipher_algorithm} --key-size {self.keysize} --hash {self.hash_algorithm} --iter-time 2000 --use-urandom luksFormat {self.device_name} --batch-mode')


    def luksHeaderBackup(self, luks_header_backup_file):
        """Stores a binary backup of the device's LUKS header and keyslot area in the specified directory and file.


        :param luks_header_backup_file: File in which the header and keyslot area are stored.
        :type luks_header_backup_file: str
        :return: A tuple containing stdout, stderr and status of the cryptsetup luksFormat command.
        :rtype: tuple
        """
        return run_command(f'cryptsetup luksHeaderBackup --header-backup-file {luks_header_backup_file} {self.device_name}')


    def luksOpen(self, s3cret):
        """Opens the encrypted device.

        :param s3cret: Passphrase to open the encrypted device.
        :type s3cret: str
        :return: A tuple containing stdout, stderr and status of the cryptsetup luksOpen command 
        :rtype: tuple
        """
        return run_command(f'printf "{s3cret}\n" | cryptsetup luksOpen {self.device_name} {self.cryptdev}')


    def info(self):
        """Logs to stdout device informations and cryptographic options.

        :param cipher_algorithm: Algorithm for the encryption
        :type cipher_algorithm: str
        :param hash_algorithm: Hash algorithm used for key derivation
        :type hash_algorithm: str
        :param keysize: Key-size for the cipher algorithm
        :type keysize: int
        """
        fastluks_logger.info(f'LUKS header information for {self.device_name}')
        fastluks_logger.info(f'Cipher algorithm: {self.cipher_algorithm}')
        fastluks_logger.info(f'Hash algorithm {self.hash_algorithm}')
        fastluks_logger.info(f'Keysize: {self.keysize}')
        fastluks_logger.info(f'Device: {self.device_name}')
        fastluks_logger.info(f'Crypt device: {self.cryptdev}')
        fastluks_logger.info(f'Mapper: /dev/mapper/{self.cryptdev}')
        fastluks_logger.info(f'Mountpoint: {self.mountpoint}')
        fastluks_logger.info(f'File system: {self.filesystem}')

    def setup_device(self, luks_header_backup_file, passphrase_length, passphrase, use_vault, vault_url, wrapping_token, secret_path, user_key):
        """Performs the setup wrokflow to encrypt the device by performing the following steps:

        * Logs to stdout device informations and cryptographic options with the device.info method
        * Checks the specified passphrase or creates a new one of the specified length
        * Sets up a the device in LUKS encryption mode with the device.luksFormat method
        * Stores the passphrase to HashiCorp Vault if `use_vault` is set to True with the write_secret_to_vault function.
        * Stores the header backup with the device.luksHeaderBackup method

        It either returns the passphrase if the setup is successful or False if it fails.

        :param luks_header_backup_file: File in which the header and keyslot area are stored.
        :type luks_header_backup_file: str
        :param passphrase_length: Lenght of the passphrase to be generated.
        :type passphrase_length: int
        :param passphrase: Specified passphrase to be used for device encryption.
        :type passphrase: str
        :param use_vault: If set to True, the passphrase is stored to HashiCorp Vault.
        :type use_vault: bool
        :param vault_url: URL of Vault server. 
        :type vault_url: str
        :param wrapping_token: Wrapping token used to write the passphrase on Vault.
        :type wrapping_token: str
        :param secret_path: Vault path in which the passphrase is stored.
        :type secret_path: str
        :param user_key: Vault key associated to the passphrase.
        :type user_key: str
        :return: The passphrase if the setup is successful or False if it fails.
        :rtype: str or bool
        """
        fastluks_logger.info('Start the encryption procedure.')
        fastluks_logger.debug(f'Using {self.cipher_algorithm} algorithm to luksformat the volume.')
        fastluks_logger.debug('Start cryptsetup')
        self.info()
        fastluks_logger.debug('Cryptsetup full command:')
        fastluks_logger.debug(f'cryptsetup -v --cipher {self.cipher_algorithm} --key-size {self.keysize} --hash {self.hash_algorithm} --iter-time 2000 --use-urandom --verify-passphrase luksFormat {device} --batch-mode')

        if passphrase_length == None:
            if passphrase == None:
                fastluks_logger.error("Missing passphrase!")
                raise LUKSError('Device setup procedure failed.') # unlock and exit
            s3cret = passphrase
        else:
            s3cret = create_random_secret(passphrase_length)
        
        # Start encryption procedure
        self.luksFormat(s3cret)

        # Write the secret to vault
        if use_vault:
            write_secret_to_vault(vault_url, wrapping_token, secret_path, user_key, s3cret)
            fastluks_logger.info('Passphrase stored in Vault')

        # Backup LUKS header
        luks_header_backup_dir = os.path.dirname(luks_header_backup_file)
        if not os.path.isdir(luks_header_backup_dir):
            os.mkdir(luks_header_backup_dir)
        _, _, luksHeaderBackup_ec = self.luksHeaderBackup(luks_header_backup_file)

        if luksHeaderBackup_ec != 0:
            # Cryptsetup returns 0 on success and a non-zero value on error.
            # Error codes are:
            # 1 wrong parameters
            # 2 no permission (bad passphrase)
            # 3 out of memory
            # 4 wrong device specified
            # 5 device already exists or device is busy.
            fastluks_logger.error(f'Command cryptsetup failed with exit code {luksHeaderBackup_ec}! Mounting {self.device_name} to {self.mountpoint} and exiting.')
            if luksHeaderBackup_ec == 2:
                fastluks_logger.error('Bad passphrase. Please try again.')
            raise LUKSError('Device setup procedure failed.') # unlock and exit

        return s3cret

    def open_device(self, s3cret):
        """Opens and mounts the encrypted device.

        :param s3cret: Passphrase to open the encrypted device.
        :type s3cret: str
        :return: False if any error occur (e.g. if the passphrase is wrong or if the crypt device already exists) 
        :rtype: bool, optional
        """
        if not Path(f'/dev/mapper/{self.cryptdev}').is_block_device():
            fastluks_logger.info(f'Opening LUKS volume and mapping it to /dev/mapper/{self.cryptdev}')
            _, _, openec = self.luksOpen(s3cret)
            
            if openec != 0:
                if openec == 2:
                    fastluks_logger.error('Bad passphrase. Please try again.')
                    raise LUKSError('luksOpen failed, mapping not created.') # unlock and exit
                else:
                    fastluks_logger.error(f'Crypt device already exists! Please check logs: {LOGFILE}')
                    fastluks_logger.error('Unable to luksOpen device.')
                    fastluks_logger.error(f'/dev/mapper/{self.cryptdev} already exists.')
                    fastluks_logger.error(f'Mounting {self.device_name} to {self.mountpoint} again.')
                    run_command(f'mount {self.device_name} {self.mountpoint}', logger=fastluks_logger)
                    raise LUKSError('luksOpen failed, mapping not created.') # unlock and exit
        else:
            fastluks_logger.info(f'LUKS volume already opened and mapped to /dev/mapper/{self.cryptdev}')


    def encryption_status(self):
        """Checks cryptdevice status, with the command cryptsetup status. It logs stdout, stderr
        and status to the logfile.
        """
        fastluks_logger.debug(f'Check {self.cryptdev} status with cryptsetup status')
        run_command(f'cryptsetup -v status {self.cryptdev}', logger=fastluks_logger)


    def create_cryptdev_ini_file(self, luks_cryptdev_file, luks_header_backup_file,
                                 save_passphrase_locally, s3cret):
        """Creates the cryptdev .ini file containing information of the encrypted device under the 'luks' section.
        It also stores the default paths for the log files of fastluks, luksctl and luksctl_api subpackages in the 'logs' section.
        After creating the ini file, it logs the output of 'dmsetup info' and 'cryptsetup luksDump' commands.

        :param luks_cryptdev_file: Path to the cryptdev .ini file.
        :type luks_cryptdev_file: str
        :param cipher_algorithm: Algorithm for the encryption, e.g. aes-xts-plain64
        :type cipher_algorithm: str
        :param hash_algorithm: Hash algorithm used for the key derivation, e.g. sha256
        :type hash_algorithm: str
        :param keysize: Key-size for the cipher algorithm, e.g. 256
        :type keysize: int
        :param luks_header_backup_file: File in which the header and keyslot area are stored.
        :type luks_header_backup_file: str
        :param save_passphrase_locally: If set to true, the passphrase is written in the .ini file in plain text. This option is usually used for testing purposes.
        :type save_passphrase_locally: bool
        :param s3cret: Passphrase to open the encrypted device, written in the .ini file only if `save_passphrase_locally` is set to True
        :type s3cret: str
        """
        luksUUID, _, _ = run_command(f'cryptsetup luksUUID {self.device_name}')
        luksUUID = luksUUID.rstrip()

        with open(luks_cryptdev_file, 'w') as f:
            config = ConfigParser()
            config.add_section('luks')
            config_luks = config['luks']
            config_luks['cipher_algorithm'] = self.cipher_algorithm
            config_luks['hash_algorithm'] = self.hash_algorithm
            config_luks['keysize'] = str(self.keysize)
            config_luks['device'] = self.device_name
            config_luks['uuid'] = luksUUID
            config_luks['cryptdev'] = self.cryptdev
            config_luks['mapper'] = f'/dev/mapper/{self.cryptdev}'
            config_luks['mountpoint'] = self.mountpoint
            config_luks['filesystem'] = self.filesystem
            config_luks['header_path'] = f'{luks_header_backup_file}'

            config.add_section('logs')
            config_logs = config['logs']
            for name,logfile in DEFAULT_LOGFILES.items():
                config_logs[name] = logfile

            if save_passphrase_locally:
                config_luks['passphrase'] = s3cret
                config.write(f)
                fastluks_logger.info(f'Device informations and key have been saved in {luks_cryptdev_file}')
            else:
                config.write(f)
                fastluks_logger.info(f'Device informations have been saved in {luks_cryptdev_file}')

        run_command(f'dmsetup info /dev/mapper/{self.cryptdev}', logger=fastluks_logger)
        run_command(f'cryptsetup luksDump {self.device_name}', logger=fastluks_logger)


    def wipe_data(self):
        """Paranoid mode function: it wipes the disk by overwriting the entire drive with random data.
        It may take some time.
        """
        fastluks_logger.info('Paranoid mode selected. Wiping disk')
        fastluks_logger.info('Wiping disk data by overwriting the entire drive with random data.')
        fastluks_logger.info('This might take time depending on the size & your machine!')
        
        run_command(f'dd if=/dev/zero of=/dev/mapper/{self.cryptdev} bs=1M status=progress')
        
        fastluks_logger.info(f'Block file /dev/mapper/{self.cryptdev} created.')
        fastluks_logger.info('Wiping done.')

    def create_fs(self):
        """Creates the filesystem for the LUKS encrypted device based on the `filesystem` attribute of the device object.

        :return: False if the mkfs command fails.
        :rtype: False, optional
        """
        fastluks_logger.info('Creating filesystem.')
        fastluks_logger.debug(f'Creating {self.filesystem} filesystem on /dev/mapper/{self.cryptdev}')
        _, _, mkfs_ec = run_command(f'mkfs -t {self.filesystem} /dev/mapper/{self.cryptdev}', logger=fastluks_logger)
        if mkfs_ec != 0:
            fastluks_logger.error(f'While creating {self.filesystem} filesystem. Please check logs.')
            fastluks_logger.error('Command mkfs failed!')
            raise LUKSError('Command mkfs failed.') # unlock and exit


    def mount_vol(self):
        """Mounts the encrypted device to the 'mountpoint' specified in the device attributes.
        """
        fastluks_logger.info('Mounting encrypted device.')
        fastluks_logger.debug(f'Mounting /dev/mapper/{self.cryptdev} to {self.mountpoint}')
        run_command(f'mount /dev/mapper/{self.cryptdev} {self.mountpoint}', logger=fastluks_logger)
        run_command('df -Hv', logger=fastluks_logger)


    def encrypt(self, luks_header_backup_file, luks_cryptdev_file,
                passphrase_length, passphrase, save_passphrase_locally,
                use_vault, vault_url, wrapping_token, secret_path, user_key):
        """Performs the encryption workflow with the following steps:

        * Creates the lock file with the lock function.
        * Creates a random name for the cryptdevice with the create_random_cryptdev_name function.
        * Checks the device volume with the device.check_vol method.
        * Checks if the volume is encrypted with the device.is_encrypted method, if it's not starts the encryption.
        * Encryption procedure:
            * Unmount the volume with the device.umount_vol method
            * Performs the device setup workflow for encryption with the device.setup_device method.
            * Unlocks and exits if the setup procedure failed.
        * Opens the successfully encrypted device with the device.open_device method, unlocks and exits if it fails.
        * Checks the encryption status with the device.encryption_status method.
        * Creates the cryptdev .ini file with the device information with the device.create_cryptdev_ini_file method.
        * Ends the encryption procedure with the end_encrypt_procedure function.
        * Unlocks and exits.

        :param cipher_algorithm: Algorithm for the encryption, e.g. aes-xts-plain64
        :type cipher_algorithm: str
        :param keysize: Key-size for the cipher algorithm, e.g. 256
        :type keysize: int
        :param hash_algorithm: Hash algorithm used for the key derivation, e.g. sha256
        :type hash_algorithm: str
        :param luks_header_backup_file: File in which the header and keyslot area are stored.
        :type luks_header_backup_file: str
        :param LOCKFILE: Path to the lockfile.
        :type LOCKFILE: str
        :param SUCCESS_FILE: Path to the encryption success file.
        :type SUCCESS_FILE: str
        :param luks_cryptdev_file: Path to the cryptdev .ini file.
        :type luks_cryptdev_file: str
        :param passphrase_length: Length of the passphrase to be generated.
        :type passphrase_length: int
        :param passphrase: Specified passphrase to be used for device encryption.
        :type passphrase: str
        :param save_passphrase_locally: If set to true, the passphrase is written in the cryptdev .ini file.
        :type save_passphrase_locally: bool
        :param use_vault: If set to true, the passphrase is stored to HashiCorp Vault.
        :type use_vault: bool
        :param vault_url: URL of Vault server.
        :type vault_url: str
        :param wrapping_token: Wrapping token used to write the passphrase on Vault.
        :type wrapping_token: str
        :param secret_path: Vault path in which the passhprase is stored.
        :type secret_path: str
        :param user_key: Vault key associated to the passphrase.
        :type user_key: str
        """
        
        cryptdev = create_random_cryptdev_name() # Assign random name to cryptdev

        check_cryptsetup() # Check that cryptsetup and dmsetup are installed

        self.check_vol() # Check which virtual volume is mounted to mountpoint, unlock and exit if it's not mounted

        if not self.is_encrypted(): # Check if the volume is encrypted, if it's not start the encryption procedure
            self.umount_vol()
            s3cret = self.setup_device(luks_header_backup_file, passphrase_length, passphrase,
                                       use_vault, vault_url, wrapping_token, secret_path, user_key)
        else:
            raise LUKSError('Device is already encrypted')

        self.open_device(s3cret) # Create mapping

        self.encryption_status() # Check status

        self.create_cryptdev_ini_file(luks_cryptdev_file, luks_header_backup_file, save_passphrase_locally, s3cret) # Create ini file


    def volume_setup(self):
        """Performs the setup workflow for the encrypted volume with the following steps:

        * Creates a lockfile with the lock function.
        * Creates the encrypted volume filesystem with the device.create_fs method. Unlocks and exits if it fails.
        * Mounts the encrypted volume.
        * Creates the setup success file with the end_volume_setup_procedure function.
        * Unlocks

        :param LOCKFILE: Path to the lockfile.
        :type LOCKFILE: str
        :param SUCCESS_FILE: Path to the volume setup success file.
        :type SUCCESS_FILE: str
        """
        
        self.create_fs() # Create filesystem

        self.mount_vol() # Mount volume

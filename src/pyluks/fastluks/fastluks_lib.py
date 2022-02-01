# Import dependencies
import random
from string import ascii_letters, digits, ascii_lowercase
import os
import sys
from pathlib import Path
from datetime import datetime
import re
import zc.lockfile
import distro
from configparser import ConfigParser

# Import internal dependencies
from ..utilities import run_command, create_logger, DEFAULT_LOGFILES
from ..vault_support import write_secret_to_vault



################################################################################
# VARIABLES

alphanum = ascii_letters + digits
time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
#now = datetime.now().strftime('-%b-%d-%y-%H%M%S')
# Get Distribution
# Ubuntu and centos currently supported
DISTNAME = distro.id()
if DISTNAME not in ['ubuntu','centos']:
    raise Exception('Distribution not supported: Ubuntu and Centos currently supported')



################################################################################
# LOGGING FACILITY

LOGGER_NAME = 'fastluks'

# Instantiate the logger
fastluks_logger = create_logger(luks_cryptdev_file='/etc/luks/luks-cryptdev.ini',
                                logger_name=LOGGER_NAME,
                                loggers_section='logs')

#____________________________________
# Custom stdout logger
def check_loglevel(loglevel):
    """Check that loglevel is valid, raise an error if the loglevel is not valid.
    This function is used by the echo function.

    :param loglevel: loglevel
    :type loglevel: str
    :raises ValueError: Raises an error if the loglevel specified is not one of INFO, DEBUG WARNING or ERROR.
    """
    valid_loglevels = ['INFO','DEBUG','WARNING','ERROR']
    if loglevel not in valid_loglevels:
        raise ValueError(f'loglevel must be one of {valid_loglevels}')


def echo(loglevel, text):
    """Custom stdout logger. It prints the loglevel, time and the specified text.

    :param loglevel: loglevel. Accepted values are INFO, DEBUG, WARNING or ERROR.
    :type loglevel: str
    :param text: Text to print to stdout.
    :type text: str
    :return: The message printed to stdout, including the loglevel and time.
    :rtype: str
    """
    check_loglevel(loglevel)
    message = f'{loglevel} {time} {text}\n'
    print(message)
    return message



################################################################################
# FUNCTIONS

#____________________________________
# Lock/UnLock Section
def lock(LOCKFILE):
    """Generate lockfile in order to avoid multiple instances to encrypt at the same time.

    :param LOCKFILE: Path for the lockfile.
    :type LOCKFILE: str
    :return: lockfile instance.
    :rtype: zc.lockfile.LockFile
    """
    # Start locking attempt
    try:
        lock = zc.lockfile.LockFile(LOCKFILE, content_template='{pid};{hostname}') # storing the PID and hostname in LOCKFILE
        return lock
    except zc.lockfile.LockError:
        # Lock failed: retrieve the PID of the locking process
        with open(LOCKFILE, 'r') as lock_file:
            pid_hostname = lock_file.readline()
            PID = re.search(r'^\s(\d+);', pid_hostname).group()
        echo('ERROR', f'Another script instance is active: PID {PID}')
        sys.exit(2)

    # lock is valid and OTHERPID is active - exit, we're locked!
    echo('ERROR', f'Lock failed, PID {PID} is active')
    echo('ERROR', f'Another fastluks process is active')
    echo('ERROR', f'If you are sure fastluks is not already running,')
    echo('ERROR', f'You can remove {LOCKFILE} and restart fastluks')
    sys.exit(2)


def unlock(lock, LOCKFILE, do_exit=True, message=None):
    """Performs the unlocking of a lockfile and terminates the process if specified.

    :param lock: LockFile object instantiated by the lock function.
    :type lock: zc.lockfile.LockFile
    :param LOCKFILE: Path to the lockfile to be unlocked.
    :type LOCKFILE: str
    :param do_exit: If set to True, the process will be terminated after the unlocking, defaults to True
    :type do_exit: bool, optional
    :param message: Message printed when the process is terminated, defaults to None
    :type message: str, optional
    """
    lock.close()
    os.remove(LOCKFILE)
    if do_exit:
        sys.exit(f'UNLOCK: {message}')


def unlock_if_false(function_return, lock, LOCKFILE, message=None):
    """Calls the unlock function if the function_return argument specified is False.

    :param function_return: If this argument is False, the unlock function is called. 
    :type function_return: bool
    :param lock: LockFile instance returned by the lock function.
    :type lock: zc.lockfile.LockFile
    :param LOCKFILE: Path to the lockfile.
    :type LOCKFILE: str
    :param message: Message to be printed by the unlock function, defaults to None
    :type message: str, optional
    """
    if function_return == False:
        unlock(lock, LOCKFILE, message=message)


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



def install_cryptsetup(logger=None):
    """Install the cryptsetup command line tool, used to interface with dm-crypt for creating,
    accessing and managing encrypted devices. It uses either apt or yum depending on the Linux distribution.

    :param logger: Logger object used to log information about the installation of cryptsetup, defaults to None
    :type logger: logging.Logger, optional
    """
    if DISTNAME == 'ubuntu':
        echo('INFO', 'Distribution: Ubuntu. Using apt.')
        run_command('apt-get install -y cryptsetup pv', logger)
    else:
        echo('INFO', 'Distribution: CentOS. Using yum.')
        run_command('yum install -y cryptsetup-luks pv', logger)


@check_distro
def check_cryptsetup():
    """Checks if the dm-crypt module and cryptsetup are installed.
    """
    echo('INFO', 'Check if the required applications are installed...')
    
    _, _, dmsetup_status = run_command('type -P dmsetup &>/dev/null')
    if dmsetup_status != 0:
        echo('INFO', 'dmsetup is not installed. Installing...')
        if DISTNAME == 'ubuntu':
            run_command('apt-get install -y dmsetup')
        else:
            run_command('yum install -y device-mapper')
    
    _, _, cryptsetup_status = run_command('type -P cryptsetup &>/dev/null')
    if cryptsetup_status != 0:
        echo('INFO', 'cryptsetup is not installed. Installing...')
        install_cryptsetup(logger=fastluks_logger)
        echo('INFO', 'cryptsetup installed.')


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
    echo('INFO', 'SUCCESSFUL.')


def end_volume_setup_procedure(SUCCESS_FILE):
    """Sends signal to unlock waiting condition, writing 'LUKS setup completed' in the specified success
    file. This file is used by automation software (e.g. Ansible) to make sure that the setup procedure
    is completed.

    :param SUCCESS_FILE: Path to the setup success file to be written.
    :type SUCCESS_FILE: str
    """
    with open(SUCCESS_FILE,'w') as success_file:
        success_file.write('Volume setup completed.') # WARNING DO NOT MODFIFY THIS LINE, THIS IS A CONTROL STRING FOR ANSIBLE
    echo('INFO', 'SUCCESSFUL.')


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


def check_passphrase(passphrase_length, passphrase, passphrase_confirmation):
    """Checks that the information provided in the device.setup_device() method is adequate to setup
    the device.
    If only the passphrase length is specified, a new passphrase of the corresponding length is generated.
    Otherwise, passphrase and passphrase_confirmation need to be set to the same value and the specified
    passphrase is returned.

    :param passphrase_length: Length of the passphrase to be generated.
    :type passphrase_length: int
    :param passphrase: Specified passphrase to be used for device encryption.
    :type passphrase: str
    :param passphrase_confirmation: Passphrase confirmation, needs to be the same as 'passphrase'
    :type passphrase_confirmation: str
    :return: Generated or specified passphrase
    :rtype: str
    """
    if passphrase_length == None:
        if passphrase == None:
            echo('ERROR', "Missing passphrase!")
            return False
        if passphrase_confirmation == None:
            echo('ERROR', 'Missing confirmation passphrase!')
            return False
        if passphrase == passphrase_confirmation:
            s3cret = passphrase
        else:
            echo('ERROR', 'No matching passphrases!')
            return False
    else:
            s3cret = create_random_secret(passphrase_length)
            return s3cret



################################################################################
# DEVICE CLASSE

class device:
    """Device class used to create, access and manage encrypted devices. 
    """


    def __init__(self, device_name, cryptdev, mountpoint, filesystem):
        """Instantiate a device object

        :param device_name: Name of the volume, e.g. /dev/vdb
        :type device_name: str
        :param cryptdev: Name of the cryptdevice, e.g. crypt
        :type cryptdev: str
        :param mountpoint: Mountpoint for the encrypted device, e.g. /export
        :type mountpoint: str
        :param filesystem: Filesystem for the volume, e.g. ext4
        :type filesystem: str
        """
        self.device_name = device_name
        self.cryptdev = cryptdev
        self.mountpoint = mountpoint
        self.filesystem = filesystem


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
                return False # unlock and terminate process


    def is_encrypted(self):
        """Checks if the device is encrypted.

        :return: True if the volume is encrypted, otherwise False.
        :rtype: bool
        """
        fastluks_logger.debug('Checking if the volume is already encrypted.')
        devices, _, _ = run_command('lsblk -p -o NAME,FSTYPE')
        if re.search(f'{self.device_name}\s+crypto_LUKS', devices):
                fastluks_logger.info('The volume is already encrypted')
                return True
        else:
            return False


    def umount_vol(self):
        """Unmount the device
        """
        fastluks_logger.info('Umounting device.')
        run_command(f'umount {self.mountpoint}', logger=fastluks_logger)
        fastluks_logger.info(f'{self.device_name} umounted, ready for encryption!')


    def luksFormat(self, s3cret, cipher_algorithm, keysize, hash_algorithm):
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
        return run_command(f'printf "{s3cret}\n" | cryptsetup -v --cipher {cipher_algorithm} --key-size {keysize} --hash {hash_algorithm} --iter-time 2000 --use-urandom luksFormat {self.device_name} --batch-mode')


    def luksHeaderBackup(self, luks_header_backup_dir, luks_header_backup_file):
        """Stores a binary backup of the device's LUKS header and keyslot area in the specified directory and file.

        :param luks_header_backup_dir: Directory for the header and keyslot area backup.
        :type luks_header_backup_dir: str
        :param luks_header_backup_file: File in which the header and keyslot area are stored.
        :type luks_header_backup_file: str
        :return: A tuple containing stdout, stderr and status of the cryptsetup luksFormat command.
        :rtype: tuple
        """
        return run_command(f'cryptsetup luksHeaderBackup --header-backup-file {luks_header_backup_dir}/{luks_header_backup_file} {self.device_name}')


    def luksOpen(self, s3cret):
        """Opens the encrypted device.

        :param s3cret: Passphrase to open the encrypted device.
        :type s3cret: str
        :return: A tuple containing stdout, stderr and status of the cryptsetup luksOpen command 
        :rtype: tuple
        """
        return run_command(f'printf "{s3cret}\n" | cryptsetup luksOpen {self.device_name} {self.cryptdev}')


    def info(self, cipher_algorithm, hash_algorithm, keysize):
        """Logs to stdout device informations and cryptographic options.

        :param cipher_algorithm: Algorithm for the encryption
        :type cipher_algorithm: str
        :param hash_algorithm: Hash algorithm used for key derivation
        :type hash_algorithm: str
        :param keysize: Key-size for the cipher algorithm
        :type keysize: int
        """
        echo('DEBUG', f'LUKS header information for {self.device_name}')
        echo('DEBUG', f'Cipher algorithm: {cipher_algorithm}')
        echo('DEBUG', f'Hash algorithm {hash_algorithm}')
        echo('DEBUG', f'Keysize: {keysize}')
        echo('DEBUG', f'Device: {self.device_name}')
        echo('DEBUG', f'Crypt device: {self.cryptdev}')
        echo('DEBUG', f'Mapper: /dev/mapper/{self.cryptdev}')
        echo('DEBUG', f'Mountpoint: {self.mountpoint}')
        echo('DEBUG', f'File system: {self.filesystem}')


    def setup_device(self, luks_header_backup_dir, luks_header_backup_file, cipher_algorithm, keysize, hash_algorithm,
                    passphrase_length, passphrase, passphrase_confirmation, use_vault, vault_url, wrapping_token, secret_path, user_key):
        """Performs the setup wrokflow to encrypt the device by performing the following steps:

        * Logs to stdout device informations and cryptographic options with the device.info method
        * Checks the specified passphrase or creates a new one of the specified length with the check_passphrase function
        * Sets up a the device in LUKS encryption mode with the device.luksFormat method
        * Stores the passphrase to HashiCorp Vault if `use_vault` is set to True with the write_secret_to_vault function.
        * Stores the header backup with the device.luksHeaderBackup method
        It either returns the passphrase if the setup is successful or False if it fails.

        :param luks_header_backup_dir: Directory for the header and keyslot area backup.
        :type luks_header_backup_dir: str
        :param luks_header_backup_file: File in which the header and keyslot area are stored.
        :type luks_header_backup_file: str
        :param cipher_algorithm: Algorithm for the encryption, e.g. aes-xts-plain64
        :type cipher_algorithm: str
        :param keysize: Key-size for the cipher algorithm, e.g. 256
        :type keysize: int
        :param hash_algorithm: Hash algorithm used for key derivaiton, e.g. sha256
        :type hash_algorithm: int
        :param passphrase_length: Lenght of the passphrase to be generated.
        :type passphrase_length: int
        :param passphrase: Specified passphrase to be used for device encryption.
        :type passphrase: str
        :param passphrase_confirmation: Passphrase confirmation, needs to be the same as 'passphrase'.
        :type passphrase_confirmation: str
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
        echo('INFO', 'Start the encryption procedure.')
        fastluks_logger.info(f'Using {cipher_algorithm} algorithm to luksformat the volume.')
        fastluks_logger.debug('Start cryptsetup')
        self.info(cipher_algorithm, hash_algorithm, keysize)
        fastluks_logger.debug('Cryptsetup full command:')
        fastluks_logger.debug(f'cryptsetup -v --cipher {cipher_algorithm} --key-size {keysize} --hash {hash_algorithm} --iter-time 2000 --use-urandom --verify-passphrase luksFormat {device} --batch-mode')

        s3cret = check_passphrase(passphrase_length, passphrase, passphrase_confirmation)
        if s3cret == False:
            return False # unlock and exit
        
        # Start encryption procedure
        self.luksFormat(s3cret, cipher_algorithm, keysize, hash_algorithm)

        # Write the secret to vault
        if use_vault:
            write_secret_to_vault(vault_url, wrapping_token, secret_path, user_key, s3cret)
            echo('INFO','Passphrase stored in Vault')

        # Backup LUKS header
        if not os.path.isdir(luks_header_backup_dir):
            os.mkdir(luks_header_backup_dir)
        _, _, luksHeaderBackup_ec = self.luksHeaderBackup(luks_header_backup_dir, luks_header_backup_file)

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
                echo('ERROR', 'Bad passphrase. Please try again.')
            return False # unlock and exit

        return s3cret


    def open_device(self, s3cret):
        """Opens and mounts the encrypted device.

        :param s3cret: Passphrase to open the encrypted device.
        :type s3cret: str
        :return: False if any error occur (e.g. if the passphrase is wrong or if the crypt device already exists) 
        :rtype: bool, optional
        """
        echo('INFO', 'Open LUKS volume')
        if not Path(f'/dev/mapper{self.cryptdev}').is_block_device():
            _, _, openec = self.luksOpen(s3cret)
            
            if openec != 0:
                if openec == 2:
                    echo('ERROR', 'Bad passphrase. Please try again.')
                    return False # unlock and exit
                else:
                    echo('ERROR', f'Crypt device already exists! Please check logs: {LOGFILE}')
                    fastluks_logger.error('Unable to luksOpen device.')
                    fastluks_logger.error(f'/dev/mapper/{self.cryptdev} already exists.')
                    fastluks_logger.error(f'Mounting {self.device_name} to {self.mountpoint} again.')
                    run_command(f'mount {self.device_name} {self.mountpoint}', logger=fastluks_logger)
                    return False # unlock and exit


    def encryption_status(self):
        """Checks cryptdevice status, with the command cryptsetup status. It logs stdout, stderr
        and status to the logfile.
        """
        fastluks_logger.info(f'Check {self.cryptdev} status with cryptsetup status')
        run_command(f'cryptsetup -v status {self.cryptdev}', logger=fastluks_logger)


    def create_cryptdev_ini_file(self, luks_cryptdev_file, cipher_algorithm, hash_algorithm, keysize, luks_header_backup_dir, luks_header_backup_file,
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
        :param luks_header_backup_dir: Directory for the header and keyslot area backup.
        :type luks_header_backup_dir: str
        :param luks_header_backup_file: File in which the header and keyslot area are stored.
        :type luks_header_backup_file: str
        :param save_passphrase_locally: If set to true, the passphrase is written in the .ini file in plain text. This option is usually used for testing purposes.
        :type save_passphrase_locally: bool
        :param s3cret: Passphrase to open the encrypted device, written in the .ini file only if `save_passphrase_locally` is set to True
        :type s3cret: str
        """
        luksUUID, _, _ = run_command(f'cryptsetup luksUUID {self.device_name}')

        with open(luks_cryptdev_file, 'w') as f:
            config = ConfigParser()
            config.add_section('luks')
            config_luks = config['luks']
            config_luks['cipher_algorithm'] = cipher_algorithm
            config_luks['hash_algorithm'] = hash_algorithm
            config_luks['keysize'] = str(keysize)
            config_luks['device'] = self.device_name
            config_luks['uuid'] = luksUUID
            config_luks['cryptdev'] = self.cryptdev
            config_luks['mapper'] = f'/dev/mapper/{self.cryptdev}'
            config_luks['mountpoint'] = self.mountpoint
            config_luks['filesystem'] = self.filesystem
            config_luks['header_path'] = f'{luks_header_backup_dir}/{luks_header_backup_file}'

            config.add_section('logs')
            config_logs = config['logs']
            for name,logfile in DEFAULT_LOGFILES.items():
                config_logs[name] = logfile

            if save_passphrase_locally:
                config_luks['passphrase'] = s3cret
                config.write(f)
                echo('INFO', f'Device informations and key have been saved in {luks_cryptdev_file}')
            else:
                config.write(f)
                echo('INFO', f'Device informations have been saved in {luks_cryptdev_file}')

        run_command(f'dmsetup info /dev/mapper/{self.cryptdev}', logger=fastluks_logger)
        run_command(f'cryptsetup luksDump {self.device_name}', logger=fastluks_logger)


    def wipe_data(self):
        """Paranoid mode function: it wipes the disk by overwriting the entire drive with random data.
        It may take some time.
        """
        echo('INFO', 'Paranoid mode selected. Wiping disk')
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
        echo('INFO', 'Creating filesystem.')
        fastluks_logger.info(f'Creating {self.filesystem} filesystem on /dev/mapper/{self.cryptdev}')
        _, _, mkfs_ec = run_command(f'mkfs -t {self.filesystem} /dev/mapper/{self.cryptdev}', logger=fastluks_logger)
        if mkfs_ec != 0:
            echo('ERROR', f'While creating {self.filesystem} filesystem. Please check logs.')
            echo('ERROR', 'Command mkfs failed!')
            return False # unlock and exit


    def mount_vol(self):
        """Mounts the encrypted device to the 'mountpoint' specified in the device attributes.
        """
        echo('INFO', 'Mounting encrypted device.')
        fastluks_logger.info(f'Mounting /dev/mapper/{self.cryptdev} to {self.mountpoint}')
        run_command(f'mount /dev/mapper/{self.cryptdev} {self.mountpoint}', logger=fastluks_logger)
        run_command('df -Hv', logger=fastluks_logger)


    def encrypt(self, cipher_algorithm, keysize, hash_algorithm, luks_header_backup_dir, luks_header_backup_file, 
               LOCKFILE, SUCCESS_FILE, luks_cryptdev_file, passphrase_length, passphrase, passphrase_confirmation,
               save_passphrase_locally, use_vault, vault_url, wrapping_token, secret_path, user_key):
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
        :param luks_header_backup_dir: Directory for the header and keyslot area backup.
        :type luks_header_backup_dir: str
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
        :param passphrase_confirmation: Passphrase confirmation, needs to be the same as passphrase.
        :type passphrase_confirmation: str
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
        
        locked = lock(LOCKFILE) # Create lock file

        cryptdev = create_random_cryptdev_name() # Assign random name to cryptdev

        check_cryptsetup() # Check that cryptsetup and dmsetup are installed

        unlock_if_false(self.check_vol(), locked, LOCKFILE, message='Volume checks not satisfied') # Check which virtual volume is mounted to mountpoint, unlock and exit if it's not mounted

        if not self.is_encrypted(): # Check if the volume is encrypted, if it's not start the encryption procedure
            self.umount_vol()
            s3cret = self.setup_device(luks_header_backup_dir, luks_header_backup_file, cipher_algorithm, keysize, hash_algorithm,
                                       passphrase_length, passphrase, passphrase_confirmation, use_vault, vault_url, wrapping_token,
                                       secret_path, user_key)
            unlock_if_false(s3cret, locked, LOCKFILE, message='Device setup procedure failed.')
        
        unlock_if_false(self.open_device(s3cret), locked, LOCKFILE, message='luksOpen failed, mapping not created.') # Create mapping

        self.encryption_status() # Check status

        self.create_cryptdev_ini_file(luks_cryptdev_file, cipher_algorithm, hash_algorithm, keysize, luks_header_backup_dir,
                                      luks_header_backup_file, save_passphrase_locally, s3cret) # Create ini file

        end_encrypt_procedure(SUCCESS_FILE) # LUKS encryption finished. Print end dialogue.

        unlock(locked, LOCKFILE, do_exit=False) # Unlock


    def volume_setup(self, LOCKFILE, SUCCESS_FILE):
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
        
        locked = lock(LOCKFILE) # Create lock file

        unlock_if_false(self.create_fs(), locked, LOCKFILE, message='Command mkfs failed.') # Create filesystem

        self.mount_vol() # Mount volume
        
        end_volume_setup_procedure(SUCCESS_FILE) # Volume setup finished. Print end dialogue

        unlock(locked, LOCKFILE, do_exit=False) # Unlock once done



################################################################################
# FASTLUKS SCRIPT FUNCTION

def encrypt_and_setup(device_name='/dev/vdb', cryptdev='crypt', mountpoint='/export',
                      filesystem='ext4', cipher_algorithm='aes-xts-plain64', keysize=256,
                      hash_algorithm='sha256', luks_header_backup_dir='/etc/luks',
                      luks_header_backup_file='luks-header.bck', luks_cryptdev_file='/etc/luks/luks-cryptdev.ini',
                      passphrase_length=8, passphrase=None, passphrase_confirmation=None,
                      save_passphrase_locally=None, use_vault=False, vault_url=None,
                      wrapping_token=None, secret_path=None, user_key=None):
    """Performs the complete workflow to encrypt the device and to setup the encrypted volume with the following steps:
    
    * Checks if the function is run as root, if not it exits.
    * Instantiate a device object.
    * Defines the default LOCKFILE and SUCCESS_FILE variables for encryption.
    * Encrypts the device with the device.encrypt method.
    * Defines the default LOCKFILE and SUCCESS_FILE variables for volume setup.
    * Sets up the volume with the device.volume_setup method.
    This function is used by the fastluks script in order to encrypt and setup a device directly from the command line.

    :param device_name: Name of the device, defaults to '/dev/vdb'
    :type device_name: str, optional
    :param cryptdev: Name of the cryptdevice, defaults to 'crypt'
    :type cryptdev: str, optional
    :param mountpoint: Mountpoint for the encrypted device, defaults to '/export'
    :type mountpoint: str, optional
    :param filesystem: Filesystem for the device, defaults to 'ext4'
    :type filesystem: str, optional
    :param cipher_algorithm: Algorithm for the encryption, defaults to 'aes-xts-plain64'
    :type cipher_algorithm: str, optional
    :param keysize: Key-size for the cipher algorithm, defaults to 256
    :type keysize: int, optional
    :param hash_algorithm: Hash algorithm used for key derivation, defaults to 'sha256'
    :type hash_algorithm: str, optional
    :param luks_header_backup_dir: Directory for the header and keyslot area backup, defaults to '/etc/luks'
    :type luks_header_backup_dir: str, optional
    :param luks_header_backup_file: File in which the header and keyslot area are stored, defaults to 'luks-header.bck'
    :type luks_header_backup_file: str, optional
    :param luks_cryptdev_file: Path to the cryptdev .ini file, defaults to '/etc/luks/luks-cryptdev.ini'
    :type luks_cryptdev_file: str, optional
    :param passphrase_length: Length of the passphrase to be generated, defaults to 8
    :type passphrase_length: int, optional
    :param passphrase: Specified passphrase to be used for device encryption, defaults to None
    :type passphrase: str, optional
    :param passphrase_confirmation: Passphrase confirmation, needs to be the same as passphrase, defaults to None
    :type passphrase_confirmation: str, optional
    :param save_passphrase_locally: If set to True, the passphrase is written in the .ini file in plain text, defaults to None
    :type save_passphrase_locally: bool, optional
    :param use_vault: If set to True, the passphrase is stored to HashiCorp Vautl, defaults to False
    :type use_vault: bool, optional
    :param vault_url: URL of Vault server, defaults to None
    :type vault_url: str, optional
    :param wrapping_token: Wrapping token used to write the passphrase on Vault, defaults to None
    :type wrapping_token: str, optional
    :param secret_path: Vault path in which the passphrase is stored, defaults to None
    :type secret_path: str, optional
    :param user_key: Vault key associated to the passphrase, defaults to None
    :type user_key: str, optional
    """
    
    if not os.geteuid() == 0:
        sys.exit('Error: Script must be run as root.')

    device_to_encrypt = device(device_name, cryptdev, mountpoint, filesystem)
    
    LOCKFILE = '/var/run/fast-luks-encryption.lock'
    SUCCESS_FILE = '/var/run/fast-luks-encryption.success'
    
    device_to_encrypt.encrypt(cipher_algorithm, keysize, hash_algorithm, luks_header_backup_dir, luks_header_backup_file, 
                              LOCKFILE, SUCCESS_FILE, luks_cryptdev_file, passphrase_length, passphrase, passphrase_confirmation,
                              save_passphrase_locally, use_vault, vault_url, wrapping_token, secret_path, user_key)

    #cryptdev_variables = read_ini_file(luks_cryptdev_file)
    #luksUUID = cryptdev_variables['uuid']
    LOCKFILE = '/var/run/fast-luks-volume-setup.lock'
    SUCCESS_FILE = '/var/run/fast-luks-volume-setup.success'

    device_to_encrypt.volume_setup(LOCKFILE, SUCCESS_FILE)
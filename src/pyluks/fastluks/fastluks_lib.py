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
    valid_loglevels = ['INFO','DEBUG','WARNING','ERROR']
    if loglevel not in valid_loglevels:
        raise ValueError(f'loglevel must be one of {valid_loglevels}')


def echo(loglevel, text):
    check_loglevel(loglevel)
    message = f'{loglevel} {time} {text}\n'
    print(message)
    return message



################################################################################
# FUNCTIONS

#____________________________________
# Lock/UnLock Section
def lock(LOCKFILE):
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
    lock.close()
    os.remove(LOCKFILE)
    if do_exit:
        sys.exit(f'UNLOCK: {message}')


def unlock_if_false(function_return, lock, LOCKFILE, message=None):
    if function_return == False:
        unlock(lock, LOCKFILE, message=message)


#____________________________________
# Volume encryption and setup functions
def create_random_cryptdev_name():
    return ''.join([random.choice(ascii_lowercase) for i in range(8)])


def info(device, cipher_algorithm, hash_algorithm, keysize, cryptdev, mountpoint, filesystem):
    echo('DEBUG', f'LUKS header information for {device}')
    echo('DEBUG', f'Cipher algorithm: {cipher_algorithm}')
    echo('DEBUG', f'Hash algorithm {hash_algorithm}')
    echo('DEBUG', f'Keysize: {keysize}')
    echo('DEBUG', f'Device: {device}')
    echo('DEBUG', f'Crypt device: {cryptdev}')
    echo('DEBUG', f'Mapper: /dev/mapper/{cryptdev}')
    echo('DEBUG', f'Mountpoint: {mountpoint}')
    echo('DEBUG', f'File system: {filesystem}')


def install_cryptsetup(logger=None):
    if DISTNAME == 'ubuntu':
        echo('INFO', 'Distribution: Ubuntu. Using apt.')
        run_command('apt-get install -y cryptsetup pv', logger)
    else:
        echo('INFO', 'Distribution: CentOS. Using yum.')
        run_command('yum install -y cryptsetup-luks pv', logger)


def check_cryptsetup():
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
    return ''.join([random.choice(alphanum) for i in range(passphrase_length)])


def end_encrypt_procedure(SUCCESS_FILE):
    # send signal to unclok waiting condition for automation software (e.g Ansible)
    with open(SUCCESS_FILE, 'w') as success_file:
        success_file.write('LUKS encryption completed.') # WARNING DO NOT MODFIFY THIS LINE, THIS IS A CONTROL STRING FOR ANSIBLE
    echo('INFO', 'SUCCESSFUL.')


def end_volume_setup_procedure(SUCCESS_FILE):
    # send signal to unclok waiting condition for automation software (e.g Ansible)
    with open(SUCCESS_FILE,'w') as success_file:
        success_file.write('Volume setup completed.') # WARNING DO NOT MODFIFY THIS LINE, THIS IS A CONTROL STRING FOR ANSIBLE
    echo('INFO', 'SUCCESSFUL.')


def read_ini_file(cryptdev_ini_file):
    config = ConfigParser()
    config.read_file(open(cryptdev_ini_file))
    luks_section = config['luks']
    return {key:luks_section[key] for key in luks_section}


def check_passphrase(passphrase_length, passphrase, passphrase_confirmation):
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


    def __init__(self, device_name, cryptdev, mountpoint, filesystem):
        self.device_name = device_name
        self.cryptdev = cryptdev
        self.mountpoint = mountpoint
        self.filesystem = filesystem


    def check_vol(self):
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
        fastluks_logger.debug('Checking if the volume is already encrypted.')
        devices, _, _ = run_command('lsblk -p -o NAME,FSTYPE')
        if re.search(f'{self.device_name}\s+crypto_LUKS', devices):
                fastluks_logger.info('The volume is already encrypted')
                return True
        else:
            return False


    def umount_vol(self):
        fastluks_logger.info('Umounting device.')
        run_command(f'umount {self.mountpoint}', logger=fastluks_logger)
        fastluks_logger.info(f'{self.device_name} umounted, ready for encryption!')


    def luksFormat(self, s3cret, cipher_algorithm, keysize, hash_algorithm):
        return run_command(f'printf "{s3cret}\n" | cryptsetup -v --cipher {cipher_algorithm} --key-size {keysize} --hash {hash_algorithm} --iter-time 2000 --use-urandom luksFormat {self.device_name} --batch-mode')


    def luksHeaderBackup(self, luks_header_backup_dir, luks_header_backup_file):
        return run_command(f'cryptsetup luksHeaderBackup --header-backup-file {luks_header_backup_dir}/{luks_header_backup_file} {self.device_name}')


    def luksOpen(self, s3cret):
        return run_command(f'printf "{s3cret}\n" | cryptsetup luksOpen {self.device_name} {self.cryptdev}')


    def setup_device(self, luks_header_backup_dir, luks_header_backup_file, cipher_algorithm, keysize, hash_algorithm,
                    passphrase_length, passphrase, passphrase_confirmation, use_vault, vault_url, wrapping_token, secret_path, user_key):
            echo('INFO', 'Start the encryption procedure.')
            fastluks_logger.info(f'Using {cipher_algorithm} algorithm to luksformat the volume.')
            fastluks_logger.debug('Start cryptsetup')
            info(self.device_name, cipher_algorithm, hash_algorithm, keysize, self.cryptdev, self.mountpoint, self.filesystem)
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
        fastluks_logger.info(f'Check {self.cryptdev} status with cryptsetup status')
        run_command(f'cryptsetup -v status {self.cryptdev}', logger=fastluks_logger)


    def create_cryptdev_ini_file(self, luks_cryptdev_file, cipher_algorithm, hash_algorithm, keysize, luks_header_backup_dir, luks_header_backup_file,
                                 save_passphrase_locally, s3cret):
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
        echo('INFO', 'Paranoid mode selected. Wiping disk')
        fastluks_logger.info('Wiping disk data by overwriting the entire drive with random data.')
        fastluks_logger.info('This might take time depending on the size & your machine!')
        
        run_command(f'dd if=/dev/zero of=/dev/mapper/{self.cryptdev} bs=1M status=progress')
        
        fastluks_logger.info(f'Block file /dev/mapper/{self.cryptdev} created.')
        fastluks_logger.info('Wiping done.')


    def create_fs(self):
        echo('INFO', 'Creating filesystem.')
        fastluks_logger.info(f'Creating {self.filesystem} filesystem on /dev/mapper/{self.cryptdev}')
        _, _, mkfs_ec = run_command(f'mkfs -t {self.filesystem} /dev/mapper/{self.cryptdev}', logger=fastluks_logger)
        if mkfs_ec != 0:
            echo('ERROR', f'While creating {self.filesystem} filesystem. Please check logs.')
            echo('ERROR', 'Command mkfs failed!')
            return False # unlock and exit


    def mount_vol(self):
        echo('INFO', 'Mounting encrypted device.')
        fastluks_logger.info(f'Mounting /dev/mapper/{self.cryptdev} to {self.mountpoint}')
        run_command(f'mount /dev/mapper/{self.cryptdev} {self.mountpoint}', logger=fastluks_logger)
        run_command('df -Hv', logger=fastluks_logger)


    def encrypt(self, cipher_algorithm, keysize, hash_algorithm, luks_header_backup_dir, luks_header_backup_file, 
               LOCKFILE, SUCCESS_FILE, luks_cryptdev_file, passphrase_length, passphrase, passphrase_confirmation,
               save_passphrase_locally, use_vault, vault_url, wrapping_token, secret_path, user_key):
        
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


    def volume_setup(self, cipher_algorithm, hash_algorithm, keysize, luksUUID, luks_header_backup_dir,
                     luks_header_backup_file, LOCKFILE, SUCCESS_FILE):
        
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
    
    if not os.geteuid() == 0:
        sys.exit('Error: Script must be run as root.')

    device_to_encrypt = device(device_name, cryptdev, mountpoint, filesystem)
    
    LOCKFILE = '/var/run/fast-luks-encryption.lock'
    SUCCESS_FILE = '/var/run/fast-luks-encryption.success'
    
    device_to_encrypt.encrypt(cipher_algorithm, keysize, hash_algorithm, luks_header_backup_dir, luks_header_backup_file, 
                              LOCKFILE, SUCCESS_FILE, luks_cryptdev_file, passphrase_length, passphrase, passphrase_confirmation,
                              save_passphrase_locally, use_vault, vault_url, wrapping_token, secret_path, user_key)

    cryptdev_variables = read_ini_file(luks_cryptdev_file)
    luksUUID = cryptdev_variables['uuid']
    LOCKFILE = '/var/run/fast-luks-volume-setup.lock'
    SUCCESS_FILE = '/var/run/fast-luks-volume-setup.success'

    device_to_encrypt.volume_setup(cipher_algorithm, hash_algorithm, keysize, luksUUID, luks_header_backup_dir,
                        luks_header_backup_file, LOCKFILE, SUCCESS_FILE)
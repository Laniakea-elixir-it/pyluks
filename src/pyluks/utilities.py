# Import dependencies
import subprocess
import os
from configparser import ConfigParser
import logging
import sys



################################################################################
# VARIABLES

DEFAULT_LOGFILES = {
    'fastluks':'/tmp/fastluks.log',
    'luksctl':'/tmp/luksctl.log',
    'luksctl_api':'/tmp/luksctl-api.log'
}



################################################################################
# FUNCTIONS

#__________________________________
# Function to run bash commands
def run_command(cmd, logger=None):
    """Run subprocess call redirecting stdout, stderr and the command exit code.

    :param cmd: Command to be executed.
    :type cmd: str
    :param logger: logging.Logger object used to log stdout, stderr and exit code, defaults to None
    :type logger: loggin.Logger, optional
    :return: Returns tuple containing stdout, stderr and exit code.
    :rtype: tuple
    """
    proc = subprocess.Popen(args=cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    communicateRes = proc.communicate()
    stdout, stderr = [x.decode('utf-8') for x in communicateRes]
    status = proc.wait()

    # Functionality to replicate cmd >> "$LOGFILE" 2>&1
    if logger != None:
        logger.debug(f'Command: {cmd}\nStdout: {stdout}\nStderr: {stderr}')
    
    return stdout, stderr, status


#__________________________________
# Create logging facility
def create_logger(luks_cryptdev_file, logger_name, loggers_section='logs'):
    """Instantiate a logging.Logger object which logs to the file specified in the cryptdev .ini file.

    :param luks_cryptdev_file: Path to the cryptdev .ini file containing the path to the log file.
    :type luks_cryptdev_file: str
    :param logger_name: Logger name assigned to the logging.Logger object.
    :type logger_name: str
    :param loggers_section: Loggers section as defined in the cryptdev .ini file, defaults to 'logs'
    :type loggers_section: str, optional
    :return: logging.Logger object.
    :rtype: loggin.Logger
    """
    # Read the logfile path from the ini file (or use the default logfile if ini file missing)
    logfile = get_logfile(luks_cryptdev_file=luks_cryptdev_file,
                          logger_name=logger_name,
                          loggers_section=loggers_section)
    
    # Create logfile if it doesn't exist
    if not os.path.exists(logfile):
        create_logfile(path=logfile)

    # Define logging format
    formatter = logging.Formatter('%(levelname)s %(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    # Define file logging handler
    file_handler = logging.FileHandler(logfile, mode='a+')  
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # Define stdout logging handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(logging.INFO)

    # Create logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(stdout_handler)

    return logger


def get_logfile(luks_cryptdev_file, logger_name, loggers_section='logs'):
    """Returns the path to the log file as defined in the cryptdev .ini file. If the log file is not defined
    in the .ini file, a default value is returned for the logger_name (possible values for logger_name
    are fastluks, luksctl and luksct_api)

    :param luks_cryptdev_file: Path to the cryptdev .ini file
    :type luks_cryptdev_file: str
    :param logger_name: Name for the logger, possible values are fastluks, luksctl and luksctl_api
    :type logger_name: str
    :param loggers_section: Loggers section as defined in the cryptdev .ini file, defaults to 'logs'
    :type loggers_section: str, optional
    :return: Path to the log file (either the default or the one specified in the cryptdev .ini file)
    :rtype: str
    """
    # Read logger file from cryptdev file
    if os.path.exists(luks_cryptdev_file):
        config = ConfigParser()
        config.read(luks_cryptdev_file)
        if loggers_section in config.sections():
            if logger_name in config[loggers_section]:
                logfile = config[loggers_section][logger_name]
                return logfile
    
    # cryptdev file or logger section/value missing, return default logger
    return DEFAULT_LOGFILES[logger_name]


def create_logfile(path):
    """Creates the log file with 666 permissions in the specified path.

    :param path: Path in which the log file is created
    :type path: str
    """
    with open(path, 'w+'):
            pass
    os.chmod(path, 0o666)

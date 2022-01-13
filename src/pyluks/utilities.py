# Import dependencies
import subprocess
import os
from configparser import ConfigParser
import logging



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
    """
    Run subprocess call redirecting stdout, stderr and the command exit code.
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

    # Read the logfile path from the ini file (or use the default logfile if ini file missing)
    logfile = get_logfile(luks_cryptdev_file=luks_cryptdev_file,
                          logger_name=logger_name,
                          loggers_section=loggers_section)
    
    # Create logfile if it doesn't exist
    if not os.path.exists(logfile):
        create_logfile(path=logfile)

    # Define logging format
    formatter = logging.Formatter('%(levelname)s %(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    # Define logging handler
    handler = logging.FileHandler(logfile, mode='a+')  
    handler.setFormatter(formatter)

    # Create logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    return logger


def get_logfile(luks_cryptdev_file, logger_name, loggers_section='logs'):

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
    
    with open(path, 'w+'):
            pass
    os.chmod(path, 0o666)

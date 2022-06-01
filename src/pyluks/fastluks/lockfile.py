# Import dependencies
import zc.lockfile
import sys
import os
import re

LOCKFILE = '/var/run/fast-luks.lock'

#____________________________________
# Lock/UnLock Section
def lock():
    """Generate lockfile in order to avoid multiple instances to encrypt at the same time.

    :return: lockfile instance.
    :rtype: zc.lockfile.LockFile
    """
    # Start locking attempt
    try:
        LOCK = zc.lockfile.LockFile(LOCKFILE, content_template='{pid};{hostname}') # storing the PID and hostname in LOCKFILE
        return LOCK
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


def unlock(LOCK, do_exit=True, message=None):
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
    LOCK.close()
    os.remove(LOCKFILE)
    if do_exit:
        sys.exit(f'UNLOCK: {message}')


# def lock_process(function):
#     """Wrapper function to use a lockfile while a function is running

#     :param function: Function to wrap
#     :type function: function
#     """
#     def wrapper_function(*args, **kwargs):
#         LOCK = lock(LOCKFILE) # lock
#         result = function(*args, **kwargs)
#         unlock(LOCK, LOCKFILE, do_exit=False) # Unlock
#         return result
#     return wrapper_function
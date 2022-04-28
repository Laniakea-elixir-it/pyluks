# Import dependencies
import json, requests
import os, sys, distro
from configparser import ConfigParser

# Import internal dependencies
from ..utilities import run_command, create_logger
from ..vault_support import read_secret
from .ssl_certificate import generate_self_signed_cert



################################################################################
# VARIABLES

__prefix__ = sys.prefix



################################################################################
# LOGGING FACILITY

LOGGER_NAME = 'luksctl_api'

# Instantiate the logger
api_logger = create_logger(luks_cryptdev_file='/etc/luks/luks-cryptdev.ini',
                           logger_name=LOGGER_NAME,
                           loggers_section='logs')



################################################################################
# FUNCTIONS

def read_api_config(luks_cryptdev_file, api_section):
    """Reads the api configurations from the cryptdev .ini file.

    :param luks_cryptdev_file: Path to the cryptdev .ini file
    :type luks_cryptdev_file: str
    :param api_section: API section as defined in the cryptdev .ini file
    :type api_section: str
    :raises FileNotFoundError: Raises an error if the cryptdev .ini file is not found.
    :return: Returns a dictionary containing key, value pairs for each API configuration option, i.e. infrastructure_configuration, virtualization_type, wn_ips, sudo_path and env_path
    :rtype: dict
    """
    
    if os.path.exists(luks_cryptdev_file):
        # Read cryptdev ini file
        config = ConfigParser()
        config.read(luks_cryptdev_file)
        api_config = config[api_section]

        # Set variables from cryptdev ini file (master node)
        infrastructure_config = api_config['infrastructure_configuration'] if 'infrastructure_configuration' in api_config else None
        virtualization_type = api_config['virtualization_type'] if 'virtualization_type' in api_config else None
        node_list = json.loads(api_config['wn_ips']) if 'wn_ips' in api_config else None
        sudo_path = api_config['sudo_path'] if 'sudo_path' in api_config else None
        env_path = api_config['env_path'] if 'env_path' in api_config else None

        # Set variables from cryptdev ini file (worker node)
        nfs_mountpoint_list = json.loads(api_config['nfs_mountpoint_list']) if 'nfs_mountpoint_list' in api_config else None

        # Define variables dictionary
        config_dict = {
            'infrastructure_config':infrastructure_config,
            'virtualization_type':virtualization_type,
            'node_list':node_list,
            'sudo_path':sudo_path,
            'env_path':env_path,
            'nfs_mountpoint_list':nfs_mountpoint_list
            }

    else:
        raise FileNotFoundError('Cryptdev ini file missing.')

    return config_dict


def write_systemd_unit_file(working_directory, environment_prefix, user, group, app,
                            service_file='/etc/systemd/system/luksctl-api.service',
                            gunicorn_config_file='/etc/luks/gunicorn.conf.py'):
    """General function to write the unit file used by systemd that defines the luksctl-api service.
    It's used by both master and wn classes to configure the master and wn API respectively.

    :param working_directory: Path to the luksctl_api subpackage
    :type working_directory: str
    :param environment_prefix: Path to the virtual environment in which pyluks is installed.
    :type environment_prefix: str
    :param user: User under which the luksctl-api service is run.
    :type user: str
    :param group: User group under which the luksctl-api service is run.
    :type group: str
    :param app: Flask app name as defined in the app.py module of luksctl_api, possible values are master_app or wn_app.
    :type app: str
    :param service_file: Path to the unit file, defaults to '/etc/systemd/system/luksctl-api.service'
    :type service_file: str, optional
    :param gunicorn_config_file: Path where the gunicorn.conf file is copyed, defaults to '/etc/luks/gunicorn.conf.py'
    :type gunicorn_config_file: str, optional
    """
    
    # Exit if command is not run as root
    if not os.geteuid() == 0:
        sys.exit('Error: write_systemd_unit_file must be run as root.')
    
    config = ConfigParser()
    config.optionxform = str
    
    config.add_section('Unit')
    config['Unit']['Description'] = 'Gunicorn instance to serve luksctl api server'
    config['Unit']['After'] = 'network.target'

    config.add_section('Service')
    config['Service']['User'] = user
    config['Service']['Group'] = group
    config['Service']['WorkingDirectory'] = working_directory
    config['Service']['Environment'] = f'"PATH={environment_prefix}/bin"'
    
    config['Service']['ExecStart'] = f'{environment_prefix}/bin/gunicorn --config {gunicorn_config_file} app:{app}'
    
    config.add_section('Install')
    config['Install']['WantedBy'] = 'multi-user.target'

    with open(service_file, 'w') as sf:
        config.write(sf)



################################################################################
# NODES CLASSES

class master:
    """Master node class, used to manage the luksctl API on a single virtual machine or on the master node of a cluster.
    """


    def __init__(self, infrastructure_config=None, virtualization_type=None, node_list=None, sudo_path='/usr/bin', env_path=None,
                 luks_cryptdev_file=None, api_section='luksctl_api'):
        """Instantiates the master class. If luks_cryptdev_file (and eventually also api_section) is defined, other arguments will be ignored and
        the object's attributes are read from the cryptdev .ini file.

        :param infrastructure_config: Infrastructure configuration, possible values are 'single_vm' or 'cluster', defaults to None
        :type infrastructure_config: str, optional
        :param virtualization_type: Virtualization type, either None or 'docker', defaults to None
        :type virtualization_type: str, optional
        :param node_list: List of nodes IPs in the cluster, defaults to None
        :type node_list: list, optional
        :param sudo_path: Path to the sudo command, defaults to '/usr/bin'
        :type sudo_path: str, optional
        :param env_path: Path to the virtual environment in which pyluks is installed, defaults to None
        :type env_path: str, optional
        :param luks_cryptdev_file: Path to the cryptdev .ini file, defaults to None
        :type luks_cryptdev_file: str, optional
        :param api_section: API section as defined in the cryptdev .ini file, defaults to 'luksctl_api'
        :type api_section: str, optional
        """
        if luks_cryptdev_file is not None:
            api_configs = read_api_config(luks_cryptdev_file=luks_cryptdev_file, api_section=api_section)
            self.infrastructure_config = api_configs['infrastructure_config']
            self.virtualization_type = api_configs['virtualization_type']
            self.node_list = api_configs['node_list']
            self.sudo_path = api_configs['sudo_path']
            self.env_path = api_configs['env_path']

        else:
            self.infrastructure_config = infrastructure_config
            self.virtualization_type = virtualization_type
            self.node_list = node_list
            self.sudo_path = sudo_path
            self.env_path = __prefix__ if env_path == None else env_path
        
        self.sudo_cmd = f'{self.sudo_path}/sudo'
        self.luksctl_cmd = f'{self.env_path}/bin/luksctl'
        self.distro_id = distro.id()
        self.app_name = 'master_app'


    def get_infrastructure_config(self): return self.infrastructure_config
    def get_virtualization_type(self): return self.virtualization_type
    def get_node_list(self): return self.node_list
    def get_sudo_path(self): return self.sudo_path
    def get_env_path(self): return self.env_path


    def write_api_config(self, luks_cryptdev_file='/etc/luks/luks-cryptdev.ini'):
        """Writes the API configuration to the cryptdev .ini file in the luksctl_api section.

        :param luks_cryptdev_file: Path to the cryptdev .ini file, defaults to '/etc/luks/luks-cryptdev.ini'
        :type luks_cryptdev_file: str, optional
        """

        config = ConfigParser()
        config.read(luks_cryptdev_file)
        # Remove luksctl_api section if written previously
        if 'luksctl_api' in config.sections():
            config.remove_section('luksctl_api')

        config.add_section('luksctl_api')
        api_config = config['luksctl_api']

        api_config['infrastructure_configuration'] = self.infrastructure_config

        if self.virtualization_type != None:
            api_config['virtualization_type'] = self.virtualization_type

        if self.node_list != None:
            api_config['wn_ips'] = json.dumps(self.node_list)

        api_config['sudo_path'] = self.sudo_path
        api_config['env_path'] = self.env_path

        with open(luks_cryptdev_file, 'w') as f:
            config.write(f)


    def write_systemd_unit_file(self, working_directory, environment_prefix, user, group):
        """Writes the unit file used by systemd that defines the luksctl-api service. It wraps the general
        write_systemd_unit_file function.

        :param working_directory: Path to the luksctl_api subpackage
        :type working_directory: str
        :param environment_prefix: Path to the virtual environment in which pyluks is installed.
        :type environment_prefix: str
        :param user: User under which the luksctl-api service is run.
        :type user: str
        :param group: User group under which the luksctl-api service is run.
        :type group: str
        """
        
        write_systemd_unit_file(working_directory=working_directory,
                                environment_prefix=environment_prefix,
                                user=user,
                                group=group,
                                app=self.app_name)


    def write_exports_file(self, nfs_export_list=['/export']):
       
       with open('/etc/exports','a+') as exports_file:
           for export_dir in nfs_export_list:
               for node in self.node_list:
                   exports_file.write(f'{export_dir} {node}:(rw,sync,no_root_squash)')


    def get_status(self):
        """Gets cryptdevice status with the 'luksctl status' command and returns a json with the following structure:
        
        * {'volume_state' : 'mounted'} if the volume is mounted.
        * {'volume_state': 'unmounted'} if the volume is unmounted.
        * {'volume_state' : 'unavailable', 'output' : stdout, 'stderr' : stderr} if the luksctl status command returns a non-recognized exit code.

        :return: String containing the json-formatted message for the volume_state
        :rtype: str
        """

        status_command = f'{self.sudo_cmd} {self.luksctl_cmd} status'
        stdout, stderr, status = run_command(status_command)

        api_logger.debug(f'Volume status stdout: {stdout}')
        api_logger.debug(f'Volume status stderr: {stderr}')
        api_logger.debug(f'Volume status: {status}')

        if str(status) == '0':
            return json.dumps({'volume_state': 'mounted' })
        elif str(status)  == '1':
            return json.dumps({'volume_state': 'unmounted' })
        else:
            return json.dumps({'volume_state': 'unavailable', 'output': stdout, 'stderr': stderr })


    def open(self, vault_url, wrapping_token, secret_root, secret_path, secret_key):
        """Reads the passphrase from HashiCorp Vault, opens and mount the cryptdevice. If the master node is
        in a cluster, it restarts the nfs using the master.nfs_restart method.
        It returns a json-formatted string containing information about the cryptdevice status, refer to the
        master.get_status method for its content.

        :param vault_url: URL to Vault server
        :type vault_url: str
        :param wrapping_token: Wrapping token used to write the passphrase to Vault
        :type wrapping_token: str
        :param secret_root: Vault root in which secrets are stored, e.g. 'secrets'
        :type secret_root: str
        :param secret_path: Vault path in which the passphrase is stored.
        :type secret_path: str
        :param secret_key: Vault key associated to the passphrase.
        :type user_key: str
        :return: String containing the json-formatted message for the volume_state
        :rtype: str
        """
        
        status_command = f'{self.sudo_cmd} {self.luksctl_cmd} status'
        stdout, stderr, status = run_command(status_command)

        if str(status) == '0':
            return json.dumps({'volume_state': 'mounted'})
        
        else:
            # Read passphrase from vault
            secret = read_secret(vault_url=vault_url,
                                 wrapping_token=wrapping_token,
                                 secret_root=secret_root,
                                 secret_path=secret_path,
                                 secret_key=secret_key)
            
            # Open volume
            open_command = f'printf "{secret}\n" | {self.sudo_cmd} {self.luksctl_cmd} open' 
            stdout, stderr, status = run_command(open_command)

            api_logger.debug(f'Volume status stdout: {stdout}')
            api_logger.debug(f'Volume status stderr: {stderr}')
            api_logger.debug(f'Volume status: {status}')

            if str(status) == '0':
                if self.infrastructure_config == 'cluster':
                    self.nfs_restart()
                return json.dumps({'volume_state': 'mounted' })

            elif str(status)  == '1':
                return json.dumps({'volume_state': 'unmounted' })

            else:
                return json.dumps({'volume_state': 'unavailable', 'output': stdout, 'stderr': stderr})

    def nfs_restart(self):
        """Restarts the nfs service and calls the master.mount_nfs_on_wns method.
        """

        api_logger.debug(f'Restarting NFS on: {self.distro_id}')
        
        if self.distro_id == 'centos':
            restart_command = f'{self.sudo_cmd} systemctl restart nfs-server'
        elif self.distro_id == 'ubuntu':
            restart_command = f'{self.sudo_cmd} systemctl restart nfs-kernel-server'
        else:
            restart_command = ''
        
        api_logger.debug(restart_command)

        stdout, stderr, status = run_command(restart_command)

        api_logger.debug(f'NFS status: {status}')
        api_logger.debug(f'NFS status stdout: {stdout}')
        api_logger.debug(f'NFS status stderr: {stderr}')
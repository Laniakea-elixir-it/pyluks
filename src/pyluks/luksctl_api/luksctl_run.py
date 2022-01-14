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

def read_api_config(luks_cryptdev_file='/etc/luks/luks-cryptdev.ini', api_section='luksctl_api'):
    
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


    def __init__(self, infrastructure_config, virtualization_type=None, node_list=None, sudo_path='/usr/bin', env_path=None):

        self.infrastructure_config = infrastructure_config
        self.virtualization_type = virtualization_type
        self.node_list = node_list
        self.sudo_path = sudo_path
        self.sudo_cmd = f'{self.sudo_path}/sudo'
        self.env_path = __prefix__ if env_path == None else env_path
        self.luksctl_cmd = f'{self.env_path}/bin/luksctl'
        self.distro_id = distro.id()
        self.app_name = 'master_app'


    def get_infrastructure_config(self): return self.infrastructure_config
    def get_virtualization_type(self): return self.virtualization_type
    def get_node_list(self): return self.node_list
    def get_sudo_path(self): return self.sudo_path
    def get_env_path(self): return self.env_path


    def write_api_config(self, luks_cryptdev_file='/etc/luks/luks-cryptdev.ini'):

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
        
        write_systemd_unit_file(working_directory=working_directory,
                                environment_prefix=environment_prefix,
                                user=user,
                                group=group,
                                app=self.app_name)


    #def write_exports_file(self, nfs_export_list=['/export']):
    #   
    #   with open('/etc/exports','a+') as exports_file:
    #       for export_dir in nfs_export_list:
    #           for node in self.node_list:
    #               exports_file.write(f'{export_dir} {node}:(rw,sync,no_root_squash)')


    def get_status(self):

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
                elif self.virtualization_type == 'docker':
                    self.docker_restart
                return json.dumps({'volume_state': 'mounted' })

            elif str(status)  == '1':
                return json.dumps({'volume_state': 'unmounted' })

            else:
                return json.dumps({'volume_state': 'unavailable', 'output': stdout, 'stderr': stderr})


    def nfs_restart(self):

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

        if str(status) == '0':
            self.mount_nfs_on_wns()


    def mount_nfs_on_wns(self):

        for node in self.node_list:
            url = f'http://{node}:5000/luksctl_api_wn/v1.0/nfs-mount'
            response = requests.post(url, verify=False)
            response.raise_for_status()
            deserialized_response = json.loads(response.text)
            api_logger.debug(f'{node} NFS: {deserialized_response["nfs_state"]}')


    def docker_restart(self):

        restart_command = f'{self.sudo_cmd} systemctl restart docker'

        stdout, stderr, status = run_command(restart_command)

        api_logger.debug(f'Docker service status: {status}')
        api_logger.debug(f'Docker service stdout: {stdout}')
        api_logger.debug(f'Docker service stderr: {stderr}')



class wn:


    def __init__(self, nfs_mountpoint_list, sudo_path='/usr/bin'):

        self.nfs_mountpoint_list = nfs_mountpoint_list
        self.sudo_path = sudo_path
        self.mount_cmd = f'{self.sudo_path}/mount'
        self.app_name = 'wn_app'

    
    def write_api_config(self, luks_cryptdev_file='/etc/luks/luks-cryptdev.ini'):

        luks_dir = os.path.dirname(luks_cryptdev_file)
        if not os.path.exists(luks_dir):
            os.mkdir(luks_dir)

        config = ConfigParser()
        config.read(luks_cryptdev_file)
        # Remove luksctl_api section if written previously
        if 'luksctl_api' in config.sections():
            config.remove_section('luksctl_api')

        config.add_section('luksctl_api')
        api_config = config['luksctl_api']

        api_config['nfs_mountpoint_list'] = json.dumps(self.nfs_mountpoint_list)
        api_config['sudo_path'] = self.sudo_path

        with open(luks_cryptdev_file, 'w') as f:
            config.write(f)


    def write_systemd_unit_file(self, working_directory, environment_prefix, user, group):
        
        write_systemd_unit_file(working_directory=working_directory,
                                environment_prefix=environment_prefix,
                                user=user,
                                group=group,
                                app=self.app_name)


    def check_status(self):

        for mountpoint in self.nfs_mountpoint_list:
            api_logger.debug(f'{mountpoint}: {os.path.ismount(mountpoint)}')
            if not os.path.ismount(mountpoint):
                return False
        
        return True


    def get_status(self):

        api_logger.debug(self.nfs_mountpoint_list)
        if self.check_status():
            return json.dumps({'nfs_state':'mounted'})
        else:
            return json.dumps({'nfs_state':'unmounted'})


    def nfs_mount(self):

        #sudo = which('sudo')
        #mount = which('mount')

        if self.check_status():
            return json.dumps({'nfs_state':'mounted'})
        
        for mountpoint in self.nfs_mountpoint_list:
            #mount_command = f'{sudo} mount -a -t nfs'
            mount_command = f'{self.mount_cmd} {mountpoint}'
            api_logger.debug(mount_command)
            stdout, stderr, status = run_command(mount_command)

            api_logger.debug(f'NFS mount subprocess call status: {status}')
            api_logger.debug(f'NFS mount subprocess call stdout: {stdout}')
            api_logger.debug(f'NFS mount subprocess call stderr: {stderr}')

        return self.get_status()

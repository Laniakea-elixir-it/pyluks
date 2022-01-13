# Import dependencies
from flask import Flask, request, abort
import json
import os
import logging
from configparser import ConfigParser

# Import internal dependencies
from .luksctl_run import read_api_config, master, api_logger



################################################################################
# APP CONFIGS

app = Flask(__name__)

api_configs = read_api_config()
infrastructure_config = api_configs['infrastructure_config']
virtualization_type = api_configs['virtualization_type']
node_list = api_configs['node_list']
sudo_path = api_configs['sudo_path']
env_path = api_configs['env_path']

# Define master node instance
master_node = master(infrastructure_config=infrastructure_config,
                     virtualization_type=virtualization_type,
                     node_list=node_list,
                     sudo_path=sudo_path,
                     env_path=env_path)



################################################################################
# FUNCTIONS

#______________________________________
@app.route('/luksctl_api/v1.0/status', methods=['GET'])
def get_status():
    
    return master_node.get_status()


#______________________________________
@app.route('/luksctl_api/v1.0/open', methods=['POST'])
def luksopen():

    if not request.json or \
       not 'vault_url' in request.json or \
       not 'vault_token' in request.json or \
       not 'secret_root' in request.json or \
       not 'secret_path' in request.json or \
       not 'secret_key' in request.json:
       abort(400)

    wn_list = master_node.get_node_list() 
    if wn_list != None:
        api_logger.debug(wn_list)

    return master_node.open(vault_url=request.json['vault_url'],
                            wrapping_token=request.json['vault_token'],
                            secret_root=request.json['secret_root'],
                            secret_path=request.json['secret_path'],
                            secret_key=request.json['secret_key'])

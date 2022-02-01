# Import dependencies
from flask import Flask
import json
import os
import logging
from configparser import ConfigParser

# Import internal dependencies
from .luksctl_run import read_api_config, wn



################################################################################
# APP CONFIGS

app = Flask(__name__)

api_configs = read_api_config()
nfs_mountpoint_list = api_configs['nfs_mountpoint_list']
sudo_path = api_configs['sudo_path']

# Define node instance
wn_node = wn(nfs_mountpoint_list=nfs_mountpoint_list,
             sudo_path=sudo_path)

@app.route('/luksctl_api_wn/v1.0/status', methods=['GET'])
def get_status():
    """Runs the wn.get_status method on a GET request.

    :return: Output from the wn.get_status method.
    :rtype: str
    """
    return wn_node.get_status()


@app.route('/luksctl_api_wn/v1.0/nfs-mount', methods=['POST'])
def nfs_mount():
    """Runs the wn.nfs_mount method on a POST request.

    :return: Output from the wn.nfs_mount method.
    :rtype: str
    """
    return wn_node.nfs_mount()

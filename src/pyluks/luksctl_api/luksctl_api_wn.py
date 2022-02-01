# Import dependencies
from flask import Flask
import json
import os
import logging
from configparser import ConfigParser

# Import internal dependencies
from .luksctl_run import wn



################################################################################
# APP CONFIGS

app = Flask(__name__)

def instantiate_worker_node():
    """Instantiate the worker_node object needed by the API functions.

    :return: A wn object which attributes are retrieved from the cryptdev .ini file.
    :rtype: pyluks.luksctl_api.luksctl_run.wn
    """
    worker_node = wn(luks_cryptdev_file='/etc/luks/luks-cryptdev.ini', api_section='luksctl_api')
    return worker_node



################################################################################
# FUNCTIONS

@app.route('/luksctl_api_wn/v1.0/status', methods=['GET'])
def get_status():
    """Runs the wn.get_status method on a GET request.

    :return: Output from the wn.get_status method.
    :rtype: str
    """

    worker_node = instantiate_worker_node()

    return worker_node.get_status()


@app.route('/luksctl_api_wn/v1.0/nfs-mount', methods=['POST'])
def nfs_mount():
    """Runs the wn.nfs_mount method on a POST request.

    :return: Output from the wn.nfs_mount method.
    :rtype: str
    """

    worker_node = instantiate_worker_node()

    return worker_node.nfs_mount()

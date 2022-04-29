# Import dependencies
from flask import Flask, request, abort, jsonify
import json
import os
import logging
from configparser import ConfigParser

# Import internal dependencies
from .luksctl_run import master, api_logger



################################################################################
# APP CONFIGS

app = Flask(__name__)

def instantiate_master_node():
    """Instantiate the master_node object needed by the API functions.

    :return: A master object which attributes are retrieved from the cryptdev .ini file.
    :rtype: pyluks.luksctl_api.luksctl_run.master
    """
    master_node = master(luks_cryptdev_file='/etc/luks/luks-cryptdev.ini', api_section='luksctl_api')
    return master_node



################################################################################
# FUNCTIONS

@app.route('/luksctl_api/v1.0/status', methods=['GET'])
def get_status():
    """Runs the master.get_status method on a GET request.

    :return: Output from the master.get_status method.
    :rtype: str
    """

    master_node = instantiate_master_node()
    
    response = master_node.get_status()

    return jsonify(response)


@app.route('/luksctl_api/v1.0/open', methods=['POST'])
def luksopen():
    """Runs the master.open method on a POST request containing the HashiCorp Vault informations to retrieve
    the passphrase.

    :return: Output from the master.open method.
    :rtype: str
    """

    master_node = instantiate_master_node()

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

    response = master_node.open(vault_url=request.json['vault_url'],
                                wrapping_token=request.json['vault_token'],
                                secret_root=request.json['secret_root'],
                                secret_path=request.json['secret_path'],
                                secret_key=request.json['secret_key'])
    
    return jsonify(response)

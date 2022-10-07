.. _luksctl_api:

===========
LUKSCtl API
===========
:ref:`luksctl_bin` functionalities can be exploited through a set of RESTFul APIs written using Python Flask micro
framework. The API code is in the `luksctl_api` subpackage of pyluks. The luskctl API is used to check the status
of an encrypted volume and unlock it without directly accessing the virtual machine through SSH.

The API is run through Gunicorn, and it can be managed through a systemd unit file. It is usually configured to
listen on port `5000` and can receive two commands: `status` and `open`.

-------------
Volume status
-------------
A GET request is sent at `/luksctl_api/v1.0/status` to check the status of the encrypted volume.
If the volume is open and mounted the API returns `mounted`, othrewise it returns `umounted`. If the API is
not available or it fails at retrieving the volume information, an `unavailable` status is shown including the
stdout and stderr of the `luksctl status` command.

Example request:

.. code-block:: console

    $ curl -k -i -X GET 'https://<vm_ip_address>:5000/luksctl_api/v1.0/status'
    HTTP/1.1 200 OK
    Server: gunicorn/19.9.0
    Date: Sun, 27 Oct 2019 08:02:54 GMT
    Connection: close
    Content-Type: application/json
    Content-Length: 27

    {"volume_state":"mounted"}

-----------
Volume open
-----------
A POST request can be sent at `/luksctl_api/v1.0/open` to open and mount the encrypted volume in case of VM reboot.
The post request should contain the Vault parameters to retrieve the encryption passphrase. First, the API checks
if the volume is already mounted. If yes it return `mounted`, otherwise it run `luksctl open` command. If the open
procedure is successful, the API returns `mounted`, otherwise `unmounted`. If the API is unavailable or other
errors occur, the `unavailable` status is shown. Additionally, the API can be configured to properly restart
some systemd services that may interfere with the volume opening process. These services can be specified in
the API configuration (see below).

Example request:

.. code-block:: console
    
    $ curl -k -X POST 'https://<vm_ip_address>:5000/luksctl_api/v1.0/open' \
     -H 'Content-Type: application/json' \
     -d '{ "vault_url": <vault_url>, "vault_token": <wrapping_read_token>, "secret_root": <vault_root>, "secret_path": <secret_path>, "secret_key": <user_key> }'

-----------------
API configuration
-----------------
To run the API, a user with proper permissions needs to be created. In Laniakea, the `luksctl_api` user is created
to run the API Gunicorn process and is given the permission to run the luksctl command as a super user.
Once the user is created, the `luksct_api` script installed with pyluks can be used to configure the API.
The script creates a self signed certificate to run the API through HTTPS and writes a systemd unit file to
properly handle the API Gunicorn process. The API parameters are then stored in the cryptdev.ini file,
in the `luksctl_api` section:

.. code-block:: ini

    [luksctl_api]
    env_path = /opt/pyluks
    daemons = nfs-server,docker
    sudo_path = /usr/bin/sudo

The parameters are:

* `env_path`: the python virtual environment path where the pyluks package is installed.
* `daemons`: a comma-separated list of systemd services that have to be stopped and started before and after
  the volume open respectively.
* `sudo_path`: path to the sudo command.

They can be changed in the config file to change the behaviour of the API.

.. note::

    In the previous version of the luksctl API, the configuration was specified in a JSON file. This file contained
    the INFRASTRUCTURE_CONFIGURATION parameter, which was used to specify if the API was installed in a single VM
    or in the master node of a cluster. With the daemons option, if the API is installed in the master node,
    it's sufficient to specify the NFS service, since AutoFS is used to automatically mount the shared volume in
    the worker nodes. In the same way, the VIRTUALIZATION_TYPE parameter, previously used to restart docker,
    is now replaced by indicating the Docker service in the daemons option.

For example, to configure the API on a single virtual machine using a self signed certificate, run:

.. code-block:: console

    $ luksctl_api --ssl --user luksctl_api

To configure the API on the master node of a cluster (nfs is used to share the encrypted volume data) using a self signed certificate:

.. code-block:: console

    $ luksctl_api --daemons nfs-server --ssl

To configure the API on a single virtual machine with docker saving container images in the encrypted storage:

.. code-block:: console
    
    $ luksctl_api --daemons docker --ssl
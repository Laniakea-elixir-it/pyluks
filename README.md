# pyluks
pyluks is a python package for storage encryption through LUKS, wrapping the functionalities provided by the cryptsetup command line tool.

The pyluks package is structured in three subpackages:
* **fastluks** contains the `device` class which can be used to encrypt, access and manage storage devices. fastluks is based on the bash script [fast-luks](https://github.com/Laniakea-elixir-it/fast-luks).
* **luksctl** can be used to manage encrypted devices. It is based on the python package [luksctl](https://github.com/Laniakea-elixir-it/luksctl).
* **luksctl_api** is an API to check the status of encrypted volumes and open them if needed. It is based on the python package [luksctl_api](https://github.com/Laniakea-elixir-it/luksctl_api).


## Installation
Currently, Ubuntu and CentOS are supported.

To setup a virtual environment and install pyluks on CentOS run:
```bash
yum install -y python3
python3 -m venv venv
. venv/bin/activate
pip install --upgrade pip
pip install pyluks
```
To do the same on Ubuntu:
```bash
apt-get update
apt-get install -y python3 python3-pip python3-venv
python3 -m venv venv
. venv/bin/activate
pip install --upgrade pip
pip install pyluks
```

# Usage
Each subpackage functionalities can be accessed thorugh a command line tool.

## fastluks
To perform encryption and volume setup with default parameters, the `fastluks` command can be used inside the virtual environment:
```bash
fastluks --device /dev/vdb
```
The encryption passphrase can be stored locally and/or on Hashicorp Vault.
- To store the passphrase locally (this is usually done for testing purposes):
```bash
fastluks --device /dev/vdb --save-passphrase-locally
```
- To store the passphrase on Vault, the flag `--vault` must be used with the required arguments specified:
<pre>
fastluks --device /dev/vdb --vault --vault-url <i>url</i> --wrapping-token <i>token</i> --secret-path <i>path</i> --user-key <i>key</i>
</pre>


## luksctl
In order to manage a volume encrypted with fastluks, the command `luksctl` can be used from the command line:
```bash
# Display volume status
luksctl status

# Open encrypted volume
luksctl open

# Close encrypted volume
luksctl close
```


## luksctl_api
In order to setup the API, the command `luksctl_api` can be used indicating the type of computing node on which the API is installed and its options, for example:
```bash
# Install the API on a single virtual machine, using a self signed certificate
luksctl_api --ssl --user luksctl_api
```
```bash
# Install the API on the master node of a cluster (nfs is used to share the encrypted volume data) using a self signed certificate
luksctl_api --daemons nfs-server --ssl 
```

By default, the API service is run by the user `luksctl_api`, which should have the permission to run the `luksctl` command. Also, the user should have the permissions to run `systemctl start` and `systemctl stop` for the daemons specified. To run the API under a different user specify the `--user` argument.

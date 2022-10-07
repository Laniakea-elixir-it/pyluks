.. _developers_documentation:

========================
Test the pyluks package
========================
Pyluks can be tested through some Terraform and Ansible recipe to make sure that everything is working before
publishing a new package version.

Some requirements are needed:

* Terraform and Ansible installed.
* An unsealed and `properly configured Vault instance <https://laniakea.readthedocs.io/en/latest/admin_documentation/vault/vault_config.html>`_.
* Clone the repository `terraform-pyluks-test <https://github.com/Laniakea-elixir-it/terraform-pyluks-test>`_:

.. code-block:: console

    $ git clone https://github.com/Laniakea-elixir-it/terraform-pyluks-test.git
    $ cd terraform-pyluks-test

----------------------------------------
Terraform: create master and worker node
----------------------------------------
First, deploy two virtual machines for a cluster:
* A master node, where pyluks is installed to encrypt the external volume and to set up the luksctl API.
* A worker node, that is used to mount the shared filesystem of the master node through NFS.

The VM specifications can be modified through the `variables.tf` file.

Source the openstack rc file, then run terraform to create the infrastructure:

.. code-block:: console
    $ terraform init
    $ terraform apply

When terraform is done creating the VMs, it will return their IP addresses. Save these in some environment
variables (this will be needed when running some Ansible playbooks):

.. code-block:: console
    $ export MASTER_IP=$(terraform output -raw master)
    $ export WORKER_IP=$(terraform output -raw worker)

--------------------------------
Ansible: encrypt external volume
--------------------------------
When terraform is done creating the VMs, it will return their IP addresses. Use the IPs to fill the inventory
file in the `plays/inventory` directory to run the Ansible playbooks.

To test the encryption, the automatically generated passphrase has to be loaded in Vault through a wrapping token.
To encrypt the storage, fill the required variables in the `pyluks_dev_test.yml` playbook related to Vault.
The pyluks version stored in a GitHub branch or the latest in PyPI can be tested:

* To test a GitHub branch (e.g. `dev`), set the variable `pyluks_package_name: 'https://github.com/Laniakea-elixir-it/pyluks/archive/dev.zip'`
* To test the latest version in `PyPI <https://pypi.org/project/pyluks>`_ set the variable  `pyluks_package_name: "pyluks"` in the playbook.

Then, run the playbook:

.. code-block:: console
    $ cd plays
    $ ansible-playbook -i inventory/hosts pyluks_dev_test.yml


If the play runs without any error, the encryption through pyluks has been successful.

---------------------------------
Ansible: configure NFS and Docker
---------------------------------
To fully test the luksctl API functioning, some services that could potentially interfere with the unlock of the
volume should be installed. In `Laniakea <https://laniakea.readthedocs.io/>`, NFS is used in virtual clusters to
share some data from the master node external volume to the worker node(s). Also, Docker is usually configured
to store container images in the external volume to ensure the OS storage is not filled completely.
Services of these type are properly restarted by the luksctl API during the volume unlocking.

A playbook can be run to configure each of the two in the master and/or worker node.

To configure NFS to share the external volume mountpoint of the master node with the worker node,  run the playbook:

.. code-block:: console

    $ ansible-playbook -i inventory/hosts -e nfs_server_ip=${MASTER_IP} -e nfs_client_ip=${WORKER_IP} nfs_playbook.yml


Then, to configure Docker on the master node to store the container images in the external volume, run the playbook:

.. code-block:: console
    $ ansible-playbook -i inventory/hosts docker_playbook.yml


----------------
luksctl API test
----------------
Finally, to test the API, access the master node with SSH to run some commands (unfortunately, no Ansible play
for now). First, you can verify that everything is properly configured:

.. code-block:: console

    $ lsblk
    NAME    MAJ:MIN RM  SIZE RO TYPE  MOUNTPOINT
    vda     252:0    0   10G  0 disk
    ├─vda1  252:1    0  9.9G  0 part  /
    ├─vda14 252:14   0    4M  0 part
    └─vda15 252:15   0  106M  0 part  /boot/efi
    vdb     252:16   0    1G  0 disk
    └─crypt 253:0    0 1022M  0 crypt /export
    $ sudo su
    # source /opt/pyluks/bin/activate
    (pyluks)# luksctl status
    Name:              crypt
    State:             ACTIVE
    Read Ahead:        256
    Tables present:    LIVE
    Open count:        1
    Event number:      0
    Major, minor:      253, 0
    Number of targets: 1
    UUID: CRYPT-LUKS1-5cc3d50d24b141bf8992111e37f99666-crypt
    Encrypted volume: [ OK ]



To close the volume, stop Docker and NFS services:

.. code-block:: console

    (pyluks)# systemctl stop docker nfs-server
    (pyluks)# luskctl close
    Encrypted volume umount: [ OK ]


Now, create another Vault wrapping token and test the luksctl API open command:

.. code-block:: console
    
    (pyluks)# curl -k -i -X GET 'https://127.0.0.1:5000/luksctl_api/v1.0/status'
    HTTP/1.1 200 OK
    Server: gunicorn
    Date: Fri, 07 Oct 2022 15:54:57 GMT
    Connection: close
    Content-Type: application/json
    Content-Length: 29

    {"volume_state":"unmounted"}
    
    (pyluks)# curl -k -X POST 'https://127.0.0.1:5000/luksctl_api/v1.0/open' -H 'Content-Type: application/json' -d '{ "vault_url": vault_instance, "vault_token": vault_token, "secret_root": secret_root, "secret_path": secret_path, "secret_key": secret_key}'
    {"volume_state":"mounted"}

    (pyluks)# luksctl status
    Name:              crypt
    State:             ACTIVE
    Read Ahead:        256
    Tables present:    LIVE
    Open count:        1
    Event number:      0
    Major, minor:      253, 0
    Number of targets: 1
    UUID: CRYPT-LUKS1-5cc3d50d24b141bf8992111e37f99666-crypt

    Encrypted volume: [ OK ]

    (pyluks)# systemctl status docker nfs-server # both services should be active

```

If you now log into the worker node, you should see in the /export directory the files shared from the master node
encrypted volume.

If everything has worked as described here, every component of pyluks have been successfully tested and
everything should be working fine.
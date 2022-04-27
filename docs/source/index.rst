.. pyluks documentation master file, created by
   sphinx-quickstart on Tue Mar 15 15:23:59 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

pyluks documentation
=====================

.. image:: https://img.shields.io/pypi/v/pyluks.svg
   :target: https://pypi.org/project/pyluks/
   :alt: latest version available on PyPI


pyluks is a package for storage encryption thorugh LUKS, the standard for Linux hard disk encryption. It wraps the functionalities of `cryptsetup <https://gitlab.com/cryptsetup/cryptsetup>`_, a command line tool to interface with `dm-crypt <https://wiki.archlinux.org/title/dm-crypt>`_ for creating, accessing and managing encrypted devices.

pyluks is composed of three subpackages, each one based on bash and python scripts used to encrypt and manage volumes for `Laniakea <https://laniakea-elixir-it.github.io/>`_:

* fastluks can be used to encrypt, access and manage storage devices thorugh the ``device`` class methods. It's derived from the bash script `fast_luks <https://github.com/Laniakea-elixir-it/fast-luks>`_;
* luksctl provides utilities to more easily access storage devices, allowing to open, close or check the status of an encrypted device. It's derived from the python script `luksctl <https://github.com/Laniakea-elixir-it/luksctl>`_;
* lukctl_api provides a RESTful API written in Flask and Gunicorn used to open or check the status of an encrypted device thorugh http requests. It's derived from the python script `luksctl_api <https://github.com/Laniakea-elixir-it/luksctl_api>`_;


Installation
------------
pyluks can be installed using pip. In order to avoid problems when installing ``cryptography``, one of pyluks dependencies, pip needs to be updated. It's recommended to install the package in a virtual environment:

.. code-block:: console 

   [root@vm ~]# python3 -m pip install virtualenv
   [root@vm ~]# python3 -m virtualenv pyluks_venv
   [root@vm ~]# source pyluks_venv/bin/activate
   (pyluks_venv) [root@vm ~]# pip install --upgrade pip
   (pyluks_venv) [root@vm ~]# pip install pyluks


.. toctree::
   :maxdepth: 2
   :caption: Contents:
 
   fastluks
   fastluks_bin
   cryptdev_file
   luksctl
   luksctl_api
   modules

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


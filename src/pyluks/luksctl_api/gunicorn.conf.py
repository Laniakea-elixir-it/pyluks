import os

workers = 2
bind = '0.0.0.0:5000'
umask = 0o007
_certfile_path = '/etc/luks/gunicorn-cert.pem'
certfile = _certfile_path if os.path.exists(_certfile_path) else None
_keyfile_path = '/etc/luks/gunicorn-key.pem'
keyfile = _keyfile_path if os.path.exists(_keyfile_path) else None

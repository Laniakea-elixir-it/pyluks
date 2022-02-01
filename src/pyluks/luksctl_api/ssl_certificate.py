# Import dependencies
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography import x509
from cryptography.hazmat.primitives import hashes
import datetime

def generate_private_key(key_size, key_file):
    """Generates a private key for the self signed certificate.

    :param key_size: Key length in bits
    :type key_size: int
    :param key_file: Path where the private key is stored.
    :type key_file: str
    :return: An instance of RSAPrivateKey containing the private key.
    :rtype: RSAPrivateKey
    """
    
    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)

    with open(key_file, 'wb') as f:
        f.write(key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.TraditionalOpenSSL, encryption_algorithm=serialization.NoEncryption()))

    return key


def generate_self_signed_cert(CN='localhost', cert_file='/etc/luks/gunicorn-cert.pem', expiration_days=3650, key_size=4096, key_file='/etc/luks/gunicorn-key.pem'):
    """Generates a self signed certificate used by the luksctl API for https.

    :param CN: DNS name, defaults to 'localhost'
    :type CN: str, optional
    :param cert_file: Path where the certificate is stored, defaults to '/etc/luks/gunicorn-cert.pem'
    :type cert_file: str, optional
    :param expiration_days: Expiration of the self signed certificate, defaults to 3650
    :type expiration_days: int, optional
    :param key_size: Private key length in bits, defaults to 4096
    :type key_size: int, optional
    :param key_file: Path where the private key is stored, defaults to '/etc/luks/gunicorn-key.pem'
    :type key_file: str, optional
    """
    subject = issuer = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, CN)])

    key = generate_private_key(key_size=key_size, key_file=key_file)

    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
    # The certificate will be valid for 3650 days
        datetime.datetime.utcnow() + datetime.timedelta(days=expiration_days)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(CN)]), critical=False,
    # Sign the certificate with private key
    ).sign(key, hashes.SHA256())

    with open(cert_file, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

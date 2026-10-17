"""TLS identities, possession proofs, and a two-sided short authentication string."""
import base64
import datetime as dt
import hashlib
import os
import secrets
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from .protocol import VERSION, ProtocolError


def fingerprint(der):
    return hashlib.sha256(der).hexdigest()


def b64(data):
    return base64.b64encode(data).decode("ascii")


def unb64(data, limit=4096):
    if not isinstance(data, str) or len(data) > limit * 2:
        raise ProtocolError("Invalid authentication data")
    try:
        result = base64.b64decode(data, validate=True)
    except ValueError as exc:
        raise ProtocolError("Invalid base64") from exc
    if len(result) > limit:
        raise ProtocolError("Authentication data too large")
    return result


def transcript(server_der, client_der, server_nonce, client_nonce):
    # Fixed-size hashes and nonces give an unambiguous, role-bound transcript.
    return (b"MouseShare pairing v1\0" + hashlib.sha256(server_der).digest()
            + hashlib.sha256(client_der).digest() + server_nonce + client_nonce)


def pairing_code(proof):
    digest = hashlib.sha256(b"SAS\0" + proof).digest()
    return f"{int.from_bytes(digest[:4], 'big') % 1_000_000:06d}"


def check_hello(hello):
    if hello.get("type") != "hello" or hello.get("version") != VERSION:
        raise ProtocolError("Incompatible MouseShare version")
    der = unb64(hello.get("cert"))
    cert = x509.load_der_x509_certificate(der)
    if not isinstance(cert.public_key(), ec.EllipticCurvePublicKey):
        raise ProtocolError("Unsupported identity key")
    if not isinstance(cert.public_key().curve, ec.SECP256R1):
        raise ProtocolError("Unsupported identity curve")
    if hello.get("id") != fingerprint(der):
        raise ProtocolError("Identity mismatch")
    nonce = unb64(hello.get("nonce"), 32)
    if len(nonce) != 32:
        raise ProtocolError("Invalid nonce")
    name = hello.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 80 or any(ord(c) < 32 for c in name):
        raise ProtocolError("Invalid device name")
    return der, cert, nonce


class Identity:
    def __init__(self, directory):
        self.cert_path = directory / "identity.crt"
        self.key_path = directory / "identity.key"
        if not self.key_path.exists() or not self.cert_path.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MouseShare device")])
            now = dt.datetime.now(dt.timezone.utc)
            cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                    .public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now - dt.timedelta(days=1))
                    .not_valid_after(now + dt.timedelta(days=3650))
                    .sign(key, hashes.SHA256()))
            for path, data in [
                (self.key_path, key.private_bytes(serialization.Encoding.PEM,
                 serialization.PrivateFormat.PKCS8, serialization.NoEncryption())),
                (self.cert_path, cert.public_bytes(serialization.Encoding.PEM)),
            ]:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
        self.key = serialization.load_pem_private_key(self.key_path.read_bytes(), None)
        self.cert = x509.load_pem_x509_certificate(self.cert_path.read_bytes())
        self.der = self.cert.public_bytes(serialization.Encoding.DER)
        self.id = fingerprint(self.der)

    def hello(self, name):
        return {"type": "hello", "version": VERSION, "id": self.id,
                "name": name[:80], "cert": b64(self.der), "nonce": b64(secrets.token_bytes(32))}

    def sign(self, proof):
        return b64(self.key.sign(proof, ec.ECDSA(hashes.SHA256())))

    def context(self, server=False):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        if server:
            context.load_cert_chain(str(self.cert_path), str(self.key_path))
        else:
            # Authentication is by an exact certificate pin or two-sided SAS confirmation.
            # The client additionally proves possession of its identity key at application level.
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context


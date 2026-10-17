import os

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from mouseshare.protocol import ProtocolError
from mouseshare.security import Identity, check_hello, pairing_code, transcript, unb64


def test_identity_persistence_and_permissions(tmp_path):
    identity = Identity(tmp_path)
    assert Identity(tmp_path).id == identity.id
    assert identity.context(True).minimum_version.name == "TLSv1_2"
    if os.name != "nt":
        assert tmp_path.joinpath("identity.key").stat().st_mode & 0o777 == 0o600


def test_signed_transcript_binds_both_parties_and_challenges(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    server, client = Identity(a), Identity(b)
    proof = transcript(server.der, client.der, b"s" * 32, b"c" * 32)
    signature = unb64(client.sign(proof))
    client.cert.public_key().verify(signature, proof, ec.ECDSA(hashes.SHA256()))
    for changed in [transcript(client.der, server.der, b"s" * 32, b"c" * 32),
                    transcript(server.der, client.der, b"t" * 32, b"c" * 32)]:
        with pytest.raises(InvalidSignature):
            client.cert.public_key().verify(signature, changed, ec.ECDSA(hashes.SHA256()))
    assert len(pairing_code(proof)) == 6
    assert pairing_code(proof) == pairing_code(proof)


def test_hello_identity_binding(tmp_path):
    identity = Identity(tmp_path)
    hello = identity.hello("test")
    assert check_hello(hello)[0] == identity.der
    hello["id"] = "0" * 64
    with pytest.raises(ProtocolError):
        check_hello(hello)


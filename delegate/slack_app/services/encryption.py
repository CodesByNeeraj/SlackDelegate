import os
import boto3
from dotenv import load_dotenv

load_dotenv()

_kms_client = None


def _get_kms_client():
    global _kms_client
    if _kms_client is None:
        _kms_client = boto3.client(
            "kms",
            region_name=os.environ.get("AWS_REGION", "ap-southeast-1"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        )
    return _kms_client


def encrypt_token(plaintext_token: str) -> bytes:
    """
    Called once, right after exchanging the OAuth code for a bot token,
    before it's ever written to DynamoDB. Never store a plaintext token.
    """
    kms = _get_kms_client()
    key_id = os.environ["KMS_KEY_ID"]
    response = kms.encrypt(KeyId=key_id, Plaintext=plaintext_token.encode())
    return response["CiphertextBlob"]


def decrypt_token(ciphertext_blob) -> str:
    """
    Called every time slack_client.py needs to make an API call on
    behalf of a workspace. Decrypts in memory, never written back to disk.
    """
    kms = _get_kms_client()
    response = kms.decrypt(CiphertextBlob=bytes(ciphertext_blob))
    return response["Plaintext"].decode()
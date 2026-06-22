import os
import boto3
from dotenv import load_dotenv

load_dotenv()

_resource = None


def get_dynamo_resource():
    """
    Returns a single shared boto3 DynamoDB resource.
    Both slack-app and api import this so there's one connection
    pattern across the whole system.
    """
    global _resource
    if _resource is None:
        _resource = boto3.resource(
            "dynamodb",
            region_name=os.environ.get("AWS_REGION", "ap-southeast-1"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        )
    return _resource


def get_table(table_name: str):
    return get_dynamo_resource().Table(table_name)
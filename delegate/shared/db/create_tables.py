"""
Creates the three DynamoDB tables for Delegate.
Run this once per AWS account/region to provision the schema.

Usage:
    python create_tables.py
"""

import os
import boto3
from dotenv import load_dotenv

load_dotenv()

dynamodb = boto3.resource(
    "dynamodb",
    region_name=os.environ.get("AWS_REGION", "ap-southeast-1"),
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
)


def create_workspaces_table():
    table = dynamodb.create_table(
        TableName="Workspaces",
        KeySchema=[
            {"AttributeName": "workspace_id", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "workspace_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    print("Created table: Workspaces")


def create_tasks_table():
    table = dynamodb.create_table(
        TableName="Tasks",
        KeySchema=[
            {"AttributeName": "workspace_id", "KeyType": "HASH"},
            {"AttributeName": "task_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "workspace_id", "AttributeType": "S"},
            {"AttributeName": "task_id", "AttributeType": "S"},
            {"AttributeName": "owner_slack_id", "AttributeType": "S"},
            {"AttributeName": "due_date", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "owner_slack_id-index",
                "KeySchema": [
                    {"AttributeName": "owner_slack_id", "KeyType": "HASH"},
                    {"AttributeName": "due_date", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    print("Created table: Tasks (with owner_slack_id-index GSI)")


def create_transcripts_table():
    table = dynamodb.create_table(
        TableName="Transcripts",
        KeySchema=[
            {"AttributeName": "workspace_id", "KeyType": "HASH"},
            {"AttributeName": "transcript_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "workspace_id", "AttributeType": "S"},
            {"AttributeName": "transcript_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    print("Created table: Transcripts")


def create_drafts_table():
    table = dynamodb.create_table(
        TableName="Drafts",
        KeySchema=[
            {"AttributeName": "draft_id", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "draft_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    dynamodb.meta.client.update_time_to_live(
        TableName="Drafts",
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
    )
    print("Created table: Drafts (with 24h TTL)")


def create_search_logs_table():
    table = dynamodb.create_table(
        TableName="SearchLogs",
        KeySchema=[
            {"AttributeName": "log_id", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "log_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    print("Created table: SearchLogs")


def create_conversation_history_table():
    table = dynamodb.create_table(
        TableName="ConversationHistory",
        KeySchema=[
            {"AttributeName": "workspace_id", "KeyType": "HASH"},
            {"AttributeName": "user_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "workspace_id", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    print("Created table: ConversationHistory (with 2h TTL)")


if __name__ == "__main__":
    create_workspaces_table()
    create_tasks_table()
    create_transcripts_table()
    create_drafts_table()
    create_search_logs_table()
    create_conversation_history_table()
    print("\nAll tables created successfully.")
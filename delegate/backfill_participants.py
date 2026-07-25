"""
One-off script to extract and backfill participant names for existing transcripts.
Run from the delegate/ directory:

    python backfill_participants.py
"""
import boto3
from dotenv import load_dotenv
from slack_app.agents.tools.participant_extractor import extract_participants

load_dotenv()

TABLE_NAME = "Transcripts"


def run():
    dynamodb = boto3.resource("dynamodb", region_name="ap-southeast-1")
    table = dynamodb.Table(TABLE_NAME)

    response = table.scan(ProjectionExpression="workspace_id, transcript_id, raw_text, filename")
    items = response.get("Items", [])
    while "LastEvaluatedKey" in response:
        response = table.scan(
            ProjectionExpression="workspace_id, transcript_id, raw_text, filename",
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    print(f"Found {len(items)} transcripts to backfill.")

    for item in items:
        workspace_id = item["workspace_id"]
        transcript_id = item["transcript_id"]
        filename = item.get("filename", "unknown")
        raw_text = item.get("raw_text", "").strip()

        if not raw_text:
            print(f"  SKIP {filename} ({transcript_id}) — no raw_text")
            continue

        print(f"  Processing {filename} ({transcript_id})...", end=" ", flush=True)
        try:
            participants = extract_participants(raw_text)
            table.update_item(
                Key={"workspace_id": workspace_id, "transcript_id": transcript_id},
                UpdateExpression="SET participants = :p",
                ExpressionAttributeValues={":p": participants},
            )
            print(f"done — {participants}")
        except Exception as e:
            print(f"FAILED — {e}")

    print("\nDone.")


if __name__ == "__main__":
    run()

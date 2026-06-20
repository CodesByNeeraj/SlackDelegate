import os

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from agents.tools.parsetext import download_file, extract_text_from_docx, extract_text_from_pdf
load_dotenv()

# This sample slack application uses SocketMode
# For the companion getting started setup guide,
# see: https://docs.slack.dev/tools/bolt-python/getting-started

# Initializes your app with your bot token
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

@app.command("/delegate")
def handle_delegate_command(ack, body, say):
    ack()
    say(
        text="Upload your meeting transcript (docx or pdf) in this channel and I'll extract the action items.",
        channel=body["channel_id"]
    )
    
   
#silence file upload warnings 
@app.event("file_shared")
def handle_file_shared_noop(body, logger):
    pass

@app.event("message")
def handle_message_events(event, client, say):
    if event.get("subtype") == "file_share":
        files = event.get("files", [])
        if not files:
            return
        
        file_data = files[0]
        file_url = file_data["url_private_download"]
        file_type = file_data["filetype"]
        
        file_bytes = download_file(file_url, os.environ.get("SLACK_BOT_TOKEN"))
        
        if file_type == "docx":
            transcript_text = extract_text_from_docx(file_bytes)
        elif file_type == "pdf":
            transcript_text = extract_text_from_pdf(file_bytes)
        else:
            say(text="Please upload a docx or pdf file.", channel=event["channel"])
            return
        
        print("EXTRACTED TEXT:", transcript_text[:500])
        say(text="Got it, processing your transcript now...", channel=event["channel"])
        # next step: send transcript_text to the LLM for parsing



@app.action("button_click")
def action_button_click(body, ack, say):
    # Acknowledge the action
    ack()
    say(f"<@{body['user']['id']}> clicked the button")


# Start your app
if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()

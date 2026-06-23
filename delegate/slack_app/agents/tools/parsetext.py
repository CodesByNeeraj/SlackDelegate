import requests
import docx
import pdfplumber
import io

def download_file(file_url, bot_token):
    headers = {"Authorization": f"Bearer {bot_token}"}
    response = requests.get(file_url, headers=headers)
    return response.content

def extract_text_from_docx(file_bytes):
    doc = docx.Document(io.BytesIO(file_bytes))
    return "\n".join([para.text for para in doc.paragraphs])

def extract_text_from_pdf(file_bytes):
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text
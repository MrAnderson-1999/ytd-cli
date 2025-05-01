from flask import Flask, request, Response, stream_with_context
import yt_dlp
import os
import uuid

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return {'error': 'No URL provided'}, 400

    # Use a unique filename per request to avoid collisions
    filename = f"{uuid.uuid4().hex}.wav"
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'outtmpl': filename,
        'quiet': True,
    }

    def generate():
        # 1. Download (returns int, not iterable) :contentReference[oaicite:3]{index=3}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # 2. Stream the file in chunks :contentReference[oaicite:4]{index=4}
        try:
            with open(filename, 'rb') as f:
                chunk = f.read(8192)
                while chunk:
                    yield chunk
                    chunk = f.read(8192)
        finally:
            # 3. Remove the temp file after streaming
            if os.path.exists(filename):
                os.remove(filename)

    headers = {
        'Content-Disposition': f'attachment; filename="audio.wav"',
        'Content-Type': 'audio/wav'
    }
    return Response(
        stream_with_context(generate()),
        headers=headers,
        mimetype='audio/wav'
    )

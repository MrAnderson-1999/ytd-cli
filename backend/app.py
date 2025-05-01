from flask import Flask, request, Response, stream_with_context, abort
from flask_cors import CORS
import yt_dlp
import os

app = Flask(__name__)
CORS(app, resources={r"/download": {"origins": "*"}})

@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return {'error': 'No URL provided'}, 400

    # Use video title in filename
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'outtmpl': '%(title)s.%(ext)s',
        'quiet': True,
    }

    # Download and get info
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    title = info.get('title') or 'audio'
    filename = f"{title}.wav"

    def generate():
        try:
            with open(filename, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    yield chunk
        finally:
            try:
                os.remove(filename)
            except OSError:
                pass

    headers = {
        'Content-Disposition': f'attachment; filename="{title}.wav"',
        'Content-Type': 'audio/wav',
    }
    return Response(
        stream_with_context(generate()),
        headers=headers,
        mimetype='audio/wav'
    )

if __name__ == '__main__':
    # Local testing
    app.run(host='0.0.0.0', port=5000)

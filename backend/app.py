from flask import Flask, request, Response, stream_with_context, abort
from flask_cors import CORS
import yt_dlp
import os

app = Flask(__name__)
# enable CORS so your frontend on :80 can POST to :5000
CORS(app, resources={r"/download": {"origins": "*"}})

@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return {'error': 'No URL provided'}, 400

    # original style download + conversion, using title-based template
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

    # run download and get back info dict, including actual filepath
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # yt-dlp only populates 'filepath' after post-processing
    filepath = info.get('filepath')
    if not filepath or not os.path.exists(filepath):
        abort(500, f"Download failed, file not found: {filepath!r}")

    def generate():
        try:
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    yield chunk
        finally:
            try:
                os.remove(filepath)
            except OSError:
                pass

    # use the original video title for the client filename
    title = info.get('title', 'audio')
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
    app.run(host='0.0.0.0', port=5000)

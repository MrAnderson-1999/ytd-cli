from flask import Flask, request, Response, stream_with_context, abort
from flask_cors import CORS
import yt_dlp
import os
from urllib.parse import quote


app = Flask(__name__)
# Allow your frontend on port 80 to POST here without CORS errors
CORS(app, resources={r"/download": {"origins": "*"}})

@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json() or {}
    url  = data.get('url', '').strip()
    if not url:
        return {'error': 'No URL provided'}, 400

    # 1) Download+convert with title-based template
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
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)  # returns metadata dict :contentReference[oaicite:7]{index=7}

        # 2) Compute the raw filename and swap to .wav
        raw_path = ydl.prepare_filename(info)        # e.g. "My Video Title.webm" :contentReference[oaicite:8]{index=8}
    base, _   = os.path.splitext(raw_path)           # splits into ("My Video Title", ".webm") :contentReference[oaicite:9]{index=9}
    wav_path  = base + '.wav'                        # "My Video Title.wav"

    # 3) Verify file exists
    if not os.path.exists(wav_path):
        abort(500, f"Download failed, file not found: {wav_path!r}")

    # 4) Stream back to client
    def generate():
        try:
            with open(wav_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    yield chunk
        finally:
            # Cleanup once streaming finishes or errors
            try:
                os.remove(wav_path)
            except OSError:
                pass

    # After downloading and extracting info:
    title = info.get('title', 'audio')
    # ASCII fallback: strip or transliterate non-ASCII
    ascii_title = title.encode('ascii', 'ignore').decode() or 'audio'
    # Percent-encode UTF-8 title per RFC5987
    encoded_title = quote(title)
    # Build the combined Content-Disposition header
    disposition = (
        f"attachment; "
        f'filename="{ascii_title}.wav"; '
        f"filename*=UTF-8''{encoded_title}.wav"
    )

    return Response(
        stream_with_context(generate()),            # keep request context active :contentReference[oaicite:10]{index=10}
        headers={
            'Content-Disposition': disposition,
            'Content-Type': 'audio/wav'
        },
        mimetype='audio/wav'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

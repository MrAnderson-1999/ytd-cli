import yt_dlp

def download_youtube_audio_as_wav(url):
    ydl_opts = {
        # Select the best audio quality available
        'format': 'bestaudio/best',
        # Post-process: extract audio and convert to WAV
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',  # This quality setting is not used for lossless formats like WAV, but required
        }],
        # Template for the output filename: will use the video title and appropriate extension
        'outtmpl': '%(title)s.%(ext)s',
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

if __name__ == '__main__':
    url = input("Enter the YouTube URL: ").strip()
    download_youtube_audio_as_wav(url)

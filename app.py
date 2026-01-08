"""
YouTube MP3 Downloader - Render.com Version
Developer: Ahmed Faiyazahed Sallu
Email: sallua543@gmail.com
"""

import os
import sys
import shutil
import time
import re
import json
import uuid
import threading
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_cors import CORS
from urllib.parse import urlparse, parse_qs
import yt_dlp

# ========== CONFIGURATION ==========
DEVELOPER_NAME = "Ahmed F.Sallu"
DEVELOPER_EMAIL = "sallua543@gmail.com"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")

# Create directory if not exists
os.makedirs(DEFAULT_DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__, 
    static_folder=os.path.join(BASE_DIR, 'static'),
    template_folder=os.path.join(BASE_DIR, 'templates')
)
CORS(app)

# ========== GLOBAL VARIABLES ==========
download_progress = {}
active_downloads = {}

# ========== UTILITY FUNCTIONS ==========
def log_message(message):
    """Simple logging"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def get_free_space():
    """Get free disk space in GB"""
    try:
        stat = shutil.disk_usage(DEFAULT_DOWNLOAD_DIR)
        return round(stat.free / (1024**3), 2)
    except:
        return 10.0  # Default value

def sanitize_url(url):
    """Clean and validate YouTube URL"""
    if not url:
        return None
    
    url = url.strip()
    
    # Convert youtu.be to youtube.com
    if 'youtu.be' in url:
        video_id = url.split('/')[-1].split('?')[0]
        url = f'https://www.youtube.com/watch?v={video_id}'
    
    # Remove tracking parameters
    url = re.sub(r'\?si=.*', '', url)
    url = re.sub(r'&t=\d+s', '', url)
    
    # Validate YouTube URL
    patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return f"https://www.youtube.com/watch?v={match.group(1)}"
    
    return None

def extract_video_id(url):
    """Extract YouTube video ID from URL"""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be\/([0-9A-Za-z_-]{11})',
        r'embed\/([0-9A-Za-z_-]{11})',
        r'\/shorts\/([0-9A-Za-z_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def clean_filename(filename):
    """Clean filename for safe saving"""
    if not filename:
        return "audio"
    
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = re.sub(r'\s+', ' ', filename)
    filename = filename.strip()
    
    # Truncate if too long
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:95] + ext if ext else name[:100]
    
    return filename

def format_duration(seconds):
    """Format seconds to HH:MM:SS"""
    if not seconds:
        return "0:00"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

# ========== REAL YOUTUBE DOWNLOAD USING YT-DLP ==========
def download_youtube_audio_real(url, quality, download_id):
    """Download real YouTube audio using yt-dlp"""
    try:
        log_message(f"Starting REAL download: {url[:50]}...")
        
        # Initialize progress
        download_progress[download_id] = {
            "status": "starting",
            "percent": "0",
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "speed": "0 B/s",
            "eta": "00:30",
            "filename": "",
            "title": "Initializing download...",
            "message": ""
        }
        
        # Custom yt-dlp options for Render.com
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DEFAULT_DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': False,
            'progress_hooks': [lambda d: progress_hook(d, download_id)],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality,
            }],
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'referer': 'https://www.youtube.com/',
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'ignoreerrors': False,
            'no_check_certificate': False,
            'prefer_insecure': False,
            'keepvideo': False,
            'writethumbnail': False,
            'writeinfojson': False,
            'extract_flat': False,
            'noplaylist': True,
            'sleep_interval': 1,
            'max_sleep_interval': 5,
            'external_downloader': None,
            'concurrent_fragment_downloads': 4,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First get info
            info = ydl.extract_info(url, download=False)
            video_title = clean_filename(info.get('title', f'audio_{download_id[:8]}'))
            
            download_progress[download_id].update({
                "status": "preparing",
                "percent": "10",
                "title": f"Preparing: {video_title[:50]}...",
                "message": "Starting download..."
            })
            
            # Then download
            result = ydl.extract_info(url, download=True)
        
        # Find the downloaded file
        expected_filename = f"{video_title}.mp3"
        expected_path = os.path.join(DEFAULT_DOWNLOAD_DIR, expected_filename)
        
        # Check if file exists
        if os.path.exists(expected_path):
            filepath = expected_path
            downloaded_filename = expected_filename
        else:
            # Search for any new MP3 files
            all_files_before = set(os.listdir(DEFAULT_DOWNLOAD_DIR))
            mp3_files = [f for f in os.listdir(DEFAULT_DOWNLOAD_DIR) 
                        if f.endswith('.mp3') and f not in all_files_before]
            
            if mp3_files:
                downloaded_filename = mp3_files[0]
                filepath = os.path.join(DEFAULT_DOWNLOAD_DIR, downloaded_filename)
            else:
                raise Exception("Downloaded MP3 file not found")
        
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath) / (1024 * 1024)  # MB
            
            # Update progress to completed
            download_progress[download_id].update({
                "status": "completed",
                "percent": "100",
                "downloaded_bytes": file_size * 1024 * 1024,
                "total_bytes": file_size * 1024 * 1024,
                "speed": "Completed",
                "eta": "00:00",
                "title": video_title,
                "message": f"Downloaded: {video_title} ({file_size:.2f} MB)",
                "filename": downloaded_filename
            })
            
            # Save to active downloads
            active_downloads[download_id] = {
                "status": "success",
                "message": f"Downloaded: {video_title} ({file_size:.2f} MB)",
                "filename": downloaded_filename,
                "path": filepath,
                "size_mb": round(file_size, 2),
                "title": video_title,
                "download_url": f"/download-file/{download_id}",
                "created_at": datetime.now().isoformat()
            }
            
            log_message(f"✅ Download completed: {downloaded_filename} ({file_size:.2f} MB)")
            
            # Clean old files if storage > 500MB
            cleanup_old_files(500)
        else:
            raise Exception("Downloaded file does not exist")
            
    except Exception as e:
        error_msg = str(e)
        log_message(f"❌ Download error: {error_msg}")
        
        if download_id in download_progress:
            download_progress[download_id].update({
                "status": "error",
                "message": error_msg[:100]  # Truncate long errors
            })

def progress_hook(d, download_id):
    """Progress hook for yt-dlp"""
    if download_id not in download_progress:
        return
    
    if d['status'] == 'downloading':
        # Parse progress information
        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        downloaded_bytes = d.get('downloaded_bytes', 0)
        
        # Calculate percentage
        if total_bytes > 0:
            percent = (downloaded_bytes / total_bytes) * 100
        else:
            percent = 0
        
        # Update progress
        download_progress[download_id].update({
            "status": "downloading",
            "percent": f"{percent:.1f}",
            "downloaded_bytes": downloaded_bytes,
            "total_bytes": total_bytes,
            "speed": d.get('_speed_str', '0 B/s'),
            "eta": d.get('_eta_str', '00:00'),
            "title": d.get('filename', d.get('_filename', 'Downloading...'))[:60],
            "message": f"Downloading: {percent:.1f}%"
        })
    
    elif d['status'] == 'finished':
        download_progress[download_id].update({
            "status": "converting",
            "percent": "95",
            "message": "Converting to MP3...",
            "speed": "Converting"
        })
    
    elif d['status'] == 'error':
        download_progress[download_id].update({
            "status": "error",
            "message": d.get('error', 'Unknown error')[:100]
        })

def cleanup_old_files(max_size_mb=500):
    """Clean old files if storage exceeds limit"""
    try:
        files = []
        for file in os.listdir(DEFAULT_DOWNLOAD_DIR):
            if file.endswith('.mp3'):
                filepath = os.path.join(DEFAULT_DOWNLOAD_DIR, file)
                size = os.path.getsize(filepath) / (1024 * 1024)  # MB
                modified = os.path.getmtime(filepath)
                files.append({
                    'path': filepath,
                    'size': size,
                    'modified': modified,
                    'name': file
                })
        
        # Sort by modification time (oldest first)
        files.sort(key=lambda x: x['modified'])
        
        # Calculate total size
        total_size = sum(f['size'] for f in files)
        
        # Remove old files if total size exceeds limit
        removed = 0
        while total_size > max_size_mb and files:
            oldest = files.pop(0)
            try:
                os.remove(oldest['path'])
                total_size -= oldest['size']
                removed += 1
                log_message(f"🧹 Cleaned old file: {oldest['name']}")
            except:
                pass
        
        if removed > 0:
            log_message(f"🧹 Cleaned {removed} old files")
            
    except Exception as e:
        log_message(f"Cleanup error: {e}")

# ========== FLASK ROUTES ==========
@app.route("/")
def home():
    """Home page"""
    try:
        # Get basic stats
        total_downloads = 0
        total_size = 0
        files_list = []
        
        if os.path.exists(DEFAULT_DOWNLOAD_DIR):
            for file in os.listdir(DEFAULT_DOWNLOAD_DIR):
                if file.endswith('.mp3'):
                    total_downloads += 1
                    try:
                        filepath = os.path.join(DEFAULT_DOWNLOAD_DIR, file)
                        size = os.path.getsize(filepath) / (1024 * 1024)
                        total_size += size
                        
                        modified = os.path.getmtime(filepath)
                        files_list.append({
                            "name": file,
                            "size_mb": round(size, 2),
                            "path": filepath,
                            "modified": datetime.fromtimestamp(modified).strftime("%Y-%m-%d %H:%M")
                        })
                    except:
                        pass
        
        free_space = get_free_space()
        
        return render_template(
            "index.html", 
            stats={
                "total_downloads": total_downloads,
                "total_size_mb": round(total_size, 2),
                "files": files_list[:5],
                "developer": {
                    "name": DEVELOPER_NAME,
                    "email": DEVELOPER_EMAIL,
                    "github": "github.com/ahmedsallu7493"
                }
            },
            free_space=free_space,
            is_pythonanywhere=False,
            developer={
                "name": DEVELOPER_NAME,
                "email": DEVELOPER_EMAIL,
                "github": "github.com/ahmedsallu7493"
            }
        )
    except Exception as e:
        log_message(f"Home error: {e}")
        return f"""
        <html><body style="padding:20px;font-family:Arial;">
            <h1>YouTube MP3 Downloader</h1>
            <p>Status: Running</p>
            <p>Error: {str(e)}</p>
            <p><a href="/health-check">Check Health</a></p>
        </body></html>
        """

@app.route("/check-url", methods=["POST"])
def check_url_endpoint():
    """Check URL using yt-dlp"""
    try:
        data = request.get_json()
        url = data.get("url", "").strip()
        
        if not url:
            return jsonify({"status": "error", "message": "No URL provided"}), 400
        
        sanitized_url = sanitize_url(url)
        if not sanitized_url:
            return jsonify({"status": "error", "message": "Invalid YouTube URL"}), 400
        
        # Get video info using yt-dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extract_flat': False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(sanitized_url, download=False)
            
            # Get best thumbnail
            thumbnails = info.get('thumbnails', [])
            thumbnail = ''
            if thumbnails:
                # Try to get highest quality thumbnail
                for thumb in reversed(thumbnails):
                    if thumb.get('url'):
                        thumbnail = thumb['url']
                        break
            
            if not thumbnail and info.get('thumbnail'):
                thumbnail = info['thumbnail']
            
            # Format duration
            duration_seconds = info.get('duration', 0)
            duration = format_duration(duration_seconds)
            
            # Check if video is too long (>2 hours)
            warning = None
            if duration_seconds > 7200:  # 2 hours
                warning = "Video is long (>2 hours). Download may take time."
            elif duration_seconds > 3600:  # 1 hour
                warning = "Video is long (>1 hour). Please be patient."
            
            return jsonify({
                "status": "success",
                "info": {
                    "title": info.get('title', 'Unknown Title'),
                    "duration": duration,
                    "uploader": info.get('uploader', 'Unknown Uploader'),
                    "thumbnail": thumbnail,
                    "duration_seconds": duration_seconds,
                    "description": info.get('description', '')[:100] + '...' if info.get('description') else '',
                    "warning": warning,
                    "view_count": info.get('view_count', 0),
                    "like_count": info.get('like_count', 0)
                }
            })
            
        except Exception as e:
            log_message(f"URL check error: {e}")
            return jsonify({
                "status": "error", 
                "message": f"Could not fetch video info: {str(e)[:100]}"
            }), 400
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download", methods=["POST"])
def download():
    """Start download"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        url = data.get("url", "").strip()
        quality = data.get("quality", "192")
        
        if not url:
            return jsonify({"status": "error", "message": "Please enter a YouTube URL"}), 400
        
        sanitized_url = sanitize_url(url)
        if not sanitized_url:
            return jsonify({"status": "error", "message": "Invalid YouTube URL"}), 400
        
        # Check if video is too long (>4 hours)
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
                info = ydl.extract_info(sanitized_url, download=False)
            
            if info.get('duration', 0) > 14400:  # 4 hours limit
                return jsonify({
                    "status": "error",
                    "message": "Video is too long (max 4 hours allowed)"
                }), 400
                
        except:
            pass  # Continue anyway
        
        # Generate download ID
        download_id = str(uuid.uuid4())
        
        # Start download in background thread
        thread = threading.Thread(
            target=download_youtube_audio_real,
            args=(sanitized_url, quality, download_id)
        )
        thread.daemon = True
        thread.start()
        
        log_message(f"Download started: {download_id}")
        
        return jsonify({
            "status": "started",
            "message": "Download started successfully!",
            "download_id": download_id,
            "check_progress": f"/progress/{download_id}",
            "download_url": f"/download-file/{download_id}"
        })
        
    except Exception as e:
        log_message(f"Download route error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/progress/<download_id>")
def get_progress(download_id):
    """Get download progress"""
    if download_id in download_progress:
        return jsonify({
            "status": "success",
            "progress": download_progress[download_id]
        })
    
    elif download_id in active_downloads:
        return jsonify({
            "status": "success",
            "progress": {
                "status": "completed",
                "percent": "100",
                "result": active_downloads[download_id]
            }
        })
    
    else:
        return jsonify({
            "status": "error",
            "message": "Download session not found"
        }), 404

@app.route("/download-file/<download_id>")
def download_file(download_id):
    """Serve downloaded file"""
    try:
        # Check if download is in active_downloads
        if download_id in active_downloads:
            result = active_downloads[download_id]
            if "path" in result and os.path.exists(result["path"]):
                try:
                    return send_file(
                        result["path"],
                        as_attachment=True,
                        download_name=result.get("filename", "audio.mp3"),
                        mimetype='audio/mpeg'
                    )
                except Exception as e:
                    log_message(f"Error sending file: {e}")
        
        # Fallback: Search for file in download directory
        if os.path.exists(DEFAULT_DOWNLOAD_DIR):
            # Look for any file that might contain the download_id
            for file in os.listdir(DEFAULT_DOWNLOAD_DIR):
                if download_id in file or file.endswith('.mp3'):
                    filepath = os.path.join(DEFAULT_DOWNLOAD_DIR, file)
                    if os.path.exists(filepath):
                        return send_file(
                            filepath,
                            as_attachment=True,
                            download_name=file,
                            mimetype='audio/mpeg'
                        )
        
        return jsonify({
            "status": "error", 
            "message": "File not found. Try downloading again."
        }), 404
        
    except Exception as e:
        log_message(f"Download file error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download-direct/<filename>")
def download_direct(filename):
    """Download file directly by filename"""
    try:
        # Security check
        if ".." in filename or "/" in filename or "\\" in filename:
            return jsonify({"status": "error", "message": "Invalid filename"}), 400
        
        filepath = os.path.join(DEFAULT_DOWNLOAD_DIR, filename)
        
        if os.path.exists(filepath):
            return send_file(
                filepath,
                as_attachment=True,
                download_name=filename,
                mimetype='audio/mpeg'
            )
        else:
            return jsonify({"status": "error", "message": "File not found"}), 404
            
    except Exception as e:
        log_message(f"Direct download error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/list-files")
def list_files():
    """List downloaded files"""
    try:
        files = []
        if os.path.exists(DEFAULT_DOWNLOAD_DIR):
            for file in sorted(os.listdir(DEFAULT_DOWNLOAD_DIR), 
                             key=lambda x: os.path.getmtime(os.path.join(DEFAULT_DOWNLOAD_DIR, x)), 
                             reverse=True):
                if file.endswith('.mp3'):
                    filepath = os.path.join(DEFAULT_DOWNLOAD_DIR, file)
                    try:
                        size = os.path.getsize(filepath) / (1024 * 1024)
                        modified = os.path.getmtime(filepath)
                        files.append({
                            "name": file,
                            "size_mb": round(size, 2),
                            "path": filepath,
                            "modified": datetime.fromtimestamp(modified).strftime("%Y-%m-%d %H:%M")
                        })
                    except:
                        continue
        
        return jsonify({
            "status": "success",
            "files": files[:10],
            "count": len(files),
            "total_size_mb": round(sum(f["size_mb"] for f in files), 2)
        })
    except Exception as e:
        log_message(f"List files error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/delete-file", methods=["POST"])
def delete_file():
    """Delete downloaded file"""
    try:
        data = request.get_json()
        filename = data.get("filename", "")
        
        if not filename:
            return jsonify({"status": "error", "message": "No filename"}), 400
        
        filepath = os.path.join(DEFAULT_DOWNLOAD_DIR, filename)
        
        # Security check
        if not filepath.startswith(DEFAULT_DOWNLOAD_DIR) or ".." in filename:
            return jsonify({"status": "error", "message": "Invalid filename"}), 400
        
        if os.path.exists(filepath):
            os.remove(filepath)
            
            # Remove from active_downloads if present
            for download_id, data in list(active_downloads.items()):
                if data.get("filename") == filename:
                    del active_downloads[download_id]
                    del download_progress[download_id]
            
            log_message(f"Deleted: {filename}")
            return jsonify({"status": "success", "message": f"Deleted: {filename}"})
        else:
            return jsonify({"status": "error", "message": "File not found"}), 404
            
    except Exception as e:
        log_message(f"Delete error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/stats")
def stats():
    """Get download statistics"""
    try:
        total_downloads = 0
        total_size = 0
        
        if os.path.exists(DEFAULT_DOWNLOAD_DIR):
            for file in os.listdir(DEFAULT_DOWNLOAD_DIR):
                if file.endswith('.mp3'):
                    total_downloads += 1
                    try:
                        filepath = os.path.join(DEFAULT_DOWNLOAD_DIR, file)
                        total_size += os.path.getsize(filepath) / (1024 * 1024)
                    except:
                        pass
        
        free_space = get_free_space()
        
        return jsonify({
            "status": "success",
            "total_downloads": total_downloads,
            "total_size_mb": round(total_size, 2),
            "free_space_gb": free_space,
            "download_dir": DEFAULT_DOWNLOAD_DIR
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/cleanup", methods=["POST"])
def cleanup():
    """Clean temporary files"""
    try:
        count = 0
        if os.path.exists(DEFAULT_DOWNLOAD_DIR):
            for file in os.listdir(DEFAULT_DOWNLOAD_DIR):
                if file.endswith(('.part', '.temp', '.ytdl', '.webm', '.m4a')):
                    try:
                        filepath = os.path.join(DEFAULT_DOWNLOAD_DIR, file)
                        os.remove(filepath)
                        count += 1
                    except:
                        continue
        
        return jsonify({
            "status": "success", 
            "message": f"Cleaned {count} temporary files"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/health-check")
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "free_space_gb": get_free_space(),
        "download_dir_exists": os.path.exists(DEFAULT_DOWNLOAD_DIR),
        "files_count": len([f for f in os.listdir(DEFAULT_DOWNLOAD_DIR) if f.endswith('.mp3')]) if os.path.exists(DEFAULT_DOWNLOAD_DIR) else 0,
        "app": "YouTube MP3 Downloader v3.0",
        "hosting": "Render.com"
    })

# ========== ERROR HANDLERS ==========
@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "error", "message": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    log_message(f"500 error: {e}")
    return jsonify({"status": "error", "message": "Internal server error"}), 500

# ========== STARTUP ==========
if __name__ == "__main__":
    print("=" * 60)
    print("🎵 YouTube MP3 Downloader - Render.com Version")
    print(f"📁 Directory: {DEFAULT_DOWNLOAD_DIR}")
    print(f"💾 Free space: {get_free_space()} GB")
    print(f"🚀 Using yt-dlp for real downloads")
    print("=" * 60)
    
    # Clear old data on startup
    download_progress.clear()
    active_downloads.clear()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
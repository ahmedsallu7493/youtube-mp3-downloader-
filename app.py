"""
YouTube MP3 Downloader - Enhanced Edition
Developer: Ahmed Sallu
PythonAnywhere Hosting Configuration
"""

import os
import sys
import shutil
import yt_dlp
import time
import re
import json
import uuid
import threading
import traceback
import subprocess
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, stream_with_context
from flask_cors import CORS
from functools import wraps

# ========== PYTHONANYWHERE CONFIGURATION ==========
# Detect if running on PythonAnywhere
IS_PYTHONANYWHERE = 'pythonanywhere' in os.environ.get('HOME', '').lower()

if IS_PYTHONANYWHERE:
    # PythonAnywhere specific configuration
    USERNAME = 'ahmedsallu'
    BASE_DIR = '/home/ahmedsallu/mysite'  # Source code location
    WORKING_DIR = '/home/ahmedsallu'  # Working directory from web app config
    
    # Change to working directory for file operations
    os.chdir(WORKING_DIR)
    
    # Set paths relative to working directory
    DOWNLOAD_DIR = os.path.join(WORKING_DIR, 'downloads')
    CONFIG_DIR = os.path.join(WORKING_DIR, 'youtube_app_data')
    
    # FFmpeg path
    FFMPEG_PATH = '/home/ahmedsallu/ffmpeg-static/ffmpeg'
    
    # Add project directory to Python path
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    
    print(f"✅ PythonAnywhere mode activated")
    print(f"   BASE_DIR: {BASE_DIR}")
    print(f"   WORKING_DIR: {WORKING_DIR}")
    print(f"   DOWNLOAD_DIR: {DOWNLOAD_DIR}")
    print(f"   FFMPEG_PATH: {FFMPEG_PATH}")
    
else:
    # Local development configuration
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    WORKING_DIR = BASE_DIR
    DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
    CONFIG_DIR = os.path.join(BASE_DIR, "app_data")
    FFMPEG_PATH = 'ffmpeg'
    print(f"✅ Local development mode")

# Developer information
DEVELOPER_NAME = "Ahmed Sallu"
DEVELOPER_EMAIL = "ahmedsallu7493@gmail.com"
DEVELOPER_GITHUB = "github.com/ahmedsallu7493"

# ========== FLASK APP SETUP ==========
app = Flask(__name__, 
    static_folder=os.path.join(BASE_DIR, 'static'),
    template_folder=os.path.join(BASE_DIR, 'templates')
)
CORS(app)

# Set secret key
app.secret_key = os.environ.get('SECRET_KEY', 'youtube-mp3-downloader-secret-key-2024')

# ========== PATHS AND FILES ==========
# Configuration files (stored in config directory)
FAILED_FILE = os.path.join(CONFIG_DIR, "failed_urls.txt")
SUCCESS_FILE = os.path.join(CONFIG_DIR, "success_urls.txt")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
LOG_FILE = os.path.join(CONFIG_DIR, "app.log")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
QUEUE_FILE = os.path.join(CONFIG_DIR, "queue.json")

# Create necessary directories
for directory in [DOWNLOAD_DIR, CONFIG_DIR]:
    os.makedirs(directory, exist_ok=True)

# Store active downloads
active_downloads = {}
download_progress = {}
download_queue = []
MAX_CONCURRENT_DOWNLOADS = 1
download_history = []

# ========== UTILITY FUNCTIONS ==========
def log_message(message, level="INFO"):
    """Log messages to file and console"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}\n"
    
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except:
        pass
    
    if IS_PYTHONANYWHERE:
        # Print to stderr for PythonAnywhere logs
        print(log_entry.strip(), file=sys.stderr)
    else:
        print(log_entry.strip())

def log_error(error_msg, exc_info=None):
    """Log errors with traceback"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [ERROR] {error_msg}\n"
    
    if exc_info:
        log_entry += f"Exception: {exc_info}\n"
        log_entry += f"Traceback: {traceback.format_exc()}\n"
    
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except:
        pass
    
    if IS_PYTHONANYWHERE:
        print(log_entry.strip(), file=sys.stderr)
    else:
        print(log_entry.strip())

def get_absolute_path(relative_path):
    """Get absolute path for file operations"""
    if IS_PYTHONANYWHERE:
        # For PythonAnywhere, use working directory
        return os.path.join(WORKING_DIR, relative_path)
    else:
        return os.path.join(BASE_DIR, relative_path)

def ffmpeg_available():
    """Check if FFmpeg is available"""
    try:
        if IS_PYTHONANYWHERE:
            # Check our static FFmpeg binary
            if os.path.exists(FFMPEG_PATH):
                result = subprocess.run([FFMPEG_PATH, '-version'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    log_message(f"FFmpeg found at: {FFMPEG_PATH}")
                    return True
            return False
        else:
            # Check system FFmpeg
            possible_paths = [
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
                '/bin/ffmpeg',
                shutil.which("ffmpeg")
            ]
            
            for path in possible_paths:
                if path and os.path.exists(path):
                    log_message(f"FFmpeg found at: {path}")
                    return True
            
            return False
    except Exception as e:
        log_error(f"Error checking FFmpeg: {e}")
        return False

def sanitize_url(url):
    """Sanitize and validate YouTube URL"""
    if not url:
        return None
    
    url = url.strip()
    
    # Remove tracking parameters
    url = re.sub(r'&t=\d+s', '', url)
    url = re.sub(r'&feature=share', '', url)
    
    # Validate YouTube URL
    youtube_patterns = [
        r'^https?://(www\.)?youtube\.com/watch\?v=[\w-]+',
        r'^https?://youtu\.be/[\w-]+',
        r'^https?://(www\.)?youtube\.com/playlist\?list=[\w-]+',
        r'^https?://(www\.)?youtube\.com/shorts/[\w-]+'
    ]
    
    for pattern in youtube_patterns:
        if re.match(pattern, url):
            return url
    
    return None

def save_to_history(url, title, filename, size_mb, status):
    """Save download to history"""
    try:
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "url": url,
            "title": title,
            "filename": filename,
            "size_mb": size_mb,
            "status": status
        }
        
        # Load existing history
        history = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except:
                history = []
        
        # Add new entry (keep last 100 entries)
        history.append(history_entry)
        if len(history) > 100:
            history = history[-100:]
        
        # Save history
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2)
            
    except Exception as e:
        log_error(f"Error saving to history: {e}")

def get_video_info(url):
    """Get video information without downloading"""
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_js_warning": True,
            "extract_flat": False,
            "ignoreerrors": False,
            "socket_timeout": 10,
            "retries": 1,
            "noprogress": True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Calculate duration in minutes:seconds
            duration_seconds = info.get('duration', 0)
            if duration_seconds:
                minutes = duration_seconds // 60
                seconds = duration_seconds % 60
                duration = f"{minutes}:{seconds:02d}"
            else:
                duration = "Unknown"
            
            # Check PythonAnywhere limits
            warning = ""
            if IS_PYTHONANYWHERE:
                if duration_seconds > 1800:  # 30 minutes
                    warning = "Video is longer than 30 minutes (PythonAnywhere free tier limit)"
                elif duration_seconds > 600:  # 10 minutes
                    warning = "Video is long, download may be slow on free tier"
            
            return {
                "status": "success",
                "title": info.get('title', 'Unknown'),
                "duration": duration,
                "duration_seconds": duration_seconds,
                "thumbnail": info.get('thumbnail', ''),
                "uploader": info.get('uploader', 'Unknown'),
                "view_count": info.get('view_count', 0),
                "like_count": info.get('like_count', 0),
                "is_live": info.get('is_live', False),
                "age_limit": info.get('age_limit', 0),
                "warning": warning
            }
    except Exception as e:
        log_error(f"Error getting video info: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

def check_disk_space():
    """Check available disk space"""
    try:
        if IS_PYTHONANYWHERE:
            # PythonAnywhere specific disk check
            stat = shutil.disk_usage(WORKING_DIR)
        else:
            stat = shutil.disk_usage(DOWNLOAD_DIR)
        
        free_gb = stat.free / (1024**3)
        return free_gb
    except Exception as e:
        log_error(f"Error checking disk space: {e}")
        return 0.5

def clean_filename(filename):
    """Clean filename for safe saving"""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = re.sub(r'\s+', ' ', filename)
    filename = filename.strip()
    
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:95] + ext
    
    return filename

def load_settings():
    """Load application settings"""
    default_settings = {
        "max_file_size_mb": 30 if IS_PYTHONANYWHERE else 50,
        "max_downloads_per_day": 10,
        "download_dir": DOWNLOAD_DIR,
        "audio_quality": "128" if IS_PYTHONANYWHERE else "192",
        "enable_progress": True,
        "auto_cleanup_days": 1 if IS_PYTHONANYWHERE else 7,
        "enable_history": True,
        "default_location": "downloads",
        "enable_thumbnail": True,
        "enable_queue": True
    }
    
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                user_settings = json.load(f)
                default_settings.update(user_settings)
    except Exception as e:
        log_error(f"Error loading settings: {e}")
    
    return default_settings

def save_settings(settings):
    """Save application settings"""
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        log_error(f"Error saving settings: {e}")
        return False

def get_download_stats():
    """Get download statistics"""
    stats = {
        "total_downloads": 0,
        "total_size_mb": 0,
        "files": [],
        "ffmpeg_available": ffmpeg_available(),
        "download_dir": DOWNLOAD_DIR,
        "developer": {
            "name": DEVELOPER_NAME,
            "email": DEVELOPER_EMAIL,
            "github": DEVELOPER_GITHUB
        }
    }
    
    try:
        if os.path.exists(DOWNLOAD_DIR):
            for file in os.listdir(DOWNLOAD_DIR):
                if file.endswith('.mp3'):
                    filepath = os.path.join(DOWNLOAD_DIR, file)
                    if os.path.isfile(filepath):
                        try:
                            size = os.path.getsize(filepath) / (1024 * 1024)
                            modified = os.path.getmtime(filepath)
                            stats["total_downloads"] += 1
                            stats["total_size_mb"] += size
                            stats["files"].append({
                                "name": file,
                                "size_mb": round(size, 2),
                                "path": filepath,
                                "modified": datetime.fromtimestamp(modified).strftime("%Y-%m-%d %H:%M")
                            })
                        except:
                            continue
    except Exception as e:
        log_error(f"Error getting stats: {e}")
    
    return stats

def auto_cleanup():
    """Automatically clean old files (PythonAnywhere specific)"""
    if not IS_PYTHONANYWHERE:
        return 0
    
    try:
        settings = load_settings()
        max_age_days = settings.get("auto_cleanup_days", 1)
        max_files = 15  # Keep only 15 newest files on free tier
        
        if not os.path.exists(DOWNLOAD_DIR):
            return 0
        
        deleted_count = 0
        now = time.time()
        cutoff = now - (max_age_days * 24 * 60 * 60)
        
        # Get all MP3 files sorted by modification time (oldest first)
        mp3_files = []
        for file in os.listdir(DOWNLOAD_DIR):
            if file.endswith('.mp3'):
                filepath = os.path.join(DOWNLOAD_DIR, file)
                if os.path.isfile(filepath):
                    mtime = os.path.getmtime(filepath)
                    mp3_files.append((mtime, filepath, file))
        
        # Sort by modification time
        mp3_files.sort()
        
        # Delete files older than cutoff
        for mtime, filepath, filename in mp3_files:
            if mtime < cutoff:
                try:
                    os.remove(filepath)
                    deleted_count += 1
                    log_message(f"Auto-cleaned: {filename}")
                except:
                    continue
        
        # If still too many files, delete oldest ones
        remaining_files = len(mp3_files) - deleted_count
        if remaining_files > max_files:
            to_delete = remaining_files - max_files
            for i in range(to_delete):
                try:
                    mtime, filepath, filename = mp3_files[i]
                    os.remove(filepath)
                    deleted_count += 1
                    log_message(f"Auto-cleaned (limit): {filename}")
                except:
                    continue
        
        if deleted_count > 0:
            log_message(f"Auto-cleanup completed: {deleted_count} files removed")
        
        return deleted_count
    except Exception as e:
        log_error(f"Auto-cleanup error: {e}")
        return 0

def check_pythonanywhere_limits(video_info):
    """Check PythonAnywhere free tier limits"""
    if not IS_PYTHONANYWHERE:
        return True
    
    # Check duration (max 10 minutes for free tier to be safe)
    duration_seconds = video_info.get('duration_seconds', 0)
    if duration_seconds > 600:  # 10 minutes
        raise Exception(f"Video too long ({duration_seconds//60}min). Max 10 minutes for PythonAnywhere free tier.")
    
    # Check if live stream
    if video_info.get('is_live', False):
        raise Exception("Live streams cannot be downloaded.")
    
    # Check age restriction
    if video_info.get('age_limit', 0) > 0:
        raise Exception("Age-restricted videos cannot be downloaded.")
    
    return True

def download_audio(url, download_dir=None, download_id=None, quality="128"):
    """Download audio with progress tracking"""
    if download_dir is None:
        settings = load_settings()
        download_dir = settings.get("download_dir", DOWNLOAD_DIR)
    
    # Check FFmpeg availability
    if not ffmpeg_available():
        raise Exception("FFmpeg is not available. This is required for MP3 conversion.")
    
    # Check disk space
    free_space = check_disk_space()
    if free_space < 0.1:  # Less than 100MB
        raise Exception(f"Insufficient disk space. Only {free_space:.2f}GB free.")
    
    log_message(f"Starting download for URL: {url[:100]}...")
    log_message(f"Quality: {quality}kbps")
    log_message(f"Download directory: {download_dir}")
    
    # Initialize progress tracking
    if download_id:
        download_progress[download_id] = {
            "status": "starting",
            "percent": 0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "speed": "0 B/s",
            "eta": "Unknown",
            "filename": "",
            "title": ""
        }
    
    # Progress hook function
    def progress_hook(d):
        if download_id and download_id in download_progress:
            if d['status'] == 'downloading':
                download_progress[download_id].update({
                    "status": "downloading",
                    "percent": d.get('_percent_str', '0%').strip('%'),
                    "downloaded_bytes": d.get('downloaded_bytes', 0),
                    "total_bytes": d.get('total_bytes', 0),
                    "speed": d.get('_speed_str', '0 B/s'),
                    "eta": d.get('_eta_str', 'Unknown'),
                    "filename": d.get('filename', ''),
                    "title": d.get('info_dict', {}).get('title', '')
                })
            elif d['status'] == 'finished':
                download_progress[download_id].update({
                    "status": "converting",
                    "percent": "100",
                    "filename": d.get('filename', '')
                })
    
    # YouTubeDL options optimized for PythonAnywhere
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nooverwrites": True,
        "socket_timeout": 30,
        "retries": 3,
        "skip_js_warning": True,
        "progress_hooks": [progress_hook],
        "max_filesize": 30 * 1024 * 1024,  # 30MB limit for free tier
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        },
        "noprogress": True,
        "extract_flat": False,
        "ignoreerrors": False,
        "no_color": True,
    }
    
    # Add FFmpeg location for PythonAnywhere
    if IS_PYTHONANYWHERE and os.path.exists(FFMPEG_PATH):
        ydl_opts["ffmpeg_location"] = FFMPEG_PATH
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info first
            info = ydl.extract_info(url, download=False)
            
            # Check PythonAnywhere limits
            check_pythonanywhere_limits({
                "duration_seconds": info.get('duration', 0),
                "is_live": info.get('is_live', False),
                "age_limit": info.get('age_limit', 0)
            })
            
            title = info.get("title", "audio")
            clean_title = clean_filename(title)
            mp3_path = os.path.join(download_dir, f"{clean_title}.mp3")
            
            if download_id:
                download_progress[download_id]["title"] = title
            
            # Check if already exists
            if os.path.exists(mp3_path):
                size_mb = os.path.getsize(mp3_path) / (1024 * 1024)
                log_message(f"File already exists: {clean_title}")
                if download_id:
                    download_progress[download_id].update({
                        "status": "completed",
                        "percent": "100",
                        "filename": mp3_path,
                        "message": f"Already downloaded: {clean_title} ({size_mb:.1f}MB)"
                    })
                return {
                    "status": "exists",
                    "message": f"Already downloaded: {clean_title} ({size_mb:.1f}MB)",
                    "filename": clean_title + ".mp3",
                    "path": mp3_path,
                    "size_mb": size_mb,
                    "title": title,
                    "quality": quality
                }
            
            log_message(f"Downloading: {title}")
            if download_id:
                download_progress[download_id].update({
                    "status": "downloading",
                    "percent": "0"
                })
            
            # Add small delay for PythonAnywhere rate limiting
            if IS_PYTHONANYWHERE:
                time.sleep(1)
            
            ydl.download([url])
            
            # Wait for file system
            time.sleep(2)
            
            # Look for the downloaded file
            for ext in ['.mp3', '.webm', '.m4a']:
                test_path = os.path.join(download_dir, f"{clean_title}{ext}")
                if os.path.exists(test_path):
                    size_mb = os.path.getsize(test_path) / (1024 * 1024)
                    log_message(f"Download completed: {clean_title}{ext} ({size_mb:.1f}MB)")
                    
                    # Save to history
                    save_to_history(url, title, clean_title + ext, size_mb, "success")
                    
                    if download_id:
                        download_progress[download_id].update({
                            "status": "completed",
                            "percent": "100",
                            "filename": test_path,
                            "message": f"Downloaded: {clean_title}{ext} ({size_mb:.1f}MB)"
                        })
                    return {
                        "status": "success",
                        "message": f"Downloaded: {clean_title}{ext} ({size_mb:.1f}MB)",
                        "filename": clean_title + ext,
                        "path": test_path,
                        "size_mb": size_mb,
                        "title": title,
                        "quality": quality,
                        "download_url": f"/download-file/{download_id}" if download_id else None
                    }
            
            # Save failed attempt to history
            save_to_history(url, title, "", 0, "failed")
            raise Exception("Download completed but file not found")
                
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        log_error(f"yt-dlp download error: {error_msg}")
        
        # User-friendly error messages
        if "Private video" in error_msg:
            error_msg = "This video is private or requires login."
        elif "Video unavailable" in error_msg:
            error_msg = "This video is unavailable in your country or has been removed."
        elif "Sign in to confirm" in error_msg:
            error_msg = "This video requires age verification."
        elif "too many requests" in error_msg.lower():
            error_msg = "Too many requests. Please wait a few minutes."
        
        # Save failed attempt to history
        save_to_history(url, "", "", 0, "failed")
        raise Exception(error_msg)
            
    except Exception as e:
        error_msg = str(e)
        log_error(f"Download error: {error_msg}", e)
        
        # Save failed attempt to history
        save_to_history(url, "", "", 0, "failed")
        
        if download_id:
            download_progress[download_id].update({
                "status": "error",
                "message": error_msg[:200]
            })
        
        raise

# ========== FLASK ROUTES ==========
@app.route("/")
def home():
    """Home page"""
    stats = get_download_stats()
    free_space = check_disk_space()
    settings = load_settings()
    
    # Auto-cleanup on home page load
    if IS_PYTHONANYWHERE:
        auto_cleanup()
    
    return render_template("index.html", 
                         stats=stats,
                         free_space=round(free_space, 2),
                         settings=settings,
                         is_pythonanywhere=IS_PYTHONANYWHERE,
                         ffmpeg_available=stats["ffmpeg_available"],
                         developer=stats["developer"])

@app.route("/check-url", methods=["POST"])
def check_url_endpoint():
    """Check URL and get video info"""
    try:
        data = request.get_json()
        url = data.get("url", "").strip()
        
        if not url:
            return jsonify({"status": "error", "message": "No URL provided"}), 400
        
        # Sanitize and validate URL
        sanitized_url = sanitize_url(url)
        if not sanitized_url:
            return jsonify({"status": "error", "message": "Invalid YouTube URL"}), 400
        
        # Get video info
        info = get_video_info(sanitized_url)
        
        if info["status"] == "error":
            return jsonify({"status": "error", "message": info["message"]}), 400
        
        return jsonify({"status": "success", "info": info})
        
    except Exception as e:
        log_error(f"URL check error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download", methods=["POST"])
def download():
    """Download endpoint"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        url = data.get("url", "").strip()
        quality = data.get("quality", "128")  # Default to 128 for PythonAnywhere
        
        if not url:
            return jsonify({"status": "error", "message": "Please enter a YouTube URL"}), 400
        
        # Sanitize and validate URL
        sanitized_url = sanitize_url(url)
        if not sanitized_url:
            return jsonify({"status": "error", "message": "Please enter a valid YouTube URL"}), 400
        
        # Check for ongoing downloads
        if len(active_downloads) >= MAX_CONCURRENT_DOWNLOADS:
            return jsonify({
                "status": "error", 
                "message": "Please wait for current download to complete",
                "queue_position": len(download_queue) + 1
            }), 429
        
        # Generate download ID
        download_id = str(uuid.uuid4())
        
        # Start download in background thread
        def download_thread():
            try:
                result = download_audio(sanitized_url, None, download_id, quality)
                active_downloads[download_id] = result
                log_message(f"Download completed successfully: {download_id}")
            except Exception as e:
                active_downloads[download_id] = {"status": "error", "message": str(e)}
                log_error(f"Download failed: {str(e)}")
        
        thread = threading.Thread(target=download_thread)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "status": "started",
            "message": "Download started successfully",
            "download_id": download_id,
            "check_progress": f"/progress/{download_id}",
            "download_url": f"/download-file/{download_id}"
        })
        
    except Exception as e:
        error_msg = str(e)
        log_error(f"Download route error: {error_msg}", e)
        return jsonify({"status": "error", "message": error_msg}), 500

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
            "message": "Download not found or expired"
        }), 404

@app.route("/download-file/<download_id>")
def download_file(download_id):
    """Serve downloaded file"""
    if download_id in active_downloads:
        result = active_downloads[download_id]
        if result.get("status") in ["success", "exists"] and "path" in result:
            filepath = result["path"]
            filename = result.get("filename", os.path.basename(filepath))
            
            if not os.path.exists(filepath):
                return jsonify({"status": "error", "message": "File not found"}), 404
            
            try:
                return send_file(
                    filepath,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='audio/mpeg'
                )
            except Exception as e:
                log_error(f"Error sending file: {e}")
                return jsonify({"status": "error", "message": "Error downloading file"}), 500
    
    return jsonify({"status": "error", "message": "File not found"}), 404

@app.route("/get-history")
def get_history_endpoint():
    """Get download history"""
    try:
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        
        # Return last 20 entries
        return jsonify({
            "status": "success",
            "history": history[-20:][::-1],  # Reverse to show newest first
            "total": len(history)
        })
    except Exception as e:
        log_error(f"Error getting history: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/clear-history", methods=["POST"])
def clear_history():
    """Clear download history"""
    try:
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
        
        # Recreate empty file
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
        
        return jsonify({"status": "success", "message": "History cleared"})
    except Exception as e:
        log_error(f"Error clearing history: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/list-files")
def list_files():
    """List downloaded files"""
    try:
        settings = load_settings()
        download_dir = settings.get("download_dir", DOWNLOAD_DIR)
        
        files = []
        if os.path.exists(download_dir):
            for file in sorted(os.listdir(download_dir), 
                             key=lambda x: os.path.getmtime(os.path.join(download_dir, x)), 
                             reverse=True):
                if file.endswith('.mp3'):
                    filepath = os.path.join(download_dir, file)
                    size = os.path.getsize(filepath) / (1024 * 1024)
                    modified = os.path.getmtime(filepath)
                    files.append({
                        "name": file,
                        "size_mb": round(size, 2),
                        "path": filepath,
                        "modified": datetime.fromtimestamp(modified).strftime("%Y-%m-%d %H:%M")
                    })
        
        return jsonify({
            "status": "success",
            "files": files[:10],  # Limit to 10 files for PythonAnywhere
            "count": len(files),
            "total_size_mb": round(sum(f["size_mb"] for f in files), 2)
        })
    except Exception as e:
        log_error(f"List files error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/delete-file", methods=["POST"])
def delete_file():
    """Delete downloaded file"""
    try:
        data = request.get_json()
        filename = data.get("filename", "")
        
        if not filename:
            return jsonify({"status": "error", "message": "No filename provided"}), 400
        
        settings = load_settings()
        download_dir = settings.get("download_dir", DOWNLOAD_DIR)
        filepath = os.path.join(download_dir, filename)
        
        # Security check
        if not filepath.startswith(download_dir) or ".." in filename:
            return jsonify({"status": "error", "message": "Invalid filename"}), 400
        
        if os.path.exists(filepath):
            os.remove(filepath)
            log_message(f"Deleted file: {filename}")
            return jsonify({"status": "success", "message": f"Deleted: {filename}"})
        else:
            return jsonify({"status": "error", "message": "File not found"}), 404
            
    except Exception as e:
        log_error(f"Error deleting file: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/cleanup", methods=["POST"])
def cleanup():
    """Clean up temporary files"""
    try:
        settings = load_settings()
        download_dir = settings.get("download_dir", DOWNLOAD_DIR)
        
        count = 0
        if os.path.exists(download_dir):
            for file in os.listdir(download_dir):
                if file.endswith(('.part', '.ytdl', '.temp', '.webm.part')):
                    try:
                        filepath = os.path.join(download_dir, file)
                        os.remove(filepath)
                        count += 1
                        log_message(f"Cleaned: {file}")
                    except:
                        continue
        
        log_message(f"Cleanup completed: {count} files removed")
        return jsonify({"status": "success", "message": f"Cleaned {count} temporary files"})
    except Exception as e:
        log_error(f"Cleanup error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/stats")
def stats():
    """Get download statistics"""
    try:
        settings = load_settings()
        download_dir = settings.get("download_dir", DOWNLOAD_DIR)
        stats_data = get_download_stats()
        free_space = check_disk_space()
        
        return jsonify({
            "status": "success",
            "stats": stats_data,
            "free_space_gb": round(free_space, 2),
            "download_dir": download_dir,
            "ffmpeg_available": stats_data["ffmpeg_available"],
            "pythonanywhere": IS_PYTHONANYWHERE
        })
    except Exception as e:
        log_error(f"Stats error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/health-check")
def health_check():
    """Health check endpoint"""
    try:
        free_space = check_disk_space()
        stats_data = get_download_stats()
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "platform": "pythonanywhere" if IS_PYTHONANYWHERE else "local",
            "disk_space_gb": round(free_space, 2),
            "ffmpeg_available": stats_data["ffmpeg_available"],
            "download_dir_exists": os.path.exists(DOWNLOAD_DIR),
            "files_count": stats_data["total_downloads"],
            "app_version": "2.1.0",
            "developer": DEVELOPER_NAME,
            "limits": {
                "max_duration_minutes": 10 if IS_PYTHONANYWHERE else 30,
                "max_file_size_mb": 30 if IS_PYTHONANYWHERE else 50,
                "max_daily_downloads": 10,
                "cpu_timeout_seconds": 100 if IS_PYTHONANYWHERE else 300
            }
        })
    except Exception as e:
        log_error(f"Health check error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/test-config")
def test_config():
    """Test configuration endpoint"""
    return jsonify({
        'status': 'ok',
        'pythonanywhere': IS_PYTHONANYWHERE,
        'username': USERNAME if IS_PYTHONANYWHERE else 'local',
        'base_dir': BASE_DIR,
        'working_dir': WORKING_DIR,
        'current_directory': os.getcwd(),
        'download_dir': DOWNLOAD_DIR,
        'config_dir': CONFIG_DIR,
        'ffmpeg_path': FFMPEG_PATH,
        'ffmpeg_exists': os.path.exists(FFMPEG_PATH) if IS_PYTHONANYWHERE else True,
        'files_in_base': os.listdir(BASE_DIR) if os.path.exists(BASE_DIR) else [],
        'files_in_working': os.listdir(WORKING_DIR) if os.path.exists(WORKING_DIR) else [],
        'python_version': sys.version,
        'flask_imported': 'Flask' in sys.modules
    })

# ========== ERROR HANDLERS ==========
@app.errorhandler(404)
def not_found(e):
    log_error(f"404 error: {e}", e)
    return jsonify({"status": "error", "message": "Resource not found"}), 404

@app.errorhandler(500)
def server_error(e):
    log_error(f"500 error: {e}", e)
    return jsonify({"status": "error", "message": "Internal server error"}), 500

@app.errorhandler(429)
def too_many_requests(e):
    return jsonify({"status": "error", "message": "Too many requests. Please wait."}), 429

@app.errorhandler(413)
def request_too_large(e):
    return jsonify({"status": "error", "message": "File too large. Max 30MB for free tier."}), 413

# ========== SECURITY HEADERS ==========
@app.after_request
def add_security_headers(response):
    """Add security headers for production"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    if IS_PYTHONANYWHERE:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# ========== APPLICATION STARTUP ==========
if __name__ == "__main__":
    print("=" * 80)
    print("🎵 YouTube MP3 Downloader - Enhanced Edition")
    print("=" * 80)
    print(f"👨‍💻 Developer: {DEVELOPER_NAME}")
    print(f"📧 Contact: {DEVELOPER_EMAIL}")
    print(f"🌐 GitHub: {DEVELOPER_GITHUB}")
    print("=" * 80)
    
    # System information
    print(f"📁 Base Directory: {BASE_DIR}")
    print(f"📂 Working Directory: {WORKING_DIR}")
    print(f"💾 Download Directory: {DOWNLOAD_DIR}")
    print(f"⚙️ Config Directory: {CONFIG_DIR}")
    print(f"🌍 PythonAnywhere: {IS_PYTHONANYWHERE}")
    print(f"🎬 FFmpeg Available: {ffmpeg_available()}")
    
    # Load settings
    settings = load_settings()
    print(f"📍 Current Download Directory: {DOWNLOAD_DIR}")
    print(f"💾 Free Disk Space: {check_disk_space():.2f} GB")
    
    # Run auto-cleanup on startup
    deleted = auto_cleanup()
    if deleted > 0:
        print(f"🧹 Auto-cleanup: {deleted} files removed")
    
    if IS_PYTHONANYWHERE:
        print("\n⚠️  PythonAnywhere Free Tier Configuration:")
        print("   • Max video duration: 10 minutes")
        print("   • Max file size: 30MB")
        print("   • Auto-cleanup: Enabled (keeps 15 newest files)")
        print("   • Default quality: 128kbps")
        print("   • Rate limiting: Enabled")
    
    # Test YouTube extraction
    try:
        print("\n🔍 Testing YouTube extraction...")
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_js_warning": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ", download=False)
            print(f"✅ YouTube extractor working!")
            print(f"   Title: {info.get('title', 'Unknown')[:50]}...")
    except Exception as e:
        print(f"❌ YouTube extractor test failed: {e}")
    
    stats = get_download_stats()
    print(f"\n📊 Existing Downloads: {stats['total_downloads']} files ({stats['total_size_mb']:.1f}MB)")
    print("=" * 80)
    
    # Start server (only for local development)
    if not IS_PYTHONANYWHERE:
        print("\n💻 Starting development server...")
        print("   Open: http://localhost:5000")
        print("=" * 80)
        
        app.run(
            debug=True,
            port=5000,
            host='0.0.0.0',
            threaded=True,
            use_reloader=True
        )
    else:
        print("\n✅ PythonAnywhere setup complete!")
        print(f"   Your app will be available at: https://ahmedsallu.pythonanywhere.com")
        print("   Make sure to:")
        print("   1. Update WSGI file")
        print("   2. Configure static files")
        print("   3. Reload web app")
        print("=" * 80)
"""
YouTube MP3 Downloader - Enhanced Edition
Developer: Ahmed Faiyazahed Sallu
Email:sallua543@gmail.com
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

# ========== CONFIGURATION ==========
DEVELOPER_NAME = "Ahmed F.Sallu"
DEVELOPER_EMAIL = "sallua543@gmail.com"
DEVELOPER_GITHUB = "[github.com/ahmedsallu7493]"


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_PYTHONANYWHERE = 'pythonanywhere' in os.environ.get('HOME', '').lower()

app = Flask(__name__, 
    static_folder=os.path.join(BASE_DIR, 'static'),
    template_folder=os.path.join(BASE_DIR, 'templates')
)
CORS(app)

# ========== STORAGE CONFIGURATION ==========
if IS_PYTHONANYWHERE:
    USERNAME = os.environ.get('USER', 'youtube_downloader_user')
    STORAGE_BASE = os.path.join('/home', USERNAME)
    DEFAULT_DOWNLOAD_DIR = os.path.join(STORAGE_BASE, 'youtube_downloads')
    CONFIG_DIR = os.path.join(STORAGE_BASE, 'youtube_app_data')
else:
    DEFAULT_DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
    CONFIG_DIR = os.path.join(BASE_DIR, "app_data")

# Configuration files
FAILED_FILE = os.path.join(CONFIG_DIR, "failed_urls.txt")
SUCCESS_FILE = os.path.join(CONFIG_DIR, "success_urls.txt")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
LOG_FILE = os.path.join(CONFIG_DIR, "app.log")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
QUEUE_FILE = os.path.join(CONFIG_DIR, "queue.json")

# Create necessary directories
for directory in [DEFAULT_DOWNLOAD_DIR, CONFIG_DIR]:
    os.makedirs(directory, exist_ok=True)

# Store active downloads
active_downloads = {}
download_progress = {}
download_queue = []
MAX_CONCURRENT_DOWNLOADS = 1
download_history = []

# ========== UTILITY FUNCTIONS ==========
def log_message(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}\n"
    
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except:
        pass
    
    print(log_entry.strip())

def log_error(error_msg, exc_info=None):
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
    
    print(log_entry.strip())

def ffmpeg_available():
    try:
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
            "retries": 1
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
                "age_limit": info.get('age_limit', 0)
            }
    except Exception as e:
        log_error(f"Error getting video info: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

def check_disk_space(download_dir=None):
    if download_dir is None:
        settings = load_settings()
        download_dir = settings.get("download_dir", DEFAULT_DOWNLOAD_DIR)
    
    try:
        stat = shutil.disk_usage(download_dir)
        free_gb = stat.free / (1024**3)
        return free_gb
    except Exception as e:
        log_error(f"Error checking disk space: {e}")
        return 0.5

def clean_filename(filename):
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = re.sub(r'\s+', ' ', filename)
    filename = filename.strip()
    
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:95] + ext
    
    return filename

def load_settings():
    default_settings = {
        "max_file_size_mb": 50,
        "max_downloads_per_day": 10,
        "download_dir": DEFAULT_DOWNLOAD_DIR,
        "audio_quality": "192",
        "enable_progress": True,
        "auto_cleanup_days": 7,
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
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        log_error(f"Error saving settings: {e}")
        return False

def get_download_stats(download_dir=None):
    if download_dir is None:
        settings = load_settings()
        download_dir = settings.get("download_dir", DEFAULT_DOWNLOAD_DIR)
    
    stats = {
        "total_downloads": 0,
        "total_size_mb": 0,
        "files": [],
        "ffmpeg_available": ffmpeg_available(),
        "download_dir": download_dir,
        "developer": {
            "name": DEVELOPER_NAME,
            "email": DEVELOPER_EMAIL,
            "github": DEVELOPER_GITHUB
        }
    }
    
    try:
        if os.path.exists(download_dir):
            for file in os.listdir(download_dir):
                if file.endswith('.mp3'):
                    filepath = os.path.join(download_dir, file)
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
    """Automatically clean old files"""
    try:
        settings = load_settings()
        download_dir = settings.get("download_dir", DEFAULT_DOWNLOAD_DIR)
        max_age_days = settings.get("auto_cleanup_days", 7)
        
        if not os.path.exists(download_dir):
            return 0
        
        deleted_count = 0
        now = time.time()
        cutoff = now - (max_age_days * 24 * 60 * 60)
        
        for file in os.listdir(download_dir):
            if file.endswith('.mp3'):
                filepath = os.path.join(download_dir, file)
                if os.path.isfile(filepath):
                    try:
                        if os.path.getmtime(filepath) < cutoff:
                            os.remove(filepath)
                            deleted_count += 1
                            log_message(f"Auto-cleaned: {file}")
                    except:
                        continue
        
        if deleted_count > 0:
            log_message(f"Auto-cleanup completed: {deleted_count} files removed")
        
        return deleted_count
    except Exception as e:
        log_error(f"Auto-cleanup error: {e}")
        return 0

def download_audio(url, download_dir=None, download_id=None, quality="192"):
    """Download audio with progress tracking"""
    if download_dir is None:
        settings = load_settings()
        download_dir = settings.get("download_dir", DEFAULT_DOWNLOAD_DIR)
    
    if not ffmpeg_available():
        raise Exception("FFmpeg is not available. This is required for MP3 conversion.")
    
    # Check disk space
    free_space = check_disk_space(download_dir)
    if free_space < 0.1:
        raise Exception(f"Insufficient disk space. Only {free_space:.2f}GB free.")
    
    log_message(f"Starting download for URL: {url[:100]}...")
    log_message(f"Quality: {quality}kbps")
    
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
    
    # YouTubeDL options
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
        "max_filesize": 50 * 1024 * 1024,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info first
            info = ydl.extract_info(url, download=False)
            
            # Check for age-restricted content
            if info.get('age_limit', 0) > 0:
                raise Exception("This video is age-restricted and cannot be downloaded.")
            
            # Check if live stream
            if info.get('is_live', False):
                raise Exception("Live streams cannot be downloaded.")
            
            # Check duration (limit to 30 minutes for free tier)
            if IS_PYTHONANYWHERE and info.get('duration', 0) > 1800:
                raise Exception("Video is too long (max 30 minutes for free tier).")
            
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
            
            ydl.download([url])
            
            # Wait for file system
            time.sleep(2)
            
            if os.path.exists(mp3_path):
                size_mb = os.path.getsize(mp3_path) / (1024 * 1024)
                log_message(f"Download completed: {clean_title} ({size_mb:.1f}MB)")
                
                # Save to history
                save_to_history(url, title, clean_title + ".mp3", size_mb, "success")
                
                if download_id:
                    download_progress[download_id].update({
                        "status": "completed",
                        "percent": "100",
                        "filename": mp3_path,
                        "message": f"Downloaded: {clean_title} ({size_mb:.1f}MB)"
                    })
                return {
                    "status": "success",
                    "message": f"Downloaded: {clean_title} ({size_mb:.1f}MB)",
                    "filename": clean_title + ".mp3",
                    "path": mp3_path,
                    "size_mb": size_mb,
                    "title": title,
                    "quality": quality,
                    "download_url": f"/download-file/{download_id}" if download_id else None
                }
            else:
                # Try to find file
                for ext in ['.mp3', '.webm', '.m4a']:
                    test_path = os.path.join(download_dir, f"{clean_title}{ext}")
                    if os.path.exists(test_path):
                        size_mb = os.path.getsize(test_path) / (1024 * 1024)
                        log_message(f"Found as {ext}: {clean_title}")
                        
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
        
        # Check for PythonAnywhere limits
        if IS_PYTHONANYWHERE:
            if info["duration_seconds"] > 1800:  # 30 minutes
                info["warning"] = "Video is longer than 30 minutes (free tier limit)"
            elif info["duration_seconds"] > 600:  # 10 minutes
                info["warning"] = "Large video, download may take longer"
        
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
        quality = data.get("quality", "192")
        
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

@app.route("/batch-download", methods=["POST"])
def batch_download():
    """Batch download endpoint (max 3 URLs for free tier)"""
    try:
        data = request.get_json()
        urls = data.get("urls", [])
        quality = data.get("quality", "192")
        
        if not urls:
            return jsonify({"status": "error", "message": "No URLs provided"}), 400
        
        # Limit to 3 URLs for free tier
        if IS_PYTHONANYWHERE:
            urls = urls[:3]
        else:
            urls = urls[:5]
        
        # Validate and sanitize URLs
        valid_urls = []
        for url in urls:
            sanitized_url = sanitize_url(url.strip())
            if sanitized_url:
                valid_urls.append(sanitized_url)
        
        if not valid_urls:
            return jsonify({"status": "error", "message": "No valid YouTube URLs found"}), 400
        
        results = []
        for url in valid_urls:
            try:
                download_id = str(uuid.uuid4())
                
                # Start download in background
                def batch_download_thread(url=url, did=download_id):
                    try:
                        result = download_audio(url, None, did, quality)
                        active_downloads[did] = result
                    except Exception as e:
                        active_downloads[did] = {"status": "error", "message": str(e)}
                
                thread = threading.Thread(target=batch_download_thread)
                thread.daemon = True
                thread.start()
                
                results.append({
                    "url": url[:60] + "..." if len(url) > 60 else url,
                    "download_id": download_id,
                    "status": "queued"
                })
                
                # Small delay between starting downloads
                time.sleep(0.5)
                
            except Exception as e:
                results.append({
                    "url": url[:60] + "..." if len(url) > 60 else url,
                    "status": "error",
                    "message": str(e)
                })
        
        return jsonify({
            "status": "success",
            "message": f"Started {len(results)} download(s)",
            "results": results
        })
        
    except Exception as e:
        log_error(f"Batch download error: {e}")
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
        download_dir = settings.get("download_dir", DEFAULT_DOWNLOAD_DIR)
        
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
            "files": files[:15],
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
        download_dir = settings.get("download_dir", DEFAULT_DOWNLOAD_DIR)
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
        download_dir = settings.get("download_dir", DEFAULT_DOWNLOAD_DIR)
        
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
        download_dir = settings.get("download_dir", DEFAULT_DOWNLOAD_DIR)
        stats_data = get_download_stats(download_dir)
        free_space = check_disk_space(download_dir)
        
        return jsonify({
            "status": "success",
            "stats": stats_data,
            "free_space_gb": round(free_space, 2),
            "download_dir": download_dir,
            "ffmpeg_available": stats_data["ffmpeg_available"]
        })
    except Exception as e:
        log_error(f"Stats error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/settings", methods=["GET", "POST"])
def settings():
    """Get or update settings"""
    if request.method == "GET":
        settings_data = load_settings()
        return jsonify({"status": "success", "settings": settings_data})
    
    elif request.method == "POST":
        try:
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "message": "No data provided"}), 400
            
            current_settings = load_settings()
            current_settings.update(data)
            
            # Validate download directory
            if "download_dir" in data:
                new_dir = data["download_dir"].strip()
                if new_dir and os.path.exists(new_dir):
                    current_settings["download_dir"] = new_dir
                else:
                    return jsonify({"status": "error", "message": "Invalid download directory"}), 400
            
            save_settings(current_settings)
            return jsonify({"status": "success", "message": "Settings updated", "settings": current_settings})
            
        except Exception as e:
            log_error(f"Settings error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/health-check")
def health_check():
    """Health check endpoint"""
    try:
        settings = load_settings()
        download_dir = settings.get("download_dir", DEFAULT_DOWNLOAD_DIR)
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "disk_space_gb": round(check_disk_space(download_dir), 2),
            "ffmpeg_available": ffmpeg_available(),
            "download_dir_exists": os.path.exists(download_dir),
            "is_pythonanywhere": IS_PYTHONANYWHERE,
            "app_version": "2.1.0",
            "developer": DEVELOPER_NAME
        })
    except Exception as e:
        log_error(f"Health check error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

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

# ========== APPLICATION STARTUP ==========
if __name__ == "__main__":
    print("=" * 80)
    print("🎵 YouTube MP3 Downloader - Enhanced Edition")
    print("=" * 80)
    print(f"👨‍💻 Developer: {DEVELOPER_NAME}")
    print(f"📧 Contact: {DEVELOPER_EMAIL}")
    print("=" * 80)
    
    # System information
    print(f"📁 Base Directory: {BASE_DIR}")
    print(f"📂 Download Directory: {DEFAULT_DOWNLOAD_DIR}")
    print(f"⚙️ Config Directory: {CONFIG_DIR}")
    print(f"🌍 PythonAnywhere: {IS_PYTHONANYWHERE}")
    print(f"🎬 FFmpeg Available: {ffmpeg_available()}")
    
    # Load settings
    settings = load_settings()
    download_dir = settings.get("download_dir", DEFAULT_DOWNLOAD_DIR)
    print(f"📍 Current Download Directory: {download_dir}")
    print(f"💾 Free Disk Space: {check_disk_space(download_dir):.2f} GB")
    
    # Run auto-cleanup on startup
    deleted = auto_cleanup()
    if deleted > 0:
        print(f"🧹 Auto-cleanup: {deleted} files removed")
    
    if IS_PYTHONANYWHERE:
        print("\n⚠️  PythonAnywhere Free Tier Limitations:")
        print("   • 512MB RAM available")
        print("   • 500MB disk space total")
        print("   • 100 seconds CPU time per request")
        print("   • No background processes")
        print("\n💡 Optimized Features:")
        print("   • Max 30 minute videos")
        print("   • Batch downloads (max 3)")
        print("   • Auto-cleanup enabled")
    
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
    
    stats = get_download_stats(download_dir)
    print(f"\n📊 Existing Downloads: {stats['total_downloads']} files ({stats['total_size_mb']:.1f}MB)")
    print("=" * 80)
    
    # Start server
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
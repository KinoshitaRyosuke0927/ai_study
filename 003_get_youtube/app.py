import csv
import io
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
YOUTUBE_API_BASE = 'https://www.googleapis.com/youtube/v3'
MAX_ARCHIVES = 50
MAX_SCAN_VIDEOS = 500  # uploads から最大500件を走査してライブアーカイブを抽出

app = FastAPI(title='YouTube Live Archive Viewer')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


class ChannelRequest(BaseModel):
    channel_input: str


def youtube_get(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if not YOUTUBE_API_KEY:
        raise HTTPException(status_code=500, detail='環境変数 YOUTUBE_API_KEY が設定されていません。')

    full_params = dict(params)
    full_params['key'] = YOUTUBE_API_KEY
    resp = requests.get(f'{YOUTUBE_API_BASE}/{endpoint}', params=full_params, timeout=30)
    if resp.status_code != 200:
        try:
            detail = resp.json()
        except Exception:
            detail = {'message': resp.text}
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()


CHANNEL_ID_RE = re.compile(r'^UC[0-9A-Za-z_-]{22}$')


def extract_channel_hint(channel_input: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (channel_id, handle)
    """
    value = channel_input.strip()
    if not value:
        return None, None

    if CHANNEL_ID_RE.fullmatch(value):
        return value, None

    # @handle only
    if value.startswith('@'):
        return None, value[1:]

    # URL patterns
    m = re.search(r'youtube\.com/channel/([^/?#]+)', value)
    if m:
        cid = m.group(1)
        if CHANNEL_ID_RE.fullmatch(cid):
            return cid, None

    m = re.search(r'youtube\.com/@([^/?#]+)', value)
    if m:
        return None, m.group(1)

    return None, value.lstrip('@') if 'youtube.com' not in value else None


def resolve_channel(channel_input: str) -> Dict[str, Any]:
    channel_id, handle = extract_channel_hint(channel_input)

    if channel_id:
        data = youtube_get('channels', {
            'part': 'snippet,statistics,contentDetails',
            'id': channel_id,
            'maxResults': 1,
        })
    elif handle:
        # forHandle が使える場合を優先（@ プレフィックスが必要）
        data = youtube_get('channels', {
            'part': 'snippet,statistics,contentDetails',
            'forHandle': f'@{handle}',
            'maxResults': 1,
        })
        if not data.get('items'):
            # 保険として search でも試す
            search = youtube_get('search', {
                'part': 'snippet',
                'q': f'@{handle}',
                'type': 'channel',
                'maxResults': 1,
            })
            items = search.get('items', [])
            if not items:
                raise HTTPException(status_code=404, detail='チャンネルが見つかりませんでした。')
            cid = items[0]['id']['channelId']
            data = youtube_get('channels', {
                'part': 'snippet,statistics,contentDetails',
                'id': cid,
                'maxResults': 1,
            })
    else:
        raise HTTPException(status_code=400, detail='channel_id または YouTube のチャンネルURL / @handle を入力してください。')

    items = data.get('items', [])
    if not items:
        raise HTTPException(status_code=404, detail='チャンネルが見つかりませんでした。')
    return items[0]


PT_RE = re.compile(
    r'^P'
    r'(?:(?P<days>\d+)D)?'
    r'(?:T'
    r'(?:(?P<hours>\d+)H)?'
    r'(?:(?P<minutes>\d+)M)?'
    r'(?:(?P<seconds>\d+)S)?'
    r')?$'
)


def iso8601_duration_to_hms(value: str) -> str:
    if not value:
        return ''
    m = PT_RE.match(value)
    if not m:
        return value
    days = int(m.group('days') or 0)
    hours = int(m.group('hours') or 0) + days * 24
    minutes = int(m.group('minutes') or 0)
    seconds = int(m.group('seconds') or 0)
    if hours > 0:
        return f'{hours}:{minutes:02}:{seconds:02}'
    return f'{minutes}:{seconds:02}'


def format_duration_csv(iso_duration: str) -> str:
    """CSV用: 常に hh:mm:ss 形式で返す"""
    if not iso_duration:
        return '00:00:00'
    m = PT_RE.match(iso_duration)
    if not m:
        return '00:00:00'
    days = int(m.group('days') or 0)
    hours = int(m.group('hours') or 0) + days * 24
    minutes = int(m.group('minutes') or 0)
    seconds = int(m.group('seconds') or 0)
    return f'{hours:02}:{minutes:02}:{seconds:02}'


def format_date_csv(published_at: str) -> str:
    """ISO 8601 日付文字列を yyyy/mm/dd 形式に変換する"""
    if not published_at:
        return ''
    try:
        y, mo, d = published_at[:10].split('-')
        return f'{y}/{mo}/{d}'
    except Exception:
        return published_at


THUMB_ORDER = ['maxres', 'standard', 'high', 'medium', 'default']


def pick_thumbnail(thumbnails: Dict[str, Any]) -> str:
    for key in THUMB_ORDER:
        item = thumbnails.get(key)
        if item and item.get('url'):
            return item['url']
    return ''


def chunked(seq: List[str], size: int) -> List[List[str]]:
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def fetch_upload_video_ids(uploads_playlist_id: str, scan_limit: Optional[int] = MAX_SCAN_VIDEOS) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    next_page_token: Optional[str] = None

    while scan_limit is None or len(collected) < scan_limit:
        params: Dict[str, Any] = {
            'part': 'snippet,contentDetails',
            'playlistId': uploads_playlist_id,
            'maxResults': 50,
        }
        if next_page_token:
            params['pageToken'] = next_page_token

        data = youtube_get('playlistItems', params)
        for item in data.get('items', []):
            video_id = item.get('contentDetails', {}).get('videoId') or item.get('snippet', {}).get('resourceId', {}).get('videoId')
            if not video_id:
                continue
            collected.append({
                'video_id': video_id,
                'playlist_published_at': item.get('contentDetails', {}).get('videoPublishedAt') or item.get('snippet', {}).get('publishedAt'),
            })
            if scan_limit is not None and len(collected) >= scan_limit:
                break

        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break

    return collected



def fetch_video_details(video_ids: List[str]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for group in chunked(video_ids, 50):
        data = youtube_get('videos', {
            'part': 'snippet,contentDetails,statistics,liveStreamingDetails,status',
            'id': ','.join(group),
            'maxResults': 50,
        })
        results.extend(data.get('items', []))
    return results



def is_live_archive(video: Dict[str, Any]) -> bool:
    live = video.get('liveStreamingDetails') or {}
    snippet = video.get('snippet') or {}
    actual_start = live.get('actualStartTime')
    actual_end = live.get('actualEndTime')
    scheduled_start = live.get('scheduledStartTime')
    live_broadcast_content = snippet.get('liveBroadcastContent')

    # もっとも確実: 過去ライブとして開始/終了時刻が入っている
    if actual_start and actual_end:
        return True

    # 配信終了直後など actualEndTime 欠落を補う
    if actual_start and not actual_end:
        return True

    # scheduled があり、現在 live でも upcoming でもなく、公開動画として存在する場合も補助的に採用
    if scheduled_start and live_broadcast_content == 'none':
        return True

    return False



def normalize_channel(item: Dict[str, Any]) -> Dict[str, Any]:
    snippet = item.get('snippet', {})
    statistics = item.get('statistics', {})
    content_details = item.get('contentDetails', {})
    return {
        'channel_id': item.get('id', ''),
        'title': snippet.get('title', ''),
        'description': snippet.get('description', ''),
        'published_at': snippet.get('publishedAt', ''),
        'thumbnail_url': pick_thumbnail(snippet.get('thumbnails', {})),
        'subscriber_count': statistics.get('subscriberCount'),
        'view_count': statistics.get('viewCount'),
        'video_count': statistics.get('videoCount'),
        'uploads_playlist_id': content_details.get('relatedPlaylists', {}).get('uploads', ''),
    }



def normalize_video(video: Dict[str, Any]) -> Dict[str, Any]:
    snippet = video.get('snippet', {})
    content_details = video.get('contentDetails', {})
    statistics = video.get('statistics', {})
    return {
        'video_id': video.get('id', ''),
        'title': snippet.get('title', ''),
        'published_at': snippet.get('publishedAt', ''),
        'duration': iso8601_duration_to_hms(content_details.get('duration', '')),
        'view_count': statistics.get('viewCount', '0'),
        'thumbnail_url': pick_thumbnail(snippet.get('thumbnails', {})),
        'watch_url': f"https://www.youtube.com/watch?v={video.get('id', '')}",
    }


@app.post('/api/channel/live-archives')
def get_channel_live_archives(req: ChannelRequest):
    channel_item = resolve_channel(req.channel_input)
    channel = normalize_channel(channel_item)
    uploads_id = channel['uploads_playlist_id']
    if not uploads_id:
        raise HTTPException(status_code=404, detail='uploads プレイリストが取得できませんでした。')

    uploads = fetch_upload_video_ids(uploads_id, scan_limit=MAX_SCAN_VIDEOS)
    if not uploads:
        return {'channel': channel, 'videos': [], 'scanned_video_count': 0}

    details = fetch_video_details([x['video_id'] for x in uploads])

    # playlist順(新しい順)を維持するため map 化
    video_map = {item.get('id'): item for item in details}
    archives: List[Dict[str, Any]] = []

    for entry in uploads:
        video = video_map.get(entry['video_id'])
        if not video:
            continue
        if is_live_archive(video):
            archives.append(normalize_video(video))
        if len(archives) >= MAX_ARCHIVES:
            break

    return {
        'channel': channel,
        'videos': archives,
        'scanned_video_count': len(uploads),
    }


def fetch_category_map(hl: str = 'ja') -> Dict[str, str]:
    """videoCategories.list で取得したカテゴリIDと名称のマッピングを返す"""
    data = youtube_get('videoCategories', {
        'part': 'snippet',
        'regionCode': 'JP',
        'hl': hl,
    })
    return {
        item.get('id', ''): item.get('snippet', {}).get('title', '')
        for item in data.get('items', [])
    }


@app.post('/api/channel/all-videos-csv')
def download_all_videos_csv(req: ChannelRequest):
    channel_item = resolve_channel(req.channel_input)
    channel = normalize_channel(channel_item)
    uploads_id = channel['uploads_playlist_id']
    if not uploads_id:
        raise HTTPException(status_code=404, detail='uploads プレイリストが取得できませんでした。')

    uploads = fetch_upload_video_ids(uploads_id, scan_limit=None)
    if not uploads:
        raise HTTPException(status_code=404, detail='動画が見つかりませんでした。')

    details = fetch_video_details([x['video_id'] for x in uploads])
    video_map = {item.get('id'): item for item in details}
    category_map = fetch_category_map()

    raw_custom_url = channel_item.get('snippet', {}).get('customUrl', '')
    channel_name = raw_custom_url.lstrip('@')

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['channel_name', 'date', 'time', 'views', 'title', 'category'])

    for entry in uploads:
        video = video_map.get(entry['video_id'])
        if not video:
            continue
        snippet = video.get('snippet', {})
        content_details = video.get('contentDetails', {})
        statistics = video.get('statistics', {})
        category_id = snippet.get('categoryId', '')
        writer.writerow([
            channel_name,
            format_date_csv(snippet.get('publishedAt', '')),
            format_duration_csv(content_details.get('duration', '')),
            statistics.get('viewCount', '0'),
            snippet.get('title', ''),
            category_map.get(category_id, category_id),
        ])

    csv_bytes = buf.getvalue().encode('utf-8-sig')
    filename = quote(f"{channel['title']}_all_videos.csv", safe='')
    return Response(
        content=csv_bytes,
        media_type='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"},
    )


@app.post('/api/channel/all-videos')
def get_all_videos(req: ChannelRequest):
    channel_item = resolve_channel(req.channel_input)
    channel = normalize_channel(channel_item)
    uploads_id = channel['uploads_playlist_id']
    if not uploads_id:
        raise HTTPException(status_code=404, detail='uploads プレイリストが取得できませんでした。')

    uploads = fetch_upload_video_ids(uploads_id, scan_limit=None)
    if not uploads:
        raise HTTPException(status_code=404, detail='動画が見つかりませんでした。')

    details = fetch_video_details([x['video_id'] for x in uploads])
    video_map = {item.get('id'): item for item in details}
    category_map = fetch_category_map()

    videos: List[Dict[str, Any]] = []
    total_views = 0
    category_counts: Dict[str, int] = {}
    year_counts: Dict[str, int] = {}

    for entry in uploads:
        video = video_map.get(entry['video_id'])
        if not video:
            continue
        snippet = video.get('snippet', {})
        content_details = video.get('contentDetails', {})
        statistics = video.get('statistics', {})
        tags = snippet.get('tags') or []
        category_id = snippet.get('categoryId', '')
        category_name = category_map.get(category_id, category_id)
        published_at = snippet.get('publishedAt', '')
        view_count = int(statistics.get('viewCount', 0) or 0)
        total_views += view_count

        year = published_at[:4] if published_at else '不明'
        year_counts[year] = year_counts.get(year, 0) + 1

        if category_name:
            category_counts[category_name] = category_counts.get(category_name, 0) + 1

        videos.append({
            'video_id': video.get('id', ''),
            'title': snippet.get('title', ''),
            'published_at': format_date_csv(published_at),
            'duration': format_duration_csv(content_details.get('duration', '')),
            'view_count': view_count,
            'tags': tags,
            'category': category_name,
            'watch_url': f"https://www.youtube.com/watch?v={video.get('id', '')}",
            'thumbnail_url': pick_thumbnail(snippet.get('thumbnails', {})),
            'is_live': is_live_archive(video),
        })

    category_breakdown = sorted(
        [{'name': k, 'count': v} for k, v in category_counts.items()],
        key=lambda x: x['count'], reverse=True
    )
    year_breakdown = sorted(
        [{'year': k, 'count': v} for k, v in year_counts.items()],
        key=lambda x: x['year'], reverse=True
    )

    return {
        'channel': channel,
        'videos': videos,
        'stats': {
            'total_videos': len(videos),
            'total_views': total_views,
            'live_archive_count': sum(1 for v in videos if v['is_live']),
        },
        'category_breakdown': category_breakdown,
        'year_breakdown': year_breakdown,
    }


@app.get('/')
def root() -> FileResponse:
    return FileResponse('static/index.html')


app.mount('/static', StaticFiles(directory='static'), name='static')

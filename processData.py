# Open up .html watch-history and put into json format

import json
import time
from dataclasses import asdict, dataclass, field
from itertools import islice
from pathlib import Path
from typing import List

import googleapiclient.discovery
import googleapiclient.errors
import pendulum
from selectolax.parser import HTMLParser


WAIT_TIME_BETWEEN_BATCHES = 0.2 # seconds


def youtube_iso8601_pt_to_seconds(youtube_iso8601_str):
    # Max video length is 12hrs, therefore...
    # Will always follow format of PT#H#M#S
    t_str = youtube_iso8601_str[2:]

    try:
        if 'H' in t_str:
            hours = int(t_str.split('H')[0])
        else:
            hours = 0
        if 'M' in t_str:
            minutes = int(t_str.split('H')[-1].split('M')[0])
        else:
            minutes = 0
        if 'S' in t_str:
            if 'H' in t_str and not 'M' in t_str:
                seconds = int(t_str.split('H')[-1].split('S')[0])
            else:
                seconds = int(t_str.split('M')[-1].split('S')[0])
        else:
            seconds = 0

        return int(hours) * 3600 + int(minutes) * 60 + int(seconds)

    except ValueError:
        print(f'Unable to parse {youtube_iso8601_str}')
        return -1
    

@dataclass(slots=True) # only works in Python 3.10+
class VideoData:
    # in watch_history.html
    title: str
    video_id: str
    channel: str
    channel_id: str
    when_watched: str

    # from API
    published: str = ''
    duration_seconds: int = -1
    view_count: int = -1
    tags: List[str] = field(default_factory=list)


def batched(iterable, n): # This is part of stdlib in Python 3.12+...
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError('n must be at least one')
    it = iter(iterable)
    while batch := tuple(islice(it, n)):
        yield batch


if __name__ == '__main__':
    # Load API key
    with open('api_keys.json', 'r') as f:
        keys = json.load(f)
    if keys['api_key'] == 'YOUR_API_KEY_HERE':
        # Details on how to get API key: https://www.reddit.com/r/youtube/comments/13ron9q/calculating_ones_total_watch_time_and_amount_of/
        raise ValueError('Please create api_keys.json and add your YouTube API key.')

    # Set up Google auth flow
    scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
    api_service_name = "youtube"
    api_version = "v3"
    youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey=keys['api_key'])

    # Load and parse user data
    watch_history_path = Path('~').expanduser() / 'Downloads' / 'Takeout' / 'YouTube and YouTube Music' / 'history' / 'watch-history.html'
    with open(watch_history_path, 'r') as f:
        raw = f.read()
    parsed = HTMLParser(raw)

    data = []

    parent_div = parsed.css_first('div')
    first_child = parent_div.css_first('div')
    for i, x in enumerate(first_child.iter()):
        # Get content elements
        content_div = x.css_first('div > div:nth-child(2)')
        a_tags = content_div.css('a')
        if len(a_tags) == 0:
            # "Watched a video that has been removed"
            # These are excluded from the output stats
            continue

        # Grab text info
        dummy_split_character = 'ʧ' # Random UTF-8 character I found
        text_parts = content_div.text(separator=dummy_split_character).split(dummy_split_character)
        if len(text_parts) == 4:
            # Public video
            _, title, channel, watched_date = text_parts
            video_url, channel_url = [a.attributes['href'] for a in a_tags]
        elif len(text_parts) == 3:
            # Private but existing video
            watched_date = text_parts[-1]
            title = 'PRIVATE VIDEO'
            channel = 'PRIVATE CHANNEL'
            video_url = a_tags[0].attributes['href']
            channel_url = ''

        # Format watched date into ISO 8601
        watched_date = pendulum.from_format(
            watched_date[:-4],
            'MMM D, YYYY, H:mm:ss\u202fA',
            tz='local',
        ).isoformat()

        current_item = VideoData(
            title,
            video_url.split('=')[-1],
            channel, 
            channel_url.split('/')[-1],
            watched_date,
        )
        data.append(current_item)

    print(f'Processed watch_history.html - {len(data)} videos found.)')
    print('Making Youtube API requests to get video info...')

    # Get video data in batches from Google API (max 50 per request)
    for start_idx, item_batch in zip(range(0, len(data)+50, 50), batched(data, 50)):
        if start_idx % 500 == 0:
            print(f'Processed {start_idx}/{len(data)} videos...')
        # Get video info / length from Google API
        batch_ids = [item.video_id for item in item_batch]
        batch_ids_str = ','.join(batch_ids)

        request = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=batch_ids_str, # can pass command-separated list of IDs
        )
        response = request.execute()

        responded_items = {x['id']: x for x in response['items']}
        for batch_idx, item in enumerate(item_batch):
            if item.video_id not in responded_items:
                # Data missing in some way
                continue
            video_id = item.video_id
            video_info = responded_items[video_id]

            # Update item in data list
            data_item = data[start_idx + batch_idx]
            data_item.published = video_info['snippet']['publishedAt']
            data_item.duration_seconds = youtube_iso8601_pt_to_seconds(video_info['contentDetails']['duration'])
            data_item.view_count = int(video_info['statistics'].get('viewCount', '0'))
            data_item.tags = video_info['snippet'].get('tags', [])
        
            # time.sleep(WAIT_TIME_BETWEEN_BATCHES)

    # Dump data into JSON
    write_dict = [asdict(item) for item in data]
    with open('watch_history.json', 'w') as f:
        json.dump(write_dict, f, indent=2)

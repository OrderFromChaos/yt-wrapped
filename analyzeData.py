import json
from collections import Counter

import matplotlib.pyplot as plt
import pendulum
import seaborn
from matplotlib.backends.backend_pdf import PdfPages
from tabulate import tabulate
from termcolor import colored, cprint


if __name__ == '__main__':

    RANGE = (
        pendulum.datetime(2023, 1, 1),
        pendulum.datetime(2023, 12, 31)
    )
    REMOVE_DUPLICATES = True
    EXCLUDE_VIDEOS_OVER_DURATION_MINUTES = 179
    CHANNEL_EXCEPTIONS_FOR_DURATION_FILTER = set([
        'Linus Tech Tips',
        'ZFG',
        'Fredrik Knudsen',
        'hbomberguy',
        'Kyle Hess',
    ])

    with open('watch_history.json', 'r') as f:
        data = json.load(f)

    print('Stats cover the period from', RANGE[0].to_date_string(), 'to', RANGE[1].to_date_string())
    print('Duplicate removal is', 'ON' if REMOVE_DUPLICATES else 'OFF')
    
    # Filter out private videos
    data = [x for x in data if x['title'] != 'PRIVATE VIDEO']

    # Filter date range
    for x in data:
        x['when_watched'] = pendulum.parse(x['when_watched'])
        x['published'] = pendulum.parse(x['published'])
    data = [x for x in data if RANGE[0] <= x['when_watched'] <= RANGE[1]]

    # Sort by watch date
    data = sorted(data, key=lambda x: x['when_watched'])

    # Filter too-long videos (likely to be music or podcasts)
    # Note that -1 is failed to parse, which means > 24hrs and definitely a livestream / music stream
    data = [
        x for x in data
        if 0 <= x['duration_seconds'] <= EXCLUDE_VIDEOS_OVER_DURATION_MINUTES * 60
        or x['channel'] in CHANNEL_EXCEPTIONS_FOR_DURATION_FILTER
    ]

    # Remove duplicates if enabled - keep oldest
    seen = set()
    new_data = []
    video_id_to_object = {}
    duplicated = Counter()
    for d in data:
        if d['video_id'] in seen:
            video_id_to_object[d['video_id']] = d
            duplicated[d['video_id']] += 1
            if REMOVE_DUPLICATES:
                continue
            else:
                new_data.append(d)
        else:
            seen.add(d['video_id'])
            new_data.append(d)
    data = new_data

    # Interesting stats:
    # 1. Most commonly watched channels
    # 2. Total videos watched
    # 3. Average video length
    # 4. Longest videos
    # 5. Shortest videos
    # 6. Common tag keywords
    # 7. Most "rewatchable" - aka most duplicated videos (both channel and video)

    print('Total videos watched:', len(data))

    channel_id_to_channel = {}
    channel_id_frequency = Counter()
    channel_id_time_watched = Counter()
    total_video_length = 0
    tag_keywords = Counter()

    for x in data:
        channel_id_to_channel[x['channel_id']] = x['channel']
        channel_id_frequency[x['channel_id']] += 1
        channel_id_time_watched[x['channel_id']] += x['duration_seconds']
        for tag in x['tags']:
            for word in tag.lower().split(' '):
                tag_keywords[word] += 1
        total_video_length += x['duration_seconds']
    
    # Remove some common words
    common_words = ['the', 'of', 'to', 'how', '2', '3', 'a', 'is', 'and']
    for cword in common_words:
        del tag_keywords[cword]

    hours_watched = round(total_video_length / 3600, 2)
    number_of_days_in_duration = (RANGE[1] - RANGE[0]).in_days()
    print('Hours watched:', hours_watched, f'(~{round(hours_watched / number_of_days_in_duration, 2)} hours per day)')
    print('Mean video length:', round(total_video_length / len(data) / 60, 2), 'minutes')

    most_watched_by_count = [
        (
            colored(channel_id_to_channel[channel_id], 'cyan'),
            colored(frequency, 'green'),
            colored(round(channel_id_time_watched[channel_id] / 3600, 2), 'green'),
        )
        for channel_id, frequency
        in channel_id_frequency.most_common(20)
    ]
    print(tabulate(most_watched_by_count, headers=['Most Watched (by video count)', 'Videos', 'Time Watched (hr)']))

    most_watched_by_time = [
        (
            colored(channel_id_to_channel[channel_id], 'cyan'),
            colored(round(frequency / 3600, 2), 'green'),
            colored(channel_id_frequency[channel_id], 'green'),
        )
        for channel_id, frequency
        in channel_id_time_watched.most_common(20)
    ]
    print(tabulate(most_watched_by_time, headers=['Most Watched (by time)', 'Time Watched (hr)', 'Videos']))


    top_tags = [
        (
            colored(tag, 'cyan'),
            colored(frequency, 'green'),
        )
        for tag, frequency
        in tag_keywords.most_common(20)
    ]
    print(tabulate(top_tags, headers=['Tag', 'Frequency']))


    # Longest videos
    data.sort(key=lambda x: x['duration_seconds'], reverse=True)
    longest_videos = [
        (
            colored(x['title'], 'cyan'),
            colored(round(x['duration_seconds'] / 3600, 2), 'green'),
            colored(x['channel'], 'yellow'),
        )
        for x in data[:20]
    ]
    print(tabulate(longest_videos, headers=['Longest video titles', 'Duration (hr)', 'Channel']))

    # Shortest videos
    shortest_videos = [
        (
            colored(x['title'], 'cyan'),
            colored(x['duration_seconds'], 'green'),
            colored(x['channel'], 'yellow'),
        )
        for x in sorted(data[-20:], key=lambda x: x['duration_seconds'])
    ]
    print(tabulate(shortest_videos, headers=['Shortest video titles', 'Duration (sec)', 'Channel']))

    # Most duplicated videos
    duplicated_videos = [
        (
            colored(video_id_to_object[video_id]['title'], 'cyan'),
            colored(frequency, 'green'),
            colored(video_id_to_object[video_id]['channel'], 'yellow'),
        )
        for video_id, frequency
        in duplicated.most_common(20)
    ]
    print(tabulate(duplicated_videos, headers=['Most rewatched video titles', 'Frequency', 'Channel']))

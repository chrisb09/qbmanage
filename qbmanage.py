import argparse, os, time
import re
import yaml
from qbittorrentapi import Client, LoginFailed
from typing import Dict, List, Tuple
from collections import defaultdict

import pandas as pd
import numpy as np

def load_config(config_path: str) -> Dict:
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
            return config['qbit']
    except FileNotFoundError:
        print("Error: config.yml not found")
        exit(1)

def connect_qbit(config: Dict) -> Client:
    try:
        client = Client(
            host=config['host'],
            port=config['port'],
            username=config['username'],
            password=config['password']
        )
        return client
    except LoginFailed:
        print("Error: Failed to connect to QBittorrent")
        exit(1)
        
def qbit_status(client: Client):
    try:
        print("Connected to qBittorrent. Version:", client.app_version())
        print("Torrents:", client.torrents_count())
        print("Total Size (TiB):", round(sum(torrent.size for torrent in client.torrents_info()) / (1024 ** 4), 2))
    except LoginFailed:
        print("Error: Failed to connect to QBittorrent")
        exit(1)
        
def overview_torrents(client: Client):
    torrents = client.torrents_info()
    
    print('-' * 120)
    print(f"Total Torrents: {len(torrents)}")
    print(f"Total Size (TiB): {sum(torrent.size for torrent in torrents) / (1024 ** 4):.2f}")
    print(f"Total Downloaded (GB): {sum(torrent.downloaded for torrent in torrents) / (1024 ** 3):.2f}")
    print(f"Total Uploaded (GB): {sum(torrent.uploaded for torrent in torrents) / (1024 ** 3):.2f}")
    print(f"Total Ratio: {(sum(torrent.uploaded for torrent in torrents) / sum(torrent.downloaded for torrent in torrents)):.2f}")
    print(f"Ratio sum: {sum(torrent.ratio for torrent in torrents) / len(torrents):.2f}")

def list_tracker_messages(client: Client, no_progress: bool = False, tracker_regex: list[str] = [], message_regex: list[str] = [], hash_regex: list[str] = [], torrent_regex: list[str] = [], full: bool = False, delete: bool = False, yes_do_as_i_say: bool = False, path_prefix: str = ''):
    tracker_matches = [re.compile(tr, re.IGNORECASE) for tr in tracker_regex] if tracker_regex else []
    message_matches = [re.compile(msg, re.IGNORECASE) for msg in message_regex] if message_regex else []
    hash_matches = [re.compile(h, re.IGNORECASE) for h in hash_regex] if hash_regex else []
    torrent_matches = [re.compile(t, re.IGNORECASE) for t in torrent_regex] if torrent_regex else []
    trackers = defaultdict(lambda: {'count': 0, 'size': 0})
    torrent_files = {} # file: [torrents]
    
    print("Client version: "+client.app_version())
    print("Client app_default_save_path: "+client.app_default_save_path())
    

    df = pd.DataFrame(columns=['Torrent Name', 'Tracker', 'Hash', 'Size', 'Files', 'Status', 'Tracker Status', 'Message'])
    
    total = len(client.torrents_info())
    current = 0
    for torrent in client.torrents_info():
        current += 1
        if not no_progress:
            print("["+"#"*int(current*20/total)+" "*int((total-current)*20/total)+"] "+f"{(100*current//total)}% {current}/{total}", end='\r')
        trackerlist = client.torrents_trackers(torrent.hash)
        if not trackerlist:
            print(f"Warning: No trackers found for torrent {torrent.name}")
            continue
        
        # Iterate over all files in the torrent
        for file in torrent.files:
            if file.name not in torrent_files:
                torrent_files[file.name] = []
            torrent_files[file.name].append(torrent)
        
        # Use the first tracker as the main one
        tracker_obj = None
        for tracker in trackerlist:
            tracker_obj = tracker
            if tracker_obj.get('url', '').startswith('**'):
                continue
            msg = tracker_obj.get('msg', 'No Message')
            if msg.startswith('You last announced'):
                msg = "You last announced X s ago. Please respect the min interval."
            if not tracker_obj:
                print(f"Warning: No enabled trackers found for torrent {torrent.name}")
                continue
            if len(tracker_obj.get('msg', 'No message')) == 0:
                continue
            # from https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-4.1)#get-torrent-trackers
            # 0 	Tracker is disabled (used for DHT, PeX, and LSD)
            # 1 	Tracker has not been contacted yet
            # 2 	Tracker has been contacted and is working
            # 3 	Tracker is updating
            # 4 	Tracker has been contacted, but it is not working (or doesn't send proper replies)
            if tracker_obj.get('status', 0) != 4:
                continue
            if tracker_matches and not any(tracker_match.search(tracker_obj.get('url', '')) for tracker_match in tracker_matches):
                continue
            if message_matches and not any(message_match.search(tracker_obj.get('msg', '')) for message_match in message_matches):
                continue
            if hash_matches and not any(hash_match.search(torrent.hash) for hash_match in hash_matches):
                continue
            if torrent_matches and not any(torrent_match.search(torrent.name) for torrent_match in torrent_matches):
                continue
            df = pd.concat([df, pd.DataFrame({  # Corrected to use pd.concat with a list
                'Torrent Name': [torrent.name],
                'Tracker': [tracker_obj.get('url', 'https://no.tracker').replace('http://', '').replace('https://', '').split('/')[0]],
                'Hash': [torrent.hash],
                'Size': [torrent.size],
                'Files': "	".join([file.name for file in torrent.files]),
                'Status': [torrent.state_enum.name],
                'Tracker Status': [tracker_obj.get('status', 'No status')],
                'Message': [msg]
            })], ignore_index=True)  # Added DataFrame constructor
            break  # Only take the first tracker that fits the criteria
        if tracker_obj is None:
            print(f"Warning: No fitting trackers found for torrent {torrent.name}")
            continue
        tracker_url = tracker_obj.get('url', 'No URL')
        tracker = tracker_url.replace('https://', '').replace('http://', '').split('/')[0]
        trackers[tracker]['count'] += 1
        trackers[tracker]['size'] += torrent.size
        trackers[tracker]['message'] = msg  # Store last message for demo
    
    
    # Print the 10 most used files
    for file, torrents in sorted(torrent_files.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
        print(f"File: {file}, Used in {len(torrents)} torrents")
    
    print(f"{'Tracker':<30} {'Count':>10} {'Size (TiB)':>15}")
    print('-' * 60)
    for tracker, data in trackers.items():
        size_tib = data['size'] / (1024 ** 4)
        print(f"{tracker:<30} {data['count']:>10} {size_tib:>15.2f}")
        
    to_delete_torrents = []
    to_delete_files = []
    
    # Loop over all message types, sorted by amount of torrents with that message
    message_counts = df['Message'].value_counts()
    for message, count in message_counts.items():
        print('-' * 120)
        print(f"{message}: {count} torrents")
        print("")
        # print table of indexers, the count of torrents and the sum of of torrent sizes per indexer
        print(f"    {'Tracker':<60} {'Count':>10} {'Size (GiB)':>15}")
        print('    '+'-' * 90)
        for tracker, data in df[df['Message'] == message].groupby('Tracker').agg({'Size': 'sum', 'Hash': 'count'}).iterrows():
            size_gib = data['Size'] / (1024 ** 3)
            print(f"    {tracker:<60} {int(data['Hash']):>10} {size_gib:>15.2f}")
        print("")
        # grouped by tracker, print a table of torrents with that message, specifically the torrent name, hash, size, status
        for tracker, data in df[df['Message'] == message].groupby('Tracker'):
            print(f"    {tracker}: {len(data)} torrents")
            print(f"        {'Hash':<40} {'Size (GiB)':>10} {'Torrent Name':<50}")
            print('        '+'-' * 100)
            if delete:
                for torrent in data.itertuples():
                    to_delete_torrents.append(torrent.Hash)
                    for file in torrent.Files.split('	'):
                        torrent_files[file] = list(filter(lambda x: x.hash != torrent.Hash, torrent_files[file]))
                        if len(torrent_files[file]) == 0:
                            to_delete_files.append(file)
            list_torrents_count = 0
            for torrent in data.itertuples():
                if not full:
                    list_torrents_count += 1 
                if list_torrents_count > 10:
                    break
                # print torrent name, hash, size, status        
                size_gib = torrent.Size / (1024 ** 3)
                print(f"        {torrent.Hash:<40} {size_gib:>10.2f} {torrent._1:<50}")
                print(f"            {'Size (GiB)':>10} {'SL':>5} {'HL':>5} {'Used':>5} {'Files':<75}")
                list_files_count = 0
                for file in torrent.Files.split('	'):
                    if not full:
                        list_files_count += 1
                    if list_files_count > 3:
                        break
                    file_path = path_prefix + os.path.join(client.app_default_save_path(), file)
                    if os.path.exists(file_path):
                        print(f"            {os.stat(file_path).st_size / (1024 ** 3):>10.2f} {os.path.islink(file_path):>5} {os.stat(file_path).st_nlink:>5} {len(torrent_files[file]) if file in torrent_files else 0:>5} {file:<75}")
                    else:
                        print(f"            Could not find file: {file_path}")
                        if not path_prefix:
                            print("            Perhaps use --path-prefix to set the correct path prefix")
                if list_files_count > 3:
                    print(f"                ... and {len(torrent.Files.split('	')) - list_files_count} more files")
            if list_torrents_count > 10:
                print(f"            ... and {len(data) - list_torrents_count} more torrents")
            print("")
        
    if delete:
        # ask if the user wants to delete the torrents
        confirm = "n"
        if yes_do_as_i_say:
            confirm = "y"
        else:
            confirm = input(f"Delete these {len(to_delete_torrents)} torrents? (y/N): ")
        if confirm.lower().startswith('y'):
            print(f"This will delete {len(to_delete_files)} files and {len(to_delete_torrents)} torrents. Specifically, these files:")
            for file in to_delete_files:
                print(f"    {file}")
            confirm = "n"
            if yes_do_as_i_say:
                confirm = "y"
            else:
                confirm = input(f"Is this correct? (y/N): ")
            if confirm.lower().startswith('y'):
                for torrent in to_delete_torrents:
                    client.torrents_delete(delete_files=False, torrent_hashes=torrent)
                for file in to_delete_files:
                    file_path = path_prefix + os.path.join(client.app_default_save_path(), file)
                    try:
                        os.remove(file_path)
                    except FileNotFoundError:
                        print(f"File {file_path} not found, skipping")
                    except PermissionError:
                        print(f"Permission denied for {file_path}, skipping")
                    except Exception as e:
                        print(f"Error deleting {file_path}: {e}")
                print("Torrents deleted")
                print(f"Deleted {len(to_delete_files)} files")
            else:
                print("Deletion canceled")
        else:
            print("Deletion canceled")
            
        print("")
        
        
def show_unused_files(client: Client, no_progress: bool = False, path_prefix: str = '', full: bool = False, delete: bool = False, yes_do_as_i_say: bool = False):

    torrent_files = {} # file: [torrents]
    
    print("Client version: "+client.app_version())
    print("Client app_default_save_path: "+client.app_default_save_path())
    
    total = len(client.torrents_info())
    current = 0
    for torrent in client.torrents_info():
        current += 1
        if not no_progress:
            print("Get files of torrents ["+"#"*int(current*20/total)+" "*int((total-current)*20/total)+"] "+f"{(100*current//total)}% {current}/{total}", end='\r')
        trackerlist = client.torrents_trackers(torrent.hash)
        if not trackerlist:
            print(f"Warning: No trackers found for torrent {torrent.name}")
            continue
        
        # Iterate over all files in the torrent
        for file in torrent.files:
            file_path = path_prefix + os.path.join(client.app_default_save_path(), file.name)
            if os.path.abspath(file_path) not in torrent_files:
                torrent_files[os.path.abspath(file_path)] = []
            torrent_files[os.path.abspath(file_path)].append(torrent)
            
    torrent_parent_dir = path_prefix + client.app_default_save_path()
    print(f"Looking for files in {torrent_parent_dir}")
    
    unused_files = []
    unused_file_size = 0
    softlink_count = 0
    hardlink_count = 0
    # use os walk
    total_count = sum([len(files) for _, _, files in os.walk(torrent_parent_dir)])
    torrent_count = current
    current = 0
    for root, dirs, files in os.walk(torrent_parent_dir):
        for file in files:
            current += 1
            if not no_progress:
                print("["+"#"*int(current*20/total_count)+" "*int((total_count-current)*20/total_count)+"] "+f"{(100*current//total_count)}% {current}/{total_count}", end='\r')
            if os.path.abspath(os.path.join(root, file)) not in torrent_files:
                unused_files.append(os.path.abspath(os.path.join(root, file)))
                if os.path.islink(os.path.join(root, file)):
                    softlink_count += 1
                elif os.stat(os.path.join(root, file)).st_nlink > 1:
                    hardlink_count += 1
                unused_file_size += os.stat(os.path.join(root, file)).st_size
                
    print(f"We searched through {torrent_count} torrents and {total_count} files.")
    print(f"Found {len(unused_files)} unused files with a total size of {unused_file_size / (1024 ** 4):.2f} TiB:")
    print(f"  of which {softlink_count} are softlinks and {hardlink_count} are hardlinks")
    print(f"  of which {len(unused_files) - softlink_count - hardlink_count} are normal files")
    # print the first 10 unused files
    if not full:
        for file in unused_files[:10]:
            print(f"    {file}")
        if len(unused_files) > 10:
            print(f"    {len(unused_files) - 10} more files")
    else:
        for file in unused_files:
            print(f"    {file}")
    
    if delete:
        confirm = "n"
        if yes_do_as_i_say:
            confirm = "y"
        else:
            confirm = input(f"Delete these unused files? (y/N): ")
        if confirm.lower().startswith('y'):
            for file in unused_files:
                file_path = os.path.join(root, file)
                try:
                    os.remove(file_path)
                except FileNotFoundError:
                    print(f"File {file_path} not found, skipping")
                except PermissionError:
                    print(f"Permission denied for {file_path}, skipping")
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")
            print("Unused files deleted")
            empty_dirs = []
            for root, dirs, files in os.walk(torrent_parent_dir):
                for dir in dirs:
                    if len(os.listdir(os.path.join(root, dir))) == 0:
                        empty_dirs.append(os.path.join(root, dir))
            print(f"Found {len(empty_dirs)} empty directories:")
            for dir in empty_dirs[:10]:
                print(f"    {dir}")
            if len(empty_dirs) > 10:
                print(f"    {len(empty_dirs) - 10} more directories")
            # ask if the user wants to delete the empty directories
            confirm = "n"
            if yes_do_as_i_say:
                confirm = ""
            else:
                confirm = input(f"Also delete empty dirs? (y/N): ")
            if confirm.lower().startswith('y'):
                for dir in empty_dirs:
                    try:
                        os.rmdir(dir)
                    except FileNotFoundError:
                        print(f"Directory {dir} not found, skipping")
                    except PermissionError:
                        print(f"Permission denied for {dir}, skipping")
                    except Exception as e:
                        print(f"Error deleting {dir}: {e}")
                print("Empty directories deleted")
                print(f"Deleted {len(empty_dirs)} empty directories")
        else:
            print("Deletion canceled")
            
class MyTracker:
    def __init__(self, url: str, status: int, msg: str):
        self.url = url
        self.status = status
        self.msg = msg
        
    def __repr__(self):
        return f"MyTracker(url={self.url}, status={self.status}, msg={self.msg})"
            
class MyTorrent:
    def __init__(self, name: str, hash: str, size: int, files: List[str], state_enum: str, category: str, tags: List[str], trackerlist: List[MyTracker]):
        self.name = name
        self.hash = hash
        self.size = size
        self.files = files
        self.state_enum = state_enum
        self.category = category
        self.tags = tags
        self.trackerlist = trackerlist

    def __init__(self, torrent):
        self.name = torrent.name
        self.hash = torrent.hash
        self.size = torrent.size
        self.files = [file.name for file in torrent.files]
        self.state_enum = torrent.state_enum.name
        self.category = torrent.category
        self.tags = torrent.tags
        self.trackerlist = [MyTracker(url=tr.url, status=tr.status, msg=tr.msg) for tr in torrent.trackers]

    def __repr__(self):
        return f"MyTorrent(name={self.name}, hash={self.hash}, size={self.size}, files={self.files}, state_enum={self.state_enum}, category={self.category}, tags={self.tags}, trackerlist={self.trackerlist})"

class MyTorrentList(List[MyTorrent]):
    trackers = set()
    def __init__(self, client: Client):
        super().__init__()
        time_a = time.time()
        self.client = client
        self.update_torrents()
        time_b = time.time()
        print(f"Time to retrieve data and trackers for all torrents: {time_b - time_a:.2f}s")
        
    def get_by_hash(self, hash: str) -> MyTorrent:
        for torrent in self:
            if torrent.hash == hash:
                return torrent
        return None

    def update_torrents(self):
        self.clear()
        current = 0
        torrents = self.client.torrents_info()
        total = len(torrents)
        for torrent in torrents:
            current += 1
            print(f"Updating torrents ["+"#"*int(current*20/total)+" "*int((total-current)*20/total)+"] "+f"{(100*current//total)}% {current}/{total}", end='\r')
            myTorrent = MyTorrent(torrent)
            self.append(myTorrent)
            for tr in myTorrent.trackerlist:
                if tr in self.trackers:
                    self.trackers.add(tr)
    def __repr__(self):
        return f"MyTorrentList(torrents={self.torrents})"

def handle_unlinked_files(client: Client, exclude_trackers: list[str] = [], exclude_messages: list[str] = [], exclude_hashes: list[str] = [], exclude_categories: list[str] = [], exclude_tags: list[str] = [], include_trackers: list[str] = [], include_messages: list[str] = [], include_hashes: list[str] = [], include_categories: list[str] = [], include_tags: list[str] = [], no_progress: bool = False, delete: bool = False, yes_do_as_i_say: bool = False, path_prefix: str = ''):
    
    cmd_start_time = time.time()
    
    exclude_tracker_matches = [re.compile(tr, re.IGNORECASE) for tr in exclude_trackers] if exclude_trackers else []
    exclude_message_matches = [re.compile(msg, re.IGNORECASE) for msg in exclude_messages] if exclude_messages else []
    exclude_hash_matches = [re.compile(h, re.IGNORECASE) for h in exclude_hashes] if exclude_hashes else []
    exclude_category_matches = [re.compile(c, re.IGNORECASE) for c in exclude_categories] if exclude_categories else []
    exclude_tag_matches = [re.compile(t, re.IGNORECASE) for t in exclude_tags] if exclude_tags else []
    include_tracker_matches = [re.compile(tr, re.IGNORECASE) for tr in include_trackers] if include_trackers else []
    include_message_matches = [re.compile(msg, re.IGNORECASE) for msg in include_messages] if include_messages else []
    include_hash_matches = [re.compile(h, re.IGNORECASE) for h in include_hashes] if include_hashes else []
    include_category_matches = [re.compile(c, re.IGNORECASE) for c in include_categories] if include_categories else []
    include_tag_matches = [re.compile(t, re.IGNORECASE) for t in include_tags] if include_tags else []
    
    print("Mathing's that are active:")
    print(f"  Exclude trackers: {exclude_tracker_matches}")
    print(f"  Exclude messages: {exclude_message_matches}")
    print(f"  Exclude hashes: {exclude_hash_matches}")
    print(f"  Exclude categories: {exclude_category_matches}")
    print(f"  Exclude tags: {exclude_tag_matches}")
    print(f"  Include trackers: {include_tracker_matches}")
    print(f"  Include messages: {include_message_matches}")
    print(f"  Include hashes: {include_hash_matches}")
    print(f"  Include categories: {include_category_matches}")
    print(f"  Include tags: {include_tag_matches}")
    
    print("path_prefix: "+path_prefix)
    
    root_dir = path_prefix + client.app_default_save_path()
    if not os.path.exists(root_dir):
        print(f"Error: {root_dir} does not exist")
        exit(1)
    if not os.path.isdir(root_dir):
        print(f"Error: {root_dir} is not a directory")
        exit(1)
    if not os.access(root_dir, os.R_OK):
        print(f"Error: {root_dir} is not readable")
        exit(1)
    if not os.access(root_dir, os.W_OK):
        print(f"Error: {root_dir} is not writable")
        exit(1)
    print(f"Using {root_dir} as root directory")

    torrents_to_consider = {} # torrent: [unlinked_files]
    unlinked_files = {} # file: [torrents]
    trackers = {} # torrent: tracker-name

    print("Client version: "+client.app_version())
    print("Client app_default_save_path: "+client.app_default_save_path())
    
    print("Retrieving torrents...")
    time_before = time.time()
    myTorrents = MyTorrentList(client)
    
    for torrent in myTorrents[:10]:
        print(f"    {torrent.name:<120} ({torrent.hash:<40}) {torrent.size / (1024 ** 3):>10.2f} GiB {torrent.state_enum:<20} {torrent.trackerlist[0].url if torrent.trackerlist else 'No tracker'}")
        print(f"    alternative: "+torrent.__repr__())
    
    
    total = len(myTorrents)
    current = 0
    time_a = 0
    time_b = 0
    time_c = 0
    time_d = 0
    for torrent in myTorrents:
        current += 1
        time_before = time.time()
        if not no_progress:
            print(f"Handle unlinked files ["+"#"*int(current*20/total)+" "*int((total-current)*20/total)+"] "+f"{(100*current//total)}% {current}/{total} "+f"{int(time_a/(time_a+time_b+time_c+time_d)*100):>3}% {int(time_b/(time_a+time_b+time_c+time_d)*100):>3}% {int(time_c/(time_a+time_b+time_c+time_d)*100):>3}% {int(time_d/(time_a+time_b+time_c+time_d)*100):>3}% " if (time_a + time_b + time_c + time_d > 0) else "", end='\r')
        trackerlist = None
        try:
            trackerlist = torrent.trackerlist
        except Exception as e:
            print(f"Error getting trackers for torrent {torrent.name}: {e}")
            continue
        if not trackerlist:
            print(f"Warning: No trackers found for torrent {torrent.name}")
            continue
        time_a += time.time() - time_before
        time_before = time.time()
        # Use the first tracker as the main one
        tracker_obj = None
        for tracker in trackerlist:
            tracker_obj = tracker
            if tracker_obj.url.startswith('**'):
                continue
            msg = tracker_obj.msg
            if msg.startswith('You last announced'):
                msg = "You last announced X seconds ago. Please respect the min interval."
            if not tracker_obj:
                print(f"Warning: No enabled trackers found for torrent {torrent.name}")
                continue
            if len(msg) == 0:
                continue

        trackers[torrent.hash] = tracker_obj.url.replace('https://', '').replace('http://', '').split('/')[0]
        
        time_b += time.time() - time_before
        time_before = time.time()
            
        unlinked_files_of_this_torrent = []
            
        # iterate over all files in the torrent
        for f in torrent.files:
            file_path = os.path.join(root_dir, f)
            if os.path.exists(file_path):
                file_path = os.path.abspath(file_path)
                if os.path.islink(file_path):
                    continue
                elif os.stat(file_path).st_nlink > 1:
                    continue
                else:
                    if os.path.abspath(file_path) not in unlinked_files:
                        unlinked_files[file_path] = []
                    unlinked_files[file_path].append(torrent)
                    unlinked_files_of_this_torrent.append(file_path)
            else:
                print(f"Warning: {file_path} does not exist")
                
        time_c += time.time() - time_before
        time_before = time.time()
                
        
        # use matching to exlude and include torrents
        if exclude_tracker_matches and any(exclude_tracker_match.search(tracker_obj.url) for exclude_tracker_match in exclude_tracker_matches):
            continue
        if exclude_message_matches and any(exclude_message_match.search(msg) for exclude_message_match in exclude_message_matches):
            continue
        if exclude_hash_matches and any(exclude_hash_match.search(torrent.hash) for exclude_hash_match in exclude_hash_matches):
            continue
        if exclude_category_matches and any(exclude_category_match.search(torrent.category) for exclude_category_match in exclude_category_matches):
            continue
        if exclude_tag_matches and any(exclude_tag_match.search(torrent.tags) for exclude_tag_match in exclude_tag_matches):
            continue
        if include_tracker_matches and not any(include_tracker_match.search(tracker_obj.url) for include_tracker_match in include_tracker_matches):
            continue
        if include_message_matches and not any(include_message_match.search(msg) for include_message_match in include_message_matches):
            continue
        if include_hash_matches and not any(include_hash_match.search(torrent.hash) for include_hash_match in include_hash_matches):
            continue
        if include_category_matches and not any(include_category_match.search(torrent.category) for include_category_match in include_category_matches):
            continue
        if include_tag_matches and not any(include_tag_match.search(torrent.tags) for include_tag_match in include_tag_matches):
            continue
        if len(unlinked_files_of_this_torrent) != 0:
            torrents_to_consider[torrent] = unlinked_files_of_this_torrent
            
        time_d += time.time() - time_before
        
    print(f"Time taken to get torrents: {time_a:.2f}s ~ {time_a/total:.2f}s/torrent or {time_a/(time_a+time_b+time_c+time_d)*100:.2f}%")
    print(f"Time taken to get trackers: {time_b:.2f}s ~ {time_b/total:.2f}s/torrent or {time_b/(time_a+time_b+time_c+time_d)*100:.2f}%")
    print(f"Time taken to get files: {time_c:.2f}s ~ {time_c/total:.2f}s/torrent or {time_c/(time_a+time_b+time_c+time_d)*100:.2f}%")
    print(f"Time taken to filter torrents: {time_d:.2f}s ~ {time_d/total:.2f}s/torrent or {time_d/(time_a+time_b+time_c+time_d)*100:.2f}%")
    print(f"Time taken to get all torrents: {time_a + time_b + time_c + time_d:.2f}s ~ {(time_a + time_b + time_c + time_d)/total:.2f}s/torrent or {(time_a + time_b + time_c + time_d)/(time_a+time_b+time_c+time_d)*100:.2f}%")
        
    print(f"Found {len(torrents_to_consider)} torrents with unlinked files:")
        
        
    df = pd.DataFrame(columns=['Torrent_Name', 'Hash', 'Size', 'Unlinked_Size', 'Tracker'])
    
    current = 0
    total = len(torrents_to_consider)
    

    for torrent, unlinked_files in torrents_to_consider.items():
        if current == 0:
            print(f"  {torrent.hash}: {','.join(unlinked_files)}")
        current += 1
        if not no_progress:
            print("Extracting data from torrents ["+"#"*int(current*20/total)+" "*int((total-current)*20/total)+"] "+f"{(100*current//total)}% {current}/{total}", end='\r')
        if torrent.hash not in trackers:
            print(f"Warning: No tracker found for torrent {torrent.name}")
            continue
        if len(unlinked_files) == 0:
            print(f"Warning: No unlinked files found for torrent {torrent.name}")
            continue
        df = pd.concat([df, pd.DataFrame({
            'Torrent_Name': [torrent.name],
            'Hash': [torrent.hash],
            'Size': [int(torrent.size)],
            'Unlinked_Size': [sum(os.stat(file).st_size for file in unlinked_files)],
            'Tracker': [trackers[torrent.hash]]
        })], ignore_index=True)
        
    print(f"Found {len(df)} torrents with unlinked files:")

    print(f"{'Size (GiB)':>15} {'Unlinked Size (GiB)':>20} {'Unlinked %':>15} {'Tracker':<30} {'Torrent Name':<60} ")
    print('-' * 120)
    # print torrents sorted by unlinked size
    for torrent in df.sort_values(by='Unlinked_Size', ascending=True).itertuples():
        print(f"{torrent.Size / (1024 ** 3):>15.2f} {torrent.Unlinked_Size / (1024 ** 3):>20.2f} {torrent.Unlinked_Size / torrent.Size * 100:>15.2f} {torrent.Tracker:<30} {torrent.Torrent_Name:<60}")
        
    print("")
    print("Grouped by torrent name:")
    # print grouped by torrent name
    print(f"{'Size (GiB)':>15} {'Unlinked Size (GiB)':>20} {'Unlinked %':>15} {'Tracker':<30} {'Torrent Name':<60}")
    print('-' * 120)
    for torrent in df.sort_values(by='Unlinked_Size', ascending=True).itertuples():
        print(f"{torrent.Size / (1024 ** 3):>15.2f} {torrent.Unlinked_Size / (1024 ** 3):>20.2f} {torrent.Unlinked_Size / torrent.Size * 100:>15.2f} {torrent.Tracker:<30} {torrent.Torrent_Name:<60}")

    print("")
    print("Grouped by tracker:")
    # print grouped by tracker
    print(f"{'Tracker':<30} {'Count':>10} {'Size (GiB)':>15} {'Unlinked Size (GiB)':>20} {'Unlinked %':>15}")
    print('-' * 120)
    for tracker, data in df.groupby('Tracker').agg({'Size': 'sum', 'Unlinked_Size': 'sum', 'Torrent_Name': 'count'}).sort_values(by='Unlinked_Size', ascending=True).iterrows():
        size_gib = data['Size'] / (1024 ** 3)
        unlinked_size_gib = data['Unlinked_Size'] / (1024 ** 3)
        unlinked_percent = unlinked_size_gib / size_gib * 100
        print(f"{tracker:<30} {int(data['Torrent_Name']):>10} {size_gib:>15.2f} {unlinked_size_gib:>20.2f} {unlinked_percent:>15.2f}")
        
    print("")

    print(f"Total size of unlinked files: {sum(os.stat(file).st_size for files in torrents_to_consider.values() for file in files) / (1024 ** 4):.2f} TiB")

    print(f"Entire command took {time.time() - cmd_start_time:.2f}s")
        

def main():
    parser = argparse.ArgumentParser(description='qBit Management Tool')
    
    parser.add_argument('--config', default='config.yml', help='Path to the config file (default: config.yml)')
    parser.add_argument('--path-prefix', default='', help='Path prefix for torrent files (default: empty)')
    
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Status of qbittorrent
    status_parser = subparsers.add_parser('status', help='Status of qbittorrent')

    # Overview of all torrents
    overview_parser = subparsers.add_parser('overview', help='Overview of all torrents')

    # List messages command
    list_parser = subparsers.add_parser('listmessages', help='List torrents by tracker messages')
    list_parser.add_argument('--no-progress', '--np', action='store_true', help='Disable progress bar')
    list_parser.add_argument('--tracker', nargs='+', help='Filter by one or more tracker URLs, in regex format, e.g. ".*blutopia.*" ".*example.*"')
    list_parser.add_argument('--message', nargs='+', help='Filter by one or more messages, in regex format, e.g. ".*unregistered.*" ".*error.*"')
    list_parser.add_argument('--hash', nargs='+', help='Filter by one or more torrent hashes, in regex format, e.g. ".*hash1.*" ".*hash2.*"')
    list_parser.add_argument('--torrent', nargs='+', help='Filter by one or more torrent names, in regex format, e.g. ".*torrent1.*" ".*torrent2.*"')
    list_parser.add_argument('--full', action='store_true', help='Show all torrents affected, not just the first 10')
    list_parser.add_argument('--delete', action='store_true', help='Delete torrents with matching messages')
    list_parser.add_argument('--yes-do-as-i-say', action='store_true', help='Delete torrents with matching messages without asking for confirmation')

    unused_parser = subparsers.add_parser('unusedfiles', help='Find files in torrent directory that are not used in any torrent')
    unused_parser.add_argument('--no-progress', '--np', action='store_true', help='Disable progress bar')
    unused_parser.add_argument('--full', action='store_true', help='Show all torrents affected, not just the first 10')
    unused_parser.add_argument('--delete', action='store_true', help='Delete files that are not used in any torrent')
    unused_parser.add_argument('--yes-do-as-i-say', action='store_true', help='Delete files that are not used in any torrent without asking for confirmation')
    
    unlinked_parser = subparsers.add_parser('unlinkedfiles', help='Find torrents that are not linked to any files')
    unlinked_parser.add_argument('--exclude-trackers', nargs='+', help='Exclude torrents with these trackers, in regex format, e.g. ".*blutopia.*" ".*example.*"')
    unlinked_parser.add_argument('--exclude-messages', nargs='+', help='Exclude torrents with these messages, in regex format, e.g. ".*unregistered.*" ".*error.*"')
    unlinked_parser.add_argument('--exclude-hashes', nargs='+', help='Exclude torrents with these hashes, in regex format, e.g. ".*hash1.*" ".*hash2.*"')
    unlinked_parser.add_argument('--exclude-categories', nargs='+', help='Exclude torrents with these categories, in regex format, e.g. ".*category1.*" ".*category2.*"')
    unlinked_parser.add_argument('--exclude-tags', nargs='+', help='Exclude torrents with these tags, in regex format, e.g. ".*tag1.*" ".*tag2.*"')
    unlinked_parser.add_argument('--include-trackers', nargs='+', help='Include torrents with these trackers, in regex format, e.g. ".*blutopia.*" ".*example.*"')
    unlinked_parser.add_argument('--include-messages', nargs='+', help='Include torrents with these messages, in regex format, e.g. ".*unregistered.*" ".*error.*"')
    unlinked_parser.add_argument('--include-hashes', nargs='+', help='Include torrents with these hashes, in regex format, e.g. ".*hash1.*" ".*hash2.*"')
    unlinked_parser.add_argument('--include-categories', nargs='+', help='Include torrents with these categories, in regex format, e.g. ".*category1.*" ".*category2.*"')
    unlinked_parser.add_argument('--include-tags', nargs='+', help='Include torrents with these tags, in regex format, e.g. ".*tag1.*" ".*tag2.*"')
    unlinked_parser.add_argument('--no-progress', '--np', action='store_true', help='Disable progress bar')
    unlinked_parser.add_argument('--delete', action='store_true', help='Delete torrents that are not linked to any files')
    unlinked_parser.add_argument('--yes-do-as-i-say', action='store_true', help='Delete torrents that are not linked to any files without asking for confirmation')

    args = parser.parse_args()
    config = load_config(args.config)
    client = connect_qbit(config)

    if args.command == 'status':
        qbit_status(client)
    elif args.command == 'overview':
        overview_torrents(client)
    elif args.command == 'listmessages':
        list_tracker_messages(client, args.no_progress, args.tracker, args.message, args.hash, args.torrent, args.full, args.delete, args.yes_do_as_i_say, args.path_prefix)
    elif args.command == 'unusedfiles':
        show_unused_files(client, args.no_progress, args.path_prefix, args.full, args.delete, args.yes_do_as_i_say)
    elif args.command == 'unlinkedfiles':
        handle_unlinked_files(client, args.exclude_trackers, args.exclude_messages, args.exclude_hashes, args.exclude_categories, args.exclude_tags, args.include_trackers, args.include_messages, args.include_hashes, args.include_categories, args.include_tags, args.no_progress, args.delete, args.yes_do_as_i_say, args.path_prefix)
    

if __name__ == '__main__':
    main()
import shutil
from getpass import getpass

import json
import os.path
import time
import datetime
from telethon import TelegramClient, ConnectionMode
from telethon.errors import SessionPasswordNeededError
from telethon.errors import (ServerError, FloodWaitError)
from telethon.tl.types import UpdateShortChatMessage, UpdateShortMessage
from telethon.utils import get_extension
from telethon.tl.types import (MessageMediaWebPage)

# Get the (current) number of lines in the terminal
cols, rows = shutil.get_terminal_size()


def sprint(string, *args, **kwargs):
    """Safe Print (handle UnicodeEncodeErrors on some terminals)"""
    try:
        print(string, *args, **kwargs)
    except UnicodeEncodeError:
        string = string.encode('utf-8', errors='ignore')\
                       .decode('ascii', errors='ignore')
        print(string, *args, **kwargs)


def print_title(title):
    # Clear previous window
    print('\n')
    print('=={}=='.format('=' * len(title)))
    sprint('= {} ='.format(title))
    print('=={}=='.format('=' * len(title)))


def bytes_to_string(byte_count):
    """Converts a byte count to a string (in KB, MB...)"""
    suffix_index = 0
    while byte_count >= 1024:
        byte_count /= 1024
        suffix_index += 1

    return '{:.2f}{}'.format(byte_count,
                             [' bytes', 'KB', 'MB', 'GB', 'TB'][suffix_index])


class InteractiveTelegramClient(TelegramClient):
    """Full featured Telegram client, meant to be used on an interactive
       session to see what Telethon is capable off -

       This client allows the user to perform some basic interaction with
       Telegram through Telethon, such as listing dialogs (open chats),
       talking to people, downloading media, and receiving updates.
    """
    def __init__(self, session_user_id, user_phone, api_id, api_hash, proxy=None):
        print_title('Initialization')

        print('Initializing interactive example...')
        super().__init__(session_user_id, api_id, api_hash, connection_mode=ConnectionMode.TCP_ABRIDGED, proxy=proxy)

        print('Connecting to Telegram servers...')
        if not self.connect():
            print('Initial connection failed. Retrying...')
            if not self.connect():
                print('Could not connect to Telegram servers.')
                return

        # Then, ensure we're authorized and have access
        if not self.is_user_authorized():
            print('First run. Sending code request...')
            self.send_code_request(user_phone)

            self_user = None
            while self_user is None:
                code = input('Enter the code you just received: ')
                try:
                    self_user = self.sign_in(user_phone, code)

                # Two-step verification may be enabled
                except SessionPasswordNeededError as e:
                    pw = getpass('Two step verification is enabled. '
                                 'Please enter your password: ')

                    self_user = self.sign_in(password=pw)

    def run(self):
        os.makedirs("output/dumps", exist_ok=True)
        os.makedirs("output/usermedia", exist_ok=True)

        # Entities represent the user, chat or channel
        # corresponding to the dialog on the same index
        dialogs, entities = self.get_dialogs(limit=70000)

        dumps = {}
        minId = {}
        maxId = {}
        allowedIds = []

        if os.path.exists("output/offsets.json"):
            with open("output/offsets.json") as outfile:
                maxIdJson = json.load(outfile)
                for key in maxIdJson:
                    maxId[int(key)] = maxIdJson[key]

        if os.path.exists("output/allow.json"):
            with open("output/allow.json") as allowfile:
                jdata = json.load(allowfile)
                allowedIds = jdata["Allow"]

        for entity in entities:
            if entity.id not in allowedIds:
                continue

            minId[entity.id] = 2147483647

            if entity.id not in maxId:
                maxId[entity.id] = 0

            currentMaxId = maxId[entity.id]

            while True:
                try:
                    total_count, messages, senders = self.get_message_history(entity, limit=200, offset_id=minId[entity.id], min_id=maxId[entity.id])

                    if len(messages) == 0:
                        break

                    for msg, sender in zip(messages, senders):
                        if msg.id < minId[entity.id]:
                            minId[entity.id] = msg.id

                        if msg.id > currentMaxId:
                            currentMaxId = msg.id

                        senderName = "???"
                        if sender:
                            senderName = getattr(sender, 'first_name', None)
                            if not senderName:
                                senderName = getattr(sender, 'title', None)
                                if not senderName:
                                    senderName = str(sender.id)
                        
                        content = ""
                        senderName = senderName.replace("/", "-")

                        # Format the message content
                        if getattr(msg, 'media', None):
                            if type(msg.media) == MessageMediaWebPage:
                                caption = getattr(msg.media, 'caption', '')
                                photo = getattr(msg.media.webpage, 'photo', None)
                                url = getattr(msg.media.webpage, 'url', '')
                                site_name = getattr(msg.media.webpage, 'site_name', '')
                                title = getattr(msg.media.webpage, 'title', '')
                                description = getattr(msg.media.webpage, 'description', '')
                                content = '[[web]:{}] {}'.format({
                                    "url": url,
                                    "site_name": site_name,
                                    "title": title,
                                    "description": description}, caption)
                                if photo is not None:
                                    msg_media_id = int(msg.id)
                                    output = str('output/usermedia/{}/{}'.format(senderName, msg_media_id)) + ".jpg"
                                    if not os.path.exists(output):
                                        print('Downloading Web picture with name {}...'.format(output))
                                        output = self._download_photo(msg.media.webpage, output, None, self.download_progress_callback)
                                        print('Web picture downloaded to {}!'.format(output))
                                    else:
                                        print('Web picture already downloaded to {}!'.format(output))
                            else: #photo, #document, #contact
                                msg_media_id = int(msg.id)
                                # Let the output be the message ID
                                output = str('output/usermedia/{}/{}'.format(senderName, msg_media_id))
                                ext = get_extension(msg.media)
                                if ext is None:
                                    ext = ""
                                if not os.path.exists(output + ext):
                                    print('Downloading media with name {}...'.format(output))
                                    output = self.download_media(msg.media, output, self.download_progress_callback)
                                    print('Media downloaded to {}!'.format(output))
                                else:
                                    print('Media already downloaded to {}!'.format(output))

                                #The media may or may not have a caption
                                caption = getattr(msg.media, 'caption', '')
                                content = '<{}> {}'.format(type(msg.media).__name__, caption)
                        elif hasattr(msg, 'message'):
                            content = msg.message
                        elif hasattr(msg, 'action'):
                            content = str(msg.action)
                        else:
                            # Unknown message, simply print its class name
                            content = type(msg).__name__

                        if senderName not in dumps:
                            dumps[senderName] = []
                            print("Added sender: " + senderName)

                        dump = json.dumps({
                            "date": str(msg.date),
                            "id": msg.id,
                            "content" : content})

                        dumps[senderName].append(dump)

                except ServerError:
                    time.sleep(2)
                except FloodWaitError as e:
                    print("Flood, waiting " + str(e.seconds) + " seconds.")
                    time.sleep(e.seconds)
                    self.reconnect() # we most likely timedout..
                finally:
                    time.sleep(1)

            maxId[entity.id] = currentMaxId

        suffix = datetime.datetime.now().strftime("%y%m%d_%H%M%S")
        for key in dumps:
            with open("output/dumps/" + key + "_" + suffix + ".json", 'w') as outfile:
                json.dump(dumps[key], outfile)

        with open("output/offsets.json", "w") as outfile:
            json.dump(maxId, outfile)

    def send_photo(self, path, entity):
        print('Uploading {}...'.format(path))
        input_file = self.upload_file(
            path, progress_callback=self.upload_progress_callback)

        # After we have the handle to the uploaded file, send it to our peer
        self.send_photo_file(input_file, entity)
        print('Photo sent!')

    def send_document(self, path, entity):
        print('Uploading {}...'.format(path))
        input_file = self.upload_file(
            path, progress_callback=self.upload_progress_callback)

        # After we have the handle to the uploaded file, send it to our peer
        self.send_document_file(input_file, entity)
        print('Document sent!')

    @staticmethod
    def download_progress_callback(downloaded_bytes, total_bytes):
        InteractiveTelegramClient.print_progress('Downloaded',
                                                 downloaded_bytes, total_bytes)

    @staticmethod
    def upload_progress_callback(uploaded_bytes, total_bytes):
        InteractiveTelegramClient.print_progress('Uploaded', uploaded_bytes,
                                                 total_bytes)

    @staticmethod
    def print_progress(progress_type, downloaded_bytes, total_bytes):
        print('{} {} out of {} ({:.2%})'.format(progress_type, bytes_to_string(
            downloaded_bytes), bytes_to_string(total_bytes), downloaded_bytes /
                                                total_bytes))

    @staticmethod
    def update_handler(update_object):
        if type(update_object) is UpdateShortMessage:
            if update_object.out:
                sprint('You sent {} to user #{}'.format(
                    update_object.message, update_object.user_id))
            else:
                sprint('[User #{} sent {}]'.format(
                    update_object.user_id, update_object.message))

        elif type(update_object) is UpdateShortChatMessage:
            if update_object.out:
                sprint('You sent {} to chat #{}'.format(
                    update_object.message, update_object.chat_id))
            else:
                sprint('[Chat #{}, user #{} sent {}]'.format(
                       update_object.chat_id, update_object.from_id,
                       update_object.message))

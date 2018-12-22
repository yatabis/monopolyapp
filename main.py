from base64 import b64encode
import json
import os
from uuid import uuid4

from bottle import get, post, request, run
from bottle import jinja2_template as render
from pprint import pprint
import psycopg2
from psycopg2.extras import DictCursor
import qrcode
import requests

CAT = os.environ.get('CHANNEL_ACCESS_TOKEN')
HEADER = {'Contetnt-Type': 'application/json', 'Authprization': f"Bearer {CAT}"}
DATABASE = os.environ.get('DATABASE_URL')


# database
def connect_db():
    return psycopg2.connect(DATABASE)


def get_room(room_id=None):
    with connect_db() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            if room_id is None:
                cur.execute('select * from room')
            else:
                cur.execute('select * from room where room_id = %s', (room_id,))
            return cur.fetchall()


def get_player(user_id=None, room=None):
    with connect_db() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            if user_id is not None:
                cur.execute('select * from player where line_id = %s', (line_id,))
            elif room is not None:
                cur.execute('select * from player where room_id = %s', (room,))
            else:
                cur.execute('select * from player')
            return cur.fetchall


# LINE API
def push_text(to, text):
    ep = "https://api.line.me/v2/bot/message/push"
    body = {'to': to, 'messages': [{'type': 'text', 'text': text}]}
    return requests.post(ep, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers=HEADER)


@get('/api/display-name/<line_id>')
def get_display_name(line_id=None):
    if line_id is None:
        return "line_id is None."
    ep = f"https://api.line.me/v2/bot/profile/{line_id}"
    req = requests.get(ep, headers=HEADER)
    return req.json().get('displayName')


# functions
def create_new_room():
    room_id = str(b64encode(str(uuid4()).encode('utf-8')))[2:-1].lower()
    room_qr = qrcode.make(f"line://app/1629635023-JwWZbqzz?room={room_id}")
    room_qr.save(f'room/{room_id}.png')
    with connect_db() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('insert into room (room_id, state) values (%s, %s);', (room_id, "starting"))
    return room_id


# callback
@get('/make-room')
def make_room():
    pass


if __name__ == '__main__':
    run(host='0.0.0.0', port=int(os.environ.get(PORT, 443)))
